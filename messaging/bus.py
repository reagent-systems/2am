"""
MessageBus — async pub/sub with file-backed broadcast log.

Topics:
  broadcast          — all agents see this (live status feed)
  agent.<id>         — direct message to a specific agent
  interrupt.<id>     — /btw interrupts for a specific agent

Usage:
  await bus.broadcast({"status": "working", ...}, sender="worker.1")
  await bus.interrupt("worker.1", "/btw please prioritize X")
  msg = bus.poll_interrupt("worker.1")   # non-blocking
"""
import asyncio
import json
import time
from pathlib import Path
from typing import Any


class MessageBus:
    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.log_path = base_path / "broadcast.jsonl"
        self._queues: dict[str, asyncio.Queue] = {}

    def _q(self, topic: str) -> asyncio.Queue:
        if topic not in self._queues:
            self._queues[topic] = asyncio.Queue()
        return self._queues[topic]

    # --- publish ---

    async def publish(self, topic: str, content: Any, sender: str = "system"):
        msg = {"ts": time.time(), "topic": topic, "sender": sender, "content": content}
        await self._q(topic).put(msg)
        # All messages also go to broadcast log
        with open(self.log_path, "a") as f:
            f.write(json.dumps(msg) + "\n")

    async def broadcast(self, content: Any, sender: str = "system"):
        await self.publish("broadcast", content, sender)

    async def send(self, agent_id: str, content: Any, sender: str = "system"):
        await self.publish(f"agent.{agent_id}", content, sender)

    async def interrupt(self, agent_id: str, message: str, sender: str = "user"):
        """Send a /btw interrupt to a running agent."""
        await self.publish(f"interrupt.{agent_id}", message, sender)

    # --- receive ---

    async def receive(self, topic: str, timeout: float | None = None) -> dict | None:
        try:
            if timeout is not None:
                return await asyncio.wait_for(self._q(topic).get(), timeout)
            return await self._q(topic).get()
        except (asyncio.TimeoutError, asyncio.QueueEmpty):
            return None

    def poll(self, topic: str) -> dict | None:
        """Non-blocking poll — returns None immediately if nothing queued."""
        try:
            return self._q(topic).get_nowait()
        except asyncio.QueueEmpty:
            return None

    def poll_interrupt(self, agent_id: str) -> str | None:
        msg = self.poll(f"interrupt.{agent_id}")
        return msg["content"] if msg else None

    # --- log ---

    def tail(self, n: int = 20) -> list[dict]:
        """Read last n entries from the broadcast log."""
        if not self.log_path.exists():
            return []
        lines = self.log_path.read_text().strip().splitlines()
        return [json.loads(l) for l in lines[-n:] if l]

    def agents_status(self) -> dict[str, dict]:
        """Derive live agent status from broadcast log."""
        status: dict[str, dict] = {}
        for entry in self.tail(200):
            c = entry.get("content", {})
            if isinstance(c, dict) and "agent" in c:
                status[c["agent"]] = c
        return status
