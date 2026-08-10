<?php
/** Inclure après avoir défini $pageTitle. */
?>
<!doctype html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title><?= htmlspecialchars($pageTitle) ?> — Administration espace client</title>
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="../assets/style.css">
</head>
<body>
<header class="app-header">
  <div class="container app-header-inner">
    <strong style="color:var(--blue-dark)">Administration — Espace client DOCTEL</strong>
    <nav class="app-nav">
      <a href="index.php">Clients</a>
    </nav>
    <div class="app-header-meta"><a href="logout.php">Déconnexion</a></div>
  </div>
</header>
<main class="app-main">
  <div class="container">
