CREATE TABLE IF NOT EXISTS channels (
  id BIGINT PRIMARY KEY,
  login VARCHAR(64) NOT NULL UNIQUE,
  display_name VARCHAR(64) NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stream_sessions (
  session_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  channel_id BIGINT NOT NULL,
  started_at DATETIME NOT NULL,
  ended_at DATETIME NULL,
  title VARCHAR(255) NULL,
  category VARCHAR(255) NULL,
  is_live TINYINT NOT NULL DEFAULT 1,
  UNIQUE KEY uniq_open_session (channel_id, is_live),
  FOREIGN KEY (channel_id) REFERENCES channels(id)
);

CREATE TABLE IF NOT EXISTS chat_messages (
  msg_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  channel_id BIGINT NOT NULL,
  session_id BIGINT NULL,
  user_id BIGINT NULL,
  user_login VARCHAR(64) NOT NULL,
  user_display VARCHAR(64) NULL,
  message TEXT NOT NULL,
  msg_ts DATETIME NOT NULL,
  raw_tags TEXT NULL,
  FOREIGN KEY (channel_id) REFERENCES channels(id)
);

CREATE TABLE IF NOT EXISTS activity_heartbeats (
  hb_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  channel_id BIGINT NOT NULL,
  session_id BIGINT NULL,
  user_login VARCHAR(64) NOT NULL,
  last_msg_ts DATETIME NOT NULL,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uniq_user_channel (channel_id, user_login),
  FOREIGN KEY (channel_id) REFERENCES channels(id)
);

CREATE TABLE IF NOT EXISTS tickets (
  ticket_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  channel_id BIGINT NOT NULL,
  session_id BIGINT NOT NULL,
  user_login VARCHAR(64) NOT NULL,
  issued_at DATETIME NOT NULL,
  reason VARCHAR(64) NOT NULL DEFAULT 'present_10min',
  FOREIGN KEY (channel_id) REFERENCES channels(id),
  FOREIGN KEY (session_id) REFERENCES stream_sessions(session_id),
  INDEX idx_session_user (session_id, user_login)
);

CREATE TABLE IF NOT EXISTS event_log (
  event_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  channel_id BIGINT NULL,
  event_type VARCHAR(64) NOT NULL,
  payload JSON NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
