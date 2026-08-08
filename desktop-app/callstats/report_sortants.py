"""Génération du rapport HTML autonome pour les appels sortants et aboutements."""

import html

from .stats_sortants import SortantsReportData

_MOIS = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def _fr_date(d) -> str:
    day_label = "1er" if d.day == 1 else str(d.day)
    return f"{day_label} {_MOIS[d.month - 1]} {d.year}"


def _fmt_eur(value: float) -> str:
    return f"{value:.2f}".replace(".", ",") + " € HT"


def _build_main_table(data: SortantsReportData) -> str:
    if data.tarifs is not None:
        tarif_cell = f'<td class="total-cell" title="{html.escape(_tarif_tooltip(data))}">{_fmt_eur(data.tarif_total)}</td>'
    else:
        tarif_cell = (
            '<td class="total-cell" title="Non calculé pour « Tous les clients » : '
            'les tarifs peuvent différer d\'un client à l\'autre.">—</td>'
        )
    return (
        '<table class="sortants-table">'
        "<thead>"
        '<tr><th colspan="2">Aboutements</th><th colspan="2">Sortants</th><th rowspan="2">TARIFS</th></tr>'
        "<tr><th>Fixes</th><th>Portables</th><th>Fixes</th><th>Portables</th></tr>"
        "</thead>"
        "<tbody><tr>"
        f'<td class="cell">{data.aboutement_fixe}</td>'
        f'<td class="cell">{data.aboutement_portable}</td>'
        f'<td class="cell">{data.sortant_fixe}</td>'
        f'<td class="cell">{data.sortant_portable}</td>'
        f"{tarif_cell}"
        "</tr></tbody>"
        "</table>"
    )


def _tarif_tooltip(data: SortantsReportData) -> str:
    t = data.tarifs
    return (
        f"Tarif aboutement vers fixe = {_fmt_eur(t['aboutement_fixe'])} | "
        f"Tarif aboutement vers portable = {_fmt_eur(t['aboutement_portable'])} | "
        f"Tarif sortant vers fixe = {_fmt_eur(t['sortant_fixe'])} | "
        f"Tarif sortant vers portable = {_fmt_eur(t['sortant_portable'])}"
    )


def _build_sms_table(data: SortantsReportData) -> str:
    if data.tarifs is None:
        return (
            '<table class="sortants-table"><thead>'
            "<tr><th>SMS de rappel/annulation de RDV</th><th>SMS contact</th></tr>"
            "</thead><tbody><tr>"
            '<td class="cell" colspan="2">Sélectionnez un client précis pour saisir les SMS.</td>'
            "</tr></tbody></table>"
        )
    return (
        '<table class="sortants-table"><thead>'
        "<tr><th>SMS de rappel/annulation de RDV</th><th>SMS contact</th></tr>"
        "</thead><tbody><tr>"
        f'<td class="cell" title="Tarif SMS de rappel/annulation = 0,15 € HT ou selon forfait">{data.sms_rappel}</td>'
        f'<td class="cell" title="Tarif SMS contact = 0,52 € HT">{data.sms_contact}</td>'
        "</tr></tbody></table>"
    )


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
  h2 {{ font-size: 1.15rem; color: var(--blue-dark); margin: 32px 0 12px; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 8px; max-width: 720px; }}
  th, td {{ border: 1px solid var(--border); text-align: center; padding: 10px 8px; font-size: 0.9rem; }}
  th {{ background: var(--bg-alt); color: var(--blue-dark); font-weight: 600; }}
  td.cell {{ cursor: default; font-weight: 600; }}
  .total-cell {{ background: var(--bg-alt); font-weight: 700; }}
  .note {{ color: var(--text-muted); font-size: 0.8rem; margin-top: 8px; }}
  .actions {{ margin: 24px 0; }}
  .actions button {{
    background: var(--blue-dark); color: #fff; border: none; border-radius: 8px;
    padding: 10px 18px; font-size: 0.9rem; cursor: pointer; margin-right: 8px;
  }}

  @media print {{
    .actions {{ display: none; }}
    body {{ padding: 0; }}
    @page {{ size: A4 landscape; margin: 10mm; }}
  }}
</style>
</head>
<body>
  <div class="actions"><button onclick="window.print()">Imprimer / Export PDF</button></div>
  <h1>{title}</h1>
  <p class="subtitle">Période analysée : du {start} au {end}</p>

  <h2>Aboutements, sortants et tarifs</h2>
  {main_table}
  <p class="note">Sortants = appels sortants basiques + tentatives de transfert (&gt;5s). Aboutements = appels transférés à un tiers pour le mettre en relation avec le client.</p>

  <h2>SMS</h2>
  {sms_table}
  <p class="note">Saisie manuelle (ces données ne proviennent pas du système téléphonique).</p>
</body>
</html>
"""


def render_report(data: SortantsReportData) -> str:
    client_label = data.client.label if data.client else "Tous les clients"
    return TEMPLATE.format(
        title=html.escape(f"Relevé des appels sortants — {client_label}"),
        start=_fr_date(data.period_start),
        end=_fr_date(data.period_end),
        main_table=_build_main_table(data),
        sms_table=_build_sms_table(data),
    )
