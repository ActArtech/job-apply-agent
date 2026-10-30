import inspect
import shutil
from dataclasses import asdict
from pathlib import Path

from ai_engine import generate_application, _has_numeric_signal, _impact_signal_ratio
from artifact_store import ArtifactStore, build_job_id, utc_now
from job_vetter import vet_job_detail, vetting_status
from pdf_generator import generate_pdf, render_tex, compile_tex_to_pdf
from email_finder import find_hiring_manager
from scraper import get_all_jobs, _extract_domain


def run_phase1(root="artifacts", max_per_source=20, log_fn=None, emit_fn=None):
    def log(msg):
        if log_fn:
            log_fn(msg)

    def emit(event):
        if emit_fn:
            emit_fn(event)

    store = ArtifactStore(root)
    new_job_ids = []
    already_found_job_ids = []

    log(f"scraping jobs (max {max_per_source} per source)…")
    sig = inspect.signature(get_all_jobs)
    if "vet" in sig.parameters:
        jobs = get_all_jobs(max_per_source=max_per_source, vet=False)
    else:
        jobs = get_all_jobs(max_per_source=max_per_source)

    emit({"type": "phase_start", "phase": "phase1", "total": len(jobs)})
    log(f"scraped {len(jobs)} candidates — deduplicating…")
    for job in jobs:
        job_id = build_job_id(job)
        company = getattr(job, "company", job_id)
        title = getattr(job, "title", "")
        if store.has_job(job_id):
            already_found_job_ids.append(job_id)
            log(f"skip: {company} — {title} (duplicate)")
            emit({"type": "job_result", "job_id": job_id, "company": company, "title": title,
                  "status": "duplicate", "reason": "already in artifact store", "engine": None})
            continue
        new_job_ids.append(store.write_job(job, jd_text=job.description))
        log(f"new: {company} — {title}")
        emit({"type": "job_result", "job_id": job_id, "company": company, "title": title,
              "status": "new", "reason": getattr(job, "source", ""), "engine": None})

    emit({"type": "phase_done", "phase": "phase1",
          "new": len(new_job_ids), "duplicates": len(already_found_job_ids)})
    log(f"done: {len(new_job_ids)} new, {len(already_found_job_ids)} duplicates")
    return {
        "phase": "phase1",
        "written": len(new_job_ids),
        "already_found": len(already_found_job_ids),
        "updated": 0,
        "job_ids": new_job_ids,
        "new_job_ids": new_job_ids,
        "already_found_job_ids": already_found_job_ids,
    }


def _vet_with_location(**kwargs):
    """Call vet_job_detail, passing location only if the callable accepts it.

    Keeps compatibility with test doubles and older callables that do not
    take the location argument.
    """
    import inspect

    target = vet_job_detail
    try:
        signature = inspect.signature(target)
    except (TypeError, ValueError):
        signature = None
    if signature is not None:
        accepts_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD
                              for p in signature.parameters.values())
        if not accepts_var_kw and "location" not in signature.parameters:
            kwargs.pop("location", None)
    return target(**kwargs)


def run_phase2(root="artifacts", max_per_source=20, log_fn=None, emit_fn=None, provider="gemini", force=False):
    def log(msg):
        if log_fn:
            log_fn(msg)

    def emit(event):
        if emit_fn:
            emit_fn(event)

    store = ArtifactStore(root)
    approved_job_ids = []
    rejected_job_ids = []
    error_job_ids = []

    all_jobs = store.list_jobs()
    pending = []
    skipped = 0
    for row in all_jobs:
        existing = store.read_json(row["job_id"], "vetting.json", None)
        if not force and vetting_status(existing) in ("approved", "rejected"):
            skipped += 1
            continue
        pending.append(row)

    total = len(pending)
    emit({"type": "phase_start", "phase": "phase2", "total": total, "engine": provider})
    log(f"vetting {total} jobs ({skipped} skipped — already vetted)…")

    for index, row in enumerate(pending, 1):
        job_id = row["job_id"]
        company = row.get("company", job_id)
        title = row.get("title", "")
        emit({"type": "job_start", "job_id": job_id, "company": company, "title": title, "index": index, "total": total})
        log(f"[{index}/{total}] {company} — {title}")
        jd = (store.job_dir(job_id) / "jd.txt").read_text(encoding="utf-8")
        vetting = _vet_with_location(
            company=row["company"],
            role=row["title"],
            url=row.get("url", ""),
            jd=jd,
            provider=provider,
            location=row.get("location", ""),
        )
        vetting["created_at"] = utc_now()
        store.write_json(job_id, "vetting.json", vetting)

        status = vetting_status(vetting)
        reason = vetting.get("reason") or vetting.get("error") or ""
        answered = (vetting.get("engine") or {}).get("answered")
        if status == "approved":
            approved_job_ids.append(job_id)
            log("  ✓ approved")
        elif status == "error":
            error_job_ids.append(job_id)
            log(f"  ⚠ couldn't vet: {reason}")
        else:
            rejected_job_ids.append(job_id)
            log(f"  ✗ rejected: {reason}")
        emit({
            "type": "job_result", "job_id": job_id, "company": company, "title": title,
            "status": status, "reason": reason, "engine": answered, "score": vetting.get("score"),
        })
        emit({
            "type": "progress", "done": index, "total": total,
            "approved": len(approved_job_ids), "rejected": len(rejected_job_ids), "errors": len(error_job_ids),
        })

    summary = {
        "approved": len(approved_job_ids), "rejected": len(rejected_job_ids),
        "errors": len(error_job_ids), "skipped": skipped,
    }
    emit({"type": "phase_done", "phase": "phase2", **summary})
    log(f"done: {summary['approved']} approved, {summary['rejected']} rejected, "
        f"{summary['errors']} errors, {skipped} skipped (already vetted)")
    return {
        "phase": "phase2",
        "reviewed": total,
        **summary,
        "approved_job_ids": approved_job_ids,
        "rejected_job_ids": rejected_job_ids,
        "error_job_ids": error_job_ids,
    }


def run_phase3(root="artifacts", job_id=None, log_fn=None, provider="gemini"):
    def log(msg):
        if log_fn:
            log_fn(msg)

    store = ArtifactStore(root)
    if not job_id:
        raise ValueError("job_id is required")
    job = store.read_json(job_id, "job.json")
    vetting = store.read_json(job_id, "vetting.json", {})
    if vetting.get("approved") is not True:
        raise ValueError(f"job {job_id} must be approved by phase2 before phase3")

    log(f"generating for {job.get('company')} — {job.get('title')} (provider={provider})")
    jd = (store.job_dir(job_id) / "jd.txt").read_text(encoding="utf-8")
    log("calling Gemini…" if provider != "groq" else "calling Groq…")

    pkg_result = generate_application(
        company=job["company"],
        role=job["title"],
        jd=jd,
        hiring_manager="",
        provider=provider,
    )

    if provider == "both":
        if not pkg_result or (pkg_result.get("gemini") is None and pkg_result.get("groq") is None):
            raise RuntimeError("generate_application returned None for both providers")
        return _run_phase3_both(store, job_id, pkg_result, log_fn)

    if not pkg_result:
        raise RuntimeError("generate_application returned None")

    return _run_phase3_single(store, job_id, pkg_result, log_fn, provider)


def _run_phase3_single(store, job_id, pkg, log_fn, provider):
    def log(msg):
        if log_fn:
            log_fn(msg)

    job_dir = store.job_dir(job_id)
    log("rendering PDF…")
    package = asdict(pkg)
    store.write_json(job_id, "package.json", package)
    (job_dir / "email.txt").write_text(pkg.email_body, encoding="utf-8")
    (job_dir / "resume.tex").write_text(render_tex(pkg), encoding="utf-8")
    pdf_path, page_count = generate_pdf(pkg, str(job_dir / "resume.pdf"))
    bullets = [b for exp in pkg.tailored_experience for b in exp.get("bullets", [])]
    numeric = sum(1 for b in bullets if _has_numeric_signal(b))
    total_b = len(bullets)
    generation = {
        "status": "generated",
        "provider": provider,
        "pdf_path": str(Path(pdf_path).name),
        "page_count": page_count,
        "impact_signal_ratio": _impact_signal_ratio(bullets),
        "numeric_bullets": numeric,
        "total_bullets": total_b,
        "created_at": utc_now(),
    }
    store.write_json(job_id, "generation.json", generation)
    log(f"done: {page_count}p PDF · {numeric}/{total_b} numeric bullets")
    return generation


def _run_phase3_both(store, job_id, pkg_dict, log_fn):
    def log(msg):
        if log_fn:
            log_fn(msg)

    job_dir = store.job_dir(job_id)
    log("rendering PDFs for both providers…")

    gemini_gen = None
    groq_gen = None

    for prov, pkg in [("gemini", pkg_dict.get("gemini")), ("groq", pkg_dict.get("groq"))]:
        if pkg is None:
            continue
        package = asdict(pkg)
        store.write_json(job_id, f"package_{prov}.json", package)
        (job_dir / f"email_{prov}.txt").write_text(pkg.email_body, encoding="utf-8")
        tex_content = render_tex(pkg)
        (job_dir / f"resume_{prov}.tex").write_text(tex_content, encoding="utf-8")
        pdf_path, page_count = generate_pdf(pkg, str(job_dir / f"resume_{prov}.pdf"))
        bullets = [b for exp in pkg.tailored_experience for b in exp.get("bullets", [])]
        numeric = sum(1 for b in bullets if _has_numeric_signal(b))
        total_b = len(bullets)
        gen = {
            "pdf_path": f"resume_{prov}.pdf",
            "page_count": page_count,
            "impact_signal_ratio": _impact_signal_ratio(bullets),
            "numeric_bullets": numeric,
            "total_bullets": total_b,
        }
        if prov == "gemini":
            gemini_gen = gen
        else:
            groq_gen = gen

    generation = {
        "status": "generated",
        "provider": "both",
        "selected": None,
        "gemini": gemini_gen,
        "groq": groq_gen,
        "created_at": utc_now(),
    }
    store.write_json(job_id, "generation.json", generation)
    log("done: both providers generated")
    return generation


def run_phase2_single(root="artifacts", job_id=None, log_fn=None):
    """Vet a single job by job_id and write vetting.json."""
    def log(msg):
        if log_fn:
            log_fn(msg)

    if not job_id:
        raise ValueError("job_id is required")

    store = ArtifactStore(root)
    row = store.read_json(job_id, "job.json")
    if not row:
        raise ValueError(f"job {job_id} not found")

    log(f"vetting {row.get('company')} — {row.get('title')}…")
    jd = (store.job_dir(job_id) / "jd.txt").read_text(encoding="utf-8")
    vetting = _vet_with_location(
        company=row["company"],
        role=row["title"],
        url=row.get("url", ""),
        jd=jd,
        location=row.get("location", ""),
    )
    vetting["created_at"] = utc_now()
    store.write_json(job_id, "vetting.json", vetting)
    status = vetting_status(vetting)
    icon = {"approved": "✓ approved", "error": "⚠ couldn't vet"}.get(status, "✗ rejected")
    log(f"{icon}: {vetting.get('reason') or ''}")
    return {"phase": "phase2-single", "job_id": job_id, "approved": status == "approved", "status": status, "reason": vetting.get("reason", "")}


def run_phase3_pdf_only(root="artifacts", job_id=None, log_fn=None):
    """Re-compile PDF from existing resume.tex without re-running AI generation."""
    def log(msg):
        if log_fn:
            log_fn(msg)

    if not job_id:
        raise ValueError("job_id is required")

    store = ArtifactStore(root)
    job_dir = store.job_dir(job_id)
    tex_path = job_dir / "resume.tex"
    if not tex_path.exists():
        raise ValueError(f"resume.tex not found for {job_id} — run full phase3 first")

    pkg = store.read_json(job_id, "package.json")
    if not pkg:
        raise ValueError(f"package.json not found for {job_id} — run full phase3 first")

    log(f"re-compiling PDF for {job_id}…")
    tex_content = tex_path.read_text(encoding="utf-8")
    pdf_path, page_count = compile_tex_to_pdf(tex_content, str(job_dir / "resume.pdf"))

    existing_gen = store.read_json(job_id, "generation.json", {})
    generation = {
        **existing_gen,
        "status": "generated",
        "page_count": page_count,
        "pdf_recompiled_at": utc_now(),
    }
    store.write_json(job_id, "generation.json", generation)
    log(f"done: {page_count}p PDF")
    return generation


def run_phase3_all(root="artifacts", limit=20, log_fn=None, emit_fn=None, provider="gemini"):
    def log(msg):
        if log_fn:
            log_fn(msg)

    def emit(event):
        if emit_fn:
            emit_fn(event)

    store = ArtifactStore(root)
    generated = []
    failed = []
    approved = [r for r in store.list_jobs() if vetting_status(r.get("vetting")) == "approved"]
    total = min(len(approved), limit)
    emit({"type": "phase_start", "phase": "phase3-all", "total": total, "engine": provider})
    log(f"{total} approved jobs to generate… (provider={provider})")

    for i, row in enumerate(approved[:limit], 1):
        company = row.get("company", row["job_id"])
        title = row.get("title", "")
        emit({"type": "job_start", "job_id": row["job_id"], "company": company, "title": title, "index": i, "total": total})
        log(f"[{i}/{total}] {company} — {title}")
        try:
            result = run_phase3(root=root, job_id=row["job_id"], log_fn=log_fn, provider=provider)
            generated.append({"job_id": row["job_id"], **result})
            emit({"type": "job_result", "job_id": row["job_id"], "company": company, "title": title,
                  "status": "generated", "reason": f"{result.get('page_count', '?')}p PDF", "engine": provider})
        except Exception as e:
            failed.append({"job_id": row["job_id"], "error": str(e)})
            emit({"type": "job_result", "job_id": row["job_id"], "company": company, "title": title,
                  "status": "failed", "reason": str(e), "engine": provider})
            log(f"  ✗ failed: {e}")
        emit({"type": "progress", "done": i, "total": total})

    emit({"type": "phase_done", "phase": "phase3-all", "generated": len(generated), "failed": len(failed)})
    log(f"done: {len(generated)} generated, {len(failed)} failed")
    return {
        "phase": "phase3-all",
        "generated": len(generated),
        "failed": len(failed),
        "results": generated,
        "errors": failed,
    }


def run_phase4_single(root="artifacts", job_id=None, log_fn=None):
    """Find hiring manager contact for a single job and write contact.json."""
    def log(msg):
        if log_fn:
            log_fn(msg)

    if not job_id:
        raise ValueError("job_id is required")

    store = ArtifactStore(root)
    row = store.read_json(job_id, "job.json")
    if not row:
        raise ValueError(f"job {job_id} not found")

    company = row.get("company", "")
    domain = _extract_domain(row.get("url", ""))
    log(f"finding contact for {company} ({domain})…")

    contact = find_hiring_manager(domain, company)
    if contact:
        payload = {
            "email": contact.email,
            "first_name": contact.first_name,
            "last_name": contact.last_name,
            "title": contact.title or getattr(contact, "position", ""),
            "linkedin_url": contact.linkedin_url,
            "discovery_method": contact.discovery_method,
            "found_at": utc_now(),
        }
        store.write_json(job_id, "contact.json", payload)
        if contact.email:
            tracking = store.read_json(job_id, "tracking.json", {}) or {}
            tracking["to_email"] = contact.email
            store.write_json(job_id, "tracking.json", tracking)
            log(f"✓ found: {contact.email}")
        else:
            log(f"partial: LinkedIn found but no email — {contact.linkedin_url}")
    else:
        log("✗ no contact found")

    return {
        "phase": "phase4-single",
        "job_id": job_id,
        "found": bool(contact and contact.email),
        "partial": bool(contact and not contact.email),
    }


def run_phase4(root="artifacts", limit=20, log_fn=None, emit_fn=None):
    """Find hiring manager contacts for all generated jobs (up to limit), skipping already-found."""
    def log(msg):
        if log_fn:
            log_fn(msg)

    def emit(event):
        if emit_fn:
            emit_fn(event)

    store = ArtifactStore(root)
    jobs = store.list_jobs()
    targets = [
        r for r in jobs
        if r.get("generation", {}).get("status") == "generated"
        and not store.read_json(r["job_id"], "contact.json", None)
    ][:limit]

    emit({"type": "phase_start", "phase": "phase4", "total": len(targets)})
    log(f"phase 4: finding contacts for {len(targets)} jobs…")
    results = {"found": 0, "partial": 0, "not_found": 0}

    for index, row in enumerate(targets, 1):
        job_id = row["job_id"]
        company = row.get("company", job_id)
        title = row.get("title", "")
        emit({"type": "job_start", "job_id": job_id, "company": company, "title": title, "index": index, "total": len(targets)})
        result = run_phase4_single(root=root, job_id=job_id, log_fn=log_fn)
        if result["found"]:
            results["found"] += 1
            status = "found"
        elif result["partial"]:
            results["partial"] += 1
            status = "partial"
        else:
            results["not_found"] += 1
            status = "not_found"
        contact = store.read_json(job_id, "contact.json", {}) or {}
        emit({"type": "job_result", "job_id": job_id, "company": company, "title": title,
              "status": status, "reason": contact.get("email") or contact.get("linkedin_url") or "no contact found",
              "engine": None})
        emit({"type": "progress", "done": index, "total": len(targets)})

    emit({"type": "phase_done", "phase": "phase4", **results})
    return {"phase": "phase4", **results}
