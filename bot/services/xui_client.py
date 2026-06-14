"""Async client for 3X-UI REST API.

Based on goVLESS/phase-a/govlessctl/xui_client.py — adapted for standalone
operation without govlessctl RPC layer. Supports 3X-UI v2 and v3 endpoints
with automatic fallbacks.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import urllib.parse
from typing import Any, Optional

import aiohttp
from loguru import logger

from bot.config import settings

RETRY_COUNT = 3
RETRY_BACKOFF = 5.0


class XuiError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _extract_csrf_token(html_text: str) -> Optional[str]:
    match = re.search(r'csrf-token"\s+content="([^"]+)"', html_text or "")
    return match.group(1) if match else None


def _quote_path(value: str) -> str:
    return urllib.parse.quote(str(value), safe="")


def _normalize_client_payload(client_obj: dict) -> dict:
    normalized = dict(client_obj)
    for key in ("limitIp", "totalGB", "expiryTime", "tgId", "reset"):
        if key in normalized:
            val = normalized.get(key)
            if val in ("", None):
                normalized[key] = 0
            else:
                try:
                    normalized[key] = int(val)
                except (TypeError, ValueError):
                    normalized[key] = 0
    if "tgId" not in normalized:
        normalized["tgId"] = 0
    if "enable" in normalized:
        normalized["enable"] = bool(normalized.get("enable"))
    return normalized


class XUIClient:
    """Async HTTP client for 3X-UI panel API."""

    def __init__(
        self,
        url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        self.url = (url or settings.xui_url).rstrip("/")
        self.username = username or settings.xui_username
        self.password = password or settings.xui_password
        self._session: Optional[aiohttp.ClientSession] = None
        self._csrf: Optional[str] = None
        self._cookie_jar: Optional[aiohttp.CookieJar] = None
        self._login_lock = asyncio.Lock()
        self._logged_in_at: float = 0.0

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._cookie_jar = aiohttp.CookieJar(unsafe=True)
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(
                cookie_jar=self._cookie_jar, timeout=timeout
            )
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def login(self) -> bool:
        async with self._login_lock:
            if self._logged_in_at and (time.time() - self._logged_in_at) < 120:
                return True
            session = await self._ensure_session()
            data = {"username": self.username, "password": self.password}
            headers: dict[str, str] = {}

            async with session.get(f"{self.url}/") as resp:
                html_text = await resp.text()
                if resp.status >= 500:
                    raise XuiError(503, f"panel HTTP {resp.status}: {html_text[:200]}")
                self._csrf = _extract_csrf_token(html_text)

            login_csrf = self._csrf
            if self._csrf:
                headers["X-CSRF-Token"] = self._csrf

            async with session.post(
                f"{self.url}/login", data=data, headers=headers
            ) as resp:
                text = await resp.text()
                if resp.status != 200:
                    raise XuiError(503, f"login HTTP {resp.status}: {text[:200]}")
                try:
                    payload = json.loads(text)
                except ValueError:
                    raise XuiError(503, f"login non-JSON: {text[:200]}")
                if not payload.get("success"):
                    raise XuiError(
                        401, f"login failed: {payload.get('msg', 'no msg')}"
                    )

            self._csrf = None
            if self._cookie_jar is not None:
                for cookie in self._cookie_jar:
                    if cookie.key.lower() in (
                        "csrf_token",
                        "csrf",
                        "x-csrf-token",
                    ):
                        self._csrf = cookie.value
                        break
            if self._csrf is None:
                self._csrf = login_csrf
            self._logged_in_at = time.time()
            return True

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        data: Any = None,
        retries: int = RETRY_COUNT,
    ) -> Any:
        last_err: Optional[Exception] = None
        for attempt in range(retries):
            try:
                await self.login()
                session = await self._ensure_session()
                headers: dict[str, str] = {}
                if self._csrf:
                    headers["X-CSRF-Token"] = self._csrf
                url = f"{self.url}{path}"
                async with session.request(
                    method, url, json=json_body, data=data, headers=headers
                ) as resp:
                    text = await resp.text()
                    if resp.status >= 500:
                        raise XuiError(503, f"3X-UI {resp.status}: {text[:200]}")
                    if resp.status in (401, 403):
                        self._logged_in_at = 0.0
                        raise XuiError(
                            401, f"3X-UI auth: {resp.status} {text[:200]}"
                        )
                    if resp.status >= 400:
                        raise XuiError(
                            resp.status, f"3X-UI HTTP {resp.status}: {text[:200]}"
                        )
                    if not text:
                        return None
                    try:
                        payload = json.loads(text)
                    except ValueError:
                        return {"raw": text}
                    if (
                        isinstance(payload, dict)
                        and payload.get("success") is False
                    ):
                        msg = payload.get("msg") or "no msg"
                        raise XuiError(400, f"3X-UI API failed: {msg}")
                    return payload
            except (
                aiohttp.ClientConnectionError,
                asyncio.TimeoutError,
                XuiError,
            ) as e:
                last_err = e
                if isinstance(e, XuiError) and e.code in (401, 403):
                    if "3X-UI auth:" in e.message and attempt < retries - 1:
                        await asyncio.sleep(RETRY_BACKOFF)
                        continue
                    raise
                if isinstance(e, XuiError) and e.code not in (503, 502, 504):
                    raise
                if attempt < retries - 1:
                    logger.warning(
                        "3X-UI request {}{} attempt {}/{} failed: {}",
                        method,
                        path,
                        attempt + 1,
                        retries,
                        e,
                    )
                    await asyncio.sleep(RETRY_BACKOFF)
                    continue
                if isinstance(e, XuiError):
                    raise
                raise XuiError(503, f"3X-UI unavailable: {e}")
        if last_err:
            raise XuiError(503, f"3X-UI unavailable after retries: {last_err}")
        raise XuiError(503, "3X-UI unavailable")

    # ── API Methods ─────────────────────────────────────────────────────

    async def get_inbounds(self) -> list[dict]:
        resp = await self._request("GET", "/panel/api/inbounds/list")
        if isinstance(resp, dict) and "obj" in resp:
            return resp.get("obj") or []
        if isinstance(resp, list):
            return resp
        return []

    async def get_inbound(self, inbound_id: int) -> Optional[dict]:
        resp = await self._request(
            "GET", f"/panel/api/inbounds/get/{int(inbound_id)}"
        )
        if isinstance(resp, dict):
            return resp.get("obj") or resp
        return None

    async def add_client(
        self, inbound_id: int, client_data: dict
    ) -> dict:
        client_data = _normalize_client_payload(client_data)
        try:
            return await self._request(
                "POST",
                "/panel/api/clients/add",
                json_body={
                    "client": client_data,
                    "inboundIds": [int(inbound_id)],
                },
            )
        except XuiError as exc:
            if exc.code != 404:
                raise
        body = {
            "id": str(int(inbound_id)),
            "settings": json.dumps({"clients": [client_data]}),
        }
        return await self._request(
            "POST", "/panel/api/inbounds/addClient", data=body
        )

    async def update_client(
        self, inbound_id: int, client_id: str, data: dict
    ) -> dict:
        data = _normalize_client_payload(data)
        email = str(data.get("email") or "")
        if email:
            try:
                return await self._request(
                    "POST",
                    f"/panel/api/clients/update/{_quote_path(email)}",
                    json_body=data,
                )
            except XuiError as exc:
                if exc.code != 404:
                    raise
        body = {
            "id": str(int(inbound_id)),
            "settings": json.dumps({"clients": [data]}),
        }
        return await self._request(
            "POST",
            f"/panel/api/inbounds/updateClient/{client_id}",
            data=body,
        )

    async def delete_client(
        self, inbound_id: int, client_id: str, email: Optional[str] = None
    ) -> bool:
        if email:
            try:
                await self._request(
                    "POST",
                    f"/panel/api/clients/del/{_quote_path(email)}",
                )
                return True
            except XuiError as exc:
                if exc.code != 404:
                    raise
        await self._request(
            "POST",
            f"/panel/api/inbounds/{int(inbound_id)}/delClient/{client_id}",
        )
        return True

    async def get_client_stats(self, email: str) -> Optional[dict]:
        try:
            resp = await self._request(
                "GET",
                f"/panel/api/clients/stats/{_quote_path(email)}",
            )
            if isinstance(resp, dict):
                return resp.get("obj") or resp
        except XuiError:
            pass
        return None

    async def reset_client_traffic(
        self, inbound_id: int, email: str
    ) -> bool:
        try:
            await self._request(
                "POST",
                f"/panel/api/clients/resetTraffic/{_quote_path(email)}",
            )
            return True
        except XuiError as exc:
            if exc.code != 404:
                raise
        await self._request(
            "POST",
            f"/panel/api/inbounds/{int(inbound_id)}/resetClientTraffic/"
            f"{urllib.parse.quote(email)}",
        )
        return True

    async def get_onlines(self) -> list[str]:
        try:
            resp = await self._request(
                "POST", "/panel/api/clients/onlines"
            )
        except XuiError as exc:
            if exc.code != 404:
                raise
            resp = await self._request(
                "POST", "/panel/api/inbounds/onlines"
            )
        if isinstance(resp, dict) and "obj" in resp:
            return resp.get("obj") or []
        if isinstance(resp, list):
            return resp
        return []

    async def regenerate_client(
        self, inbound_id: int, client_id: str
    ) -> dict:
        """Delete and re-create a client with a new UUID."""
        import uuid as uuid_mod

        inbound = await self.get_inbound(inbound_id)
        if not inbound:
            raise XuiError(404, f"inbound {inbound_id} not found")

        settings_obj = inbound.get("settings_obj")
        if settings_obj is None:
            raw_settings = inbound.get("settings", "{}")
            settings_obj = json.loads(raw_settings) if isinstance(raw_settings, str) else raw_settings

        clients = settings_obj.get("clients", [])
        old_client = None
        for c in clients:
            if c.get("id") == client_id:
                old_client = c
                break

        if old_client is None:
            raise XuiError(404, f"client {client_id} not found in inbound")

        email = old_client.get("email", "")
        await self.delete_client(inbound_id, client_id, email=email)

        new_uuid = str(uuid_mod.uuid4())
        new_client = dict(old_client)
        new_client["id"] = new_uuid

        await self.add_client(inbound_id, new_client)

        return {"old_uuid": client_id, "new_uuid": new_uuid, "email": email}

    async def ping(self) -> bool:
        try:
            await self.login()
            return True
        except Exception:
            return False


def build_vless_link(
    uuid: str,
    server: str,
    port: int,
    inbound: dict,
    email: str,
    flow: str = "",
) -> str:
    """Build a VLESS URI from inbound config."""
    def quote(x: object) -> str:
        return urllib.parse.quote(str(x), safe="")
    stream = inbound.get("stream_obj") or {}
    if not stream and isinstance(inbound.get("stream_settings"), str):
        try:
            stream = json.loads(inbound["stream_settings"])
        except (ValueError, TypeError):
            stream = {}

    network = stream.get("network", "tcp")
    security = stream.get("security", "tls")

    if security == "reality":
        rs = stream.get("realitySettings", {}) or {}
        pbk = (
            (rs.get("settings") or {}).get("publicKey")
            or rs.get("publicKey", "")
        )
        sni_list = rs.get("serverNames") or [""]
        sni = sni_list[0] if sni_list else ""
        sid_list = rs.get("shortIds") or [""]
        sid = sid_list[0] if sid_list else ""
        fp = (rs.get("settings") or {}).get("fingerprint") or "chrome"
        common = (
            f"security=reality&pbk={pbk}&fp={fp}&sni={sni}&sid={sid}&spx=%2F"
        )
    elif security == "tls":
        ts = stream.get("tlsSettings", {}) or {}
        sni = ts.get("serverName") or server
        fp = (ts.get("settings") or {}).get("fingerprint") or "chrome"
        common = f"security=tls&sni={sni}&fp={fp}"
        alpn_list = ts.get("alpn") or []
        if alpn_list:
            common += f"&alpn={quote(','.join(alpn_list))}"
    else:
        common = f"security={security}"

    params = f"encryption=none&type={network}&{common}"

    if network == "tcp" and flow:
        params += f"&flow={quote(flow)}"
    elif network == "xhttp":
        xs = stream.get("xhttpSettings", {}) or {}
        path_q = quote(xs.get("path", "/") or "/")
        mode_ = xs.get("mode", "auto") or "auto"
        params += f"&path={path_q}&mode={mode_}"
    elif network == "grpc":
        gs = stream.get("grpcSettings", {}) or {}
        sn = gs.get("serviceName", "") or ""
        mode_ = "multi" if gs.get("multiMode") else "single"
        params += f"&serviceName={quote(sn)}&mode={mode_}"
    elif network == "ws":
        ws = stream.get("wsSettings", {}) or {}
        path_q = quote(ws.get("path", "/") or "/")
        host_h = (ws.get("headers", {}) or {}).get("Host", "")
        params += f"&path={path_q}"
        if host_h:
            params += f"&host={quote(host_h)}"

    enc_name = quote(email)
    return f"vless://{uuid}@{server}:{port}?{params}#{enc_name}"
