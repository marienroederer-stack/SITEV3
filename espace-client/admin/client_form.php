<?php
require_once __DIR__ . '/../includes/auth.php';

require_admin_auth();

$id = isset($_GET['id']) ? (int) $_GET['id'] : null;
$client = $id ? find_client_by_id($id) : null;
if ($id && $client === null) {
    header('Location: index.php');
    exit;
}

$error = '';
$newTokenMessage = '';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $action = $_POST['action'] ?? 'save';

    if ($action === 'delete' && $client) {
        delete_client((int) $client['id']);
        header('Location: index.php');
        exit;
    }

    if ($action === 'regenerate_token' && $client) {
        $newToken = regenerate_client_token((int) $client['id']);
        $client['secret_token'] = $newToken;
        $newTokenMessage = 'Nouveau lien généré : ' . APP_URL . '/acces.php?t=' . $newToken;
    }

    if ($action === 'save') {
        $nom = trim($_POST['nom'] ?? '');
        $slug = trim($_POST['slug'] ?? '') ?: slugify($nom);
        $login = trim($_POST['login'] ?? '');
        $password = (string) ($_POST['password'] ?? '');

        if ($nom === '' || $slug === '' || $login === '' || (!$client && $password === '')) {
            $error = 'Merci de renseigner au minimum le nom, le slug, l\'identifiant' . (!$client ? ' et le mot de passe.' : '.');
        } else {
            try {
                if ($client) {
                    update_client((int) $client['id'], $nom, $slug, $login, $password ?: null);
                    header('Location: index.php');
                    exit;
                } else {
                    $created = create_client($nom, $slug, $login, $password);
                    header('Location: index.php');
                    exit;
                }
            } catch (PDOException $e) {
                $error = 'Le slug ou l\'identifiant est déjà utilisé par un autre client.';
            }
        }
    }
}

$pageTitle = $client ? 'Modifier ' . $client['nom'] : 'Ajouter un client';
require __DIR__ . '/../includes/admin_layout_header.php';
?>
<p class="eyebrow">Administration</p>
<h1><?= htmlspecialchars($pageTitle) ?></h1>

<?php if ($error !== ''): ?>
  <p class="form-error"><?= htmlspecialchars($error) ?></p>
<?php endif; ?>
<?php if ($newTokenMessage !== ''): ?>
  <p class="form-error" style="background:#e9f7ee;color:#1a7a3a;"><?= htmlspecialchars($newTokenMessage) ?></p>
<?php endif; ?>

<div class="login-card" style="max-width:520px; margin-left:0;">
  <form method="post">
    <input type="hidden" name="action" value="save">
    <div class="form-field">
      <label for="nom">Nom du cabinet</label>
      <input id="nom" name="nom" type="text" required value="<?= htmlspecialchars($client['nom'] ?? '') ?>">
    </div>
    <div class="form-field">
      <label for="slug">Slug (identifiant technique, doit correspondre au slug utilisé dans l'application callstats)</label>
      <input id="slug" name="slug" type="text" required value="<?= htmlspecialchars($client['slug'] ?? '') ?>">
    </div>
    <div class="form-field">
      <label for="login">Identifiant de connexion</label>
      <input id="login" name="login" type="text" required value="<?= htmlspecialchars($client['login'] ?? '') ?>">
    </div>
    <div class="form-field">
      <label for="password">Mot de passe <?= $client ? '(laisser vide pour ne pas le changer)' : '' ?></label>
      <input id="password" name="password" type="password" <?= $client ? '' : 'required' ?>>
    </div>
    <button type="submit" class="btn">Enregistrer</button>
  </form>
</div>

<?php if ($client): ?>
  <h2>Lien secret</h2>
  <p style="word-break:break-all;"><?= htmlspecialchars(APP_URL) ?>/acces.php?t=<?= htmlspecialchars($client['secret_token']) ?></p>
  <form method="post" onsubmit="return confirm('Régénérer le lien ? L\'ancien lien cessera de fonctionner.');" style="margin-bottom:32px;">
    <input type="hidden" name="action" value="regenerate_token">
    <button type="submit" class="btn" style="background:var(--blue-light);">Régénérer le lien</button>
  </form>

  <h2>Zone de suppression</h2>
  <form method="post" onsubmit="return confirm('Supprimer définitivement ce client et toutes ses statistiques ?');">
    <input type="hidden" name="action" value="delete">
    <button type="submit" class="btn" style="background:#a3231f;">Supprimer ce client</button>
  </form>
<?php endif; ?>

<?php require __DIR__ . '/../includes/admin_layout_footer.php'; ?>
