"""Team net error, centered (owner 2026-11-06): the ranking test on both live boards.

Each row's team ratings minus its average team in the season, the same zero as the opponent-adjusted margins they are
compared with, so a metric is not charged for where its zero sits. The shift is one number per row per season, from the
ratings and minutes only (never the results). In a season raw^2 = centered^2 + offset^2, where the offset is the row's
average team rating.

Computed from the harness's own team ratings with the harness's own resamples (its bootstrap and seed), so the pinned
harness (eval_v1.1.0.py) is unchanged and the intervals line up with every other test on the board.
"""
import json

import numpy as np

TEST = "net_rmse_centered"


def center(team_ratings, season_of):
    out = np.array(team_ratings, dtype=float)
    season_of = np.asarray(season_of)
    for s in np.unique(season_of):
        cols = season_of == s
        out[:, cols] -= out[:, cols].mean(axis=1, keepdims=True)
    return out


def scores(ev, names, ranked, team_ratings, games, team_seasons, resamples=2000, confidence=0.90):
    """{"rows": {name: {value, interval, offset, rank (ranked rows only)}}, "pairs": [...]} for the centered test.
    names = the rows of team_ratings; ranked = the names that get a rank range (the metrics)."""
    season_of = team_seasons.index.get_level_values(0)
    cen = center(team_ratings, season_of)
    target = team_seasons.adjusted_margin.values

    def score_rows(game_rows, team_rows):            # one test x rows, the harness's bootstrap shape
        return np.sqrt(((cen[:, team_rows] - target[team_rows]) ** 2).mean(axis=1))[None, :]

    point = score_rows(None, np.arange(len(team_seasons)))[0]
    with np.errstate(invalid="ignore"):
        draws = ev.bootstrap(score_rows, games, team_seasons, resamples)["all"][:, 0, :]
    q = [(1 - confidence) / 2, (1 + confidence) / 2]
    cols = [names.index(k) for k in ranked]
    order = draws[:, cols].argsort(axis=1).argsort(axis=1) + 1
    rows = {}
    for i, k in enumerate(names):
        s = {"value": float(point[i]), "interval": [float(v) for v in np.quantile(draws[:, i], q)],
             "offset": float(np.asarray(team_ratings[i]).mean())}
        if k in ranked:
            r = order[:, ranked.index(k)]
            s["rank"] = [int(np.quantile(r, q[0], method="lower")), int(np.quantile(r, q[1], method="higher"))]
        rows[k] = s
    pairs = []
    for j, a in enumerate(ranked):
        for b in ranked[j + 1:]:
            ia, ib = names.index(a), names.index(b)
            pairs.append({"part": "all", "test": TEST, "a": a, "b": b, "diff": float(point[ia] - point[ib]),
                          "interval": [float(v) for v in np.quantile(draws[:, ia] - draws[:, ib], q)]})
    return {"rows": rows, "pairs": pairs, "resamples": resamples, "confidence": confidence}


def write(path, result):
    path.write_text(json.dumps(result, indent=1), encoding="utf-8")
