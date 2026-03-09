# Twitch Giveaway Bot (Codex-ready)

This bot tracks **chat presence** (JOIN/PART) on multiple Twitch channels, requires a **one-time global opt-in codeword**, issues tickets every 10 minutes, stores everything in MySQL, and supports weighted multi-session draws.

## Requirements
- Linux recommended
- Python 3.9+
- MySQL 8+ (or compatible)
- A Twitch App (Client ID/Secret) and a **User Access Token + Refresh Token** for EventSub subscriptions.
- A Twitch IRC OAuth token for the bot account (usually `oauth:<token>`)

## Setup
```bash
git clone <this repo>
cd twitch-giveaway-codex
cp .env.example .env
pip install -r requirements.txt
```

## Database
Apply migrations in order (example using mysql CLI):
```bash
mysql -u bot -p twitch_giveaway < migrations/001_init.sql
mysql -u bot -p twitch_giveaway < migrations/002_bucketed_tickets.sql
mysql -u bot -p twitch_giveaway < migrations/003_global_optins_and_draws.sql
```

## Run
```bash
PYTHONPATH=src python -m giveaway_bot.bot
```

## Draw (weighted, multi-session)
List sessions:
```bash
PYTHONPATH=src python -m giveaway_bot.draw --list
```

Draw 3 winners across sessions 101,105,106:
```bash
PYTHONPATH=src python -m giveaway_bot.draw --sessions 101,105,106 --winners 3 --desc "Finale Staffel 2"
```

## Admin CLI
Ticket-Statistik (pro User & Kanal):
```bash
PYTHONPATH=src python -m giveaway_bot.admin stats
```

Optional auf Kanal oder Zeitraum begrenzen:
```bash
PYTHONPATH=src python -m giveaway_bot.admin stats --channel-id 123456 --from 2024-01-01T00:00:00 --to 2024-01-31T23:59:59
```

Alle Tickets eines Users löschen (optional mit Kanal/Zeitraum-Filter):
```bash
PYTHONPATH=src python -m giveaway_bot.admin purge-user --user someviewer --from 2024-01-01T00:00:00
```

Alle Tickets im Topf löschen:
```bash
PYTHONPATH=src python -m giveaway_bot.admin purge-all-tickets
```

Kompletten Runtime-Status zurücksetzen (wie frisch installiert):
```bash
PYTHONPATH=src python -m giveaway_bot.admin reset-all --yes
```

## Notes
- Twitch does not provide a reliable per-user "viewer list". Presence via IRC membership is the practical solution.
- Very large chats can produce high JOIN/PART traffic. If that becomes an issue, you can switch to message-based activity.
