<?php
/**
 * Inclure après avoir défini $pageTitle et $activeNav ('statistiques'|'informations'|'contact').
 * $client (tableau) doit être défini par la page appelante via require_client_auth().
 */
?>
<!doctype html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title><?= htmlspecialchars($pageTitle) ?> — Espace client DOCTEL</title>
<link rel="icon" type="image/svg+xml" href="../assets/logo.svg">
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="assets/style.css">
</head>
<body>
<header class="app-header">
  <div class="container app-header-inner">
    <a href="statistiques.php" class="app-logo-link" aria-label="DOCTEL">
      <img src="../assets/logo.svg" alt="DOCTEL" class="app-logo-img">
    </a>
    <nav class="app-nav">
      <a href="statistiques.php" class="<?= $activeNav === 'statistiques' ? 'active' : '' ?>">Statistiques</a>
      <a href="informations.php" class="<?= $activeNav === 'informations' ? 'active' : '' ?>">Informations</a>
      <a href="contact.php" class="<?= $activeNav === 'contact' ? 'active' : '' ?>">Contact</a>
    </nav>
    <div class="app-header-meta">
      <span><?= htmlspecialchars($client['nom']) ?></span>
      <a href="logout.php">Déconnexion</a>
    </div>
  </div>
</header>
<main class="app-main">
  <div class="container">
