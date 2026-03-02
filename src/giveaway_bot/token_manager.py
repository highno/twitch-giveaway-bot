import aiohttp
import asyncio
import time
from typing import Optional

class TokenManager:
    """Maintains a user access token, validates expiry, refreshes using refresh_token."""

    def __init__(self, client_id: str, client_secret: str, access_token: str, refresh_token: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token = access_token.strip()
        self._refresh_token = refresh_token.strip()
        self._expires_at: Optional[float] = None
        self._lock = asyncio.Lock()

    @property
    def access_token(self) -> str:
        return self._access_token

    async def _validate(self) -> Optional[int]:
        headers = {"Authorization": f"OAuth {self._access_token}"}
        async with aiohttp.ClientSession() as s:
            async with s.get("https://id.twitch.tv/oauth2/validate", headers=headers) as r:
                if r.status != 200:
                    return None
                data = await r.json()
                return int(data.get("expires_in", 0))

    async def _refresh(self) -> None:
        if not self._refresh_token:
            raise RuntimeError("Token invalid/expired and TWITCH_USER_REFRESH_TOKEN is not set.")
        params = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        async with aiohttp.ClientSession() as s:
            async with s.post("https://id.twitch.tv/oauth2/token", params=params) as r:
                data = await r.json()
                if r.status != 200:
                    raise RuntimeError(f"Token refresh failed {r.status}: {data}")
                self._access_token = data["access_token"]
                if data.get("refresh_token"):
                    self._refresh_token = data["refresh_token"]
                expires_in = int(data.get("expires_in", 0))
                self._expires_at = time.time() + max(0, expires_in - 60)

    async def ensure_fresh(self) -> str:
        async with self._lock:
            if self._expires_at and time.time() < self._expires_at:
                return self._access_token

            expires_in = await self._validate()
            if expires_in is None or expires_in <= 0:
                await self._refresh()
                return self._access_token

            self._expires_at = time.time() + max(0, expires_in - 60)
            if expires_in < 120:
                await self._refresh()
            return self._access_token
