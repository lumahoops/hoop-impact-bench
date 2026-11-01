"""Games and player minutes from NBA.com live box scores, when stats.nba.com blocks this PC.

  python live/code/from_box.py      <HIB_BOX>/*_boxscore.json.gz -> live/data/games_2026-27.csv, minutes_2026-27.csv,
                                                                   players_2026-27.csv (nba_id, name: for matching names)

Final regular-season games only (game ids 002..., gameStatus 3). Date = the game's US Eastern date. Minutes are the box
score's playing time rounded to whole minutes; players with 0 are dropped (same format as fetch_games.py). Checked on
2026-10-31: the 52 games through 10-26 match the leaguegamelog pull exactly (scores, dates, players; minutes within 3).
"""
import glob
import gzip
import json
import re
import pandas as pd

from paths import BOX, DATA as OUT, SEASON


def minutes(s):
    m = re.match(r"PT(\d+)M([\d.]+)S", s or "")
    return int(m.group(1)) + float(m.group(2)) / 60 if m else 0.0


def main():
    games, mins, names = [], [], {}
    for f in sorted(glob.glob(str(BOX / "*_boxscore.json.gz"))):
        d = json.load(gzip.open(f))
        g = d.get("game", d)
        if g.get("gameStatus") != 3 or not g["gameId"].startswith("002"):
            continue
        h, a = g["homeTeam"], g["awayTeam"]
        games.append((SEASON, g["gameId"], g["gameEt"][:10], h["teamTricode"], a["teamTricode"],
                      int(h["score"]), int(a["score"]), 0, g["gameTimeUTC"]))
        for t in (h, a):
            for p in t["players"]:
                m = round(minutes(p["statistics"].get("minutes")))
                if m > 0:
                    mins.append((SEASON, g["gameId"], t["teamTricode"], int(p["personId"]), m))
                    names[int(p["personId"])] = p.get("name") or f'{p.get("firstName", "")} {p.get("familyName", "")}'.strip()
    g = pd.DataFrame(games, columns=["season", "game_id", "date", "home", "away", "home_pts", "away_pts", "neutral",
                                     "tip_utc"])                  # tip_utc: for the daily board's saved-before-tip rule
    m = pd.DataFrame(mins, columns=["season", "game_id", "team", "nba_id", "min"])
    g = g.sort_values(["date", "game_id"])
    OUT.mkdir(parents=True, exist_ok=True)
    g.to_csv(OUT / f"games_{SEASON}.csv", index=False)
    m.to_csv(OUT / f"minutes_{SEASON}.csv", index=False)
    p = pd.DataFrame(sorted(names.items()), columns=["nba_id", "name"]).assign(season=SEASON)
    p[["season", "nba_id", "name"]].to_csv(OUT / f"players_{SEASON}.csv", index=False)
    print(f"{SEASON}: {len(g)} games {g.date.min()} to {g.date.max()}, {len(m)} player-games (box scores)")


if __name__ == "__main__":
    main()
