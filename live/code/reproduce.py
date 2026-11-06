"""Rebuild the published live boards from this checkout and check they match, number for number.

  git checkout <any commit>                  # any day's state of the repo
  HIB_RATINGS=/path/to/ratings python live/code/reproduce.py

Uses only what is in the repo (live/data, live/reference, live/snapshots, live/code/eval_v1.1.0.py) plus the ratings files, which are
not published (each must match its fingerprint in live/snapshots/, or the run stops):
  <HIB_RATINGS>/preseason/<metric>.csv        the frozen board
  <HIB_RATINGS>/daily/<date>/<metric>.csv     the daily board (one folder per snapshot day)
Scores both boards, both views, in a temporary folder with the release harness and compares every published number in
live/results/<stem>.json, <stem>_games.csv and <stem>_picks.csv (frozen, frozen_full, daily, daily_established). Only updated_utc and repo_commit may differ (they record when and
from which commit a run was made). Exit code 0 = reproduced.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
LIVE = HERE.parent
SKIP = {"updated_utc", "repo_commit"}
STEMS = {"frozen": ["frozen", "frozen_full"], "daily": ["daily", "daily_established"]}   # paths.py VIEWS


def diff(a, b, path=""):
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in set(a) | set(b):
            if k not in SKIP:
                out += diff(a.get(k), b.get(k), f"{path}.{k}")
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in diff(x, y, f"{path}[{i}]")]
    return [] if a == b else [f"{path}: published {a!r}, rebuilt {b!r}"]


def main():
    boards = [b for b in ("frozen", "daily") if (LIVE / "results" / f"{b}.json").exists()]
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, HIB_WORK=str(Path(tmp) / "work"), HIB_RESULTS=str(Path(tmp) / "results"))
        steps = {"frozen": [["score.py"], ["publish.py", "frozen"]], "daily": [["daily_score.py"], ["publish.py", "daily"]]}
        for board in boards:
            for step in steps[board]:
                r = subprocess.run([sys.executable, str(HERE / step[0]), *step[1:]], env=env, capture_output=True, text=True)
                if r.returncode != 0:
                    print(f"{board}: could not rebuild ({step[0]}): {(r.stderr or r.stdout).strip()[-400:]}")
                    ok = False
                    break
            else:
                for stem in STEMS[board]:              # both views; a view published later may be absent
                    if (LIVE / "results" / f"{stem}.json").exists():
                        ok &= compare(stem, Path(tmp) / "results")
    sys.exit(0 if ok else 1)


def compare(stem, rebuilt):
    pub = json.loads((LIVE / "results" / f"{stem}.json").read_text(encoding="utf-8"))
    new = json.loads((rebuilt / f"{stem}.json").read_text(encoding="utf-8"))
    d = diff(pub, new)
    g1 = pd.read_csv(LIVE / "results" / f"{stem}_games.csv", dtype={"game_id": str})
    g2 = pd.read_csv(rebuilt / f"{stem}_games.csv", dtype={"game_id": str})
    games_same = g1.equals(g2)
    p1, p2 = (LIVE / "results" / f"{stem}_picks.csv"), (rebuilt / f"{stem}_picks.csv")
    if p1.exists():           # W-L picks (published from 2026-11-01)
        games_same &= pd.read_csv(p1, dtype={"game_id": str}).equals(pd.read_csv(p2, dtype={"game_id": str}))
    print(f"{stem}: {'REPRODUCED' if not d and games_same else 'DIFFERS'} "
          f"({pub['games']} games through {pub['scored_through']})")
    for line in d[:10]:
        print("   ", line)
    if not games_same:
        print("    per-game or picks file differs")
    return not d and games_same

if __name__ == "__main__":
    main()
