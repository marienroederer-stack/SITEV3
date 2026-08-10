<?php
/** Connexion PDO et accès aux données (clients, statistiques mensuelles). */

require_once __DIR__ . '/../config.php';

function db(): PDO
{
    static $pdo = null;
    if ($pdo === null) {
        $dsn = 'mysql:host=' . DB_HOST . ';dbname=' . DB_NAME . ';charset=utf8mb4';
        $pdo = new PDO($dsn, DB_USER, DB_PASS, [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        ]);
    }
    return $pdo;
}

function find_client_by_login(string $login): ?array
{
    $stmt = db()->prepare('SELECT * FROM clients WHERE login = ?');
    $stmt->execute([$login]);
    $row = $stmt->fetch();
    return $row ?: null;
}

function find_client_by_token(string $token): ?array
{
    $stmt = db()->prepare('SELECT * FROM clients WHERE secret_token = ?');
    $stmt->execute([$token]);
    $row = $stmt->fetch();
    return $row ?: null;
}

function find_client_by_id(int $id): ?array
{
    $stmt = db()->prepare('SELECT * FROM clients WHERE id = ?');
    $stmt->execute([$id]);
    $row = $stmt->fetch();
    return $row ?: null;
}

function find_client_by_slug(string $slug): ?array
{
    $stmt = db()->prepare('SELECT * FROM clients WHERE slug = ?');
    $stmt->execute([$slug]);
    $row = $stmt->fetch();
    return $row ?: null;
}

function list_clients(): array
{
    return db()->query('SELECT * FROM clients ORDER BY nom')->fetchAll();
}

function slugify(string $text): string
{
    $ascii = @iconv('UTF-8', 'ASCII//TRANSLIT', $text) ?: $text;
    $slug = strtolower(trim(preg_replace('/[^a-zA-Z0-9]+/', '-', $ascii), '-'));
    return $slug !== '' ? $slug : 'client';
}

function create_client(string $nom, string $slug, string $login, string $password): array
{
    $stmt = db()->prepare(
        'INSERT INTO clients (slug, nom, login, password_hash, secret_token) VALUES (?, ?, ?, ?, ?)'
    );
    $stmt->execute([
        $slug,
        $nom,
        $login,
        password_hash($password, PASSWORD_DEFAULT),
        bin2hex(random_bytes(24)),
    ]);
    return find_client_by_id((int) db()->lastInsertId());
}

function update_client(int $id, string $nom, string $slug, string $login, ?string $newPassword): void
{
    if ($newPassword !== null && $newPassword !== '') {
        $stmt = db()->prepare(
            'UPDATE clients SET nom = ?, slug = ?, login = ?, password_hash = ? WHERE id = ?'
        );
        $stmt->execute([$nom, $slug, $login, password_hash($newPassword, PASSWORD_DEFAULT), $id]);
    } else {
        $stmt = db()->prepare('UPDATE clients SET nom = ?, slug = ?, login = ? WHERE id = ?');
        $stmt->execute([$nom, $slug, $login, $id]);
    }
}

function regenerate_client_token(int $id): string
{
    $token = bin2hex(random_bytes(24));
    $stmt = db()->prepare('UPDATE clients SET secret_token = ? WHERE id = ?');
    $stmt->execute([$token, $id]);
    return $token;
}

function delete_client(int $id): void
{
    $stmt = db()->prepare('DELETE FROM clients WHERE id = ?');
    $stmt->execute([$id]);
}

/** Retourne les statistiques d'une année, indexées par mois (1-12). */
function get_stats_for_year(int $clientId, int $annee): array
{
    $stmt = db()->prepare('SELECT * FROM stats_mensuelles WHERE client_id = ? AND annee = ?');
    $stmt->execute([$clientId, $annee]);
    $byMonth = [];
    foreach ($stmt->fetchAll() as $row) {
        $byMonth[(int) $row['mois']] = $row;
    }
    return $byMonth;
}

/** Insère ou met à jour partiellement une ligne mensuelle (ne touche pas les colonnes non fournies). */
function upsert_stats(int $clientId, int $annee, int $mois, array $fields): void
{
    $allowed = ['nb_appels', 'url_entrants', 'url_sortants'];
    $fields = array_intersect_key($fields, array_flip($allowed));
    if (!$fields) {
        return;
    }

    $pdo = db();
    $stmt = $pdo->prepare('SELECT id FROM stats_mensuelles WHERE client_id = ? AND annee = ? AND mois = ?');
    $stmt->execute([$clientId, $annee, $mois]);
    $existing = $stmt->fetch();

    if ($existing) {
        $set = implode(', ', array_map(fn($col) => "$col = :$col", array_keys($fields)));
        $fields['id'] = $existing['id'];
        $pdo->prepare("UPDATE stats_mensuelles SET $set WHERE id = :id")->execute($fields);
    } else {
        $fields['client_id'] = $clientId;
        $fields['annee'] = $annee;
        $fields['mois'] = $mois;
        $cols = implode(', ', array_keys($fields));
        $placeholders = implode(', ', array_map(fn($col) => ":$col", array_keys($fields)));
        $pdo->prepare("INSERT INTO stats_mensuelles ($cols) VALUES ($placeholders)")->execute($fields);
    }
}
