<?php
header('Content-Type: text/html; charset=utf-8');

$destinataire = 'contact@doctel.fr';

$nom = isset($_POST['nom']) ? trim($_POST['nom']) : '';
$email = isset($_POST['email']) ? trim($_POST['email']) : '';
$message = isset($_POST['message']) ? trim($_POST['message']) : '';

if ($nom === '' || $email === '' || $message === '' || !filter_var($email, FILTER_VALIDATE_EMAIL)) {
    http_response_code(400);
    echo "Merci de remplir correctement tous les champs du formulaire.";
    exit;
}

$sujet = "CONTACT DEPUIS DOCTEL.FR";
$corps = "Nom : $nom\r\nEmail : $email\r\n\r\nMessage :\r\n$message";

$entetes = "From: DOCTEL Site <$destinataire>\r\n";
$entetes .= "Reply-To: $email\r\n";
$entetes .= "Content-Type: text/plain; charset=UTF-8\r\n";
$entetes .= "MIME-Version: 1.0\r\n";

$envoye = mail($destinataire, $sujet, $corps, $entetes, "-f$destinataire");

if ($envoye) {
    header('Location: index.html?envoye=1#contact');
} else {
    http_response_code(500);
    echo "Une erreur est survenue lors de l'envoi. Merci de nous contacter par téléphone.";
}
