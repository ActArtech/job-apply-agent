import time

from dashboard_api.runs import RunRegistry, RunState


def wait_for(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_runstate_events_default_empty():
    run = RunState(run_id="x", phase="phase2")
    assert run.events == []
    assert "events" in run.as_dict()


def test_execute_passes_emit_fn_when_fn_accepts_two_params(monkeypatch, tmp_path):
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path))
    registry = RunRegistry()

    def fn(log_fn, emit_fn):
        log_fn("hello")
        emit_fn({"type": "job_result", "status": "approved"})
        return {"ok": True}

    run = registry.start("phase2", fn)
    assert wait_for(lambda: (registry.get(run.run_id) or RunState("x", "y")).status == "succeeded")
    final = registry.get(run.run_id)
    assert any(e["type"] == "job_result" for e in final.events)
    assert any("hello" in line for line in final.logs)


def test_execute_still_supports_single_param_fn(monkeypatch, tmp_path):
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path))
    registry = RunRegistry()
    run = registry.start("phase1", lambda log_fn: {"ok": True})
    assert wait_for(lambda: (registry.get(run.run_id) or RunState("x", "y")).status == "succeeded")
