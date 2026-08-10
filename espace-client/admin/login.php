<?php
require_once __DIR__ . '/../includes/auth.php';

start_app_session();
if (!empty($_SESSION['admin_authenticated'])) {
    header('Location: index.php');
    exit;
}

$error = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $password = (string) ($_POST['password'] ?? '');
    if (attempt_admin_login($password)) {
        header('Location: index.php');
        exit;
    }
    $error = 'Mot de passe incorrect.';
}
?>
<!doctype html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Administration — Espace client DOCTEL</title>
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="../assets/style.css">
</head>
<body>
<main class="app-main">
  <div class="container" style="max-width:420px;">
    <p class="eyebrow">Espace client — administration</p>
    <h1>Connexion administrateur</h1>
    <div class="login-card">
      <?php if ($error !== ''): ?>
        <p class="form-error"><?= htmlspecialchars($error) ?></p>
      <?php endif; ?>
      <form method="post">
        <div class="form-field">
          <label for="password">Mot de passe administrateur</label>
          <input id="password" name="password" type="password" required autofocus>
        </div>
        <button type="submit" class="btn">Se connecter</button>
      </form>
    </div>
  </div>
</main>
</body>
</html>
