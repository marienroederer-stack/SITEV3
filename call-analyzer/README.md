# CADUCEA — Analyse interne des appels

Application de bureau (Windows) pour l'analyse **interne** des appels entrants du
standard : volumes par créneau, par opérateur, par code affaire, temps d'attente,
taux de TAG... Indépendante de l'application "DOCTEL - analyse appels entrants"
(`../desktop-app`), qui génère les rapports **envoyés aux clients**.

## Fonctionnement

- **Import** : bouton "Importer un fichier…", même export Excel/CSV du standard
  téléphonique que l'autre application (colonnes Date, Heure, Type, Numéro
  Appelé, Identifiant Appelé, Nom Appelé, Durée Totale, Annonce, File, Sonnerie,
  Comm, Tag, Call Id, Code Affaire...). Seuls les appels **entrants** sont
  retenus ; aucun autre filtre n'est appliqué (contrairement à DOCTEL, cet outil
  sert au diagnostic global, pas à la facturation).
- **Dédoublonnage** entre imports successifs via la colonne **Call Id**.
- **Répertoires** : les onglets "Listing clients" (SDA / Nom / Code affaire) et
  "Listing opérateurs" (Login / Poste / Nom) sont préremplis depuis le cahier
  des charges initial, puis mis à jour automatiquement à chaque import — un
  nouveau SDA ou un nouveau login rencontré est ajouté (poste/nom à compléter
  manuellement pour un opérateur). Si le nom ou le code affaire d'un SDA déjà
  connu change dans un nouvel import, la fiche est mise à jour mais les
  statistiques déjà enregistrées restent attachées au même SDA (aucun
  historique perdu).
- **Trois onglets d'analyse** — Par client / Par opérateur / Par code affaire —
  chacun avec :
  - un sélecteur de valeur ("Tous les X" ou une valeur précise),
  - une vue Jour / Semaine / Mois (Semaine par défaut),
  - une granularité de créneau 15 / 30 / 60 min (60 min par défaut),
  - une navigation période précédente/suivante,
  - un sélecteur "Comparer avec" (n'importe quel mois déjà importé),
  - un rapport avec grille créneaux × jours (totaux en bas de colonne et en
    fin de ligne), durée moyenne de traitement (colonne Comm), attente
    moyenne globale (Annonce + File + Sonnerie), attente moyenne sur
    sonnerie seule, ratios d'appels de plus de 3/4/5/6 minutes (colonne
    Durée Totale) et taux de TAG (part des appels avec un tag renseigné),
    avec répartition par catégorie de tag.
- **Journal des imports** : historique des fichiers importés et de leur effet
  (lignes lues/ajoutées/doublons/nouveaux clients ou opérateurs).

Horaires retenus pour la grille : lundi-vendredi 8h-20h, samedi 8h-12h,
dimanche fermé (horaires d'ouverture réels du standard).

## Installation / développement (Windows)

```powershell
cd call-analyzer
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Les données (base SQLite locale) sont stockées dans
`%APPDATA%\CaduceaCallAnalyzer\`.

## Construire le .exe

1. **Automatique** : l'onglet Actions du dépôt GitHub contient un workflow
   "Build Windows executable (Analyse interne des appels)" (déclenchable
   manuellement) qui produit `CADUCEA - Analyse interne des appels.exe` en
   artefact téléchargeable.
2. **Locale** (sur une machine Windows) :

   ```powershell
   cd call-analyzer
   pip install pyinstaller
   pyinstaller packaging/call_analyzer.spec
   ```
