ALTER TABLE stream_sessions
  ADD COLUMN stream_id VARCHAR(64) NULL AFTER category,
  ADD UNIQUE KEY uniq_stream_id (stream_id);
