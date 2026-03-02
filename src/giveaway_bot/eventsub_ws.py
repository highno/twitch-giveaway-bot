import json
import aiohttp
import websockets
from typing import Callable, Awaitable, Optional

DEFAULT_WS_URL = "wss://eventsub.wss.twitch.tv/ws"

class EventSubWS:
    def __init__(self, client_id: str, token_manager):
        self.client_id = client_id
        self.token_manager = token_manager
        self.session_id: Optional[str] = None

    async def create_subscription(self, sub_type: str, version: str, condition: dict):
        token = await self.token_manager.ensure_fresh()
        headers = {
            "Client-Id": self.client_id,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        body = {
            "type": sub_type,
            "version": version,
            "condition": condition,
            "transport": {"method": "websocket", "session_id": self.session_id},
        }
        async with aiohttp.ClientSession() as s:
            async with s.post("https://api.twitch.tv/helix/eventsub/subscriptions", headers=headers, json=body) as r:
                data = await r.json()
                if r.status not in (200, 202):
                    raise RuntimeError(f"create_subscription failed {r.status}: {data}")
                return data

    async def run(
        self,
        on_msg: Callable[[dict], Awaitable[None]],
        subscribe_fn: Callable[[], Awaitable[None]],
    ):
        ws_url = DEFAULT_WS_URL
        while True:
            async with websockets.connect(ws_url) as ws:
                welcome = json.loads(await ws.recv())
                if welcome.get("metadata", {}).get("message_type") != "session_welcome":
                    raise RuntimeError(f"Expected session_welcome, got {welcome}")
                self.session_id = welcome["payload"]["session"]["id"]

                await self.token_manager.ensure_fresh()
                await subscribe_fn()

                while True:
                    raw = await ws.recv()
                    msg = json.loads(raw)
                    mtype = msg.get("metadata", {}).get("message_type")

                    if mtype == "session_reconnect":
                        ws_url = msg["payload"]["session"]["reconnect_url"]
                        await on_msg(msg)
                        break  # reconnect outer loop

                    await on_msg(msg)
