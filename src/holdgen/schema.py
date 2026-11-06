"""hold-spec/1: the single definition of the spec format.

The pydantic models below are the source of truth. From them we derive:
  * structural validation (pydantic) + semantic checks (`check`), returned as `Issue`s
  * schema/hold-spec.schema.json   (`holdgen schema`)
  * web/src/spec/types.gen.ts      (`holdgen codegen`, see codegen.py)

Frame (mm): x along the hold, y up the wall, z out of the wall; the back is z = 0.
Section points are [z, y] pairs: drawn with the wall on the left, up is up the wall.
"""
from __future__ import annotations

from collections import Counter
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

SCHEMA_ID = "hold-spec/1"
ROOTS = ("bottom_root", "ledge_root")

Vec2 = tuple[float, float]
Vec3 = tuple[float, float, float]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Station(_Model):
    """A drawn cross-section. Authoritative: the built hold matches it within the voxel tolerance."""
    x: float = Field(description="Position along the hold (mm).")
    points: list[Vec2] = Field(min_length=3, description="Control points [z, y]. First = bottom root on the wall, "
                               "then up the face, over the lip, down the ledge; last = ledge root on the wall.")
    landmarks: dict[str, int] = Field(default_factory=dict, description="Landmark name -> point index. "
                                      "bottom_root/ledge_root are implicit. Same names, same order on every station.")
    corners: list[int] = Field(default_factory=list, description="Point indices where the spline has a sharp corner.")
    note: str = ""


def _split_loop(pts: list, key: int) -> tuple[list, list]:
    """Split a closed loop at its leftmost and rightmost points into two open chains, each running
    left to right. Returns (chain with the larger mean of coordinate `key`, the other)."""
    n = len(pts)
    i0 = min(range(n), key=lambda i: (pts[i][0], i))
    i1 = max(range(n), key=lambda i: (pts[i][0], -i))
    fwd = [pts[(i0 + k) % n] for k in range((i1 - i0) % n + 1)]
    back = [pts[(i0 - k) % n] for k in range((i0 - i1) % n + 1)]
    mean = lambda c: sum(q[key] for q in c) / len(c)
    return (fwd, back) if mean(fwd) >= mean(back) else (back, fwd)


def _is_point_list(v) -> bool:
    return isinstance(v, list) and len(v) >= 3 and all(isinstance(q, (list, tuple)) and len(q) == 2 for q in v)


_STRENGTH = Field(0.5, ge=0, le=1, description="Influence between stations. Zero at every station regardless.")


class FrontView(_Model):
    """Loose guide seen from the front ([x, y]): the hold's upper and lower edge, each an open curve
    from the left tip to the right tip. The two edges share their end points (the tips)."""
    upper: list[Vec2] = Field(min_length=2, description="Upper edge [x, y], left tip to right tip.")
    lower: list[Vec2] = Field(min_length=2, description="Lower edge [x, y], left tip to right tip.")
    strength: float = _STRENGTH

    @model_validator(mode="before")
    @classmethod
    def _from_loop(cls, data):
        """Earlier files stored the front view as one closed loop: split it at the tips."""
        if isinstance(data, dict) and "points" in data and "upper" not in data and "lower" not in data:
            data = dict(data)
            pts = data.pop("points")
            data.pop("corners", None)
            if _is_point_list(pts):
                data["upper"], data["lower"] = _split_loop([list(q) for q in pts], key=1)
        return data


class TopView(_Model):
    """Loose guide seen from above ([x, z]): an open curve from the wall at the left end, out over the
    hold, back to the wall at the right end. First and last points sit on the wall (z = 0)."""
    points: list[Vec2] = Field(min_length=3)
    strength: float = _STRENGTH
    corners: list[int] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _from_loop(cls, data):
        """Earlier files could store a closed top outline: keep its outer chain and drop its ends to the wall."""
        if isinstance(data, dict) and _is_point_list(data.get("points")):
            pts = [list(q) for q in data["points"]]
            if abs(pts[0][1]) > 0.05 and abs(pts[-1][1]) > 0.05:      # neither end on the wall: a loop
                outer, _ = _split_loop(pts, key=1)
                outer[0], outer[-1] = [outer[0][0], 0.0], [outer[-1][0], 0.0]
                data = {**data, "points": outer, "corners": []}
        return data


class Dent(_Model):
    type: Literal["dent"]
    surface: Optional[Literal["front", "ledge"]] = Field(None, description="With a 2D center: 'front' = [x, y], 'ledge' = [x, z].")
    center: list[float] = Field(min_length=2, max_length=3)
    size: Vec3 = Field((8.0, 8.0, 4.0), description="1-sigma radii along x, y, z (mm).")
    depth: float = Field(description="mm; positive removes material, negative adds.")
    note: str = ""


class Groove(_Model):
    type: Literal["groove"]
    surface: Optional[Literal["front", "ledge"]] = None
    path: list[list[float]] = Field(min_length=2)
    width: float = Field(6.0, gt=0)
    depth: float
    note: str = ""


Feature = Annotated[Union[Dent, Groove], Field(discriminator="type")]


class Mounting(_Model):
    screws: list[Vec2] = Field(default_factory=list, description="Screw positions [x, y] on the wall.")
    hole_dia: float = Field(4.8, gt=0)
    countersink_dia: float = Field(10.0, gt=0)


class EndCaps(_Model):
    radius: float = Field(6.0, gt=0, description="Rounded end used where no view extends past the outermost station.")


class BuildSettings(_Model):
    voxel: float = Field(0.3, ge=0.05, le=2.0)
    smooth_sigma_vox: float = Field(0.5, ge=0)
    sample_step: float = Field(0.2, gt=0, le=2.0)


class NoteAnchor(_Model):
    view: Literal["front", "top", "section"]
    at: Vec2
    station_x: Optional[float] = None


class Note(_Model):
    anchor: NoteAnchor
    text: str = ""


class HoldSpec(_Model):
    schema_id: Literal["hold-spec/1"] = Field(SCHEMA_ID, alias="schema")
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,79}$")
    units: Literal["mm"] = "mm"
    wall_angle_deg: float = Field(45.0, ge=0, le=90)
    description: str = ""
    stations: list[Station] = Field(min_length=2)
    front_view: Optional[FrontView] = None
    top_view: Optional[TopView] = None
    end_caps: EndCaps = Field(default_factory=EndCaps)
    features: list[Feature] = Field(default_factory=list)
    mounting: Mounting = Field(default_factory=Mounting)
    build: BuildSettings = Field(default_factory=BuildSettings)
    notes: list[Note] = Field(default_factory=list)

    def dump(self) -> dict:
        return self.model_dump(by_alias=True, mode="json")


class Issue(_Model):
    level: Literal["error", "warning"]
    code: str
    message: str
    path: list[Union[str, int]] = Field(default_factory=list)


# ---------------------------------------------------------------------------- semantic checks

def landmark_order(st: Station) -> list[tuple[str, int]]:
    lm = {**st.landmarks, "bottom_root": 0, "ledge_root": len(st.points) - 1}
    return sorted(lm.items(), key=lambda kv: kv[1])


def check(spec: HoldSpec) -> list[Issue]:
    out: list[Issue] = []

    def err(code, msg, *path):
        out.append(Issue(level="error", code=code, message=msg, path=list(path)))

    def warn(code, msg, *path):
        out.append(Issue(level="warning", code=code, message=msg, path=list(path)))

    xs = [s.x for s in spec.stations]
    if len({round(x, 6) for x in xs}) != len(xs):
        err("station.duplicate_x", "Two stations share the same x.", "stations")

    orders = []
    for i, s in enumerate(spec.stations):
        tag = f"Station x = {s.x:g}"
        n = len(s.points)
        for j, (z, _) in enumerate(s.points):
            if z < -1e-6:
                err("station.behind_wall", f"{tag}: point {j} is behind the wall (z < 0).", "stations", i, "points", j)
        for end, j in (("first", 0), ("last", n - 1)):
            if abs(s.points[j][0]) > 0.05:
                err("station.root_off_wall", f"{tag}: the {end} point must sit on the wall (z = 0).", "stations", i, "points", j)
        if s.points[0][1] >= s.points[-1][1]:
            err("station.direction", f"{tag}: draw from the bottom root up the face and back down the ledge; "
                "the first point must be lower than the last.", "stations", i)
        for name, j in s.landmarks.items():
            if name in ROOTS:
                err("landmark.reserved", f"{tag}: '{name}' is implicit; don't list it.", "stations", i, "landmarks", name)
            elif not 0 < j < n - 1:
                err("landmark.range", f"{tag}: landmark '{name}' must be an interior point index (1..{n - 2}).",
                    "stations", i, "landmarks", name)
        if len(set(s.landmarks.values())) != len(s.landmarks):
            err("landmark.shared_point", f"{tag}: two landmarks sit on the same point.", "stations", i, "landmarks")
        for c in s.corners:
            if not 0 < c < n - 1:
                err("corner.range", f"{tag}: corner index {c} must be an interior point.", "stations", i, "corners")
        orders.append(tuple(k for k, _ in landmark_order(s)))

    # the landmark sequence most stations use is the reference; flag the stations that differ
    if orders:
        ref = Counter(orders).most_common(1)[0][0]
        for i, (s, o) in enumerate(zip(spec.stations, orders)):
            if o != ref:
                inner = lambda t: ", ".join(k for k in t if k not in ROOTS) or "none"
                err("landmark.mismatch", f"Station x = {s.x:g}: landmarks ({inner(o)}) don't match the other "
                    f"stations ({inner(ref)}) in the same order along the curve.", "stations", i, "landmarks")
        if not any("lip_apex" in s.landmarks for s in spec.stations):
            warn("landmark.no_lip_apex", "No lip_apex landmark; readouts use the highest point of each section.")

    fv = spec.front_view
    if fv is not None:
        for end, j in (("left", 0), ("right", -1)):
            if max(abs(a - b) for a, b in zip(fv.upper[j], fv.lower[j])) > 0.05:
                err("front_view.tips", f"Front view: the upper and lower edges must meet at the {end} tip.", "front_view")
        x0, x1 = fv.upper[0][0], fv.upper[-1][0]
        if x0 >= x1:
            err("front_view.direction", "Front view: the left tip must be left of the right tip.", "front_view")
        else:
            for edge in ("upper", "lower"):
                for j, (x, _) in enumerate(getattr(fv, edge)[1:-1], 1):
                    if not x0 < x < x1:
                        err("front_view.outside_tips", f"Front view: {edge} point {j} is outside the tips "
                            f"(x {x0:g} to {x1:g}).", "front_view", edge, j)
    tv = spec.top_view
    if tv is not None:
        p = tv.points
        if any(z < -1e-6 for _, z in p):
            err("top_view.behind_wall", "Top view points must have z >= 0.", "top_view", "points")
        if abs(p[0][1]) > 0.05 or abs(p[-1][1]) > 0.05:
            err("top_view.ends_off_wall", "Top view: the first and last points must sit on the wall (z = 0).", "top_view")
        if p[0][0] >= p[-1][0]:
            err("top_view.direction", "Top view: draw it from the left end to the right end.", "top_view")
        for c in tv.corners:
            if not 0 < c < len(p) - 1:
                err("corner.range", f"Top view: corner index {c} must be an interior point.", "top_view", "corners")
    for k, f in enumerate(spec.features):
        anchors = [f.center] if isinstance(f, Dent) else f.path
        dims = {len(a) for a in anchors}
        if len(dims) != 1 or dims - {2, 3}:
            err("feature.anchor", f"Feature {k}: anchors must all be [x, y], [x, z] or [x, y, z].", "features", k)
        elif dims == {2} and f.surface is None:
            err("feature.surface", f"Feature {k}: a 2D anchor needs surface 'front' or 'ledge'.", "features", k)
        elif dims == {3} and f.surface is not None:
            warn("feature.surface_ignored", f"Feature {k}: surface is ignored for 3D anchors.", "features", k)
    if spec.mounting.countersink_dia <= spec.mounting.hole_dia:
        err("mounting.countersink", "Countersink diameter must exceed the hole diameter.", "mounting")
    return out


def validate(raw: dict) -> tuple[Optional[HoldSpec], list[Issue]]:
    """Parse + check. Returns (spec or None, issues). Structural errors come back as issues too."""
    try:
        spec = HoldSpec.model_validate(raw)
    except ValidationError as e:
        issues = [Issue(level="error", code="schema." + er["type"],
                        message=f"{'.'.join(str(p) for p in er['loc']) or 'spec'}: {er['msg']}",
                        path=[p for p in er["loc"] if isinstance(p, (str, int))])
                  for er in e.errors()]
        return None, issues
    return spec, check(spec)


def json_schema() -> dict:
    s = HoldSpec.model_json_schema(by_alias=True, mode="validation")
    s["$id"] = "https://github.com/parker-smith02/hold-shaping-engine/schema/hold-spec.schema.json"
    s["title"] = "hold-spec/1"
    return s
