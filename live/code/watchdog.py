"""Daily check, run by GitHub (.github/workflows/live-watchdog.yml) at 15:45 UTC, independent of the server that does
the work. Fails, and so makes GitHub email the repo owner, when any of these is true:

  - today's snapshot manifest (live/snapshots/daily/<today ET>.json) is missing
  - a metric in it is empty (its pull failed all morning; that day's games will be left off the daily board)
  - a metric was saved after 16:00 UTC (later than the earliest regular-season tip-offs)
  - the published results have not been updated in 26 hours

It fails again every day the problem lasts. Standard library only.
"""
import datetime
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

LIVE = Path(__file__).resolve().parent.parent
LATEST_SAVE = datetime.time(16, 0)


def main():
    now = datetime.datetime.now(datetime.timezone.utc)
    day = now.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    problems = []
    path = LIVE / "snapshots" / "daily" / f"{day}.json"
    if not path.exists():
        problems.append(f"no daily snapshot for {day}: the job did not run or could not push")
    else:
        man = json.loads(path.read_text())
        cutoff = datetime.datetime.combine(datetime.date.fromisoformat(day), LATEST_SAVE, datetime.timezone.utc)
        for k, e in man["metrics"].items():
            if e["status"] == "empty":
                problems.append(f"{k} is EMPTY for {day} after {e.get('tries', '?')} tries: {e.get('reason', '')}")
            else:
                saved = datetime.datetime.fromisoformat(e.get("saved_at_utc", man["saved_at_utc"]))
                if saved > cutoff:
                    problems.append(f"{k} was saved at {saved:%H:%M} UTC, after {LATEST_SAVE:%H:%M} UTC")
    res = LIVE / "results" / "frozen.json"
    if res.exists():
        updated = datetime.datetime.fromisoformat(json.loads(res.read_text(encoding="utf-8"))["updated_utc"])
        if now - updated > datetime.timedelta(hours=26):
            problems.append(f"results last updated {updated:%Y-%m-%d %H:%M} UTC, over 26 hours ago")
    else:
        problems.append("live/results/frozen.json is missing")
    if problems:
        print(f"HIB live board, {day}: {len(problems)} problem(s)")
        for p in problems:
            print(" -", p)
        sys.exit(1)
    print(f"HIB live board, {day}: snapshot complete, results fresh")


if __name__ == "__main__":
    main()
