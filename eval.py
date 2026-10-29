"""
Hoop Impact Bench (HIB) v1: do last season's impact-metric values predict this season?

Bring one CSV per metric with columns season,nba_id,rating. `rating` is the value that was known before that
season's opening night (last season's value, or a preseason projection), in points per 100 possessions; nba_id is the
NBA.com person id. The file name is the metric's name.

Rules, the same for every metric (Taylor Snarr's 2020 retrodiction rules):
  players who played under 250 minutes the season before, rookies included, count as -2.0 (replacement level);
  players missing from a file count as -2.0.
A team's rating, in a game or over a season, is 5 x the minutes-weighted mean of its players' values.

Tests
  game margins     R^2 of each game's final margin on home-minus-away team rating (one straight line, home edge in)
  team win %       correlation between team-season rating and win % (Krishna Narsu's 2024 test)
  team net rating  RMSE between team-season rating, taken at face value, and the team's average margin adjusted for
                   opponents and home court (Snarr's 2020 test)
  rebuilt rosters  the same scores on the third of games / teams that kept the least of last season's minutes
Every score gets a bootstrap interval and a rank range (team-seasons resampled, the same resamples for every metric).

Usage
  python eval.py                         the bundled metrics (ratings/)
  python eval.py --ratings mine.csv      add yours: CSV files or folders of CSVs
  python eval.py --baselines             add reference rows: every player 0, last season's team, same-season RAPM
  python eval.py --by-season             also print every score season by season
  python eval.py --confidence 0.95       interval level (default 0.90)
  python eval.py --min-minutes 0         score every file as-is: only players missing from a file get --replacement
  python eval.py --replacement -1.0      the value those players get (default -2.0)
  python eval.py --out my_run            save the run somewhere else (default runs/<date_time>)

Each run folder holds results.json (every score, interval and rank range, plus a sha256 fingerprint of each input
file), games.csv (every game's actual margin and each metric's predicted margin) and teams.csv (every team-season's
results and each metric's team rating).
"""
import argparse
import datetime
import hashlib
import json
import platform
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
VERSION = "1.0.0-dev"
STANDARD = {"min_minutes": 250, "replacement": -2.0}
SEED = 7
TESTS = [("margin_r2", "game margin R2", True), ("winpct_r", "team win % r", True), ("net_rmse", "team net RMSE", False)]
BASELINES = {
    "baseline_zero": "every player 0, so only the -2.0 rule separates teams",
    "baseline_last_team": "each player = his main team's opponent-adjusted margin last season / 5",
    "ceiling_rapm_same_season": "RAPM fit on the season being scored: it has seen those games",
}


def season_after(season, k=1):
    """'2024-25' -> '2025-26' (k=1); k=-1 goes back a season"""
    y = int(season[:4]) + k
    return f"{y}-{str(y + 1)[2:]}"


def prev(season):
    return season_after(season, -1)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git_commit():
    """The repo commit this copy was run from, if it is a git checkout."""
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


# ---------------------------------------------------------------- inputs

def read_ratings(path):
    """One metric's CSV, refused with the reason if anything would score silently wrong."""
    d = pd.read_csv(path)
    need = ["season", "nba_id", "rating"]
    missing = [c for c in need if c not in d.columns]
    if missing:
        raise SystemExit(f"{path.name}: missing column(s) {missing}; need {need}")
    d = d[need].copy()
    bad = ~d.season.astype(str).str.fullmatch(r"\d{4}-\d{2}")
    if bad.any():
        raise SystemExit(f"{path.name}, row {bad.idxmax() + 2}: season must look like 2024-25")
    for c in ("nba_id", "rating"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
        if d[c].isna().any():
            raise SystemExit(f"{path.name}, row {d[c].isna().idxmax() + 2}: {c} is missing or not a number")
    d["nba_id"] = d.nba_id.astype(int)
    dup = d.duplicated(["season", "nba_id"])
    if dup.any():
        raise SystemExit(f"{path.name}, row {dup.idxmax() + 2}: a second rating for the same player and season")
    return d


def csv_files(paths):
    files = []
    for p in map(Path, paths):
        if p.is_dir():
            files += sorted(p.glob("*.csv"))
        elif p.is_file() and p.suffix.lower() == ".csv":
            files.append(p)
        else:
            raise SystemExit(f"{p}: not a CSV file or a folder")
    names = [f.stem for f in files]
    clash = sorted({n for n in names if names.count(n) > 1} | (set(names) & set(BASELINES)))
    if clash:
        raise SystemExit(f"these names are taken twice: {clash}; every metric needs its own file name")
    return files


# ---------------------------------------------------------------- season data

def opponent_adjusted(G):
    """Each team-season's average margin adjusted for opponents and home court (least squares, as in SRS)."""
    out = {}
    for s, g in G.groupby("season"):
        teams = sorted(set(g.home) | set(g.away))
        ix = {t: i for i, t in enumerate(teams)}
        X = np.zeros((len(g), len(teams) + 1))
        rows = np.arange(len(g))
        X[rows, [ix[t] for t in g.home]] = 1.0
        X[rows, [ix[t] for t in g.away]] = -1.0
        X[:, -1] = 1.0 - g.neutral.values                                  # home edge
        team = np.linalg.lstsq(X, g.margin.values, rcond=None)[0][:-1]
        out.update({(s, t): team[ix[t]] - team.mean() for t in teams})
    return pd.Series(out)


def baselines(games, minutes):
    """Reference rows built from the game data (plus the same-season RAPM file in reference/)."""
    adj = opponent_adjusted(games)
    season_min = minutes.groupby(["season", "team", "nba_id"], as_index=False)["min"].sum()
    main_team = season_min.sort_values("min").drop_duplicates(["season", "nba_id"], keep="last")
    last = pd.DataFrame({"season": main_team.season.map(season_after), "nba_id": main_team.nba_id,
                         "rating": [adj[(s, t)] / 5 for s, t in zip(main_team.season, main_team.team)]})
    zero = season_min[["season", "nba_id"]].drop_duplicates().assign(rating=0.0)
    return {"baseline_zero": zero, "baseline_last_team": last,
            "ceiling_rapm_same_season": read_ratings(HERE / "reference" / "rapm_same_season.csv")}


def prepare(systems, games, minutes):
    """Seasons every metric covers, plus the games, player-minutes and team-seasons in them."""
    have = set(games.season)
    seasons = sorted(s for s in set.intersection(*(set(d.season) for d in systems.values()))
                     if s in have and prev(s) in have)
    if not seasons:
        cover = ", ".join(f"{k} {d.season.min()} to {d.season.max()}" for k, d in systems.items())
        raise SystemExit(f"no season is covered by every metric and the game data ({cover}; games "
                         f"{min(have)} to {max(have)}, the first season only supplies last-season minutes)")

    season_min = minutes.groupby(["season", "team", "nba_id"], as_index=False)["min"].sum()
    last_min = season_min.groupby(["season", "nba_id"])["min"].sum()

    def minutes_last_season(d):
        key = pd.MultiIndex.from_arrays([d.season.map(prev), d.nba_id])
        return last_min.reindex(key).fillna(0.0).values

    continuity = {}
    for s in seasons:
        before = season_min[season_min.season == prev(s)]
        kept = set(zip(before.team, before.nba_id))
        for t, d in season_min[season_min.season == s].groupby("team"):
            continuity[(s, t)] = d["min"][[(t, p) in kept for p in d.nba_id]].sum() / d["min"].sum()

    G = games[games.season.isin(seasons)].sort_values(["date", "game_id"]).reset_index(drop=True)
    cont = np.minimum([continuity[(s, t)] for s, t in zip(G.season, G.home)],
                      [continuity[(s, t)] for s, t in zip(G.season, G.away)])
    G["low"] = cont <= np.quantile(cont, 1 / 3)
    G["cluster"] = list(zip(G.season, G.home))                             # resampling unit: home team-season

    M = minutes[minutes.game_id.isin(G.game_id)].reset_index(drop=True)    # one row per player per game
    M["game"] = M.game_id.map(pd.Series(G.index, index=G.game_id)).values
    team_game_min = M.groupby(["game_id", "team"])["min"].transform("sum")
    home = M.team.values == G.home.values[M.game]
    M["weight"] = np.where(home, 1.0, -1.0) * 5 * M["min"] / team_game_min
    M["last_min"] = minutes_last_season(M)

    side = lambda team, margin: pd.DataFrame({"season": G.season, "team": team, "margin": margin})
    by_team = pd.concat([side(G.home, G.margin), side(G.away, -G.margin)]).groupby(["season", "team"]).margin
    T = pd.DataFrame({"winpct": by_team.apply(lambda m: (m > 0).mean()), "net": opponent_adjusted(G)})
    T.index.names = ["season", "team"]
    T["continuity"] = [continuity[i] for i in T.index]
    T["low"] = T.continuity <= np.quantile(T.continuity, 1 / 3)

    S = season_min[season_min.season.isin(seasons)].reset_index(drop=True)  # one row per player per team-season
    S["last_min"] = minutes_last_season(S)
    S["team_row"] = T.index.get_indexer(pd.MultiIndex.from_arrays([S.season, S.team]))
    return seasons, G, M, S, T


# ---------------------------------------------------------------- scoring

def player_values(rows, ratings, min_minutes, replacement):
    """Each row's value under the rules; also whether the rules left him to the file, and whether the file rates him."""
    key = pd.MultiIndex.from_arrays([rows.season, rows.nba_id])
    r = ratings.set_index(["season", "nba_id"]).rating.reindex(key).values
    eligible = rows.last_min.values >= min_minutes
    rated = ~np.isnan(r)
    return np.where(eligible & rated, r, replacement), eligible, rated


def correlations(A, b):
    """Correlation of every row of A with b."""
    Ac, bc = A - A.mean(axis=1, keepdims=True), b - b.mean()
    return (Ac @ bc) / np.sqrt((Ac * Ac).sum(axis=1) * (bc @ bc))


def evaluate(systems, seasons, G, M, S, T, min_minutes, replacement, confidence, resamples):
    names = list(systems)
    X = np.zeros((len(names), len(G)))                                      # home minus away team rating per game
    R = np.zeros((len(names), len(T)))                                      # team-season rating
    coverage = {}
    team_minutes = np.bincount(S.team_row, weights=S["min"], minlength=len(T))
    for i, k in enumerate(names):
        d = systems[k][systems[k].season.isin(seasons)]
        v, eligible, rated = player_values(M, d, min_minutes, replacement)
        X[i] = np.bincount(M.game, weights=M.weight * v, minlength=len(G))
        coverage[k] = float(M["min"][eligible & rated].sum() / M["min"][eligible].sum())
        v, _, _ = player_values(S, d, min_minutes, replacement)
        R[i] = 5 * np.bincount(S.team_row, weights=v * S["min"], minlength=len(T)) / team_minutes
    y, winpct, net = G.margin.values, T.winpct.values, T.net.values

    def scores(gi, ti):
        """tests x metrics, on game rows gi and team rows ti"""
        return np.vstack([correlations(X[:, gi], y[gi]) ** 2, correlations(R[:, ti], winpct[ti]),
                          np.sqrt(((R[:, ti] - net[ti]) ** 2).mean(axis=1))])

    every_g, every_t = np.arange(len(G)), np.arange(len(T))
    parts = {"all": (every_g, every_t), "rebuilt": (every_g[G.low.values], every_t[T.low.values])}
    point = {p: scores(*rows) for p, rows in parts.items()}
    season_of = T.index.get_level_values(0)
    by_season = {s: scores(np.flatnonzero(G.season == s), np.flatnonzero(season_of == s)) for s in seasons}

    # bootstrap: resample team-seasons; a game goes with its home team-season; every metric sees the same resamples
    games_of = {c: [] for c in T.index}
    for i, c in enumerate(G.cluster):
        games_of[c].append(i)
    games_of = [np.array(games_of[c], dtype=int) for c in T.index]
    low_g, low_t = G.low.values, T.low.values
    rng = np.random.default_rng(SEED)
    boot = {p: np.zeros((resamples, len(TESTS), len(names))) for p in parts}
    for b in range(resamples):
        pick = rng.integers(0, len(T), len(T))
        gi = np.concatenate([games_of[c] for c in pick])
        boot["all"][b] = scores(gi, pick)
        boot["rebuilt"][b] = scores(gi[low_g[gi]], pick[low_t[pick]])

    q = [(1 - confidence) / 2, (1 + confidence) / 2]
    ranked = [i for i, k in enumerate(names) if k not in BASELINES]          # reference rows get no rank
    out = {k: {"baseline": k in BASELINES, "coverage": coverage[k],
               "by_season": {s: {t: float(by_season[s][j, i]) for j, (t, _, _) in enumerate(TESTS)} for s in seasons}}
           for i, k in enumerate(names)}
    for p in parts:
        for j, (t, _, higher) in enumerate(TESTS):
            draws = boot[p][:, j, ranked]
            ranks = (-draws if higher else draws).argsort(axis=1).argsort(axis=1) + 1
            for i, k in enumerate(names):
                s = {"value": float(point[p][j, i]), "interval": [float(v) for v in np.quantile(boot[p][:, j, i], q)]}
                if i in ranked:
                    r = ranks[:, ranked.index(i)]
                    s["rank"] = [int(np.quantile(r, q[0], method="lower")), int(np.quantile(r, q[1], method="higher"))]
                out[k].setdefault(p, {})[t] = s
    return out, X, R


def write_logs(out, G, T, X, R, names):
    """games.csv and teams.csv: the per-game and per-team-season numbers behind every score."""
    g = G[["season", "game_id", "date", "home", "away", "home_pts", "away_pts", "margin"]].copy()
    g["rebuilt"] = G.low.astype(int)
    for i, k in enumerate(names):                                           # predicted margin from the run's line
        slope, edge = np.polyfit(X[i], G.margin.values, 1)
        g[k] = (edge + slope * X[i]).round(2)
    g.to_csv(out / "games.csv", index=False)
    t = T.reset_index().rename(columns={"winpct": "win_pct", "net": "adjusted_margin", "low": "rebuilt"})
    t["rebuilt"] = t.rebuilt.astype(int)
    t["win_pct"], t["adjusted_margin"], t["continuity"] = t.win_pct.round(3), t.adjusted_margin.round(2), t.continuity.round(3)
    for i, k in enumerate(names):
        t[k] = R[i].round(3)
    t.to_csv(out / "teams.csv", index=False)


# ---------------------------------------------------------------- report

def num(v, digits=3):
    s = f"{v:.{digits}f}"
    return s.replace("0.", ".", 1) if abs(v) < 1 else s


def fmt(test, v):
    """Errors in points (2 decimals); R2 and r as .xxx"""
    return f"{v:.2f}" if test == "net_rmse" else num(v)


def report(meta, res, by_season, saved):
    c = int(round(meta["confidence"] * 100))
    rules = meta["rules"]
    if rules["min_minutes"] > 0:
        rule = (f"under {rules['min_minutes']:g} minutes last season (rookies included) = {rules['replacement']:.1f}; "
                f"not in a file = {rules['replacement']:.1f}")
    else:
        rule = f"every file as-is; not in a file = {rules['replacement']:.1f}"
    rule += "   [v1 standard]" if rules == STANDARD else "   [custom rules]"
    L = [f"Hoop Impact Bench (HIB) v{meta['version']}",
         "Do last season's impact-metric values predict this season?", "",
         f"  seasons    {meta['seasons'][0]} to {meta['seasons'][-1]}: {meta['games']:,} games, "
         f"{meta['team_seasons']} team-seasons",
         f"  rules      {rule}",
         f"  intervals  {c}%, {meta['resamples']:,} resamples of team-seasons, the same for every metric"]
    refs = [k for k in res if res[k]["baseline"]]
    if refs:
        L += ["  baselines  not ranked:"] + [f"             {k}: {BASELINES[k]}" for k in refs]
    L += [""]
    w = max(len(k) for k in res) + 2

    def ranked(part, t, title, note, higher):
        out = [title, f"  {note}", f"  {'rank':<7}{'metric':<{w}}{'score':>7}   {c}% interval"]
        for k in sorted(res, key=lambda k: res[k][part][t]["value"], reverse=higher):
            s = res[k][part][t]
            lo, hi = s.get("rank", (None, None))
            rank = "-" if lo is None else str(lo) if lo == hi else f"{lo}-{hi}"
            out.append(f"  {rank:<7}{k:<{w}}{fmt(t, s['value']):>7}   {fmt(t, s['interval'][0])} to {fmt(t, s['interval'][1])}")
        return out + [""]

    L += ranked("all", "margin_r2", "GAME MARGINS", "share of each game's final margin the ratings explain, R2 "
                "(higher is better)", True)
    L += ranked("all", "winpct_r", "TEAM WIN %", "correlation with team win %, r (higher is better; Narsu 2024)", True)
    L += ranked("all", "net_rmse", "TEAM NET RATING", "ratings at face value vs opponent-adjusted margin, error in "
                "points (lower is better; Snarr 2020)", False)

    L += ["REBUILT ROSTERS", "  the same tests on the third of games and teams that kept the least of last season's minutes",
          f"  {'':<7}{'metric':<{w}}{'game R2':<20}{'win % r':<20}{'net RMSE':<20}"]
    cell = lambda t, s: f"{fmt(t, s['value'])} ({fmt(t, s['interval'][0])}-{fmt(t, s['interval'][1])})"
    for k in sorted(res, key=lambda k: res[k]["rebuilt"]["margin_r2"]["value"], reverse=True):
        L.append(f"  {'':<7}{k:<{w}}" + "".join(f"{cell(t, res[k]['rebuilt'][t]):<20}" for t, _, _ in TESTS))

    order = sorted(res, key=lambda k: res[k]["all"]["margin_r2"]["value"], reverse=True)
    metrics = [k for k in order if not res[k]["baseline"]]
    L += ["", "COVERAGE", "  share of the minutes left to each file (players over the minutes cutoff) that the file rates"]
    L += ["  " + "   ".join(f"{k} {res[k]['coverage']:.0%}" for k in metrics[i:i + 5]) for i in range(0, len(metrics), 5)]
    L += [""]
    if by_season:
        for t, label, _ in TESTS:
            L += [f"BY SEASON: {label}", f"  {'':<7}{'metric':<{w}}" + "".join(f"{s:>9}" for s in meta["seasons"])]
            L += [f"  {'':<7}{k:<{w}}" + "".join(f"{fmt(t, v[t]):>9}" for v in res[k]["by_season"].values()) for k in order]
            L += [""]
    L.append(f"Saved {saved}")
    L.append("  results.json (scores, intervals, rank ranges, input fingerprints), games.csv (per game), teams.csv (per team)")
    return "\n".join(L)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ratings", nargs="+", default=[], help="CSV files or folders of CSVs (season,nba_id,rating)")
    ap.add_argument("--no-bundled", action="store_true", help="leave out the metrics in ratings/")
    ap.add_argument("--baselines", action="store_true", help="add the reference rows (not ranked)")
    ap.add_argument("--by-season", action="store_true", help="also print every score season by season")
    ap.add_argument("--confidence", type=float, default=0.90, help="interval level, e.g. 0.90 or 0.95")
    ap.add_argument("--min-minutes", type=float, default=STANDARD["min_minutes"],
                    help="players under this many minutes last season get --replacement (0 = use every file as-is)")
    ap.add_argument("--replacement", type=float, default=STANDARD["replacement"])
    ap.add_argument("--resamples", type=int, default=2000)
    ap.add_argument("--out", help="folder for the run (default: runs/<date_time>)")
    a = ap.parse_args()
    if not 0 < a.confidence < 1:
        raise SystemExit("--confidence must be between 0 and 1, e.g. 0.90")

    files = csv_files(([] if a.no_bundled else [HERE / "ratings"]) + a.ratings)
    games = pd.read_csv(HERE / "data" / "games.csv", dtype={"game_id": str})
    games["margin"] = (games.home_pts - games.away_pts).astype(float)
    minutes = pd.read_csv(HERE / "data" / "minutes.csv", dtype={"game_id": str})
    systems = {f.stem: read_ratings(f) for f in files}
    if a.baselines:
        systems.update(baselines(games, minutes))
        files.append(HERE / "reference" / "rapm_same_season.csv")
    if not systems:
        raise SystemExit("nothing to score: add --ratings or --baselines, or drop --no-bundled")
    seasons, G, M, S, T = prepare(systems, games, minutes)
    res, X, R = evaluate(systems, seasons, G, M, S, T, a.min_minutes, a.replacement, a.confidence, a.resamples)

    out = Path(a.out) if a.out else HERE / "runs" / datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    meta = {"benchmark": "Hoop Impact Bench (HIB)", "version": VERSION, "seasons": seasons, "games": len(G),
            "team_seasons": len(T), "rules": {"min_minutes": a.min_minutes, "replacement": a.replacement},
            "confidence": a.confidence, "resamples": a.resamples, "seed": SEED,
            "harness": sha256(Path(__file__)), "git_commit": git_commit(),
            "environment": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__},
            "inputs": {f.name: sha256(f) for f in [HERE / "data" / "games.csv", HERE / "data" / "minutes.csv"] + files}}
    (out / "results.json").write_text(json.dumps({"meta": meta, "metrics": res}, indent=1), encoding="utf-8")
    write_logs(out, G, T, X, R, list(systems))
    print(report(meta, res, a.by_season, out))


if __name__ == "__main__":
    main()
