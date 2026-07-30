from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import logging
from threading import RLock
from typing import Callable

from .model import AccessContext, CollectionRef, CollectionSnapshot, Operation, TargetKind


_LOGGER = logging.getLogger(__name__)


class EventKind(str, Enum):
    BEFORE_MUTATION = "before_mutation"
    AFTER_MUTATION = "after_mutation"
    BEFORE_TRANSACTION = "before_transaction"
    AFTER_TRANSACTION = "after_transaction"
    BEFORE_EXTERNAL_MUTATION = "before_external_mutation"
    AFTER_EXTERNAL_MUTATION = "after_external_mutation"
    COLLECTION_MIGRATED = "collection_migrated"


@dataclass(slots=True)
class Event:
    kind: EventKind
    transaction_id: str = ""
    operation_name: str = ""
    actor: AccessContext = field(default_factory=AccessContext)
    collections: tuple[CollectionRef, ...] = ()
    key: str | None = None
    before: tuple[CollectionSnapshot, ...] = ()
    after: tuple[CollectionSnapshot, ...] = ()
    cancellable: bool = False
    cancelled: bool = False
    cancellation_reason: str = ""


@dataclass(frozen=True, slots=True)
class EventFilter:
    kind: EventKind | None = None
    target_kind: TargetKind | None = None
    target: object | None = None
    collection: str | None = None
    key: str | None = None

    def matches(self, event: Event) -> bool:
        if self.kind is not None and event.kind is not self.kind:
            return False
        if self.key is not None and event.key != self.key:
            return False
        if self.target_kind is None and self.target is None and self.collection is None:
            return True
        for ref in event.collections:
            if self.target_kind is not None and ref.target.kind is not self.target_kind:
                continue
            if self.target is not None and ref.target != self.target:
                continue
            if self.collection is not None and ref.collection != self.collection:
                continue
            return True
        return False


class EventBus:
    def __init__(self) -> None:
        self._lock = RLock()
        self._next_id = 1
        self._listeners: dict[int, tuple[EventFilter, Callable[[Event], None]]] = {}

    def subscribe(self, filter_: EventFilter, listener: Callable[[Event], None]) -> int:
        with self._lock:
            subscription_id = self._next_id
            self._next_id += 1
            self._listeners[subscription_id] = (filter_, listener)
            return subscription_id

    def unsubscribe(self, subscription_id: int) -> bool:
        with self._lock:
            return self._listeners.pop(subscription_id, None) is not None

    def publish(self, event: Event) -> tuple[Exception, ...]:
        with self._lock:
            listeners = [
                (subscription_id, listener)
                for subscription_id, (filter_, listener) in self._listeners.items()
                if filter_.matches(event)
            ]
        failures: list[Exception] = []
        for subscription_id, listener in listeners:
            try:
                listener(event)
            except Exception as exc:
                failures.append(exc)
                try:
                    _LOGGER.exception(
                        "dynamic-property event listener %d failed for %s",
                        subscription_id,
                        event.kind.value,
                    )
                except Exception:
                    # A broken logging handler must not defeat listener isolation.
                    pass
        return tuple(failures)
