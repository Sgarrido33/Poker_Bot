"""Persistent observation-only adapter for a locally trained NoRegrets blueprint."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
from pathlib import Path
import queue
import subprocess
import threading
import sys
from time import perf_counter

from .domain import Action, Observation
from .strategy import Decision


@dataclass(frozen=True)
class NoRegretsDecision(Decision):
    external: dict | None = None

    def to_dict(self) -> dict:
        result = super().to_dict()
        result["external"] = self.external
        return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class NoRegretsOpponent:
    """Keep one Rust daemon alive; public state is rebuilt and checked per request.

    `profile_manifest` is a JSON sidecar containing the original training keys
    plus `artifact_path` and `sha256`. No arena deck or opponent cards cross the
    process boundary.
    """

    def __init__(self, seed: int, profile_manifest: str | Path, *,
                 executable: str | Path | None = None, executable_sha256: str | None = None,
                 timeout_s: float = 12.0):
        self.seed = int(seed)
        self.manifest_path = Path(profile_manifest).resolve()
        self.profile = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        artifact_value = self.profile.get("artifact_path", self.profile.get("artifact"))
        if not artifact_value:
            raise ValueError("NoRegrets profile sidecar must name artifact_path")
        self.blueprint = (self.manifest_path.parent / artifact_value).resolve() if not Path(artifact_value).is_absolute() else Path(artifact_value)
        expected = self.profile.get("sha256", self.profile.get("artifact_sha256"))
        if not expected or _sha256(self.blueprint).casefold() != str(expected).casefold():
            raise ValueError("NoRegrets blueprint SHA-256 does not match profile sidecar")
        if executable is None:
            root = Path(__file__).resolve().parents[1]
            executable = root / "research/noregrets_integration_20261028/artifacts/noregrets-pokerfight-adapter.exe"
        self.executable = Path(executable).resolve()
        if not self.executable.is_file():
            raise FileNotFoundError(f"NoRegrets adapter executable missing: {self.executable}")
        runtime_manifest = self.executable.with_suffix(".runtime.json")
        if executable_sha256 is None:
            if not runtime_manifest.is_file():
                raise FileNotFoundError("NoRegrets adapter runtime SHA sidecar is required")
            executable_sha256 = json.loads(runtime_manifest.read_text(encoding="utf-8"))["sha256"]
        if _sha256(self.executable).casefold() != str(executable_sha256).casefold():
            raise ValueError("NoRegrets adapter executable SHA-256 mismatch")
        if not 0.1 <= timeout_s <= 120:
            raise ValueError("timeout_s must be in [0.1,120]")
        self.timeout_s = timeout_s
        self._lock = threading.Lock()
        self._lines: queue.Queue = queue.Queue()
        self._process: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._stderr = self.manifest_path.parent / "adapter_stderr.log"
        self.telemetry = {"decisions": 0, "fallbacks": 0, "transferred_stack": 0,
                          "menu_mismatch": 0, "timeouts": 0, "restarts": 0,
                          "unseen_infoset": 0, "zero_mass": 0, "legal_translations": 0}

    def _start(self) -> None:
        if self._process:
            if self._process.poll() is None:
                return
            self._terminate()
        inbox = queue.Queue()
        self._lines = inbox
        err = self._stderr.open("a", encoding="utf-8")
        try:
            self._process = subprocess.Popen(
                [str(self.executable), "serve", "--blueprint", str(self.blueprint),
                 "--manifest", str(self.manifest_path)], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=err, text=True, encoding="utf-8", bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        finally:
            err.close()
        self._reader = threading.Thread(target=self._read_stdout, args=(self._process, inbox), daemon=True)
        self._reader.start()

    def _read_stdout(self, process: subprocess.Popen, inbox: queue.Queue) -> None:
        assert process.stdout is not None
        try:
            for line in process.stdout:
                inbox.put(line)
        except Exception as error:
            inbox.put({"__reader_error__": str(error)})
        finally:
            inbox.put(None)
            process.stdout.close()

    def _restart_after_timeout(self, *, timed_out: bool = True) -> None:
        self._terminate()
        if timed_out:
            self.telemetry["timeouts"] += 1
        self.telemetry["restarts"] += 1

    def decide(self, obs: Observation) -> NoRegretsDecision:
        started = perf_counter()
        if obs.big_blind != self.profile.get("bb", 100):
            raise ValueError("NoRegrets profile big blind mismatch")
        if len(obs.players) != self.profile.get("players"):
            raise ValueError("NoRegrets blueprint player count mismatch; choose matching trained profile")
        # Seed depends only on public observation and this seat's fixed seed.
        stable = (self.seed, obs.table_id, obs.hand_id, obs.hero_id,
                  tuple((a.event_id, a.player_id, a.street, a.kind, a.amount) for a in obs.history))
        query_seed = int.from_bytes(hashlib.sha256(repr(stable).encode()).digest()[:8], "big")
        payload = asdict(obs)
        payload["seed"] = query_seed
        with self._lock:
            self._start()
            process, inbox = self._process, self._lines
            assert process and process.stdin
            deadline = started + self.timeout_s

            def send():
                try:
                    process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
                    process.stdin.flush()
                except Exception as error:
                    inbox.put({"__write_error__": str(error)})

            threading.Thread(target=send, daemon=True).start()
            try:
                line = inbox.get(timeout=max(0.0, deadline - perf_counter()))
            except queue.Empty:
                self._restart_after_timeout()
                raise TimeoutError(f"NoRegrets adapter exceeded {self.timeout_s}s and was restarted")
            if line is None or isinstance(line, dict):
                error = line if isinstance(line, dict) else {"worker_closed": True}
                self._restart_after_timeout(timed_out=False)
                raise RuntimeError(f"NoRegrets adapter I/O failure: {error}")
            if perf_counter() > deadline:
                self._restart_after_timeout()
                raise TimeoutError(f"NoRegrets adapter exceeded {self.timeout_s}s and was restarted")
        result = json.loads(line)
        if not result.get("ok"):
            raise ValueError(f"NoRegrets rejected observation: {result.get('error')}")
        raw = result["action"]
        action = Action(raw["kind"], raw.get("amount", 0))
        if not action.is_legal(obs):
            raise RuntimeError(f"NoRegrets returned illegal action: {raw}")
        self.telemetry["decisions"] += 1
        self.telemetry["fallbacks"] += int(result["fallback"])
        self.telemetry["transferred_stack"] += int(result["profile_transfer"])
        self.telemetry["menu_mismatch"] += int(result["menu_mismatches_delta"] > 0)
        self.telemetry["unseen_infoset"] += int(result["fallback_reason"] == "unseen_infoset")
        self.telemetry["zero_mass"] += int(result["fallback_reason"] == "zero_mass")
        self.telemetry["legal_translations"] += len(result["legal_translations"])
        external = {k: result[k] for k in ("iterations", "profile_players", "profile_stack",
                    "observed_start_stacks", "profile_transfer", "fallback",
                    "lookup_stats_delta", "menu_mismatches_delta", "menu_mismatch_sizes",
                    "fallback_reason", "fallback_reason_stats_delta", "legal_translations", "candidates", "seed")
                   if k in result}
        fallback_reason = result.get("fallback_reason", "unseen_infoset" if result["fallback"] else "none")
        external["fallback_reason"] = fallback_reason
        suffix = (":menu_mismatch_fallback" if fallback_reason == "menu_mismatch"
                  else ":sparse_fallback" if result["fallback"] else ":lookup")
        return NoRegretsDecision(action, "external:noregrets" + suffix,
                                 (perf_counter() - started) * 1000, bool(result["fallback"]), external=external)

    def close(self) -> None:
        with self._lock:
            self._terminate()

    def _terminate(self) -> None:
        process, self._process = self._process, None
        if not process:
            return
        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        for stream in (process.stdin, process.stdout):
            if stream:
                try:
                    stream.close()
                except OSError:
                    pass

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()


class NoRegretsTableOpponent:
    """Select the trained blueprint matching the current live seat count.

    At most one child and one loaded blueprint are retained. A bust-out that
    changes table cardinality closes the previous daemon before loading the
    newly matching profile.
    """

    def __init__(self, seed: int, profiles_manifest: str | Path, *,
                 executable: str | Path | None = None, executable_sha256: str | None = None,
                 timeout_s: float = 12.0):
        self.seed = int(seed)
        self.profiles_manifest = Path(profiles_manifest).resolve()
        self.executable = executable
        self.executable_sha256 = executable_sha256
        self.timeout_s = timeout_s
        self._active_players: int | None = None
        self._active: NoRegretsOpponent | None = None
        self.telemetry = {"profile_switches": 0, "decisions": 0}

    def _profile_for(self, players: int) -> Path:
        if not 2 <= players <= 6:
            raise ValueError("NoRegrets table supports 2..6 live players")
        source = self.profiles_manifest
        if source.is_dir():
            choices = sorted(source.glob(f"noregrets_{players}max*.json"))
            choices = [p for p in choices if "repeat" not in p.stem.casefold()]
            if not choices:
                raise ValueError(f"no profile for {players}-max in {source}")
            # Prefer the highest-iteration training budget when a directory has
            # multiple variants; an explicit index selects any intended profile.
            choices.sort(key=lambda p: (json.loads(p.read_text(encoding="utf-8")).get("iterations", 0),
                                        json.loads(p.read_text(encoding="utf-8")).get("stack", 0), p.name),
                         reverse=True)
            return choices[0]
        index = json.loads(source.read_text(encoding="utf-8"))
        profiles = index.get("profiles", index)
        value = profiles.get(str(players), profiles.get(f"{players}-max"))
        if not isinstance(value, str):
            raise ValueError(f"profiles manifest has no path for {players}-max")
        path = Path(value)
        return path.resolve() if path.is_absolute() else (source.parent / path).resolve()

    def decide(self, obs: Observation) -> NoRegretsDecision:
        started = perf_counter()
        n = len(obs.players)
        if self._active is None or self._active_players != n:
            if self._active:
                self._active.close()
            profile = self._profile_for(n)
            self._active = NoRegretsOpponent(self.seed, profile, executable=self.executable,
                executable_sha256=self.executable_sha256, timeout_s=self.timeout_s)
            self._active_players = n
            self.telemetry["profile_switches"] += 1
        result = self._active.decide(obs)
        self.telemetry["decisions"] += 1
        return replace(result, elapsed_ms=(perf_counter() - started) * 1000)

    def close(self) -> None:
        if self._active:
            self._active.close()
        self._active = None
        self._active_players = None

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
