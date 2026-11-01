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


HEAD = ('<div class="wide"><table><tr><th>rank</th><th class="l">metric</th><th>game margins R²</th>'
        '<th>team win % r</th><th>net error</th>{}</tr>')


def live_board(d):
    net = d["net_error_shown"]
    ex = len(d["snapshot"].get("excluded_games") or [])
    h = [f"<p>{escape(d['title'])}</p>",
         f"<p>{d['games']} games, {d['first_game']} to {d['scored_through']} · updated "
         f"{d['updated_utc'][:16].replace('T', ' ')} UTC"
         + (f" · {ex} game{'s' if ex != 1 else ''} left off (it tipped off before every metric's value for that day was "
            "saved)" if ex else "") + "</p>",
         HEAD.format('<th class="l">label</th>')]
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
    rules = d["rules"]
    rule = (f"Rule: under {rules['min_minutes']:g} minutes last season (rookies included) or not rated = "
            f"{rules['replacement']:g}." if rules["min_minutes"] else
            f"Rule: every player at the metric's own value; a player the metric does not rate = {rules['replacement']:g}.")
    h.append(f"<p class=\"d\">{rule} Rank is the range of places in the middle {round(d['confidence'] * 100)}% of "
             f"{d['resamples']} resamples: overlapping ranges are not separated yet."
             + ("" if net else f" Net error: {escape(d['net_error_note'])}.") + " Italic rows are references, not ranked.</p>")
    h.append("<p class=\"d\">Labels: " + "; ".join(f"<b>{escape(k)}</b> {escape(v)}" for k, v in d["labels"].items()) + ".</p>")
    b = d["board"]
    h.append(f'<p class="d">Files: <a href="live/results/{b}.json">{b}.json</a>, <a href="live/results/{b}_games.csv">per '
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
                     "<p>Dynamic board: no games scored yet. Each game is scored with each metric's rating exactly as "
                     "published that morning, saved before tip-off. The first scores appear the morning after the first "
                     "such game.</p>")]
    m = est["meta"]
    parts.append(section("retro", f"Retro: {m['seasons'][0]} to {m['seasons'][-1]}", "\n".join([
        f"<p>Each season's preseason ratings, scored on that season's games: {m['games']:,} games, {m['team_seasons']} "
        f"team-seasons, {m['seasons'][0]} to {m['seasons'][-1]}. HIB v{m['version']}.</p>",
        retro_table(est, "Established players", "Under 250 minutes the season before, rookies included: -2.0 for every metric."),
        retro_table(full, "Full forecast", "Every player at the metric's own rating."),
        '<p class="d">Past seasons are the values each site shows today (its current model), not archived as published, so '
        'the live track is the stricter test. See the <a href="https://github.com/lumahoops/hoop-impact-bench#readme">README</a>.</p>'])))
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
