<?php
require_once __DIR__ . '/includes/auth.php';

$client = require_client_auth();
$pageTitle = 'Informations';
$activeNav = 'informations';

require __DIR__ . '/includes/layout_header.php';
?>
<p class="eyebrow">Espace client</p>
<h1>Informations</h1>
<p style="color:var(--text-muted)">Cette page sera complétée prochainement.</p>
<?php require __DIR__ . '/includes/layout_footer.php'; ?>
