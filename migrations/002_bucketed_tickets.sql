ALTER TABLE tickets
  ADD COLUMN bucket_start DATETIME NOT NULL AFTER issued_at;

CREATE UNIQUE INDEX uniq_ticket_bucket
  ON tickets(channel_id, session_id, user_login, bucket_start);
