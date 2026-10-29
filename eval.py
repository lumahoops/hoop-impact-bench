"""
Hoop Impact Bench (HIB) v1: do last season's impact-metric values predict this season?

Bring one CSV per metric with columns season,nba_id,rating. `rating` is the value that was known before that
season's opening night (last season's value, or a preseason projection), in points per 100 possessions above
league average; nba_id is the NBA.com person id. The file name is the metric's name.

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

The v1 window is the regular seasons 2020-21 to 2025-26. Every metric in a run is scored on the seasons all of them
cover, so a file that covers fewer seasons shrinks the window for the whole run; such runs, and runs with other rules,
are marked custom: compare them only with runs under the same rules and seasons.

Usage
  python eval.py                         the bundled metrics (ratings/)
  python eval.py --ratings mine.csv      add yours: CSV files or folders of CSVs
  python eval.py --baselines             add reference rows: every player 0, last season's team, same-season RAPM
  python eval.py --by-season             also print every score season by season
  python eval.py --pairs                 also print each metric minus the leader, with paired intervals
  python eval.py --confidence 0.95       interval level (default 0.90)
  python eval.py --min-minutes 0         no low-minute rule: every file as-is; only missing players get --replacement
  python eval.py --replacement -1.0      the value those players get (default -2.0)
  python eval.py --resamples 5000        bootstrap resamples (default 2000, at least 100)
  python eval.py --out my_run            save the run somewhere else (default runs/<date_time>)

Each run folder holds results.json (every score, interval and rank range, the paired difference between every two
metrics, and a sha256 fingerprint of each input file), games.csv (every game's actual margin and each metric's
predicted margin) and teams.csv (every team-season's results and each metric's team rating).
"""
import argparse
import datetime
import hashlib
import itertools
import json
import platform
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
VERSION = "1.0.0"
STANDARD = {"min_minutes": 250, "replacement": -2.0}
STANDARD_SEASONS = ["2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
SEED = 7
TESTS = [("margin_r2", "game margin R2", True),  # (key, label, higher is better)
         ("winpct_r", "team win % r", True),
         ("net_rmse", "team net RMSE", False)]
HIGHER = {test: higher for test, _, higher in TESTS}
BASELINES = {
    "baseline_zero": "every player 0 (under the default rule, only the -2.0 for low-minute players separates teams; "
                     "with --min-minutes 0 every team is 0: R2 and r are 0, and its net error is the error of calling "
                     "every team average)",
    "baseline_last_team": "each player = his main team's opponent-adjusted margin last season / 5",
    "ceiling_rapm_same_season": "RAPM fit on the season being scored: it has seen those games",
}
WARN_COVERAGE = 0.9  # a file should rate at least 90% of the minutes of players with 250+ minutes last season
WARN_AVERAGE = 1.5   # and put their minutes-weighted average within 1.5 points of 0 (league average)


# ---------------------------------------------------------------- small helpers

def season_after(season, k=1):
    """'2024-25' -> '2025-26' (k=1); k=-1 goes back a season."""
    year = int(season[:4]) + k
    return f"{year}-{str(year + 1)[2:]}"


def prev(season):
    return season_after(season, -1)


def season_span(seasons):
    """['2020-21', '2021-22', '2023-24'] -> '2020-21 to 2021-22, 2023-24'"""
    runs = []
    for s in sorted(seasons):
        if runs and s == season_after(runs[-1][1]):
            runs[-1][1] = s
        else:
            runs.append([s, s])
    return ", ".join(a if a == b else f"{a} to {b}" for a, b in runs)


def sha256(path):
    """Fingerprint of a text file. Windows line endings (CRLF) count as LF, so a Windows copy and a Mac/Linux copy
    of the same file get the same fingerprint (equal to sha256sum of the LF copy)."""
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def git_commit():
    """The repo commit this copy was run from, if it is a git checkout."""
    try:
        run = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True, text=True, timeout=10)
        return run.stdout.strip() or None
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
    """The CSV files among paths (files or folders); every metric needs its own name."""
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


# ---------------------------------------------------------------- the season data every metric is scored on

def opponent_adjusted(games):
    """Each team-season's average margin adjusted for opponents and home court (least squares, as in SRS)."""
    out = {}
    for season, g in games.groupby("season"):
        teams = sorted(set(g.home) | set(g.away))
        column = {t: i for i, t in enumerate(teams)}
        design = np.zeros((len(g), len(teams) + 1))
        rows = np.arange(len(g))
        design[rows, [column[t] for t in g.home]] = 1.0
        design[rows, [column[t] for t in g.away]] = -1.0
        design[:, -1] = 1.0 - g.neutral.values                              # home edge
        strength = np.linalg.lstsq(design, g.margin.values, rcond=None)[0][:-1]
        out.update({(season, t): strength[column[t]] - strength.mean() for t in teams})
    return pd.Series(out)


def baselines(games, minutes):
    """Reference rows built from the game data (plus the same-season RAPM file in reference/)."""
    adjusted = opponent_adjusted(games)
    season_minutes = minutes.groupby(["season", "team", "nba_id"], as_index=False)["min"].sum()
    main_team = season_minutes.sort_values("min").drop_duplicates(["season", "nba_id"], keep="last")
    last_team = pd.DataFrame({
        "season": main_team.season.map(season_after),
        "nba_id": main_team.nba_id,
        "rating": [adjusted[(s, t)] / 5 for s, t in zip(main_team.season, main_team.team)]})
    zero = season_minutes[["season", "nba_id"]].drop_duplicates().assign(rating=0.0)
    return {"baseline_zero": zero, "baseline_last_team": last_team,
            "ceiling_rapm_same_season": read_ratings(HERE / "reference" / "rapm_same_season.csv")}


def common_seasons(systems, games):
    """The seasons every metric covers that have games, and games the season before (for last-season minutes)."""
    have = set(games.season)
    covered = set.intersection(*(set(d.season) for d in systems.values()))
    seasons = sorted(s for s in covered if s in have and prev(s) in have)
    if not seasons:
        cover = ", ".join(f"{k} {d.season.min()} to {d.season.max()}" for k, d in systems.items())
        raise SystemExit(f"no season is covered by every metric and the game data ({cover}; games "
                         f"{min(have)} to {max(have)}, the first season only supplies last-season minutes)")
    return seasons


def roster_continuity(season_minutes, seasons):
    """(season, team) -> share of the team's minutes played by players who were on the same team the season before."""
    out = {}
    for season in seasons:
        before = season_minutes[season_minutes.season == prev(season)]
        kept = set(zip(before.team, before.nba_id))
        for team, rows in season_minutes[season_minutes.season == season].groupby("team"):
            stayed = [(team, p) in kept for p in rows.nba_id]
            out[(season, team)] = rows["min"][stayed].sum() / rows["min"].sum()
    return out


def team_results(games):
    """Win % and opponent-adjusted margin of every team-season in games."""
    def side(team, margin):
        return pd.DataFrame({"season": games.season, "team": team, "margin": margin})
    margins = pd.concat([side(games.home, games.margin), side(games.away, -games.margin)])
    win_pct = margins.groupby(["season", "team"]).margin.apply(lambda m: (m > 0).mean())
    out = pd.DataFrame({"win_pct": win_pct, "adjusted_margin": opponent_adjusted(games)})
    out.index.names = ["season", "team"]
    return out


def prepare(systems, games, minutes):
    """The seasons every metric covers, and four tables for them:

    games           one row per game: margin, rebuilt (a low-continuity game), cluster (its home team-season)
    player_games    one row per player per game: weight = +5 (home) or -5 (away) x his share of his team's minutes
    player_seasons  one row per player per team-season: minutes, team_row (his row in team_seasons)
    team_seasons    one row per team-season: win_pct, adjusted_margin, continuity, rebuilt

    Both player tables also carry last_min, the player's minutes the season before (for the 250-minute rule).
    """
    seasons = common_seasons(systems, games)
    season_minutes = minutes.groupby(["season", "team", "nba_id"], as_index=False)["min"].sum()
    minutes_by_season = season_minutes.groupby(["season", "nba_id"])["min"].sum()

    def minutes_last_season(rows):
        key = pd.MultiIndex.from_arrays([rows.season.map(prev), rows.nba_id])
        return minutes_by_season.reindex(key).fillna(0.0).values

    continuity = roster_continuity(season_minutes, seasons)

    games = games[games.season.isin(seasons)].sort_values(["date", "game_id"]).reset_index(drop=True)
    kept = np.minimum([continuity[(s, t)] for s, t in zip(games.season, games.home)],
                      [continuity[(s, t)] for s, t in zip(games.season, games.away)])
    games["rebuilt"] = kept <= np.quantile(kept, 1 / 3)
    games["cluster"] = list(zip(games.season, games.home))

    player_games = minutes[minutes.game_id.isin(games.game_id)].reset_index(drop=True)
    player_games["game"] = player_games.game_id.map(pd.Series(games.index, index=games.game_id)).values
    team_minutes = player_games.groupby(["game_id", "team"])["min"].transform("sum")
    side = np.where(player_games.team.values == games.home.values[player_games.game], 1.0, -1.0)
    player_games["weight"] = side * 5 * player_games["min"] / team_minutes
    player_games["last_min"] = minutes_last_season(player_games)

    team_seasons = team_results(games)
    team_seasons["continuity"] = [continuity[i] for i in team_seasons.index]
    team_seasons["rebuilt"] = team_seasons.continuity <= np.quantile(team_seasons.continuity, 1 / 3)

    player_seasons = season_minutes[season_minutes.season.isin(seasons)].reset_index(drop=True)
    player_seasons["last_min"] = minutes_last_season(player_seasons)
    team_key = pd.MultiIndex.from_arrays([player_seasons.season, player_seasons.team])
    player_seasons["team_row"] = team_seasons.index.get_indexer(team_key)
    return seasons, games, player_games, player_seasons, team_seasons


# ---------------------------------------------------------------- scoring

def lookup(rows, ratings):
    """Each row's rating in the file (nan when the file does not rate that player in that season)."""
    key = pd.MultiIndex.from_arrays([rows.season, rows.nba_id])
    return ratings.set_index(["season", "nba_id"]).rating.reindex(key).values


def apply_rules(raw, last_min, min_minutes, replacement):
    """The rules: a player under min_minutes last season, or not rated, gets the replacement value.
    Also returns which rows the rules leave to the file (eligible) and which the file rates."""
    eligible = last_min >= min_minutes
    rated = ~np.isnan(raw)
    return np.where(eligible & rated, raw, replacement), eligible, rated


def rate_teams(systems, seasons, player_games, player_seasons, n_games, n_teams, min_minutes, replacement):
    """Every metric's home-minus-away rating in each game and rating for each team-season, plus file checks."""
    names = list(systems)
    game_ratings = np.zeros((len(names), n_games))
    team_ratings = np.zeros((len(names), n_teams))
    checks = {}
    minutes = player_games["min"].values
    established = player_games.last_min.values >= STANDARD["min_minutes"]  # 250+ minutes last season
    team_minutes = np.bincount(player_seasons.team_row, weights=player_seasons["min"], minlength=n_teams)
    for i, name in enumerate(names):
        ratings = systems[name][systems[name].season.isin(seasons)]
        raw = lookup(player_games, ratings)
        value, eligible, rated = apply_rules(raw, player_games.last_min.values, min_minutes, replacement)
        game_ratings[i] = np.bincount(player_games.game, weights=player_games.weight * value, minlength=n_games)
        known = established & rated
        checks[name] = {
            "coverage": float(minutes[eligible & rated].sum() / minutes[eligible].sum()),
            "coverage_established": float(minutes[known].sum() / minutes[established].sum()),
            "average_established": float(np.average(raw[known], weights=minutes[known])) if known.any() else None}
        raw = lookup(player_seasons, ratings)
        value, _, _ = apply_rules(raw, player_seasons.last_min.values, min_minutes, replacement)
        team_ratings[i] = 5 * np.bincount(player_seasons.team_row, weights=value * player_seasons["min"],
                                          minlength=n_teams) / team_minutes
    return game_ratings, team_ratings, checks


def correlations(a, b):
    """Correlation of every row of a with b; a constant row (every team equal) explains nothing: 0."""
    a, b = a - a.mean(axis=1, keepdims=True), b - b.mean()
    with np.errstate(invalid="ignore", divide="ignore"):
        r = (a @ b) / np.sqrt((a * a).sum(axis=1) * (b @ b))
    return np.nan_to_num(r)


def score(game_ratings, team_ratings, targets, game_rows, team_rows):
    """The three tests (rows) for every metric (columns), on the given games and team-seasons."""
    margin, win_pct, adjusted_margin = targets
    return np.vstack([correlations(game_ratings[:, game_rows], margin[game_rows]) ** 2,
                      correlations(team_ratings[:, team_rows], win_pct[team_rows]),
                      np.sqrt(((team_ratings[:, team_rows] - adjusted_margin[team_rows]) ** 2).mean(axis=1))])


def bootstrap(score_rows, games, team_seasons, resamples):
    """Scores on resamples of team-seasons (a game goes with its home team-season); every metric is scored on the
    same resamples. Returns {"all": ..., "rebuilt": ...}, each an array resamples x tests x metrics."""
    games_of = {c: [] for c in team_seasons.index}
    for i, cluster in enumerate(games.cluster):
        games_of[cluster].append(i)
    games_of = [np.array(games_of[c], dtype=int) for c in team_seasons.index]
    rebuilt_game, rebuilt_team = games.rebuilt.values, team_seasons.rebuilt.values
    rng = np.random.default_rng(SEED)
    draws = {"all": [], "rebuilt": []}
    for _ in range(resamples):
        teams = rng.integers(0, len(team_seasons), len(team_seasons))
        game_rows = np.concatenate([games_of[t] for t in teams])
        draws["all"].append(score_rows(game_rows, teams))
        draws["rebuilt"].append(score_rows(game_rows[rebuilt_game[game_rows]], teams[rebuilt_team[teams]]))
    return {part: np.array(d) for part, d in draws.items()}


def summarize(names, seasons, point, by_season, draws, checks, confidence):
    """results.json's metrics: each score with its interval and, for ranked metrics, its rank range."""
    q = [(1 - confidence) / 2, (1 + confidence) / 2]
    ranked = [i for i, name in enumerate(names) if name not in BASELINES]   # reference rows get no rank
    out = {name: {"baseline": name in BASELINES, **checks[name],
                  "by_season": {s: {test: float(by_season[s][j, i]) for j, (test, _, _) in enumerate(TESTS)}
                                for s in seasons}}
           for i, name in enumerate(names)}
    for part, d in draws.items():
        for j, (test, _, higher) in enumerate(TESTS):
            ranks = (-d[:, j, ranked] if higher else d[:, j, ranked]).argsort(axis=1).argsort(axis=1) + 1
            for i, name in enumerate(names):
                s = {"value": float(point[part][j, i]), "interval": [float(v) for v in np.quantile(d[:, j, i], q)]}
                if i in ranked:
                    r = ranks[:, ranked.index(i)]
                    s["rank"] = [int(np.quantile(r, q[0], method="lower")), int(np.quantile(r, q[1], method="higher"))]
                out[name].setdefault(part, {})[test] = s
    return out


def paired_differences(names, point, draws, confidence):
    """Every two metrics: A minus B on all the data, with an interval from the same resamples (paired)."""
    q = [(1 - confidence) / 2, (1 + confidence) / 2]
    out = []
    for part, d in draws.items():
        for j, (test, _, _) in enumerate(TESTS):
            for i, k in itertools.combinations(range(len(names)), 2):
                out.append({"part": part, "test": test, "a": names[i], "b": names[k],
                            "diff": float(point[part][j, i] - point[part][j, k]),
                            "interval": [float(v) for v in np.quantile(d[:, j, i] - d[:, j, k], q)]})
    return out


def evaluate(systems, seasons, games, player_games, player_seasons, team_seasons, min_minutes, replacement,
             confidence, resamples):
    """Scores, intervals, ranks and paired differences for every metric; also the game and team ratings."""
    names = list(systems)
    game_ratings, team_ratings, checks = rate_teams(systems, seasons, player_games, player_seasons, len(games),
                                                    len(team_seasons), min_minutes, replacement)
    targets = (games.margin.values, team_seasons.win_pct.values, team_seasons.adjusted_margin.values)

    def score_rows(game_rows, team_rows):
        return score(game_ratings, team_ratings, targets, game_rows, team_rows)

    every_game, every_team = np.arange(len(games)), np.arange(len(team_seasons))
    point = {"all": score_rows(every_game, every_team),
             "rebuilt": score_rows(every_game[games.rebuilt.values], every_team[team_seasons.rebuilt.values])}
    season_of = team_seasons.index.get_level_values(0)
    by_season = {s: score_rows(np.flatnonzero(games.season == s), np.flatnonzero(season_of == s)) for s in seasons}
    draws = bootstrap(score_rows, games, team_seasons, resamples)
    results = summarize(names, seasons, point, by_season, draws, checks, confidence)
    return results, paired_differences(names, point, draws, confidence), game_ratings, team_ratings


def write_logs(folder, games, team_seasons, game_ratings, team_ratings, names):
    """games.csv and teams.csv: the per-game and per-team-season numbers behind every score."""
    g = games[["season", "game_id", "date", "home", "away", "home_pts", "away_pts", "margin", "rebuilt"]].copy()
    g["rebuilt"] = g.rebuilt.astype(int)
    for i, name in enumerate(names):
        x = game_ratings[i]
        if np.ptp(x) == 0:                     # a constant rating predicts the average margin
            g[name] = round(float(games.margin.mean()), 2)
        else:                                  # the predicted margin from the run's straight line
            slope, edge = np.polyfit(x, games.margin.values, 1)
            g[name] = (edge + slope * x).round(2)
    g.to_csv(folder / "games.csv", index=False)
    t = team_seasons.reset_index()
    t = t.assign(win_pct=t.win_pct.round(3), adjusted_margin=t.adjusted_margin.round(2),
                 continuity=t.continuity.round(3), rebuilt=t.rebuilt.astype(int))
    for i, name in enumerate(names):
        t[name] = team_ratings[i].round(3)
    t.to_csv(folder / "teams.csv", index=False)


# ---------------------------------------------------------------- report

def num(v, digits=3):
    """.123 under 1 (like a batting average), 1.234 otherwise"""
    s = f"{v:.{digits}f}"
    return s.replace("0.", ".", 1) if abs(v) < 1 else s


def fmt(test, v):
    """Errors in points (2 decimals); R2 and r as .xxx"""
    return f"{v:.2f}" if test == "net_rmse" else num(v)


def signed(test, v):
    return ("-" if v < 0 else "+") + fmt(test, abs(v))


def percent(meta):
    return int(round(meta["confidence"] * 100))


def by_r2(results):
    return sorted(results, key=lambda k: results[k]["all"]["margin_r2"]["value"], reverse=True)


def file_warnings(results):
    """Files whose ids or units look wrong."""
    out = []
    for name, r in results.items():
        if r["baseline"]:
            continue
        if r["coverage_established"] < WARN_COVERAGE:
            out.append(f"  WARNING    {name} rates only {r['coverage_established']:.0%} of the minutes of players "
                       "with 250+ minutes last season: check that nba_id is the NBA.com person id")
        average = r["average_established"]
        if average is not None and abs(average) > WARN_AVERAGE:
            out.append(f"  WARNING    {name} puts the average player with 250+ minutes last season at "
                       f"{average:+.1f}, not near 0: ratings must be points per 100 above league average "
                       "(convert PER and similar stats first)")
    return out


def header(meta, results):
    std, rules = meta["standard"], meta["rules"]
    replacement = f"{rules['replacement']:.1f}"
    if rules["min_minutes"] > 0:
        rule = (f"under {rules['min_minutes']:g} minutes last season (rookies included) = {replacement}; "
                f"not in a file = {replacement}")
    else:
        rule = f"no low-minute rule (every file as-is); not in a file = {replacement}"
    lines = [f"Hoop Impact Bench (HIB) v{meta['version']}",
             "Do last season's impact-metric values predict this season?", "",
             f"  seasons    {season_span(meta['seasons'])}: {meta['games']:,} games, {meta['team_seasons']} "
             "team-seasons" + ("   [v1 window]" if std["window"] else "   [custom window]")]
    lines += [f"             shortened by {k} (covers {v})" for k, v in meta["window_limited_by"].items()]
    lines += [f"  rules      {rule}" + ("   [v1 rules]" if std["rules"] else "   [custom rules]"),
              f"  intervals  {percent(meta)}%, {meta['resamples']:,} resamples of team-seasons, the same for every "
              "metric"]
    if not (std["rules"] and std["window"]):
        lines.append("  custom run: compare it only with runs under the same rules and seasons, not with the v1 "
                     "results")
    lines += file_warnings(results)
    references = [k for k in results if results[k]["baseline"]]
    if references:
        lines += ["  baselines  not ranked:"] + [f"             {k}: {BASELINES[k]}" for k in references]
    return lines + [""]


def ranked_table(meta, results, test, title, note, width):
    lines = [title, f"  {note}", f"  {'rank':<7}{'metric':<{width}}{'score':>7}   {percent(meta)}% interval"]
    for name in sorted(results, key=lambda k: results[k]["all"][test]["value"], reverse=HIGHER[test]):
        s = results[name]["all"][test]
        lo, hi = s.get("rank", (None, None))
        rank = "-" if lo is None else str(lo) if lo == hi else f"{lo}-{hi}"
        low, high = fmt(test, s["interval"][0]), fmt(test, s["interval"][1])
        lines.append(f"  {rank:<7}{name:<{width}}{fmt(test, s['value']):>7}   {low} to {high}")
    return lines + [""]


def rebuilt_table(results, width):
    def cell(test, s):
        return f"{fmt(test, s['value'])} ({fmt(test, s['interval'][0])}-{fmt(test, s['interval'][1])})"
    lines = ["REBUILT ROSTERS",
             "  the same tests on the third of games and teams that kept the least of last season's minutes",
             f"  {'':<7}{'metric':<{width}}{'game R2':<20}{'win % r':<20}{'net RMSE':<20}"]
    for name in sorted(results, key=lambda k: results[k]["rebuilt"]["margin_r2"]["value"], reverse=True):
        cells = "".join(f"{cell(test, results[name]['rebuilt'][test]):<20}" for test, _, _ in TESTS)
        lines.append(f"  {'':<7}{name:<{width}}" + cells)
    return lines


def coverage_lines(results):
    metrics = [k for k in by_r2(results) if not results[k]["baseline"]]
    lines = ["", "COVERAGE",
             "  share of the minutes left to each file (players over the minutes cutoff) that the file rates"]
    for i in range(0, len(metrics), 5):
        lines.append("  " + "   ".join(f"{k} {results[k]['coverage']:.0%}" for k in metrics[i:i + 5]))
    return lines + [""]


def paired_lines(meta, results, pairs, width):
    """Each metric minus the leader on every test, the noise level, and which metrics beat the floors."""
    diff = {}                                  # (test, a, b) -> (a minus b, interval low, interval high)
    for x in pairs:
        if x["part"] == "all":
            lo, hi = x["interval"]
            diff[(x["test"], x["a"], x["b"])] = (x["diff"], lo, hi)
            diff[(x["test"], x["b"], x["a"])] = (-x["diff"], -hi, -lo)
    ranked = [k for k in results if not results[k]["baseline"]]
    if not ranked:
        return []
    floors = [k for k in ("baseline_zero", "baseline_last_team") if k in results]
    lines = ["PAIRED DIFFERENCES", f"  each metric minus the leader, scored on the same resamples "
             f"({percent(meta)}% interval); an interval that holds 0 is a tie"]
    for test, label, higher in TESTS:
        order = sorted(ranked, key=lambda k: results[k]["all"][test]["value"], reverse=higher)
        leader = order[0]
        lines.append(f"  {label}: leader {leader}")
        for name in order[1:]:
            d, lo, hi = diff[(test, name, leader)]
            tie = "   tie" if lo <= 0 <= hi else ""
            lines.append(f"    {name:<{width}}{signed(test, d):>7}   {signed(test, lo)} to {signed(test, hi)}{tie}")
        if len(ranked) > 1:
            half_widths = [(diff[(test, a, b)][2] - diff[(test, a, b)][1]) / 2
                           for a, b in itertools.combinations(ranked, 2)]
            lines.append(f"    differences smaller than about {fmt(test, np.median(half_widths))} are within the "
                         "noise (median half-width of the paired intervals)")
        for floor in floors:
            better = [k for k in ranked if (diff[(test, k, floor)][1] > 0 if higher else diff[(test, k, floor)][2] < 0)]
            rest = [k for k in ranked if k not in better]
            lines.append(f"    better than {floor}: {len(better)} of {len(ranked)}"
                         + (f" (not: {', '.join(rest)})" if rest else ""))
    return lines + [""]


def by_season_lines(meta, results, width):
    lines = []
    for test, label, _ in TESTS:
        lines += [f"BY SEASON: {label}",
                  f"  {'':<7}{'metric':<{width}}" + "".join(f"{s:>9}" for s in meta["seasons"])]
        for name in by_r2(results):
            values = results[name]["by_season"].values()
            lines.append(f"  {'':<7}{name:<{width}}" + "".join(f"{fmt(test, v[test]):>9}" for v in values))
        lines.append("")
    return lines


def report(meta, results, pairs, by_season, show_pairs, saved):
    """The printed report."""
    width = max(len(k) for k in results) + 2
    lines = header(meta, results)
    lines += ranked_table(meta, results, "margin_r2", "GAME MARGINS",
                          "share of each game's final margin the ratings explain, R2 (higher is better)", width)
    lines += ranked_table(meta, results, "winpct_r", "TEAM WIN %",
                          "correlation with team win %, r (higher is better; Narsu 2024)", width)
    lines += ranked_table(meta, results, "net_rmse", "TEAM NET RATING",
                          "ratings at face value vs opponent-adjusted margin, error in points "
                          "(lower is better; Snarr 2020)", width)
    lines += rebuilt_table(results, width) + coverage_lines(results)
    if show_pairs:
        lines += paired_lines(meta, results, pairs, width)
    if by_season:
        lines += by_season_lines(meta, results, width)
    lines += [f"Saved {saved}", "  results.json (scores, intervals, rank ranges, input fingerprints), "
              "games.csv (per game), teams.csv (per team)"]
    return "\n".join(lines)


# ---------------------------------------------------------------- main

def parse_args():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ratings", nargs="+", default=[], help="CSV files or folders of CSVs (season,nba_id,rating)")
    ap.add_argument("--no-bundled", action="store_true", help="leave out the metrics in ratings/")
    ap.add_argument("--baselines", action="store_true", help="add the reference rows (not ranked)")
    ap.add_argument("--by-season", action="store_true", help="also print every score season by season")
    ap.add_argument("--pairs", action="store_true",
                    help="also print each metric minus the leader with paired intervals, and who clears the floors")
    ap.add_argument("--confidence", type=float, default=0.90, help="interval level, e.g. 0.90 or 0.95")
    ap.add_argument("--min-minutes", type=float, default=STANDARD["min_minutes"],
                    help="players under this many minutes last season get --replacement (0 = use every file as-is)")
    ap.add_argument("--replacement", type=float, default=STANDARD["replacement"],
                    help="the value those players, and players missing from a file, get (default -2.0)")
    ap.add_argument("--resamples", type=int, default=2000, help="bootstrap resamples (default 2000, at least 100)")
    ap.add_argument("--out", help="folder for the run (default: runs/<date_time>)")
    args = ap.parse_args()
    if not 0 < args.confidence < 1:
        raise SystemExit("--confidence must be between 0 and 1, e.g. 0.90")
    if args.resamples < 100:
        raise SystemExit("--resamples must be at least 100 (default 2000)")
    return args


def new_run_folder():
    """runs/<date_time>; runs started in the same second get _2, _3, ..."""
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    for n in itertools.count(1):
        folder = HERE / "runs" / (stamp if n == 1 else f"{stamp}_{n}")
        try:
            folder.mkdir(parents=True)
            return folder
        except FileExistsError:
            continue


def main():
    args = parse_args()
    files = csv_files(([] if args.no_bundled else [HERE / "ratings"]) + args.ratings)
    games = pd.read_csv(HERE / "data" / "games.csv", dtype={"game_id": str})
    games["margin"] = (games.home_pts - games.away_pts).astype(float)
    minutes = pd.read_csv(HERE / "data" / "minutes.csv", dtype={"game_id": str})
    systems = {f.stem: read_ratings(f) for f in files}
    if args.baselines:
        systems.update(baselines(games, minutes))
        files.append(HERE / "reference" / "rapm_same_season.csv")
    if not systems:
        raise SystemExit("nothing to score: add --ratings or --baselines, or drop --no-bundled")

    seasons, games, player_games, player_seasons, team_seasons = prepare(systems, games, minutes)
    results, pairs, game_ratings, team_ratings = evaluate(
        systems, seasons, games, player_games, player_seasons, team_seasons,
        args.min_minutes, args.replacement, args.confidence, args.resamples)

    folder = Path(args.out) if args.out else new_run_folder()
    folder.mkdir(parents=True, exist_ok=True)
    rules = {"min_minutes": args.min_minutes, "replacement": args.replacement}
    meta = {
        "benchmark": "Hoop Impact Bench (HIB)", "version": VERSION, "seasons": seasons, "games": len(games),
        "team_seasons": len(team_seasons), "rules": rules,
        "standard": {"rules": rules == STANDARD, "window": seasons == STANDARD_SEASONS},
        "window_limited_by": {k: season_span(set(d.season) & set(STANDARD_SEASONS)) for k, d in systems.items()
                              if not set(STANDARD_SEASONS) <= set(d.season)},
        "confidence": args.confidence, "resamples": args.resamples, "seed": SEED,
        "harness": sha256(Path(__file__)), "git_commit": git_commit(),
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__},
        "inputs": {f.name: sha256(f) for f in [HERE / "data" / "games.csv", HERE / "data" / "minutes.csv"] + files}}
    output = {"meta": meta, "metrics": results, "pairs": pairs}
    (folder / "results.json").write_text(json.dumps(output, indent=1), encoding="utf-8")
    write_logs(folder, games, team_seasons, game_ratings, team_ratings, list(systems))
    print(report(meta, results, pairs, args.by_season, args.pairs, folder))


if __name__ == "__main__":
    main()
