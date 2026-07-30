import os
from pathlib import Path
from pdf_generator import render_tex, generate_pdf, compile_tex_to_pdf
from ai_engine import ApplicationPackage

def test_template_exists():
    assert Path("templates/resume.tex").exists()

def test_render_tex():
    pkg = ApplicationPackage(
        company="TestCo", role="SE", match_score=90, summary="",
        tailored_experience=[
            {"company": "Test", "role": "Dev", "bullets": ["Did a thing"], "period": "2020-2021", "location": "Remote"},
            {"company": "Test (Project)", "role": "Dev", "bullets": ["Did a thing"], "period": "2020-2021", "location": "Remote"}
        ],
        tailored_skills={"Languages": ["Python"]},
        keywords_matched=[], keywords_missing=[], email_subject="", email_body="",
        headline="Backend-Leaning Full-Stack Engineer | Async APIs · Postgres | @Hughes · ex-IndiaMart",
    )
    tex_output = render_tex(pkg)
    assert "Test" in tex_output
    assert "Did a thing" in tex_output
    # AI-tailored headline is injected; the old hardcoded tagline is gone.
    assert "@Hughes · ex-IndiaMart" in tex_output
    assert "4+ YOE" not in tex_output

def test_compile_tex_to_pdf(tmp_path):
    import shutil
    import pytest
    if not shutil.which("pdflatex"):
        pytest.skip("pdflatex not installed")
    tex = r"""\documentclass{article}\begin{document}Hello world\end{document}"""
    out = str(tmp_path / "out.pdf")
    pdf_path, page_count = compile_tex_to_pdf(tex, out)
    assert os.path.exists(pdf_path)
    assert isinstance(page_count, int)
    assert page_count >= 1


def test_compile_tex_to_pdf_bad_latex_raises(tmp_path):
    import shutil
    import pytest
    if not shutil.which("pdflatex"):
        pytest.skip("pdflatex not installed")
    with pytest.raises(Exception):
        compile_tex_to_pdf(r"\documentclass{article}\begin{BROKEN}", str(tmp_path / "out.pdf"))


def test_generate_pdf():
    import shutil
    import pytest
    if not shutil.which("pdflatex"):
        pytest.skip("pdflatex not installed")
        
    pkg = ApplicationPackage(
        company="TestCo", role="SE", match_score=90, summary="",
        tailored_experience=[
            {"company": "Test", "role": "Dev", "bullets": ["Did a thing"], "period": "2020-2021", "location": "Remote"},
            {"company": "Test (Project)", "role": "Dev", "bullets": ["Did a thing"], "period": "2020-2021", "location": "Remote"}
        ],
        tailored_skills={"Languages": ["Python"]},
        keywords_matched=["Python"], keywords_missing=[], email_subject="", email_body=""
    )
    pdf_path, page_count = generate_pdf(pkg, "test_output.pdf")
    assert os.path.exists(pdf_path)
    assert page_count >= 1
    # Cleanup
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
