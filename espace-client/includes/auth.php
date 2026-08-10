<?php
/** Authentification côté client (login/mot de passe ou lien secret) et côté admin. */

require_once __DIR__ . '/db.php';

function start_app_session(): void
{
    if (session_status() === PHP_SESSION_ACTIVE) {
        return;
    }
    session_set_cookie_params([
        'lifetime' => 0,
        'path' => '/',
        'httponly' => true,
        'samesite' => 'Lax',
        'secure' => !empty($_SERVER['HTTPS']),
    ]);
    session_start();
}

function current_client(): ?array
{
    start_app_session();
    if (empty($_SESSION['client_id'])) {
        return null;
    }
    return find_client_by_id((int) $_SESSION['client_id']);
}

function require_client_auth(): array
{
    $client = current_client();
    if ($client === null) {
        header('Location: login.php');
        exit;
    }
    return $client;
}

function set_client_session(array $client): void
{
    start_app_session();
    session_regenerate_id(true);
    $_SESSION['client_id'] = $client['id'];
}

function attempt_login(string $login, string $password): ?array
{
    $client = find_client_by_login($login);
    if ($client === null || !password_verify($password, $client['password_hash'])) {
        usleep(300000); // ralentit le brute-force sans gêner un usage normal
        return null;
    }
    return $client;
}

function attempt_token_login(string $token): ?array
{
    if ($token === '') {
        return null;
    }
    return find_client_by_token($token);
}

function logout_client(): void
{
    start_app_session();
    $_SESSION = [];
    session_destroy();
}

// -- Administration ----------------------------------------------------

function require_admin_auth(): void
{
    start_app_session();
    if (empty($_SESSION['admin_authenticated'])) {
        header('Location: login.php');
        exit;
    }
}

function attempt_admin_login(string $password): bool
{
    if (password_verify($password, ADMIN_PASSWORD_HASH)) {
        start_app_session();
        session_regenerate_id(true);
        $_SESSION['admin_authenticated'] = true;
        return true;
    }
    usleep(300000);
    return false;
}

function logout_admin(): void
{
    start_app_session();
    unset($_SESSION['admin_authenticated']);
}
