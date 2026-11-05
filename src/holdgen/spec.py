"""Engine-facing spec: validate with `schema`, then lower to the plain dict the geometry modules use.

The engine works on a normalized dict (sorted stations, explicit root landmarks,
`landmark_order`) rather than the pydantic model, so the numeric code stays free of
model plumbing.
"""
from __future__ import annotations

import json

from . import schema


class SpecError(ValueError):
    def __init__(self, issues):
        self.issues = issues
        super().__init__("; ".join(i.message for i in issues if i.level == "error"))


def lower(model: schema.HoldSpec) -> dict:
    d = model.dump()
    st = sorted(d["stations"], key=lambda s: s["x"])
    for s, m in zip(st, sorted(model.stations, key=lambda s: s.x)):
        s["landmarks"] = dict(schema.landmark_order(m))
    d["stations"] = st
    d["landmark_order"] = [k for k, _ in schema.landmark_order(sorted(model.stations, key=lambda s: s.x)[0])]
    return d


def normalize(raw: dict) -> dict:
    """Validate a raw spec dict and return the engine dict. Raises SpecError on errors."""
    model, issues = schema.validate(raw)
    if model is None or any(i.level == "error" for i in issues):
        raise SpecError(issues)
    return lower(model)


def load(path) -> dict:
    with open(path) as f:
        return normalize(json.load(f))
