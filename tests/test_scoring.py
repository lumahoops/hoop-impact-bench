"""Tests of the scoring path: small cases with known answers, and the rules a reader checks first.
Run: python tests/test_scoring.py (or pytest). The last three run eval.py end to end (a few seconds each)."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
from eval import apply_rules, correlations, opponent_adjusted, prev, score  # noqa: E402


def run_eval(*args):
    """results.json of an eval.py run (100 resamples: enough for these checks)."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([sys.executable, str(HERE / "eval.py"), *args, "--resamples", "100", "--out", tmp],
                       check=True, capture_output=True)
        return json.loads((Path(tmp) / "results.json").read_text(encoding="utf-8"))


def test_opponent_adjusted_round_robin():
    # neutral site: A beats B by 6, B beats C by 6, A beats C by 12 -> A +6, B 0, C -6
    games = pd.DataFrame({"season": "2024-25", "home": ["A", "B", "A"], "away": ["B", "C", "C"],
                          "margin": [6.0, 6.0, 12.0], "neutral": [1, 1, 1]})
    adjusted = opponent_adjusted(games)
    assert np.allclose([adjusted[("2024-25", t)] for t in "ABC"], [6, 0, -6])


def test_rules_replace_low_minute_and_unrated_players():
    value, eligible, rated = apply_rules(np.array([1.0, 5.0, np.nan]), np.array([300, 100, 300]), 250, -2.0)
    assert value.tolist() == [1.0, -2.0, -2.0]
    assert eligible.tolist() == [True, False, True] and rated.tolist() == [True, True, False]


def test_perfect_ratings_score_perfectly_and_constants_score_zero():
    margin, win_pct, adjusted = np.array([5.0, -3.0, 8.0, 1.0]), np.array([.7, .4, .5]), np.array([4.0, -2.0, 1.0])
    game_ratings = np.vstack([margin, np.full(4, 2.0)])        # a perfect metric and a constant one
    team_ratings = np.vstack([adjusted, np.full(3, 2.0)])
    r2, r, rmse = score(game_ratings, team_ratings, (margin, win_pct, adjusted), np.arange(4), np.arange(3))
    assert np.isclose(r2[0], 1) and np.isclose(rmse[0], 0)
    assert r2[1] == 0 and r[1] == 0
    assert correlations(np.ones((1, 3)), np.array([1.0, 2.0, 3.0]))[0] == 0


def test_rookie_values_only_count_without_the_low_minute_rule():
    """Under the default rule a file's values for players under 250 minutes last season (rookies included) are
    replaced by -2.0, so changing them changes nothing; with --min-minutes 0 they count."""
    loki = pd.read_csv(HERE / "ratings" / "loki.csv")
    minutes = pd.read_csv(HERE / "data" / "minutes.csv", dtype={"game_id": str})
    last = minutes.groupby(["season", "nba_id"])["min"].sum()
    low = np.array([last.get((prev(s), p), 0.0) < 250 for s, p in zip(loki.season, loki.nba_id)])
    assert low.sum() > 500                                     # plenty of rookies and low-minute players
    with tempfile.TemporaryDirectory() as tmp:
        loki.to_csv(Path(tmp) / "loki.csv", index=False)
        loki.assign(rating=np.where(low, 40.0, loki.rating)).to_csv(Path(tmp) / "wild.csv", index=False)
        for rules, should_match in (([], True), (["--min-minutes", "0"], False)):
            m = run_eval("--no-bundled", "--ratings", tmp, *rules)["metrics"]
            match = all(m["loki"]["all"][t]["value"] == m["wild"]["all"][t]["value"] for t in m["loki"]["all"])
            assert match == should_match, rules


def test_reference_rows_are_never_ranked():
    m = run_eval("--baselines")["metrics"]
    ranked = [k for k, v in m.items() if not v["baseline"]]
    for name, v in m.items():
        for part in ("all", "rebuilt"):
            for s in v[part].values():
                assert ("rank" in s) == (name in ranked)
                assert "rank" not in s or 1 <= s["rank"][0] <= s["rank"][1] <= len(ranked)


def test_a_file_with_fewer_seasons_marks_the_run_custom():
    with tempfile.TemporaryDirectory() as tmp:
        short = pd.read_csv(HERE / "ratings" / "loki.csv").query("season != '2020-21'")
        short.to_csv(Path(tmp) / "short.csv", index=False)
        meta = run_eval("--ratings", str(Path(tmp) / "short.csv"))["meta"]
    assert meta["standard"]["window"] is False and meta["seasons"][0] == "2021-22"
    assert meta["window_limited_by"] == {"short": "2021-22 to 2025-26"}


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for t in tests:
        t()
    print(f"OK: {len(tests)} tests passed")
