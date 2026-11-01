"""Write the GitHub Pages site (index.html at the repo root) with every board already in the HTML.

  python live/code/render_page.py

Reads live/results/frozen.json, live/results/daily.json (if any) and launch/*.json; fills live/code/page.html. No
JavaScript is needed to read the numbers (search engines and plain fetchers see them); JavaScript only switches tabs.
Run by the VPS job after publish.py, and committed with the results.
"""
import json
from html import escape
from pathlib import Path

from paths import LIVE, REPO, RESULTS

NAMES = {"loki": "LOKI †", "openrapm": "OpenRAPM", "arc_2yr": "ARC, 2-year †", "epm_current": "EPM", "darko": "DARKO",
         "lebron": "LEBRON", "bpm_bbref": "BPM (Basketball-Reference)", "pulse": "Pulse", "xrapm": "xRAPM", "xpm": "xPM",
         "danny": "Danny Harlan's EPM projection", "grbnu": "GRBNU",
         "ceiling_rapm_same_season": "Same-season RAPM (ceiling)", "rapm_last_season": "Last season's RAPM, no prior",
         "baseline_zero": "Everyone 0 (floor)", "baseline_last_team": "Last season's team (floor)"}


def f3(x):
    return "" if x is None else (f"{x:.3f}".replace("0.", ".", 1) if 0 <= x < 1 else f"{x:.3f}".replace("-0.", "-.", 1)
                                 if -1 < x < 0 else f"{x:.3f}")


def rk(r):
    return "" if not r else str(r[0]) if r[0] == r[1] else f"{r[0]}-{r[1]}"


def iv(i):
    return f" <small>({f3(i[0])}-{f3(i[1])})</small>" if i else ""


HEAD = ('<div class="wide"><table><tr><th>rank</th><th class="l">metric</th><th>game R²</th>'
        '<th>win % r</th><th>net error</th>{}</tr>')


def day(iso):
    import datetime
    d = datetime.date.fromisoformat(iso[:10])
    return f"{d:%b} {d.day}"


def live_board(d):
    net = d["net_error_shown"]
    ex = len(d["snapshot"].get("excluded_games") or [])
    h = [f"<p>{escape(d['title'])}</p>",
         f"<p><b>{d['games']} games scored</b>, {day(d['first_game'])} to {day(d['scored_through'])}. Updated "
         f"{day(d['updated_utc'])}, {d['updated_utc'][11:16]} UTC.</p>"]
    if ex:
        h.append(f"<p>{ex} game{' is' if ex == 1 else 's are'} not scored because {'it' if ex == 1 else 'they'} started "
                 "before that day's ratings were saved.</p>")
    h.append(HEAD.format('<th class="l">label</th>'))
    for m in d["metrics"]:
        t = m["tests"]
        name = f'<a href="{escape(m["url"])}">{escape(m["name"])}</a>' if m.get("url") else escape(m["name"])
        maker = "" if m["maker"] in m["name"] else f" <small>{escape(m['maker'])}</small>"
        h.append(f'<tr><td>{rk(t["margin_r2"].get("rank"))}</td><td class="l">{name}{" †" if m["ours"] else ""}{maker}</td>'
                 f'<td>{f3(t["margin_r2"]["value"])}{iv(t["margin_r2"]["interval"])}</td><td>{f3(t["winpct_r"]["value"])}</td>'
                 f'<td>{f"{t["net_rmse"]["value"]:.2f}" if net else "-"}</td>'
                 f'<td class="l" title="{escape(m["source"])}">{escape(m["label"])}</td></tr>')
    for r in d["reference"]:
        t = r["tests"]
        h.append(f'<tr class="ref"><td></td><td class="l" title="{escape(r["description"])}">{escape(r["name"])}</td>'
                 f'<td>{f3(t["margin_r2"]["value"])}{iv(t["margin_r2"]["interval"])}</td><td>{f3(t["winpct_r"]["value"])}</td>'
                 f'<td>{f"{t["net_rmse"]["value"]:.2f}" if net else "-"}</td><td></td></tr>')
    h.append("</table></div>")
    rules, tests = d["rules"], d["tests"]
    rule = (f"Minutes rule: a player with fewer than {rules['min_minutes']:g} minutes in 2025-26, including every rookie, "
            f"is rated {rules['replacement']:.1f} for every metric." if rules["min_minutes"] else
            f"Minutes rule: every player is rated at the metric's own value, and a player the metric does not rate is "
            f"{rules['replacement']:.1f}.")
    h.append('<p class="d">How to read it:</p><ul class="d">'
             f"<li>{escape(tests['margin_r2'])}. Higher is better.</li>"
             f"<li>{escape(tests['winpct_r'])}. Higher is better.</li>"
             f"<li>{escape(tests['net_rmse'])}. Lower is better.{'' if net else ' ' + escape(d['net_error_note']) + '.'}</li>"
             f"<li>Rank: the range of places a metric reaches across {d['resamples']:,} resamples of the games (the middle "
             f"{round(d['confidence'] * 100)}%). Metrics whose ranges overlap are not separated by the games played so far.</li>"
             f"<li>{rule}</li>"
             "<li>Italic rows are reference points and are not ranked: RAPM fit on these same games (an upper reference), "
             "the average of all metrics, last season's RAPM, and two floors.</li></ul>")
    h.append('<p class="d">Labels:</p><ul class="d">'
             + "".join(f"<li><b>{escape(k)}</b>: {escape(v)}</li>" for k, v in d["labels"].items()) + "</ul>")
    b = d["board"]
    h.append(f'<p class="d">Data: <a href="live/results/{b}.json">{b}.json</a>, <a href="live/results/{b}_games.csv">every '
             f'game</a>, <a href="live/results/{b}_history.csv">history</a>. Scored with eval.py v1.1.0 (sha256 '
             f'{d["harness_sha256"][:12]}...).</p>')
    return "\n".join(h)


def retro_table(d, title, note):
    rows = sorted(d["metrics"].items(), key=lambda kv: -kv[1]["all"]["margin_r2"]["value"])
    h = [f"<h3>{title}</h3>", f'<p class="d">{note}</p>', HEAD.format("")]
    for ref in (False, True):
        for k, v in rows:
            if v["baseline"] != ref:
                continue
            a = v["all"]
            h.append(f'<tr{" class=\"ref\"" if ref else ""}><td>{"" if ref else rk(a["margin_r2"]["rank"])}</td>'
                     f'<td class="l">{escape(NAMES.get(k, k))}</td><td>{f3(a["margin_r2"]["value"])}{iv(a["margin_r2"]["interval"])}</td>'
                     f'<td>{f3(a["winpct_r"]["value"])}</td><td>{a["net_rmse"]["value"]:.2f}</td></tr>')
    h.append("</table></div>")
    return "\n".join(h)


def section(tab, title, body):
    return f'<section class="board" data-tab="{tab}" id="{tab}-board">\n<h2>{title}</h2>\n{body}\n</section>'


def main():
    load = lambda p: json.loads(p.read_text(encoding="utf-8")) if p.exists() else None   # noqa: E731
    frozen, daily = load(RESULTS / "frozen.json"), load(RESULTS / "daily.json")
    est, full = load(REPO / "launch" / "established-players.json"), load(REPO / "launch" / "full-forecast.json")
    parts = [section("live", "2026-27 preseason board", live_board(frozen) if frozen else "<p>No games scored yet.</p>"),
             section("daily", "2026-27 dynamic board", live_board(daily) if daily else
                     "<p>No games are scored yet. The dynamic board uses each metric's ratings as published on the "
                     "morning of each game day, saved before that day's first game.</p>")]
    m = est["meta"]
    parts.append(section("retro", f"Retro: {m['seasons'][0]} to {m['seasons'][-1]}", "\n".join([
        f"<p>The retro tables score each season from {m['seasons'][0]} to {m['seasons'][-1]} ({m['games']:,} games, "
        f"{m['team_seasons']} team-seasons) with the ratings each metric had before that season (HIB v{m['version']}).</p>",
        "<p>The past ratings come from each metric's current model rather than from what it published at the time, so a "
        "model may fit seasons it was built on. The 2026-27 boards do not have that problem.</p>",
        retro_table(est, "Established players", "A player with fewer than 250 minutes the season before, including every rookie, is rated -2.0 for every metric."),
        retro_table(full, "Full forecast", "Every player is rated at the metric's own value."),
        '<p class="d">Method, sources and every file: the <a href="https://github.com/lumahoops/hoop-impact-bench#readme">'
        'README</a>.</p>'])))
    lead = ", ".join(f"{x['name']} {f3(x['tests']['margin_r2']['value'])}" for x in (frozen or {}).get("metrics", [])[:3])
    desc = ("Open benchmark for NBA impact metrics (EPM, DARKO, LEBRON, BPM, xRAPM, OpenRAPM, LOKI and more): each "
            "metric's saved ratings scored on 2026-27 games they never saw"
            + (f"; preseason board after {frozen['games']} games: {lead}" if frozen else "") + ".")
    page = (LIVE / "code" / "page.html").read_text(encoding="utf-8")
    page = page.replace("{{DESCRIPTION}}", escape(desc)).replace("{{BOARDS}}", "\n".join(parts))
    (REPO / "index.html").write_text(page, encoding="utf-8", newline="\n")
    print(f"index.html: preseason {frozen['games'] if frozen else 0} games, dynamic {daily['games'] if daily else 0} games, retro")


if __name__ == "__main__":
    main()
