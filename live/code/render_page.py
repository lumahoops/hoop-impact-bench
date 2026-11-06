"""Write the GitHub Pages site (index.html at the repo root) with every board already in the HTML.

  python live/code/render_page.py

Reads live/results/ (both views of each board: frozen_full.json + frozen.json, daily.json + daily_established.json) and
launch/*.json; fills live/code/page.html. Each board is a table with one line above it; the explanation sits in a drawer
(a <details> element, so it is in the HTML for search engines and opens without JavaScript). The view switch (Full
forecast, the default / Established players; owner 2026-11-06) is two radio buttons and CSS, so it works without
JavaScript too; both tables are in the HTML. JavaScript only switches tabs, sorts columns and sets the colour theme.
Run by the VPS job after publish.py, and committed with the results. Wording is the assistant's, for the owner to edit.
"""
import datetime
import json
from html import escape

from paths import LIVE, REPO, RESULTS, VIEW_NAMES, VIEWS

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
NET = "net_rmse_centered"   # the ranking test (owner 2026-11-06)
ORDER = ["full", "established"]   # the switch: the default first
VIEW_NOTE = {   # the line under the switch
    "full": "Every player counts at the metric's own rating, rookies and low-minute players included. A player the "
            "metric does not rate counts as -2.0.",
    "established": "A player with fewer than 250 minutes the season before, including every rookie, counts as -2.0 for "
                   "every metric (Taylor Snarr's 2020 rule), and so does a player the metric does not rate.",
}
DEFS = [   # the drawer's definitions, each starting with the term it defines
    ("Net error", "the average miss, in points per 100 possessions, between each team's rating and its opponent-adjusted "
                  "margin, after each metric's team ratings are shifted so its average team is 0 (the adjusted margins "
                  "average 0). Lower is better. This is the ranking test: it checks whether the players' ratings add up "
                  "to the teams' results. The small numbers are its 90% range."),
    ("Raw", "the same miss at face value, before the shift. Hover a raw number for the metric's offset, its average team "
            "rating: raw² = net error² + offset². The shift is one number per metric, computed from the ratings and "
            "minutes only, never from the results."),
    ("Game R²", "the share of the variation in final game margins that the predicted margins explain. Higher is better."),
    ("Win % r", "the correlation between team ratings and team winning percentage. Higher is better."),
]


def f3(x):
    return "" if x is None else (f"{x:.3f}".replace("0.", ".", 1) if 0 <= x < 1 else f"{x:.3f}".replace("-0.", "-.", 1)
                                 if -1 < x < 0 else f"{x:.3f}")


def rk(r):
    return "" if not r else str(r[0]) if r[0] == r[1] else f"{r[0]}-{r[1]}"


def ivn(i):
    return f" <small>{i[0]:.2f}-{i[1]:.2f}</small>" if i else ""


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
    "net": "Ranking test. Average miss vs. each team's opponent-adjusted margin, points per 100, with each metric's "
           "average team set to 0. Lower is better",
    "raw": "Net error at face value, before the shift. Hover a number for the metric's offset (its average team rating)",
    "label": "Where the ratings came from; hover a label for its source",
}


def cols(wl_col, label_col):
    return ([("rank", "n", "a", "rank"), ("metric", "t", "a", "metric")] + ([("W-L", "n", "d", "wl")] if wl_col else [])
            + [("net error <small>90% range</small>", "n", "a", "net"), ("raw", "n", "a", "raw"),
               ("game R²", "n", "d", "r2"), ("win % r", "n", "d", "winpct")]
            + ([("label", "t", "a", "label")] if label_col else []))


def td(text, v=None, cls="", title=None):
    return (f'<td{f" class={chr(34)}{cls}{chr(34)}" if cls else ""}{f" data-v={chr(34)}{v}{chr(34)}" if v is not None else ""}'
            f'{f" title={chr(34)}{escape(title)}{chr(34)}" if title else ""}>{text}</td>')


def net_cells(t, offset, bold=True):
    """The ranked net error (centered) with its range, then raw with the offset on hover."""
    c, r = t[NET], t["net_rmse"]
    return (td(f'{"<b>" if bold else ""}{c["value"]:.2f}{"</b>" if bold else ""}{ivn(c["interval"])}', c["value"])
            + td(f'{r["value"]:.2f}', r["value"], title=f"offset {offset:+.2f}: the metric's average team rating"))


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
    s = (f"After {d['games']} games, {lead['name']} leads on team net error at {lead['tests'][NET]['value']:.2f} "
         f"points per 100" + (f", ahead of {second['name']} at {second['tests'][NET]['value']:.2f}" if second else "")
         + ".")
    return s + (" " + d["net_error_note"] if d.get("early") else "")


def switch(group, tables):
    """Radio buttons + CSS: the first view is checked (the default); without JavaScript the switch still works."""
    h = ['<div class="views">']
    for i, (view, _) in enumerate(tables):
        h.append(f'<input type="radio" name="v-{group}" id="v-{group}-{view}"{" checked" if i == 0 else ""}>'
                 f'<label for="v-{group}-{view}">{VIEW_NAMES[view]}</label>')
    for view, html in tables:
        h.append(f'<div class="view v-{view}">\n<p class="rule">{escape(VIEW_NOTE[view])}</p>\n{html}\n</div>')
    h.append("</div>")
    return "\n".join(h)


def live_table(d, default):
    h = [head(cols(True, True)), '<tbody class="rk">']
    for m in d["metrics"]:
        t = m["tests"]
        name = f'<a href="{escape(m["url"])}">{escape(m["name"])}</a>' if m.get("url") else escape(m["name"])
        maker = "" if m["maker"] in m["name"] else f" <small>{escape(m['maker'])}</small>"
        r = t[NET].get("rank") or [0, 0]
        row_id = f' id="m-{m["id"]}"' if default else ""      # anchors (#m-xpm) point at the default view
        h.append(f"<tr{row_id}>"
                 + td(rk(t[NET].get("rank")), r[0] + r[1] / 100)
                 + td(f'{name}{" †" if m["ours"] else ""}{maker}', escape(m["name"]), "l")
                 + td(wl(m), (m.get("record") or {}).get("w", ""))
                 + net_cells(t, m["offset"])
                 + td(f3(t["margin_r2"]["value"]), t["margin_r2"]["value"])
                 + td(f3(t["winpct_r"]["value"]), t["winpct_r"]["value"])
                 + f'<td class="l" title="{escape(m["source"] or "")}">{escape(m["label"])}</td></tr>')
    h.append('</tbody><tbody class="refs">')
    for r in d["reference"]:
        t = r["tests"]
        h.append(f'<tr class="ref"><td></td><td class="l" title="{escape(r["description"])}">{escape(r["name"])}</td><td></td>'
                 + net_cells(t, r["offset"], bold=False)
                 + f'<td>{f3(t["margin_r2"]["value"])}</td><td>{f3(t["winpct_r"]["value"])}</td><td></td></tr>')
    h.append("</tbody></table></div>")
    return "\n".join(h)


def live_board(docs):
    """docs = {view: board document}; the default view leads the page and the summary."""
    views = [v for v in ORDER if docs.get(v)]
    d = docs[views[0]]
    ex = len(d["snapshot"].get("excluded_games") or [])
    tables = [(v, live_table(docs[v], i == 0)) for i, v in enumerate(views)]
    h = [f'<p class="line">{LINE[d["board"]]}</p>',
         f'<p class="meta"><b>{d["games"]} games</b> · {day(d["first_game"])} to {day(d["scored_through"])} · updated '
         f'{day(d["updated_utc"])}, {d["updated_utc"][11:16]} UTC</p>',
         f'<p class="early">{escape(d["net_error_note"])}</p>' if d.get("early") else "",
         "{{DRAWER}}", switch(d["board"], tables)]

    body = [f"<p><b>{escape(summary(d))}</b></p>", WHAT, f"<p>{escape(d['title'])}</p>"]
    if ex:
        body.append(f"<p>{ex} game{' is' if ex == 1 else 's are'} left out because {'it' if ex == 1 else 'they'} started "
                    "before that day's ratings were saved.</p>")
    body.append("<p><b>Columns</b></p><ul>"
                + "".join(f"<li>{term}: {escape(text)}</li>" for term, text in DEFS)
                + (f"<li>W-L: {escape(d['record_note'][5:] if d['record_note'].startswith('W-L: ') else d['record_note'])}.</li>"
                   if d.get("record_note") else "")
                + f"<li>Rank: the range of places on net error a metric reaches across {d['resamples']:,} resamples of the "
                f"games (the middle {round(d['confidence'] * 100)}%). Metrics whose ranges overlap are not separated by the "
                "games so far.</li>"
                "<li>Italic rows: reference points, not ranked. RAPM fit on these same games (an upper reference), the "
                "average of all metrics, last season's RAPM, and two floors.</li></ul>")
    body.append("<p><b>Views</b></p><ul>"
                + "".join(f"<li>{VIEW_NAMES[v]}{' (the default)' if i == 0 else ''}: {escape(VIEW_NOTE[v])}</li>"
                          for i, v in enumerate(ORDER))
                + "</ul>")
    body.append("<p><b>Labels</b></p><ul>" + "".join(f"<li>{escape(k)}: {escape(v)}</li>" for k, v in d["labels"].items())
                + "</ul>")
    body.append('<p>Sources for the tests: game margins and team net error follow <a href="https://dunksandthrees.com/blog/'
                'metric-comparison">Taylor Snarr\'s 2020 metric comparison</a>; team win % r is <a href="https://x.com/'
                'knarsu3/status/1763321501766627328">Krishna Narsu\'s 2024 test</a>; the 250-minute cutoff is <a href="'
                'https://www.apbr.org/metrics/viewtopic.php?f=2&amp;t=8196&amp;start=15#p15334">Neil Paine\'s</a>. Questions or '
                'errors: <a href="https://github.com/lumahoops/hoop-impact-bench/issues">open an issue</a>.</p>')
    links = []
    for v in views:
        stem = VIEWS[d["board"]][v][0]
        links.append(f'{VIEW_NAMES[v]}: <a href="live/results/{stem}.json">{stem}.json</a>, '
                     f'<a href="live/results/{stem}_games.csv">every game</a>, <a href="live/results/{stem}_history.csv">history</a>')
    body.append(f'<p>Data. {"; ".join(links)}. Computed with eval.py v1.1.0 (sha256 {d["harness_sha256"][:12]}...), '
                'net error centered by live/code/centered.py. Rules: <a href="https://github.com/lumahoops/hoop-impact-bench/'
                'blob/main/live/PROTOCOL.md">live protocol</a>.</p>')
    return "\n".join(h).replace("{{DRAWER}}", drawer("\n".join(body)))


def retro_table(d):
    rows = sorted(d["metrics"].items(), key=lambda kv: kv[1]["all"][NET]["value"])
    h = [head(cols(False, False))]
    for ref in (False, True):
        h.append('<tbody class="refs">' if ref else '<tbody class="rk">')
        for k, v in rows:
            if v["baseline"] != ref:
                continue
            a = v["all"]
            r = a[NET].get("rank") or [0, 0]
            h.append(f'<tr{" class=\"ref\"" if ref else ""}>'
                     + td("" if ref else rk(a[NET].get("rank")), None if ref else r[0] + r[1] / 100)
                     + td(escape(NAMES.get(k, k)), escape(NAMES.get(k, k)), "l")
                     + net_cells(a, v["offset"], bold=not ref)
                     + td(f3(a["margin_r2"]["value"]), a["margin_r2"]["value"])
                     + td(f3(a["winpct_r"]["value"]), a["winpct_r"]["value"]) + "</tr>")
        h.append("</tbody>")
    h.append("</table></div>")
    return "\n".join(h)


def retro(est, full):
    m = full["meta"]
    body = [WHAT,
            f"<p>The retro tables compute each season from {m['seasons'][0]} to {m['seasons'][-1]} ({m['games']:,} games, "
            f"{m['team_seasons']} team-seasons) using the ratings each metric had before that season (HIB v{m['version']}).</p>",
            "<p>The retro tables are a loose baseline for comparing metrics, not a conclusive ranking. HIB did not receive "
            "any of the past ratings before each season was played, so it cannot confirm that a metric's fitting held out the "
            "seasons it is scored on; how fully each one did varies (README, the metrics table). The 2026-27 boards are out of "
            "sample for every metric by construction: each rating is saved, and its fingerprint published, before the games "
            "it is scored on.</p>",
            "<p><b>Columns</b></p><ul>" + "".join(f"<li>{term}: {escape(text)}</li>" for term, text in DEFS)
            + "<li>Rank: the range of places on net error across 2,000 resamples of team-seasons (the middle 90%).</li>"
            "<li>Italic rows: reference points, not ranked.</li></ul>",
            "<p><b>Views</b></p><ul>" + "".join(f"<li>{VIEW_NAMES[v]}{' (the default)' if i == 0 else ''}: "
                                                f"{escape(VIEW_NOTE[v])}</li>" for i, v in enumerate(ORDER)) + "</ul>",
            '<p>Method, sources and every file: the <a href="https://github.com/lumahoops/hoop-impact-bench#readme">README'
            '</a> and <a href="https://github.com/lumahoops/hoop-impact-bench/blob/main/launch/provenance.csv">provenance'
            '</a>.</p>']
    return "\n".join([
        f'<p class="line">{m["seasons"][0]} to {m["seasons"][-1]}, computed using the ratings each metric had before '
        f'each season.</p>',
        f'<p class="meta"><b>{m["games"]:,} games</b> · {m["team_seasons"]} team-seasons</p>',
        drawer("\n".join(body)),
        switch("retro", [("full", retro_table(full)), ("established", retro_table(est))])])


def section(tab, title, body):
    return f'<section class="board" data-tab="{tab}" id="{tab}-board">\n<h2>{title}</h2>\n{body}\n</section>'


def main():
    load = lambda p: json.loads(p.read_text(encoding="utf-8")) if p.exists() else None   # noqa: E731
    boards = {b: {v: load(RESULTS / f"{stem}.json") for v, (stem, _) in VIEWS[b].items()} for b in VIEWS}
    frozen, daily = boards["frozen"]["full"] or boards["frozen"]["established"], boards["daily"]["full"]
    est, full = load(REPO / "launch" / "established-players.json"), load(REPO / "launch" / "full-forecast.json")
    empty = lambda b: f'<p class="line">{LINE[b]}</p><p class="meta">No games yet.</p>' + drawer(WHAT)   # noqa: E731
    parts = [section("live", "2026-27 preseason", live_board(boards["frozen"]) if frozen else empty("frozen")),
             section("daily", "2026-27 dynamic", live_board(boards["daily"]) if daily else empty("daily")),
             section("retro", f"Retro {full['meta']['seasons'][0]} to {full['meta']['seasons'][-1]}", retro(est, full))]
    desc = ("Open benchmark for NBA impact metrics (EPM, DARKO, LEBRON, BPM, xRAPM, OpenRAPM, LOKI and more), computed on "
            "2026-27 games played after each metric's ratings were saved."
            + (f" {summary(frozen)}" if frozen else ""))
    page = (LIVE / "code" / "page.html").read_text(encoding="utf-8")
    card = "https://hoopimpactbench.org/live/results/card.png"
    if frozen:   # a new address each update, so link previews fetch the new card
        card += "?v=" + frozen["updated_utc"][:16].replace(":", "").replace("-", "")
    base = "https://hoopimpactbench.org/"
    files = [(f"live/results/{stem}{ext}", kind) for b in VIEWS for _, (stem, _) in VIEWS[b].items()
             for ext, kind in ((".json", "application/json"), ("_picks.csv", "text/csv"))] \
        + [("launch/full-forecast.json", "application/json"), ("launch/established-players.json", "application/json")]
    dataset = {   # schema.org Dataset: tells search engines this page is the source of these numbers
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "Hoop Impact Bench: NBA impact metric leaderboards, 2026-27", "description": desc, "url": base,
        "sameAs": "https://github.com/lumahoops/hoop-impact-bench", "isAccessibleForFree": True,
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "creator": {"@type": "Organization", "name": "LUMA Basketball Research", "url": "https://lumahoops.org"},
        "keywords": ["NBA", "impact metrics", "EPM", "DARKO", "LEBRON", "BPM", "RAPM", "benchmark"],
        "temporalCoverage": "2020-10-01/..",
        "variableMeasured": ["team net rating error (centered)", "game margin R\u00b2", "team win % correlation", "W-L"],
        **({"dateModified": frozen["scored_through"]} if frozen else {}),   # changes only when new games are scored
        "version": full["meta"]["version"],
        "measurementTechnique": "Each player's saved rating weighted by actual minutes gives a team rating per game; home minus "
                                "away is the predicted margin, compared with final margins (R\u00b2), team win % (r) and "
                                "opponent-adjusted team margins (net error, with each metric's average team set to 0).",
        "citation": "Snarr, T. (2020). Metric comparison. Dunks & Threes. https://dunksandthrees.com/blog/metric-comparison",
        "distribution": [{"@type": "DataDownload", "encodingFormat": f, "contentUrl": base + p} for p, f in files
                         if (REPO / p).exists()]}
    jsonld = '<script type="application/ld+json">' + json.dumps(dataset, ensure_ascii=False) + "</script>"
    page = page.replace("{{DESCRIPTION}}", escape(desc)).replace("{{CARD}}", card).replace("{{JSONLD}}", jsonld) \
        .replace("{{BOARDS}}", "\n".join(parts))
    (REPO / "index.html").write_text(page, encoding="utf-8", newline="\n")
    print(f"index.html: preseason {frozen['games'] if frozen else 0} games, dynamic {daily['games'] if daily else 0} games, "
          f"retro; views {', '.join(ORDER)}")


if __name__ == "__main__":
    main()
