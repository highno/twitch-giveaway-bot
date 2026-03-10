import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

def _req(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing env var: {name}")
    return v

def _bool(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")

@dataclass(frozen=True)
class Config:
    mysql_host: str = _req("MYSQL_HOST")
    mysql_port: int = int(os.getenv("MYSQL_PORT", "3306"))
    mysql_user: str = _req("MYSQL_USER")
    mysql_password: str = _req("MYSQL_PASSWORD")
    mysql_db: str = _req("MYSQL_DB")

    twitch_client_id: str = _req("TWITCH_CLIENT_ID")
    twitch_client_secret: str = _req("TWITCH_CLIENT_SECRET")

    twitch_user_access_token: str = _req("TWITCH_USER_ACCESS_TOKEN")
    twitch_user_refresh_token: str = os.getenv("TWITCH_USER_REFRESH_TOKEN", "").strip()

    channel_logins: list[str] = None

    bot_nick: str = _req("BOT_NICK")
    irc_oauth_token: str = _req("IRC_OAUTH_TOKEN")

    optin_codeword: str = _req("OPTIN_CODEWORD").strip().lower()
    command_ticket_count: str = os.getenv("COMMAND_TICKET_COUNT", "Anzahl_Tickets").strip().lower()
    command_pause_participation: str = os.getenv("COMMAND_PAUSE_PARTICIPATION", "Ausstieg").strip().lower()
    command_delete_user_data: str = os.getenv("COMMAND_DELETE_USER_DATA", "Ausstieg_Loeschen").strip().lower()

    response_optin_success: str = os.getenv(
        "RESPONSE_OPTIN_SUCCESS",
        "@{user} Du nimmst jetzt an der Verlosung teil. Mit '{ticket_count_command}' siehst du jederzeit deinen Stand (aktuell: {tickets}).",
    )
    response_not_registered: str = os.getenv(
        "RESPONSE_NOT_REGISTERED",
        "@{user} Du bist noch nicht registriert. Schreibe '{optin_codeword}', um teilzunehmen.",
    )
    response_ticket_count: str = os.getenv(
        "RESPONSE_TICKET_COUNT",
        "@{user} Du hast aktuell {tickets} Ticket(s) im Lostopf.",
    )
    response_pause_success: str = os.getenv(
        "RESPONSE_PAUSE_SUCCESS",
        "@{user} Du bist vorübergehend aus dem Wettbewerb ausgestiegen. Mit '{delete_user_data_command}' kannst du anschließend alle deine Daten löschen.",
    )
    response_pause_not_active: str = os.getenv(
        "RESPONSE_PAUSE_NOT_ACTIVE",
        "@{user} Du bist derzeit nicht aktiv im Wettbewerb.",
    )
    response_delete_success: str = os.getenv(
        "RESPONSE_DELETE_SUCCESS",
        "@{user} Deine gespeicherten Daten wurden gelöscht.",
    )
    response_delete_requires_pause: str = os.getenv(
        "RESPONSE_DELETE_REQUIRES_PAUSE",
        "@{user} Das Löschen ist erst nach einem vorübergehenden Ausstieg mit '{pause_command}' möglich.",
    )

    ticket_interval_minutes: int = int(os.getenv("TICKET_INTERVAL_MINUTES", "10"))

    ignored_logins: set[str] = None
    ignore_verified_bots: bool = _bool("IGNORE_VERIFIED_BOTS", "1")

    def __post_init__(self):
        object.__setattr__(
            self,
            "channel_logins",
            [c.strip().lower() for c in _req("CHANNEL_LOGINS").split(",") if c.strip()],
        )
        ignored = os.getenv("IGNORED_LOGINS", "")
        default_ignored = {
            "streamelements", "nightbot", "moobot", "streamlabs", "wizebot", "commanderroot",
        }
        env_ignored = {x.strip().lower() for x in ignored.split(",") if x.strip()}
        object.__setattr__(self, "ignored_logins", default_ignored | env_ignored)
