<?php
require_once __DIR__ . '/includes/auth.php';

if (current_client() !== null) {
    header('Location: statistiques.php');
    exit;
}

$error = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $login = trim($_POST['login'] ?? '');
    $password = (string) ($_POST['password'] ?? '');
    $client = attempt_login($login, $password);
    if ($client !== null) {
        set_client_session($client);
        header('Location: statistiques.php');
        exit;
    }
    $error = 'Identifiant ou mot de passe incorrect.';
}
?>
<!doctype html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Connexion — Espace client DOCTEL</title>
<link rel="icon" type="image/svg+xml" href="../assets/logo.svg">
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="assets/style.css">
</head>
<body>
<header class="app-header">
  <div class="container app-header-inner">
    <a href="../index.html" class="app-logo-link" aria-label="DOCTEL">
      <img src="../assets/logo.svg" alt="DOCTEL" class="app-logo-img">
    </a>
  </div>
</header>
<main class="app-main">
  <div class="container" style="max-width:480px;">
    <p class="eyebrow">Espace client</p>
    <h1>Statistiques d'appels</h1>
    <p style="color:var(--text-muted)">Connectez-vous avec vos identifiants, ou utilisez le lien personnel qui vous a été transmis.</p>

    <div class="login-card">
      <?php if ($error !== ''): ?>
        <p class="form-error"><?= htmlspecialchars($error) ?></p>
      <?php endif; ?>
      <form method="post">
        <div class="form-field">
          <label for="login">Identifiant</label>
          <input id="login" name="login" type="text" required autofocus>
        </div>
        <div class="form-field">
          <label for="password">Mot de passe</label>
          <input id="password" name="password" type="password" required>
        </div>
        <button type="submit" class="btn">Se connecter</button>
      </form>
    </div>
    <p class="form-note">Vous avez perdu votre lien ou vos identifiants ? Contactez DOCTEL au 04 73 23 11 56.</p>
  </div>
</main>
</body>
</html>
