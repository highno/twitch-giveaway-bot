import asyncio
from datetime import datetime, timezone
from typing import Callable, Awaitable

IRC_HOST = "irc.chat.twitch.tv"
IRC_PORT = 6667

class IRCChat:
    def __init__(self, nick: str, oauth_token: str):
        self.nick = nick
        self.oauth_token = oauth_token
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None

    async def connect(self):
        self.reader, self.writer = await asyncio.open_connection(IRC_HOST, IRC_PORT)
        self._send(f"PASS {self.oauth_token}")
        self._send(f"NICK {self.nick}")
        # membership => JOIN/PART, tags => metadata
        self._send("CAP REQ :twitch.tv/tags twitch.tv/commands twitch.tv/membership")
        await asyncio.sleep(0.2)

    def _send(self, line: str):
        assert self.writer
        self.writer.write((line + "\r\n").encode("utf-8"))

    async def join(self, channel_login: str):
        self._send(f"JOIN #{channel_login}")

    async def listen(
        self,
        on_privmsg: Callable[[dict], Awaitable[None]],
        on_join: Callable[[dict], Awaitable[None]],
        on_part: Callable[[dict], Awaitable[None]],
    ):
        assert self.reader
        while True:
            raw = await self.reader.readline()
            if not raw:
                await asyncio.sleep(0.5)
                continue

            line = raw.decode("utf-8", errors="ignore").strip()

            if line.startswith("PING"):
                self._send("PONG :tmi.twitch.tv")
                continue

            tags = None
            rest = line
            if line.startswith("@") and " " in line:
                tags, rest = line.split(" ", 1)

            if " JOIN #" in rest:
                prefix, chan = rest.split(" JOIN #", 1)
                user_part = prefix.split(":", 1)[-1]
                user_login = user_part.split("!", 1)[0].lower()
                channel = chan.strip().lower()
                await on_join({"channel": channel, "user_login": user_login, "ts": datetime.now(timezone.utc), "tags": tags})
                continue

            if " PART #" in rest:
                prefix, chan = rest.split(" PART #", 1)
                user_part = prefix.split(":", 1)[-1]
                user_login = user_part.split("!", 1)[0].lower()
                channel = chan.strip().lower()
                await on_part({"channel": channel, "user_login": user_login, "ts": datetime.now(timezone.utc), "tags": tags})
                continue

            if " PRIVMSG " in rest:
                prefix, trailing = rest.split(" PRIVMSG ", 1)
                user_part = prefix.split(":", 1)[-1]
                user_login = user_part.split("!", 1)[0].lower()
                chan_part, msg_part = trailing.split(" :", 1)
                channel = chan_part.strip().lstrip("#").lower()
                message = msg_part
                await on_privmsg({
                    "channel": channel,
                    "user_login": user_login,
                    "message": message,
                    "tags": tags,
                    "ts": datetime.now(timezone.utc),
                })
