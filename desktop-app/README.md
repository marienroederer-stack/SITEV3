# DOCTEL — Statistiques d'appels

Application de bureau (Windows) qui importe les listings d'appels (Excel/CSV),
calcule des statistiques par client (cabinet médical) sur son cycle mensuel
propre, affiche un rapport interactif et permet de l'exporter en PDF ou de le
publier directement sur le site web.

## Règles appliquées

- Seuls les appels **entrants aboutis** sont comptabilisés (Type = entrant,
  Raison du rejet = normal ou vide).
- La durée retenue est la colonne **Comm** (temps de communication réel).
- Les appels dont la durée Comm est **inférieure à 10 secondes** ne sont pas
  comptabilisés.
- Le dédoublonnage entre deux imports successifs se fait via la colonne
  **Call Id** — un même fichier ou une période qui se chevauche peut être
  réimporté sans créer de doublons.
- Chaque client (identifié par son "Numéro Appelé", le SDA dédié du cabinet)
  a un **jour de début de cycle mensuel** propre, réglable dans
  Réglages > Clients (1 = mois civil, 3 = "du 3 au 2 du mois suivant", etc.).
  Ce réglage est permanent tant qu'il n'est pas changé manuellement.
- Les statistiques couvrent lundi-vendredi 8h-20h et samedi 8h-12h (créneaux
  de 30 minutes) ; le dimanche est hors périmètre.

## Utiliser l'application

1. **Importer** : bouton "Importer un fichier…", sélectionner l'export Excel
   ou CSV du standard téléphonique. Les nouveaux clients sont détectés
   automatiquement (cycle = mois civil par défaut, modifiable ensuite).
2. **Client** : choisir "Tous les clients" (vue globale, mois civil) ou un
   cabinet précis (son propre cycle mensuel s'applique).
3. **Période** : naviguer avec "◀ Période précédente" / "Période suivante ▶"
   pour consulter les cycles passés (tant que les données ont été importées).
4. **Exporter PDF** / **Exporter HTML** : enregistre le rapport affiché.
5. **Publier sur le site** : envoie le rapport HTML du client sélectionné sur
   l'hébergeur configuré (Réglages > Publication), à une URL stable
   `<url de base>/<slug du client>.html`.

## Réglages > Archivage

Les appels importés restent en base indéfiniment (rien n'est purgé
automatiquement). Depuis Réglages > Archivage :
- **Exporter le mois sélectionné en CSV** génère un fichier d'archive et
  marque le mois comme "archivé" (n'efface rien).
- **Supprimer les appels des mois déjà archivés** supprime d'un coup les
  appels de tous les mois exportés mais pas encore purgés — utile si
  plusieurs mois sont archivés en retard. Action irréversible, confirmation
  demandée à chaque fois.

## Réglages > Publication (FTP/SFTP)

Les identifiants sont stockés localement, le mot de passe étant chiffré
(fichier `secret.key` généré sur le poste). C'est une protection contre une
lecture accidentelle du fichier de données, pas contre un accès complet à la
machine — ne réutilisez pas ce mot de passe pour un autre usage sensible.

Le dossier distant (ex : `/rapports`) doit correspondre à un emplacement
accessible en écriture par le compte FTP/SFTP fourni. C'est vous qui liez
ensuite manuellement chaque page publiée depuis l'espace client existant du
site (l'application ne gère pas l'authentification des clients).

## Installation / développement (Windows)

```powershell
cd desktop-app
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Les données (base SQLite + clé de chiffrement) sont stockées dans
`%APPDATA%\DoctelCallStats\`.

## Construire le .exe

Deux options :

1. **Automatique** : l'onglet Actions du dépôt GitHub contient un workflow
   "Build Windows executable" (déclenchable manuellement) qui produit
   `DoctelStatsAppels.exe` en artefact téléchargeable — aucune installation
   nécessaire de votre côté.
2. **Locale** (sur une machine Windows) :

   ```powershell
   cd desktop-app
   pip install pyinstaller
   pyinstaller packaging/callstats.spec
   ```

   L'exécutable est généré dans `desktop-app/dist/DoctelStatsAppels.exe`.
