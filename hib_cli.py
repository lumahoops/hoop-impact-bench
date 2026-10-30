"""Console entry points for the installed package (pip install hoop-impact-bench).

  hib --ratings my_metric.csv        same as: python eval.py --ratings my_metric.csv
  hib-check                          same as: python check.py

Runs go to ./runs/<date_time> in the folder you run from (not inside the installed package) unless you pass --out.
"""
import runpy
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run_eval():
    args = sys.argv[1:]
    if "--out" not in args and not any(a in ("-h", "--help") for a in args):
        args += ["--out", str(Path.cwd() / "runs" / datetime.now().strftime("%Y-%m-%d_%H%M%S"))]
    sys.argv = [str(HERE / "eval.py")] + args
    runpy.run_path(str(HERE / "eval.py"), run_name="__main__")


def run_check():
    sys.argv = [str(HERE / "check.py")] + sys.argv[1:]
    runpy.run_path(str(HERE / "check.py"), run_name="__main__")
