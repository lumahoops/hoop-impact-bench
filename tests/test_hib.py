"""Small tests for the parts that can break quietly. Run: python tests/test_hib.py (or pytest)."""
import hashlib
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eval import read_ratings, season_span, sha256  # noqa: E402

GOOD = "season,nba_id,rating\n2024-25,1628983,7.85\n2024-25,203999,8.10\n"


def write(folder, name, text, **kw):
    path = Path(folder) / name
    with open(path, "w", newline="", **kw) as f:
        f.write(text)
    return path


def refused(folder, text, says):
    try:
        read_ratings(write(folder, "bad.csv", text))
    except SystemExit as e:
        assert says in str(e), f"expected '{says}' in: {e}"
        return
    raise AssertionError(f"accepted a file that should be refused ({says})")


def test_fingerprint_ignores_line_endings():
    with tempfile.TemporaryDirectory() as d:
        lf, crlf = write(d, "lf.csv", GOOD), write(d, "crlf.csv", GOOD.replace("\n", "\r\n"))
        assert sha256(lf) == sha256(crlf) == hashlib.sha256(GOOD.encode()).hexdigest()


def test_reader_accepts_excel_csv():
    with tempfile.TemporaryDirectory() as d:
        r = read_ratings(write(d, "excel.csv", GOOD.replace("\n", "\r\n"), encoding="utf-8-sig"))
        assert list(r.columns) == ["season", "nba_id", "rating"] and len(r) == 2


def test_reader_refuses_bad_files():
    with tempfile.TemporaryDirectory() as d:
        refused(d, "season,player,rating\n2024-25,1,1.0\n", "missing column")
        refused(d, "season,nba_id,rating\n2024,1,1.0\n", "row 2: season")
        refused(d, "season,nba_id,rating\n2024-25,1,1.0\n2024-25,jamesle01,1.0\n", "row 3: nba_id")
        refused(d, "season,nba_id,rating\n2024-25,1,1.0\n2024-25,2,\n", "row 3: rating")
        refused(d, "season,nba_id,rating\n2024-25,1,1.0\n2024-25,1,2.0\n", "row 3: a second rating")


def test_season_span():
    assert season_span(["2021-22", "2020-21", "2023-24"]) == "2020-21 to 2021-22, 2023-24"
    assert season_span(["2024-25"]) == "2024-25"


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for t in tests:
        t()
    print(f"OK: {len(tests)} tests passed")
