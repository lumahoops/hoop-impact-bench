"""
HoopBench v1 (working name): do last season's impact-metric values predict this season?

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
  calibration      slope of the game-margin line: actual points per rating point (1.00 = face value)
  rebuilt rosters  the same scores on the third of games / teams that kept the least of last season's minutes
Every score gets a bootstrap interval (team-seasons resampled, the same resamples for every metric); the three ranked
tests also get a rank range from the same resamples.

Usage
  python eval.py                         the bundled metrics (ratings/)
  python eval.py --ratings mine.csv      add yours: CSV files or folders of CSVs
  python eval.py --by-season             also print every score season by season
  python eval.py --confidence 0.95       interval level (default 0.90)
  python eval.py --min-minutes 0         score every file as-is: only players missing from a file get --replacement
  python eval.py --replacement -1.0      the value those players get (default -2.0)
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
VERSION = "1.0.0-dev"
STANDARD = {"min_minutes": 250, "replacement": -2.0}
SEED = 7


def prev(season):
    """'2024-25' -> '2023-24'"""
    y = int(season[:4]) - 1
    return f"{y}-{str(y + 1)[2:]}"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


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
    clash = sorted({n for n in names if names.count(n) > 1})
    if clash:
        raise SystemExit(f"two files share the name {clash}; every metric needs its own file name")
    return files


# ---------------------------------------------------------------- the season data

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
    G["margin"] = (G.home_pts - G.away_pts).astype(float)
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
    T["low"] = [continuity[i] <= np.quantile(list(continuity.values()), 1 / 3) for i in T.index]

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


def game_scores(x, y):
    xm, ym = x - x.mean(), y - y.mean()
    sxx, syy, sxy = (xm * xm).sum(), (ym * ym).sum(), (xm * ym).sum()
    return {"margin_r2": sxy * sxy / (sxx * syy), "slope": sxy / sxx}


def team_scores(rating, winpct, net):
    return {"winpct_r": float(np.corrcoef(rating, winpct)[0, 1]), "net_rmse": float(np.sqrt(((rating - net) ** 2).mean()))}


TESTS = [  # key, label, higher is better
    ("margin_r2", "game margin R2", True), ("winpct_r", "team win % r", True),
    ("net_rmse", "team net RMSE", False), ("slope", "calibration slope", None)]


def evaluate(systems, seasons, G, M, S, T, min_minutes, replacement, confidence, resamples):
    y, winpct, net = G.margin.values, T.winpct.values, T.net.values
    low_g, low_t = G.low.values, T.low.values
    X, R, coverage = {}, {}, {}
    for k, d in systems.items():
        d = d[d.season.isin(seasons)]
        v, eligible, rated = player_values(M, d, min_minutes, replacement)
        X[k] = np.bincount(M.game, weights=M.weight * v, minlength=len(G))      # home minus away rating per game
        coverage[k] = float(M["min"][eligible & rated].sum() / M["min"][eligible].sum())
        v, _, _ = player_values(S, d, min_minutes, replacement)
        R[k] = 5 * np.bincount(S.team_row, weights=v * S["min"], minlength=len(T)) / np.bincount(
            S.team_row, weights=S["min"], minlength=len(T))                     # team-season rating

    def scores(k, gi, ti):
        return {**game_scores(X[k][gi], y[gi]), **team_scores(R[k][ti], winpct[ti], net[ti])}

    every_g, every_t = np.arange(len(G)), np.arange(len(T))
    point = {k: {"all": scores(k, every_g, every_t), "rebuilt": scores(k, every_g[low_g], every_t[low_t])} for k in systems}
    by_season = {k: {s: scores(k, np.flatnonzero(G.season == s), np.flatnonzero(T.index.get_level_values(0) == s))
                     for s in seasons} for k in systems}

    # bootstrap: resample team-seasons; a game goes with its home team-season; every metric sees the same resamples
    clusters = list(T.index)
    games_of = {c: [] for c in clusters}
    for i, c in enumerate(G.cluster):
        games_of[c].append(i)
    games_of = [np.array(games_of[c], dtype=int) for c in clusters]
    rng = np.random.default_rng(SEED)
    boot = {k: {part: {t: [] for t, _, _ in TESTS} for part in ("all", "rebuilt")} for k in systems}
    for _ in range(resamples):
        pick = rng.integers(0, len(clusters), len(clusters))
        gi = np.concatenate([games_of[c] for c in pick])
        for k in systems:
            for part, g_, t_ in (("all", gi, pick), ("rebuilt", gi[low_g[gi]], pick[low_t[pick]])):
                for t, v in scores(k, g_, t_).items():
                    boot[k][part][t].append(v)

    lo_q, hi_q = (1 - confidence) / 2, (1 + confidence) / 2
    out = {}
    for k in systems:
        out[k] = {"coverage": coverage[k], "by_season": by_season[k]}
        for part in ("all", "rebuilt"):
            out[k][part] = {t: {"value": float(point[k][part][t]),
                                "interval": [float(q) for q in np.quantile(boot[k][part][t], [lo_q, hi_q])]}
                            for t, _, _ in TESTS}
    for part in ("all", "rebuilt"):                                          # rank ranges from the same resamples
        for t, _, higher in TESTS:
            if higher is None:
                continue
            draws = np.array([boot[k][part][t] for k in systems])            # metrics x resamples
            ranks = (-draws if higher else draws).argsort(axis=0).argsort(axis=0) + 1
            for i, k in enumerate(systems):
                out[k][part][t]["rank"] = [int(np.quantile(ranks[i], lo_q, method="lower")),
                                           int(np.quantile(ranks[i], hi_q, method="higher"))]
    return out


# ---------------------------------------------------------------- report

def num(v, digits=3):
    s = f"{v:.{digits}f}"
    return s.replace("0.", ".", 1) if abs(v) < 1 else s


def fmt(test, v):
    """Errors and slopes in points (2 decimals); R2 and r as .xxx"""
    return f"{v:.2f}" if test in ("net_rmse", "slope") else num(v)


def report(meta, res, by_season, saved):
    c = int(round(meta["confidence"] * 100))
    rules = meta["rules"]
    if rules["min_minutes"] > 0:
        rule = (f"under {rules['min_minutes']:g} minutes last season (rookies included) = {rules['replacement']:.1f}; "
                f"not in a file = {rules['replacement']:.1f}")
    else:
        rule = f"every file as-is; not in a file = {rules['replacement']:.1f}"
    rule += "   [v1 standard]" if rules == STANDARD else "   [custom rules]"
    L = [f"HoopBench v{meta['version']}  (working name)",
         "Do last season's impact-metric values predict this season?", "",
         f"  seasons    {meta['seasons'][0]} to {meta['seasons'][-1]}: {meta['games']:,} games, "
         f"{meta['team_seasons']} team-seasons",
         f"  rules      {rule}",
         f"  intervals  {c}%, {meta['resamples']:,} resamples of team-seasons, the same for every metric", ""]
    w = max(len(k) for k in res) + 2

    def ranked(part, t, title, note, higher):
        rows = sorted(res, key=lambda k: res[k][part][t]["value"], reverse=higher)
        out = [title, f"  {note}", f"  {'rank':<7}{'metric':<{w}}{'score':>7}   {c}% interval"]
        for k in rows:
            s = res[k][part][t]
            lo, hi = s["rank"]
            out.append(f"  {(str(lo) if lo == hi else f'{lo}-{hi}'):<7}{k:<{w}}{fmt(t, s['value']):>7}   "
                       f"{fmt(t, s['interval'][0])} to {fmt(t, s['interval'][1])}")
        return out + [""]

    L += ranked("all", "margin_r2", "GAME MARGINS", "share of each game's final margin the ratings explain, R2 "
                "(higher is better)", True)
    L += ranked("all", "winpct_r", "TEAM WIN %", "correlation with team win %, r (higher is better; Narsu 2024)", True)
    L += ranked("all", "net_rmse", "TEAM NET RATING", "ratings at face value vs opponent-adjusted margin, error in "
                "points (lower is better; Snarr 2020)", False)

    order = sorted(res, key=lambda k: res[k]["all"]["margin_r2"]["value"], reverse=True)
    L += ["CALIBRATION", "  actual points per rating point in the game-margin line (1.00 = the ratings work at face value)",
          f"  {'':<7}{'metric':<{w}}{'slope':>7}   {c}% interval"]
    for k in order:
        s = res[k]["all"]["slope"]
        L.append(f"  {'':<7}{k:<{w}}{s['value']:>7.2f}   {s['interval'][0]:.2f} to {s['interval'][1]:.2f}")
    L += ["", "REBUILT ROSTERS",
          "  the same tests on the third of games and teams that kept the least of last season's minutes",
          f"  {'':<7}{'metric':<{w}}{'game R2':<20}{'win % r':<20}{'net RMSE':<20}"]
    cell = lambda t, s: f"{fmt(t, s['value'])} ({fmt(t, s['interval'][0])}-{fmt(t, s['interval'][1])})"
    for k in sorted(res, key=lambda k: res[k]["rebuilt"]["margin_r2"]["value"], reverse=True):
        s = res[k]["rebuilt"]
        L.append(f"  {'':<7}{k:<{w}}" + "".join(f"{cell(t, s[t]):<20}" for t in ("margin_r2", "winpct_r", "net_rmse")))
    L += ["", "COVERAGE",
          "  share of the minutes left to each file (players over the minutes cutoff) that the file rates",
          "  " + "   ".join(f"{k} {res[k]['coverage']:.0%}" for k in order), ""]
    if by_season:
        for t, label, _ in TESTS:
            L += [f"BY SEASON: {label}", f"  {'':<7}{'metric':<{w}}" + "".join(f"{s:>9}" for s in meta["seasons"])]
            for k in order:
                L.append(f"  {'':<7}{k:<{w}}" + "".join(f"{fmt(t, v[t]):>9}" for v in res[k]["by_season"].values()))
            L += [""]
    L.append(f"Saved {saved} (every score, interval and rank range, plus a sha256 fingerprint of each input file)")
    return "\n".join(L)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ratings", nargs="+", default=[], help="CSV files or folders of CSVs (season,nba_id,rating)")
    ap.add_argument("--no-bundled", action="store_true", help="leave out the metrics in ratings/")
    ap.add_argument("--by-season", action="store_true", help="also print every score season by season")
    ap.add_argument("--confidence", type=float, default=0.90, help="interval level, e.g. 0.90 or 0.95")
    ap.add_argument("--min-minutes", type=float, default=STANDARD["min_minutes"],
                    help="players under this many minutes last season get --replacement (0 = use every file as-is)")
    ap.add_argument("--replacement", type=float, default=STANDARD["replacement"])
    ap.add_argument("--resamples", type=int, default=2000)
    ap.add_argument("--out", default=str(HERE / "results"))
    a = ap.parse_args()
    if not 0 < a.confidence < 1:
        raise SystemExit("--confidence must be between 0 and 1, e.g. 0.90")

    files = csv_files(([] if a.no_bundled else [HERE / "ratings"]) + a.ratings)
    if not files:
        raise SystemExit("no ratings to score: add --ratings or drop --no-bundled")
    systems = {f.stem: read_ratings(f) for f in files}
    games = pd.read_csv(HERE / "data" / "games.csv", dtype={"game_id": str})
    minutes = pd.read_csv(HERE / "data" / "minutes.csv", dtype={"game_id": str})
    seasons, G, M, S, T = prepare(systems, games, minutes)
    res = evaluate(systems, seasons, G, M, S, T, a.min_minutes, a.replacement, a.confidence, a.resamples)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    meta = {"benchmark": "HoopBench (working name)", "version": VERSION, "seasons": seasons, "games": len(G),
            "team_seasons": len(T), "rules": {"min_minutes": a.min_minutes, "replacement": a.replacement},
            "confidence": a.confidence, "resamples": a.resamples, "seed": SEED,
            "inputs": {f.name: sha256(f) for f in [HERE / "data" / "games.csv", HERE / "data" / "minutes.csv"] + files}}
    saved = out / "results.json"
    saved.write_text(json.dumps({"meta": meta, "metrics": res}, indent=1), encoding="utf-8")
    print(report(meta, res, a.by_season, saved))


if __name__ == "__main__":
    main()
