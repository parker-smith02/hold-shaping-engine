"""Build jobs: status files across restarts, and shutdown with a build in flight."""
import json
import time

import pytest

from holdgen_server.jobs import BuildJobs


def test_restart_marks_unfinished_jobs_failed(tmp_path):
    for job_id, state in [("20260101-000000-aaaaaa", "running"), ("20260101-000000-bbbbbb", "queued"),
                          ("20260101-000000-cccccc", "done")]:
        (tmp_path / job_id).mkdir()
        (tmp_path / job_id / "status.json").write_text(json.dumps({"id": job_id, "state": state}))
    jobs = BuildJobs(tmp_path)
    try:
        assert jobs.get("20260101-000000-aaaaaa")["state"] == "failed"
        assert "interrupted" in jobs.get("20260101-000000-bbbbbb")["error"]
        assert jobs.get("20260101-000000-cccccc")["state"] == "done"
    finally:
        jobs.shutdown()


@pytest.mark.slow
def test_shutdown_kills_a_running_build(tmp_path, ravage):
    jobs = BuildJobs(tmp_path / "builds")
    job = jobs.submit(ravage)
    for _ in range(200):                                     # spawn + imports take a few seconds
        if jobs.get(job["id"])["state"] == "running":
            break
        time.sleep(0.1)
    assert jobs.get(job["id"])["state"] == "running"
    procs = list(jobs.pool._processes.values())
    t0 = time.monotonic()
    jobs.shutdown()
    assert time.monotonic() - t0 < 6
    assert not any(p.is_alive() for p in procs)
    assert BuildJobs(tmp_path / "builds").get(job["id"])["state"] == "failed"
