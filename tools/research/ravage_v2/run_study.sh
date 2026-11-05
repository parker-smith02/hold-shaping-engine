#!/bin/bash
# Station-count / guide-strength / control-point-density study for the Ravage rebuild.
set -e
cd "$(dirname "$0")"; export PYTHONPATH=../../../src
REF=${REF:-.}   # run gen_v2.py and gen_v2_noscrews.py here first
run() {  # name, extract args...
  name=$1; shift
  python3 extract.py $REF study/$name.json "$@" --name $name 2>study/$name.extract.log
  python3 -m holdgen build study/$name.json -o study/$name --no-preview >/dev/null 2>study/$name.build.log
  echo "== $name: $(grep -c . /dev/null)" >/dev/null
  echo "== $name  ($(python3 -c "import json;s=json.load(open('study/$name.json'));print(sum(len(t['points']) for t in s['stations']),'control points')"))"
  python3 compare.py $REF study/$name/$name.stl study/$name.json study/$name/compare.png
  python3 -c "import json;r=json.load(open('study/$name/report.json'));print('  station max dev:',max(s['deviation_mm']['max'] for s in r['stations']),' watertight:',r['mesh']['watertight'])"
}
mkdir -p study
run st3          -40 0 40
run st5          -55 -25 0 25 55
run st7          -60 -40 -20 0 20 40 60
run st5_guide0   -55 -25 0 25 55 --views-strength 0
run st5_guide1   -55 -25 0 25 55 --views-strength 1
run st5_noviews  -55 -25 0 25 55 --no-views
run st5_handfit  -55 -25 0 25 55 --tol 0.25
