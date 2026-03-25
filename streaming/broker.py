from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class EventMessage:
    topic: str
    offset: int
    key: str | None
    payload: dict[str, Any]
    published_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "offset": self.offset,
            "key": self.key,
            "payload": self.payload,
            "published_at": self.published_at,
        }


class InMemoryKafkaBroker:
    """
    Lightweight Kafka-compatible abstraction for tests and local demos.

    The public API mirrors the publish/history semantics the agents need so the
    same orchestration code can later swap to aiokafka without rewrites.
    """

    def __init__(self) -> None:
        self._history: dict[str, deque[EventMessage]] = defaultdict(lambda: deque(maxlen=10000))
        self._offsets: dict[str, int] = defaultdict(int)

    async def publish(self, topic: str, payload: dict[str, Any], key: str | None = None) -> EventMessage:
        offset = self._offsets[topic]
        self._offsets[topic] += 1
        message = EventMessage(
            topic=topic,
            offset=offset,
            key=key,
            payload=payload,
            published_at=_timestamp(),
        )
        self._history[topic].append(message)
        return message

    def history(self, topic: str) -> list[dict[str, Any]]:
        return [message.to_dict() for message in self._history.get(topic, [])]

    def last_payload(self, topic: str) -> dict[str, Any] | None:
        messages = self._history.get(topic, [])
        return messages[-1].payload if messages else None

    def topic_size(self, topic: str) -> int:
        return len(self._history.get(topic, []))
