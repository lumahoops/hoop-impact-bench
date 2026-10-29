"""
Do preseason NBA player ratings predict the season that follows?

Give it one CSV per rating system (columns season,nba_id,rating: the values shown BEFORE that season's opening
night). Every system is scored on the same games with the same rules:

  margin  Game margin. A team's game rating is 5 x the minutes-weighted mean of its players' ratings, using the
          minutes they played in that game. Home minus away predicts the final margin through a straight line
          fitted leave-one-season-out. Score: R^2.
  winpct  Team-season win %. A team's rating is 5 x the season-minutes-weighted mean of its players' ratings.
          Score: correlation r (Krishna Narsu's 2024 test) and R^2.
  mov     Team-season average margin, the same team rating taken at face value. Score: RMSE in points
          (Taylor Snarr's 2020 retrodiction test).

Each test is also scored on the third of games/teams that kept the least of last season's minutes, and the
margin-R^2 gap between the first system and each other one gets a 90% bootstrap interval.

Usage:
  python eval.py                          the systems in ratings/
  python eval.py --extra my_ratings/      add your own systems (one CSV each, named after the system)
  python eval.py --minutes my_mins.csv    team tests on your minutes (season,team,nba_id,min) instead of actual
  python eval.py --fill replacement       unrated players = -2.0 instead of the fitted newcomer fill
  python eval.py --first epm              measure the bootstrap gaps from this system (default: first by name)
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
REPLACEMENT = -2.0
BOOTSTRAPS, SEED = 2000, 7


def prev(season):
    """'2024-25' -> '2023-24'"""
    y = int(season[:4]) - 1
    return f"{y}-{str(y + 1)[2:]}"


def r2(y, p):
    return 1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_checked(path, columns, numeric):
    """Read a user-supplied CSV and refuse anything that would score silently wrong."""
    path = Path(path)
    d = pd.read_csv(path)
    missing = [c for c in columns if c not in d.columns]
    if missing:
        raise SystemExit(f"{path.name}: missing column(s) {missing}; expected {columns}")
    d = d[columns].copy()
    if not d.season.astype(str).str.fullmatch(r"\d{4}-\d{2}").all():
        raise SystemExit(f"{path.name}: season must look like 2024-25")
    for c in numeric:
        d[c] = pd.to_numeric(d[c], errors="coerce")
        if d[c].isna().any():
            raise SystemExit(f"{path.name}: {d[c].isna().sum()} row(s) with a missing or non-numeric {c}")
    d["nba_id"] = d.nba_id.astype(int)
    key = [c for c in columns if c not in numeric or c == "nba_id"]
    if d.duplicated(key).any():
        raise SystemExit(f"{path.name}: duplicate rows for {key}, e.g. {d[d.duplicated(key)].iloc[0].tolist()}")
    return d


# ---------------------------------------------------------------- unrated players

# A system that does not rate a player still has to put a number in his minutes. The fair default fits that number
# from game results, separately for each system, out of sample: newcomers (no NBA rating last season) get a value
# from draft pick and age, anyone else unrated gets one constant.
FILL_FEATURES = ["newcomer", "newcomer x log(pick)", "undrafted", "newcomer x (age - 21)", "other unrated"]


def fill_features(newcomers, season, pid):
    if (season, pid) not in newcomers:
        return [0.0, 0.0, 0.0, 0.0, 1.0]
    pick, age = newcomers[(season, pid)]
    undrafted = pd.isna(pick)
    log_pick = np.log(61.0 if undrafted else pick)        # undrafted ranks just after the last pick
    age = 22.0 if pd.isna(age) else age                    # ponytail: missing age -> typical rookie age
    return [1.0, log_pick, float(undrafted), age - 21.0, 0.0]


# ---------------------------------------------------------------- tests

def game_margin_test(G, M, ratings, fill, newcomers):
    """Predicted margin per game (leave-one-season-out) and, per season, the fitted fill weights in rating units."""
    rated = np.array([p in ratings[s] for s, p in zip(M.season, M.nba_id)])
    value = np.array([ratings[s].get(p, REPLACEMENT) for s, p in zip(M.season, M.nba_id)])
    weight = M.sign * 5 * M["min"] / M.team_min                   # +home / -away share of the team's 5 slots
    use_fill = fill == "fitted"

    def per_game(x):
        return np.bincount(M.game, weights=weight * x, minlength=len(G))

    columns = [np.ones(len(G)), per_game(np.where(rated | (not use_fill), value, 0.0))]
    if use_fill:
        X = np.array([[0.0] * 5 if r else fill_features(newcomers, s, p) for s, p, r in zip(M.season, M.nba_id, rated)])
        columns += [per_game(X[:, j]) for j in range(X.shape[1])]
    Z, y = np.column_stack(columns), G.margin.values

    pred, fill_weights = np.zeros(len(G)), {}
    for s in G.season.unique():
        test = (G.season == s).values
        coef = np.linalg.lstsq(Z[~test], y[~test], rcond=None)[0]   # [home edge, rating scale, fill...]
        pred[test] = Z[test] @ coef
        fill_weights[s] = coef[2:] / coef[1]                         # fill in rating units
    return pred, fill_weights, float((rated * M["min"]).sum() / M["min"].sum())


def team_tests(team_min, ratings, fill_weights, fill, newcomers, results):
    """Team rating from season minutes, scored against win % (Narsu) and average margin (Snarr)."""
    def player_value(s, p):
        if p in ratings[s]:
            return ratings[s][p]
        if fill == "fitted":
            return float(np.dot(fill_features(newcomers, s, p), fill_weights[s]))
        return REPLACEMENT

    tm = team_min.assign(value=[player_value(s, p) for s, p in zip(team_min.season, team_min.nba_id)])
    tm["weighted"] = tm.value * tm["min"]
    team = tm.groupby(["season", "team"])[["weighted", "min"]].sum()
    team = results.join(5 * team.weighted.div(team["min"]).rename("rating"), how="inner")

    def scores(d):
        line = np.polyval(np.polyfit(d.rating, d.winpct, 1), d.rating)
        return {"winpct_r": float(np.corrcoef(d.rating, d.winpct)[0, 1]), "winpct_r2": float(r2(d.winpct.values, line)),
                "mov_rmse": float(np.sqrt(((d.rating - d.mov) ** 2).mean()))}
    return scores(team), scores(team[team.low])


def bootstrap_gaps(G, preds, first):
    """Margin-R^2 gap, first system minus each other, with a 90% interval resampling home team-seasons."""
    rng = np.random.default_rng(SEED)
    rows = {c: np.flatnonzero(G.cluster.values == c) for c in sorted(G.cluster.unique())}
    clusters = list(rows)
    draws = [np.concatenate([rows[c] for c in rng.choice(clusters, len(clusters))]) for _ in range(BOOTSTRAPS)]
    y, gaps = G.margin.values, {}
    for k in preds:
        if k == first:
            continue
        for label, keep in (("all", np.ones(len(G), bool)), ("low", G.low.values)):
            gap = lambda i: r2(y[i], preds[first][i]) - r2(y[i], preds[k][i])
            boot = [gap(i[keep[i]]) for i in draws]
            gaps.setdefault(k, {})[label] = [float(gap(np.flatnonzero(keep))), *np.quantile(boot, [0.05, 0.95]).tolist()]
    return gaps


# ---------------------------------------------------------------- data

def load_inputs(extra):
    files = sorted((HERE / "ratings").glob("*.csv")) + (sorted(Path(extra).glob("*.csv")) if extra else [])
    systems = {f.stem: read_checked(f, ["season", "nba_id", "rating"], ["nba_id", "rating"]) for f in files}
    if len(systems) < len(files):
        raise SystemExit("two ratings files share a name; system names must be unique")
    games = pd.read_csv(HERE / "data" / "games.csv", dtype={"game_id": str})
    minutes = pd.read_csv(HERE / "data" / "minutes.csv", dtype={"game_id": str})
    newcomers = pd.read_csv(HERE / "data" / "newcomers.csv")
    return files, systems, games, minutes, newcomers


def prepare(systems, games, minutes):
    """Seasons every system rates, the games and player-minutes in them, and each team's roster continuity."""
    have = set(games.season)
    seasons = sorted(s for s in set.intersection(*(set(d.season) for d in systems.values()))
                     if s in have and prev(s) in have)
    if not seasons:
        raise SystemExit("no season is rated by every system (and has the previous season's games)")

    team_min = minutes.groupby(["season", "team", "nba_id"], as_index=False)["min"].sum()
    continuity = {}
    for s in seasons:
        kept = set(zip(*team_min[team_min.season == prev(s)][["team", "nba_id"]].values.T))
        for t, d in team_min[team_min.season == s].groupby("team"):
            continuity[(s, t)] = d["min"][[(t, p) in kept for p in d.nba_id]].sum() / d["min"].sum()

    G = games[games.season.isin(seasons)].sort_values(["date", "game_id"]).reset_index(drop=True)
    G["margin"] = (G.home_pts - G.away_pts).astype(float)
    G["cont"] = [min(continuity[(s, h)], continuity[(s, a)]) for s, h, a in zip(G.season, G.home, G.away)]
    G["low"] = G.cont <= G.cont.quantile(1 / 3)
    G["cluster"] = G.season + ":" + G.home

    M = minutes[minutes.game_id.isin(G.game_id)].reset_index(drop=True)
    M["team_min"] = M.groupby(["game_id", "team"])["min"].transform("sum")
    M["game"] = M.game_id.map(dict(zip(G.game_id, G.index)))
    M["sign"] = np.where(M.team.values == G.home.values[M.game], 1.0, -1.0)

    side = lambda team, margin: pd.DataFrame({"season": G.season, "team": team, "margin": margin})
    results = pd.concat([side(G.home, G.margin), side(G.away, -G.margin)]).groupby(["season", "team"]).margin
    results = pd.DataFrame({"winpct": results.apply(lambda m: (m > 0).mean()), "mov": results.mean()})
    results["low"] = [continuity[i] <= np.quantile(list(continuity.values()), 1 / 3) for i in results.index]
    return seasons, G, M, team_min[team_min.season.isin(seasons)], results


# ---------------------------------------------------------------- report

ROWS = [("Game margin R^2", "margin_r2", 3), ("Team win % r", "winpct_r", 3), ("Team win % R^2", "winpct_r2", 3),
        ("Team avg margin RMSE (pts)", "mov_rmse", 2)]


def report(meta, res, gaps, hashes):
    order = meta["systems"]
    head = ["| Test | " + " | ".join(order) + " |", "|---|" + "---|" * len(order)]
    lines = [f"# Preseason ratings vs the season that followed ({meta['fill']} fill)", "",
             f"Seasons {meta['seasons'][0]} to {meta['seasons'][-1]}: {meta['games']:,} games, "
             f"{meta['low_games']:,} of them low-continuity. Team tests use {meta['minutes']} minutes.", ""]
    for part, title in (("all", "All"), ("low", "Low-continuity rosters")):
        lines += [f"## {title}", ""] + head
        lines += [f"| {t} | " + " | ".join(f"{res[k][part][key]:.{nd}f}" for k in order) + " |" for t, key, nd in ROWS]
        lines += [""]
    lines += [f"Share of game minutes each system rated: " + ", ".join(f"{k} {res[k]['rated_share']:.2f}" for k in order), ""]
    if gaps:
        lines += [f"## Margin R^2 gap, {order[0]} minus each (90% bootstrap interval)", ""]
        lines += [f"- {k}: all {g['all'][0]:+.3f} [{g['all'][1]:+.3f}, {g['all'][2]:+.3f}]; "
                  f"low-continuity {g['low'][0]:+.3f} [{g['low'][1]:+.3f}, {g['low'][2]:+.3f}]" for k, g in gaps.items()]
        lines += [""]
    lines += ["## Inputs (sha256)", ""] + [f"- `{name}` {h}" for name, h in hashes.items()]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--extra", help="folder of more <system>.csv files (season,nba_id,rating)")
    ap.add_argument("--minutes", help="CSV season,team,nba_id,min to use for the team tests instead of actual minutes")
    ap.add_argument("--fill", choices=["fitted", "replacement"], default="fitted")
    ap.add_argument("--first", help="system the bootstrap gaps are measured from (default: first by name)")
    ap.add_argument("--out", default=str(HERE / "results"))
    a = ap.parse_args()

    files, systems, games, minutes, newcomer_rows = load_inputs(a.extra)
    seasons, G, M, team_min, results = prepare(systems, games, minutes)
    if a.minutes:
        team_min = read_checked(a.minutes, ["season", "team", "nba_id", "min"], ["nba_id", "min"])
        team_min = team_min[team_min.season.isin(seasons)]
        unknown = set(team_min.team) - set(games.home) - set(games.away)
        if unknown:
            raise SystemExit(f"{Path(a.minutes).name}: unknown team code(s) {sorted(unknown)}; use the codes in data/games.csv")
        files.append(Path(a.minutes))
    newcomers = {(s, p): (pick, age) for s, p, pick, age in newcomer_rows[["season", "nba_id", "pick", "age"]].values}
    if a.first and a.first not in systems:
        raise SystemExit(f"--first {a.first}: no such system; have {sorted(systems)}")
    order = sorted(systems, key=lambda k: (k != a.first, k))

    res, preds = {}, {}
    for k in order:
        d = systems[k][systems[k].season.isin(seasons)]
        ratings = {s: dict(zip(g.nba_id.astype(int), g.rating.astype(float))) for s, g in d.groupby("season")}
        preds[k], fill_weights, share = game_margin_test(G, M, ratings, a.fill, newcomers)
        all_, low = team_tests(team_min, ratings, fill_weights, a.fill, newcomers, results)
        res[k] = {"all": {"margin_r2": float(r2(G.margin.values, preds[k])), **all_},
                  "low": {"margin_r2": float(r2(G.margin.values[G.low], preds[k][G.low])), **low},
                  "rated_share": share}
    gaps = bootstrap_gaps(G, preds, order[0]) if len(order) > 1 else {}

    meta = {"seasons": seasons, "games": len(G), "low_games": int(G.low.sum()), "fill": a.fill, "systems": order,
            "minutes": Path(a.minutes).name if a.minutes else "actual"}
    data = [HERE / "data" / f for f in ("games.csv", "minutes.csv", "newcomers.csv")]
    hashes = {f.name: sha256(f) for f in data + files}
    out = Path(a.out)
    out.mkdir(exist_ok=True)
    tag = "" if a.fill == "fitted" else f"_{a.fill}"
    (out / f"results{tag}.json").write_text(json.dumps({"meta": meta, "results": res, "gaps": gaps, "sha256": hashes}, indent=1))
    text = report(meta, res, gaps, hashes)
    (out / f"results{tag}.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
