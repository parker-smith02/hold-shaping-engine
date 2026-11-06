"""Local HTTP API for the editor: preview, validation, hold library and build jobs.

OpenAPI docs are served at /api/docs. Request/response models live in models.py and
also generate the client's TypeScript types (codegen.py).

Status codes:
  400  malformed request (not JSON, wrong fields)            -> ErrorResponse
  404  unknown hold / build / file                           -> ErrorResponse
  422  the spec itself has errors, or geometry failed        -> ErrorResponse with issues
"""
import contextlib
from pathlib import Path
from typing import Any, Optional

from fastapi import Body, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from holdgen import __version__, fit, preview as preview_mod, schema, spec as spec_mod

from . import models as M
from .jobs import BuildJobs
from .store import HoldStore, StoreError


class ApiError(Exception):
    def __init__(self, status: int, error: str, issues=()):
        self.status, self.error, self.issues = status, error, list(issues)


def _engine_spec(raw: dict):
    """Validate a raw spec into the engine dict, or raise 422 with the issues."""
    model, issues = schema.validate(raw)
    if model is None or any(i.level == "error" for i in issues):
        raise ApiError(422, "spec has errors", issues)
    return spec_mod.lower(model), issues


ERRORS = {400: {"model": M.ErrorResponse}, 404: {"model": M.ErrorResponse}, 422: {"model": M.ErrorResponse}}


def create_app(holds_dir: Path, builds_dir: Path, web_dist: Optional[Path] = None,
               build_workers: int = 1) -> FastAPI:
    store = HoldStore(holds_dir)
    jobs = BuildJobs(builds_dir, workers=build_workers)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        jobs.shutdown()

    app = FastAPI(title="holdgen", version=__version__, lifespan=lifespan,
                  docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    app.state.store, app.state.jobs = store, jobs

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        body = M.ErrorResponse(error=exc.error, issues=exc.issues)
        return JSONResponse(body.model_dump(), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _bad_request(request: Request, exc: RequestValidationError):
        msg = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
        return JSONResponse(M.ErrorResponse(error=f"bad request: {msg}").model_dump(), status_code=400)

    # Endpoints doing geometry are plain `def`: FastAPI runs them in its threadpool, keeping the
    # event loop free while numpy works (preview ~40 ms, section-at ~50 ms).

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "version": __version__}

    @app.get("/api/schema")
    def get_schema() -> dict:
        return schema.json_schema()

    @app.post("/api/validate", response_model=M.ValidateResponse, responses=ERRORS)
    def validate(body: M.SpecRequest):
        _, issues = schema.validate(body.spec)
        return M.ValidateResponse(issues=issues)

    @app.post("/api/preview", response_model=M.PreviewResponse, responses=ERRORS)
    def preview(body: M.PreviewRequest):
        spec, issues = _engine_spec(body.spec)
        try:
            payload = preview_mod.preview(spec, body.step, body.dx)
        except Exception as e:                     # report geometry failures with the spec's issues
            raise ApiError(422, f"preview failed: {type(e).__name__}: {e}", issues)
        return {**payload, "issues": [i.model_dump() for i in issues]}

    @app.post("/api/section-at", response_model=M.SectionAtResponse, responses=ERRORS)
    def section_at(body: M.SectionAtRequest):
        spec, issues = _engine_spec(body.spec)
        try:
            station = fit.section_at(spec, body.x)
        except ValueError as e:                    # x outside the hold
            raise ApiError(422, str(e)) from None
        except Exception as e:                     # report geometry failures with the spec's issues
            raise ApiError(422, f"section-at failed: {type(e).__name__}: {e}", issues) from None
        return {"station": station}

    @app.get("/api/holds", response_model=M.HoldList)
    def holds_list():
        return {"holds": store.list()}

    @app.post("/api/migrate", responses=ERRORS)
    def migrate(body: M.SpecRequest) -> dict[str, Any]:
        """A spec in the current hold-spec/1 shape (older files, drafts and imports are converted)."""
        model, issues = schema.validate(body.spec)
        if model is None:
            raise ApiError(422, "spec does not match hold-spec/1", issues)
        return model.dump()

    @app.get("/api/holds/{name}", responses=ERRORS)
    def hold_get(name: str) -> dict[str, Any]:
        try:
            raw = store.get(name)
            model, _ = schema.validate(raw)       # older files load in the current shape
            return model.dump() if model is not None else raw
        except FileNotFoundError:
            raise ApiError(404, "no such hold")
        except StoreError as e:
            raise ApiError(400, str(e))

    @app.put("/api/holds/{name}", response_model=M.SaveResponse, responses=ERRORS)
    def hold_put(name: str, spec: dict[str, Any] = Body(...)):
        try:
            store.check_name(name)                 # a bad path is a bad request, not a bad spec
        except StoreError as e:
            raise ApiError(400, str(e))
        raw = {**spec, "name": name}
        model, issues = schema.validate(raw)
        if model is None:                          # structurally broken: refuse. Semantic errors are fine in drafts.
            raise ApiError(422, "spec does not match hold-spec/1", issues)
        try:
            store.put(name, model.dump())
        except StoreError as e:
            raise ApiError(400, str(e))
        return M.SaveResponse(name=name, issues=issues)

    @app.delete("/api/holds/{name}", status_code=204, responses=ERRORS)
    def hold_delete(name: str):
        try:
            store.delete(name)
        except FileNotFoundError:
            raise ApiError(404, "no such hold")
        except StoreError as e:
            raise ApiError(400, str(e))
        return Response(status_code=204)

    @app.post("/api/builds", status_code=202, response_model=M.BuildStatus, responses=ERRORS)
    def build_submit(body: M.SpecRequest):
        spec, _ = _engine_spec(body.spec)
        return jobs.submit(spec)

    @app.get("/api/builds/{job_id}", response_model=M.BuildStatus, responses=ERRORS)
    def build_get(job_id: str):
        try:
            return jobs.get(job_id)
        except FileNotFoundError:
            raise ApiError(404, "no such build")

    @app.get("/api/builds/{job_id}/files/{name}", responses=ERRORS)
    def build_file(job_id: str, name: str):
        try:
            p = jobs.file(job_id, name)
        except FileNotFoundError:
            raise ApiError(404, "no such file")
        return FileResponse(p, filename=p.name if p.suffix == ".stl" else None)

    if web_dist and Path(web_dist).joinpath("index.html").exists():
        app.mount("/", StaticFiles(directory=str(web_dist), html=True), name="web")
    return app
