import argparse
import csv
import json
import shutil
from datetime import date
from pathlib import Path
from typing import Optional

from artifact_store import ArtifactStore, utc_now
from config import SHEET_COLUMNS
from scraper import Job


EXACT_OUTCOMES = {
    "submitted": "Exact URL Submitted",
    "pending": "Exact URL Pending",
    "blocked": "Exact URL Blocked",
    "failed": "Exact URL Failed",
}


def _path_or_none(path):
    if not path:
        return None
    return Path(path)


def _read_submit_result(path: Optional[Path]) -> dict:
    if not path or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _copy_if_present(source: Optional[Path], destination: Path) -> Optional[Path]:
    if not source:
        return None
    if not source.exists():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def _csv_has_row(csv_path: Path, url: str, outcome: str) -> bool:
    if not csv_path.exists():
        return False
    with csv_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("JD URL") == url and row.get("Outcome") == outcome:
                return True
    return False


def _csv_fieldnames(csv_path: Path) -> list[str]:
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return SHEET_COLUMNS
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            return SHEET_COLUMNS
    return header or SHEET_COLUMNS


def _append_csv_row(
    csv_path: Path,
    company: str,
    role: str,
    url: str,
    match_score: Optional[int],
    outcome: str,
    notes: str,
) -> bool:
    if _csv_has_row(csv_path, url, outcome):
        return False

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = csv_path.exists()
    fieldnames = _csv_fieldnames(csv_path)
    row = {
        "Date": date.today().isoformat(),
        "Company": company,
        "Role": role,
        "JD URL": url,
        "Hiring Manager": "",
        "Their Email": "",
        "LinkedIn URL": "",
        "Match Score": f"{match_score}%" if match_score is not None else "",
        "Outcome": outcome,
        "Email Sent?": "No",
        "Email Subject": "",
        "Follow-up Sent?": "No",
        "Response": "",
        "Notes": notes,
    }
    with csv_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        if not file_exists or csv_path.stat().st_size == 0:
            writer.writeheader()
        writer.writerow(row)
    return True


def record_exact_application(
    company: str,
    role: str,
    url: str,
    jd_text: str,
    resume_path,
    submit_result_path=None,
    artifact_root="artifacts",
    csv_path="applications.csv",
    match_score: Optional[int] = None,
    status: str = "submitted",
    notes: str = "",
    location: str = "",
):
    status = (status or "submitted").lower()
    outcome = EXACT_OUTCOMES.get(status, f"Exact URL {status.title()}")
    resume_source = _path_or_none(resume_path)
    submit_source = _path_or_none(submit_result_path)

    job = Job(
        title=role,
        company=company,
        company_domain="",
        location=location,
        url=url,
        description=jd_text,
        source="exact-url",
        remote=False,
    )
    store = ArtifactStore(artifact_root)
    job_id = store.write_job(job, jd_text=jd_text)
    job_dir = store.job_dir(job_id)

    resume_artifact = _copy_if_present(resume_source, job_dir / "resume.pdf")
    submit_artifact = _copy_if_present(submit_source, job_dir / "submit_result.json")
    submit_result = _read_submit_result(submit_artifact)

    now = utc_now()
    tracking = store.read_json(job_id, "tracking.json", {"history": []})
    tracking.setdefault("history", [])
    tracking.update(
        {
            "status": status,
            "apply_type": "exact_url",
            "outcome": outcome,
            "source_url": url,
            "resume_artifact": str(resume_artifact) if resume_artifact else "",
            "submit_result_artifact": str(submit_artifact) if submit_artifact else "",
            "confirmation_url": submit_result.get("url", ""),
            "notes": notes,
            "updated_at": now,
        }
    )
    if status == "submitted" and not tracking.get("submitted_at"):
        tracking["submitted_at"] = now
    tracking["history"].append({"status": status, "outcome": outcome, "notes": notes, "at": now})
    store.write_json(job_id, "tracking.json", tracking)

    store.write_json(
        job_id,
        "generation.json",
        {
            "status": "generated",
            "match_score": match_score,
            "resume_artifact": str(resume_artifact) if resume_artifact else "",
            "updated_at": now,
        },
    )

    note_parts = []
    if resume_artifact:
        note_parts.append(f"resume={resume_artifact}")
    if submit_artifact:
        note_parts.append(f"submit_result={submit_artifact}")
    if notes:
        note_parts.append(notes)
    csv_appended = _append_csv_row(
        Path(csv_path),
        company=company,
        role=role,
        url=url,
        match_score=match_score,
        outcome=outcome,
        notes="; ".join(note_parts),
    )

    return {
        "job_id": job_id,
        "job_dir": str(job_dir),
        "resume_artifact": str(resume_artifact) if resume_artifact else "",
        "submit_result_artifact": str(submit_artifact) if submit_artifact else "",
        "tracking": tracking,
        "csv_appended": csv_appended,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Record an exact-URL job application.")
    parser.add_argument("--company", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--jd-file")
    parser.add_argument("--jd-text", default="")
    parser.add_argument("--resume", required=True)
    parser.add_argument("--submit-result")
    parser.add_argument("--artifact-root", default="artifacts")
    parser.add_argument("--csv", default="applications.csv")
    parser.add_argument("--match-score", type=int)
    parser.add_argument("--status", default="submitted")
    parser.add_argument("--notes", default="")
    parser.add_argument("--location", default="")
    args = parser.parse_args(argv)

    jd_text = args.jd_text
    if args.jd_file:
        jd_text = Path(args.jd_file).read_text(encoding="utf-8")

    result = record_exact_application(
        company=args.company,
        role=args.role,
        url=args.url,
        jd_text=jd_text,
        resume_path=args.resume,
        submit_result_path=args.submit_result,
        artifact_root=args.artifact_root,
        csv_path=args.csv,
        match_score=args.match_score,
        status=args.status,
        notes=args.notes,
        location=args.location,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
