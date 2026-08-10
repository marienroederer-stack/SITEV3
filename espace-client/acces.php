<?php
/** Point d'entrée du lien secret permanent : espace-client/acces.php?t=XXXX */
require_once __DIR__ . '/includes/auth.php';

$token = trim($_GET['t'] ?? '');
$client = attempt_token_login($token);
if ($client === null) {
    header('Location: login.php');
    exit;
}

set_client_session($client);
header('Location: statistiques.php');
exit;
