from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from artifact_store import ArtifactStore, utc_now
from dashboard_api.analytics import compute_funnel, compute_response_rate, compute_sources, compute_sent_today
from dashboard_api.runs import RunRegistry
from phase_runner import run_phase1, run_phase2, run_phase2_single, run_phase3, run_phase3_all, run_phase3_pdf_only, run_phase4, run_phase4_single


app = FastAPI(title="Job Apply Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3101",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3101",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

registry = RunRegistry()

ALLOWED_REVIEW_STATUSES = {"pending", "approved", "rejected", "needs_regen"}
ALLOWED_ARTIFACTS = {"resume.pdf", "resume.tex", "email.txt", "jd.txt"}


class ReviewUpdate(BaseModel):
    status: str
    notes: str = ""


class PhaseRequest(BaseModel):
    max: int = 20
    limit: int = 20
    jobId: Optional[str] = None
    provider: str = "gemini"
    engine: Optional[str] = None
    force: bool = False


class PipelineRequest(BaseModel):
    max: int = 10
    limit: int = 20
    phases: list[str] = ["phase1", "phase2", "phase3"]
    engine: Optional[str] = None
    force: bool = False


class ProfileUpdate(BaseModel):
    name: str = ""
    email: str = ""
    base_resume_text: str = ""
    target_roles: list = []
    years_experience: int = 0


class CriteriaUpdate(BaseModel):
    require_remote: bool = False
    salary_floor: int = 0
    exclude_sources: list = []
    exclude_keywords: list = []


class SettingsUpdate(BaseModel):
    gemini_key: str = ""
    groq_key: str = ""
    hunter_key: str = ""
    apollo_key: str = ""
    serper_key: str = ""
    gmail_token_path: str = ""
    max_per_source: int = 20
    daily_email_limit: int = 10
    scraper_sources: dict = {}
    auto_send: bool = False
    ai_engine: str = "gemini"


class EmailDraftUpdate(BaseModel):
    body: str


class TrackingEmailUpdate(BaseModel):
    to_email: str


class OpenFolderRequest(BaseModel):
    path: str


class SelectProviderRequest(BaseModel):
    provider: str  # "gemini" or "groq"


def artifact_store() -> ArtifactStore:
    root = os.environ.get("ARTIFACT_ROOT")
    if not root:
        return ArtifactStore()
    path = Path(root)
    if path.name == "applications":
        return ArtifactStore(path.parent)
    return ArtifactStore(path)


def _resolve_engine(req: PhaseRequest) -> str:
    if req.engine:
        return req.engine
    settings = artifact_store().read_global("settings.json", {})
    return settings.get("ai_engine") or req.provider or "gemini"


def _read_json_or_404(store: ArtifactStore, job_id: str, name: str, default=None):
    try:
        return store.read_json(job_id, name, default)
    except ValueError:
        raise HTTPException(status_code=404, detail="not found") from None


def _job_dir_or_404(store: ArtifactStore, job_id: str):
    try:
        return store.job_dir(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="not found") from None


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/jobs")
def list_jobs():
    return artifact_store().list_jobs()


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    store = artifact_store()
    job = _read_json_or_404(store, job_id, "job.json")
    if not job:
        raise HTTPException(status_code=404, detail="not found")
    job_dir = _job_dir_or_404(store, job_id)
    jd_path = job_dir / "jd.txt"
    return {
        **job,
        "jd": jd_path.read_text(encoding="utf-8") if jd_path.exists() else "",
        "vetting": _read_json_or_404(store, job_id, "vetting.json", {}),
        "generation": _read_json_or_404(store, job_id, "generation.json", {}),
        "review": _read_json_or_404(store, job_id, "review.json", {"status": "pending", "notes": ""}),
        "package": _read_json_or_404(store, job_id, "package.json", None),
        "contact": _read_json_or_404(store, job_id, "contact.json", None),
        "artifacts_dir": str(job_dir),
    }


@app.post("/jobs/{job_id}/review")
def update_review(job_id: str, req: ReviewUpdate):
    if req.status not in ALLOWED_REVIEW_STATUSES:
        raise HTTPException(status_code=400, detail="invalid status")

    store = artifact_store()
    if not _read_json_or_404(store, job_id, "job.json"):
        raise HTTPException(status_code=404, detail="not found")

    current = _read_json_or_404(
        store,
        job_id,
        "review.json",
        {"status": "pending", "notes": "", "decision_history": []},
    )
    history = list(current.get("decision_history", []))
    entry = {"status": req.status, "notes": req.notes, "created_at": utc_now()}
    payload = {
        "status": req.status,
        "notes": req.notes,
        "updated_at": utc_now(),
        "decision_history": [*history, entry],
    }
    store.write_json(job_id, "review.json", payload)
    return payload


class VetUpdate(BaseModel):
    approved: bool
    reason: str = "Manual override"

@app.post("/jobs/{job_id}/vet")
def update_vet(job_id: str, req: VetUpdate):
    store = artifact_store()
    if not _read_json_or_404(store, job_id, "job.json"):
        raise HTTPException(status_code=404, detail="not found")
    store.write_json(job_id, "vetting.json", {
        "approved": req.approved,
        "status": "approved" if req.approved else "rejected",
        "reason": req.reason,
        "stage": "unknown",
        "stage_bucket": "unknown",
        "engine": {"requested": "manual", "answered": "manual"},
        "created_at": utc_now(),
    })
    return {"ok": True, "approved": req.approved}


@app.get("/jobs/{job_id}/artifact/{name}")
def get_artifact(job_id: str, name: str):
    if name not in ALLOWED_ARTIFACTS:
        raise HTTPException(status_code=403, detail="forbidden")
    file_path = _job_dir_or_404(artifact_store(), job_id) / name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="not found")
    media_type = "application/pdf" if name.endswith(".pdf") else "text/plain"
    return FileResponse(file_path, media_type=media_type)


@app.get("/jobs/{job_id}/pdf-download")
def download_pdf(job_id: str):
    job_dir = _job_dir_or_404(artifact_store(), job_id)
    pdf_path = job_dir / "resume.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF not generated yet")
    filename = f"{job_id}-resume.pdf"
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.patch("/jobs/{job_id}/email-draft")
def patch_email_draft(job_id: str, req: EmailDraftUpdate):
    store = artifact_store()
    job_dir = _job_dir_or_404(store, job_id)
    pkg = store.read_json(job_id, "package.json", {})
    pkg["email_body"] = req.body
    pkg["email_edited_at"] = utc_now()
    store.write_json(job_id, "package.json", pkg)
    (job_dir / "email.txt").write_text(req.body, encoding="utf-8")
    return {"ok": True}


@app.patch("/jobs/{job_id}/tracking/email")
def patch_tracking_email(job_id: str, req: TrackingEmailUpdate):
    store = artifact_store()
    _job_dir_or_404(store, job_id)
    if not req.to_email:
        raise HTTPException(status_code=400, detail="to_email required")
    existing = store.read_json(job_id, "tracking.json", {})
    existing["to_email"] = req.to_email
    existing["updated_at"] = utc_now()
    store.write_json(job_id, "tracking.json", existing)
    return existing


@app.post("/jobs/{job_id}/direct-apply")
def direct_apply(job_id: str):
    store = artifact_store()
    job_dir = _job_dir_or_404(store, job_id)
    job = store.read_json(job_id, "job.json", {})
    pkg = store.read_json(job_id, "package.json", {})
    jd_url = job.get("url", "")
    if not jd_url:
        return {"ok": False, "message": "No job URL found — cannot direct apply"}
    try:
        from applier import apply_directly
        result = apply_directly(
            company=job.get("company", ""),
            role=job.get("title", ""),
            jd_url=jd_url,
            cover_letter=pkg.get("email_body", ""),
            resume_path=str(job_dir / "resume.pdf"),
        )
        return {"ok": result, "message": "Applied successfully" if result else "Direct apply failed — check logs"}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


@app.post("/system/open-folder")
def open_folder(req: OpenFolderRequest):
    if sys.platform != "darwin":
        raise HTTPException(status_code=400, detail="Not supported on this platform")
    try:
        subprocess.Popen(["open", req.path])
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/phases/phase2-single", status_code=202)
def start_phase2_single(req: PhaseRequest):
    if not req.jobId:
        raise HTTPException(status_code=400, detail="jobId required")
    _job_id = req.jobId
    run = registry.start(
        f"phase2-single:{_job_id}",
        lambda log_fn: run_phase2_single(job_id=_job_id, log_fn=log_fn),
    )
    return {"run_id": run.run_id, "phase": run.phase, "status": run.status}


@app.post("/phases/phase4-single", status_code=202)
def start_phase4_single(req: PhaseRequest):
    if not req.jobId:
        raise HTTPException(status_code=400, detail="jobId required")
    _job_id = req.jobId
    run = registry.start(
        f"phase4-single:{_job_id}",
        lambda log_fn: run_phase4_single(job_id=_job_id, log_fn=log_fn),
    )
    return {"run_id": run.run_id, "phase": run.phase, "status": run.status}


@app.post("/phases/{phase}", status_code=202)
def start_phase(phase: str, req: PhaseRequest):
    if phase == "phase1":
        run = registry.start("phase1", lambda log_fn, emit_fn: run_phase1(max_per_source=req.max, log_fn=log_fn, emit_fn=emit_fn))
    elif phase == "phase2":
        _engine = _resolve_engine(req)
        _force = req.force
        run = registry.start(
            "phase2",
            lambda log_fn, emit_fn: run_phase2(
                max_per_source=req.max, log_fn=log_fn, emit_fn=emit_fn, provider=_engine, force=_force
            ),
        )
    elif phase == "phase3":
        if not req.jobId:
            raise HTTPException(status_code=400, detail="jobId required")
        _job_id = req.jobId
        _provider = _resolve_engine(req)
        run = registry.start("phase3", lambda log_fn: run_phase3(job_id=_job_id, log_fn=log_fn, provider=_provider))
    elif phase == "phase3-all":
        _provider = _resolve_engine(req)
        run = registry.start("phase3-all", lambda log_fn, emit_fn: run_phase3_all(limit=req.limit, log_fn=log_fn, emit_fn=emit_fn, provider=_provider))
    elif phase == "phase3-pdf-only":
        if not req.jobId:
            raise HTTPException(status_code=400, detail="jobId required")
        _job_id = req.jobId
        run = registry.start(f"phase3-pdf:{_job_id}", lambda log_fn: run_phase3_pdf_only(job_id=_job_id, log_fn=log_fn))
    elif phase == "phase4":
        run = registry.start("phase4", lambda log_fn, emit_fn: run_phase4(limit=req.limit, log_fn=log_fn, emit_fn=emit_fn))
    else:
        raise HTTPException(status_code=400, detail="unknown phase")
    return {"run_id": run.run_id, "phase": run.phase, "status": run.status}


@app.get("/runs")
def list_runs():
    return [run.as_dict() for run in registry.list()]


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    run = registry.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="not found")
    return run.as_dict()


@app.get("/runs/{run_id}/events")
def run_events(run_id: str):
    def stream():
        last_log = 0
        last_event = 0
        while True:
            run = registry.get(run_id)
            if not run:
                yield "event: error\ndata: not found\n\n"
                return
            for log in run.logs[last_log:]:
                yield f"event: log\ndata: {json.dumps({'message': log})}\n\n"
            last_log = len(run.logs)
            for event in run.events[last_event:]:
                yield f"event: structured\ndata: {json.dumps(event)}\n\n"
            last_event = len(run.events)
            if run.status in {"succeeded", "failed"}:
                yield f"event: done\ndata: {json.dumps(run.as_dict())}\n\n"
                return
            time.sleep(0.25)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/pipelines/safe-prepare", status_code=202)
def safe_prepare(req: PipelineRequest):
    settings = artifact_store().read_global("settings.json", {})
    engine = req.engine or settings.get("ai_engine") or "gemini"
    selected = [p for p in ["phase1", "phase2", "phase3", "phase4"] if p in req.phases]
    if not selected:
        raise HTTPException(status_code=400, detail="phases must include at least one of phase1-phase4")

    def run_all(log_fn=None, emit_fn=None):
        def log(msg):
            if log_fn:
                log_fn(msg)
        results = {"phase": "safe-prepare", "phases": selected, "engine": engine}
        if "phase1" in selected:
            log("phase 1: gathering…")
            results["phase1"] = run_phase1(max_per_source=req.max, log_fn=log_fn, emit_fn=emit_fn)
        if "phase2" in selected:
            log("phase 2: vetting…")
            results["phase2"] = run_phase2(max_per_source=req.max, log_fn=log_fn, emit_fn=emit_fn, provider=engine, force=req.force)
        if "phase3" in selected:
            log("phase 3: generating…")
            results["phase3_all"] = run_phase3_all(limit=req.limit, log_fn=log_fn, emit_fn=emit_fn, provider=engine)
        if "phase4" in selected:
            log("phase 4: finding contacts…")
            results["phase4"] = run_phase4(limit=req.limit, log_fn=log_fn, emit_fn=emit_fn)
        return results

    run = registry.start("safe-prepare", run_all)
    return {"run_id": run.run_id, "phase": run.phase, "status": run.status}


try:
    from gmail_sender import send_email as _gmail_send
    send_email = _gmail_send
except Exception:
    send_email = None

ALLOWED_TRACKING_STATUSES = {"sent", "replied", "interview", "offer", "rejected", "withdrawn"}


class TrackingUpdate(BaseModel):
    status: str
    notes: str = ""


class SendRequest(BaseModel):
    to_email: str


class BulkSendRequest(BaseModel):
    job_ids: list[str]
    dry_run: bool = False


class RegenRequest(BaseModel):
    hint: str = ""


def _mask_key(val: str) -> str:
    if not val or len(val) < 8:
        return val
    return val[:4] + "-****"


_KEY_FIELDS = ("gemini_key", "groq_key", "hunter_key", "apollo_key", "serper_key")


@app.get("/profile")
def get_profile():
    return artifact_store().read_global("profile.json", {})


@app.put("/profile")
def put_profile(req: ProfileUpdate):
    data = req.model_dump()
    artifact_store().write_global("profile.json", data)
    return data


@app.get("/criteria")
def get_criteria():
    return artifact_store().read_global("criteria.json", {})


@app.put("/criteria")
def put_criteria(req: CriteriaUpdate):
    data = req.model_dump()
    artifact_store().write_global("criteria.json", data)
    return data


@app.get("/settings")
def get_settings():
    data = artifact_store().read_global("settings.json", {})
    masked = {**data}
    for field in _KEY_FIELDS:
        if masked.get(field):
            masked[field] = _mask_key(masked[field])
    return masked


@app.put("/settings")
def put_settings(req: SettingsUpdate):
    store = artifact_store()
    existing = store.read_global("settings.json", {})
    incoming = req.model_dump()
    for field in _KEY_FIELDS:
        if incoming.get(field, "").endswith("-****"):
            incoming[field] = existing.get(field, "")
    store.write_global("settings.json", {**existing, **incoming})
    return get_settings()


@app.get("/jobs/{job_id}/tracking")
def get_tracking(job_id: str):
    _job_dir_or_404(artifact_store(), job_id)
    return artifact_store().read_json(job_id, "tracking.json", {})


@app.put("/jobs/{job_id}/tracking")
def put_tracking(job_id: str, req: TrackingUpdate):
    if req.status not in ALLOWED_TRACKING_STATUSES:
        raise HTTPException(status_code=400, detail=f"invalid status: {req.status}")
    store = artifact_store()
    _job_dir_or_404(store, job_id)
    existing = store.read_json(job_id, "tracking.json", {"history": []})
    existing.setdefault("history", [])
    existing["status"] = req.status
    existing["notes"] = req.notes
    existing["updated_at"] = utc_now()
    existing["history"].append({"status": req.status, "notes": req.notes, "at": utc_now()})
    store.write_json(job_id, "tracking.json", existing)
    return existing


@app.post("/jobs/{job_id}/send")
def send_job_email(job_id: str, req: SendRequest):
    store = artifact_store()
    _job_dir_or_404(store, job_id)
    pkg = store.read_json(job_id, "package.json")
    if not pkg:
        raise HTTPException(status_code=400, detail="no package — run phase3 first")
    if not req.to_email:
        raise HTTPException(status_code=400, detail="to_email required")
    if send_email is None:
        raise HTTPException(status_code=503, detail="gmail_sender not available")
    try:
        send_email(
            to_email=req.to_email,
            subject=pkg.get("email_subject", ""),
            body=pkg.get("email_body", ""),
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    tracking = {
        "status": "sent",
        "to_email": req.to_email,
        "sent_at": utc_now(),
        "updated_at": utc_now(),
        "history": [{"status": "sent", "at": utc_now()}],
    }
    store.write_json(job_id, "tracking.json", tracking)
    return {"ok": True, "tracking": tracking}


@app.post("/jobs/{job_id}/followup")
def send_followup_email(job_id: str, req: SendRequest):
    store = artifact_store()
    _job_dir_or_404(store, job_id)
    if send_email is None:
        raise HTTPException(status_code=503, detail="gmail_sender not available")
    pkg = store.read_json(job_id, "package.json", {})
    subject = f"Following up — {pkg.get('email_subject', job_id)}"
    body = "Hi,\n\nJust following up on my previous email. Still very interested in the role.\n\nBest,\nSohaib"
    try:
        send_email(to_email=req.to_email, subject=subject, body=body)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    followups = store.read_json(job_id, "followups.json", [])
    followups.append({"sent_at": utc_now(), "to_email": req.to_email, "subject": subject, "body": body})
    store.write_json(job_id, "followups.json", followups)
    return {"ok": True, "followup_count": len(followups)}


@app.get("/jobs/{job_id}/history")
def get_history(job_id: str):
    _job_dir_or_404(artifact_store(), job_id)
    return artifact_store().read_json(job_id, "history.json", [])


@app.post("/jobs/{job_id}/generation/select")
def select_generation_provider(job_id: str, req: SelectProviderRequest):
    import shutil
    if req.provider not in ("gemini", "groq"):
        raise HTTPException(status_code=400, detail="provider must be 'gemini' or 'groq'")
    store = artifact_store()
    generation = store.read_json(job_id, "generation.json", {})
    if generation.get("provider") != "both":
        raise HTTPException(status_code=400, detail="job was not generated with provider='both'")
    if generation.get(req.provider) is None:
        raise HTTPException(status_code=400, detail=f"{req.provider} result is not available")
    job_dir = store.job_dir(job_id)
    src_pdf = job_dir / f"resume_{req.provider}.pdf"
    src_pkg = job_dir / f"package_{req.provider}.json"
    if src_pdf.exists():
        shutil.copy(src_pdf, job_dir / "resume.pdf")
    if src_pkg.exists():
        shutil.copy(src_pkg, job_dir / "package.json")
    generation["selected"] = req.provider
    store.write_json(job_id, "generation.json", generation)
    return {"ok": True, "selected": req.provider}


@app.post("/jobs/{job_id}/regen", status_code=202)
def regen_job(job_id: str, req: RegenRequest):
    store = artifact_store()
    _job_dir_or_404(store, job_id)
    if req.hint:
        store.write_json(job_id, "regen_hints.json", {"hint": req.hint, "requested_at": utc_now()})

    def _run(log_fn=None):
        return run_phase3(job_id=job_id, log_fn=log_fn)

    run = registry.start(f"regen:{job_id}", _run)
    history = store.read_json(job_id, "history.json", [])
    history.append({"event": "regen_requested", "hint": req.hint, "run_id": run.run_id, "at": utc_now()})
    store.write_json(job_id, "history.json", history)
    return {"run_id": run.run_id}


@app.get("/analytics/funnel")
def analytics_funnel():
    return compute_funnel(artifact_store())


@app.get("/analytics/response-rate")
def analytics_response_rate():
    return compute_response_rate(artifact_store())


@app.get("/analytics/sources")
def analytics_sources():
    return compute_sources(artifact_store())


@app.get("/analytics/sent-today")
def analytics_sent_today():
    store = artifact_store()
    data = compute_sent_today(store)
    settings = store.read_global("settings.json", {})
    data["limit"] = settings.get("daily_email_limit", 10)
    return data


@app.post("/jobs/bulk-send")
def bulk_send(req: BulkSendRequest):
    store = artifact_store()
    settings = store.read_global("settings.json", {})
    daily_limit = settings.get("daily_email_limit", 10)
    sent_today_data = compute_sent_today(store)
    remaining = daily_limit - sent_today_data["sent_today"]

    results: dict[str, dict] = {}
    sent_count = 0

    for job_id in req.job_ids:
        if sent_count >= remaining:
            results[job_id] = {"ok": False, "error": "daily limit reached"}
            continue
        try:
            pkg = store.read_json(job_id, "package.json", {})
            to_email = pkg.get("to_email", "")
            if not to_email:
                results[job_id] = {"ok": False, "error": "no to_email in package.json"}
                continue
            if not req.dry_run:
                if send_email is None:
                    results[job_id] = {"ok": False, "error": "gmail_sender not available"}
                    continue
                send_email(
                    to_email=to_email,
                    subject=pkg.get("email_subject", ""),
                    body=pkg.get("email_body", ""),
                )
                tracking = {
                    "status": "sent",
                    "to_email": to_email,
                    "sent_at": utc_now(),
                    "updated_at": utc_now(),
                    "history": [{"status": "sent", "at": utc_now()}],
                }
                store.write_json(job_id, "tracking.json", tracking)
            results[job_id] = {"ok": True, "to_email": to_email}
            sent_count += 1
        except Exception as exc:
            results[job_id] = {"ok": False, "error": str(exc)}

    return {"results": results, "sent": sent_count, "dry_run": req.dry_run}


@app.get("/review-queue")
def review_queue():
    rows = []
    for job in artifact_store().list_jobs():
        if job.get("generation", {}).get("status") != "generated":
            continue
        if job.get("review", {}).get("status", "pending") != "pending":
            continue
        rows.append(job)
    return rows
