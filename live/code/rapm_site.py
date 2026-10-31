"""
HIB's plain RAPM, solved the way LUMA's site solves its published RAPM boards (courtshare-backend
_build_xpts_windows.py / _build_rapm_history.py), one season at a time, no prior, no box score.

  stints    _leaf_stints_<SS>.json: [home5, away5, seconds, home_pts, away_pts, home_tally, away_tally],
            tally = [rimA, rimP, midA, midP, thrA, thrP, fta, ftp, tov, oreb, fbA, fbP]
  rows      two per stint, one for each team's offense: offense five, defense five
  kept      stints of 15+ seconds whose offense had 0.3+ possessions; regular-season games only (ids 002...)
  poss      counted: FGA + 0.44 FTA + TOV - OREB  (not estimated from time)
  target    100 x points / possessions, centred on its possession-weighted league mean
  weights   possessions
  design    +1 for each offensive player (offense column), +1 for each defensive player (defense column)
  penalty   ridge, alpha = 10,000, on all 2P player terms (no home-court term, as on the site)
  rating    net = offense - defense (defense stored raw: negative = good)
  gate      none: every player who appears is rated (the site's 2,000-possession gate is for display only)

Outputs, each rating labelled with the season it is used to PREDICT (HIB format season,nba_id,rating):
  --hist   reference/rapm_same_season.csv   fit on the season itself (2020-21 .. 2025-26): a ceiling, it saw the games
           reference/rapm_last_season.csv   fit on the previous season only (2019-20 .. 2024-25), carried forward
  --live   live/reference/rapm_same_season_2026-27.csv   2026-27 so far
           live/reference/rapm_last_season_2026-27.csv   2025-26 -> 2026-27

Stints come from HIB_STINTS_DIR (_leaf_stints_<SS>.json), or --stints-2627 for this season's file.
Usage: python live/code/rapm_site.py --live [--stints-2627 FILE]  |  --hist OUTDIR
"""
import argparse
import json
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.sparse.linalg import lsqr

REPO = Path(__file__).resolve().parents[2]
BE = Path(os.environ.get("HIB_STINTS_DIR", REPO.parent / "cdxtest" / "courtshare-backend"))   # _leaf_stints_<SS>.json
ALPHA, MIN_SECONDS, MIN_POSS = 10000.0, 15.0, 0.3


def code(season):                       # "2025-26" -> "2526"
    return season[2:4] + season[5:7]


def label(year_start):
    return f"{year_start}-{str(year_start + 1)[2:]}"


def poss_of(t):
    return max(t[0] + t[2] + t[4] + 0.44 * t[6] + t[8] - t[9], 0.0)


def load(season, override=None):
    path = Path(override) if override else BE / f"_leaf_stints_{code(season)}.json"
    s = json.load(open(path))
    return {g: ss for g, ss in s.items() if str(g).zfill(10).startswith("002")}


def fit(stints):
    rows = []
    for ss in stints.values():
        for st in ss:
            if float(st[2]) < MIN_SECONDS:
                continue
            h5, a5 = [int(x) for x in st[0]], [int(x) for x in st[1]]
            for o5, d5, tal in ((h5, a5, st[5]), (a5, h5, st[6])):
                ps = poss_of(tal)
                if ps < MIN_POSS or len(o5) != 5 or len(d5) != 5:
                    continue
                pts = tal[1] + tal[3] + tal[5] + tal[7]
                rows.append((o5, d5, ps, 100.0 * pts / ps))
    pids = sorted({p for o5, d5, _, _ in rows for p in o5 + d5})
    idx = {p: i for i, p in enumerate(pids)}
    P = len(pids)
    ri, ci, dat, W = [], [], [], []
    for r, (o5, d5, w, _) in enumerate(rows):
        sw = math.sqrt(w)
        for p in o5:
            ri.append(r); ci.append(idx[p]); dat.append(sw)
        for p in d5:
            ri.append(r); ci.append(P + idx[p]); dat.append(sw)
        W.append(sw)
    W = np.asarray(W)
    Xw = sp.csr_matrix((dat, (ri, ci)), shape=(len(rows), 2 * P))
    aug = sp.vstack([Xw, sp.identity(2 * P) * math.sqrt(ALPHA)]).tocsr()
    y = np.asarray([r[3] for r in rows])
    mu = np.average(y, weights=W ** 2)
    b = lsqr(aug, np.concatenate([(y - mu) * W, np.zeros(2 * P)]), iter_lim=1500, atol=1e-10, btol=1e-10)[0]
    return {p: round(float(b[idx[p]] - b[P + idx[p]]), 3) for p in pids}, len(rows)


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=["season", "nba_id", "rating"]).to_csv(path, index=False)
    print(f"{path}: {len(rows)} ratings")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hist")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--stints-2627")
    a = ap.parse_args()
    if a.hist:
        same, last = [], []
        for y in range(2020, 2026):                 # seasons scored: 2020-21 .. 2025-26
            t, p = label(y), label(y - 1)
            r, n = fit(load(t)); same += [(t, k, v) for k, v in r.items()]
            r2, n2 = fit(load(p)); last += [(t, k, v) for k, v in r2.items()]
            print(f"{t}: same-season {n} rows; last season ({p}) {n2} rows", flush=True)
        write(Path(a.hist) / "rapm_same_season.csv", same)
        write(Path(a.hist) / "rapm_last_season.csv", last)
    if a.live:
        r, n = fit(load("2026-27", a.stints_2627)); print(f"2026-27 so far: {n} rows")
        out = REPO / "live" / "reference"
        write(out / "rapm_same_season_2026-27.csv", [("2026-27", k, v) for k, v in r.items()])
        r2, n2 = fit(load("2025-26")); print(f"2025-26: {n2} rows")
        write(out / "rapm_last_season_2026-27.csv", [("2026-27", k, v) for k, v in r2.items()])


if __name__ == "__main__":
    main()
