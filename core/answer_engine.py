"""
Answer engine: generates answers for job application form fields.
Uses the Anthropic SDK for open-ended questions.
Falls back to rule-based answers for common fields.
"""

import os
import yaml
from pathlib import Path
from anthropic import Anthropic

_CONFIG_DIR = Path(__file__).parent.parent / "config"

def _load_profile() -> dict:
    with open(_CONFIG_DIR / "profile.yaml") as f:
        return yaml.safe_load(f)


PROFILE = _load_profile()

_client = None

def _anthropic() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


PROFILE_CONTEXT = (
    f"You are helping {PROFILE['name']}, a {PROFILE['experience_years']}-year backend engineer, "
    f"apply for jobs. Background: currently at {PROFILE['current_company']}, "
    f"skills: {', '.join(PROFILE['skills'][:6])}, "
    f"notice period: {PROFILE['notice_period']}, "
    f"current CTC: {PROFILE['current_ctc_lpa']} LPA, "
    f"expected CTC: {PROFILE['expected_ctc_lpa']} LPA."
)


def ask_claude(question: str, job_title: str = "", company: str = "") -> str:
    """Generate a compelling, concise answer for an open-ended question."""
    prompt = (
        f"{PROFILE_CONTEXT}\n\n"
        f"Job: {job_title} at {company}\n\n"
        f"Write a concise, confident answer (2–3 sentences max) to this job application question. "
        f"Answer in first person. Be specific about backend/systems experience. "
        f"Do NOT ask clarifying questions. Do NOT explain reasoning. "
        f"Just write the answer directly as if you are {PROFILE['name']} filling out the form.\n\n"
        f"Question: {question}"
    )
    try:
        message = _anthropic().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
    except Exception:
        pass

    # Static fallback
    return (
        f"With {PROFILE['experience_years']} years of backend engineering experience in "
        f"C++, Go, and Python, I am confident I can contribute immediately. "
        f"I have designed distributed systems and high-throughput APIs, "
        f"and I am excited to bring that expertise to this role."
    )


def answer_field(label: str, input_type: str = "text", options: list = None,
                 job_title: str = "", company: str = "") -> str:
    """Return the right answer for a form field by label."""
    label_lower = label.lower()
    options = options or []

    if any(w in label_lower for w in ["notice", "joining", "availability", "when can you join", "start"]):
        return PROFILE["notice_period"]

    if any(w in label_lower for w in ["current ctc", "current salary", "current package", "current compensation"]):
        if any(u in label_lower for u in ["lakh", "lpa", "lac"]):
            return str(PROFILE["current_ctc_lpa"])
        return str(int(PROFILE["current_ctc_lpa"] * 100_000))

    if any(w in label_lower for w in ["expected ctc", "expected salary", "expected package", "expected compensation"]):
        if any(u in label_lower for u in ["lakh", "lpa", "lac"]):
            return str(PROFILE["expected_ctc_lpa"])
        return str(int(PROFILE["expected_ctc_lpa"] * 100_000))

    if any(w in label_lower for w in ["experience", "years of exp", "total exp", "how many year"]):
        return str(PROFILE["experience_years"])

    if any(w in label_lower for w in ["relocat", "willing to move", "open to reloc"]):
        return "Yes"

    if "skill" in label_lower and options:
        matching = [o for o in options if any(
            s.lower() in o.lower() for s in PROFILE["skills"]
        )]
        return matching[0] if matching else options[0]

    if label_lower.endswith("?") and any(
        w in label_lower for w in ["are you", "do you", "have you", "can you", "will you"]
    ):
        return "Yes"

    # Open-ended — use Claude
    return ask_claude(label, job_title, company)
