"""
Turns Basketball-Reference "Advanced" season tables into a Hoop Impact Bench ratings file.

Basketball-Reference's numbers are theirs, so they are not in this repository. To score their BPM:
  1. On basketball-reference.com open each season's Advanced table (Seasons > 2024-25 > Advanced), then
     Share & Export > Get table as CSV, and save the text as a file, e.g. bbref_2024-25.csv.
  2. python tools/from_bbref.py 2019-20=bbref_2019-20.csv 2020-21=bbref_2020-21.csv ... --out bpm_bbref.csv
  3. python eval.py --ratings bpm_bbref.csv

A table's values become the preseason ratings for the NEXT season (the 2024-25 table rates players for 2025-26).
Players are matched to NBA.com ids by name within the season (data/players.csv); anyone not matched is listed.
--column picks another column, e.g. OBPM or DBPM.
"""
import argparse
import re
import unicodedata
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent.parent
MULTI_TEAM = {"TOT", "2TM", "3TM", "4TM", "5TM"}
ALIASES = {  # Basketball-Reference spelling -> NBA.com spelling, after normalising
    "nicolasclaxton": "nicclaxton", "cameronthomas": "camthomas", "herbertjones": "herbjones",
    "moritzwagner": "moewagner", "nahshonhyland": "boneshyland", "kenyonmartin": "kjmartin",
}


def key(name):
    """lower-case letters only, accents and Jr./Sr./II-IV dropped"""
    s = "".join(c for c in unicodedata.normalize("NFKD", str(name)) if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z]", "", s.replace("*", ""))
    s = re.sub(r"(jr|sr|ii|iii|iv)$", "", s)
    return ALIASES.get(s, s)


def season_after(season):
    y = int(season[:4]) + 1
    return f"{y}-{str(y + 1)[2:]}"


def read_table(path, column):
    t = pd.read_csv(path)
    team = "Team" if "Team" in t.columns else "Tm"
    need = ["Player", team, column]
    if any(c not in t.columns for c in need):
        raise SystemExit(f"{path}: expected columns {need}; is this a Basketball-Reference Advanced table?")
    t = t[(t.Player != "Player") & (t.Player != "League Average") & t.Player.notna()].copy()   # repeated headers
    who = "Player-additional" if "Player-additional" in t.columns else "Player"
    t["multi"] = t[team].isin(MULTI_TEAM)
    t = t.sort_values("multi", ascending=False).drop_duplicates(who)          # a traded player's season-total row
    t[column] = pd.to_numeric(t[column], errors="coerce")
    return t[t[column].notna()]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tables", nargs="+", help="SEASON=FILE, the season the table is from, e.g. 2024-25=bbref.csv")
    ap.add_argument("--column", default="BPM")
    ap.add_argument("--out", default="bpm_bbref.csv")
    a = ap.parse_args()

    players = pd.read_csv(HERE / "data" / "players.csv")
    players["key"] = players.name.map(key)
    rows, missed = [], []
    for arg in a.tables:
        season, _, path = arg.partition("=")
        if not re.fullmatch(r"\d{4}-\d{2}", season) or not path:
            raise SystemExit(f"{arg}: write SEASON=FILE, e.g. 2024-25=bbref_2024-25.csv")
        ids = players[players.season == season].groupby("key").nba_id.unique()
        t = read_table(path, a.column)
        for name, value in zip(t.Player, t[a.column]):
            match = ids.get(key(name), [])
            if len(match) == 1:
                rows.append((season_after(season), int(match[0]), float(value)))
            else:
                missed.append(f"{season} {name}")
        print(f"{season}: {len(t)} players in the table")
    out = pd.DataFrame(rows, columns=["season", "nba_id", "rating"]).drop_duplicates(["season", "nba_id"])
    out.to_csv(a.out, index=False)
    print(f"wrote {a.out}: {len(out)} ratings ({a.column})")
    if missed:
        print(f"not matched ({len(missed)}): " + "; ".join(missed[:25]) + (" ..." if len(missed) > 25 else ""))


if __name__ == "__main__":
    main()
