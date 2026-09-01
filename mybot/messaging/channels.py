from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from typing import Any
from urllib import error, request

from .bus import InboundMessage, MessageBus, OutboundMessage


class BaseChannel(ABC):
    name: str = "base"

    def __init__(self, bus: MessageBus):
        self.bus = bus

    @abstractmethod
    async def start(self): ...

    @abstractmethod
    async def stop(self): ...

    @abstractmethod
    async def send(self, message: OutboundMessage): ...

    async def handle_message(self, sender_id: str, chat_id: str, content: str) -> None:
        await self.bus.publish_inbound(
            InboundMessage(
                channel=self.name,
                sender_id=sender_id,
                chat_id=chat_id,
                content=content,
            )
        )


class CLIChannel(BaseChannel):
    name = "cli"

    def __init__(self, bus: MessageBus):
        super().__init__(bus)
        self._ready_for_input = asyncio.Event() # 异步开关
        self._ready_for_input.set() # 默认开

    async def start(self):
        loop = asyncio.get_running_loop()
        while True:
            await self._ready_for_input.wait()  # 等待可以输入的信号。第一次默认开，直接运行
            user_input = await loop.run_in_executor(None, lambda: input("You: ").strip())
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit"):
                return
            self._ready_for_input.clear()   # 收到输入后，关掉输入开关，等 bot 回复后再开。
            await self.handle_message("user", "direct", user_input)

    async def stop(self):
        return None

    async def send(self, message: OutboundMessage):
        print(f"\nBot: {message.content}\n")
        self._ready_for_input.set() # bot 回复后，开输入开关，让用户可以继续输入。


class FeishuChannel(BaseChannel):
    name = "feishu"

    def __init__(self, bus: MessageBus, app_id: str, app_secret: str):
        super().__init__(bus)
        self.app_id = app_id
        self.app_secret = app_secret
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event = asyncio.Event()
        self._token_lock = asyncio.Lock()
        self._tenant_access_token: str | None = None
        self._tenant_token_expire_at = 0.0
        self._ws_task: asyncio.Task | None = None

    async def start(self):
        self._loop = asyncio.get_running_loop()
        self._ws_task = asyncio.create_task(asyncio.to_thread(self._run_long_connection))
        print("Feishu long connection started.")
        await self._stop_event.wait()

    async def stop(self):
        self._stop_event.set()
        if self._ws_task:
            self._ws_task.cancel()

    async def send(self, message: OutboundMessage):
        token = await self._get_tenant_access_token()
        url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
        payload = {
            "receive_id": message.chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": message.content}, ensure_ascii=False),
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        await asyncio.to_thread(self._post_json, url, payload, headers)

    async def _get_tenant_access_token(self) -> str:
        async with self._token_lock:
            now = asyncio.get_running_loop().time()
            if self._tenant_access_token and now < self._tenant_token_expire_at:
                return self._tenant_access_token

            url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
            payload = {"app_id": self.app_id, "app_secret": self.app_secret}
            headers = {"Content-Type": "application/json; charset=utf-8"}
            data = await asyncio.to_thread(self._post_json, url, payload, headers)

            if data.get("code"):
                raise RuntimeError(f"Feishu token error: {data}")

            self._tenant_access_token = data["tenant_access_token"]
            expire = int(data.get("expire", 7200))
            self._tenant_token_expire_at = now + max(60, expire - 60)
            return self._tenant_access_token

    def _post_json(self, url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(url, data=body, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
        return json.loads(raw) if raw else {}

    def _run_long_connection(self):
        try:
            import lark_oapi as lark
            from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
        except ImportError as exc:
            raise RuntimeError(
                "Feishu long connection requires the 'lark-oapi' package."
            ) from exc

        def on_message(data) -> None:
            event = getattr(data, "event", None)
            if event is None:
                return

            sender = getattr(event, "sender", None)
            sender_id_obj = getattr(sender, "sender_id", None)
            message = getattr(event, "message", None)
            if message is None:
                return
            if getattr(message, "message_type", "") != "text":
                return
            if getattr(sender, "sender_type", "") == "app":
                return

            text = self._extract_text_content(getattr(message, "content", ""))
            if not text or self._loop is None:
                return

            sender_id = self._pick_sender_id(sender_id_obj)
            chat_id = getattr(message, "chat_id", None) or sender_id or "default"
            future = asyncio.run_coroutine_threadsafe(
                self.handle_message(sender_id, chat_id, text),
                self._loop,
            )
            future.add_done_callback(lambda f: f.exception())

        event_handler = (
            EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(on_message)
            .build()
        )
        client = lark.ws.Client(
            self.app_id,
            self.app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO,
        )
        client.start()

    def _pick_sender_id(self, sender_id_obj: Any) -> str:
        if sender_id_obj is None:
            return "unknown"
        for name in ("open_id", "user_id", "union_id"):
            value = getattr(sender_id_obj, name, None)
            if value:
                return value
        return "unknown"

    def _extract_text_content(self, content: str) -> str:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            return content
        text = payload.get("text", "")
        return text.strip() if isinstance(text, str) else ""
