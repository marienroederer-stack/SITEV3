-- Schéma de la base "espace client" (statistiques d'appels).
-- À exécuter une fois dans la base MySQL créée sur l'hébergement OVH
-- (Espace client OVH > Hébergements > Bases de données > phpMyAdmin, ou en ligne de commande).

CREATE TABLE IF NOT EXISTS clients (
  id INT AUTO_INCREMENT PRIMARY KEY,
  slug VARCHAR(100) NOT NULL,
  nom VARCHAR(200) NOT NULL,
  login VARCHAR(100) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  secret_token VARCHAR(64) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uniq_clients_slug (slug),
  UNIQUE KEY uniq_clients_login (login),
  UNIQUE KEY uniq_clients_token (secret_token)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS stats_mensuelles (
  id INT AUTO_INCREMENT PRIMARY KEY,
  client_id INT NOT NULL,
  annee SMALLINT NOT NULL,
  mois TINYINT NOT NULL,
  nb_appels INT NULL,
  url_entrants VARCHAR(500) NULL,
  url_sortants VARCHAR(500) NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uniq_stats_periode (client_id, annee, mois),
  CONSTRAINT fk_stats_client FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
