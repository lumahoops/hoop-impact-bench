# Preseason ratings vs the season that followed (fitted fill)

Seasons 2020-21 to 2025-26: 7,230 games, 2,429 of them low-continuity. Team tests use actual minutes.

## All

| Test | loki | loki_bpm |
|---|---|---|
| Game margin R^2 | 0.195 | 0.199 |
| Team win % r | 0.828 | 0.831 |
| Team win % R^2 | 0.686 | 0.691 |
| Team avg margin RMSE (pts) | 3.49 | 3.80 |

## Low-continuity rosters

| Test | loki | loki_bpm |
|---|---|---|
| Game margin R^2 | 0.245 | 0.251 |
| Team win % r | 0.815 | 0.835 |
| Team win % R^2 | 0.665 | 0.697 |
| Team avg margin RMSE (pts) | 3.87 | 4.15 |

Share of game minutes each system rated: loki 1.00, loki_bpm 1.00

## Margin R^2 gap, loki minus each (90% bootstrap interval)

- loki_bpm: all -0.004 [-0.007, -0.001]; low-continuity -0.006 [-0.012, -0.001]

## Inputs (sha256)

- `games.csv` 2d317a0a6c399a090b110264f8b742b12b12da96eab972d9f9e9db3a39e07370
- `minutes.csv` 071882adf99bffb53364141369b739cc582348d695f3272723df7019adf94879
- `newcomers.csv` eff67f3ea985a7bf8e9dd00f656f7e39834a710c887c03a72dae8586eaef7f7c
- `loki.csv` 7867d7afa9bc2ef9df0f6d847f4b4706d1cb714730042da6645633161a01322f
- `loki_bpm.csv` 3952f7ea07738298907e1613dd4b0f93e6d6ebe5b47c8488f356d8ac66cbc59a
