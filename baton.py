"""
baton.py — the object every stage passes to the next.

A Baton is deliberately small: run_id, created_at, mode, a payload dict (the
actual content), and a history list (one note per stage that has touched it).
Stages never share anything richer than this — no transcripts, no extra state.
The real per-stage payload schema is NOT decided here; that happens empirically
later (Step 15). This file only defines the envelope, not what goes inside it.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

REQUIRED_FIELDS = ("run_id", "created_at", "mode", "payload", "history")
VALID_MODES = ("human", "auto")


@dataclass
class Baton:
    run_id: str
    created_at: str
    mode: str
    payload: dict[str, Any] = field(default_factory=lambda: {"dummy": True})
    history: list[dict[str, str]] = field(default_factory=list)

    def add_history(self, stage: str, note: str) -> None:
        """Record that `stage` touched this baton, with a one-line note of what it did."""
        self.history.append(
            {
                "stage": stage,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "note": note,
            }
        )

    def validate(self) -> None:
        """Raise immediately if the baton is missing or has malformed required fields."""
        data = asdict(self)
        for name in REQUIRED_FIELDS:
            if name not in data or data[name] is None:
                raise ValueError(f"Baton missing required field: {name}")
        if self.mode not in VALID_MODES:
            raise ValueError(f"Baton mode must be one of {VALID_MODES}, got: {self.mode!r}")
        if not isinstance(self.payload, dict):
            raise ValueError("Baton payload must be a dict")
        if not isinstance(self.history, list):
            raise ValueError("Baton history must be a list")

    def to_json(self) -> str:
        """Serialize to a JSON string, for saving between stages."""
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, raw: str) -> "Baton":
        """Rebuild a Baton from a JSON string and validate it before returning."""
        data = json.loads(raw)
        baton = cls(
            run_id=data["run_id"],
            created_at=data["created_at"],
            mode=data["mode"],
            payload=data.get("payload", {}),
            history=data.get("history", []),
        )
        baton.validate()
        return baton
