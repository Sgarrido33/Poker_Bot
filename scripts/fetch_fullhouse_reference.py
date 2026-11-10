"""Fetch only pinned original Fullhouse runtime files for reference parity.

Does not fetch or execute the separate Fullhouse engine. The adapter, weights
and license already ship in pokerfight/external/fullhouse for offline use.
"""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen


def main():
    base = Path(__file__).resolve().parents[1]
    manifest = json.loads((base / "pokerfight/external/fullhouse/SOURCE.json").read_text(encoding="utf-8"))
    destination = base / "research/external_sources/fullhouse"
    for name, digest in manifest["original_files"].items():
        target = destination / name
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == digest:
            continue
        url = f"https://raw.githubusercontent.com/advitrocks9/fullhouse-bot/{manifest['commit']}/{name}"
        with urlopen(url, timeout=30) as response:
            raw = response.read()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError(f"Upstream bytes changed: {name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    print(f"Pinned reference verified: {manifest['commit']}")


if __name__ == "__main__":
    main()
