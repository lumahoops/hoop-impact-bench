<!-- Assistant draft (2026-10-29), for Aayo to edit before publishing. -->
# Hoop Impact Bench

**Do last season's impact-metric values predict this season?** If you build an NBA impact metric (a rating of a
player's effect on his team's point margin), run it here. Every metric is scored on the same games with the same
rules, so the numbers are comparable with anyone else's.

```
pip install numpy pandas
python eval.py                          # the bundled metrics
python eval.py --ratings my_metric.csv  # add yours
python check.py                         # confirm this copy reproduces the published results
```

A run takes a few seconds, prints a report, and saves `runs/<date_time>/results.json`.

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

Regular seasons 2020-21 to 2025-26: 7,230 games, 180 team-seasons.

| Test | Question | Score | Credit |
|---|---|---|---|
| Game margins | How much of each game's final margin do the ratings explain? | R² | |
| Team win % | Do better-rated teams win more? | r | Krishna Narsu (2024) |
| Team net rating | How far is the team rating, taken at face value, from the team's opponent-adjusted margin? | RMSE (points) | Taylor Snarr (2020) |
| Rebuilt rosters | The same tests on the third of games and teams that kept the least of last season's minutes | | Snarr (2020), roster continuity |

Every score has a bootstrap interval: team-seasons are resampled, and every metric is scored on the same resamples.
The ranked tests also show a rank range from those resamples. Nothing is combined into one overall score.

## Options

| Option | Effect |
|---|---|
| `--ratings PATH ...` | Add metrics: CSV files or folders of CSVs |
| `--no-bundled` | Leave out the metrics in `ratings/` |
| `--by-season` | Also print every score season by season |
| `--confidence 0.95` | Interval level (default 0.90) |
| `--min-minutes 0` | Score every file as-is: only players missing from a file get the replacement value. Default 250 |
| `--replacement -1.0` | The value those players get. Default -2.0 |
| `--out FOLDER` | Where to save `results.json` (default `runs/<date_time>`) |

Runs with `--min-minutes` or `--replacement` changed are marked **custom rules** in the report and in `results.json`.

## What is here

| Path | Contents |
|---|---|
| `ratings/` | Metrics we can publish (LUMA's own outputs) |
| `data/games.csv` | Regular-season scores, 2019-20 to 2025-26 (`neutral` = 1 for neutral-site games) |
| `data/minutes.csv` | Minutes per player per game, same seasons (2019-20 only supplies last-season minutes) |
| `eval.py` | The harness |
| `results/results.json` | The published run of the bundled metrics |
| `check.py` | Reruns it and compares with `results/results.json` |

Other people's ratings (EPM, DARKO, LEBRON, ...) belong to their authors and are not in this repository. Bring your
own copy. `results.json` lists a sha256 fingerprint for every input file, so two people can confirm they scored
the same file.

## Credit and license

Data: CC BY 4.0 (`LICENSE-DATA`). Credit: LUMA Basketball Research (https://lumahoops.org). Code: MIT (`LICENSE`).
Questions, results and holes found: open an issue or email us.
