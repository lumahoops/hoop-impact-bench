<!-- Assistant draft (2026-10-30), for Aayo to edit. -->
# Live track, 2026-27

The historical results score past seasons with each metric's current model. A model built after those seasons may fit
them better than it would have at the time, and anyone can submit ratings fitted to results that are already known.
The live track removes both problems: every rating is saved, and its fingerprint published here, before the games it
is scored on.

## Two boards

- Frozen preseason: each metric's rating from before opening night (October 20, 2026), never updated, scored on every
  2026-27 game so far.
- Daily: every morning before that day's games, each metric's current published rating is saved, and that day's games
  are scored with it. The tally runs all season. A metric that changes its model mid-season is scored on the version it
  had that day.

The daily board scores forecasts as they are actually published. A metric is scored on whatever it showed that
morning: one that updates daily (EPM, DARKO, Pulse, OpenRAPM) uses that day's values; one that updates weekly (LOKI) or
not at all during the season (xRAPM, preseason-only projections) carries its latest value until it changes. Saving the
values ourselves each morning is what makes them true forecasts: a site's view of a past date shows its current model,
not what it said then.

Both boards use the unchanged HIB harness with no low-minute rule: every player counts at the metric's own value, and
only a player the metric does not rate counts as -2.0. Rookies and low-minute players are part of a forecast, and a
daily board rates them as soon as a metric does. (The 250-minute v1 rule stays for the historical tables. The live
boards used it until 2026-11-01, when the owner dropped it, with 88 games played; every score was recomputed under
the new rule from the same saved files.)

ARC (2-year window) stays in the frozen snapshot but is not scored on the frozen board (owner, 2026-11-01): it is a
window ending 2025-26, not a forecast, and has no rookies. ARC Live stays on the daily board. Early in the season the intervals are wide; read the rank ranges, not the order.

## Labels

| Label | Meaning |
|---|---|
| archived | Published before the games, with proof (a release fingerprint or a dated public record) |
| saved | Saved by us before the games, but with no public record of the date (our own copy) |
| pulled | Daily board: fetched from the maker's site that morning, fingerprinted and pushed before the games |
| carried | Daily board: the metric published nothing newer, so its latest saved value is reused unchanged |
| empty | Daily board: the pull failed all morning (tried at 09:30, 12:00 and 15:00 UTC). No value that day, and that day's games are left off the daily board for every metric, so all metrics are always scored on the same games |
| backfill | Taken later from a site's date view, which shows the current model for a past date |

## Files

Everything needed to rebuild any day's boards is in the repo, except the ratings files themselves:

- `live/code/`: the scoring code (`score.py` frozen board, `daily_score.py` daily board, `publish.py`, `rapm_site.py`
  for the RAPM reference rows, `from_box.py` for the game data) and `reproduce.py`, which rebuilds both boards from a
  checkout and checks every published number. Run `HIB_RATINGS=<folder> python live/code/reproduce.py` on any commit.
- `live/data/`: 2026-27 games (with tip-off times) and player minutes, updated daily from NBA.com box scores.
- `live/reference/`: the 2026-27 RAPM reference rows.
- A GitHub Action (`.github/workflows/live-watchdog.yml`) checks every afternoon that the day's snapshot is complete and
  saved early enough, and that the results are fresh; a failed check emails the maintainer, every day it lasts.

- `live/snapshots/<name>.json`: for each metric, the label, the source and the sha256 fingerprint of the ratings
  file, plus the time it was saved. These are committed before the games they are scored on; the git history is the
  timestamp.
- Third-party ratings files are not published. Anyone who saves the same file can match its fingerprint.
- Scores are published in `live/results/`, the one source for every page that shows the board:
  - `frozen.json`: the frozen preseason board. Ranked metrics (score, 90% interval and rank range on each test, plus
    label, source and fingerprint), reference rows that are not ranked (same-season RAPM ceiling, the consensus of all
    metrics, last season's RAPM, two floors), and every pairwise gap. Net error is flagged hidden until every team has
    played 20 games.
  - `frozen_games.csv`: one row per game, the result and each row's predicted home margin.
  - `frozen_history.csv`: each scoring run's numbers, appended, to show how the board moves.
- The consensus is each player's average across the ranked metrics that rate him. It is scored in a separate run, so it
  never changes anyone's rank range.
- The RAPM reference rows for 2026-27 are solved the way LUMA's site solves its published RAPM: counted possessions
  (FGA + 0.44 FTA + TOV - OREB), separate offense and defense terms, ridge 10,000, stints of 15+ seconds.
