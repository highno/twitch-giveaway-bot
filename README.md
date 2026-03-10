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
mysql -u bot -p twitch_giveaway < migrations/004_presence_events.sql
```

## Run
```bash
PYTHONPATH=src python -m giveaway_bot.bot
```

Optional ohne Logdatei:
```bash
PYTHONPATH=src python -m giveaway_bot.bot --no-log
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

Frühere Gewinner optional ausschließen:
```bash
PYTHONPATH=src python -m giveaway_bot.draw --sessions 101,105,106 --winners 3 --exclude-previous-winners
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


## Chat-Kommandos
- `OPTIN_CODEWORD`: Einmalige globale Teilnahme.
- `COMMAND_TICKET_COUNT`: Ticketstand abrufen (vorher hartkodiert als `Anzahl_Tickets`).
- `COMMAND_PAUSE_PARTICIPATION`: Temporärer Ausstieg (keine neuen Tickets).
- `COMMAND_DELETE_USER_DATA`: Löscht alle User-Daten, nur nach temporärem Ausstieg erlaubt.

Alle Bot-Antworten auf diese Kommandos sind über `RESPONSE_*` Variablen in `.env` anpassbar.


## Admin Webservice
Start:
```bash
PYTHONPATH=src python -m giveaway_bot.admin_web
```

Features:
- HTTP Basic Auth via `.env` (`ADMIN_WEB_USERNAME`, `ADMIN_WEB_PASSWORD`)
- Port/Host konfigurierbar (`ADMIN_WEB_HOST`, `ADMIN_WEB_PORT`)
- Frei wählbarer Root-Pfad (`ADMIN_WEB_BASE_PATH`, z. B. `/admin` hinter TLS-Proxy)
- Filterbare Statistik wie im CLI inkl. Liste aktuell als anwesend erkannter User pro Kanal
- User-Detailansicht mit Ticket-Timeline + JOIN/PART-Presence-Events (soweit technisch erfassbar)
- Auslosung inkl. Option „frühere Gewinner ausschließen“
- Auslosungsergebnisse im Web löschbar (für Test-/Wiederholungsfälle)
