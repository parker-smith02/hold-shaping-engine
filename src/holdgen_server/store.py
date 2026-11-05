"""The hold library: one `holds/<name>.json` file per spec, formatted for clean git diffs."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import tempfile
from pathlib import Path

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,79}$")


class StoreError(ValueError):
    pass


def _fmt_points(obj):
    """JSON with each [a, b] pair on one line: specs are mostly point lists, and one point per line
    keeps diffs of a moved control point to a single line."""
    text = json.dumps(obj, indent=2, ensure_ascii=False)
    return re.sub(r"\[\s+(-?[\d.eE+-]+),\s+(-?[\d.eE+-]+)(?:,\s+(-?[\d.eE+-]+))?\s+\]",
                  lambda m: "[" + ", ".join(g for g in m.groups() if g is not None) + "]", text) + "\n"


class HoldStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        if not NAME_RE.match(name):
            raise StoreError(f"invalid hold name {name!r}: use lowercase letters, digits, '_', '.', '-'")
        return self.root / f"{name}.json"

    def list(self) -> list[dict]:
        out = []
        for p in sorted(self.root.glob("*.json")):
            try:
                d = json.loads(p.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            out.append({"name": p.stem, "stations": len(d.get("stations", [])),
                        "description": d.get("description", "")[:200],
                        "updated": dt.datetime.fromtimestamp(p.stat().st_mtime, dt.timezone.utc).isoformat()})
        return sorted(out, key=lambda h: h["updated"], reverse=True)

    def get(self, name: str) -> dict:
        p = self._path(name)
        if not p.exists():
            raise FileNotFoundError(name)
        return json.loads(p.read_text())

    def put(self, name: str, spec: dict) -> None:
        p = self._path(name)
        fd, tmp = tempfile.mkstemp(dir=self.root, prefix=f".{name}.", suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            f.write(_fmt_points(spec))
        os.replace(tmp, p)                                   # atomic on POSIX and Windows

    def delete(self, name: str) -> None:
        p = self._path(name)
        if not p.exists():
            raise FileNotFoundError(name)
        p.unlink()
