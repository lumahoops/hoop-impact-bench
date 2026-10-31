"""Frozen preseason board: score every 2026-27 game so far with each metric's opening-night rating.

  python live/code/score.py

Inputs   live/snapshots/preseason.json (fingerprints), <HIB_RATINGS>/preseason/<metric>.csv (the ratings; each must match
         its fingerprint), live/data/ (2026-27 games and minutes), live/reference/ (2026-27 RAPM reference rows)
Runs     the HIB v1.1.0 harness (live/code/eval_v1.1.0.py, eval.py of that release byte for byte; sha256 checked), twice on a scratch copy of the repo's data:
           <HIB_WORK>/runs/frozen/                   every metric (ranked) + the reference rows (--baselines)
           <HIB_WORK>/runs/frozen_with_consensus/    every metric + the consensus (only the consensus row is used, so it
                                                     never changes anyone's rank range)
The consensus is each player's average across the metrics that rate him.
"""
import json
import shutil
import subprocess
import sys

import pandas as pd

from paths import FROZEN_DROPPED, HARNESS, PRESEASON_RULES, DATA, REFERENCE, RATINGS, RELEASE_HARNESS, REPO, RUNS, SEASON, SNAPSHOTS, WORK

FIRST_GAME = "2026-10-20"


def sha256(path):
    import hashlib
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def scratch(work):
    """eval.py + the release's data and reference files, with this season's games and RAPM rows appended."""
    shutil.rmtree(work, ignore_errors=True)
    (work / "data").mkdir(parents=True)
    shutil.copy(HARNESS, work / "eval.py")
    if sha256(work / "eval.py") != RELEASE_HARNESS:
        sys.exit("eval.py is not the release harness")
    shutil.copytree(REPO / "reference", work / "reference")
    for f in ("rapm_same_season", "rapm_last_season"):
        pd.concat([pd.read_csv(work / "reference" / f"{f}.csv"), pd.read_csv(REFERENCE / f"{f}_{SEASON}.csv")]) \
            .to_csv(work / "reference" / f"{f}.csv", index=False)
    g = pd.read_csv(DATA / f"games_{SEASON}.csv", dtype={"game_id": str})
    m = pd.read_csv(DATA / f"minutes_{SEASON}.csv", dtype={"game_id": str})
    g = g[g.date >= FIRST_GAME]
    base_g = pd.read_csv(REPO / "data" / "games.csv", dtype={"game_id": str})
    base_m = pd.read_csv(REPO / "data" / "minutes.csv", dtype={"game_id": str})
    pd.concat([base_g, g[base_g.columns]]).to_csv(work / "data" / "games.csv", index=False)
    pd.concat([base_m, m[m.game_id.isin(g.game_id)][base_m.columns]]).to_csv(work / "data" / "minutes.csv", index=False)
    return len(g), g.date.max()


def main():
    manifest = json.loads((SNAPSHOTS / "preseason.json").read_text())
    files = []
    for k, e in sorted(manifest["metrics"].items()):          # alphabetical, as the harness lists files
        f = RATINGS / "preseason" / f"{k}.csv"
        if not f.exists():
            sys.exit(f"missing ratings file {f}")
        if sha256(f) != e["sha256"]:
            sys.exit(f"{f} does not match its published fingerprint")
        if k not in FROZEN_DROPPED:
            files.append(f)
    work = WORK / "work" / "frozen"
    n, last = scratch(work)
    cons = WORK / "derived" / "consensus.csv"                  # the file's name is the row's name in the results
    cons.parent.mkdir(parents=True, exist_ok=True)
    wide = pd.concat([pd.read_csv(f).assign(m=f.stem) for f in files]).pivot_table(index="nba_id", columns="m", values="rating")
    pd.DataFrame({"season": SEASON, "nba_id": wide.index, "rating": wide.mean(axis=1).round(3)}).to_csv(cons, index=False)
    for out, more, flags in (("frozen", [], ["--baselines"]), ("frozen_with_consensus", [str(cons)], [])):
        shutil.rmtree(RUNS / out, ignore_errors=True)
        cmd = [sys.executable, str(work / "eval.py"), "--no-bundled", "--out", str(RUNS / out)] + flags + \
              ["--ratings"] + [str(f) for f in files] + more
        subprocess.run(cmd, check=True, capture_output=True)
        if json.loads((RUNS / out / "results.json").read_text())["meta"]["rules"] != PRESEASON_RULES:
            sys.exit("the harness defaults are not the preseason rules")
    picks(work, files)
    print(f"frozen board: {n} games through {last}, {len(files)} metrics + consensus + reference rows")


def picks(work, files):
    """<RUNS>/frozen/picks.csv: each 2026-27 game's home-minus-away team rating for every metric, from the harness's own
    rate_teams (no fitted line, no home edge). Positive = the metric picks the home team; W-L comes from its sign."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("hib_eval", work / "eval.py")
    ev = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ev)
    games = pd.read_csv(work / "data" / "games.csv", dtype={"game_id": str})
    games["margin"] = (games.home_pts - games.away_pts).astype(float)
    minutes = pd.read_csv(work / "data" / "minutes.csv", dtype={"game_id": str})
    systems = {f.stem: ev.read_ratings(f) for f in files}
    seasons, games, player_games, player_seasons, team_seasons = ev.prepare(systems, games, minutes)
    game_ratings, _, _ = ev.rate_teams(systems, seasons, player_games, player_seasons, len(games), len(team_seasons),
                                       PRESEASON_RULES["min_minutes"], PRESEASON_RULES["replacement"])
    out = pd.DataFrame({k: game_ratings[i].round(4) for i, k in enumerate(systems)})
    out.insert(0, "game_id", games.game_id.values)
    out[games.season.values == SEASON].to_csv(RUNS / "frozen" / "picks.csv", index=False)


if __name__ == "__main__":
    main()
