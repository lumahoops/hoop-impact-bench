<!-- Assistant draft (2026-10-30), for Aayo to edit. -->
# Live track, 2026-27

The historical results score past seasons with each metric's current model. A model built after those seasons may fit
them better than it would have at the time, and anyone can submit ratings fitted to results that are already known.
The live track removes both problems: every rating is saved, and its fingerprint published here, before the games it
is scored on.

## Two boards

- Preseason: each metric's rating from before opening night (October 20, 2026), scored on every 2026-27 game so far.
- Weekly: every Monday, each metric's current rating is saved and scored on that week's games only. A metric that
  changes its model mid-season is scored on the version it had that week.

Weekly means one information cutoff for everyone: a metric that updates daily (EPM, DARKO, Pulse) is scored on its
Monday-morning ratings for the whole week, the same as a metric that updates weekly (LOKI). A possible later addition is
a daily board, which would score each game with each metric's latest ratings from before tip-off that day and so
reward models that update fastest.

Both use the unchanged HIB harness and the v1 rules (under 250 minutes last season, rookies included, or missing
from a file = -2.0). Early in the season the intervals are wide; read the rank ranges, not the order.

## Labels

| Label | Meaning |
|---|---|
| archived | Published before the games, with proof (a release fingerprint or a dated public record) |
| saved | Saved by us before the games, but with no public record of the date (our own copy) |
| pulled_now | Saved by us at the time of the snapshot (every weekly snapshot) |
| backfill | Taken later from a site's date view, which shows the current model for a past date |

## Files

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
