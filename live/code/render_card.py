"""Draw the link-preview card (1200 x 630, dark mode) from the preseason board: live/results/card.png.

  python live/code/render_card.py

Top five rows of the preseason table (rank range, metric, game R²), the game count and dates. Needs Pillow; the
fonts are DejaVu Sans Mono (Linux) or Consolas (Windows). Run by the VPS job before render_page.py.
"""
import datetime
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from paths import RESULTS

W, H, M = 1200, 630, 64
BG, FG, MUTED, LINE, HEAD = "#2e2e2e", "#e4e4e4", "#a8a8a8", "#5c5c5c", "#3a3a3a"
FONTS = {"regular": ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "C:/Windows/Fonts/consola.ttf"],
         "bold": ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", "C:/Windows/Fonts/consolab.ttf"]}


def font(kind, size):
    for p in FONTS[kind]:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    raise SystemExit(f"no {kind} monospace font found")


def f3(x):
    return f"{x:.3f}".replace("0.", ".", 1) if 0 <= x < 1 else f"{x:.3f}"


def day(iso):
    d = datetime.date.fromisoformat(iso[:10])
    return f"{d:%b} {d.day}"


def main():
    f = RESULTS / "frozen_full.json"           # the default view (owner 2026-11-06); frozen.json = established players
    d = json.loads((f if f.exists() else RESULTS / "frozen.json").read_text(encoding="utf-8"))
    img = Image.new("RGB", (W, H), BG)
    g = ImageDraw.Draw(img)
    title, tag, small = font("bold", 46), font("regular", 26), font("regular", 22)
    cell, cell_b, head = font("regular", 30), font("bold", 30), font("regular", 22)

    g.text((M, 52), "Hoop Impact Bench", font=title, fill=FG)
    g.text((W - M, 66), "2026-27 preseason", font=tag, fill=MUTED, anchor="ra")
    g.text((M, 116), "NBA impact metrics, tested on games played after their ratings were saved", font=small, fill=MUTED)

    top, row = 172, 62
    cols = (M, M + 130, W - M)                     # rank | metric | game R² (right-aligned)
    g.rectangle((M, top, W - M, top + 46), fill=HEAD)
    g.text((cols[0] + 14, top + 12), "rank", font=head, fill=MUTED)
    g.text((cols[1] + 14, top + 12), "metric", font=head, fill=MUTED)
    g.text((cols[2] - 14, top + 12), "net error  90% range", font=head, fill=MUTED, anchor="ra")
    y = top + 46
    for m in d["metrics"][:5]:
        t = m["tests"].get("net_rmse_centered") or m["tests"]["net_rmse"]   # the ranked test: net error, centered
        r = t.get("rank") or ["", ""]
        g.line((M, y, W - M, y), fill=LINE, width=1)
        g.text((cols[0] + 14, y + 14), f"{r[0]}-{r[1]}" if r[0] != r[1] else str(r[0]), font=cell, fill=FG)
        g.text((cols[1] + 14, y + 14), m["name"] + (" †" if m.get("ours") else ""), font=cell, fill=FG)
        rng = f"{t['interval'][0]:.2f}-{t['interval'][1]:.2f}"
        g.text((cols[2] - 14, y + 20), rng, font=head, fill=MUTED, anchor="ra")
        w = g.textlength(rng, font=head)
        g.text((cols[2] - 14 - w - 18, y + 14), f"{t['value']:.2f}", font=cell_b, fill=FG, anchor="ra")
        y += row
    g.rectangle((M, top, W - M, y), outline=LINE, width=1)
    g.line((cols[1], top, cols[1], y), fill=LINE, width=1)

    foot = (f"{d['games']} games · {day(d['first_game'])} to {day(d['scored_through'])} · "
            "ratings saved before opening night")
    g.text((M, H - 74), foot, font=small, fill=MUTED)
    g.text((W - M, H - 74), "hoopimpactbench.org", font=small, fill=MUTED, anchor="ra") \
        if g.textlength(foot, font=small) + g.textlength("hoopimpactbench.org", font=small) + 40 < W - 2 * M \
        else g.text((M, H - 44), "hoopimpactbench.org", font=small, fill=MUTED)
    img.save(RESULTS / "card.png", optimize=True)
    print(f"card.png: top 5 of {len(d['metrics'])}, {d['games']} games")


if __name__ == "__main__":
    main()
