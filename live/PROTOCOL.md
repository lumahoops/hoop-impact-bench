<!-- Assistant draft (2026-10-30), for Aayo to edit. -->
# Live track, 2026-27

The historical results score past seasons with each metric's current model. A model built after those seasons may fit
them better than it would have at the time, and anyone can submit ratings fitted to results that are already known.
The live track removes both problems: every rating is saved, and its fingerprint published here, before the games it
is scored on.

## Two tracks

The live track has two boards, scored on the same 2026-27 games with the same harness and rules:

- **Preseason** (files `frozen*`): each metric's rating saved before opening night (October 20, 2026), never updated.
  For a projection (LOKI, xPM, Danny Harlan's, DARKO, EPM) that is its preseason forecast. For a metric that publishes
  only season ratings (BPM, xRAPM, OpenRAPM, Pulse, LEBRON) it is the 2025-26 final, which is what that metric offered
  before the season. Fingerprints: `live/snapshots/preseason.json`.
- **Dynamic** (files `daily*`): every morning before that day's games, each metric's rating is saved exactly as its
  maker publishes it that morning, and that day's games are scored with it. Season-to-date ratings (OpenRAPM 2026-27,
  Basketball-Reference BPM 2026-27, Pulse, ARC Live) are used as published, even early in the season when they rest
  on a few games: HIB does not choose which of a maker's numbers counts, blend them, or wait for them to settle. A
  metric that publishes nothing newer (LOKI between weekly solves, xRAPM, xPM, Danny Harlan's, LEBRON until its
  2026-27 values appear) carries its latest saved value. A metric that changes its model mid-season is scored on the
  version it had that day. Fingerprints: `live/snapshots/daily/<date>.json`.

Saving the values ourselves each morning is what makes the dynamic board a true forecast: a site's view of a past date
shows its current model, not what it said then.

Rules (from 2026-11-06; see the amendment below). Every board has two views, computed from the same saved files:

- **Full forecast** (the default on both boards): every player counts at the metric's own rating, rookies and
  low-minute players included; a player the metric does not rate counts as -2.0.
- **Established players**: a player with fewer than 250 minutes in 2025-26, including every rookie, counts as -2.0 for
  every metric (Taylor Snarr's 2020 rule, the rule registered for the preseason board), and so does a player the metric
  does not rate. It matches the historical tables' Established players view.

Until 2026-11-06 the preseason board used only the registered rule and the dynamic board only the full forecast. (On
2026-11-01, with 88 games played, both boards were briefly scored without the low-minute rule; the owner then set the
preseason board back to the registered rule and kept the dynamic board without it.)

ARC (2-year window) stays in the preseason snapshot but is not scored on the preseason board (owner, 2026-11-01): it is
a window ending 2025-26, not a forecast, and has no rookies. ARC Live stays on the dynamic board.

Ranking test: team net error, centered (owner, 2026-11-06; at face value from 2026-11-01). It checks whether the
players' ratings, weighted by the minutes they played, add up to each team's opponent-adjusted net rating, in points per
100, after each metric's team ratings are shifted so its average team is 0, like the adjusted margins. The face-value
error is published beside it as "raw", with the offset (the metric's average team). Game margin R² and team win % r are
reported beside it. Until 2026-11-01 the live boards were ordered by game
margin R² and net error was hidden until every team had played 20 games; net error is now shown from the first game
with an "early" note until then, because the rank ranges and the floor rows already show how little a few games
separate.


Both boards use the HIB v1.1.0 harness, unchanged for the whole season (`live/code/eval_v1.1.0.py` is that release's
`eval.py` byte for byte; later releases of the historical benchmark do not change it). The centered net error is
computed from the harness's own team ratings and its own resamples by `live/code/centered.py`. Early in the season the
intervals are wide; read the rank ranges, not the order.

## Amendment, 2026-11-06 (owner)

Made after 123 games on the preseason board and 39 on the dynamic board.

- Ranking test: team net error, centered. Each metric's team ratings are shifted by one number so its average team is
  0, like the opponent-adjusted margins. The shift uses the saved ratings and the minutes played, never results. The
  face-value score is published beside it as "raw"; raw² = centered² + offset², where the offset is the metric's
  average team.
- Rules: both boards count every player at the metric's own rating, and a player the metric does not rate as -2.0.
  The preseason board's registered rule (under 250 minutes in 2025-26, rookies included, = -2.0) is published beside
  it as the Established players view, computed from the same saved files, so the registered scores remain available.
- The harness (`live/code/eval_v1.1.0.py`) is unchanged. Centering is applied to its team ratings, and the rule is its
  `--min-minutes` setting.
- No published number changes meaning. `net_rmse` stays the face-value error in every file; `net_rmse_centered` and
  `offset` are new. `frozen.json` keeps the registered rule; the preseason board's full forecast is `frozen_full.json`.
  `daily.json` keeps the full forecast; the dynamic board's established view is `daily_established.json`. The history
  files gain net error columns, filled in for earlier dates from the saved files.

## Labels

| Label | Meaning |
|---|---|
| archived | Published before the games, with proof (a release fingerprint or a dated public record) |
| saved | Saved by us before the games, but with no public record of the date (our own copy) |
| pulled | Dynamic board: fetched from the maker's site that morning, fingerprinted and pushed before the games |
| carried | Dynamic board: the metric published nothing newer, so its latest saved value is reused unchanged |
| empty | Dynamic board: the pull failed all morning (tried at 09:30, 12:00 and 15:00 UTC). No value that day, and that day's games are left off the dynamic board for every metric, so all metrics are always scored on the same games |
| backfill | Taken later from a site's date view, which shows the current model for a past date |

## Files

Everything needed to rebuild any day's boards is in the repo, except the ratings files themselves:

- `live/code/`: the scoring code (`score.py` preseason board, `daily_score.py` dynamic board, `publish.py`, `rapm_site.py`
  for the RAPM reference rows, `from_box.py` for the game data) and `reproduce.py`, which rebuilds both boards from a
  checkout and checks every published number. Run `HIB_RATINGS=<folder> python live/code/reproduce.py` on any commit.
- `live/data/`: 2026-27 games (with tip-off times), player minutes and player names (for matching names to ids), updated daily from NBA.com box scores.
- `live/reference/`: the 2026-27 RAPM reference rows.
- A GitHub Action (`.github/workflows/live-watchdog.yml`) checks every afternoon that the day's snapshot is complete and
  saved early enough, and that the results are fresh; a failed check emails the maintainer, every day it lasts.

- `live/snapshots/<name>.json`: for each metric, the label, the source and the sha256 fingerprint of the ratings
  file, plus the time it was saved. These are committed before the games they are scored on; the git history is the
  timestamp.
- Third-party ratings files are not published. Anyone who saves the same file can match its fingerprint.
- Scores are published in `live/results/`, the one source for every page that shows the board:
  - `frozen_full.json`: the preseason board, full forecast (the default view); `frozen.json`: the same board,
    established players. `daily.json` (full forecast) and `daily_established.json`: the dynamic board, same layout,
    plus the snapshot days and any games left off. Each holds the ranked metrics (score, 90% interval and rank range
    on each test, the offset, label, source and fingerprint), reference rows that are not ranked (same-season RAPM
    ceiling, the consensus of all metrics, last season's RAPM, two floors), and every pairwise gap. Both boards are
    ranked by team net error, centered, shown from the first game, with an "early" flag until every team has played 20.
  - `<file>_games.csv`: one row per game, the result and each row's predicted home margin.
  - `<file>_picks.csv`: one row per game, each metric's home-minus-away team rating (its sign is the W-L pick).
  - `<file>_history.csv`: each scoring run's numbers, appended, to show how the board moves.
- The consensus is each player's average across the ranked metrics that rate him. It is scored in a separate run, so it
  never changes anyone's rank range.
- The RAPM reference rows for 2026-27 are solved the way LUMA's site solves its published RAPM: counted possessions
  (FGA + 0.44 FTA + TOV - OREB), separate offense and defense terms, ridge 10,000, stints of 15+ seconds.
