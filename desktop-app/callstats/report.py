"""Génération du rapport HTML autonome (interactif à l'écran, imprimable en PDF)."""

import html
from datetime import date, datetime

from . import db
from .stats import JOURS_SEMAINE, SLOTS_SAMEDI, SLOTS_SEMAINE, TRANCHES, ReportData

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


def _build_grid_table(data: ReportData) -> str:
    max_count = max((cell.count for cell in data.grid.values()), default=0)
    rows_html = []
    for h, m in SLOTS_SEMAINE:
        cells = [f"<th class=\"slot-label\">{h:02d}h{m:02d}</th>"]
        for weekday in range(6):
            valid_slots = SLOTS_SAMEDI if weekday == 5 else SLOTS_SEMAINE
            if (h, m) not in valid_slots:
                cells.append("<td class=\"closed\">—</td>")
                continue
            cell = data.grid.get((weekday, (h, m)))
            count = cell.count if cell else 0
            bg = _heat_color(count, max_count)
            fg = _text_color_for(bg)
            avg = f"Durée moyenne : {_fmt_duration(cell.avg_seconds)}" if cell and cell.count else "Aucun appel"
            tooltip = html.escape(f"{JOURS_SEMAINE[weekday]} {h:02d}h{m:02d} — {count} appel(s). {avg}")
            cells.append(
                f'<td class="cell" style="background:{bg};color:{fg}" title="{tooltip}">'
                f'{count if count else ""}</td>'
            )
        rows_html.append(f"<tr>{''.join(cells)}</tr>")

    header = "<tr><th></th>" + "".join(f"<th>{d}</th>" for d in JOURS_SEMAINE) + "</tr>"
    return f'<table class="grid-table"><thead>{header}</thead><tbody>{"".join(rows_html)}</tbody></table>'


def _build_recap_table(data: ReportData) -> str:
    max_count = max(data.recap.values(), default=0)
    rows_html = []
    for weekday, jour in enumerate(JOURS_SEMAINE):
        cells = [f"<th class=\"slot-label\">{jour}</th>"]
        for label, _, _ in TRANCHES:
            count = data.recap.get((weekday, label), 0)
            bg = _heat_color(count, max_count)
            fg = _text_color_for(bg)
            cells.append(f'<td class="cell" style="background:{bg};color:{fg}">{count if count else ""}</td>')
        rows_html.append(f"<tr>{''.join(cells)}</tr>")

    header = "<tr><th></th>" + "".join(f"<th>{label}</th>" for label, _, _ in TRANCHES) + "</tr>"
    return f'<table class="recap-table"><thead>{header}</thead><tbody>{"".join(rows_html)}</tbody></table>'


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
  th, td {{ border: 1px solid var(--border); text-align: center; padding: 6px 4px; font-size: 0.82rem; }}
  th {{ background: var(--bg-alt); color: var(--blue-dark); font-weight: 600; }}
  td.slot-label, th.slot-label {{ text-align: right; padding-right: 10px; white-space: nowrap; }}
  td.closed {{ background: #fafafa; color: #ccc; }}
  td.cell {{ cursor: default; font-weight: 600; }}
  .note {{ color: var(--text-muted); font-size: 0.8rem; margin-top: 8px; }}
  .actions {{ margin: 24px 0; }}
  .actions button {{
    background: var(--blue-dark); color: #fff; border: none; border-radius: 8px;
    padding: 10px 18px; font-size: 0.9rem; cursor: pointer; margin-right: 8px;
  }}
  footer {{ margin-top: 40px; color: var(--text-muted); font-size: 0.75rem; }}
  @media print {{
    .actions {{ display: none; }}
    body {{ padding: 0; }}
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
    <div class="stat"><div class="value">{avg_duration}</div><div class="label">Durée moyenne par appel</div></div>
  </div>

  <h2>Répartition des appels par créneau de 30 minutes</h2>
  {grid_table}
  <p class="note">Survolez une case pour voir la durée moyenne de communication sur ce créneau. Lundi-vendredi 8h-20h, samedi 8h-12h.</p>

  <h2>Récapitulatif par jour de semaine et tranche horaire</h2>
  {recap_table}
  <p class="note">Nombre d'appels reçus, tous les jours identiques regroupés ensemble (ex : tous les lundis de la période).</p>

  <footer>Rapport généré le {generated_at} — DOCTEL, statistiques d'appels internes.</footer>
</body>
</html>
"""


def render_report(data: ReportData) -> str:
    client_label = data.client.nom_appele if data.client else "Tous les clients"
    total_duration = _fmt_duration(data.total_seconds)
    avg_duration = _fmt_duration(data.total_seconds / data.total_calls) if data.total_calls else "—"

    return TEMPLATE.format(
        title=html.escape(f"Statistiques d'appels — {client_label}"),
        start=_fr_date(data.period_start),
        end=_fr_date(data.period_end),
        total_calls=data.total_calls,
        total_duration=total_duration,
        avg_duration=avg_duration,
        grid_table=_build_grid_table(data),
        recap_table=_build_recap_table(data),
        generated_at=datetime.now().strftime("%d/%m/%Y à %H:%M"),
    )
