"""
Resume tailoring module.
Given a job description, uses Claude to produce a tailored resume JSON,
then renders it to a PDF using a template.

Flow:
  1. Load base resume JSON (parsed from PDF once)
  2. Send JD + resume to Claude → tailored resume JSON
  3. Render PDF using a simple HTML → PDF pipeline (weasyprint)
  4. Cache result keyed by (platform, job_id) to avoid repeat LLM calls
"""

import hashlib
import json
import os
import yaml
from pathlib import Path
from anthropic import Anthropic

_BASE_DIR = Path(__file__).parent.parent
_CACHE_DIR = _BASE_DIR / "data" / "tailored_resumes"
_RESUME_JSON = _BASE_DIR / "data" / "base_resume.json"

_client = None

def _anthropic() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def _cache_key(platform: str, job_id: str) -> str:
    return hashlib.sha256(f"{platform}:{job_id}".encode()).hexdigest()[:16]


def _cached_path(platform: str, job_id: str) -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / f"{_cache_key(platform, job_id)}.pdf"


def base_resume_pdf() -> Path:
    """Return the base resume PDF path (city-appropriate version)."""
    # Default to the Gurgaon version — callers can override
    return _BASE_DIR.parent / "resume" / "HarshitResume.pdf"


def tailor_resume(job_description: str, platform: str, job_id: str,
                  job_title: str = "", company: str = "") -> Path:
    """
    Return path to a tailored PDF for this job.
    Uses cache if already generated.
    Falls back to base resume PDF if tailoring fails.
    """
    cached = _cached_path(platform, job_id)
    if cached.exists():
        return cached

    base_pdf = base_resume_pdf()

    # Try to load base resume JSON if it exists
    if _RESUME_JSON.exists():
        with open(_RESUME_JSON) as f:
            base_resume = json.load(f)
    else:
        # No JSON — skip tailoring, return base PDF
        return base_pdf

    prompt = f"""You are a professional resume writer. Rewrite the following resume to better match this job description.

Rules:
- Do NOT fabricate any experience, skills, or achievements
- Do NOT change dates, company names, or job titles
- Prioritize the top 5 skills from the JD that the candidate actually has
- Reorder bullet points to surface the most relevant experience first
- Keep the same JSON structure — only change text within the existing fields
- Make it ATS-optimized for the role: {job_title} at {company}

Job Description:
{job_description[:3000]}

Base Resume JSON:
{json.dumps(base_resume, indent=2)}

Return ONLY valid JSON. No explanation, no markdown fences."""

    try:
        message = _anthropic().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        tailored_json = json.loads(message.content[0].text.strip())
        return _render_to_pdf(tailored_json, cached)
    except Exception:
        # Tailoring failed — return base PDF
        return base_pdf


def _render_to_pdf(resume_data: dict, output_path: Path) -> Path:
    """Render resume dict to PDF via HTML template using weasyprint."""
    try:
        from weasyprint import HTML
    except ImportError:
        # weasyprint not installed — return base PDF
        return base_resume_pdf()

    html = _resume_to_html(resume_data)
    HTML(string=html).write_pdf(str(output_path))
    return output_path


def _resume_to_html(data: dict) -> str:
    """Convert resume dict to a clean HTML string for PDF rendering."""
    name = data.get("name", "")
    contact = data.get("contact", {})
    summary = data.get("summary", "")
    experience = data.get("experience", [])
    skills = data.get("skills", [])
    education = data.get("education", [])

    exp_html = ""
    for job in experience:
        bullets = "".join(f"<li>{b}</li>" for b in job.get("bullets", []))
        exp_html += f"""
        <div class="job">
          <div class="job-header">
            <strong>{job.get('title','')}</strong> — {job.get('company','')}
            <span class="date">{job.get('duration','')}</span>
          </div>
          <ul>{bullets}</ul>
        </div>"""

    skills_html = " &bull; ".join(skills) if isinstance(skills, list) else skills

    edu_html = ""
    for edu in education:
        edu_html += f"<p><strong>{edu.get('degree','')}</strong>, {edu.get('institution','')} ({edu.get('year','')})</p>"

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  body {{ font-family: Arial, sans-serif; font-size: 11px; margin: 30px; color: #111; }}
  h1 {{ font-size: 20px; margin-bottom: 2px; }}
  .contact {{ color: #555; font-size: 10px; margin-bottom: 12px; }}
  h2 {{ font-size: 13px; border-bottom: 1px solid #ccc; margin-top: 14px; padding-bottom: 2px; }}
  .job {{ margin-bottom: 10px; }}
  .job-header {{ display: flex; justify-content: space-between; font-size: 11px; }}
  .date {{ color: #777; }}
  ul {{ margin: 4px 0 0 16px; padding: 0; }}
  li {{ margin-bottom: 2px; }}
</style>
</head>
<body>
  <h1>{name}</h1>
  <div class="contact">
    {contact.get('email','')} | {contact.get('phone','')} | {contact.get('linkedin','')}
  </div>

  <h2>Summary</h2>
  <p>{summary}</p>

  <h2>Experience</h2>
  {exp_html}

  <h2>Skills</h2>
  <p>{skills_html}</p>

  <h2>Education</h2>
  {edu_html}
</body>
</html>"""
