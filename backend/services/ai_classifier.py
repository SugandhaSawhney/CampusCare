"""AI triage: LLM (OpenAI-compatible) with strict Pydantic validation, deterministic fallback,
and a rule-based safety net that can only make handling MORE careful, never less."""
import json
import urllib.request
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator

import config
from services import rule_classifier as rc

DeptLit = Literal["IT Services", "Mental Health / Counselling", "Academics", "Finance / Scholarship", "Medical",
                  "Hostel", "Placement", "Disability Support", "Campus Safety"]


class TriageOutput(BaseModel):
    category: DeptLit
    subcategory: str
    primary_department: DeptLit
    secondary_departments: List[DeptLit] = Field(default_factory=list)
    priority: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    sensitivity: Literal["NORMAL", "CONFIDENTIAL", "HIGH"]
    scope: Literal["INDIVIDUAL", "CLASS", "BATCH", "DEPARTMENT", "CAMPUS"]
    required_skill: str
    confidence: float = Field(ge=0, le=1)
    human_review_required: bool
    routing_reason: str = Field(max_length=600)
    deadline_hours: Optional[float] = None
    is_emergency: bool = False

    @field_validator("subcategory")
    @classmethod
    def valid_sub(cls, v, info):
        dept = info.data.get("primary_department")
        allowed = rc.SUBCATEGORIES.get(dept, [])
        if v not in allowed:
            raise ValueError(f"subcategory '{v}' not allowed for {dept}")
        return v


SYSTEM_PROMPT = f"""You are the triage classifier for a university student-support routing system.
Classify the student's request. Rules:
- Use ONLY these departments: {json.dumps(rc.DEPARTMENTS)}. Never invent departments.
- Use ONLY these subcategories per department: {json.dumps(rc.SUBCATEGORIES)}.
- category must equal primary_department. required_skill must equal subcategory.
- Mental Health / Counselling is distinct from ordinary cases: any sign of emotional distress, anxiety, depression,
  loneliness or wanting counselling => primary_department "Mental Health / Counselling", sensitivity "HIGH".
  Any self-harm or suicide indication => subcategory "Crisis Support", priority "CRITICAL", is_emergency true.
- sensitivity: HIGH for mental health, harassment, assault; CONFIDENTIAL for personal medical or disability matters; else NORMAL.
- scope: INDIVIDUAL (one student), CLASS (a section/class), BATCH (a year/batch), DEPARTMENT, CAMPUS (everyone / nobody can ...).
  Do not assume a wider scope than the text states.
- priority reflects the wording's urgency only (LOW/MEDIUM/HIGH/CRITICAL). Physical danger or medical emergency => CRITICAL.
- deadline_hours: hours until any deadline mentioned (today=12, tomorrow=24), else null.
- secondary_departments: other departments genuinely needed to resolve it (e.g. IT Services when a portal/payment system is failing). Empty for HIGH sensitivity.
- confidence: your honest probability (0-1) that primary_department is correct. Set human_review_required true if below 0.85 or ambiguous.
- routing_reason: one or two short sentences. Do not repeat sensitive personal details.
Return STRICT JSON only with keys: category, subcategory, primary_department, secondary_departments, priority,
sensitivity, scope, required_skill, confidence, human_review_required, routing_reason, deadline_hours, is_emergency."""


def _call_llm(title: str, description: str, hint: Optional[str]) -> Optional[dict]:
    if not config.LLM_API_KEY:
        return None
    body = {
        "model": config.LLM_MODEL,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({"title": title, "description": description, "student_category_hint": hint})},
        ],
    }
    try:
        req = urllib.request.Request(
            f"{config.LLM_BASE_URL}/chat/completions", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {config.LLM_API_KEY}"},
        )
        with urllib.request.urlopen(req, timeout=config.LLM_TIMEOUT_SECONDS) as resp:
            content = json.loads(resp.read())["choices"][0]["message"]["content"]
        content = content.strip().removeprefix("```json").removesuffix("```").strip()
        return TriageOutput.model_validate(json.loads(content)).model_dump()
    except (ValidationError, Exception):
        return None  # invalid / unavailable AI output is never trusted -> fallback


def classify_request(title: str, description: str, hint: Optional[str] = None, extra_rules=None) -> dict:
    rules = rc.classify(title, description, hint, extra_rules)
    llm = _call_llm(title, description, hint)
    if not llm:
        return rules

    out = {**llm, "engine": "llm", "is_crisis": rules["is_crisis"], "batch_label": rules["batch_label"],
           "matched_signals": rules["matched_signals"], "conflict": False}
    out["category"] = out["primary_department"]
    out["required_skill"] = out["subcategory"]
    out["deadline_hours"] = out.get("deadline_hours") or rules["deadline_hours"]
    # Safety net: deterministic signals can only escalate care.
    rank = {"NORMAL": 0, "CONFIDENTIAL": 1, "HIGH": 2}
    if rank[rules["sensitivity"]] > rank[out["sensitivity"]]:
        out["sensitivity"] = rules["sensitivity"]
        out["routing_reason"] += " Sensitivity raised by safety rules."
    if rules["is_crisis"] or (rules["primary_department"] == rc.MH and out["primary_department"] != rc.MH):
        out.update(primary_department=rc.MH, category=rc.MH,
                   subcategory="Crisis Support" if rules["is_crisis"] else rules["subcategory"],
                   required_skill="Crisis Support" if rules["is_crisis"] else rules["subcategory"],
                   sensitivity="HIGH", secondary_departments=[])
        out["routing_reason"] += " Safety rule: mental-health indicators route to Counselling."
    if rules["is_emergency"]:
        out["priority"], out["is_emergency"] = "CRITICAL", True
    if out["sensitivity"] == "HIGH":
        out["secondary_departments"] = []
    # Disagreement between AI and rules on the department = conflicting classification -> human review.
    if rules["primary_department"] and rules["primary_department"] != out["primary_department"] and out["sensitivity"] != "HIGH":
        out["conflict"] = True
        out["human_review_required"] = True
        out["routing_reason"] += f" Rule-based check suggested {rules['primary_department']} instead."
    if out["confidence"] < config.CONFIDENCE_AUTO_ROUTE:
        out["human_review_required"] = True
    out["secondary_departments"] = [d for d in out["secondary_departments"] if d != out["primary_department"]][:2]
    return out
