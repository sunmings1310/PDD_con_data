"""比特浏览器 API 对接：接管已创建隔离环境。"""

from __future__ import annotations

from typing import Any, Optional

import httpx
from loguru import logger


class BrowserClient:
    """
    对接 BitBrowser 开放 API。
    一套任务绑定一个隔离环境，任务结束再释放，不跨任务复用。
    """

    def __init__(
        self,
        api_url: str = "http://127.0.0.1:54345",
        group_id: str = "",
        *,
        force_direct: bool = True,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.group_id = group_id or ""
        # 默认强制直连：避免窗口里失效 SOCKS 导致 ERR_SOCKS_CONNECTION_FAILED
        self.force_direct = force_direct
        # API 请求本身也禁止走系统代理
        self._client = httpx.Client(timeout=30.0, trust_env=False)

    def _post(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.api_url}{path}"
        resp = self._client.post(url, json=payload or {})
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {"data": data}

    def health(self) -> bool:
        try:
            self._post("/browser/list", {"page": 0, "pageSize": 1})
            return True
        except Exception as exc:
            logger.warning("BitBrowser API 不可用: {} ({})", self.api_url, exc)
            return False

    def get_available_env(self) -> Optional[str]:
        """获取一个可用环境 ID（优先未打开的）。"""
        payload: dict[str, Any] = {"page": 0, "pageSize": 50}
        if self.group_id:
            payload["groupId"] = self.group_id
        try:
            data = self._post("/browser/list", payload)
        except Exception as exc:
            logger.error("获取环境列表失败: {}", exc)
            return None

        rows = []
        body = data.get("data") or data
        if isinstance(body, dict):
            rows = body.get("list") or body.get("data") or []
        elif isinstance(body, list):
            rows = body

        for row in rows:
            if not isinstance(row, dict):
                continue
            env_id = str(row.get("id") or row.get("browserId") or "")
            if not env_id:
                continue
            status = str(row.get("status") or row.get("openStatus") or "")
            if status in ("0", "Closed", "closed", ""):
                return env_id
        if rows and isinstance(rows[0], dict):
            return str(rows[0].get("id") or rows[0].get("browserId") or "") or None
        logger.error("未找到可用 BitBrowser 环境，请先在比特浏览器中创建窗口")
        return None

    def clear_proxy(self, env_id: str) -> bool:
        """
        将该窗口代理改为 noproxy（直连本机网络）。
        解决 ERR_SOCKS_CONNECTION_FAILED：失效 SOCKS 导致无法打开页面。
        """
        payloads = [
            # 批量改代理（推荐）
            (
                "/browser/proxy/update",
                {
                    "ids": [env_id],
                    "proxyMethod": 2,
                    "proxyType": "noproxy",
                    "host": "",
                    "port": "",
                    "proxyUserName": "",
                    "proxyPassword": "",
                },
            ),
            # 部分更新兜底
            (
                "/browser/update/partial",
                {
                    "ids": [env_id],
                    "proxyMethod": 2,
                    "proxyType": "noproxy",
                    "host": "",
                    "port": "",
                },
            ),
        ]
        for path, body in payloads:
            try:
                data = self._post(path, body)
                ok = data.get("success", True)
                if ok is False and str(data.get("code")) not in ("0", "200", ""):
                    logger.warning("清除代理接口返回异常 path={} data={}", path, data)
                    continue
                logger.info("已将环境改为直连(noproxy) env_id={} via={}", env_id, path)
                return True
            except Exception as exc:
                logger.warning("清除代理失败 path={} err={}", path, exc)
        return False

    def connect_env(self, env_id: str) -> Optional[str]:
        """打开并连接环境，返回 Playwright CDP websocket 地址。"""
        # 先关掉可能已打开的旧会话，再清代理，再打开（代理变更需重开才生效）
        try:
            self._post("/browser/close", {"id": env_id})
        except Exception:
            pass

        if self.force_direct:
            if not self.clear_proxy(env_id):
                logger.warning("未能自动关闭代理，若仍报 SOCKS 错误请手动在比特里改直连")

        try:
            data = self._post("/browser/open", {"id": env_id})
        except Exception as exc:
            logger.error("打开环境失败 env_id={} err={}", env_id, exc)
            return None

        body = data.get("data") or data
        ws = None
        if isinstance(body, dict):
            ws = body.get("ws") or body.get("http") or body.get("webSocketDebuggerUrl")
            if not ws and isinstance(body.get("data"), dict):
                inner = body["data"]
                ws = inner.get("ws") or inner.get("http")
        if not ws:
            logger.error("打开环境成功但未返回 ws 地址: {}", data)
            return None

        self._current_env_id = env_id
        self._ws_endpoint = str(ws)
        logger.info("已接管 BitBrowser 环境 env_id={} ws={}", env_id, self._ws_endpoint)
        return self._ws_endpoint

    def close_env(self, env_id: str | None = None) -> None:
        target = env_id or self._current_env_id
        if not target:
            return
        try:
            self._post("/browser/close", {"id": target})
            logger.info("已释放 BitBrowser 环境 env_id={}", target)
        except Exception as exc:
            logger.warning("释放环境失败 env_id={} err={}", target, exc)
        finally:
            if target == self._current_env_id:
                self._current_env_id = None
                self._ws_endpoint = None

    @property
    def ws_endpoint(self) -> Optional[str]:
        return self._ws_endpoint

    def close(self) -> None:
        self.close_env()
        self._client.close()
