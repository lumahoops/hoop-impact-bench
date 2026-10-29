<!-- Assistant draft (2026-10-29), for Aayo to edit before publishing. -->
# Hoop Impact Bench (HIB)

**Do last season's impact-metric values predict this season?** If you build an NBA impact metric (a rating of a
player's effect on his team's point margin), run it here. Every metric is scored on the same games with the same
rules, so the numbers are comparable with anyone else's.

```
pip install numpy pandas
python eval.py                          # the bundled metrics
python eval.py --ratings my_metric.csv  # add yours
python check.py                         # confirm this copy reproduces the published results
```

A run takes a few seconds, prints a report, and saves a folder `runs/<date_time>/` with:

- `results.json`: every score, its interval and rank range, and a sha256 fingerprint of each input file (Windows
  line endings count as Mac/Linux ones, so both copies of a file match);
- `games.csv`: every game's actual margin and each metric's predicted margin;
- `teams.csv`: every team-season's win %, opponent-adjusted margin and each metric's team rating.

## Your file

One CSV per metric, named after it (`my_metric.csv`):

```
season,nba_id,rating
2024-25,1628983,7.85
2024-25,203999,8.10
```

- `season`: the season being predicted, like `2024-25`.
- `nba_id`: NBA.com person id.
- `rating`: points per 100 possessions, **known before that season's opening night**: last season's value, or a
  preseason projection. A value computed after opening night has seen the games it is predicting.

## Rules (the same for every metric)

From Taylor Snarr's 2020 retrodiction study (the 250-minute cutoff is Neil Paine's):

- players who played under 250 minutes the season before, rookies included, count as **-2.0** (replacement level);
- players missing from your file count as -2.0.

A team's rating, in a game or over a season, is 5 x the minutes-weighted mean of its players' values, using the minutes
they actually played.

## The tests

The v1 window: regular seasons 2020-21 to 2025-26, 7,230 games, 180 team-seasons. Every metric in a run is scored on
the seasons all of them cover, so cover the whole window to be comparable with the published results.

| Test | Question | Score | Credit |
|---|---|---|---|
| Game margins | How much of each game's final margin do the ratings explain? | R² | |
| Team win % | Do better-rated teams win more? | r | Krishna Narsu (2024) |
| Team net rating | How far is the team rating, taken at face value, from the team's opponent-adjusted margin? | RMSE (points) | Taylor Snarr (2020) |
| Rebuilt rosters | The same tests on the third of games and teams that kept the least of last season's minutes | | Snarr (2020), roster continuity |

Every score has a bootstrap interval: team-seasons are resampled, and every metric is scored on the same resamples.
Rank ranges come from the same resamples. Nothing is combined into one overall score.

## Options

| Option | Effect |
|---|---|
| `--ratings PATH ...` | Add metrics: CSV files or folders of CSVs |
| `--no-bundled` | Leave out the metrics in `ratings/` |
| `--baselines` | Add three reference rows, not ranked: every player 0 (only the -2.0 rule separates teams), each player = his main team's opponent-adjusted margin last season / 5, and RAPM fit on the season being scored (it has seen those games, so it shows a ceiling) |
| `--by-season` | Also print every score season by season |
| `--confidence 0.95` | Interval level (default 0.90) |
| `--min-minutes 0` | Score every file as-is: only players missing from a file get the replacement value. Default 250 |
| `--replacement -1.0` | The value those players get. Default -2.0 |
| `--resamples 5000` | Bootstrap resamples. Default 2000 |
| `--out FOLDER` | Where to save the run (default `runs/<date_time>`) |

Runs with `--min-minutes` or `--replacement` changed, or with a file that covers fewer seasons than the v1 window, are
marked **custom** in the report and in `results.json` (`meta.standard`): compare them only with runs under the same
rules and seasons.

## Bundled metrics

Each file holds, for every season, a value known before that season started.

| File | What it is |
|---|---|
| `ratings/loki.csv` | LOKI preseason ratings from LUMA's current model |
| `ratings/loki_bpm.csv` | LOKI with a BPM prior in place of its counted box-score prior (research variant) |
| `ratings/arc_1yr.csv`, `arc_2yr.csv`, `arc_3yr.csv` | ARC, LUMA's published boards: 1, 2 or 3 seasons ending the season before |
| `ratings/openrapm.csv` | OpenRAPM by Nathan Walker (github.com/bbstats/openrapm, MIT license in `ratings/OPENRAPM_LICENSE.txt`): its published ratings, snapshot built 2026-10-29, each player's previous-season value. Its box-score prior is trained on RAPM from every other season, later ones included, so these are not the values known before each season |
| `reference/rapm_same_season.csv` | Plain RAPM (ridge regression on lineup stints, no prior) fit on the season itself, for `--baselines`. It has seen the games it is scored on, so it is a ceiling, not an entry |

Other people's ratings (EPM, DARKO, LEBRON, Basketball-Reference's BPM, your own RAPM, ...) belong to their authors and
are not in this repository. Bring your own copy. The sha256 fingerprints in `results.json` let two people confirm they scored the
same file.

### Basketball-Reference BPM

1. On basketball-reference.com open each season's Advanced table (Seasons > 2024-25 > Advanced), then
   Share & Export > Get table as CSV, and save the text as a file, e.g. `bbref_2024-25.csv`.
2. `python tools/from_bbref.py 2019-20=bbref_2019-20.csv 2020-21=bbref_2020-21.csv ... --out bpm_bbref.csv`
3. `python eval.py --ratings bpm_bbref.csv`

Each table becomes the preseason ratings for the next season. Traded players use their season-total row, players are
matched to NBA.com ids by name (`data/players.csv`), and anyone not matched is listed. `--column OBPM` (or any other
column) scores that column instead.

## Data

| Path | Contents |
|---|---|
| `data/games.csv` | Regular-season scores, 2019-20 to 2025-26 (`neutral` = 1 for neutral-site games, including the 2020 Orlando restart) |
| `data/minutes.csv` | Minutes per player per game, same seasons (2019-20 only supplies last-season minutes) |
| `data/players.csv` | NBA.com id and name for every player-season, 2019-20 to 2025-26 |
| `results/` | The published run of the bundled metrics; `check.py` compares against it |

## Credit and license

Copyright 2026 Court Share LLC. Code: MIT (`LICENSE`). Data and ratings: CC BY 4.0 (`LICENSE-DATA`), except
`ratings/openrapm.csv` (Nathan Walker, MIT, `ratings/OPENRAPM_LICENSE.txt`). Credit: LUMA Basketball Research
(https://lumahoops.org). How to cite: `CITATION.cff`.

Questions, results and holes found: open an issue.
