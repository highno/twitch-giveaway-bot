# Twitch Giveaway Bot (Codex Project)

## Goal
Maintain a robust Twitch giveaway bot that:
- Tracks chat presence via Twitch IRC membership (JOIN/PART) across multiple channels.
- Requires a one-time **global opt-in** codeword (one opt-in per user, applies to all channels).
- Issues **one ticket per opted-in & present user per 10-minute bucket** (idempotent across restarts).
- Persists all state to MySQL.
- Detects stream online/offline via EventSub WebSocket (**handles session_reconnect**).
- Supports weighted **multi-session draws** via CLI.

## Constraints
- Python 3.9+ (Linux server recommended).
- No reliance on "viewer list" APIs.
- Tickets must be idempotent across restarts using a unique bucket constraint.

## Run (Dev)
1. Copy `.env.example` -> `.env` and fill values.
2. Install deps: `pip install -r requirements.txt`
3. Apply SQL migrations in `migrations/` in order.
4. Start: `PYTHONPATH=src python -m giveaway_bot.bot`

## Run (Systemd)
- Install unit from `systemd/`, set WorkingDirectory and EnvironmentFile.
- `systemctl enable --now twitch-giveaway-bot`

## Draw CLI
- List sessions: `PYTHONPATH=src python -m giveaway_bot.draw --list`
- Draw: `PYTHONPATH=src python -m giveaway_bot.draw --sessions 101,105 --winners 3 --desc "Final"`

## Coding Standards
- Any DB write must tolerate transient MySQL errors (deadlocks/lock wait timeout) with retry/backoff.
- Duplicate-key errors for ticket issuance must be ignored (idempotent).
- EventSub must handle `session_reconnect` using reconnect_url.
- TokenManager must validate and refresh tokens automatically.
- Ignore known bot accounts and (optionally) verified bot flags.

## Safety / Abuse
- Ignore known bot accounts (`IGNORED_LOGINS`) and optional verified-bot tags.
- Never grant tickets to ignored accounts.
