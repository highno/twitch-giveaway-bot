import aiohttp
from typing import Any, Optional

class TwitchAPI:
    """Minimal Helix client using an App Access Token (client_credentials)."""

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self._app_token: Optional[str] = None

    async def _get_app_token(self) -> str:
        if self._app_token:
            return self._app_token
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://id.twitch.tv/oauth2/token",
                params={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "client_credentials",
                },
            ) as r:
                data = await r.json()
                if r.status != 200:
                    raise RuntimeError(f"App token error {r.status}: {data}")
                self._app_token = data["access_token"]
                return self._app_token

    async def get_users_by_logins(self, logins: list[str]) -> list[dict[str, Any]]:
        token = await self._get_app_token()
        headers = {"Client-Id": self.client_id, "Authorization": f"Bearer {token}"}
        params = [("login", l) for l in logins]
        async with aiohttp.ClientSession() as s:
            async with s.get("https://api.twitch.tv/helix/users", headers=headers, params=params) as r:
                data = await r.json()
                if r.status != 200:
                    raise RuntimeError(f"get_users failed {r.status}: {data}")
                return data.get("data", [])
