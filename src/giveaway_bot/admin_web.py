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


def local_dt_span(value: Optional[datetime]) -> str:
    raw = as_iso(value)
    if not raw:
        return "-"
    safe = escape(raw)
    return f"<span class='js-local-dt' data-utc-datetime='{safe}'>{safe}</span>"


def app_href(request: web.Request, path: str = "") -> str:
    prefix = request.app["base_prefix"]
    suffix = path if path.startswith("/") else f"/{path}" if path else ""
    if prefix:
        return f"{prefix}{suffix}" or "/"
    return suffix or "/"


def nav_html(request: web.Request) -> str:
    return (
        "<nav class='top-nav'>"
        f"<a href='{app_href(request, '/')}' >Dashboard</a>"
        f"<a href='{app_href(request, '/stats')}' >Ticket-Statistik</a>"
        f"<a href='{app_href(request, '/users')}' >User-Details</a>"
        f"<a href='{app_href(request, '/draw')}' >Auslosung</a>"
        f"<a href='{app_href(request, '/draw-runs')}' >Auslosungs-Ergebnisse</a>"
        "<button type='button' id='theme-toggle' class='theme-toggle'>🌙 Dark</button>"
        "</nav>"
    )


def render_page(request: web.Request, title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang='de'>
<head>
  <meta charset='utf-8'/>
  <meta name='viewport' content='width=device-width, initial-scale=1'/>
  <title>{escape(title)}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0f1624;
      --panel: #172033;
      --panel-border: #2a3753;
      --text: #ecf1fb;
      --muted: #9eb0cc;
      --accent: #8b9dff;
      --accent-soft: #2a3656;
      --danger: #ff8b8b;
      --ok: #5bd9a1;
      --card-bg: #1b2740;
      --input-bg: #121b2d;
      --th-bg: #1f2b43;
      --th-text: #c8d5ed;
      --sort-indicator: #7f92b6;
    }}

    :root[data-theme='light'] {{
      color-scheme: light;
      --bg: #f3f5f9;
      --panel: #ffffff;
      --panel-border: #dde3ee;
      --text: #182230;
      --muted: #5c6b82;
      --accent: #5b6bff;
      --accent-soft: #edf0ff;
      --danger: #b42318;
      --ok: #067647;
      --card-bg: #fcfdff;
      --input-bg: #ffffff;
      --th-bg: #f8f9fc;
      --th-text: #243447;
      --sort-indicator: #90a0b8;
    }}

    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    .page {{ max-width: 1300px; margin: 0 auto; padding: 1.25rem; }}
    h1 {{ margin: 0 0 1rem; font-size: 1.7rem; }}
    h2 {{ margin: 1.25rem 0 0.75rem; font-size: 1.2rem; }}

    .top-nav {{
      display: flex;
      gap: 0.5rem;
      flex-wrap: wrap;
      background: var(--panel);
      border: 1px solid var(--panel-border);
      border-radius: 12px;
      padding: 0.65rem;
      margin-bottom: 1rem;
    }}
    .top-nav a {{
      text-decoration: none;
      color: var(--text);
      font-weight: 600;
      border-radius: 8px;
      padding: 0.45rem 0.75rem;
    }}
    .top-nav a:hover {{ background: var(--accent-soft); color: var(--accent); }}
    .theme-toggle {{ margin-left: auto; }}

    .panel {{
      background: var(--panel);
      border: 1px solid var(--panel-border);
      border-radius: 12px;
      padding: 1rem;
      margin-bottom: 1rem;
      overflow: auto;
    }}

    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; }}
    .card {{
      border: 1px solid var(--panel-border);
      border-radius: 10px;
      padding: 0.9rem;
      background: var(--card-bg);
    }}
    .metric-value {{ font-size: 1.6rem; font-weight: 700; margin-top: 0.35rem; }}

    form {{ display: grid; gap: 0.75rem; }}
    .form-grid {{ display: grid; gap: 0.75rem; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }}
    .field {{ display: flex; flex-direction: column; gap: 0.35rem; }}
    label {{ font-size: 0.88rem; color: var(--muted); font-weight: 600; }}
    input, select, button {{
      font: inherit;
      border-radius: 8px;
      border: 1px solid var(--panel-border);
      background: var(--input-bg);
      color: var(--text);
      padding: 0.5rem 0.65rem;
      min-height: 2.2rem;
    }}
    button {{ cursor: pointer; font-weight: 600; }}
    button.primary {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
    .inline {{ display: inline; }}

    .error {{ color: var(--danger); margin: 0.5rem 0; font-weight: 600; }}
    .ok {{ color: var(--ok); margin: 0.5rem 0; font-weight: 600; }}

    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 0.55rem; border-bottom: 1px solid var(--panel-border); vertical-align: top; }}
    th {{
      background: var(--th-bg);
      text-align: left;
      font-size: 0.9rem;
      white-space: nowrap;
      color: var(--th-text);
    }}
    th.sortable {{ cursor: pointer; user-select: none; }}
    th.sortable::after {{ content: " ↕"; color: var(--sort-indicator); font-size: 0.85em; }}

    .table-wrap {{ overflow: auto; }}
    .table-footer {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-top: 0.6rem;
      gap: 0.6rem;
      flex-wrap: wrap;
      color: var(--muted);
      font-size: 0.9rem;
    }}

    .hint {{ color: var(--muted); font-size: 0.9rem; }}
    .checkbox {{ display: flex; align-items: center; gap: 0.5rem; font-size: 0.95rem; }}
  </style>
</head>
<body>
<div class='page'>
{nav_html(request)}
{body}
</div>
<script>
(function() {{
  function applyTheme() {{
    const root = document.documentElement;
    const stored = localStorage.getItem('admin-theme');
    const theme = stored === 'light' ? 'light' : 'dark';
    root.dataset.theme = theme;
    const btn = document.getElementById('theme-toggle');
    if (btn) btn.textContent = theme === 'dark' ? '☀️ Light' : '🌙 Dark';
  }}

  function formatLocalDateTimes() {{
    document.querySelectorAll('.js-local-dt').forEach((node) => {{
      const raw = (node.dataset.utcDatetime || '').trim();
      if (!raw) return;
      const dt = new Date(raw.replace(' ', 'T') + 'Z');
      if (Number.isNaN(dt.getTime())) return;
      node.textContent = dt.toLocaleString('de-DE');
      node.dataset.sortValue = String(dt.getTime());
      node.title = `UTC: ${raw}`;
    }});
  }}

  function parseValue(value, type) {{
    const v = (value || '').trim();
    if (type === 'number') {{
      const n = Number(v.replace(',', '.'));
      return Number.isNaN(n) ? Number.NEGATIVE_INFINITY : n;
    }}
    if (type === 'datetime') {{
      const timestamp = Number(v);
      if (!Number.isNaN(timestamp) && timestamp > 0) return timestamp;
      const t = Date.parse(v.replace(' ', 'T'));
      return Number.isNaN(t) ? 0 : t;
    }}
    return v.toLowerCase();
  }}

  applyTheme();
  document.getElementById('theme-toggle')?.addEventListener('click', () => {{
    const root = document.documentElement;
    const next = root.dataset.theme === 'light' ? 'dark' : 'light';
    localStorage.setItem('admin-theme', next);
    applyTheme();
  }});
  formatLocalDateTimes();

  document.querySelectorAll('table[data-enhanced="1"]').forEach((table) => {{
    const tbody = table.querySelector('tbody');
    if (!tbody) return;
    const rows = Array.from(tbody.querySelectorAll('tr'));
    const pageSize = Math.max(1, Number(table.dataset.pageSize || 25));
    const defaultSortIndex = table.dataset.defaultSortIndex;
    const defaultSortType = table.dataset.defaultSortType || 'text';
    const defaultSortDir = table.dataset.defaultSortDir === 'asc' ? 'asc' : 'desc';
    let page = 1;

    const wrapper = table.closest('.table-wrap') || table.parentElement;
    const footer = document.createElement('div');
    footer.className = 'table-footer';
    footer.innerHTML = `<span class='table-info'></span><div><button type='button' class='prev'>← Zurück</button> <button type='button' class='next'>Weiter →</button></div>`;
    wrapper.appendChild(footer);

    function renderPage() {{
      const maxPage = Math.max(1, Math.ceil(rows.length / pageSize));
      page = Math.min(Math.max(1, page), maxPage);
      const start = (page - 1) * pageSize;
      const end = start + pageSize;
      rows.forEach((row, idx) => {{ row.style.display = (idx >= start && idx < end) ? '' : 'none'; }});
      footer.querySelector('.table-info').textContent = `Seite ${{page}} / ${{maxPage}} · ${{rows.length}} Zeilen`;
      footer.querySelector('.prev').disabled = page <= 1;
      footer.querySelector('.next').disabled = page >= maxPage;
    }}

    footer.querySelector('.prev').addEventListener('click', () => {{ page -= 1; renderPage(); }});
    footer.querySelector('.next').addEventListener('click', () => {{ page += 1; renderPage(); }});

    function sortTable(idx, type, asc) {{
      rows.sort((a, b) => {{
        const av = parseValue((a.children[idx]?.dataset.sortValue || a.children[idx]?.innerText || ''), type);
        const bv = parseValue((b.children[idx]?.dataset.sortValue || b.children[idx]?.innerText || ''), type);
        if (av === bv) return 0;
        if (av > bv) return asc ? 1 : -1;
        return asc ? -1 : 1;
      }});
      rows.forEach((row) => tbody.appendChild(row));
      page = 1;
      renderPage();
    }}

    table.querySelectorAll('th[data-sort-index]').forEach((th) => {{
      th.classList.add('sortable');
      th.addEventListener('click', () => {{
        const idx = Number(th.dataset.sortIndex);
        const type = th.dataset.sortType || 'text';
        const asc = th.dataset.sortDir !== 'asc';
        table.querySelectorAll('th[data-sort-index]').forEach((h) => delete h.dataset.sortDir);
        th.dataset.sortDir = asc ? 'asc' : 'desc';
        sortTable(idx, type, asc);
      }});
    }});

    if (defaultSortIndex !== undefined) {{
      const idx = Number(defaultSortIndex);
      if (!Number.isNaN(idx)) {{
        const th = table.querySelector(`th[data-sort-index="${{idx}}"]`);
        if (th) th.dataset.sortDir = defaultSortDir;
        sortTable(idx, defaultSortType, defaultSortDir === 'asc');
        return;
      }}
    }}

    renderPage();
  }});
}})();
</script>
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


def channel_options(channels: list[dict], selected: str = "") -> str:
    options = ["<option value=''>Alle Kanäle</option>"]
    for channel in channels:
        cid = str(channel["id"])
        marker = " selected" if cid == selected else ""
        label = escape(channel["login"])
        options.append(f"<option value='{cid}'{marker}>{cid} · {label}</option>")
    return "".join(options)


def user_datalist(users: list[str], datalist_id: str) -> str:
    options = "".join(f"<option value='{escape(user)}'></option>" for user in users)
    return f"<datalist id='{datalist_id}'>{options}</datalist>"


async def dashboard(request: web.Request):
    db: Database = request.app["db"]
    cfg: Config = request.app["cfg"]

    total_minutes = await db.detected_viewer_minutes_total(cfg.ticket_interval_minutes)
    ticket_rows = await db.user_ticket_leaderboard(limit=1)
    all_tickets = await db.user_ticket_leaderboard(limit=100000)
    ticket_total = sum(int(row["tickets"]) for row in all_tickets)

    body = f"""
<div class='panel'>
  <h1>Admin Dashboard</h1>
  <div class='grid'>
    <div class='card'><div>Erkannte Gesamtzuschauerminuten</div><div class='metric-value'>{total_minutes}</div></div>
    <div class='card'><div>Gesamttickets</div><div class='metric-value'>{ticket_total}</div></div>
    <div class='card'><div>Top User (Tickets)</div><div class='metric-value'>{escape(ticket_rows[0]['user_login']) if ticket_rows else '-'}</div></div>
  </div>
</div>

<div class='panel'>
  <h2>Gesammelte Tickets pro User</h2>
  <p class='hint'>Initial nach Ticketanzahl sortiert, alternativ nach Username sortierbar.</p>
  <div class='table-wrap'>
    <table data-enhanced='1' data-page-size='25' data-default-sort-index='1' data-default-sort-type='number' data-default-sort-dir='desc'>
      <thead>
        <tr>
          <th data-sort-index='0'>User</th>
          <th data-sort-index='1' data-sort-type='number'>Tickets</th>
        </tr>
      </thead>
      <tbody>{''.join(f"<tr><td>{escape(row['user_login'])}</td><td data-sort-value='{int(row['tickets'])}'>{int(row['tickets'])}</td></tr>" for row in all_tickets)}</tbody>
    </table>
  </div>
</div>
"""
    return web.Response(text=render_page(request, "Dashboard", body), content_type="text/html")


async def stats(request: web.Request):
    db: Database = request.app["db"]
    cfg: Config = request.app["cfg"]

    channels = await db.list_channels()
    users = await db.list_known_users(limit=2000)
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
    minutes_rows = await db.user_minutes_leaderboard(cfg.ticket_interval_minutes, limit=1000)
    tickets_rows = await db.user_ticket_leaderboard(limit=1000)
    present_rows = await db.currently_present_users(channel_id=channel_id or None)

    stats_rows = "".join(
        f"<tr><td>{escape(row['user_login'])}</td><td data-sort-value='{row['channel_id']}'>{row['channel_id']}</td>"
        f"<td>{escape(row['channel_login'])}</td><td data-sort-value='{int(row['tickets'])}'>{int(row['tickets'])}</td></tr>"
        for row in rows
    )
    mins_rows = "".join(
        f"<tr><td>{escape(row['user_login'])}</td><td data-sort-value='{int(row['minutes'])}'>{int(row['minutes'])}</td>"
        f"<td data-sort-value='{int(row['tickets'])}'>{int(row['tickets'])}</td></tr>"
        for row in minutes_rows
    )
    ticket_rows = "".join(
        f"<tr><td>{escape(row['user_login'])}</td><td data-sort-value='{int(row['tickets'])}'>{int(row['tickets'])}</td></tr>"
        for row in tickets_rows
    )
    present_html = "".join(
        f"<tr><td data-sort-value='{row['channel_id']}'>{row['channel_id']}</td><td>{escape(row['channel_login'])}</td>"
        f"<td>{escape(row['user_login'])}</td><td data-sort-value='{as_iso(row['joined_at'])}'>{local_dt_span(row['joined_at'])}</td></tr>"
        for row in present_rows
    )

    body = f"""
<div class='panel'>
<h1>Statistik</h1>
{f"<p class='error'>{error}</p>" if error else ''}
<form method='get'>
  <div class='form-grid'>
    <div class='field'><label>Kanal</label><select name='channel_id'>{channel_options(channels, channel_id_raw)}</select></div>
    <div class='field'><label>Von</label><input type='datetime-local' name='from' value='{escape(request.query.get('from',''))}' /></div>
    <div class='field'><label>Bis</label><input type='datetime-local' name='to' value='{escape(request.query.get('to',''))}' /></div>
  </div>
  <div><button class='primary' type='submit'>Filtern</button></div>
</form>
</div>

<div class='panel'>
<h2>Aktuell als anwesend erkannte User</h2>
<div class='table-wrap'>
<table data-enhanced='1' data-page-size='20'><thead><tr><th data-sort-index='0' data-sort-type='number'>Kanal-ID</th><th data-sort-index='1'>Kanal</th><th data-sort-index='2'>User</th><th data-sort-index='3' data-sort-type='datetime'>Erkannt seit</th></tr></thead><tbody>{present_html}</tbody></table>
</div>
</div>

<div class='panel'>
<h2>Tickets pro User/Kanal</h2>
<div class='table-wrap'>
<table data-enhanced='1' data-page-size='25'><thead><tr><th data-sort-index='0'>User</th><th data-sort-index='1' data-sort-type='number'>Kanal-ID</th><th data-sort-index='2'>Kanal</th><th data-sort-index='3' data-sort-type='number'>Tickets</th></tr></thead><tbody>{stats_rows}</tbody></table>
</div>
</div>

<div class='panel'>
<h2>Hitliste erkannte Minuten</h2>
<div class='table-wrap'>
<table data-enhanced='1' data-page-size='25'><thead><tr><th data-sort-index='0'>User</th><th data-sort-index='1' data-sort-type='number'>Minuten</th><th data-sort-index='2' data-sort-type='number'>Tickets</th></tr></thead><tbody>{mins_rows}</tbody></table>
</div>
</div>

<div class='panel'>
<h2>Hitliste Tickets</h2>
<div class='table-wrap'>
<table data-enhanced='1' data-page-size='25'><thead><tr><th data-sort-index='0'>User</th><th data-sort-index='1' data-sort-type='number'>Tickets</th></tr></thead><tbody>{ticket_rows}</tbody></table>
</div>
{user_datalist(users, 'known-users-stats')}
</div>
"""
    return web.Response(text=render_page(request, "Statistik", body), content_type="text/html")


async def users(request: web.Request):
    db: Database = request.app["db"]

    channels = await db.list_channels()
    known_users = await db.list_known_users(limit=3000)
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
        error = f"Ungültiger Filter: {escape(str(exc))}"

    ticket_html = "".join(
        f"<tr><td data-sort-value='{row['channel_id']}'>{row['channel_id']}</td><td>{escape(row['channel_login'])}</td>"
        f"<td data-sort-value='{as_iso(row['bucket_start'])}'>{local_dt_span(row['bucket_start'])}</td><td data-sort-value='{as_iso(row['issued_at'])}'>{local_dt_span(row['issued_at'])}</td>"
        f"<td>{local_dt_span(row['bucket_start'])} - {local_dt_span(row['issued_at'])}</td></tr>"
        for row in ticket_rows
    )
    presence_html = "".join(
        f"<tr><td data-sort-value='{row['channel_id']}'>{row['channel_id']}</td><td>{escape(row['channel_login'])}</td>"
        f"<td>{escape(row['event_type'])}</td><td data-sort-value='{as_iso(row['event_ts'])}'>{local_dt_span(row['event_ts'])}</td></tr>"
        for row in presence_rows
    )

    body = f"""
<div class='panel'>
<h1>User-Details</h1>
{f"<p class='error'>{error}</p>" if error else ''}
<form method='get'>
  <div class='form-grid'>
    <div class='field'><label>User</label><input name='user' value='{escape(user_login)}' list='known-users' placeholder='Username wählen oder eingeben' /></div>
    <div class='field'><label>Kanal</label><select name='channel_id'>{channel_options(channels, channel_id_raw)}</select></div>
    <div class='field'><label>Von</label><input type='datetime-local' name='from' value='{escape(request.query.get('from',''))}' /></div>
    <div class='field'><label>Bis</label><input type='datetime-local' name='to' value='{escape(request.query.get('to',''))}' /></div>
    <div class='field'><label>Sortierung</label>
      <select name='sort'>
        <option value='time' {'selected' if sort_by == 'time' else ''}>Nur Zeit</option>
        <option value='channel_time' {'selected' if sort_by == 'channel_time' else ''}>Kanal + Zeit</option>
      </select>
    </div>
  </div>
  <div><button class='primary' type='submit'>Anzeigen</button></div>
</form>
{user_datalist(known_users, 'known-users')}
</div>

<div class='panel'>
<h2>Ticket-Timeline</h2>
<div class='table-wrap'>
<table data-enhanced='1' data-page-size='25'><thead><tr><th data-sort-index='0' data-sort-type='number'>Kanal-ID</th><th data-sort-index='1'>Kanal</th><th data-sort-index='2' data-sort-type='datetime'>Bucket Start</th><th data-sort-index='3' data-sort-type='datetime'>Ticket Zeit</th><th data-sort-index='4'>Erkannter Anwesenheitszeitraum</th></tr></thead><tbody>{ticket_html}</tbody></table>
</div>
</div>

<div class='panel'>
<h2>Presence-Events (JOIN/PART)</h2>
<div class='table-wrap'>
<table data-enhanced='1' data-page-size='25'><thead><tr><th data-sort-index='0' data-sort-type='number'>Kanal-ID</th><th data-sort-index='1'>Kanal</th><th data-sort-index='2'>Typ</th><th data-sort-index='3' data-sort-type='datetime'>Zeit</th></tr></thead><tbody>{presence_html}</tbody></table>
</div>
<p class='hint'>Hinweis: Der Zeitraum endet i.d.R. mit dem nächsten PART-Event oder Session-Ende; historisch werden hier die erkannten JOIN/PART-Ereignisse angezeigt.</p>
</div>
"""
    return web.Response(text=render_page(request, "User", body), content_type="text/html")


async def draw_get(request: web.Request):
    db: Database = request.app["db"]
    sessions = await db.list_sessions(limit=300)
    rows = "".join(
        f"<tr><td><input type='checkbox' name='sessions' value='{session['session_id']}'/></td><td data-sort-value='{session['session_id']}'>{session['session_id']}</td>"
        f"<td data-sort-value='{session['channel_id']}'>{session['channel_id']}</td><td data-sort-value='{as_iso(session['started_at'])}'>{local_dt_span(session['started_at'])}</td>"
        f"<td data-sort-value='{as_iso(session['ended_at'])}'>{local_dt_span(session['ended_at'])}</td><td>{escape(str(session['title'] or ''))}</td></tr>"
        for session in sessions
    )
    body = f"""
<div class='panel'>
<h1>Auslosung</h1>
<form method='post' action='{app_href(request, '/draw')}'>
  <div class='form-grid'>
    <div class='field'><label>Beschreibung</label><input name='desc' /></div>
    <div class='field'><label>Gewinner</label><input type='number' min='1' name='winners' value='1' /></div>
  </div>
  <label class='checkbox'><input type='checkbox' name='exclude_previous_winners' value='1'/> Frühere Gewinner ausschließen</label>
  <div class='table-wrap'>
    <table data-enhanced='1' data-page-size='30'><thead><tr><th data-sort-index='0'></th><th data-sort-index='1' data-sort-type='number'>Session</th><th data-sort-index='2' data-sort-type='number'>Kanal</th><th data-sort-index='3' data-sort-type='datetime'>Start</th><th data-sort-index='4' data-sort-type='datetime'>Ende</th><th data-sort-index='5'>Titel</th></tr></thead><tbody>{rows}</tbody></table>
  </div>
  <div><button class='primary' type='submit'>Auslosen</button></div>
</form>
</div>
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
        "<div class='panel'>"
        f"<h1>Auslosung abgeschlossen</h1><p>draw_id={draw_id}</p><ul>{pick_rows}</ul>"
        f"<p><a href='{app_href(request, '/draw-runs')}'>Zu den Auslosungsergebnissen</a></p>"
        "</div>"
    )
    return web.Response(text=render_page(request, "Auslosung abgeschlossen", body), content_type="text/html")


async def draw_runs(request: web.Request):
    db: Database = request.app["db"]
    runs = await db.draw_runs(limit=500)
    rows = []
    for run in runs:
        winners = await db.draw_winners(run["draw_id"])
        winner_list = ", ".join(f"{winner['user_login']} ({winner['weight_tickets']})" for winner in winners) or "-"
        rows.append(
            f"<tr><td data-sort-value='{run['draw_id']}'>{run['draw_id']}</td><td data-sort-value='{as_iso(run['created_at'])}'>{local_dt_span(run['created_at'])}</td>"
            f"<td>{escape(str(run['description'] or ''))}</td><td>{escape(winner_list)}</td>"
            f"<td><form class='inline' method='post' action='{app_href(request, '/draw-runs/delete')}'><input type='hidden' name='draw_id' value='{run['draw_id']}'/><button type='submit'>Löschen</button></form></td></tr>"
        )
    body = (
        "<div class='panel'><h1>Auslosungsergebnisse</h1><div class='table-wrap'>"
        "<table data-enhanced='1' data-page-size='30'><thead><tr><th data-sort-index='0' data-sort-type='number'>Draw ID</th><th data-sort-index='1' data-sort-type='datetime'>Zeit</th><th data-sort-index='2'>Beschreibung</th><th data-sort-index='3'>Gewinner</th><th>Aktion</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div></div>"
    )
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
