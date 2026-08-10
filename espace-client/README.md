# Espace client — statistiques d'appels

Espace sécurisé où chaque cabinet (client DOCTEL) consulte ses statistiques
mensuelles d'appels, publiées par l'application de bureau `callstats`
(voir `desktop-app/`). Non responsive, comme demandé — c'est un outil de
consultation, pas une vitrine.

## Ce qu'il faut préparer sur OVH

1. **Base de données MySQL** : dans l'espace client OVH, Hébergements >
   Bases de données > Créer une base MySQL. Notez le nom de la base,
   l'hôte (ex: `xxxxx.mysql.db`), l'utilisateur et le mot de passe.
2. **Importer le schéma** : via phpMyAdmin (lien fourni par OVH) ou en ligne
   de commande, exécutez `sql/schema.sql` dans cette base — il crée les
   deux tables (`clients`, `stats_mensuelles`).
3. **PHP** : déjà disponible sur tout hébergement mutualisé OVH (PHP 8.x),
   rien à activer.
4. **Déployer les fichiers** : uploadez tout le dossier `espace-client/`
   (par FTP ou via le déploiement git déjà en place pour le reste du site)
   à la racine du site, à côté de `index.html`.
5. **Configurer** : copiez `config.php.example` en `config.php` sur le
   serveur (jamais dans git) et complétez :
   - `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASS` : les identifiants de l'étape 1.
   - `ADMIN_PASSWORD_HASH` : générez-le avec
     `php -r 'echo password_hash("votre-mot-de-passe", PASSWORD_DEFAULT), PHP_EOL;'`
   - `API_KEY` : une clé partagée avec l'application de bureau, générée avec
     `php -r 'echo bin2hex(random_bytes(32)), PHP_EOL;'`
   - `APP_URL` : l'URL publique de ce dossier, ex. `https://doctel.fr/espace-client`.
6. **HTTPS** : vérifiez que le site est bien servi en HTTPS (certificat Let's
   Encrypt gratuit, activable depuis l'espace client OVH) — les mots de passe
   et le lien secret transitent en clair sinon.

## Utilisation

### Créer un client (cabinet)

`espace-client/admin/` — connectez-vous avec le mot de passe administrateur,
« + Ajouter un client » : renseignez le nom, le **slug** (doit être identique
au slug utilisé pour ce client dans l'application callstats — visible dans
Réglages > Clients de l'appli), un identifiant et un mot de passe. Le lien
secret permanent est généré automatiquement et affiché sur la fiche du client.

### Saisir les années précédentes (une seule fois)

`espace-client/admin/` > « Statistiques » sur la ligne du client concerné,
puis choisissez l'année (2023, 2024, 2025…) et saisissez à la main le nombre
d'appels de chaque mois. Les liens vers les pages détaillées ne sont pas
obligatoires pour les années archivées.

### Alimentation automatique du mois en cours

Une fois le client créé avec le **même slug** que dans callstats, et l'URL +
la clé API renseignées dans callstats (Réglages > Publication), chaque
« Publier sur le site » depuis l'appli met aussi à jour le tableau de
l'espace client automatiquement (nombre d'appels et lien), sans ressaisie.

### Accès des clients

Un client accède à son espace :
- soit via son **lien secret permanent** (`acces.php?t=...`), à lui
  transmettre une fois — à ne pas diffuser par un canal non sécurisé ;
- soit via `espace-client/login.php` avec son identifiant/mot de passe.

## Sécurité

- Mots de passe hashés (`password_hash`/`password_verify`), jamais stockés
  en clair.
- Le lien secret est un jeton aléatoire de 48 caractères hexadécimaux —
  non devinable par force brute dans un délai raisonnable. En cas de doute
  sur une fuite, régénérez-le depuis l'administration (l'ancien lien cesse
  aussitôt de fonctionner).
- `config.php` (identifiants réels) n'est jamais commité dans le dépôt git
  (voir `.gitignore` à la racine du site) et son accès direct est bloqué par
  `.htaccess`.
- L'API `api/update.php` exige la clé `API_KEY` dans l'en-tête `X-Api-Key` ;
  sans elle, aucune écriture n'est possible.
