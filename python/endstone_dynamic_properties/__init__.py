"""Unified dynamic-properties API for Endstone world, actor, item, storage and block targets."""

from .audit import AuditRecord, AuditSink, VectorAuditSink
from .events import Event, EventBus, EventFilter, EventKind
from .model import *
from .native import NativeManifestStatus, REQUIRED_SYMBOLS, verify_native_manifest
from .service import AccessPolicy, DynamicPropertyService, InMemoryAdapter, describe_target

__version__ = "0.1.0a5"
__service__ = "endstone:dynamic-properties:v1"
__all__ = [name for name in globals() if not name.startswith("_")]
