<?php
require_once __DIR__ . '/includes/auth.php';

$client = require_client_auth();
$pageTitle = 'Contact';
$activeNav = 'contact';

require __DIR__ . '/includes/layout_header.php';
?>
<p class="eyebrow">Espace client</p>
<h1>Contact</h1>
<ul style="list-style:none; padding:0; color:var(--text)">
  <li style="margin-bottom:10px;"><strong>Téléphone</strong> — <a href="tel:+33473231156">04 73 23 11 56</a></li>
  <li style="margin-bottom:10px;"><strong>Email gestion</strong> — <a href="mailto:gestion3@doctel.fr">gestion3@doctel.fr</a></li>
  <li style="margin-bottom:10px;"><strong>Adresse</strong> — 20 rue du Château des Vergnes, 63100 Clermont-Ferrand</li>
</ul>
<?php require __DIR__ . '/includes/layout_footer.php'; ?>
