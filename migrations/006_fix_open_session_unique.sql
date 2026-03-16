-- Fix uniqueness semantics for stream_sessions:
-- allow unlimited closed sessions (is_live=0) while still enforcing only one open session per channel.

-- 1) Defensive cleanup: if historical/manual changes left multiple open sessions,
-- close all but the newest one per channel before adding the new unique index.
UPDATE stream_sessions s
JOIN (
  SELECT ranked.session_id
  FROM (
    SELECT
      session_id,
      ROW_NUMBER() OVER (
        PARTITION BY channel_id
        ORDER BY started_at DESC, session_id DESC
      ) AS rn
    FROM stream_sessions
    WHERE is_live = 1
  ) AS ranked
  WHERE ranked.rn > 1
) AS dupes ON dupes.session_id = s.session_id
SET
  s.is_live = 0,
  s.ended_at = COALESCE(s.ended_at, NOW());

-- 2) Remove the old index that incorrectly limited one closed session as well.
ALTER TABLE stream_sessions
  DROP INDEX uniq_open_session;

-- 3) Add a generated helper column that is 1 only for open sessions,
-- and NULL for closed sessions. MySQL unique indexes allow multiple NULLs,
-- so this enforces uniqueness only for open sessions.
ALTER TABLE stream_sessions
  ADD COLUMN open_slot TINYINT GENERATED ALWAYS AS (
    CASE WHEN is_live = 1 THEN 1 ELSE NULL END
  ) STORED;

ALTER TABLE stream_sessions
  ADD UNIQUE KEY uniq_open_session (channel_id, open_slot);
