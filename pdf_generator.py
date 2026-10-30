import os
import shutil
import jinja2
from ai_engine import ApplicationPackage
from config import MY_NAME, MY_EMAIL, MY_PHONE, MY_PORTFOLIO, RESUME

# Set up Jinja2 environment with custom delimiters to avoid conflict with LaTeX {}
latex_jinja_env = jinja2.Environment(
    block_start_string='<%',
    block_end_string='%>',
    variable_start_string='<<',
    variable_end_string='>>',
    comment_start_string='<#',
    comment_end_string='#>',
    trim_blocks=True,
    autoescape=False,
    loader=jinja2.FileSystemLoader(os.path.abspath('.'))
)

def escape_latex(val):
    """
    Recursively escape strings for LaTeX to prevent issues with characters like % and &.
    """
    if isinstance(val, str):
        val = val.replace('\\', r'\textbackslash{}')
        val = val.replace('%', r'\%')
        val = val.replace('$', r'\$')
        val = val.replace('#', r'\#')
        val = val.replace('_', r'\_')
        val = val.replace('{', r'\{')
        val = val.replace('}', r'\}')
        val = val.replace('&', r'\&')
        val = val.replace('^', r'\textasciicircum{}')
        val = val.replace('~', r'\textasciitilde{}')
        return val
    elif isinstance(val, list):
        return [escape_latex(x) for x in val]
    elif isinstance(val, dict):
        return {escape_latex(k): escape_latex(v) for k, v in val.items()}
    return val

def render_tex(pkg: ApplicationPackage) -> str:
    template = latex_jinja_env.get_template('templates/resume.tex')
    
    # We need to merge period and location from RESUME into the AI's tailored_experience
    # because the AI output only includes company, role, and bullets
    tailored_exp = pkg.tailored_experience
    
    for i, exp in enumerate(tailored_exp):
        if i < len(RESUME["experience"]):
            # Preserve original metadata
            exp["period"] = RESUME["experience"][i].get("period", "")
            exp["location"] = RESUME["experience"][i].get("location", "")
    
    # Split into experience and projects based on the 'Project' tag in the company name
    exp_list = []
    proj_list = []
    for exp in tailored_exp:
        if "Project" in exp.get("company", ""):
            # Reformat for the projects section of the template
            proj_list.append({
                "name": exp["company"].replace(" (Project)", ""),
                "role": exp["role"],
                "period": exp.get("period", ""),
                "location": exp.get("location", ""),
                "bullets": exp["bullets"]
            })
        else:
            exp_list.append(exp)
            
    education = RESUME.get("education", {})
    skills = pkg.tailored_skills if getattr(pkg, 'tailored_skills', None) else RESUME.get("skills", {})
    
    context = {
        'name': MY_NAME,
        'phone': MY_PHONE,
        'email': MY_EMAIL,
        'portfolio': MY_PORTFOLIO,
        'headline': pkg.headline,
        'experience': exp_list,
        'projects': proj_list,
        'education': education,
        'skills': skills
    }
    
    # Escape context so things like '%' in '23%' don't break LaTeX
    context = escape_latex(context)
    
    return template.render(**context)

def compile_tex_to_pdf(tex_content: str, output_filename: str) -> tuple[str, int]:
    """Compile a LaTeX string to PDF without re-rendering from an ApplicationPackage."""
    import subprocess
    import tempfile
    import shutil
    import re

    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = os.path.join(tmpdir, "resume.tex")
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(tex_content)
        try:
            result = subprocess.run(
                [_find_pdflatex(), "-interaction=nonstopmode", "-halt-on-error", "resume.tex"],
                cwd=tmpdir,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            output_log = result.stdout.decode("utf-8", errors="replace")
            page_count = 1
            match = re.search(r"Output written on .*? \((\d+) pages?,", output_log)
            if match:
                page_count = int(match.group(1))
            pdf_tmp = os.path.join(tmpdir, "resume.pdf")
            output_path = os.path.abspath(output_filename)
            shutil.copy(pdf_tmp, output_path)
            return output_path, page_count
        except subprocess.CalledProcessError as e:
            print("pdflatex compilation failed!")
            print(e.stdout.decode("utf-8", errors="replace"))
            raise e


def _find_pdflatex() -> str:
    """Locate the pdflatex executable.

    The Windows per-user MiKTeX install is not on PATH for non-interactive
    shells, so an absolute fallback path is tried.
    """
    found = shutil.which("pdflatex")
    if found:
        return found
    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\MiKTeX\miktex\bin\x64\pdflatex.exe"),
        r"C:\Program Files\MiKTeX\miktex\bin\x64\pdflatex.exe",
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return "pdflatex"


def generate_pdf(pkg: ApplicationPackage, output_filename: str) -> tuple[str, int]:
    import subprocess
    import tempfile
    import shutil
    import re
    
    tex_content = render_tex(pkg)
    
    # We create a temporary directory to compile the latex so it doesn't leave auxiliary files everywhere
    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = os.path.join(tmpdir, "resume.tex")
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(tex_content)
            
        try:
            # Run pdflatex
            result = subprocess.run(
                [_find_pdflatex(), "-interaction=nonstopmode", "-halt-on-error", "resume.tex"],
                cwd=tmpdir,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            output_log = result.stdout.decode('utf-8', errors='replace')
            
            # Find page count in output like "Output written on resume.pdf (1 page, 65000 bytes)."
            page_count = 1
            match = re.search(r"Output written on .*? \((\d+) pages?,", output_log)
            if match:
                page_count = int(match.group(1))
            
            # The PDF will be in tmpdir/resume.pdf
            pdf_tmp_path = os.path.join(tmpdir, "resume.pdf")
            
            # Move to the desired output location
            output_path = os.path.abspath(output_filename)
            shutil.copy(pdf_tmp_path, output_path)
            return output_path, page_count
        except subprocess.CalledProcessError as e:
            # Print the stdout so the user can see what failed in latex compilation
            print("pdflatex compilation failed!")
            print(e.stdout.decode('utf-8', errors='replace'))
            raise e


