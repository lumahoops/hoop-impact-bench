"""Rerun eval.py and confirm it reproduces a published results.json.

  python check.py                                    the published run of the bundled metrics (results/results.json)
  python check.py launch/established-players.json --ratings FOLDER_OR_FILES
                                                     a published run that also scored files not in this repository:
                                                     bring your copies, under any file name; a copy counts only if
                                                     its sha256 fingerprint matches the one in the results

A metric's scores and intervals do not depend on the other metrics in the run (every run uses the same resamples), so
each metric you hold is checked even if you lack the rest. Rank ranges are checked when you hold every file.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from eval import sha256  # noqa: E402  (the same fingerprint eval.py records)

REPO_FILES = {"games.csv": HERE / "data" / "games.csv", "minutes.csv": HERE / "data" / "minutes.csv",
              "rapm_same_season.csv": HERE / "reference" / "rapm_same_season.csv"}


def same(x, y, ranks=True):
    """Equal up to 1e-6: linear algebra on different machines can differ in the last bits. ranks=False skips ranks."""
    if isinstance(x, dict):
        keys = {k for k in x if ranks or k != "rank"}
        return (isinstance(y, dict) and keys == {k for k in y if ranks or k != "rank"}
                and all(same(x[k], y[k], ranks) for k in keys))
    if isinstance(x, list):
        return isinstance(y, list) and len(x) == len(y) and all(same(a, b, ranks) for a, b in zip(x, y))
    if isinstance(x, float) or isinstance(y, float):
        return abs(x - y) <= 1e-6
    return x == y


def pair_table(pairs, keep):
    """(part, test, a, b) -> [diff, low, high], oriented a < b, for pairs of metrics in keep."""
    out = {}
    for x in pairs:
        a, b, d, (lo, hi) = x["a"], x["b"], x["diff"], x["interval"]
        if a in keep and b in keep:
            if a > b:
                a, b, d, lo, hi = b, a, -d, -hi, -lo
            out[(x["part"], x["test"], a, b)] = [d, lo, hi]
    return out


ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("results", nargs="?", default=str(HERE / "results" / "results.json"), help="a published results.json")
ap.add_argument("--ratings", nargs="+", default=[], help="your copies of the scored files: CSV files or folders")
a = ap.parse_args()
pub = json.loads(Path(a.results).read_text(encoding="utf-8"))
meta = pub["meta"]

if sha256(HERE / "eval.py") != meta["harness"]:
    sys.exit("FAIL: eval.py differs from the version that made these results (harness fingerprint)")
for name, path in REPO_FILES.items():
    if name in meta["inputs"] and sha256(path) != meta["inputs"][name]:
        sys.exit(f"FAIL: {path.relative_to(HERE)} differs from the file these results were made from")

by_print, names_seen = {}, set()                    # your files, found by fingerprint whatever their names
for p in [HERE / "ratings"] + [Path(x) for x in a.ratings]:
    for f in (sorted(p.glob("*.csv")) if p.is_dir() else [p]):
        if f.is_file():
            by_print.setdefault(sha256(f), f)
            names_seen.add(f.name)
held, other, missing = {}, [], []
for name, fp in meta["inputs"].items():
    if name in REPO_FILES:
        continue
    if fp in by_print:
        held[name] = by_print[fp]
    elif name in names_seen:
        other.append(name)
    else:
        missing.append(name)

baselines = any(m["baseline"] for m in pub["metrics"].values())
if not held and not baselines:
    sys.exit("FAIL: none of your files matches a file these results scored")
rules = meta["rules"]
cmd = [sys.executable, str(HERE / "eval.py"), "--no-bundled", "--min-minutes", str(rules["min_minutes"]),
       "--replacement", str(rules["replacement"]), "--confidence", str(meta["confidence"]),
       "--resamples", str(meta["resamples"])]
cmd += ["--baselines"] if baselines else []
with tempfile.TemporaryDirectory() as tmp:
    files = Path(tmp) / "ratings"                   # each held file under the name it was scored under
    files.mkdir()
    for name, f in held.items():
        shutil.copyfile(f, files / name)
    cmd += ["--ratings", str(files)] if held else []
    run = subprocess.run(cmd + ["--out", str(Path(tmp) / "run")], capture_output=True, text=True)
    if run.returncode:
        sys.exit(f"FAIL: eval.py stopped: {run.stderr.strip().splitlines()[-1] if run.stderr.strip() else run.returncode}")
    rerun = json.loads((Path(tmp) / "run" / "results.json").read_text(encoding="utf-8"))

if rerun["meta"]["seasons"] != meta["seasons"]:
    sys.exit("FAIL: your files cover different seasons from the published run")
complete = not other and not missing
names = list(rerun["metrics"])
bad = [k for k in names if not same(rerun["metrics"][k], pub["metrics"][k], complete)]
if pub.get("pairs"):
    mine, theirs = pair_table(rerun["pairs"], names), pair_table(pub["pairs"], names)
    if mine.keys() != theirs.keys() or not all(same(mine[k], theirs[k]) for k in mine):
        bad.append("paired differences")
if bad:
    sys.exit(f"FAIL: same files, different results for {', '.join(bad)}")

n = len(pub["metrics"])
print(f"OK: {len(names) if not complete else n} of {n} rows reproduced, {meta['games']:,} games, {meta['seasons'][0]} to "
      f"{meta['seasons'][-1]}" + (": scores, intervals and rank ranges" if complete else
                                   ": scores and intervals (rank ranges need every file)"))
for name in other:
    print(f"  your copy of {name} is a different file (expected sha256 {meta['inputs'][name][:16]}...)")
for name in missing:
    print(f"  not held: {name} (sha256 {meta['inputs'][name][:16]}...)")
