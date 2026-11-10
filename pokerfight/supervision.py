"""A hard local response boundary around a persistent worker process.

The parent's watchdog can kill a blocked sampler. The official adapter still
needs to include receiving/parsing/network time in its absolute deadline.
"""
from dataclasses import asdict
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
from time import perf_counter

from .domain import Action, safe_action
from .equity import EquityResult
from .strategy import Decision


class SupervisedPolicy:
    def __init__(self, config, timeout_ms=4250, command=None, policy="v4"):
        if timeout_ms < 1:
            raise ValueError("timeout_ms debe ser positivo")
        if policy not in ("v2", "v4", "v4rb", "v5", "v6", "v7"):
            raise ValueError("Política supervisada desconocida")
        self.config = config
        self.timeout_ms = timeout_ms
        self.command = command or [sys.executable, "-m", "pokerfight.search_worker", json.dumps(asdict(config)), policy]
        self.process = None
        self.request_id = 0
        # Warmup is explicit and outside individual calls in persistent serve.
        self._start(perf_counter() + 10)

    def _start(self, deadline):
        inbox = queue.Queue()
        self.inbox = inbox
        self.process = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1,
            cwd=Path(__file__).resolve().parents[1],
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        process = self.process

        def read():
            try:
                for line in process.stdout:
                    inbox.put(json.loads(line))
            except Exception as error:
                inbox.put({"error": str(error)})
            finally:
                inbox.put({"error": "worker_closed"})
                process.stdout.close()

        threading.Thread(target=read, daemon=True).start()
        try:
            message = inbox.get(timeout=max(0, deadline - perf_counter()))
            if not message.get("ready"):
                raise RuntimeError(message)
        except Exception:
            self.close()
            raise

    def decide(self, obs, *, deadline=None):
        started = perf_counter()
        local_deadline = started + self.timeout_ms / 1000
        deadline = local_deadline if deadline is None else min(deadline, local_deadline)
        if deadline <= started:
            return Decision(safe_action(obs), "supervisor:deadline", 0, True)
        try:
            if self.process is None or self.process.poll() is not None:
                self._start(deadline)
            self.request_id += 1
            request = {"request_id": self.request_id, "observation": asdict(obs)}
            process, inbox = self.process, self.inbox
            payload = json.dumps(request) + "\n"

            def write():
                try:
                    process.stdin.write(payload)
                    process.stdin.flush()
                except Exception as error:
                    inbox.put({"error": str(error)})

            # A child that stops reading can block even the pipe write. Keep
            # that operation outside the watchdog thread as well.
            threading.Thread(target=write, daemon=True).start()
            message = self.inbox.get(timeout=max(0, deadline - perf_counter()))
            if message.get("request_id") != self.request_id:
                raise RuntimeError(message.get("error", "worker_request_mismatch"))
            d = message["decision"]
            action = Action(**d["action"])
            if not action.is_legal(obs):
                raise ValueError("worker_illegal_action")
            return Decision(action, d["reason"], (perf_counter() - started) * 1000, d["fallback"],
                            EquityResult(**d["equity"]) if d["equity"] else None, d.get("search"))
        except Exception as error:
            self.close()
            return Decision(safe_action(obs), f"supervisor:{type(error).__name__}:{error}",
                            (perf_counter() - started) * 1000, True)

    def close(self):
        process, self.process = self.process, None
        if process is not None:
            if process.poll() is None:
                try:
                    process.kill()
                except OSError:
                    pass
            try:
                process.wait(timeout=.1)
            except subprocess.TimeoutExpired:
                pass
            if process.stdin:
                try:
                    process.stdin.close()
                except OSError:
                    pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
