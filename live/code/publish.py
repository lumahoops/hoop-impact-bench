"""Live track, step 3: turn a scoring run into the public results both front ends read (GitHub Pages, lumahoops.org).

  python live/code/publish.py frozen | daily

Reads   <HIB_WORK>/runs/frozen/, frozen_with_consensus/   (score.py)       or   <HIB_WORK>/runs/daily/ (daily_score.py)
        live/snapshots/                                   labels, sources and fingerprints committed before the games
Writes  live/results/<board>.json         the board: metrics (ranked), reference rows (not ranked), pairwise gaps
        live/results/<board>_games.csv    one row per game: the result and every row's predicted home margin
        live/results/<board>_history.csv  one row per metric per scoring run (appended), for "how the board moved"

Ranks come from the 11 metrics only; the consensus is scored in a second run so it never shifts anyone's rank range.
Net error is published but flagged hidden until every team has played NET_MIN_GAMES games.
"""
import datetime
import json
import sys

import pandas as pd

from paths import RESULTS as OUT, RUNS, SNAPSHOTS
NET_MIN_GAMES = 20
TESTS = ["margin_r2", "winpct_r", "net_rmse"]

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
    "ceiling_rapm_same_season": ("Same-season RAPM (ceiling)", "Plain RAPM fit on this season's games so far: it has seen the games it is scored on."),
    "consensus": ("Consensus of all metrics", "Each player's average across the ranked metrics that rate him (equal weights)."),
    "rapm_last_season": ("Last season's RAPM, no prior", "Plain RAPM fit on 2025-26 only, carried forward."),
    "baseline_last_team": ("Last season's team (floor)", "Each player = his main team's opponent-adjusted margin last season / 5."),
    "baseline_zero": ("Everyone 0 (floor)", "Every player 0; only the -2.0 for low-minute players separates teams."),
}


def tests(m, ranked):
    out = {}
    for t in TESTS:
        x = m["all"][t]
        out[t] = {"value": round(x["value"], 4), "interval": [round(v, 4) for v in x["interval"]]}
        if ranked:
            out[t]["rank"] = x["rank"]
    return out


def main(board="frozen"):
    if board == "preseason":
        board = "frozen"
    if board == "frozen":
        name = "preseason"
        run = json.loads((RUNS / "frozen" / "results.json").read_text())
        cons = json.loads((RUNS / "frozen_with_consensus" / "results.json").read_text())
        snap = json.loads((SNAPSHOTS / f"{name}.json").read_text())
        games = pd.read_csv(RUNS / "frozen" / "games.csv", dtype={"game_id": str})
        cg = pd.read_csv(RUNS / "frozen_with_consensus" / "games.csv", dtype={"game_id": str})
        if run["meta"]["harness"] != cons["meta"]["harness"] or run["meta"]["games"] != cons["meta"]["games"]:
            sys.exit("the two runs disagree on the harness or the games")
        info = snap["metrics"]
        snap_meta = {"file": f"live/snapshots/{name}.json", "saved_at_utc": snap["saved_at_utc"]}
        title = "Preseason board: each metric's rating saved before opening night (2026-10-20), never updated"
    else:
        run = json.loads((RUNS / "daily" / "results.json").read_text())
        cons = run
        games = pd.read_csv(RUNS / "daily" / "games.csv", dtype={"game_id": str})
        cg = games
        days = sorted((SNAPSHOTS / "daily").glob("*.json"))
        latest = json.loads(days[-1].read_text())
        info = {k: {**v, "label": v["status"]} for k, v in latest["metrics"].items()}
        snap_meta = {"files": "live/snapshots/daily/<date>.json", "latest": latest["date"],
                     "latest_saved_at_utc": latest["saved_at_utc"], "days": run["meta"]["snapshot_days"],
                     "excluded_games": run["meta"]["excluded_games"]}
        title = ("Dynamic board: each game scored with every metric's rating exactly as published that morning, saved "
                 "before tip-off (season-to-date ratings as published; metrics that publish nothing newer carry their "
                 "latest value)")

    per_team = pd.concat([games.home, games.away]).value_counts()
    net_shown = bool(per_team.min() >= NET_MIN_GAMES)
    ranked = [k for k, v in run["metrics"].items() if not v["baseline"]]
    metrics = []
    for k in sorted(ranked, key=lambda k: -run["metrics"][k]["all"]["margin_r2"]["value"]):
        m, s = run["metrics"][k], info[k]
        nm, maker, url = METRICS[k]
        url = PRESEASON_LINK.get(k, url) if board == "frozen" else url
        metrics.append({"id": k, "name": nm, "maker": maker, "url": url, "ours": k in OURS,
                        "label": s["label"], "source": s["source"], "sha256": s.get("sha256"), "players": s.get("rows"),
                        **({"as_of": s["as_of"]} if "as_of" in s else {}),
                        "coverage": round(m["coverage_established" if board == "frozen" else "coverage"], 4), "tests": tests(m, True)})
    reference = []
    for k, (nm, what) in REFERENCE.items():
        m = cons["metrics"]["consensus"] if k == "consensus" else run["metrics"].get(k)
        if m:
            reference.append({"id": k, "name": nm, "description": what, "tests": tests(m, False)})
    pairs = [{"test": p["test"], "a": p["a"], "b": p["b"], "diff": round(p["diff"], 4),
              "interval": [round(v, 4) for v in p["interval"]],
              "separated": p["interval"][0] > 0 or p["interval"][1] < 0}
             for p in run["pairs"] if p["part"] == "all" and p["a"] in ranked and p["b"] in ranked]

    meta = run["meta"]
    doc = {
        "board": board, "season": "2026-27", "title": title,
        "scored_through": games.date.max(), "first_game": games.date.min(), "games": int(len(games)),
        "games_per_team": {"min": int(per_team.min()), "max": int(per_team.max())},
        "updated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "net_error_shown": net_shown, "net_error_note": f"hidden until every team has played {NET_MIN_GAMES} games",
        "rules": meta["rules"], "confidence": meta["confidence"], "resamples": meta["resamples"],
        "harness_sha256": meta["harness"], "repo_commit": meta["git_commit"],
        "snapshot": snap_meta,
        "labels": ({"archived": "published before the games, with proof (dated public record or release fingerprint)",
                    "saved": "saved by us before the games, no public record of the date",
                    "backfill": "taken later from the site's own view of that date (the site's current model)"}
                   if board == "frozen" else
                   {"pulled": "fetched from the maker's site that morning and fingerprinted before the games",
                    "carried": "the metric published nothing newer, so its latest saved value was reused",
                    "empty": "the pull failed all morning; that day's games are left off the board for every metric"}),
        "tests": {"margin_r2": "Game margins R²: how much of each game's margin the ratings x actual minutes explain",
                  "winpct_r": "Team win % r: correlation between team ratings and team win %",
                  "net_rmse": "Team net error: points per 100 between team ratings and opponent-adjusted margins"},
        "metrics": metrics, "reference": reference, "pairs": pairs,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{board}.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    keep = ["season", "game_id", "date", "home", "away", "home_pts", "away_pts", "margin"]
    pred = ranked + [k for k in REFERENCE if k in games.columns]
    if board == "daily":
        pred = [p for p in pred if p != "consensus"]
    g = games[keep + pred].merge(cg[["game_id", "consensus"]], on="game_id", how="left")
    g.to_csv(OUT / f"{board}_games.csv", index=False)

    hist_path = OUT / f"{board}_history.csv"
    rows = []
    for item in metrics + reference:
        t = item["tests"]
        rows.append({"scored_through": doc["scored_through"], "games": doc["games"], "id": item["id"],
                     "margin_r2": t["margin_r2"]["value"], "margin_r2_lo": t["margin_r2"]["interval"][0],
                     "margin_r2_hi": t["margin_r2"]["interval"][1],
                     "rank_lo": t["margin_r2"].get("rank", [None, None])[0], "rank_hi": t["margin_r2"].get("rank", [None, None])[1],
                     "winpct_r": t["winpct_r"]["value"]})
    new = pd.DataFrame(rows)
    if hist_path.exists():
        old = pd.read_csv(hist_path)
        new = pd.concat([old[old.scored_through != doc["scored_through"]], new])
    new.to_csv(hist_path, index=False)
    print(f"live/results: {board}.json ({len(metrics)} metrics, {len(reference)} reference rows, {len(pairs)} pairs), "
          f"{board}_games.csv ({len(g)} games), {board}_history.csv; through {doc['scored_through']}, "
          f"net error {'shown' if net_shown else 'hidden'}")


if __name__ == "__main__":
    main(*sys.argv[1:])
