"""HTTP API contract. These models generate web/src/api/types.gen.ts (see codegen.py).

Requests carry the spec as a raw object (`tsType: HoldSpec` for the client) so that an
invalid spec comes back as a list of Issues instead of a request-parsing failure.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from holdgen.schema import Issue, Station

SpecField = Field(json_schema_extra={"tsType": "HoldSpec"})


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SpecRequest(_M):
    spec: dict[str, Any] = SpecField


class PreviewRequest(_M):
    spec: dict[str, Any] = SpecField
    step: float = Field(0.4, ge=0.1, le=2.0, description="Arc-length sample step of the preview loft (mm).")
    dx: float = Field(1.0, ge=0.25, le=5.0, description="Spacing of preview rings along x (mm).")


class SectionAtRequest(_M):
    spec: dict[str, Any] = SpecField
    x: float


class ValidateResponse(_M):
    issues: list[Issue]


class Readouts(_M):
    depth: float
    chord_incut: float
    incut_at_wall: Optional[float]
    incut_near_lip: Optional[float]
    ledge_below_horizontal_on_wall: float
    thickness: float
    height: float


class ReadoutRow(_M):
    x: float
    kind: Literal["station", "between"]
    readouts: Readouts


class LoftInfo(_M):
    x_min: float
    x_max: float
    landmarks: list[str]
    tips: dict[str, Literal["taper", "cap"]]


class Extents(_M):
    x: list[float]
    y_lo: list[float]
    y_hi: list[float]
    z_hi: list[float]


class MeshPayload(_M):
    positions: str = Field(description="base64 little-endian float32 xyz triples")
    indices: str = Field(description="base64 little-endian uint32 triangle indices")
    vertex_count: int
    triangle_count: int


class BBox(_M):
    min: tuple[float, float, float]
    max: tuple[float, float, float]


class ScrewFace(_M):
    x: float
    y: float
    face_z: float


class PreviewResponse(_M):
    issues: list[Issue]
    loft: LoftInfo
    extents: Extents
    mesh: MeshPayload
    bbox: BBox
    readouts: list[ReadoutRow]
    screws: list[ScrewFace]


class SectionAtResponse(_M):
    station: Station


class ErrorResponse(_M):
    error: str
    issues: list[Issue] = Field(default_factory=list)


class HoldSummary(_M):
    name: str
    updated: str
    stations: int
    description: str


class HoldList(_M):
    holds: list[HoldSummary]


class SaveResponse(_M):
    name: str
    issues: list[Issue]


BuildState = Literal["queued", "running", "done", "failed"]


class BuildStatus(_M):
    id: str
    name: str
    state: BuildState
    created: str
    finished: Optional[str] = None
    error: Optional[str] = None
    log: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    report: Optional[dict[str, Any]] = None


API_MODELS = [SpecRequest, PreviewRequest, SectionAtRequest, ValidateResponse, PreviewResponse,
              SectionAtResponse, ErrorResponse, HoldList, SaveResponse, BuildStatus]
