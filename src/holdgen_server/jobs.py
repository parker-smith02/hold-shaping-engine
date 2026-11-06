"""Full builds run as jobs in a separate process (CPU-bound, 20-40 s), one at a time.

Each job writes to <builds_dir>/<id>/ (the files listed in holdgen.pipeline.OUTPUT_FILES)
plus status.json, so results survive a server restart.
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import json
import multiprocessing as mp
import os
import re
import tempfile
import threading
import time
import traceback
import uuid
from pathlib import Path


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


JOB_ID_RE = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9a-f]{6}$")


def _retry(fn, tries: int = 200, delay: float = 0.01):
    """Windows can't replace a file another process has open (and a reader can catch the swap):
    status.json is written by the worker while the server polls it, so retry briefly."""
    for i in range(tries):
        try:
            return fn()
        except (PermissionError, json.JSONDecodeError):
            if i == tries - 1:
                raise
            time.sleep(delay)


def _read_status(path: Path) -> dict:
    return _retry(lambda: json.loads(path.read_text(encoding="utf-8")))


def _write_status(path: Path, st: dict) -> None:
    # A unique tmp per write: the worker, the pool's done-callback thread and a restart sweep can all
    # write the same status.json, and a shared tmp name interleaves their writes.
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(st, indent=1))
        _retry(lambda: tmp.replace(path))
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _patch_status(path: Path, **fields) -> None:
    st = _read_status(path)
    st.update(fields)
    _write_status(path, st)


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
        self._fail_interrupted()

    def _fail_interrupted(self) -> None:
        """Jobs left queued/running by a previous server process will never finish: say so."""
        for p in self.root.glob("*/status.json"):
            try:
                st = _read_status(p)
            except (OSError, json.JSONDecodeError):
                continue
            if st.get("state") in ("queued", "running"):
                st.update(state="failed", error="interrupted: the server stopped before the build finished",
                          finished=_now())
                _write_status(p, st)

    def _status_path(self, job_id: str) -> Path:
        return self.root / job_id / "status.json"

    def _write(self, st: dict) -> None:
        p = self._status_path(st["id"])
        p.parent.mkdir(parents=True, exist_ok=True)
        _write_status(p, st)

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
        return _read_status(p)

    def file(self, job_id: str, name: str) -> Path:
        from holdgen.pipeline import OUTPUT_FILES
        if name not in OUTPUT_FILES or not JOB_ID_RE.match(job_id):
            raise FileNotFoundError(name)
        p = self.root / job_id / name
        if not p.exists():
            raise FileNotFoundError(name)
        return p

    def shutdown(self) -> None:
        """Stop now: cancel queued jobs and kill a running build (otherwise interpreter exit waits
        for it). The next server start marks it failed."""
        procs = list((self.pool._processes or {}).values())    # no public API for killing workers
        self.pool.shutdown(wait=False, cancel_futures=True)
        for proc in procs:
            if proc.is_alive():
                proc.terminate()
        for proc in procs:
            proc.join(timeout=5)
