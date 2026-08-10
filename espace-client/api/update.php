<?php
/**
 * API appelée par l'application de bureau callstats juste après la publication FTP
 * d'un rapport, pour mettre à jour automatiquement le tableau de l'espace client.
 *
 * Requête : POST, en-tête "X-Api-Key: <clé>", corps JSON :
 *   {"slug":"...", "annee":2026, "mois":8, "type":"entrants"|"sortants",
 *    "url":"https://...", "nb_appels":123}
 * "nb_appels" est ignoré pour type=sortants (le tableau n'affiche que le nombre
 * d'appels entrants).
 */

require_once __DIR__ . '/../includes/db.php';

header('Content-Type: application/json; charset=utf-8');

function fail(int $status, string $message): never
{
    http_response_code($status);
    echo json_encode(['ok' => false, 'error' => $message]);
    exit;
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    fail(405, 'Méthode non autorisée.');
}

$providedKey = $_SERVER['HTTP_X_API_KEY'] ?? '';
if (!hash_equals(API_KEY, $providedKey)) {
    fail(401, 'Clé API invalide.');
}

$payload = json_decode(file_get_contents('php://input'), true);
if (!is_array($payload)) {
    fail(400, 'Corps JSON invalide.');
}

$slug = trim((string) ($payload['slug'] ?? ''));
$annee = (int) ($payload['annee'] ?? 0);
$mois = (int) ($payload['mois'] ?? 0);
$type = (string) ($payload['type'] ?? '');
$url = trim((string) ($payload['url'] ?? ''));

if ($slug === '' || $annee < 2000 || $mois < 1 || $mois > 12 || !in_array($type, ['entrants', 'sortants'], true) || $url === '') {
    fail(400, 'Champs manquants ou invalides.');
}

$client = find_client_by_slug($slug);
if ($client === null) {
    fail(404, "Client inconnu pour le slug \"$slug\" — créez-le d'abord dans l'administration.");
}

$fields = $type === 'entrants' ? ['url_entrants' => $url] : ['url_sortants' => $url];
if ($type === 'entrants' && isset($payload['nb_appels'])) {
    $fields['nb_appels'] = (int) $payload['nb_appels'];
}

upsert_stats((int) $client['id'], $annee, $mois, $fields);

echo json_encode(['ok' => true]);
