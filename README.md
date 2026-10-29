<!-- Assistant draft (2026-10-28), for Aayo to edit before publishing. -->
# Preseason rating benchmark

Do preseason NBA player ratings predict the season that follows? Put any rating system in, get the same tests out,
on the same games, with the same rules for everyone.

```
pip install numpy pandas
python eval.py                       # score the systems in ratings/
python eval.py --extra my_ratings/   # add yours
python check.py                      # confirm this repo reproduces the published results
```

A run takes a few seconds and writes `results/results.md` and `results/results.json`.

## The tests

Seasons 2020-21 to 2025-26, regular season, 7,230 games.

| Test | How a team's rating is built | Score |
|---|---|---|
| Game margin | 5 x the minutes-weighted mean of its players' ratings, minutes from that game. Home minus away predicts the margin through a straight line fitted leave-one-season-out. | R² |
| Team win % | 5 x the season-minutes-weighted mean of its players' ratings | r and R² ([Krishna Narsu](https://x.com/knarsu3)'s test) |
| Team average margin | the same team rating, taken at face value | RMSE in points (Taylor Snarr's 2020 retrodiction) |

Each test is repeated on the third of games and teams that kept the least of last season's minutes, where a
preseason rating has the most work to do. The game-margin gap between the first system and each other one gets a 90%
bootstrap interval (resampling home team-seasons).

## Add your system

One CSV per system, named after it (`mine.csv`), columns `season,nba_id,rating`:

```
season,nba_id,rating
2024-25,1628983,7.85
2024-25,203999,8.10
```

- `season`: like `2024-25`.
- `nba_id`: NBA.com person id.
- `rating`: points per 100 possessions, **as shown before that season's opening night**. A value from after opening
  night has seen the season it is predicting.

Put the files in a folder and run `python eval.py --extra that_folder/`. Only seasons every system covers are
scored, so the comparison is always on identical games. Bad files are refused with the reason, not scored.

## Options

| Option | Effect |
|---|---|
| `--minutes FILE` | Team tests use your minutes (`season,team,nba_id,min`) instead of the minutes actually played, e.g. a projected-minutes model. Game margins always use real game minutes. |
| `--fill replacement` | Players a system does not rate count as -2.0. Default (`fitted`): newcomers get a value from draft pick and age, anyone else unrated gets one constant, both fitted from game results in the other seasons, separately for each system. |
| `--seasons FIRST:LAST` | Score only these seasons, e.g. `2021-22:2024-25` (2 or more; each is predicted by a fit on the others). |
| `--first NAME` | The system the bootstrap gaps are measured from. |

## Ratings we do not publish

Other systems' ratings belong to their authors and are not in this repository. When we report a score for one, we
publish the sha256 of the exact file we used (`results.json`, `sha256`). Anyone holding the same file gets the same
hash and, running `eval.py`, the same numbers.

## What is here

| Path | Contents |
|---|---|
| `ratings/loki.csv` | LOKI preseason ratings 2020-21 to 2025-26, as published before each opening night |
| `ratings/loki_bpm.csv` | LOKI with a BPM prior in place of its counted box-score prior (research variant, not the published board) |
| `data/games.csv` | regular-season scores 2019-20 to 2025-26 (`neutral` = 1 for neutral-site games) |
| `data/minutes.csv` | minutes per player per game, same seasons (2019-20 only feeds roster continuity) |
| `data/newcomers.csv` | players with no NBA rating the season before: draft pick (blank = undrafted) and age |

## Credit and license

Data: CC BY 4.0 (`LICENSE-DATA`). Credit: LUMA Basketball Research (https://lumahoops.org). Code: MIT (`LICENSE`).
Holes found: open an issue.
