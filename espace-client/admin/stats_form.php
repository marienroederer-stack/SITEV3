<?php
require_once __DIR__ . '/../includes/auth.php';

require_admin_auth();

$clientId = (int) ($_GET['client_id'] ?? 0);
$client = $clientId ? find_client_by_id($clientId) : null;
if ($client === null) {
    header('Location: index.php');
    exit;
}

$currentYear = (int) date('Y');
$annee = isset($_GET['annee']) ? (int) $_GET['annee'] : $currentYear;

$MOIS = [
    1 => 'Janvier', 2 => 'Février', 3 => 'Mars', 4 => 'Avril', 5 => 'Mai', 6 => 'Juin',
    7 => 'Juillet', 8 => 'Août', 9 => 'Septembre', 10 => 'Octobre', 11 => 'Novembre', 12 => 'Décembre',
];

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $postedYear = (int) ($_POST['annee'] ?? $annee);
    foreach (array_keys($MOIS) as $m) {
        $nbAppels = trim($_POST["nb_appels_$m"] ?? '');
        $urlEntrants = trim($_POST["url_entrants_$m"] ?? '');
        $urlSortants = trim($_POST["url_sortants_$m"] ?? '');
        upsert_stats((int) $client['id'], $postedYear, $m, [
            'nb_appels' => $nbAppels === '' ? null : (int) $nbAppels,
            'url_entrants' => $urlEntrants === '' ? null : $urlEntrants,
            'url_sortants' => $urlSortants === '' ? null : $urlSortants,
        ]);
    }
    header('Location: stats_form.php?client_id=' . $client['id'] . '&annee=' . $postedYear . '&saved=1');
    exit;
}

$statsByMonth = get_stats_for_year((int) $client['id'], $annee);
$pageTitle = 'Statistiques — ' . $client['nom'];
require __DIR__ . '/../includes/admin_layout_header.php';
?>
<p class="eyebrow">Administration</p>
<h1><?= htmlspecialchars($client['nom']) ?> — <?= $annee ?></h1>
<p><a href="index.php">&larr; Retour à la liste des clients</a></p>

<?php if (isset($_GET['saved'])): ?>
  <p class="form-error" style="background:#e9f7ee;color:#1a7a3a;">Enregistré.</p>
<?php endif; ?>

<p>
  <?php for ($y = $currentYear; $y >= $currentYear - 4; $y--): ?>
    <a href="stats_form.php?client_id=<?= $client['id'] ?>&annee=<?= $y ?>" style="margin-right:12px; font-weight:<?= $y === $annee ? '800' : '400' ?>;"><?= $y ?></a>
  <?php endfor; ?>
</p>

<form method="post">
  <input type="hidden" name="annee" value="<?= $annee ?>">
  <div class="table-scroll">
  <table class="stats-table" style="width:100%;">
    <thead>
      <tr>
        <th class="row-label">Mois</th>
        <th>Nb appels</th>
        <th>URL Stats Entrants</th>
        <th>URL Stats Sortants</th>
      </tr>
    </thead>
    <tbody>
      <?php foreach ($MOIS as $m => $label): $row = $statsByMonth[$m] ?? []; ?>
        <tr>
          <td class="row-label"><?= $label ?></td>
          <td><input type="number" min="0" name="nb_appels_<?= $m ?>" value="<?= htmlspecialchars($row['nb_appels'] ?? '') ?>" style="width:90px;"></td>
          <td><input type="text" name="url_entrants_<?= $m ?>" value="<?= htmlspecialchars($row['url_entrants'] ?? '') ?>" style="width:220px;"></td>
          <td><input type="text" name="url_sortants_<?= $m ?>" value="<?= htmlspecialchars($row['url_sortants'] ?? '') ?>" style="width:220px;"></td>
        </tr>
      <?php endforeach; ?>
    </tbody>
  </table>
  </div>
  <p style="margin-top:20px;"><button type="submit" class="btn">Enregistrer</button></p>
</form>

<?php require __DIR__ . '/../includes/admin_layout_footer.php'; ?>
