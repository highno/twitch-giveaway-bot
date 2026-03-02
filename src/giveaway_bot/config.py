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
