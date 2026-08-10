<?php
require_once __DIR__ . '/../includes/auth.php';

require_admin_auth();
$pageTitle = 'Clients';
$clients = list_clients();

require __DIR__ . '/../includes/admin_layout_header.php';
?>
<p class="eyebrow">Administration</p>
<h1>Clients</h1>
<p><a class="btn" href="client_form.php">+ Ajouter un client</a></p>

<div class="table-scroll">
<table class="stats-table" style="width:100%;">
  <thead>
    <tr>
      <th class="row-label">Nom</th>
      <th class="row-label">Slug</th>
      <th class="row-label">Identifiant</th>
      <th class="row-label">Lien secret</th>
      <th class="row-label">Actions</th>
    </tr>
  </thead>
  <tbody>
    <?php foreach ($clients as $c): ?>
      <tr>
        <td class="row-label"><?= htmlspecialchars($c['nom']) ?></td>
        <td><?= htmlspecialchars($c['slug']) ?></td>
        <td><?= htmlspecialchars($c['login']) ?></td>
        <td style="max-width:280px; overflow:hidden; text-overflow:ellipsis;">
          <?= htmlspecialchars(APP_URL) ?>/acces.php?t=<?= htmlspecialchars($c['secret_token']) ?>
        </td>
        <td>
          <a href="client_form.php?id=<?= (int) $c['id'] ?>">Modifier</a>
          &nbsp;·&nbsp;
          <a href="stats_form.php?client_id=<?= (int) $c['id'] ?>">Statistiques</a>
        </td>
      </tr>
    <?php endforeach; ?>
    <?php if (!$clients): ?>
      <tr><td colspan="5">Aucun client pour le moment.</td></tr>
    <?php endif; ?>
  </tbody>
</table>
</div>

<?php require __DIR__ . '/../includes/admin_layout_footer.php'; ?>
