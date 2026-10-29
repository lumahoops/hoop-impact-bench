"""Rerun eval.py on the files in this repo and confirm it reproduces the published results/results.json."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent


def rounded(x):
    """6 decimals: linear algebra on different machines can differ in the last bits."""
    if isinstance(x, float):
        return round(x, 6)
    if isinstance(x, dict):
        return {k: rounded(v) for k, v in x.items()}
    if isinstance(x, list):
        return [rounded(v) for v in x]
    return x


published = json.loads((HERE / "results" / "results.json").read_text(encoding="utf-8"))
with tempfile.TemporaryDirectory() as tmp:
    subprocess.run([sys.executable, str(HERE / "eval.py"), "--out", tmp], check=True, capture_output=True)
    rerun = json.loads((Path(tmp) / "results.json").read_text(encoding="utf-8"))

if rerun["meta"]["inputs"] != published["meta"]["inputs"]:
    sys.exit("FAIL: the input files differ from the ones the published results were made from")
if rerun["meta"]["harness"] != published["meta"]["harness"]:
    sys.exit("FAIL: eval.py differs from the version that made the published results")
if rounded(rerun["metrics"]) != rounded(published["metrics"]):
    sys.exit("FAIL: same input files, different results")
meta = published["meta"]
print(f"OK: {len(published['metrics'])} metrics, {meta['games']:,} games, {meta['seasons'][0]} to "
      f"{meta['seasons'][-1]}: results reproduced")
