<?php
require_once __DIR__ . '/includes/auth.php';

logout_client();
header('Location: login.php');
exit;
