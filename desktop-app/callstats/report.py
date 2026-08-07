"""Génération du rapport HTML autonome (interactif à l'écran, imprimable en PDF)."""

import html
from datetime import date

from . import holidays
from .stats import (
    JOURS_SEMAINE,
    SEUIL_1_SECONDES,
    SEUIL_2_SECONDES,
    SLOTS_SAMEDI,
    SLOTS_SEMAINE,
    TRANCHES,
    GridCell,
    ReportData,
)

_MOIS = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]
_JOURS_ABBR = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]


def _fr_date(d: date) -> str:
    day_label = "1er" if d.day == 1 else str(d.day)
    return f"{day_label} {_MOIS[d.month - 1]} {d.year}"


def _fmt_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    m, s = divmod(seconds, 60)
    return f"{m} min {s:02d} s" if m else f"{s} s"


def _fmt_hms(seconds: float) -> str:
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _fmt_pct(value: float) -> str:
    return f"{value:.1f}".replace(".", ",") + " %"


def _heat_color(count: int, max_count: int) -> str:
    if max_count <= 0 or count <= 0:
        return "#ffffff"
    ratio = count / max_count
    # Interpolation entre bg-alt (#f5f8fd) et blue-light (#3fb2ff)
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


def _off_day_label(d: date) -> str:
    """Raison pour laquelle le jour est grisé (dimanche / jour férié), ou chaîne vide si ouvré."""
    ferie = holidays.jour_ferie_label(d)
    if ferie:
        return ferie
    if d.weekday() == 6:
        return "Dimanche"
    return ""


def _build_day_grid_table(data: ReportData) -> str:
    max_count = max((cell.count for cell in data.day_grid.values()), default=0)

    header_cells = ['<th class="corner sticky-col sticky-row">Créneau</th>', '<th class="total-col sticky-row">TOTAL</th>']
    for d in data.days:
        off_label = _off_day_label(d)
        cls = "off-day sticky-row" if off_label else "sticky-row"
        title_attr = f' title="{html.escape(off_label)}"' if off_label else ""
        header_cells.append(
            f'<th class="{cls}"{title_attr}>{_JOURS_ABBR[d.weekday()]}<br>{d.strftime("%d/%m")}</th>'
        )
    header_row = f"<tr>{''.join(header_cells)}</tr>"

    total_row_cells = ['<th class="slot-label sticky-col">TOTAL</th>']
    total_row_cells.append(f'<td class="total-col total-cell">{data.total_calls}</td>')
    for d in data.days:
        if _off_day_label(d):
            total_row_cells.append('<td class="closed off-day">—</td>')
            continue
        cell = data.day_totals.get(d, GridCell())
        tooltip = html.escape(
            f"{JOURS_SEMAINE[d.weekday()]} {d.strftime('%d/%m/%Y')} — {cell.count} appel(s). "
            + (f"Durée moyenne : {_fmt_duration(cell.avg_seconds)}" if cell.count else "Aucun appel")
        )
        total_row_cells.append(f'<td class="total-cell" title="{tooltip}">{cell.count if cell.count else ""}</td>')
    rows_html = [f'<tr class="total-row">{"".join(total_row_cells)}</tr>']

    for h, m in SLOTS_SEMAINE:
        end_h, end_m = (h, m + 30) if m == 0 else (h + 1, 0)
        label = f"{h:02d}h{m:02d}-{end_h:02d}h{end_m:02d}"
        cells = [f'<th class="slot-label sticky-col">{label}</th>']

        slot_cell = data.slot_totals.get((h, m), GridCell())
        slot_tooltip = html.escape(
            f"Créneau {label} — {slot_cell.count} appel(s) sur la période. "
            + (f"Durée moyenne : {_fmt_duration(slot_cell.avg_seconds)}" if slot_cell.count else "Aucun appel")
        )
        cells.append(
            f'<td class="total-col total-cell" title="{slot_tooltip}">{slot_cell.count if slot_cell.count else ""}</td>'
        )

        for d in data.days:
            weekday = d.weekday()
            if _off_day_label(d):
                cells.append('<td class="closed off-day">—</td>')
                continue
            valid_slots = SLOTS_SAMEDI if weekday == 5 else SLOTS_SEMAINE
            if (h, m) not in valid_slots:
                cells.append('<td class="closed">—</td>')
                continue
            cell = data.day_grid.get((d, (h, m)))
            count = cell.count if cell else 0
            bg = _heat_color(count, max_count)
            fg = _text_color_for(bg)
            avg = f"Durée moyenne : {_fmt_duration(cell.avg_seconds)}" if cell and cell.count else "Aucun appel"
            tooltip = html.escape(f"{JOURS_SEMAINE[weekday]} {d.strftime('%d/%m/%Y')} {label} — {count} appel(s). {avg}")
            cells.append(
                f'<td class="cell" style="background:{bg};color:{fg}" title="{tooltip}">'
                f'{count if count else ""}</td>'
            )
        rows_html.append(f"<tr>{''.join(cells)}</tr>")

    return (
        '<div class="table-scroll"><table class="day-grid-table">'
        f"<thead>{header_row}</thead><tbody>{''.join(rows_html)}</tbody></table></div>"
    )


def _build_recap_table(data: ReportData) -> str:
    grand_total = data.total_calls
    max_count = max((c.count for c in data.weekday_recap.values()), default=0)

    header = "<tr><th></th>" + "".join(f"<th>{d}</th>" for d in JOURS_SEMAINE) + "<th>TOTAL</th></tr>"

    rows_html = []
    for label, _, _ in TRANCHES:
        cells = [f'<th class="slot-label">{label}</th>']
        tranche_total = 0
        for weekday in range(6):
            cell = data.weekday_recap.get((weekday, label), GridCell())
            tranche_total += cell.count
            bg = _heat_color(cell.count, max_count)
            fg = _text_color_for(bg)
            pct = (cell.count / grand_total * 100) if grand_total else 0
            avg = f" — durée moyenne : {_fmt_duration(cell.avg_seconds)}" if cell.count else ""
            tooltip = html.escape(f"{JOURS_SEMAINE[weekday]} {label} — {cell.count} appel(s), {_fmt_pct(pct)} du total{avg}")
            cells.append(f'<td class="cell" style="background:{bg};color:{fg}" title="{tooltip}">{cell.count if cell.count else ""}</td>')
        pct_total = (tranche_total / grand_total * 100) if grand_total else 0
        cells.append(f'<td class="total-cell" title="{html.escape(f"{_fmt_pct(pct_total)} du total")}">{tranche_total}</td>')
        rows_html.append(f"<tr>{''.join(cells)}</tr>")

    # Ligne TOTAL
    total_cells = ['<th class="slot-label">TOTAL</th>']
    for weekday in range(6):
        cell = data.weekday_totals.get(weekday, GridCell())
        pct = (cell.count / grand_total * 100) if grand_total else 0
        tooltip = html.escape(f"{JOURS_SEMAINE[weekday]} — {cell.count} appel(s), {_fmt_pct(pct)} du total")
        total_cells.append(f'<td class="total-cell" title="{tooltip}">{cell.count}</td>')
    total_cells.append(f'<td class="total-cell grand-total">{grand_total}</td>')
    rows_html.append(f'<tr class="total-row">{"".join(total_cells)}</tr>')

    # Ligne NB Jours avec appels
    jours_cells = ['<th class="slot-label">NB jours avec appels</th>']
    for weekday in range(6):
        n = data.weekday_days_with_calls.get(weekday, 0)
        if weekday == 5:  # samedi affiché entre parenthèses, exclu du total
            jours_cells.append(f'<td class="muted">({n})</td>')
        else:
            jours_cells.append(f"<td>{n}</td>")
    total_jours = sum(data.weekday_days_with_calls.get(w, 0) for w in range(5))
    jours_cells.append(f'<td class="total-cell">{total_jours}</td>')
    rows_html.append(f"<tr>{''.join(jours_cells)}</tr>")

    # Ligne MOYENNE (appels / jour avec appels)
    moy_cells = ['<th class="slot-label">Moyenne / jour</th>']
    for weekday in range(6):
        n = data.weekday_days_with_calls.get(weekday, 0)
        total = data.weekday_totals.get(weekday, GridCell()).count
        moy = f"{total / n:.1f}".replace(".", ",") if n else "—"
        moy_cells.append(f"<td>{moy}</td>")
    moy_cells.append('<td class="total-cell">—</td>')
    rows_html.append(f"<tr>{''.join(moy_cells)}</tr>")

    return (
        '<div class="table-scroll"><table class="recap-table">'
        f"<thead>{header}</thead><tbody>{''.join(rows_html)}</tbody></table></div>"
    )


def _build_traitement_table(data: ReportData) -> str:
    header = "<tr>" + "".join(f"<th>{html.escape(t.label)}</th>" for t in data.traitement) + "</tr>"
    count_row = "<tr>" + "".join(f'<td class="cell">{t.count}</td>' for t in data.traitement) + "</tr>"
    pct_row = "<tr>" + "".join(f'<td class="total-cell">{_fmt_pct(t.pct)}</td>' for t in data.traitement) + "</tr>"
    return f'<table class="traitement-table"><thead>{header}</thead><tbody>{count_row}{pct_row}</tbody></table>'


def _build_subdivision_table(data: ReportData) -> str:
    sub = data.subdivision
    header = "<tr>" + "".join(
        f'<th>Attribution/report de RDV<br>Dr {html.escape(nom.title())}</th>' for nom in sub.names
    ) + "</tr>"
    count_row = "<tr>" + "".join(f'<td class="cell">{c}</td>' for c in sub.counts) + "</tr>"
    pct_row = "<tr>" + "".join(f'<td class="total-cell">{_fmt_pct(p)}</td>' for p in sub.pcts) + "</tr>"
    return f'<table class="traitement-table"><thead>{header}</thead><tbody>{count_row}{pct_row}</tbody></table>'


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
  .summary {{
    display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 32px;
  }}
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
  td.muted {{ color: var(--text-muted); }}
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
  th.sticky-col, td.total-col {{
    position: sticky; background: var(--bg-alt);
  }}
  th.sticky-col {{ left: 0; z-index: 3; }}
  td.total-col, th.total-col {{ left: 96px; z-index: 2; }}
  th.sticky-row {{ position: sticky; top: 0; z-index: 4; }}
  th.corner {{ z-index: 5; left: 0; }}
  .total-cell {{ background: var(--bg-alt); font-weight: 700; }}
  .total-row th, .total-row td {{ background: #e9f0ff; font-weight: 700; }}
  .grand-total {{ color: var(--blue-dark); }}
  th.off-day, td.off-day {{ background: #f0f0f0 !important; color: #bbb; }}

  @media print {{
    .actions {{ display: none; }}
    body {{ padding: 0; }}
    @page {{ size: A4 landscape; margin: 10mm; }}

    /* Le défilement horizontal et les en-têtes/colonnes "collants" ne servent qu'à l'écran :
       à l'impression ils provoquent des en-têtes dupliqués et des tableaux tronqués. On les
       désactive et on force chaque tableau à tenir exactement dans la largeur de la page. */
    .table-scroll {{ overflow: visible; border: none; }}
    .table-scroll table {{ table-layout: fixed; width: 100%; min-width: 0; }}
    th.sticky-col, td.total-col, th.total-col, th.sticky-row, th.corner {{ position: static; }}

    table.day-grid-table th, table.day-grid-table td {{
      font-size: 6.5pt; padding: 1px 2px; min-width: 0; overflow: hidden;
    }}
    /* table-layout: fixed tire les largeurs de colonnes de la 1ère ligne (l'en-tête) : on
       cible donc aussi th.corner (en-tête "Créneau"), pas seulement td/th.slot-label. */
    table.day-grid-table th.slot-label, table.day-grid-table th.corner {{
      width: 54px; white-space: normal; line-height: 1.15;
    }}
    table.day-grid-table td.total-col, table.day-grid-table th.total-col {{ width: 30px; }}
    table.recap-table th, table.recap-table td {{ font-size: 8pt; padding: 3px 2px; }}
  }}
</style>
</head>
<body>
  <div class="actions"><button onclick="window.print()">Imprimer / Export PDF</button></div>
  <h1>{title}</h1>
  <p class="subtitle">Période analysée : du {start} au {end}</p>

  <div class="summary">
    <div class="stat"><div class="value">{total_calls}</div><div class="label">Appels aboutis</div></div>
    <div class="stat"><div class="value">{total_duration}</div><div class="label">Durée totale de communication</div></div>
    <div class="stat"><div class="value">{dmt}</div><div class="label">Durée moyenne de traitement (DMT)</div></div>
    <div class="stat"><div class="value">{over_seuil1}</div><div class="label">Appels &gt; 3 min</div></div>
    <div class="stat"><div class="value">{over_seuil2}</div><div class="label">Appels &gt; 6 min</div></div>
    <div class="stat"><div class="value">{moyenne_hors_samedi}</div><div class="label">Moyenne appels/jour (hors samedi)</div></div>
  </div>

  <h2>Détail jour par jour, par créneau de 30 minutes</h2>
  {day_grid_table}
  <p class="note">Survolez une case pour voir la durée moyenne de communication. Lundi-vendredi 8h-20h, samedi 8h-12h.</p>

  <h2>Récapitulatif par jour de semaine et tranche horaire</h2>
  {recap_table}
  <p class="note">Tous les jours identiques regroupés ensemble (ex : tous les lundis de la période). Survolez une case pour voir son pourcentage du total.</p>

  <h2>Traitement des appels</h2>
  {traitement_table}
  <p class="note">Pourcentage sur le total d'appels du mois.</p>
  {subdivision_section}
</body>
</html>
"""


def render_report(data: ReportData) -> str:
    client_label = data.client.label if data.client else "Tous les clients"
    total_duration = _fmt_duration(data.total_seconds)
    dmt = _fmt_hms(data.total_seconds / data.total_calls) if data.total_calls else "—"

    if data.subdivision:
        names = " / ".join(n.title() for n in data.subdivision.names)
        subdivision_section = (
            f"<h2>Répartition par médecin — {html.escape(names)}</h2>"
            f"{_build_subdivision_table(data)}"
            '<p class="note">Le 1er médecin du groupe absorbe l\'écart d\'arrondi : la somme des '
            "3 comptages correspond exactement au total RDV ci-dessus, et la somme des "
            "pourcentages fait exactement 100&nbsp;%.</p>"
        )
    else:
        subdivision_section = ""

    return TEMPLATE.format(
        title=html.escape(f"Relevé des appels entrants — {client_label}"),
        start=_fr_date(data.period_start),
        end=_fr_date(data.period_end),
        total_calls=data.total_calls,
        total_duration=total_duration,
        dmt=dmt,
        over_seuil1=data.count_over_seuil1,
        over_seuil2=data.count_over_seuil2,
        moyenne_hors_samedi=f"{data.moyenne_hors_samedi:.1f}".replace(".", ","),
        day_grid_table=_build_day_grid_table(data),
        recap_table=_build_recap_table(data),
        traitement_table=_build_traitement_table(data),
        subdivision_section=subdivision_section,
    )
