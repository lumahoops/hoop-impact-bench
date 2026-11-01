"""Write the GitHub Pages site (index.html at the repo root) with every board already in the HTML.

  python live/code/render_page.py

Reads live/results/frozen.json, live/results/daily.json (if any) and launch/*.json; fills live/code/page.html. Each board
is a table with one line above it; the explanation sits in a drawer under it (a <details> element, so it is in the HTML
for search engines and opens without JavaScript). JavaScript only switches tabs and the colour theme.
Run by the VPS job after publish.py, and committed with the results.
"""
import datetime
import json
from html import escape

from paths import LIVE, REPO, RESULTS

NAMES = {"loki": "LOKI †", "openrapm": "OpenRAPM", "arc_2yr": "ARC, 2-year †", "epm_current": "EPM", "darko": "DARKO",
         "lebron": "LEBRON", "bpm_bbref": "BPM (Basketball-Reference)", "pulse": "Pulse", "xrapm": "xRAPM", "xpm": "xPM",
         "danny": "Danny Harlan's EPM projection", "grbnu": "GRBNU",
         "ceiling_rapm_same_season": "Same-season RAPM (ceiling)", "rapm_last_season": "Last season's RAPM, no prior",
         "baseline_zero": "Everyone 0 (floor)", "baseline_last_team": "Last season's team (floor)"}

WHAT = ("<p>Hoop Impact Bench tests NBA player impact metrics (EPM, DARKO, LEBRON, BPM and others) on games played after "
        "their ratings were saved. In each game, every player's rating is weighted by the minutes he played, which gives "
        "each team a rating in points per 100 possessions. The home team's rating minus the away team's is the predicted "
        "margin, and the tables measure how closely the predicted margins follow the final margins.</p>"
        "<p>2026-27 is the current NBA season, which opened on October 20, 2026. The retro tables cover the six seasons "
        "before it.</p>")

LINE = {   # the one line above each table
    "frozen": "Every 2026-27 game, computed using each metric's ratings from before opening night (October 20, 2026).",
    "daily": "Each 2026-27 game day, computed using each metric's ratings as published that morning.",
}


def f3(x):
    return "" if x is None else (f"{x:.3f}".replace("0.", ".", 1) if 0 <= x < 1 else f"{x:.3f}".replace("-0.", "-.", 1)
                                 if -1 < x < 0 else f"{x:.3f}")


def rk(r):
    return "" if not r else str(r[0]) if r[0] == r[1] else f"{r[0]}-{r[1]}"


def iv(i):
    return f" <small>{f3(i[0])}-{f3(i[1])}</small>" if i else ""


def day(iso):
    d = datetime.date.fromisoformat(iso[:10])
    return f"{d:%b} {d.day}"


HEAD = ('<div class="wide"><table><tr><th>rank</th><th class="l">metric</th><th>game R² <small>90% range</small></th>'
        '<th>win % r</th><th>net error{}</th>{}</tr>')


def drawer(body):
    return f'<details class="help"><summary>? What this table shows</summary>\n{body}\n</details>'


def live_board(d):
    net = d["net_error_shown"]
    ex = len(d["snapshot"].get("excluded_games") or [])
    h = [f'<p class="line">{LINE[d["board"]]}</p>',
         f'<p class="meta"><b>{d["games"]} games</b> · {day(d["first_game"])} to {day(d["scored_through"])} · updated '
         f'{day(d["updated_utc"])}, {d["updated_utc"][11:16]} UTC</p>',
         "{{DRAWER}}",
         HEAD.format("" if net else " <small>after 20 games</small>", '<th class="l">label</th>')]
    for m in d["metrics"]:
        t = m["tests"]
        name = f'<a href="{escape(m["url"])}">{escape(m["name"])}</a>' if m.get("url") else escape(m["name"])
        maker = "" if m["maker"] in m["name"] else f" <small>{escape(m['maker'])}</small>"
        h.append(f'<tr><td>{rk(t["margin_r2"].get("rank"))}</td><td class="l">{name}{" †" if m["ours"] else ""}{maker}</td>'
                 f'<td><b>{f3(t["margin_r2"]["value"])}</b>{iv(t["margin_r2"]["interval"])}</td><td>{f3(t["winpct_r"]["value"])}</td>'
                 f'<td>{f"{t["net_rmse"]["value"]:.2f}" if net else "-"}</td>'
                 f'<td class="l" title="{escape(m["source"])}">{escape(m["label"])}</td></tr>')
    for r in d["reference"]:
        t = r["tests"]
        h.append(f'<tr class="ref"><td></td><td class="l" title="{escape(r["description"])}">{escape(r["name"])}</td>'
                 f'<td>{f3(t["margin_r2"]["value"])}{iv(t["margin_r2"]["interval"])}</td><td>{f3(t["winpct_r"]["value"])}</td>'
                 f'<td>{f"{t["net_rmse"]["value"]:.2f}" if net else "-"}</td><td></td></tr>')
    h.append("</table></div>")

    rules, tests = d["rules"], d["tests"]
    rule = (f"A player with fewer than {rules['min_minutes']:g} minutes in 2025-26, including every rookie, is rated "
            f"{rules['replacement']:.1f} for every metric." if rules["min_minutes"] else
            f"Every player is rated at the metric's own value. A player the metric does not rate is "
            f"{rules['replacement']:.1f}.")
    b = d["board"]
    body = [WHAT, f"<p>{escape(d['title'])}</p>"]
    if ex:
        body.append(f"<p>{ex} game{' is' if ex == 1 else 's are'} left out because {'it' if ex == 1 else 'they'} started "
                    "before that day's ratings were saved.</p>")
    body.append("<p><b>Columns</b></p><ul>"
                f"<li>{escape(tests['margin_r2'])}. Higher is better. The small numbers are its 90% range.</li>"
                f"<li>{escape(tests['winpct_r'])}. Higher is better.</li>"
                f"<li>{escape(tests['net_rmse'])}. Lower is better.{'' if net else ' ' + escape(d['net_error_note']) + '.'}</li>"
                f"<li>Rank: the range of places a metric reaches across {d['resamples']:,} resamples of the games (the middle "
                f"{round(d['confidence'] * 100)}%). Metrics whose ranges overlap are not separated by the games so far.</li>"
                f"<li>Minutes rule: {rule}</li>"
                "<li>Italic rows are reference points and are not ranked: RAPM fit on these same games (an upper "
                "reference), the average of all metrics, last season's RAPM, and two floors.</li></ul>")
    body.append("<p><b>Labels</b></p><ul>" + "".join(f"<li>{escape(k)}: {escape(v)}</li>" for k, v in d["labels"].items())
                + "</ul>")
    body.append(f'<p>Data: <a href="live/results/{b}.json">{b}.json</a>, <a href="live/results/{b}_games.csv">every game</a>, '
                f'<a href="live/results/{b}_history.csv">history</a>. Computed with eval.py v1.1.0 (sha256 '
                f'{d["harness_sha256"][:12]}...). Rules: <a href="https://github.com/lumahoops/hoop-impact-bench/blob/main/'
                'live/PROTOCOL.md">live protocol</a>.</p>')
    return "\n".join(h).replace("{{DRAWER}}", drawer("\n".join(body)))


def retro_table(d, title, note):
    rows = sorted(d["metrics"].items(), key=lambda kv: -kv[1]["all"]["margin_r2"]["value"])
    h = [f"<h3>{title}</h3>", f'<p class="meta">{note}</p>', HEAD.format("", "")]
    for ref in (False, True):
        for k, v in rows:
            if v["baseline"] != ref:
                continue
            a = v["all"]
            h.append(f'<tr{" class=\"ref\"" if ref else ""}><td>{"" if ref else rk(a["margin_r2"]["rank"])}</td>'
                     f'<td class="l">{escape(NAMES.get(k, k))}</td><td>{"" if ref else "<b>"}{f3(a["margin_r2"]["value"])}'
                     f'{"" if ref else "</b>"}{iv(a["margin_r2"]["interval"])}</td>'
                     f'<td>{f3(a["winpct_r"]["value"])}</td><td>{a["net_rmse"]["value"]:.2f}</td></tr>')
    h.append("</table></div>")
    return "\n".join(h)


def retro(est, full):
    m = est["meta"]
    body = [WHAT,
            f"<p>The retro tables compute each season from {m['seasons'][0]} to {m['seasons'][-1]} ({m['games']:,} games, "
            f"{m['team_seasons']} team-seasons) using the ratings each metric had before that season (HIB v{m['version']}).</p>",
            "<p>The past ratings come from each metric's current model rather than from what it published at the time, so "
            "a model may fit seasons it was built on. The 2026-27 tables do not have that problem.</p>",
            "<p>Columns: game R² is the share of the variation in final game margins that the predicted margins explain; "
            "win % r is the correlation between team ratings and team winning percentage; net error is the average miss, "
            "in points per 100 possessions, between team ratings and opponent-adjusted team margins. Rank is the range of "
            "places across 2,000 resamples (the middle 90%). Italic rows are reference points and are not ranked.</p>",
            '<p>Method, sources and every file: the <a href="https://github.com/lumahoops/hoop-impact-bench#readme">README'
            '</a> and <a href="https://github.com/lumahoops/hoop-impact-bench/blob/main/launch/provenance.csv">provenance'
            '</a>.</p>']
    return "\n".join([
        f'<p class="line">{m["seasons"][0]} to {m["seasons"][-1]}, computed using the ratings each metric had before '
        f'each season.</p>',
        f'<p class="meta"><b>{m["games"]:,} games</b> · {m["team_seasons"]} team-seasons</p>',
        drawer("\n".join(body)),
        retro_table(est, "Established players", "A player with fewer than 250 minutes the season before, including every "
                    "rookie, is rated -2.0 for every metric."),
        retro_table(full, "Full forecast", "Every player is rated at the metric's own value.")])


def section(tab, title, body):
    return f'<section class="board" data-tab="{tab}" id="{tab}-board">\n<h2>{title}</h2>\n{body}\n</section>'


def main():
    load = lambda p: json.loads(p.read_text(encoding="utf-8")) if p.exists() else None   # noqa: E731
    frozen, daily = load(RESULTS / "frozen.json"), load(RESULTS / "daily.json")
    est, full = load(REPO / "launch" / "established-players.json"), load(REPO / "launch" / "full-forecast.json")
    empty = lambda b: f'<p class="line">{LINE[b]}</p><p class="meta">No games yet.</p>' + drawer(WHAT)   # noqa: E731
    parts = [section("live", "2026-27 preseason", live_board(frozen) if frozen else empty("frozen")),
             section("daily", "2026-27 dynamic", live_board(daily) if daily else empty("daily")),
             section("retro", f"Retro {est['meta']['seasons'][0]} to {est['meta']['seasons'][-1]}", retro(est, full))]
    lead = ", ".join(f"{x['name']} {f3(x['tests']['margin_r2']['value'])}" for x in (frozen or {}).get("metrics", [])[:3])
    desc = ("Open benchmark for NBA impact metrics (EPM, DARKO, LEBRON, BPM, xRAPM, OpenRAPM, LOKI and more), computed on "
            "2026-27 games played after each metric's ratings were saved"
            + (f". Preseason table after {frozen['games']} games: {lead}" if frozen else "") + ".")
    page = (LIVE / "code" / "page.html").read_text(encoding="utf-8")
    card = "https://lumahoops.github.io/hoop-impact-bench/live/results/card.png"
    if frozen:   # a new address each update, so link previews fetch the new card
        card += "?v=" + frozen["updated_utc"][:16].replace(":", "").replace("-", "")
    page = page.replace("{{DESCRIPTION}}", escape(desc)).replace("{{CARD}}", card).replace("{{BOARDS}}", "\n".join(parts))
    (REPO / "index.html").write_text(page, encoding="utf-8", newline="\n")
    print(f"index.html: preseason {frozen['games'] if frozen else 0} games, dynamic {daily['games'] if daily else 0} games, retro")


if __name__ == "__main__":
    main()
