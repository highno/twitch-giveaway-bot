CREATE TABLE IF NOT EXISTS presence_events (
  presence_event_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  channel_id BIGINT NOT NULL,
  session_id BIGINT NULL,
  user_login VARCHAR(64) NOT NULL,
  event_type VARCHAR(16) NOT NULL,
  event_ts DATETIME NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_presence_user_time (user_login, event_ts),
  INDEX idx_presence_channel_time (channel_id, event_ts),
  FOREIGN KEY (channel_id) REFERENCES channels(id)
);
