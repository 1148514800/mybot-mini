from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass
class InboundMessage:
    channel: str
    sender_id: str
    chat_id: str
    content: str

    @property
    def session_key(self) -> str:
        return f"{self.channel}:{self.chat_id}"


@dataclass
class OutboundMessage:
    channel: str
    chat_id: str
    content: str


class MessageBus:
    def __init__(self):
        self.inbound: asyncio.Queue[InboundMessage] = asyncio.Queue()   # 存所有进入系统的消息
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue() # 存所有等待发送出去的消息

    async def publish_inbound(self, message: InboundMessage):   # 把入站消息放进 inbound
        await self.inbound.put(message)

    async def consume_inbound(self) -> InboundMessage:  # 从 inbound 取一条消息
        return await self.inbound.get()

    async def publish_outbound(self, message: OutboundMessage): # 把出站消息放进 outbound
        await self.outbound.put(message)

    async def consume_outbound(self) -> OutboundMessage:    # 从 outbound 取一条消息
        return await self.outbound.get()


async def route_outbound(bus: MessageBus, channels: dict[str, object]):
    '''把 agent 产生的回复，从 MessageBus.outbound 队列里取出来，再按 message.channel 发给对应的通道对象，比如 CLI。'''
    while True:
        try:
            message = await asyncio.wait_for(bus.consume_outbound(), timeout=1.0)
        except asyncio.TimeoutError:
            continue
        channel = channels.get(message.channel)
        if channel:
            await channel.send(message)
