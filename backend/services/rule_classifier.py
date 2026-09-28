"""Deterministic keyword classifier. Used when no LLM key is configured, when the LLM fails,
and ALWAYS as a safety net for sensitivity / crisis / scope / deadline signals.
Pure Python (no framework imports) so it can be unit tested in isolation."""
import re

DEPARTMENTS = [
    "IT Services", "Mental Health / Counselling", "Academics", "Finance / Scholarship", "Medical",
    "Hostel", "Placement", "Disability Support", "Campus Safety",
]
MH = "Mental Health / Counselling"

SUBCATEGORIES = {
    "IT Services": ["Portal Access", "Network / Wi-Fi", "Email & Accounts", "Software / LMS"],
    MH: ["Counselling Request", "Stress & Anxiety", "Crisis Support"],
    "Academics": ["Course Registration", "Exams & Grades", "Attendance", "Timetable"],
    "Finance / Scholarship": ["Fee Payment", "Scholarship", "Refund", "Fee Discrepancy"],
    "Medical": ["Urgent Medical", "Appointment", "Medical Leave"],
    "Hostel": ["Maintenance", "Room Allocation", "Mess & Food"],
    "Placement": ["Placement Registration", "Internship", "Company Drive"],
    "Disability Support": ["Accommodation Request", "Accessibility"],
    "Campus Safety": ["Harassment", "Safety Concern", "Theft & Loss"],
}
PRIORITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
SENSITIVITIES = ["NORMAL", "CONFIDENTIAL", "HIGH"]
SCOPES = ["INDIVIDUAL", "CLASS", "BATCH", "DEPARTMENT", "CAMPUS"]

# (department, subcategory, [(phrase, weight)])
KEYWORD_RULES = [
    ("Finance / Scholarship", "Fee Payment", [("fee payment", 3), ("fee", 2), ("payment", 2), ("transaction", 1.5), ("amount deducted", 2), ("challan", 2), ("tuition", 1.5), ("pay fees", 2)]),
    ("Finance / Scholarship", "Scholarship", [("scholarship", 3.5), ("stipend", 2.5), ("financial aid", 3.5), ("bursary", 3)]),
    ("Finance / Scholarship", "Refund", [("refund", 3.5), ("caution deposit", 3)]),
    ("Finance / Scholarship", "Fee Discrepancy", [("fee is wrong", 3), ("overcharged", 3), ("charged twice", 3)]),
    ("IT Services", "Portal Access", [("student portal", 2.5), ("portal", 1.5), ("login", 2), ("log in", 2), ("password", 2), ("cannot access", 1.5), ("can't access", 1.5), ("unable to access", 1.5), ("erp", 2), ("otp", 1.5)]),
    ("IT Services", "Network / Wi-Fi", [("wifi", 3), ("wi-fi", 3), ("internet", 2.5), ("network", 1.5)]),
    ("IT Services", "Email & Accounts", [("email account", 3), ("college email", 3), ("outlook", 2)]),
    ("IT Services", "Software / LMS", [("lms", 3), ("moodle", 3), ("software", 1.5), ("laptop", 1.5)]),
    ("Academics", "Course Registration", [("course registration", 3), ("register for", 2), ("registration", 1), ("enrol", 2), ("credits", 1.5), ("elective", 2), ("add/drop", 2.5)]),
    ("Academics", "Exams & Grades", [("exam", 2), ("grade", 2), ("marks", 2), ("result", 1.5), ("revaluation", 3), ("transcript", 2.5)]),
    ("Academics", "Attendance", [("attendance", 3.5)]),
    ("Academics", "Timetable", [("timetable", 3.5), ("class schedule", 2.5), ("clash", 1.5)]),
    (MH, "Counselling Request", [("counsell", 3.5), ("counselor", 3.5), ("therapist", 3.5), ("talk to someone", 3), ("mental health", 3.5), ("wellbeing", 2)]),
    (MH, "Stress & Anxiety", [("anxiety", 3.5), ("anxious", 3.5), ("stressed", 2.5), ("stress", 2), ("overwhelmed", 3.5), ("depress", 3.5), ("panic", 3), ("lonely", 3), ("can't sleep", 2), ("cannot sleep", 2), ("hopeless", 4), ("can't cope", 3.5), ("cannot cope", 3.5), ("burnout", 3), ("burnt out", 3), ("crying", 2.5), ("isolated", 2.5)]),
    (MH, "Crisis Support", [("suicid", 6), ("kill myself", 6), ("end my life", 6), ("self-harm", 6), ("self harm", 6), ("hurt myself", 6), ("want to die", 6), ("no reason to live", 6)]),
    ("Medical", "Urgent Medical", [("chest pain", 6), ("bleeding", 4), ("unconscious", 6), ("can't breathe", 6), ("cannot breathe", 6), ("fainted", 4.5), ("injury", 3), ("injured", 3), ("fever", 2.5), ("ambulance", 6), ("allergic reaction", 4), ("fracture", 4)]),
    ("Medical", "Appointment", [("doctor", 2.5), ("medical", 2), ("clinic", 2.5), ("health centre", 3), ("health center", 3), ("medicine", 2), ("sick", 2), ("appointment", 1)]),
    ("Medical", "Medical Leave", [("medical leave", 4), ("medical certificate", 3.5)]),
    ("Hostel", "Maintenance", [("hostel", 2), ("leak", 2.5), ("plumbing", 3), ("electricity", 2), ("ceiling fan", 2.5), ("tap", 1.5), ("repair", 1.5), ("maintenance", 2), ("broken", 1), ("water supply", 2.5)]),
    ("Hostel", "Room Allocation", [("room allocation", 3.5), ("roommate", 2.5), ("room change", 3.5), ("warden", 2)]),
    ("Hostel", "Mess & Food", [("mess", 2.5), ("food quality", 3)]),
    ("Placement", "Placement Registration", [("placement", 3.5), ("recruit", 2), ("resume", 2), ("tpo", 3), ("job offer", 3)]),
    ("Placement", "Internship", [("internship", 3)]),
    ("Placement", "Company Drive", [("company drive", 3.5), ("campus drive", 3.5), ("aptitude test", 2)]),
    ("Disability Support", "Accommodation Request", [("disability", 4.5), ("extra time", 2.5), ("scribe", 3.5), ("dyslexia", 4.5), ("adhd", 3.5), ("hearing impair", 4.5), ("visually impaired", 4.5), ("accommodation", 1.5)]),
    ("Disability Support", "Accessibility", [("wheelchair", 4.5), ("accessib", 3.5), ("ramp", 2.5), ("lift not working", 2.5)]),
    ("Campus Safety", "Harassment", [("harass", 5), ("stalk", 5), ("assault", 6), ("bully", 3.5), ("ragging", 6), ("threaten", 4), ("followed me", 4)]),
    ("Campus Safety", "Safety Concern", [("unsafe", 3.5), ("safety", 2.5), ("security guard", 2.5), ("streetlight", 2), ("fight", 3), ("fire", 3), ("intruder", 4)]),
    ("Campus Safety", "Theft & Loss", [("stolen", 3.5), ("theft", 3.5), ("lost my", 1.5)]),
]

EMERGENCY_TERMS = ["chest pain", "unconscious", "can't breathe", "cannot breathe", "ambulance", "bleeding", "assault",
                   "fire", "intruder", "suicid", "kill myself", "end my life", "self-harm", "self harm", "hurt myself", "want to die",
                   "no reason to live"]
CRISIS_TERMS = ["suicid", "kill myself", "end my life", "self-harm", "self harm", "hurt myself", "want to die", "no reason to live"]
HIGH_SENSITIVITY_SUBCATS = {"Harassment"}
CONFIDENTIAL_DEPTS = {"Medical", "Disability Support"}
LOW_URGENCY_TERMS = ["suggestion", "feedback", "just wanted to know", "enquiry", "inquiry", "whenever possible", "no rush"]
FAILURE_TERMS = ["fail", "error", "not working", "not loading", "down", "crash", "stuck", "timeout", "timed out"]
TECH_SURFACE_TERMS = ["payment", "portal", "website", "online", "gateway", "app", "system", "server", "payment page"]


def _norm(text: str) -> str:
    return " " + re.sub(r"\s+", " ", (text or "").lower()) + " "


def _hits(text, phrases):
    return [p for p in phrases if p in text]


def detect_scope(text: str) -> str:
    t = _norm(text)
    if re.search(r"(everyone|all students|whole|entire|every student)[\w\s]{0,20}(department|dept)", t) or "our department" in t:
        return "DEPARTMENT"
    if re.search(r"\b(nobody|no one|no-one) (can|is able|could)\b", t) or re.search(r"(entire|whole|across the) (campus|university|college)", t) or "all students" in t:
        return "CAMPUS"
    if re.search(r"\bbatch\b", t) or re.search(r"(many|several|lots of|most) (students|of us)", t) or re.search(r"(all|entire) (of )?(our )?(year|20\d\d)", t):
        return "BATCH"
    if re.search(r"\b(section|class|classmates|our group|whole class)\b", t):
        return "CLASS"
    if re.search(r"\b(we|our|us)\b", t) and re.search(r"(everyone|all of us|we all|many)", t):
        return "CLASS"
    return "INDIVIDUAL"


def detect_batch(text: str):
    m = re.search(r"\b(cse|ece|eee|me|civil|it|mba)\s*[- ]?\s*(20\d\d)\b", (text or "").lower())
    return f"{m.group(1).upper()} {m.group(2)}" if m else None


def detect_deadline_hours(text: str):
    t = _norm(text)
    if re.search(r"\b(today|tonight|in a few hours|within hours|by evening)\b", t):
        return 12.0
    m = re.search(r"in (\d+) hours", t)
    if m:
        return float(m.group(1))
    if "tomorrow" in t:
        return 24.0
    m = re.search(r"in (\d+) days", t)
    if m:
        return float(m.group(1)) * 24
    if re.search(r"\b(by|before|due|until|ends?) (this week|friday|monday|the weekend)\b", t):
        return 72.0
    if re.search(r"\b(deadline|due date|last date)\b", t):
        return 96.0
    return None


def classify(title: str, description: str, category_hint: str = None, extra_rules=None) -> dict:
    """Return a triage dict with the same shape as the LLM output."""
    text = _norm(f"{title}. {description}")
    rules = list(KEYWORD_RULES)
    for r in extra_rules or []:  # admin-configured rules: (department, subcategory, keyword, weight)
        rules.append((r[0], r[1], [(r[2].lower(), r[3])]))

    sub_scores, dept_scores, matched = {}, {}, {}
    for dept, sub, phrases in rules:
        s = 0.0
        for phrase, w in phrases:
            if phrase in text:
                s += w
                matched.setdefault(dept, []).append(phrase)
        if s:
            sub_scores[(dept, sub)] = sub_scores.get((dept, sub), 0) + s
            dept_scores[dept] = dept_scores.get(dept, 0) + s

    if category_hint and category_hint in dept_scores:
        dept_scores[category_hint] += 1.0  # the student's optional hint nudges, never decides

    scope = detect_scope(text)
    deadline = detect_deadline_hours(text)
    batch = detect_batch(text)
    emergency = bool(_hits(text, EMERGENCY_TERMS))
    crisis = bool(_hits(text, CRISIS_TERMS))

    if not dept_scores:
        return {
            "category": "Unclassified", "subcategory": "Unclassified", "primary_department": None,
            "secondary_departments": [], "priority": "MEDIUM", "sensitivity": "NORMAL", "scope": scope,
            "required_skill": None, "confidence": 0.43, "human_review_required": True,
            "routing_reason": "No department-specific signals were found in the request, so it needs a human to read it.",
            "deadline_hours": deadline, "is_emergency": False, "is_crisis": False, "batch_label": batch,
            "matched_signals": {}, "engine": "rules", "conflict": False,
        }

    ranked = sorted(dept_scores.items(), key=lambda kv: -kv[1])
    mh_score = dept_scores.get(MH, 0)
    # Safety-first: any meaningful mental-health signal routes to counselling regardless of other topics.
    primary, s1 = (MH, mh_score) if mh_score >= 2 else ranked[0]
    others = [(d, s) for d, s in ranked if d != primary]
    s2 = others[0][1] if others else 0
    ratio = s2 / s1 if s1 else 0

    subs = sorted([(sub, s) for (d, sub), s in sub_scores.items() if d == primary], key=lambda kv: -kv[1])
    subcategory = "Crisis Support" if (primary == MH and crisis) else subs[0][0]

    # Sensitivity
    if primary == MH or subcategory in HIGH_SENSITIVITY_SUBCATS or crisis:
        sensitivity = "HIGH"
    elif primary in CONFIDENTIAL_DEPTS:
        sensitivity = "CONFIDENTIAL"
    else:
        sensitivity = "NORMAL"

    # Secondary departments: strong co-signals or cross-cutting technical failure. Never for HIGH sensitivity.
    secondary = []
    if sensitivity != "HIGH":
        for d, s in others:
            if s / s1 >= 0.6 and d != MH:
                secondary.append(d)
        if primary != "IT Services" and _hits(text, FAILURE_TERMS) and _hits(text, TECH_SURFACE_TERMS) and "IT Services" not in secondary:
            secondary.append("IT Services")
        if primary != "Finance / Scholarship" and re.search(r"\b(fee|fees|payment)\b", text) and "Finance / Scholarship" not in secondary:
            secondary.append("Finance / Scholarship")
    secondary = secondary[:2]

    # Confidence (deterministic heuristic, clearly labelled as such in the UI)
    conf = min(0.96, 0.5 + 0.09 * s1)
    conflict = primary != MH and ratio >= 0.85
    if ratio > 0.6 and primary != MH:
        conf *= 1 - (ratio - 0.6) * 0.8
    conf = round(max(0.3, conf), 2)

    # Base urgency from wording only (impact is applied later by the routing engine)
    if emergency:
        priority = "CRITICAL"
    elif _hits(text, LOW_URGENCY_TERMS):
        priority = "LOW"
    else:
        priority = "MEDIUM"

    review = conf < 0.85 or conflict
    reason_bits = [f"signals for {primary} ({', '.join(matched.get(primary, [])[:4])})"]
    if primary == MH and ranked[0][0] != MH:
        reason_bits.append(f"mental-health indicators take precedence over {ranked[0][0]} (safety-first rule)")
    if secondary:
        reason_bits.append(f"supporting: {', '.join(secondary)}")
    if conflict:
        reason_bits.append(f"conflicting signals with {others[0][0]}")
    return {
        "category": primary, "subcategory": subcategory, "primary_department": primary,
        "secondary_departments": secondary, "priority": priority, "sensitivity": sensitivity, "scope": scope,
        "required_skill": subcategory, "confidence": conf, "human_review_required": review,
        "routing_reason": "Keyword analysis found " + "; ".join(reason_bits) + ".",
        "deadline_hours": deadline, "is_emergency": emergency, "is_crisis": crisis, "batch_label": batch,
        "matched_signals": matched, "engine": "rules", "conflict": conflict,
    }
