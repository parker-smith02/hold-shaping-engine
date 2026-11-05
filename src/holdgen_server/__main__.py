"""Run the local server.

    holdgen-server                              # holds/ and .holdgen/builds in the current directory
    holdgen-server --holds ./holds --web web/dist --port 8000
"""
from __future__ import annotations

import argparse
from pathlib import Path


def main(argv=None) -> None:
    import uvicorn

    from .app import create_app

    ap = argparse.ArgumentParser(prog="holdgen-server")
    ap.add_argument("--holds", type=Path, default=Path("holds"))
    ap.add_argument("--builds", type=Path, default=Path(".holdgen/builds"))
    ap.add_argument("--web", type=Path, default=Path("web/dist"), help="built web app to serve at /")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--build-workers", type=int, default=1)
    a = ap.parse_args(argv)
    app = create_app(a.holds.resolve(), a.builds.resolve(), a.web.resolve(), a.build_workers)
    uvicorn.run(app, host=a.host, port=a.port, log_level="info")


if __name__ == "__main__":
    main()
