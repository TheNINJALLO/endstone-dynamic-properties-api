from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Protocol

from .model import AccessContext, CollectionSnapshot, Status


@dataclass(frozen=True, slots=True)
class AuditRecord:
    transaction_id: str
    operation_name: str
    actor: AccessContext
    status: Status
    message: str
    before: tuple[CollectionSnapshot, ...] = ()
    after: tuple[CollectionSnapshot, ...] = ()
    external: bool = False
    rolled_back: bool = False


class AuditSink(Protocol):
    def record(self, record: AuditRecord) -> None:
        """Persist one record; services isolate and log raised exceptions."""
        ...


class VectorAuditSink:
    def __init__(self) -> None:
        self._lock = RLock()
        self._records: list[AuditRecord] = []

    def record(self, record: AuditRecord) -> None:
        with self._lock:
            self._records.append(record)

    def records(self) -> tuple[AuditRecord, ...]:
        with self._lock:
            return tuple(self._records)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
