from datetime import datetime, timezone

from artifact_store import ArtifactStore


def compute_funnel(store: ArtifactStore) -> dict:
    rows = store.list_jobs()
    gathered = len(rows)
    vetted = sum(1 for r in rows if r.get("vetting"))
    approved = sum(1 for r in rows if r.get("vetting", {}).get("approved") is True)
    generated = sum(1 for r in rows if r.get("generation", {}).get("status") == "generated")
    reviewed = sum(
        1 for r in rows
        if r.get("review", {}).get("status") in {"approved", "rejected", "needs_regen"}
    )
    sent = sum(1 for r in rows if r.get("tracking", {}).get("status") == "sent")
    return {
        "gathered": gathered,
        "vetted": vetted,
        "approved": approved,
        "generated": generated,
        "reviewed": reviewed,
        "sent": sent,
    }


def compute_response_rate(store: ArtifactStore) -> dict:
    rows = store.list_jobs()
    statuses = [r.get("tracking", {}).get("status", "") for r in rows]
    sent = sum(1 for s in statuses if s in {"sent", "replied", "interview", "offer", "rejected"})
    replied = sum(1 for s in statuses if s in {"replied", "interview", "offer"})
    interview = sum(1 for s in statuses if s in {"interview", "offer"})
    offer = sum(1 for s in statuses if s == "offer")
    return {
        "sent": sent,
        "replied": replied,
        "interview": interview,
        "offer": offer,
        "rate_reply": round(replied / sent, 3) if sent else 0,
        "rate_interview": round(interview / sent, 3) if sent else 0,
    }


def compute_sources(store: ArtifactStore) -> list:
    rows = store.list_jobs()
    sources: dict = {}
    for r in rows:
        src = r.get("source", "unknown")
        if src not in sources:
            sources[src] = {"source": src, "total": 0, "approved": 0, "generated": 0, "sent": 0}
        sources[src]["total"] += 1
        if r.get("vetting", {}).get("approved") is True:
            sources[src]["approved"] += 1
        if r.get("generation", {}).get("status") == "generated":
            sources[src]["generated"] += 1
        if r.get("tracking", {}).get("status") == "sent":
            sources[src]["sent"] += 1
    return sorted(sources.values(), key=lambda x: x["total"], reverse=True)


def compute_sent_today(store: ArtifactStore) -> dict:
    rows = store.list_jobs()
    today = datetime.now(timezone.utc).date().isoformat()
    sent_today = sum(
        1 for r in rows
        if (r.get("tracking", {}).get("sent_at") or "").startswith(today)
    )
    return {"sent_today": sent_today}
