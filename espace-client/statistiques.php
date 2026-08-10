<?php
require_once __DIR__ . '/includes/auth.php';

$client = require_client_auth();
$pageTitle = 'Statistiques';
$activeNav = 'statistiques';

$MOIS = [
    1 => 'Janvier', 2 => 'Février', 3 => 'Mars', 4 => 'Avril', 5 => 'Mai', 6 => 'Juin',
    7 => 'Juillet', 8 => 'Août', 9 => 'Septembre', 10 => 'Octobre', 11 => 'Novembre', 12 => 'Décembre',
];

$currentYear = (int) date('Y');
$previousYearsCount = 3;

function render_year_table(int $annee, array $statsByMonth, array $mois): string
{
    $html = '<div class="table-scroll"><table class="stats-table"><thead><tr>';
    $html .= '<th class="row-label">' . $annee . '</th>';
    foreach ($mois as $label) {
        $html .= '<th>' . htmlspecialchars($label) . '</th>';
    }
    $html .= '</tr></thead><tbody>';

    $html .= '<tr><td class="row-label">Nb appels</td>';
    foreach (array_keys($mois) as $m) {
        $val = $statsByMonth[$m]['nb_appels'] ?? null;
        $html .= '<td>' . ($val !== null ? (int) $val : '<span class="empty">—</span>') . '</td>';
    }
    $html .= '</tr>';

    $html .= '<tr><td class="row-label">Stats Entrants</td>';
    foreach (array_keys($mois) as $m) {
        $url = $statsByMonth[$m]['url_entrants'] ?? null;
        $html .= '<td>' . ($url ? '<a class="stat-link" href="' . htmlspecialchars($url) . '" target="_blank" rel="noopener">Voir</a>' : '<span class="empty">—</span>') . '</td>';
    }
    $html .= '</tr>';

    $html .= '<tr><td class="row-label">Stats Sortants</td>';
    foreach (array_keys($mois) as $m) {
        $url = $statsByMonth[$m]['url_sortants'] ?? null;
        $html .= '<td>' . ($url ? '<a class="stat-link" href="' . htmlspecialchars($url) . '" target="_blank" rel="noopener">Voir</a>' : '<span class="empty">—</span>') . '</td>';
    }
    $html .= '</tr>';

    $html .= '</tbody></table></div>';
    return $html;
}

require __DIR__ . '/includes/layout_header.php';
?>
<p class="eyebrow">Espace client</p>
<h1><?= htmlspecialchars($client['nom']) ?> — statistiques mensuelles d'appels</h1>

<div class="year-block current">
  <?= render_year_table($currentYear, get_stats_for_year((int) $client['id'], $currentYear), $MOIS) ?>
</div>

<h2>Années précédentes</h2>
<?php for ($i = 1; $i <= $previousYearsCount; $i++):
    $annee = $currentYear - $i;
?>
  <details class="year-block">
    <summary><?= $annee ?></summary>
    <?= render_year_table($annee, get_stats_for_year((int) $client['id'], $annee), $MOIS) ?>
  </details>
<?php endfor; ?>

<?php require __DIR__ . '/includes/layout_footer.php'; ?>
