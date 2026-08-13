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

$sujet = "Nouveau message depuis le site DOCTEL";
$corps = "Nom : $nom\nEmail : $email\n\nMessage :\n$message";
$entetes = "From: $destinataire\r\nReply-To: $email\r\n";

$envoye = mail($destinataire, $sujet, $corps, $entetes);

if ($envoye) {
    header('Location: index.html?message=envoye#contact');
} else {
    http_response_code(500);
    echo "Une erreur est survenue lors de l'envoi. Merci de nous contacter par téléphone.";
}
