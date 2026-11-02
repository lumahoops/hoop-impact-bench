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


def ivn(i):
    return f" <small>{i[0]:.2f}-{i[1]:.2f}</small>" if i else ""


def iv(i):
    return f" <small>{f3(i[0])}-{f3(i[1])}</small>" if i else ""


def day(iso):
    d = datetime.date.fromisoformat(iso[:10])
    return f"{d:%b} {d.day}"


def head(cols):
    """Table header; each column sorts on click (data-s: n = number, t = text; data-d: a = ascending first) and shows a
    one-line definition on hover."""
    return ('<div class="wide"><table class="sort"><thead><tr>'
            + "".join(f'<th data-s="{s}" data-d="{d}" title="{escape(TIPS.get(key, ""))}"'
                      f'{" class=\"l\"" if s == "t" else ""}>{label}</th>' for label, s, d, key in cols)
            + "</tr></thead>")


TIPS = {
    "rank": "Range of places on net error across 2,000 resamples of the games (middle 90%)",
    "metric": "The impact metric and its maker",
    "wl": "Games won by the team the metric rated higher (no home-court edge)",
    "r2": "Share of the variation in final margins that the predicted margins explain. Higher is better",
    "winpct": "Correlation between team ratings and team win %. Higher is better",
    "net": "Ranking test. Average miss vs. each team's opponent-adjusted margin, points per 100. Lower is better",
    "label": "Where the ratings came from; hover a label for its source",
}


def cols(wl_col, net_note, label_col):
    return ([("rank", "n", "a", "rank"), ("metric", "t", "a", "metric")] + ([("W-L", "n", "d", "wl")] if wl_col else [])
            + [(f"net error <small>90% range</small>{net_note}", "n", "a", "net"), ("game R²", "n", "d", "r2"),
               ("win % r", "n", "d", "winpct")]
            + ([("label", "t", "a", "label")] if label_col else []))


def td(text, v=None, cls=""):
    return f'<td{f" class={chr(34)}{cls}{chr(34)}" if cls else ""}{f" data-v={chr(34)}{v}{chr(34)}" if v is not None else ""}>{text}</td>'


def wl(m):
    r = m.get("record")
    return f"{r['w']}-{r['l']}" if r else ""


def drawer(body):
    return f'<details class="help"><summary>? What this table shows</summary>\n{body}\n</details>'


def summary(d):
    """One plain sentence: who leads on team net error, by how much, and how early it is."""
    m = d["metrics"]
    if not m:
        return ""
    lead, second = m[0], m[1] if len(m) > 1 else None
    s = (f"After {d['games']} games, {lead['name']} leads on team net error at {lead['tests']['net_rmse']['value']:.2f} "
         f"points per 100" + (f", ahead of {second['name']} at {second['tests']['net_rmse']['value']:.2f}" if second else "")
         + ".")
    return s + (" " + d["net_error_note"] if d.get("early") else "")


def live_board(d):
    net = d["net_error_shown"]
    ex = len(d["snapshot"].get("excluded_games") or [])
    h = [f'<p class="line">{LINE[d["board"]]}</p>',
         f'<p class="meta"><b>{d["games"]} games</b> · {day(d["first_game"])} to {day(d["scored_through"])} · updated '
         f'{day(d["updated_utc"])}, {d["updated_utc"][11:16]} UTC</p>',
         f'<p class="early">{escape(d["net_error_note"])}</p>' if d.get("early") else "",
         "{{DRAWER}}",
         head(cols(True, "", True)), '<tbody class="rk">']
    for m in d["metrics"]:
        t = m["tests"]
        name = f'<a href="{escape(m["url"])}">{escape(m["name"])}</a>' if m.get("url") else escape(m["name"])
        maker = "" if m["maker"] in m["name"] else f" <small>{escape(m['maker'])}</small>"
        r = t["net_rmse"].get("rank") or [0, 0]
        h.append(f'<tr id="m-{m["id"]}">' + td(rk(t["net_rmse"].get("rank")), r[0] + r[1] / 100)
                 + td(f'{name}{" †" if m["ours"] else ""}{maker}', escape(m["name"]), "l")
                 + td(wl(m), (m.get("record") or {}).get("w", ""))
                 + td(f'<b>{t["net_rmse"]["value"]:.2f}</b>{ivn(t["net_rmse"]["interval"])}', t["net_rmse"]["value"])
                 + td(f3(t["margin_r2"]["value"]), t["margin_r2"]["value"])
                 + td(f3(t["winpct_r"]["value"]), t["winpct_r"]["value"])
                 + f'<td class="l" title="{escape(m["source"])}">{escape(m["label"])}</td></tr>')
    h.append('</tbody><tbody class="refs">')
    for r in d["reference"]:
        t = r["tests"]
        h.append(f'<tr class="ref"><td></td><td class="l" title="{escape(r["description"])}">{escape(r["name"])}</td><td></td>'
                 f'<td>{t["net_rmse"]["value"]:.2f}{ivn(t["net_rmse"]["interval"])}</td><td>{f3(t["margin_r2"]["value"])}</td>'
                 f'<td>{f3(t["winpct_r"]["value"])}</td><td></td></tr>')
    h.append("</tbody>")
    h.append("</table></div>")

    rules, tests = d["rules"], d["tests"]
    rule = (f"A player with fewer than {rules['min_minutes']:g} minutes in 2025-26, including every rookie, is rated "
            f"{rules['replacement']:.1f} for every metric." if rules["min_minutes"] else
            f"Every player is rated at the metric's own value. A player the metric does not rate is "
            f"{rules['replacement']:.1f}.")
    b = d["board"]
    body = [f"<p><b>{escape(summary(d))}</b></p>", WHAT, f"<p>{escape(d['title'])}</p>"]
    if ex:
        body.append(f"<p>{ex} game{' is' if ex == 1 else 's are'} left out because {'it' if ex == 1 else 'they'} started "
                    "before that day's ratings were saved.</p>")
    body.append("<p><b>Columns</b></p><ul>"
                f"<li>{escape(tests['net_rmse'])}. Lower is better. This is the ranking test: it checks whether the players' "
                "ratings add up to the team's actual net rating, at face value. The small numbers are its 90% range.</li>"
                f"<li>{escape(tests['margin_r2'])}. Higher is better.</li>"
                f"<li>{escape(tests['winpct_r'])}. Higher is better.</li>"
                + (f"<li>{escape(d['record_note'])}.</li>" if d.get("record_note") else "") +
                f"<li>Rank: the range of places on net error a metric reaches across {d['resamples']:,} resamples of the games (the middle "
                f"{round(d['confidence'] * 100)}%). Metrics whose ranges overlap are not separated by the games so far.</li>"
                f"<li>Minutes rule: {rule}</li>"
                "<li>Italic rows are reference points and are not ranked: RAPM fit on these same games (an upper "
                "reference), the average of all metrics, last season's RAPM, and two floors.</li></ul>")
    body.append("<p><b>Labels</b></p><ul>" + "".join(f"<li>{escape(k)}: {escape(v)}</li>" for k, v in d["labels"].items())
                + "</ul>")
    body.append('<p>Sources for the tests: game margins and team net error follow <a href="https://dunksandthrees.com/blog/'
                'metric-comparison">Taylor Snarr\'s 2020 metric comparison</a>; team win % r is <a href="https://x.com/'
                'knarsu3/status/1763321501766627328">Krishna Narsu\'s 2024 test</a>; the 250-minute cutoff is <a href="'
                'https://www.apbr.org/metrics/viewtopic.php?f=2&amp;t=8196&amp;start=15#p15334">Neil Paine\'s</a>. Questions or '
                'errors: <a href="https://github.com/lumahoops/hoop-impact-bench/issues">open an issue</a>.</p>')
    body.append(f'<p>Data: <a href="live/results/{b}.json">{b}.json</a>, <a href="live/results/{b}_games.csv">every game</a>, '
                f'<a href="live/results/{b}_history.csv">history</a>. Computed with eval.py v1.1.0 (sha256 '
                f'{d["harness_sha256"][:12]}...). Rules: <a href="https://github.com/lumahoops/hoop-impact-bench/blob/main/'
                'live/PROTOCOL.md">live protocol</a>.</p>')
    return "\n".join(h).replace("{{DRAWER}}", drawer("\n".join(body)))


def retro_table(d, title, note):
    rows = sorted(d["metrics"].items(), key=lambda kv: kv[1]["all"]["net_rmse"]["value"])
    h = [f"<h3>{title}</h3>", f'<p class="meta">{note}</p>', head(cols(False, "", False))]
    for ref in (False, True):
        h.append('<tbody class="refs">' if ref else '<tbody class="rk">')
        for k, v in rows:
            if v["baseline"] != ref:
                continue
            a = v["all"]
            r = a["net_rmse"].get("rank") or [0, 0]
            h.append(f'<tr{" class=\"ref\"" if ref else ""}>'
                     + td("" if ref else rk(a["net_rmse"].get("rank")), None if ref else r[0] + r[1] / 100)
                     + td(escape(NAMES.get(k, k)), escape(NAMES.get(k, k)), "l")
                     + td(f'{"" if ref else "<b>"}{a["net_rmse"]["value"]:.2f}{"" if ref else "</b>"}{ivn(a["net_rmse"]["interval"])}',
                          a["net_rmse"]["value"])
                     + td(f3(a["margin_r2"]["value"]), a["margin_r2"]["value"])
                     + td(f3(a["winpct_r"]["value"]), a["winpct_r"]["value"]) + "</tr>")
        h.append("</tbody>")
    h.append("</table></div>")
    return "\n".join(h)


def retro(est, full):
    m = est["meta"]
    body = [WHAT,
            f"<p>The retro tables compute each season from {m['seasons'][0]} to {m['seasons'][-1]} ({m['games']:,} games, "
            f"{m['team_seasons']} team-seasons) using the ratings each metric had before that season (HIB v{m['version']}).</p>",
            "<p>The retro tables are a loose baseline for comparing metrics, not a conclusive ranking. HIB did not receive "
            "any of the past ratings before each season was played, so it cannot confirm that a metric's fitting held out the "
            "seasons it is scored on; how fully each one did varies (README, the metrics table). The 2026-27 boards are out of "
            "sample for every metric by construction: each rating is saved, and its fingerprint published, before the games "
            "it is scored on.</p>",
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
            "2026-27 games played after each metric's ratings were saved."
            + (f" {summary(frozen)}" if frozen else ""))
    page = (LIVE / "code" / "page.html").read_text(encoding="utf-8")
    card = "https://hoopimpactbench.org/live/results/card.png"
    if frozen:   # a new address each update, so link previews fetch the new card
        card += "?v=" + frozen["updated_utc"][:16].replace(":", "").replace("-", "")
    base = "https://hoopimpactbench.org/"
    files = [("live/results/frozen.json", "application/json"), ("live/results/frozen_picks.csv", "text/csv"),
             ("live/results/daily.json", "application/json"), ("live/results/daily_picks.csv", "text/csv"),
             ("launch/established-players.json", "application/json"), ("launch/full-forecast.json", "application/json")]
    dataset = {   # schema.org Dataset: tells search engines this page is the source of these numbers
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "Hoop Impact Bench: NBA impact metric leaderboards, 2026-27", "description": desc, "url": base,
        "sameAs": "https://github.com/lumahoops/hoop-impact-bench", "isAccessibleForFree": True,
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "creator": {"@type": "Organization", "name": "LUMA Basketball Research", "url": "https://lumahoops.org"},
        "keywords": ["NBA", "impact metrics", "EPM", "DARKO", "LEBRON", "BPM", "RAPM", "benchmark"],
        "temporalCoverage": "2020-10-01/..",
        "variableMeasured": ["game margin R\u00b2", "team win % correlation", "team net rating error", "W-L"],
        **({"dateModified": frozen["scored_through"]} if frozen else {}),   # changes only when new games are scored
        "version": "1.1.0",
        "measurementTechnique": "Each player's saved rating weighted by actual minutes gives a team rating per game; home minus "
                                "away is the predicted margin, compared with final margins (R\u00b2), team win % (r) and "
                                "opponent-adjusted team margins (net error).",
        "citation": "Snarr, T. (2020). Metric comparison. Dunks & Threes. https://dunksandthrees.com/blog/metric-comparison",
        "distribution": [{"@type": "DataDownload", "encodingFormat": f, "contentUrl": base + p} for p, f in files
                         if (REPO / p).exists()]}
    jsonld = '<script type="application/ld+json">' + json.dumps(dataset, ensure_ascii=False) + "</script>"
    page = page.replace("{{DESCRIPTION}}", escape(desc)).replace("{{CARD}}", card).replace("{{JSONLD}}", jsonld) \
        .replace("{{BOARDS}}", "\n".join(parts))
    (REPO / "index.html").write_text(page, encoding="utf-8", newline="\n")
    print(f"index.html: preseason {frozen['games'] if frozen else 0} games, dynamic {daily['games'] if daily else 0} games, retro")


if __name__ == "__main__":
    main()
