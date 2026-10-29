"""Rerun eval.py on the files in this repo and confirm it reproduces the published results/results.json."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
published = json.loads((HERE / "results" / "results.json").read_text())
with tempfile.TemporaryDirectory() as tmp:
    subprocess.run([sys.executable, str(HERE / "eval.py"), "--out", tmp], check=True, capture_output=True)
    rerun = json.loads((Path(tmp) / "results.json").read_text())

if rerun["sha256"] != published["sha256"]:
    sys.exit("FAIL: the input files differ from the ones the published results were made from")
def rounded(x):   # 6 decimals: different machines' linear algebra can differ in the last bits
    if isinstance(x, float):
        return round(x, 6)
    if isinstance(x, dict):
        return {k: rounded(v) for k, v in x.items()}
    if isinstance(x, list):
        return [rounded(v) for v in x]
    return x


if rounded(rerun) != rounded(published):
    sys.exit("FAIL: same inputs, different results")
print(f"OK: {len(published['meta']['systems'])} systems, {published['meta']['games']:,} games, results reproduced")
