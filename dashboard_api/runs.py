from __future__ import annotations

import inspect
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, Thread
from typing import Callable
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RunState:
    run_id: str
    phase: str
    status: str = "queued"
    logs: list[str] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    result: dict | None = None
    error: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RunState":
        allowed = {field.name for field in cls.__dataclass_fields__.values()}
        values = {key: value for key, value in data.items() if key in allowed}
        return cls(**values)


class RunRegistry:
    def __init__(self):
        self._lock = Lock()
        self._runs: dict[str, RunState] = {}

    def _runs_dir(self) -> Path:
        root = os.environ.get("ARTIFACT_ROOT")
        if root:
            path = Path(root)
            artifact_root = path.parent if path.name == "applications" else path
        else:
            artifact_root = Path("artifacts")
        runs_dir = artifact_root / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        return runs_dir

    def _persist_unlocked(self, run: RunState):
        path = self._runs_dir() / f"{run.run_id}.json"
        path.write_text(json.dumps(run.as_dict(), indent=2, sort_keys=True), encoding="utf-8")

    def _load_run(self, run_id: str) -> RunState | None:
        path = self._runs_dir() / f"{run_id}.json"
        if not path.exists():
            return None
        try:
            return RunState.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, TypeError):
            return None

    def start(self, phase: str, fn: Callable[[], dict]) -> RunState:
        run = RunState(run_id=uuid4().hex, phase=phase)
        with self._lock:
            self._runs[run.run_id] = run
            self._persist_unlocked(run)
        Thread(target=self._execute, args=(run.run_id, fn), daemon=True).start()
        return run

    def _execute(self, run_id: str, fn):
        log_fn = lambda msg: self.append_log(run_id, msg)
        emit_fn = lambda event: self.append_event(run_id, event)
        self.append_log(run_id, "started")
        self.update(run_id, status="running")
        try:
            params = inspect.signature(fn).parameters
            if len(params) >= 2:
                result = fn(log_fn, emit_fn)
            elif params:
                result = fn(log_fn)
            else:
                result = fn()
        except Exception as exc:
            self.append_log(run_id, f"failed: {exc}")
            self.update(run_id, status="failed", error=str(exc))
            return
        self.update(run_id, status="succeeded", result=result)
        self.append_log(run_id, "succeeded")

    def append_log(self, run_id: str, message: str):
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return
            run.logs.append(f"{utc_now()} {message}")
            run.updated_at = utc_now()
            self._persist_unlocked(run)

    def append_event(self, run_id: str, event: dict):
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return
            run.events.append({**event, "at": utc_now()})
            run.updated_at = utc_now()
            self._persist_unlocked(run)

    def update(self, run_id: str, **changes):
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return
            for key, value in changes.items():
                setattr(run, key, value)
            run.updated_at = utc_now()
            self._persist_unlocked(run)

    def get(self, run_id: str) -> RunState | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run:
                return run
        return self._load_run(run_id)

    def list(self) -> list[RunState]:
        runs: dict[str, RunState] = {}
        for path in self._runs_dir().glob("*.json"):
            try:
                run = RunState.from_dict(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError, TypeError):
                continue
            runs[run.run_id] = run
        with self._lock:
            runs.update(self._runs)
        return sorted(runs.values(), key=lambda run: run.updated_at, reverse=True)
