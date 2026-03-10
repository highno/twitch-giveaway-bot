import asyncio
import base64
import hmac
from datetime import datetime
from html import escape
from typing import Optional

from aiohttp import web

from giveaway_bot.config import Config
from giveaway_bot.db import Database
from giveaway_bot.raffle import run_draw


def parse_dt(value: str) -> Optional[datetime]:
    value = (value or "").strip()
    if not value:
        return None
    return datetime.fromisoformat(value)


def as_iso(value: Optional[datetime]) -> str:
    return value.isoformat(sep=" ") if value else ""


def app_href(request: web.Request, path: str = "") -> str:
    prefix = request.app["base_prefix"]
    suffix = path if path.startswith("/") else f"/{path}" if path else ""
    if prefix:
        return f"{prefix}{suffix}" or "/"
    return suffix or "/"


def nav_html(request: web.Request) -> str:
    return (
        f"<nav>"
        f"<a href='{app_href(request, '/')}' >Dashboard</a>"
        f"<a href='{app_href(request, '/stats')}' >Ticket-Statistik</a>"
        f"<a href='{app_href(request, '/users')}' >User-Details</a>"
        f"<a href='{app_href(request, '/draw')}' >Auslosung</a>"
        f"<a href='{app_href(request, '/draw-runs')}' >Auslosungs-Ergebnisse</a>"
        f"</nav>"
    )


def render_page(request: web.Request, title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang='de'>
<head>
  <meta charset='utf-8'/>
  <meta name='viewport' content='width=device-width, initial-scale=1'/>
  <title>{escape(title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 1.5rem; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
    th, td {{ border: 1px solid #ccc; padding: 0.35rem; text-align: left; vertical-align: top; }}
    th {{ background: #f5f5f5; }}
    nav a {{ margin-right: 1rem; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; }}
    .card {{ border: 1px solid #ddd; padding: 0.75rem; }}
    .error {{ color: #a40000; margin: 0.5rem 0; }}
    .ok {{ color: #056608; margin: 0.5rem 0; }}
    form.inline {{ display: inline; }}
  </style>
</head>
<body>
{nav_html(request)}
{body}
</body>
</html>"""


@web.middleware
async def auth_middleware(request: web.Request, handler):
    auth = request.headers.get("Authorization", "")
    username = request.app["cfg"].admin_web_username
    password = request.app["cfg"].admin_web_password
    expected = "Basic " + base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")

    if not hmac.compare_digest(auth, expected):
        return web.Response(status=401, headers={"WWW-Authenticate": 'Basic realm="Giveaway Admin"'}, text="Unauthorized")
    return await handler(request)


async def dashboard(request: web.Request):
    db: Database = request.app["db"]
    cfg: Config = request.app["cfg"]

    total_minutes = await db.detected_viewer_minutes_total(cfg.ticket_interval_minutes)
    ticket_rows = await db.user_ticket_leaderboard(limit=1)
    all_tickets = await db.user_ticket_leaderboard(limit=100000)
    ticket_total = sum(int(row["tickets"]) for row in all_tickets)

    body = f"""
<h1>Admin Dashboard</h1>
<div class='grid'>
  <div class='card'><b>Erkannte Gesamtzuschauerminuten</b><br>{total_minutes}</div>
  <div class='card'><b>Gesamttickets</b><br>{ticket_total}</div>
  <div class='card'><b>Top User (Tickets)</b><br>{escape(ticket_rows[0]['user_login']) if ticket_rows else '-'}</div>
</div>
"""
    return web.Response(text=render_page(request, "Dashboard", body), content_type="text/html")


async def stats(request: web.Request):
    db: Database = request.app["db"]
    cfg: Config = request.app["cfg"]

    channel_id_raw = request.query.get("channel_id", "")
    error = ""
    try:
        channel_id = int(channel_id_raw or "0")
        start_ts = parse_dt(request.query.get("from", ""))
        end_ts = parse_dt(request.query.get("to", ""))
    except ValueError as exc:
        channel_id = 0
        start_ts = None
        end_ts = None
        error = f"Ungültiger Filter: {escape(str(exc))}"

    rows = await db.ticket_stats_per_user_channel(channel_id=channel_id or None, start_ts=start_ts, end_ts=end_ts)
    minutes_rows = await db.user_minutes_leaderboard(cfg.ticket_interval_minutes, limit=500)
    tickets_rows = await db.user_ticket_leaderboard(limit=500)
    present_rows = await db.currently_present_users(channel_id=channel_id or None)

    stats_rows = "".join(
        f"<tr><td>{escape(row['user_login'])}</td><td>{row['channel_id']}</td><td>{escape(row['channel_login'])}</td><td>{int(row['tickets'])}</td></tr>"
        for row in rows
    )
    mins_rows = "".join(
        f"<tr><td>{escape(row['user_login'])}</td><td>{int(row['minutes'])}</td><td>{int(row['tickets'])}</td></tr>"
        for row in minutes_rows
    )
    ticket_rows = "".join(
        f"<tr><td>{escape(row['user_login'])}</td><td>{int(row['tickets'])}</td></tr>"
        for row in tickets_rows
    )
    present_html = "".join(
        f"<tr><td>{row['channel_id']}</td><td>{escape(row['channel_login'])}</td><td>{escape(row['user_login'])}</td><td>{as_iso(row['joined_at'])}</td></tr>"
        for row in present_rows
    )

    body = f"""
<h1>Statistik</h1>
{f"<p class='error'>{error}</p>" if error else ''}
<form method='get'>
  Kanal-ID: <input name='channel_id' value='{escape(channel_id_raw)}' />
  Von: <input name='from' value='{escape(request.query.get('from',''))}' placeholder='YYYY-MM-DDTHH:MM:SS' />
  Bis: <input name='to' value='{escape(request.query.get('to',''))}' placeholder='YYYY-MM-DDTHH:MM:SS' />
  <button type='submit'>Filtern</button>
</form>
<h2>Aktuell als anwesend erkannte User</h2>
<table><tr><th>Kanal-ID</th><th>Kanal</th><th>User</th><th>Erkannt seit</th></tr>{present_html}</table>
<h2>Tickets pro User/Kanal</h2>
<table><tr><th>User</th><th>Kanal-ID</th><th>Kanal</th><th>Tickets</th></tr>{stats_rows}</table>
<h2>Hitliste erkannte Minuten</h2>
<table><tr><th>User</th><th>Minuten</th><th>Tickets</th></tr>{mins_rows}</table>
<h2>Hitliste Tickets</h2>
<table><tr><th>User</th><th>Tickets</th></tr>{ticket_rows}</table>
"""
    return web.Response(text=render_page(request, "Statistik", body), content_type="text/html")


async def users(request: web.Request):
    db: Database = request.app["db"]

    user_login = request.query.get("user", "").strip().lower()
    channel_id_raw = request.query.get("channel_id", "")
    sort_by = request.query.get("sort", "time")
    if sort_by not in {"time", "channel_time"}:
        sort_by = "time"

    error = ""
    ticket_rows = []
    presence_rows = []
    try:
        channel_id = int(channel_id_raw or "0")
        start_ts = parse_dt(request.query.get("from", ""))
        end_ts = parse_dt(request.query.get("to", ""))
        if user_login:
            ticket_rows = await db.user_ticket_timeline(
                user_login,
                channel_id=channel_id or None,
                start_ts=start_ts,
                end_ts=end_ts,
                sort_by=sort_by,
            )
            presence_rows = await db.user_presence_timeline(
                user_login,
                channel_id=channel_id or None,
                start_ts=start_ts,
                end_ts=end_ts,
                sort_by=sort_by,
            )
    except ValueError as exc:
        channel_id = 0
        error = f"Ungültiger Filter: {escape(str(exc))}"

    ticket_html = "".join(
        f"<tr><td>{row['channel_id']}</td><td>{escape(row['channel_login'])}</td><td>{as_iso(row['bucket_start'])}</td><td>{as_iso(row['issued_at'])}</td><td>{as_iso(row['bucket_start'])} - {as_iso(row['issued_at'])}</td></tr>"
        for row in ticket_rows
    )
    presence_html = "".join(
        f"<tr><td>{row['channel_id']}</td><td>{escape(row['channel_login'])}</td><td>{escape(row['event_type'])}</td><td>{as_iso(row['event_ts'])}</td></tr>"
        for row in presence_rows
    )

    body = f"""
<h1>User-Details</h1>
{f"<p class='error'>{error}</p>" if error else ''}
<form method='get'>
  User: <input name='user' value='{escape(user_login)}' />
  Kanal-ID: <input name='channel_id' value='{escape(channel_id_raw)}' />
  Von: <input name='from' value='{escape(request.query.get('from',''))}' />
  Bis: <input name='to' value='{escape(request.query.get('to',''))}' />
  Sortierung:
  <select name='sort'>
    <option value='time' {'selected' if sort_by == 'time' else ''}>Nur Zeit</option>
    <option value='channel_time' {'selected' if sort_by == 'channel_time' else ''}>Kanal + Zeit</option>
  </select>
  <button type='submit'>Anzeigen</button>
</form>
<h2>Ticket-Timeline</h2>
<table><tr><th>Kanal-ID</th><th>Kanal</th><th>Bucket Start</th><th>Ticket Zeit</th><th>Erkannter Anwesenheitszeitraum</th></tr>{ticket_html}</table>
<h2>Presence-Events (JOIN/PART)</h2>
<table><tr><th>Kanal-ID</th><th>Kanal</th><th>Typ</th><th>Zeit</th></tr>{presence_html}</table>
<p>Hinweis: Der Zeitraum endet i.d.R. mit dem nächsten PART-Event oder Session-Ende; historisch werden hier die erkannten JOIN/PART-Ereignisse angezeigt.</p>
"""
    return web.Response(text=render_page(request, "User", body), content_type="text/html")


async def draw_get(request: web.Request):
    db: Database = request.app["db"]
    sessions = await db.list_sessions(limit=100)
    rows = "".join(
        f"<tr><td><input type='checkbox' name='sessions' value='{session['session_id']}'/></td><td>{session['session_id']}</td><td>{session['channel_id']}</td><td>{as_iso(session['started_at'])}</td><td>{as_iso(session['ended_at'])}</td><td>{escape(str(session['title'] or ''))}</td></tr>"
        for session in sessions
    )
    body = f"""
<h1>Auslosung</h1>
<form method='post' action='{app_href(request, '/draw')}'>
  Beschreibung: <input name='desc' />
  Gewinner: <input name='winners' value='1' />
  <label><input type='checkbox' name='exclude_previous_winners' value='1'/> Frühere Gewinner ausschließen</label>
  <table><tr><th></th><th>Session</th><th>Kanal</th><th>Start</th><th>Ende</th><th>Titel</th></tr>{rows}</table>
  <button type='submit'>Auslosen</button>
</form>
"""
    return web.Response(text=render_page(request, "Auslosung", body), content_type="text/html")


async def draw_post(request: web.Request):
    db: Database = request.app["db"]
    data = await request.post()

    sessions = [int(value) for value in data.getall("sessions", [])]
    if not sessions:
        raise web.HTTPBadRequest(reason="Mindestens eine Session muss ausgewählt werden.")

    winners = int(data.get("winners", "1") or "1")
    if winners <= 0:
        raise web.HTTPBadRequest(reason="Gewinner-Anzahl muss größer als 0 sein.")

    desc = data.get("desc", "")
    exclude = data.get("exclude_previous_winners") == "1"

    try:
        draw_id, picks = await run_draw(
            db,
            session_ids=sessions,
            winners=winners,
            description=desc,
            exclude_past_winners=exclude,
        )
    except ValueError as exc:
        raise web.HTTPBadRequest(reason=str(exc)) from exc

    pick_rows = "".join(f"<li>{escape(user)} (Tickets: {weight})</li>" for user, weight in picks)
    body = (
        f"<h1>Auslosung abgeschlossen</h1>"
        f"<p>draw_id={draw_id}</p><ul>{pick_rows}</ul>"
        f"<p><a href='{app_href(request, '/draw-runs')}'>Zu den Auslosungsergebnissen</a></p>"
    )
    return web.Response(text=render_page(request, "Auslosung abgeschlossen", body), content_type="text/html")


async def draw_runs(request: web.Request):
    db: Database = request.app["db"]
    runs = await db.draw_runs(limit=200)
    rows = []
    for run in runs:
        winners = await db.draw_winners(run["draw_id"])
        winner_list = ", ".join(f"{winner['user_login']} ({winner['weight_tickets']})" for winner in winners) or "-"
        rows.append(
            f"<tr><td>{run['draw_id']}</td><td>{as_iso(run['created_at'])}</td><td>{escape(str(run['description'] or ''))}</td><td>{escape(winner_list)}</td>"
            f"<td><form class='inline' method='post' action='{app_href(request, '/draw-runs/delete')}'><input type='hidden' name='draw_id' value='{run['draw_id']}'/><button type='submit'>Löschen</button></form></td></tr>"
        )
    body = f"<h1>Auslosungsergebnisse</h1><table><tr><th>Draw ID</th><th>Zeit</th><th>Beschreibung</th><th>Gewinner</th><th>Aktion</th></tr>{''.join(rows)}</table>"
    return web.Response(text=render_page(request, "Auslosungen", body), content_type="text/html")


async def draw_runs_delete(request: web.Request):
    db: Database = request.app["db"]
    data = await request.post()
    draw_id = int(data.get("draw_id", "0") or "0")
    if draw_id:
        await db.delete_draw(draw_id)
    raise web.HTTPFound(app_href(request, "/draw-runs"))


async def create_app() -> web.Application:
    cfg = Config()
    db = Database(cfg.mysql_host, cfg.mysql_port, cfg.mysql_user, cfg.mysql_password, cfg.mysql_db)
    await db.connect()

    app = web.Application(middlewares=[auth_middleware])
    app["cfg"] = cfg
    app["db"] = db

    base_path = cfg.admin_web_base_path.strip() or "/"
    if not base_path.startswith("/"):
        base_path = "/" + base_path
    base_path = base_path.rstrip("/") or "/"
    prefix = "" if base_path == "/" else base_path
    app["base_prefix"] = prefix

    app.router.add_get(prefix + "/", dashboard)
    app.router.add_get(prefix + "/stats", stats)
    app.router.add_get(prefix + "/users", users)
    app.router.add_get(prefix + "/draw", draw_get)
    app.router.add_post(prefix + "/draw", draw_post)
    app.router.add_get(prefix + "/draw-runs", draw_runs)
    app.router.add_post(prefix + "/draw-runs/delete", draw_runs_delete)

    async def on_cleanup(_app: web.Application):
        await db.close()

    app.on_cleanup.append(on_cleanup)
    return app


async def amain():
    app = await create_app()
    cfg: Config = app["cfg"]
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, cfg.admin_web_host, cfg.admin_web_port)
    await site.start()
    print(f"Admin-Web läuft auf http://{cfg.admin_web_host}:{cfg.admin_web_port}{cfg.admin_web_base_path}")
    while True:
        await asyncio.sleep(3600)


def main():
    asyncio.run(amain())


if __name__ == "__main__":
    main()
