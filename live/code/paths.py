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
# Rules (owner 2026-11-06; before that 2026-11-01). Two views of every board, scored from the same saved files:
#   full          the full forecast, the default on both boards: every player at the metric's own value, rookies
#                 included; a player the metric does not rate = -2.0
#   established   established players (Snarr 2020): under 250 minutes in 2025-26, rookies included, or not rated = -2.0
# The preseason board was registered with the established rule, so its files keep their names (frozen*) and the full
# view is frozen_full*; score.py runs the harness with its defaults for the established view, --min-minutes 0 for the
# full view. The dynamic board was registered with no rule (daily*); its established view is daily_established*.
PRESEASON_RULES = {"min_minutes": 250, "replacement": -2.0}   # established players (the harness defaults)
DYNAMIC_RULES = {"min_minutes": 0.0, "replacement": -2.0}    # full forecast
VIEWS = {   # board -> view -> (run folder under <HIB_WORK>/runs = results file stem in live/results, rules)
    "frozen": {"full": ("frozen_full", DYNAMIC_RULES), "established": ("frozen", PRESEASON_RULES)},
    "daily": {"full": ("daily", DYNAMIC_RULES), "established": ("daily_established", PRESEASON_RULES)},
}
DEFAULT_VIEW = "full"
VIEW_NAMES = {"full": "Full forecast", "established": "Established players"}
# Metrics kept in the frozen snapshot (fingerprint committed) but not scored on the frozen board (owner, 2026-11-01).
FROZEN_DROPPED = {"arc_2yr": "a 2-year window ending 2025-26, not a forecast, with no rookies; ARC Live stays on the daily board"}
HARNESS = Path(__file__).resolve().parent / "eval_v1.1.0.py"   # eval.py of release v1.1.0, byte for byte: the live
# track keeps the harness it was registered with, whatever later releases change
RELEASE_HARNESS = "cfde3f922e88298361c51bf293b959e8a93626fde51fe4db2c7bedc2f5d11b4a"   # eval.py v1.1.0
