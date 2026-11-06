"""Daily board: score every 2026-27 game with each metric's rating as saved on the morning of that game, before tip-off.

  python live/code/daily_score.py                         every game so far, both views
  python live/code/daily_score.py --through 2026-11-02    only games through that date (rebuilding a past day's board)

Two views (live/code/paths.py VIEWS), scored from the same saved files:
  <HIB_WORK>/runs/daily/               full forecast: every player at the metric's value as published, rookies included
  <HIB_WORK>/runs/daily_established/   established players: under 250 minutes in 2025-26, rookies included, = -2.0
Each run also gets centered.json: team net error centered (live/code/centered.py), the ranked test.

A game on date D uses the snapshot of date D (live/snapshots/daily/D.json; ratings in <HIB_RATINGS>/daily/D/). Each
metric's value counts for the game only if that metric's entry was saved before the game's tip-off (tip_utc) and is
not empty (a pull that failed all morning). If any ranked metric has no valid value for a game, the game is left off
the board for every metric, so all of them are always scored on the same games; the excluded games and the reason are
recorded. Values are never carried across days by the scorer: no snapshot that day, no score that day.

The release harness does the scoring: prepare, apply_rules, score, bootstrap, summarize and paired_differences come
from a byte-identical copy of eval.py (sha256 checked). The only new piece is the lookup (a player's value can differ
from game to game); a team-season's rating is the minutes-weighted average of its players' values over the games scored.
The consensus (each player's average across that morning's metrics) and the reference rows are not ranked.
"""
import argparse
import hashlib
import importlib.util
import json
import shutil
import sys

import numpy as np
import pandas as pd

import centered
from paths import HARNESS, DATA, REFERENCE, RATINGS, RELEASE_HARNESS, REPO, RUNS, SEASON, SNAPSHOTS, VIEWS, WORK


def sha256(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def harness(work, reference=REFERENCE):
    shutil.rmtree(work, ignore_errors=True)
    (work / "data").mkdir(parents=True)
    shutil.copy(HARNESS, work / "eval.py")
    shutil.copytree(REPO / "reference", work / "reference")
    for f in ("rapm_same_season", "rapm_last_season"):
        pd.concat([pd.read_csv(work / "reference" / f"{f}.csv"), pd.read_csv(reference / f"{f}_{SEASON}.csv")]) \
            .to_csv(work / "reference" / f"{f}.csv", index=False)
    spec = importlib.util.spec_from_file_location("hib_eval", work / "eval.py")
    ev = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ev)
    if ev.sha256(work / "eval.py") != RELEASE_HARNESS:
        sys.exit("eval.py is not the release harness")
    return ev


def load_snapshots():
    """date -> {metric: (ratings Series or None, saved_at Timestamp or None, status)}; fingerprints checked."""
    out = {}
    for m in sorted((SNAPSHOTS / "daily").glob("*.json")):
        man = json.loads(m.read_text())
        day = man["date"]
        entries = {}
        for k, e in man["metrics"].items():
            f = RATINGS / "daily" / day / f"{k}.csv"
            if e["status"] == "empty":
                entries[k] = (None, None, "empty")
                continue
            if not f.exists() or sha256(f) != e["sha256"]:
                sys.exit(f"{f} is missing or does not match its published fingerprint")
            saved = pd.Timestamp(e.get("saved_at_utc", man["saved_at_utc"]))
            entries[k] = (pd.read_csv(f).set_index("nba_id").rating, saved, e["status"])
        out[day] = entries
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--through", help="score only games through this date (YYYY-MM-DD)")
    ap.add_argument("--reference", help="folder with that day's rapm_*_2026-27.csv (default live/reference)")
    args = ap.parse_args()
    from pathlib import Path
    reference = Path(args.reference) if args.reference else REFERENCE
    snaps = load_snapshots()
    if args.through:
        snaps = {d: v for d, v in snaps.items() if d <= args.through}
    if not snaps:
        sys.exit("no daily snapshots yet")
    names = sorted(set.union(*(set(e) for e in snaps.values())))
    g26 = pd.read_csv(DATA / f"games_{SEASON}.csv", dtype={"game_id": str})
    m26 = pd.read_csv(DATA / f"minutes_{SEASON}.csv", dtype={"game_id": str})
    g26 = g26[g26.date >= min(snaps)]
    if args.through:
        g26 = g26[g26.date <= args.through]
    tip = pd.to_datetime(g26.tip_utc, utc=True)
    keep, excluded = [], []
    for (_, row), t in zip(g26.iterrows(), tip):
        day = snaps.get(row.date)
        if day is None:
            excluded.append({"game_id": row.game_id, "date": row.date, "reason": "no snapshot that day"})
            continue
        bad = [k for k in names if k not in day or day[k][0] is None or day[k][1] >= t]
        if bad:
            excluded.append({"game_id": row.game_id, "date": row.date,
                             "reason": "no value saved before tip-off: " + ", ".join(sorted(bad))})
        else:
            keep.append(row.game_id)
    g26 = g26[g26.game_id.isin(keep)]
    if g26.empty:
        sys.exit("no game has a full set of values saved before its tip-off yet")

    ev = harness(WORK / "work" / "daily", reference)
    base_g = pd.read_csv(REPO / "data" / "games.csv", dtype={"game_id": str})
    base_m = pd.read_csv(REPO / "data" / "minutes.csv", dtype={"game_id": str})
    games = pd.concat([base_g, g26[base_g.columns]])
    games["margin"] = (games.home_pts - games.away_pts).astype(float)
    minutes = pd.concat([base_m, m26[m26.game_id.isin(g26.game_id)][base_m.columns]])
    refs = ev.baselines(games, minutes)
    order = names + ["consensus"] + list(refs)
    systems = {k: pd.DataFrame({"season": [SEASON], "nba_id": [0], "rating": [0.0]}) for k in names + ["consensus"]}
    systems.update(refs)
    seasons, games, player_games, player_seasons, team_seasons = ev.prepare(systems, games, minutes)

    day_of = player_games.game.map(games.date).values                # each player-game's date
    team_key = pd.MultiIndex.from_arrays([player_games.season, player_games.team])
    pg_team = team_seasons.index.get_indexer(team_key)
    mins = player_games["min"].values
    team_minutes = np.bincount(pg_team, weights=mins, minlength=len(team_seasons))
    established = player_games.last_min.values >= ev.STANDARD["min_minutes"]

    raws = {}                                    # each row's value per player-game, as saved (before any rule)
    for k in order:
        if k in refs:
            raws[k] = ev.lookup(player_games, refs[k][refs[k].season.isin(seasons)])
        else:
            raw = np.full(len(player_games), np.nan)
            for day in np.unique(day_of):
                rows = day_of == day
                ids = player_games.nba_id.values[rows]
                if k == "consensus":
                    raw[rows] = pd.DataFrame({m: snaps[day][m][0] for m in names}).mean(axis=1).reindex(ids).values
                else:
                    raw[rows] = snaps[day][k][0].reindex(ids).values
            raws[k] = raw
    ev.BASELINES = dict(ev.BASELINES, consensus="each player's average across that morning's metrics")   # not ranked
    for view, (name, rules) in VIEWS["daily"].items():
        score_view(ev, view, name, rules, order, names, raws, games, player_games, team_seasons, pg_team, mins,
                   team_minutes, established, seasons, snaps, excluded)
    print(f"daily board: {len(games)} games {games.date.min()} to {games.date.max()}, {len(excluded)} excluded, "
          f"{len(names)} metrics + consensus + {len(refs)} reference rows, views {', '.join(VIEWS['daily'])}")


def score_view(ev, view, name, rules, order, names, raws, games, player_games, team_seasons, pg_team, mins,
               team_minutes, established, seasons, snaps, excluded):
    """One view of the board under its rules: results.json, games.csv, teams.csv, picks.csv, centered.json."""
    game_ratings = np.zeros((len(order), len(games)))
    team_ratings = np.zeros((len(order), len(team_seasons)))
    checks = {}
    for i, k in enumerate(order):
        raw = raws[k]
        value, eligible, rated = ev.apply_rules(raw, player_games.last_min.values, rules["min_minutes"], rules["replacement"])
        game_ratings[i] = np.bincount(player_games.game, weights=player_games.weight * value, minlength=len(games))
        team_ratings[i] = 5 * np.bincount(pg_team, weights=value * mins, minlength=len(team_seasons)) / team_minutes
        known = established & rated
        checks[k] = {"coverage": float(mins[eligible & rated].sum() / mins[eligible].sum()),
                     "coverage_established": float(mins[known].sum() / mins[established].sum()),
                     "average_established": float(np.average(raw[known], weights=mins[known])) if known.any() else None}

    targets = (games.margin.values, team_seasons.win_pct.values, team_seasons.adjusted_margin.values)

    def score_rows(game_rows, team_rows):
        return ev.score(game_ratings, team_ratings, targets, game_rows, team_rows)

    every_game, every_team = np.arange(len(games)), np.arange(len(team_seasons))
    point = {"all": score_rows(every_game, every_team),
             "rebuilt": score_rows(every_game[games.rebuilt.values], every_team[team_seasons.rebuilt.values])}
    draws = ev.bootstrap(score_rows, games, team_seasons, 2000)
    results = ev.summarize(order, seasons, point, {SEASON: point["all"]}, draws, checks, 0.90)
    pairs = [p for p in ev.paired_differences(order, point, draws, 0.90) if p["a"] in names and p["b"] in names]

    out = RUNS / name
    out.mkdir(parents=True, exist_ok=True)
    meta = {"benchmark": "Hoop Impact Bench (HIB)", "board": "daily", "version": ev.VERSION, "seasons": seasons,
            "games": int(len(games)), "team_seasons": int(len(team_seasons)), "rules": rules, "confidence": 0.90,
            "resamples": 2000, "seed": ev.SEED, "harness": ev.sha256(WORK / "work" / "daily" / "eval.py"),
            "git_commit": ev.git_commit(), "first_game": games.date.min(), "scored_through": games.date.max(),
            "snapshot_days": sorted(snaps), "excluded_games": excluded}
    (out / "results.json").write_text(json.dumps({"meta": meta, "metrics": results, "pairs": pairs}, indent=1), encoding="utf-8")
    ev.write_logs(out, games, team_seasons, game_ratings, team_ratings, order)
    # picks.csv: each 2026-27 game's home-minus-away team rating per metric (raw: no fitted line, no home edge)
    pk = pd.DataFrame({k: game_ratings[i].round(4) for i, k in enumerate(order) if k in names})
    pk.insert(0, "game_id", games.game_id.values)
    pk[games.season.values == SEASON].to_csv(out / "picks.csv", index=False)
    centered.write(out / "centered.json", centered.scores(ev, order, names, team_ratings, games, team_seasons))

if __name__ == "__main__":
    main()
