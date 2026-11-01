"""Where the live-track code finds things. Public inputs live in the repo; private ones (the ratings files) wherever
you keep them, set by environment variables:

  HIB_RATINGS   folder with preseason/<metric>.csv and daily/<date>/<metric>.csv   (default _private_live/snapshots)
  HIB_WORK      scratch folder for runs                                            (default _private_live)
  HIB_BOX       NBA.com box scores, *_boxscore.json.gz (only from_box.py needs them; default <HIB_WORK>/raw/box_2627)
  HIB_RESULTS   where publish.py writes the boards (default live/results; reproduce.py points it elsewhere)
"""
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SEASON = "2026-27"
LIVE = REPO / "live"
DATA = LIVE / "data"                    # games_2026-27.csv, minutes_2026-27.csv (public)
REFERENCE = LIVE / "reference"          # rapm_same_season_2026-27.csv, rapm_last_season_2026-27.csv (public)
SNAPSHOTS = LIVE / "snapshots"          # fingerprint manifests (public)
RESULTS = Path(os.environ.get("HIB_RESULTS", LIVE / "results"))   # the published boards (public)
RATINGS = Path(os.environ.get("HIB_RATINGS", REPO / "_private_live" / "snapshots"))
WORK = Path(os.environ.get("HIB_WORK", REPO / "_private_live"))
BOX = Path(os.environ.get("HIB_BOX", WORK / "raw" / "box_2627"))
RUNS = WORK / "runs"
# Live rule (owner, 2026-11-01): no low-minute rule. Every player counts at the metric's own value; only a player the
# metric does not rate gets the replacement. (The 250-minute v1 rule is for the historical tables.)
RULES = {"min_minutes": 0.0, "replacement": -2.0}
RELEASE_HARNESS = "cfde3f922e88298361c51bf293b959e8a93626fde51fe4db2c7bedc2f5d11b4a"   # eval.py v1.1.0
