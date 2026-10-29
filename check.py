"""Rerun eval.py and confirm it reproduces the published results.

  python check.py                                every published run: results/results.json and launch/*.json
  python check.py --ratings FOLDER_OR_FILES      also use your copies of files that are not in this repository
                                                 (any file names: a copy counts only if its sha256 matches)
  python check.py launch/full-forecast.json      just this run
  python check.py --strict                       fail unless every row of every run is reproduced

Each run gets one line: OK (every row reproduced), PARTIAL (every row you hold the files for is reproduced, the rest
are listed as not checked) or FAIL. A metric's scores and intervals do not depend on the other metrics in the run
(every run uses the same resamples), so each metric you hold is checked even if you lack the rest; rank ranges are
checked when you hold every file.
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


def your_files(paths):
    """sha256 -> file, for the bundled ratings and every CSV you pointed at; also every file name seen."""
    by_print, names = {}, set()
    for p in [HERE / "ratings"] + [Path(x) for x in paths]:
        for f in (sorted(p.glob("*.csv")) if p.is_dir() else [p]):
            if f.is_file():
                by_print.setdefault(sha256(f), f)
                names.add(f.name)
    return by_print, names


def rerun(meta, baselines, held):
    """eval.py on the held files, under the run's rules, with each file under the name it was scored under."""
    rules = meta["rules"]
    cmd = [sys.executable, str(HERE / "eval.py"), "--no-bundled", "--min-minutes", str(rules["min_minutes"]),
           "--replacement", str(rules["replacement"]), "--confidence", str(meta["confidence"]),
           "--resamples", str(meta["resamples"])]
    cmd += ["--baselines"] if baselines else []
    with tempfile.TemporaryDirectory() as tmp:
        files = Path(tmp) / "ratings"
        files.mkdir()
        for name, f in held.items():
            shutil.copyfile(f, files / name)
        cmd += ["--ratings", str(files)] if held else []
        run = subprocess.run(cmd + ["--out", str(Path(tmp) / "run")], capture_output=True, text=True)
        if run.returncode:
            return None, run.stderr.strip().splitlines()[-1] if run.stderr.strip() else f"exit code {run.returncode}"
        return json.loads((Path(tmp) / "run" / "results.json").read_text(encoding="utf-8")), None


def check(path, by_print, names_seen):
    """('OK' | 'PARTIAL' | 'FAIL', lines) for one published results.json."""
    pub = json.loads(Path(path).read_text(encoding="utf-8"))
    meta, rows = pub["meta"], len(pub["metrics"])
    if sha256(HERE / "eval.py") != meta["harness"]:
        return "FAIL", ["eval.py differs from the version that made this run (harness fingerprint)"]
    for name, repo_file in REPO_FILES.items():
        if name in meta["inputs"] and sha256(repo_file) != meta["inputs"][name]:
            return "FAIL", [f"{repo_file.relative_to(HERE)} differs from the file this run was made from"]

    held, different, missing = match_inputs(meta, by_print, names_seen)
    baselines = any(m["baseline"] for m in pub["metrics"].values())
    if not held and not baselines:
        return "PARTIAL", [f"0 of {rows} rows checked: you hold none of its files"] + not_held(meta, different, missing)

    new, error = rerun(meta, baselines, held)
    if error:
        return "FAIL", [f"eval.py stopped: {error}"]
    if new["meta"]["seasons"] != meta["seasons"]:
        return "FAIL", ["your files cover different seasons from the published run"]
    complete = not different and not missing
    names = list(new["metrics"])
    bad = differences(new, pub, names, complete)
    if bad:
        return "FAIL", [f"same files, different results for {', '.join(bad)}"]
    if complete:
        return "OK", [f"{rows} of {rows} rows reproduced: scores, intervals, rank ranges, paired differences"]
    lines = [f"{len(names)} of {rows} rows reproduced (scores, intervals, paired differences); "
             f"{rows - len(names)} not checked, and rank ranges need every file"]
    return "PARTIAL", lines + not_held(meta, different, missing)


def match_inputs(meta, by_print, names_seen):
    """The run's input files you hold (name -> your file), hold a different copy of, or do not have."""
    held, different, missing = {}, [], []
    for name, fp in meta["inputs"].items():
        if name in REPO_FILES:
            continue
        if fp in by_print:
            held[name] = by_print[fp]
        else:
            (different if name in names_seen else missing).append(name)
    return held, different, missing


def differences(new, pub, names, ranks):
    """The rows (and the paired differences) of the rerun that do not match the published run."""
    bad = [k for k in names if not same(new["metrics"][k], pub["metrics"][k], ranks)]
    if pub.get("pairs"):
        mine, theirs = pair_table(new["pairs"], names), pair_table(pub["pairs"], names)
        if mine.keys() != theirs.keys() or not all(same(mine[k], theirs[k]) for k in mine):
            bad.append("paired differences")
    return bad


def not_held(meta, different, missing):
    return ([f"  your copy of {n} is a different file (expected sha256 {meta['inputs'][n][:16]}...)" for n in different]
            + [f"  not held: {n} (sha256 {meta['inputs'][n][:16]}...)" for n in missing])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="*", help="published results files (default: results/results.json, launch/*.json)")
    ap.add_argument("--ratings", nargs="+", default=[], help="your copies of the scored files: CSV files or folders")
    ap.add_argument("--strict", action="store_true", help="fail unless every row of every run is reproduced")
    args = ap.parse_args()
    published = [HERE / "results" / "results.json"] + sorted((HERE / "launch").glob("*.json"))
    runs = [Path(r) for r in args.runs] or published
    by_print, names_seen = your_files(args.ratings)
    statuses = []
    for path in runs:
        status, lines = check(path, by_print, names_seen)
        statuses.append(status)
        full, home = path.resolve(), HERE.resolve()
        shown = full.relative_to(home) if full.is_relative_to(home) else path
        print(f"{status:<8} {shown}: {lines[0]}")
        for line in lines[1:]:
            print(f"         {line}")
    if "FAIL" in statuses or (args.strict and "PARTIAL" in statuses):
        sys.exit(1)


if __name__ == "__main__":
    main()
