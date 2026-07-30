from scraper import Job, _company_region, _work_mode


def make_job(location="", description="", source="remotive", remote=False, title="Backend Engineer", company="Acme"):
    return Job(
        title=title, company=company, company_domain="",
        location=location, url="https://x.com/j", description=description,
        source=source, remote=remote,
    )


def test_region_india_from_location_marker():
    assert _company_region(make_job(location="Bengaluru, India")) == "india"


def test_region_india_from_instahyre_source():
    assert _company_region(make_job(source="instahyre")) == "india"


def test_region_foreign_from_marker():
    assert _company_region(make_job(location="Berlin, Germany")) == "foreign"


def test_region_remote_only_is_unknown_not_foreign():
    job = make_job(location="Remote", remote=True)
    assert _company_region(job) == "unknown"


def test_region_unknown_when_no_markers():
    assert _company_region(make_job(location="", description="Great role")) == "unknown"


def test_work_mode_remote():
    assert _work_mode(make_job(location="Remote", remote=True)) == "remote"


def test_work_mode_hybrid():
    assert _work_mode(make_job(location="Bengaluru (Hybrid)", description="hybrid setup")) == "hybrid"


def test_work_mode_wfo_for_india_onsite():
    assert _work_mode(make_job(location="Mumbai, India")) == "wfo"


def test_work_mode_unknown():
    assert _work_mode(make_job(location="", description="role")) == "unknown"


def test_job_has_region_and_work_mode_fields():
    job = make_job()
    assert job.region == ""
    assert job.work_mode == ""
