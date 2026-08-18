"""Génération du rapport HTML interactif (affiché dans l'application, imprimable en PDF)."""

import html
from datetime import date
from typing import Optional

from .stats import JOURS_ABBR, JOURS_SEMAINE, GridCell, ReportData, Summary, all_slots, slot_label

_MOIS = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def _fr_date(d: date) -> str:
    day_label = "1er" if d.day == 1 else str(d.day)
    return f"{day_label} {_MOIS[d.month - 1]} {d.year}"


def _fmt_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    m, s = divmod(seconds, 60)
    return f"{m} min {s:02d} s" if m else f"{s} s"


def _fmt_pct(value: float) -> str:
    return f"{value:.1f}".replace(".", ",") + " %"


def _fmt_num(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def _heat_color(count: int, max_count: int) -> str:
    if max_count <= 0 or count <= 0:
        return "#ffffff"
    ratio = count / max_count
    r1, g1, b1 = 0xF5, 0xF8, 0xFD
    r2, g2, b2 = 0x3F, 0xB2, 0xFF
    r = round(r1 + (r2 - r1) * ratio)
    g = round(g1 + (g2 - g1) * ratio)
    b = round(b1 + (b2 - b1) * ratio)
    return f"#{r:02x}{g:02x}{b:02x}"


def _text_color_for(bg_hex: str) -> str:
    r, g, b = int(bg_hex[1:3], 16), int(bg_hex[3:5], 16), int(bg_hex[5:7], 16)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#1a1a2e" if luminance > 0.55 else "#ffffff"


def _build_grid_table(data: ReportData) -> str:
    from .stats import slots_for_weekday

    slots = all_slots(data.granularity)
    max_count = max((cell.count for cell in data.grid.values()), default=0)
    valid_slots_by_weekday = {w: set(slots_for_weekday(w, data.granularity)) for w in range(6)}

    header_cells = ['<th class="corner sticky-col sticky-row">Créneau</th>', '<th class="total-col sticky-row">TOTAL</th>']
    for d in data.days:
        header_cells.append(f'<th class="sticky-row">{JOURS_ABBR[d.weekday()]}<br>{d.strftime("%d/%m")}</th>')
    header_row = f"<tr>{''.join(header_cells)}</tr>"

    total_row_cells = ['<th class="slot-label sticky-col">TOTAL</th>']
    total_row_cells.append(f'<td class="total-col total-cell">{data.grand_total.count}</td>')
    for d in data.days:
        cell = data.day_totals.get(d, GridCell())
        tooltip = html.escape(
            f"{JOURS_SEMAINE[d.weekday()]} {d.strftime('%d/%m/%Y')} — {cell.count} appel(s). "
            + (f"Durée moyenne : {_fmt_duration(cell.avg_comm)}" if cell.count else "Aucun appel")
        )
        total_row_cells.append(f'<td class="total-cell" title="{tooltip}">{cell.count if cell.count else ""}</td>')
    rows_html = [f'<tr class="total-row">{"".join(total_row_cells)}</tr>']

    for h, m in slots:
        label = slot_label(h, m, data.granularity)
        cells = [f'<th class="slot-label sticky-col">{label}</th>']

        slot_cell = data.slot_totals.get((h, m), GridCell())
        slot_tooltip = html.escape(
            f"Créneau {label} — {slot_cell.count} appel(s) sur la période. "
            + (f"Durée moyenne : {_fmt_duration(slot_cell.avg_comm)}" if slot_cell.count else "Aucun appel")
        )
        cells.append(
            f'<td class="total-col total-cell" title="{slot_tooltip}">{slot_cell.count if slot_cell.count else ""}</td>'
        )

        for d in data.days:
            weekday = d.weekday()
            if weekday == 6:
                cells.append('<td class="closed off-day">—</td>')
                continue
            if (h, m) not in valid_slots_by_weekday[weekday]:
                cells.append('<td class="closed">—</td>')
                continue
            cell = data.grid.get((d, (h, m)))
            count = cell.count if cell else 0
            bg = _heat_color(count, max_count)
            fg = _text_color_for(bg)
            avg = f"Durée moyenne : {_fmt_duration(cell.avg_comm)}" if cell and cell.count else "Aucun appel"
            tooltip = html.escape(f"{JOURS_SEMAINE[weekday]} {d.strftime('%d/%m/%Y')} {label} — {count} appel(s). {avg}")
            cells.append(
                f'<td class="cell" style="background:{bg};color:{fg}" title="{tooltip}">{count if count else ""}</td>'
            )
        rows_html.append(f"<tr>{''.join(cells)}</tr>")

    return (
        '<div class="table-scroll"><table class="day-grid-table">'
        f"<thead>{header_row}</thead><tbody>{''.join(rows_html)}</tbody></table></div>"
    )


def _build_tag_table(summary: Summary) -> str:
    header = "<tr>" + "".join(f"<th>{html.escape(t.label)}</th>" for t in summary.tag_breakdown) + "</tr>"
    count_row = "<tr>" + "".join(f'<td class="cell">{t.count}</td>' for t in summary.tag_breakdown) + "</tr>"
    pct_row = "<tr>" + "".join(f'<td class="total-cell">{_fmt_pct(t.pct)}</td>' for t in summary.tag_breakdown) + "</tr>"
    return f'<table class="traitement-table"><thead>{header}</thead><tbody>{count_row}{pct_row}</tbody></table>'


def _summary_stats_html(summary: Summary) -> str:
    ratio_stats = "".join(
        f'<div class="stat"><div class="value">{_fmt_pct(summary.ratios[m])}</div>'
        f'<div class="label">Appels &gt; {m} min</div></div>'
        for m in sorted(summary.ratios)
    )
    return f"""
    <div class="stat"><div class="value">{summary.total_calls}</div><div class="label">Appels entrants</div></div>
    <div class="stat"><div class="value">{_fmt_duration(summary.avg_comm_seconds)}</div><div class="label">Durée moyenne de traitement</div></div>
    <div class="stat"><div class="value">{_fmt_duration(summary.avg_wait_global_seconds)}</div><div class="label">Attente moyenne globale (annonce+file+sonnerie)</div></div>
    <div class="stat"><div class="value">{_fmt_duration(summary.avg_wait_sonnerie_seconds)}</div><div class="label">Attente moyenne sur sonnerie</div></div>
    {ratio_stats}
    <div class="stat"><div class="value">{_fmt_pct(summary.tag_rate_pct)}</div><div class="label">Taux de TAG (appels qualifiés)</div></div>
    """


def _comparison_section_html(current_label: str, current: Summary, compare_label: str, compare: Summary) -> str:
    def raw_delta_text(d: float, kind: str) -> str:
        sign = "+" if d >= 0 else ""
        if kind == "int":
            return f"{sign}{int(round(d))}"
        if kind == "duration":
            return f"{sign}{_fmt_duration(abs(d))}" if d >= 0 else f"-{_fmt_duration(abs(d))}"
        return f"{sign}{_fmt_num(d)} pt"  # écart en points, pour un taux déjà exprimé en %

    def delta(a: float, b: float, kind: str):
        """Écart affiché en pourcentage d'évolution par rapport à la valeur de comparaison,
        avec l'écart brut (dans son unité propre) visible au survol."""
        d = a - b
        cls = "up" if d > 0 else ("down" if d < 0 else "")
        tooltip = html.escape(f"Écart : {raw_delta_text(d, kind)}")
        if b == 0:
            text = "0,0 %" if a == 0 else "—"
        else:
            pct = d / b * 100
            sign = "+" if pct >= 0 else ""
            text = f"{sign}{_fmt_num(pct)} %"
        return f'<span class="delta {cls}" title="{tooltip}">{text}</span>'

    rows = [
        ("Appels entrants", current.total_calls, compare.total_calls, lambda x: str(int(x)), "int"),
        ("Durée moyenne de traitement", current.avg_comm_seconds, compare.avg_comm_seconds, _fmt_duration, "duration"),
        ("Attente moyenne globale", current.avg_wait_global_seconds, compare.avg_wait_global_seconds, _fmt_duration, "duration"),
        ("Attente moyenne sonnerie", current.avg_wait_sonnerie_seconds, compare.avg_wait_sonnerie_seconds, _fmt_duration, "duration"),
        ("Taux de TAG", current.tag_rate_pct, compare.tag_rate_pct, _fmt_pct, "pct"),
    ]
    for m in sorted(current.ratios):
        rows.append((f"Appels &gt; {m} min", current.ratios[m], compare.ratios[m], _fmt_pct, "pct"))

    body = ""
    for label, cur_val, cmp_val, fmt, kind in rows:
        body += (
            f"<tr><th>{label}</th><td>{fmt(cur_val)}</td><td>{fmt(cmp_val)}</td>"
            f"<td>{delta(cur_val, cmp_val, kind)}</td></tr>"
        )

    return f"""
    <h2>Comparaison — {html.escape(current_label)} vs {html.escape(compare_label)}</h2>
    <table class="compare-table">
      <thead><tr><th></th><th>{html.escape(current_label)}</th><th>{html.escape(compare_label)}</th><th>Écart</th></tr></thead>
      <tbody>{body}</tbody>
    </table>
    """


TEMPLATE = """<!doctype html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  :root {{
    --blue-dark: #002e99;
    --blue-light: #3fb2ff;
    --text: #1a1a2e;
    --text-muted: #5a5f73;
    --border: #e7ecf5;
    --bg-alt: #f5f8fd;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    padding: 32px;
    font-family: 'Montserrat', Arial, sans-serif;
    color: var(--text);
    background: #ffffff;
  }}
  h1 {{ font-size: 1.6rem; color: var(--blue-dark); margin: 0 0 4px; }}
  .subtitle {{ color: var(--text-muted); margin: 0 0 24px; }}
  .summary {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 32px; }}
  .summary .stat {{
    background: var(--bg-alt); border: 1px solid var(--border); border-radius: 12px;
    padding: 12px 20px; min-width: 160px;
  }}
  .summary .stat .value {{ font-size: 1.4rem; font-weight: 700; color: var(--blue-dark); }}
  .summary .stat .label {{ font-size: 0.85rem; color: var(--text-muted); }}
  h2 {{ font-size: 1.15rem; color: var(--blue-dark); margin: 32px 0 12px; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 8px; }}
  th, td {{ border: 1px solid var(--border); text-align: center; padding: 6px 4px; font-size: 0.82rem; white-space: nowrap; }}
  th {{ background: var(--bg-alt); color: var(--blue-dark); font-weight: 600; }}
  td.slot-label, th.slot-label {{ text-align: right; padding-right: 10px; }}
  td.closed {{ background: #fafafa; color: #ccc; }}
  td.cell {{ cursor: default; font-weight: 600; }}
  .note {{ color: var(--text-muted); font-size: 0.8rem; margin-top: 8px; }}
  .actions {{ margin: 24px 0; }}
  .actions button {{
    background: var(--blue-dark); color: #fff; border: none; border-radius: 8px;
    padding: 10px 18px; font-size: 0.9rem; cursor: pointer; margin-right: 8px;
  }}
  .table-scroll {{ overflow-x: auto; border: 1px solid var(--border); border-radius: 8px; width: 100%; }}
  .table-scroll table {{ width: 100%; min-width: max-content; margin-bottom: 0; border: none; }}
  table.day-grid-table th, table.day-grid-table td {{ font-size: 0.72rem; padding: 4px 6px; min-width: 34px; }}
  th.slot-label, td.total-col, th.total-col {{ width: 96px; min-width: 96px; }}
  th.sticky-col, td.total-col {{ position: sticky; background: var(--bg-alt); }}
  th.sticky-col {{ left: 0; z-index: 3; }}
  td.total-col, th.total-col {{ left: 96px; z-index: 2; }}
  th.sticky-row {{ position: sticky; top: 0; z-index: 4; }}
  th.corner {{ z-index: 5; left: 0; }}
  .total-cell {{ background: var(--bg-alt); font-weight: 700; }}
  .total-row th, .total-row td {{ background: #e9f0ff; font-weight: 700; }}
  th.off-day, td.off-day {{ background: #f0f0f0 !important; color: #bbb; }}
  table.compare-table td, table.compare-table th {{ white-space: normal; }}
  .delta {{ cursor: help; border-bottom: 1px dotted currentColor; }}
  .delta.up {{ color: #0a7a2f; }}
  .delta.down {{ color: #b3261e; }}

  @media print {{
    .actions {{ display: none; }}
    body {{ padding: 0; }}
    @page {{ size: A4 landscape; margin: 10mm; }}
    .table-scroll {{ overflow: visible; border: none; }}
    .table-scroll table {{ table-layout: fixed; width: 100%; min-width: 0; }}
    th.sticky-col, td.total-col, th.total-col, th.sticky-row, th.corner {{ position: static; }}
    table.day-grid-table th, table.day-grid-table td {{ font-size: 6.5pt; padding: 1px 2px; min-width: 0; overflow: hidden; }}
    table.day-grid-table th.slot-label, table.day-grid-table th.corner {{ width: 54px; white-space: normal; line-height: 1.15; }}
    table.day-grid-table td.total-col, table.day-grid-table th.total-col {{ width: 30px; }}
  }}
</style>
</head>
<body>
  <div class="actions"><button onclick="window.print()">Imprimer / Export PDF</button></div>
  <h1>{title}</h1>
  <p class="subtitle">Période analysée : du {start} au {end} — granularité {granularity} min</p>

  <div class="summary">
    {summary_stats}
  </div>

  <h2>Détail par créneau et par jour</h2>
  {grid_table}
  <p class="note">Survolez une case pour voir le détail. Lundi-vendredi 8h-20h, samedi 8h-12h, dimanche fermé.</p>

  <h2>Traitement des appels (par tag)</h2>
  {tag_table}
  <p class="note">Pourcentage sur le total d'appels de la période. Un appel peut porter plusieurs tags (ex : "RDV + MESS") et compter dans plusieurs catégories.</p>

  {comparison_section}
</body>
</html>
"""


def render_report(data: ReportData, comparison: Optional[tuple] = None) -> str:
    """`comparison`, si fourni, est un tuple (label, Summary) du mois choisi pour comparaison."""
    comparison_section = ""
    if comparison:
        compare_label, compare_summary = comparison
        current_label = f"{_fr_date(data.period_start)} – {_fr_date(data.period_end)}"
        comparison_section = _comparison_section_html(current_label, data.summary, compare_label, compare_summary)

    return TEMPLATE.format(
        title=html.escape(f"Analyse des appels — {data.label}"),
        start=_fr_date(data.period_start),
        end=_fr_date(data.period_end),
        granularity=data.granularity,
        summary_stats=_summary_stats_html(data.summary),
        grid_table=_build_grid_table(data),
        tag_table=_build_tag_table(data.summary),
        comparison_section=comparison_section,
    )


SYNTHESIS_TEMPLATE = """<!doctype html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  :root {{
    --blue-dark: #002e99;
    --text: #1a1a2e;
    --text-muted: #5a5f73;
    --border: #e7ecf5;
    --bg-alt: #f5f8fd;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; padding: 32px; font-family: 'Montserrat', Arial, sans-serif; color: var(--text); background: #fff; }}
  h1 {{ font-size: 1.4rem; color: var(--blue-dark); margin: 0 0 20px; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid var(--border); text-align: center; padding: 8px 10px; font-size: 0.85rem; }}
  th {{ background: var(--bg-alt); color: var(--blue-dark); font-weight: 600; }}
  .table-scroll {{ overflow-x: auto; border: 1px solid var(--border); border-radius: 8px; }}
  .table-scroll table {{ border: none; white-space: nowrap; }}
  td:first-child, th:first-child {{ text-align: left; font-weight: 600; }}
  tr:nth-child(even) td {{ background: var(--bg-alt); }}
  tr.total-row td {{ background: #e9f0ff; font-weight: 700; border-top: 2px solid var(--blue-dark); }}
  table.sortable th {{ cursor: pointer; user-select: none; white-space: nowrap; }}
  table.sortable th::after {{ content: "\\2195"; color: #b7c2da; margin-left: 4px; font-weight: 400; }}
  table.sortable th.sort-asc::after {{ content: "\\25B2"; color: var(--blue-dark); }}
  table.sortable th.sort-desc::after {{ content: "\\25BC"; color: var(--blue-dark); }}
  .note {{ color: var(--text-muted); font-size: 0.8rem; margin-top: 12px; }}
  .actions {{ margin: 0 0 24px; }}
  .actions button {{
    background: var(--blue-dark); color: #fff; border: none; border-radius: 8px;
    padding: 10px 18px; font-size: 0.9rem; cursor: pointer;
  }}
  @media print {{
    .actions {{ display: none; }}
    body {{ padding: 0; }}
    @page {{ size: A4 portrait; margin: 12mm; }}
    table.sortable th::after {{ content: ""; }}
  }}
</style>
</head>
<body>
  <div class="actions"><button onclick="window.print()">Imprimer / Export PDF</button></div>
  <h1>{title}</h1>
  {table}
  <p class="note">{note}</p>
  <script>
    (function() {{
      var table = document.querySelector("table.sortable");
      if (!table) return;
      var headers = table.querySelectorAll("thead th");
      var state = {{ col: -1, dir: 1 }};
      headers.forEach(function(th, colIndex) {{
        th.addEventListener("click", function() {{
          var tbody = table.querySelector("tbody");
          var totalRow = tbody.querySelector("tr.total-row");
          var rows = Array.prototype.filter.call(tbody.querySelectorAll("tr"), function(r) {{
            return !r.classList.contains("total-row");
          }});
          var dir = (state.col === colIndex) ? -state.dir : 1;
          state = {{ col: colIndex, dir: dir }};
          rows.sort(function(a, b) {{
            var av = a.children[colIndex].dataset.value;
            var bv = b.children[colIndex].dataset.value;
            var an = parseFloat(av), bn = parseFloat(bv);
            var cmp;
            if (!isNaN(an) && !isNaN(bn) && av !== "" && bv !== "") {{
              cmp = an - bn;
            }} else {{
              cmp = av.localeCompare(bv, "fr");
            }}
            return cmp * dir;
          }});
          rows.forEach(function(r) {{ tbody.appendChild(r); }});
          if (totalRow) tbody.appendChild(totalRow);
          headers.forEach(function(h) {{ h.classList.remove("sort-asc", "sort-desc"); }});
          th.classList.add(dir === 1 ? "sort-asc" : "sort-desc");
        }});
      }});
    }})();
  </script>
</body>
</html>
"""


def _build_summary_table(first_header: str, rows: list, total_row: Optional[tuple] = None) -> str:
    """`rows` : liste de (label, Summary) ou (label, Summary, clé_de_tri) si le libellé
    affiché ne doit pas servir tel quel au tri de la 1ère colonne (ex : "Août 2026" doit se
    trier chronologiquement, pas alphabétiquement). `total_row` (optionnel, même format) est
    affiché en dernière ligne, mise en évidence, et reste toujours en bas quel que soit le
    tri (voir le script de tri dans SYNTHESIS_TEMPLATE)."""
    sample = rows[0] if rows else total_row
    ratio_thresholds = sorted(sample[1].ratios) if sample else []
    header_cells = (
        f"<th>{html.escape(first_header)}</th><th>Appels</th><th>Durée moy.<br>traitement</th>"
        "<th>Attente<br>globale</th><th>Attente<br>sonnerie</th>"
        + "".join(f"<th>&gt; {m} min</th>" for m in ratio_thresholds)
        + "<th>Taux de<br>TAG</th>"
    )

    def _row_cells(label: str, summary: Summary, sort_key=None) -> str:
        first_value = html.escape(str(label if sort_key is None else sort_key))
        return (
            f'<td data-value="{first_value}">{html.escape(label)}</td>'
            f'<td data-value="{summary.total_calls}">{summary.total_calls}</td>'
            f'<td data-value="{summary.avg_comm_seconds}">{_fmt_duration(summary.avg_comm_seconds)}</td>'
            f'<td data-value="{summary.avg_wait_global_seconds}">{_fmt_duration(summary.avg_wait_global_seconds)}</td>'
            f'<td data-value="{summary.avg_wait_sonnerie_seconds}">{_fmt_duration(summary.avg_wait_sonnerie_seconds)}</td>'
            + "".join(
                f'<td data-value="{summary.ratios[m]}">{_fmt_pct(summary.ratios[m])}</td>' for m in ratio_thresholds
            )
            + f'<td data-value="{summary.tag_rate_pct}">{_fmt_pct(summary.tag_rate_pct)}</td>'
        )

    body_rows = [f"<tr>{_row_cells(*r)}</tr>" for r in rows]
    if total_row:
        body_rows.append(f'<tr class="total-row">{_row_cells(*total_row)}</tr>')

    return (
        '<table class="sortable">'
        f"<thead><tr>{header_cells}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"
    )


def render_monthly_synthesis(label: str, rows: list) -> str:
    """`rows` : liste de (ym:"YYYY-MM", Summary), triée par mois croissant."""
    formatted_rows = []
    for ym, summary in rows:
        year, month = ym.split("-")
        month_label = f"{_MOIS[int(month) - 1].capitalize()} {year}"
        formatted_rows.append((month_label, summary, int(year) * 100 + int(month)))

    return SYNTHESIS_TEMPLATE.format(
        title=html.escape(f"Synthèse mensuelle — {label}"),
        table=_build_summary_table("Mois", formatted_rows),
        note="Un mois sans appel pour cette sélection apparaît avec des totaux à zéro plutôt que d'être omis.",
    )


DIMENSION_COLUMN_LABELS = {"client": "Client", "operateur": "Opérateur", "code_affaire": "Code affaire"}
DIMENSION_PLURAL_LABELS = {
    "client": "tous les clients",
    "operateur": "tous les opérateurs",
    "code_affaire": "tous les codes affaire",
}


def render_dimension_breakdown(
    dimension: str, period_start: date, period_end: date, rows: list, total_summary: Summary
) -> str:
    """`rows` : liste de (label, Summary), une par valeur de la dimension ayant au moins un
    appel sur la période ; `total_summary` : résumé "Tous" sur la même période, affiché en
    ligne TOTAL."""
    period_label = f"du {_fr_date(period_start)} au {_fr_date(period_end)}"
    column_label = DIMENSION_COLUMN_LABELS.get(dimension, "Valeur")
    table_html = _build_summary_table(column_label, rows, total_row=("TOTAL", total_summary))

    return SYNTHESIS_TEMPLATE.format(
        title=html.escape(f"Comparaison — {DIMENSION_PLURAL_LABELS.get(dimension, dimension)} — {period_label}"),
        table=table_html,
        note="Triée par nombre d'appels décroissant. Seules les valeurs ayant au moins un appel sur la période sont affichées.",
    )


def render_long_term_comparison(label: str, rows: list) -> str:
    """Comparaison sur le long terme : un mois par colonne (voir
    stats.build_monthly_synthesis), un sous-ensemble d'indicateurs clés par ligne — pour
    garder le tableau lisible même avec de nombreux mois importés."""
    month_labels = []
    for ym, _ in rows:
        year, month = ym.split("-")
        month_labels.append(f"{_MOIS[int(month) - 1].capitalize()} {year}")

    header_cells = "<th>Indicateur</th>" + "".join(f"<th>{html.escape(m)}</th>" for m in month_labels)

    metric_rows = [
        ("Nombre d'appels", lambda s: str(s.total_calls)),
        ("Durée moyenne de traitement (DMT)", lambda s: _fmt_duration(s.avg_comm_seconds)),
        ("Appels > 3 min", lambda s: _fmt_pct(s.ratios.get(3, 0.0))),
        ("Appels > 6 min", lambda s: _fmt_pct(s.ratios.get(6, 0.0))),
        ("Taux de TAG", lambda s: _fmt_pct(s.tag_rate_pct)),
    ]
    body_rows = []
    for metric_label, fmt_fn in metric_rows:
        cells = "".join(f"<td>{fmt_fn(summary)}</td>" for _, summary in rows)
        body_rows.append(f"<tr><th>{html.escape(metric_label)}</th>{cells}</tr>")

    table_html = (
        '<div class="table-scroll"><table>'
        f"<thead><tr>{header_cells}</tr></thead><tbody>{''.join(body_rows)}</tbody></table></div>"
    )

    return SYNTHESIS_TEMPLATE.format(
        title=html.escape(f"Comparaison long terme — {label}"),
        table=table_html,
        note="Un mois sans appel pour cette sélection apparaît avec des totaux à zéro plutôt que d'être omis.",
    )
