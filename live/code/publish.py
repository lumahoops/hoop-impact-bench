"""Live track, step 3: turn the scoring runs into the public results both front ends read (GitHub Pages, lumahoops.org).

  python live/code/publish.py frozen | daily              both views of the board
  python live/code/publish.py frozen --history-only       only add this run's rows to the history files

Each board has two views (live/code/paths.py VIEWS), each with its own files, <stem> below:
  frozen   full forecast: frozen_full           established players: frozen (the registered rule, the old name)
  daily    full forecast: daily (the old name)  established players: daily_established
Reads   <HIB_WORK>/runs/<stem>/ (score.py: also <stem>_with_consensus/; daily_score.py), each with centered.json
        live/snapshots/                                   labels, sources and fingerprints committed before the games
Writes  live/results/<stem>.json         the board: metrics (ranked), reference rows (not ranked), pairwise gaps
        live/results/<stem>_games.csv    one row per game: the result and every row's predicted home margin
        live/results/<stem>_picks.csv    one row per game: each metric's home-minus-away team rating (the W-L picks)
        live/results/<stem>_history.csv  one row per metric per scoring run (appended), for "how the board moved"

Ranks come from the metrics only; the consensus is scored in a second run so it never shifts anyone's rank range.
Ranked by team net error, centered (from 2026-11-06; at face value 2026-11-01 to 11-05, still published as
net_rmse), shown from the first game; until every team has played NET_MIN_GAMES games the board carries an 'early'
note. No published field changes meaning: net_rmse stays the face-value error; net_rmse_centered and offset are new.
"""
import datetime
import json
import sys

import pandas as pd

from paths import DEFAULT_VIEW, RESULTS as OUT, RUNS, SNAPSHOTS, VIEW_NAMES, VIEWS
NET_MIN_GAMES = 20
TESTS = ["margin_r2", "winpct_r", "net_rmse"]          # from the harness runs; net_rmse_centered from centered.json
PRIMARY = "net_rmse_centered"
RULE_NOTE = {   # one line per view
    "full": "Every player counts at the metric's own rating, rookies and low-minute players included. A player the "
            "metric does not rate counts as -2.0.",
    "established": "A player with fewer than 250 minutes in 2025-26, including every rookie, counts as -2.0 for every "
                   "metric (Taylor Snarr's 2020 rule), and so does a player the metric does not rate.",
}

METRICS = {   # display name, maker, link (straight to the board the values come from)
    "loki": ("LOKI", "LUMA Basketball Research", "https://lumahoops.org/loki"),
    "xpm": ("xPM", "George Berry, VORP.app", "https://vorp.app"),
    "danny": ("EPM projection (Danny Harlan)", "Danny Harlan", "https://github.com/dannyharlan05/nba-epm-projections"),
    "epm": ("EPM", "Taylor Snarr, Dunks & Threes", "https://dunksandthrees.com/epm"),
    "darko": ("DARKO", "Kostya Medvedovsky", "https://www.darko.app/"),
    "pulse": ("Pulse", "CourtSignal", "https://courtsignal.net/ratings"),
    "openrapm": ("OpenRAPM", "Nathan Walker", "https://openrapm.com/"),
    "xrapm": ("xRAPM", "Jeremias Engelmann", "https://xrapm.com/"),
    "lebron": ("LEBRON", "BBall Index", "https://www.bball-index.com/lebron-database/"),
    "bpm_bbref": ("BPM (Basketball-Reference)", "Daniel Myers / Basketball-Reference",
                  "https://www.basketball-reference.com/leagues/NBA_2027_advanced.html"),
    "arc_2yr": ("ARC, 2-year", "LUMA Basketball Research", "https://lumahoops.org/arc"),
    "arc": ("ARC Live", "LUMA Basketball Research", "https://lumahoops.org/arc"),
}
OURS = {"loki", "arc_2yr", "arc"}
PRESEASON_LINK = {   # the preseason board uses last season's table where that is what was scored
    "bpm_bbref": "https://www.basketball-reference.com/leagues/NBA_2026_advanced.html"}
REFERENCE = {   # id: (display name, what it is)
    "ceiling_rapm_same_season": ("Same-season RAPM (ceiling)", "Plain RAPM fit on this season's games so far: it has seen the games it is computed on."),
    "consensus": ("Consensus of all metrics", "Each player's average across the ranked metrics that rate him (equal weights)."),
    "rapm_last_season": ("Last season's RAPM, no prior", "Plain RAPM fit on 2025-26 only, carried forward."),
    "baseline_last_team": ("Last season's team (floor)", "Each player = his main team's opponent-adjusted margin last season / 5."),
    "baseline_zero": ("Everyone 0 (floor)", None),   # description by view: ZERO_NOTE
}
ZERO_NOTE = {"full": "Every player 0, so every team is rated league average.",
             "established": "Every player 0; only the -2.0 for players under 250 minutes in 2025-26 separates teams."}


def games_per_team(per_team):
    lo, hi = int(per_team.min()), int(per_team.max())
    return f"{lo} game" if lo == hi == 1 else f"{lo} games" if lo == hi else f"{lo}-{hi} games"


def tests(m, c, ranked):
    """The harness's three tests plus the centered net error (c = the row's entry in centered.json)."""
    out = {}
    for t in TESTS:
        x = m["all"][t]
        out[t] = {"value": round(x["value"], 4), "interval": [round(v, 4) for v in x["interval"]]}
        if ranked:
            out[t]["rank"] = x["rank"]
    out[PRIMARY] = {"value": round(c["value"], 4), "interval": [round(v, 4) for v in c["interval"]]}
    if ranked:
        out[PRIMARY]["rank"] = c["rank"]
    return out


def main(board="frozen", *flags):
    if board == "preseason":
        board = "frozen"
    done = []
    for view, (stem, rules) in VIEWS[board].items():
        if not (RUNS / stem / "results.json").exists():
            print(f"live/results: no run for {stem} ({view}); skipped")
            continue
        publish(board, view, stem, rules, history_only="--history-only" in flags)
        done.append(stem)
    if not done:
        sys.exit(f"no runs to publish for {board}")


def publish(board, view, stem, rules, history_only=False):
    run_dir = RUNS / stem
    cen = json.loads((run_dir / "centered.json").read_text())
    if board == "frozen":
        name = "preseason"
        run = json.loads((run_dir / "results.json").read_text())
        cons = json.loads((RUNS / f"{stem}_with_consensus" / "results.json").read_text())
        snap = json.loads((SNAPSHOTS / f"{name}.json").read_text())
        games = pd.read_csv(run_dir / "games.csv", dtype={"game_id": str})
        cg = pd.read_csv(RUNS / f"{stem}_with_consensus" / "games.csv", dtype={"game_id": str})
        if run["meta"]["harness"] != cons["meta"]["harness"] or run["meta"]["games"] != cons["meta"]["games"]:
            sys.exit("the two runs disagree on the harness or the games")
        info = snap["metrics"]
        snap_meta = {"file": f"live/snapshots/{name}.json", "saved_at_utc": snap["saved_at_utc"]}
        title = ("The preseason board uses the ratings each metric had published before opening night of the 2026-27 NBA "
                 "season (October 20, 2026). These ratings stay fixed, and every 2026-27 regular-season game is computed using them.")
    else:
        run = json.loads((run_dir / "results.json").read_text())
        cons = run
        games = pd.read_csv(run_dir / "games.csv", dtype={"game_id": str})
        cg = games
        days = sorted((SNAPSHOTS / "daily").glob("*.json"))
        latest = json.loads(days[-1].read_text())
        info = {k: {**v, "label": v["status"]} for k, v in latest["metrics"].items()}
        snap_meta = {"files": "live/snapshots/daily/<date>.json", "latest": latest["date"],
                     "latest_saved_at_utc": latest["saved_at_utc"], "days": run["meta"]["snapshot_days"],
                     "excluded_games": run["meta"]["excluded_games"]}
        title = ("The dynamic board uses each metric's ratings as published on the morning of each game day, saved before "
                 "that day's first game. Metrics that do not update daily, or have published nothing new that morning, are "
                 "computed using their most recent ratings.")

    per_team = pd.concat([games.home, games.away]).value_counts()
    net_shown = bool(per_team.min() >= NET_MIN_GAMES)
    ranked = [k for k, v in run["metrics"].items() if not v["baseline"]]
    # picks: each metric's raw home-minus-away team rating per game (score.py / daily_score.py); its sign is the pick
    if run["meta"]["rules"] != rules or not set(ranked) <= set(cen["rows"]):
        sys.exit(f"{stem}: the run is not under the {view} rules, or centered.json does not match it")
    pk = pd.read_csv(run_dir / "picks.csv", dtype={"game_id": str}) \
        .merge(games[["game_id", "date", "home", "away", "home_pts", "away_pts"]], on="game_id").sort_values(["date", "game_id"])
    home_won = pk.home_pts > pk.away_pts
    wins = {k: int(((pk[k] > 0) == home_won).sum()) for k in ranked}
    metrics = []
    for k in sorted(ranked, key=lambda k: cen["rows"][k]["value"]):        # primary test: net error, centered
        m, s = run["metrics"][k], info[k]
        nm, maker, url = METRICS[k]
        url = PRESEASON_LINK.get(k, url) if board == "frozen" else url
        metrics.append({"id": k, "name": nm, "maker": maker, "url": url, "ours": k in OURS,
                        "label": s["label"], "source": s.get("source"), "sha256": s.get("sha256"), "players": s.get("rows"),
                        **({"as_of": s["as_of"]} if "as_of" in s else {}),
                        "coverage": round(m["coverage_established" if view == "established" else "coverage"], 4),
                        "record": {"w": wins[k], "l": len(pk) - wins[k]}, "offset": round(cen["rows"][k]["offset"], 4),
                        "tests": tests(m, cen["rows"][k], True)})
    reference = []
    for k, (nm, what) in REFERENCE.items():
        m = cons["metrics"]["consensus"] if k == "consensus" else run["metrics"].get(k)
        if m and k in cen["rows"]:
            reference.append({"id": k, "name": nm, "description": what or ZERO_NOTE[view],
                              "offset": round(cen["rows"][k]["offset"], 4), "tests": tests(m, cen["rows"][k], False)})
    pairs = [{"test": p["test"], "a": p["a"], "b": p["b"], "diff": round(p["diff"], 4),
              "interval": [round(v, 4) for v in p["interval"]],
              "separated": p["interval"][0] > 0 or p["interval"][1] < 0}
             for p in run["pairs"] + cen["pairs"] if p["part"] == "all" and p["a"] in ranked and p["b"] in ranked]

    meta = run["meta"]
    doc = {
        "board": board, "view": view, "view_name": VIEW_NAMES[view], "default_view": DEFAULT_VIEW,
        "views": {v: f"live/results/{s}.json" for v, (s, _) in VIEWS[board].items()},
        "season": "2026-27", "title": title, "rule_note": RULE_NOTE[view],
        "scored_through": games.date.max(), "first_game": games.date.min(), "games": int(len(games)),
        "games_per_team": {"min": int(per_team.min()), "max": int(per_team.max())},
        "updated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "primary_test": PRIMARY, "net_error_shown": True, "early": not net_shown,
        "net_error_note": (f"Early: {games_per_team(per_team)} per team. A few games decide each team's "
                           f"margin, so the ranges overlap and the floor rows score about the same as the metrics until "
                           f"every team has played {NET_MIN_GAMES}.") if not net_shown else "",
        "record_note": "W-L: each game counts as a win when the team the metric rates higher won (no home-court edge, the same for every metric)",
        "rules": meta["rules"], "confidence": meta["confidence"], "resamples": meta["resamples"],
        "harness_sha256": meta["harness"], "repo_commit": meta["git_commit"],
        "snapshot": snap_meta,
        "labels": ({"archived": "published by the maker before opening night, with a public date (archive snapshot, release or commit)",
                    "saved": "copied before opening night, with no public record of the date",
                    "backfill": "taken later from the maker's view of a past date, which shows its current model"}
                   if board == "frozen" else
                   {"pulled": "new ratings saved from the maker's site that morning",
                    "carried": "no new ratings published, so the most recent saved ratings are used",
                    "empty": "the ratings could not be saved that morning, so that day's games are left out for every metric"}),
        "tests": {"margin_r2": "Game R²: the share of the variation in final game margins that the predicted margins explain",
                  "winpct_r": "Win % r: the correlation between team ratings and team winning percentage",
                  "net_rmse": "Net error, raw: the average miss, in points per 100 possessions, between team ratings at face value and opponent-adjusted team margins",
                  PRIMARY: "Net error (the ranking test): the same miss after each metric's team ratings are shifted so its average team is 0, like the adjusted margins",
                  "offset": "The metric's average team rating, points per 100; raw net error squared = net error squared + offset squared"},
        "metrics": metrics, "reference": reference, "pairs": pairs,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    if not history_only:
        (OUT / f"{stem}.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        keep = ["season", "game_id", "date", "home", "away", "home_pts", "away_pts", "margin"]
        pred = ranked + [k for k in REFERENCE if k in games.columns]
        if board == "daily":
            pred = [p for p in pred if p != "consensus"]
        g = games[keep + pred].merge(cg[["game_id", "consensus"]], on="game_id", how="left")
        g.to_csv(OUT / f"{stem}_games.csv", index=False)
        pk[["game_id", "date", "home", "away", "home_pts", "away_pts"] + ranked].round(2) \
            .to_csv(OUT / f"{stem}_picks.csv", index=False)

    hist_path = OUT / f"{stem}_history.csv"
    rows = []
    for item in metrics + reference:
        t = item["tests"]
        c = t[PRIMARY]
        rows.append({"scored_through": doc["scored_through"], "games": doc["games"], "id": item["id"],
                     "margin_r2": t["margin_r2"]["value"], "margin_r2_lo": t["margin_r2"]["interval"][0],
                     "margin_r2_hi": t["margin_r2"]["interval"][1],
                     "rank_lo": t["margin_r2"].get("rank", [None, None])[0], "rank_hi": t["margin_r2"].get("rank", [None, None])[1],
                     "winpct_r": t["winpct_r"]["value"],
                     # from 2026-11-06 (earlier rows backfilled from the saved files): net error raw and centered
                     "net_rmse": t["net_rmse"]["value"], "net_rmse_centered": c["value"],
                     "net_rmse_centered_lo": c["interval"][0], "net_rmse_centered_hi": c["interval"][1],
                     "net_rank_lo": c.get("rank", [None, None])[0], "net_rank_hi": c.get("rank", [None, None])[1],
                     "offset": item["offset"]})
    new = pd.DataFrame(rows)
    if hist_path.exists():
        old = pd.read_csv(hist_path)
        new = pd.concat([old[old.scored_through != doc["scored_through"]], new])
    new.sort_values("scored_through", kind="stable").to_csv(hist_path, index=False)
    print(f"live/results: {stem}.json ({view}: {len(metrics)} metrics, {len(reference)} reference rows, {len(pairs)} pairs)"
          f"{', games and picks' if not history_only else ' not rewritten (history only)'}, {stem}_history.csv; "
          f"through {doc['scored_through']}, ranked by net error, centered{' (early)' if not net_shown else ''}")


if __name__ == "__main__":
    main(*sys.argv[1:])
