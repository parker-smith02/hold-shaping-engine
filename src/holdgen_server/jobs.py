"""Full builds run as jobs in a separate process (CPU-bound, 20-40 s), one at a time.

Each job writes to <builds_dir>/<id>/ (the files listed in holdgen.pipeline.OUTPUT_FILES)
plus status.json, so results survive a server restart.
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import json
import multiprocessing as mp
import re
import threading
import traceback
import uuid
from pathlib import Path


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


JOB_ID_RE = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9a-f]{6}$")


def _patch_status(path: Path, **fields) -> None:
    st = json.loads(path.read_text(encoding="utf-8"))
    st.update(fields)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=1))
    tmp.replace(path)


def _run(spec: dict, out_dir: str) -> dict:
    """Worker-process entry: marks itself running and streams log lines into status.json."""
    from holdgen import pipeline
    status = Path(out_dir) / "status.json"
    log: list[str] = []

    def emit(line: str) -> None:
        log.append(line)
        _patch_status(status, log=log)

    _patch_status(status, state="running")
    summary = pipeline.build_to_dir(spec, out_dir, log=emit)
    return {"summary": summary, "log": log}


class BuildJobs:
    def __init__(self, root: Path, workers: int = 1):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        ctx = mp.get_context("spawn")                       # no fork of a threaded server
        self.pool = cf.ProcessPoolExecutor(max_workers=workers, mp_context=ctx)
        self.lock = threading.Lock()

    def _status_path(self, job_id: str) -> Path:
        return self.root / job_id / "status.json"

    def _write(self, st: dict) -> None:
        p = self._status_path(st["id"])
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(st, indent=1))
        tmp.replace(p)

    def submit(self, spec: dict) -> dict:
        job_id = dt.datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        st = {"id": job_id, "name": spec["name"], "state": "queued", "created": _now(),
              "finished": None, "error": None, "log": [], "files": [], "report": None}
        self._write(st)
        fut = self.pool.submit(_run, spec, str(self.root / job_id))
        fut.add_done_callback(lambda f: self._done(job_id, f))
        return st

    def _done(self, job_id: str, fut: cf.Future) -> None:
        st = self.get(job_id)
        try:
            res = fut.result()
            st.update(state="done", report=res["summary"], log=res["log"])
        except Exception as e:                                    # surface the failure to the client
            st.update(state="failed", error=f"{type(e).__name__}: {e}",
                      log=traceback.format_exception(e)[-6:])
        st["finished"] = _now()
        from holdgen.pipeline import OUTPUT_FILES
        st["files"] = [f for f in OUTPUT_FILES if (self.root / job_id / f).exists()]
        with self.lock:
            self._write(st)

    def get(self, job_id: str) -> dict:
        if not JOB_ID_RE.match(job_id):
            raise FileNotFoundError(job_id)
        p = self._status_path(job_id)
        if not p.exists():
            raise FileNotFoundError(job_id)
        return json.loads(p.read_text(encoding="utf-8"))

    def file(self, job_id: str, name: str) -> Path:
        from holdgen.pipeline import OUTPUT_FILES
        if name not in OUTPUT_FILES or not JOB_ID_RE.match(job_id):
            raise FileNotFoundError(name)
        p = self.root / job_id / name
        if not p.exists():
            raise FileNotFoundError(name)
        return p

    def shutdown(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=True)
