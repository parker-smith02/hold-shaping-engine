"""Generated files are current: TypeScript types + JSON Schema (codegen) and the curves golden."""
import subprocess
import sys

from conftest import ROOT


def test_codegen_is_current():
    from holdgen_server import codegen
    assert codegen.main(["--check"]) == 0, "run: python -m holdgen_server.codegen"


def test_curves_golden_is_current():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "gen_golden.py"), "--check"], cwd=ROOT)
    assert r.returncode == 0, "run: python tools/gen_golden.py"
