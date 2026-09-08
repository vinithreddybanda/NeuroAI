from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class GitHubClient:
    BASE = "https://api.github.com"

    def __init__(self, token: str | None = None):
        self.token = (token or os.getenv("GITHUB_TOKEN", "")).strip()
        if not self.token:
            raise RuntimeError("GITHUB_TOKEN is missing from the environment.")

    def _request_sync(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
    ) -> Any:
        if not path.startswith("/"):
            path = "/" + path

        url = self.BASE + path
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)

        body = json.dumps(json_body).encode("utf-8") if json_body is not None else None

        req = urllib.request.Request(
            url,
            data=body,
            method=method.upper(),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "SecondBrain-NeuroSAN",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GitHub API {exc.code} {exc.reason}: {raw[:2000]}") from exc

    async def request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> Any:
        return await asyncio.to_thread(self._request_sync, method, path, params, json)