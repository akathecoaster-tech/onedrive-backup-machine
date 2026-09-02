"""Microsoft Graph helpers for OneDrive Backup Machine."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import quote

import aiohttp
from msal import PublicClientApplication

from token_cache import FileTokenCache

_LOGGER = logging.getLogger(__name__)

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
SCOPES = ["Files.Read.All", "User.Read"]


class OneDriveClient:
    def __init__(self, client_id: str, cache_path: Path) -> None:
        self.client_id = client_id.strip()
        self.cache = FileTokenCache(cache_path)
        self._app: PublicClientApplication | None = None
        self._device_flow: dict[str, Any] | None = None

    @property
    def configured(self) -> bool:
        return bool(self.client_id)

    def _pca(self) -> PublicClientApplication:
        if self._app is None:
            if not self.client_id:
                raise RuntimeError("client_id is not configured")
            self._app = PublicClientApplication(
                client_id=self.client_id,
                authority="https://login.microsoftonline.com/consumers",
                token_cache=self.cache,
            )
        return self._app

    def accounts(self) -> list:
        return self._pca().get_accounts()

    def is_authenticated(self) -> bool:
        accounts = self.accounts()
        if not accounts:
            return False
        result = self._pca().acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            self.cache.save()
            return True
        return False

    def begin_device_login(self) -> dict[str, Any]:
        flow = self._pca().initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(f"Failed to start device login: {flow}")
        self._device_flow = flow
        return {
            "user_code": flow.get("user_code"),
            "verification_uri": flow.get("verification_uri"),
            "message": flow.get("message"),
            "expires_in": flow.get("expires_in"),
        }

    def complete_device_login(self) -> dict[str, Any]:
        if not self._device_flow:
            raise RuntimeError("No device login in progress")
        result = self._pca().acquire_token_by_device_flow(self._device_flow)
        self._device_flow = None
        if "access_token" not in result:
            raise RuntimeError(result.get("error_description") or result.get("error") or "Login failed")
        self.cache.save()
        return {"authenticated": True, "account": (result.get("id_token_claims") or {}).get("preferred_username")}

    def get_access_token(self) -> str:
        accounts = self.accounts()
        if not accounts:
            raise RuntimeError("Not authenticated with OneDrive")
        result = self._pca().acquire_token_silent(SCOPES, account=accounts[0])
        if not result or "access_token" not in result:
            raise RuntimeError("Unable to refresh OneDrive token; login again")
        self.cache.save()
        return result["access_token"]

    async def _request(
        self,
        session: aiohttp.ClientSession,
        method: str,
        url: str,
        **kwargs,
    ) -> Any:
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.get_access_token()}"
        async with session.request(method, url, headers=headers, **kwargs) as response:
            if response.status >= 400:
                text = await response.text()
                raise RuntimeError(f"Graph {method} {url} failed ({response.status}): {text[:300]}")
            if response.content_type and "json" in response.content_type:
                return await response.json()
            return await response.read()

    async def iter_files(self, session: aiohttp.ClientSession, remote_path: str) -> AsyncIterator[dict[str, Any]]:
        remote_path = remote_path.strip().strip("/")
        if remote_path:
            url = f"{GRAPH_ROOT}/me/drive/root:/{quote(remote_path)}:/children?$select=id,name,file,folder,size,lastModifiedDateTime,eTag,@microsoft.graph.downloadUrl"
        else:
            url = f"{GRAPH_ROOT}/me/drive/root/children?$select=id,name,file,folder,size,lastModifiedDateTime,eTag,@microsoft.graph.downloadUrl"

        stack = [(url, remote_path)]
        while stack:
            page_url, parent = stack.pop()
            payload = await self._request(session, "GET", page_url)
            for item in payload.get("value", []):
                name = item.get("name") or "unnamed"
                child_path = f"{parent}/{name}".strip("/")
                if "folder" in item:
                    next_url = f"{GRAPH_ROOT}/me/drive/items/{item['id']}/children?$select=id,name,file,folder,size,lastModifiedDateTime,eTag,@microsoft.graph.downloadUrl"
                    stack.append((next_url, child_path))
                elif "file" in item:
                    item = dict(item)
                    item["_relative_path"] = child_path
                    yield item
            next_link = payload.get("@odata.nextLink")
            if next_link:
                stack.append((next_link, parent))

    async def download_file(self, session: aiohttp.ClientSession, item: dict[str, Any], dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        url = item.get("@microsoft.graph.downloadUrl")
        if not url:
            url = f"{GRAPH_ROOT}/me/drive/items/{item['id']}/content"
            headers = {"Authorization": f"Bearer {self.get_access_token()}"}
        else:
            headers = {}
        async with session.get(url, headers=headers) as response:
            if response.status >= 400:
                text = await response.text()
                raise RuntimeError(f"Download failed ({response.status}): {text[:300]}")
            with dest.open("wb") as handle:
                async for chunk in response.content.iter_chunked(1024 * 256):
                    handle.write(chunk)
