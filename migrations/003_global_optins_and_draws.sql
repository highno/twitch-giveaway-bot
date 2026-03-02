CREATE TABLE IF NOT EXISTS global_opt_ins (
  optin_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_login VARCHAR(64) NOT NULL,
  opted_in_at DATETIME NOT NULL,
  revoked_at DATETIME NULL,
  is_active TINYINT NOT NULL DEFAULT 1,
  UNIQUE KEY uniq_optin_user (user_login)
);

CREATE TABLE IF NOT EXISTS draw_runs (
  draw_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  description VARCHAR(255) NULL
);

CREATE TABLE IF NOT EXISTS draw_run_sessions (
  draw_id BIGINT NOT NULL,
  session_id BIGINT NOT NULL,
  PRIMARY KEY(draw_id, session_id)
);

CREATE TABLE IF NOT EXISTS winners (
  winner_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  draw_id BIGINT NOT NULL,
  user_login VARCHAR(64) NOT NULL,
  weight_tickets INT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
