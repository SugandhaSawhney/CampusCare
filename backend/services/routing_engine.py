"""CampusCare routing engine: triage -> sensitivity -> scope -> clustering -> impact priority ->
department selection -> workload-aware assignment -> SLA -> escalation.
All decisions are deterministic given the classifier output and are explained in plain language."""
from collections import Counter
from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

import config
from database import utcnow
from models import (AuditLog, CampusSupportRequest, Cluster, ClusterMember, Department, Escalation, Notification,
                    RequestDepartment, Role, RoutingRule, SLARecord, SLARule, StaffProfile, User)
from services import ai_classifier
from services.similarity import fallback_similarity, cosine, get_embedding

ACTIVE_STATUSES = {"ASSIGNED", "IN_PROGRESS", "WAITING_FOR_STUDENT", "ESCALATED", "REOPENED"}
SLA_CLOCK_STATUSES = {"ASSIGNED", "IN_PROGRESS", "ESCALATED", "REOPENED", "AWAITING_HUMAN_REVIEW"}
OPEN_STATUSES = ACTIVE_STATUSES | {"NEW", "TRIAGING", "AWAITING_HUMAN_REVIEW"}
P = config.PRIORITIES


# ------------------------------------------------------------------ helpers
def audit(db, req, actor, action, old=None, new=None, reason=None):
    db.add(AuditLog(request_id=req.id if req else None, actor_id=actor.id if actor else None, action=action,
                    old_value=None if old is None else str(old), new_value=None if new is None else str(new), reason=reason))


def notify(db, user_id, req, message, kind="INFO"):
    if user_id:
        db.add(Notification(user_id=user_id, request_id=req.id if req else None, message=message[:400], kind=kind))


def dept_by_name(db, name) -> Optional[Department]:
    return db.query(Department).filter(Department.name == name).first() if name else None


def users_with_role(db, role):
    return db.query(User).join(Role, User.role_id == Role.id).filter(Role.name == role, User.is_active.is_(True)).all()


def pct(a, b):
    return round(100.0 * a / b, 1) if b else None


# ------------------------------------------------------------------ 1. classification
def classify_request(db: Session, req: CampusSupportRequest) -> dict:
    extra = [(r.department.name, r.subcategory, r.keyword, r.weight)
             for r in db.query(RoutingRule).filter(RoutingRule.active.is_(True)).all()]
    return ai_classifier.classify_request(req.title, req.description, req.category_hint, extra)


def determine_sensitivity(result: dict, privacy_mode: str) -> str:
    s = result["sensitivity"]
    if privacy_mode in ("CONFIDENTIAL", "ANONYMOUS") and s == "NORMAL":
        s = "CONFIDENTIAL"  # student-chosen privacy can only raise protection
    return s


def determine_scope(result: dict) -> str:
    return result["scope"] if result["scope"] in ("INDIVIDUAL", "CLASS", "BATCH", "DEPARTMENT", "CAMPUS") else "INDIVIDUAL"


def is_clusterable(req) -> bool:
    return req.sensitivity_level == "NORMAL" and req.privacy_mode == "NORMAL" and not req.anonymous \
        and req.category not in (None, "Unclassified", "Mental Health / Counselling")


# ------------------------------------------------------------------ 2. impact
def population_for(scope, batch_label):
    if scope in ("BATCH", "CLASS") and batch_label:
        return config.BATCH_SIZES.get(batch_label, config.DEFAULT_BATCH_SIZE) if scope == "BATCH" else config.CLASS_SIZE
    return {"CLASS": config.CLASS_SIZE, "DEPARTMENT": config.DEPARTMENT_SIZE, "CAMPUS": config.CAMPUS_SIZE,
            "BATCH": config.DEFAULT_BATCH_SIZE}.get(scope)


def cluster_impact(db, cluster: Cluster) -> dict:
    reqs = [m.request for m in cluster.members]
    students = {r.student_id for r in reqs}
    batches = Counter(r.student.batch_label for r in reqs if r.student and r.student.batch_label)
    batch_label, pop = cluster.batch_label, cluster.population_size
    if batches:
        top, n = batches.most_common(1)[0]
        if n / max(1, len(reqs)) >= 0.6:
            batch_label = top
            pop = config.BATCH_SIZES.get(top, config.DEFAULT_BATCH_SIZE)
    wide = max((r.scope for r in reqs), key=lambda s: ["INDIVIDUAL", "CLASS", "BATCH", "DEPARTMENT", "CAMPUS"].index(s), default="INDIVIDUAL")
    if wide in ("DEPARTMENT", "CAMPUS"):
        pop = population_for(wide, None)
    cluster.batch_label, cluster.population_size, cluster.scope = batch_label, pop, wide
    open_n = sum(1 for r in reqs if r.status in OPEN_STATUSES)
    return {"affected_count": len(students), "request_count": len(reqs), "open_count": open_n,
            "population": pop, "affected_pct": pct(len(students), pop) if pop else None, "batch_label": batch_label, "scope": wide}


def calculate_priority(base, deadline_hours, affected, affected_pct, scope, is_emergency):
    if is_emergency:
        return "CRITICAL", "CRITICAL because the request describes a possible emergency."
    idx, reasons = P.index(base), []
    if deadline_hours is not None and deadline_hours <= config.DEADLINE_BUMP_HOURS:
        idx += 1
        when = "today" if deadline_hours <= 12 else "tomorrow" if deadline_hours <= 24 else f"within {int(deadline_hours)}h"
        reasons.append(f"the deadline is {when}")
    if affected >= config.IMPACT_BUMP_AFFECTED_COUNT or (affected_pct or 0) >= config.IMPACT_BUMP_AFFECTED_PCT:
        idx += 1
        reasons.append(f"{affected} students are affected" + (f" ({affected_pct}% of the cohort)" if affected_pct else ""))
    if scope == "CAMPUS" and idx < P.index(config.CAMPUS_WIDE_MIN_PRIORITY):
        idx = P.index(config.CAMPUS_WIDE_MIN_PRIORITY)
        reasons.append("the issue is campus-wide")
    cap = max(P.index(base), P.index(config.MAX_IMPACT_PRIORITY))
    final = P[min(idx, cap)]
    if final != base:
        return final, f"Priority increased from {base} to {final} because " + " and ".join(reasons) + "."
    if reasons:
        return final, f"Priority {final}; impact noted ({' and '.join(reasons)}) but already at the configured ceiling for impact rules."
    return final, f"Priority {final} based on the request wording; no deadline or impact modifiers applied."


# ------------------------------------------------------------------ 3. clustering (non-sensitive only)
def find_similar_cases(db, req, limit=50):
    since = utcnow() - timedelta(days=config.CLUSTER_WINDOW_DAYS)
    cands = (db.query(CampusSupportRequest)
             .filter(CampusSupportRequest.id != req.id, CampusSupportRequest.created_at >= since,
                     CampusSupportRequest.sensitivity_level == "NORMAL", CampusSupportRequest.privacy_mode == "NORMAL",
                     CampusSupportRequest.primary_department_id == req.primary_department_id)
             .order_by(CampusSupportRequest.created_at.desc()).limit(limit).all())
    use_emb = bool(req.embedding)
    text = f"{req.title}. {req.description}"
    out = []
    for c in cands:
        if use_emb and c.embedding:
            s, method = cosine(req.embedding, c.embedding), "embedding"
            thr = config.SIMILARITY_THRESHOLD_EMBEDDING
        else:
            s = fallback_similarity(text, req.category, req.subcategory, f"{c.title}. {c.description}", c.category, c.subcategory)
            method, thr = "keyword", config.SIMILARITY_THRESHOLD_FALLBACK
        if s >= thr:
            out.append((c, round(s, 3), method))
    return sorted(out, key=lambda x: -x[1])


def create_or_attach_cluster(db, req):
    matches = find_similar_cases(db, req)
    target, sim, method = None, 1.0, "seed"
    for c, s, m in matches:
        if c.cluster_id:
            target, sim, method = db.get(Cluster, c.cluster_id), s, m
            break
    if not target:
        label = {"Fee Payment": "Fee Payment Failure", "Portal Access": "Student Portal Access Failure",
                 "Course Registration": "Course Registration Blocked"}.get(req.subcategory, f"{req.subcategory} Issues")
        target = Cluster(label=label, category=req.category, subcategory=req.subcategory,
                         primary_department_id=req.primary_department_id, priority=req.priority, scope=req.scope)
        db.add(target)
        db.flush()
        for c, s, m in matches:  # pull in unclustered similar requests
            if not c.cluster_id:
                db.add(ClusterMember(cluster_id=target.id, request_id=c.id, similarity=s, method=m))
                c.cluster_id = target.id
    db.add(ClusterMember(cluster_id=target.id, request_id=req.id, similarity=sim, method=method))
    req.cluster_id = target.id
    db.flush()
    db.refresh(target)
    return target, len(matches), method


def remove_from_cluster(db, req, actor=None, reason="Sensitivity changed"):
    if not req.cluster_id:
        return
    cid = req.cluster_id
    db.query(ClusterMember).filter(ClusterMember.request_id == req.id).delete()
    req.cluster_id = None
    req.affected_count = 1
    audit(db, req, actor, "CLUSTER_REMOVED", cid, None, reason)
    db.flush()


def recompute_cluster(db, cluster, actor=None):
    """Re-apply impact-aware priority to every OPEN member (never lowers priority automatically)."""
    impact = cluster_impact(db, cluster)
    top = "LOW"
    for m in cluster.members:
        r = m.request
        r.affected_count = impact["affected_count"]
        if r.status not in OPEN_STATUSES:
            continue
        base = (r.last_ai_analysis or {}).get("priority", r.priority)
        new, why = calculate_priority(base, r.deadline_hours, impact["affected_count"], impact["affected_pct"], r.scope,
                                      (r.last_ai_analysis or {}).get("is_emergency", False))
        if P.index(new) > P.index(r.priority):
            audit(db, r, actor, "PRIORITY_RECALCULATED", r.priority, new, why)
            r.priority, r.priority_reason = new, why
            start_sla(db, r, keep_start=True)
        top = max(top, r.priority, key=P.index)
    cluster.priority = top
    return impact


# ------------------------------------------------------------------ 4. departments
def select_primary_department(db, result):
    dept = dept_by_name(db, result.get("primary_department"))
    if not dept:
        return None, "No department matched the request."
    skill = result.get("required_skill")
    if skill and dept.capabilities and skill not in dept.capabilities:
        alt = next((d for d in db.query(Department).all() if skill in (d.capabilities or [])), None)
        if alt:
            return alt, f"{dept.name} lacks capability '{skill}', so {alt.name} was selected."
        return dept, f"No department lists capability '{skill}'; kept {dept.name}."
    return dept, None


def select_secondary_departments(db, result, primary):
    out = []
    for name in result.get("secondary_departments", []):
        d = dept_by_name(db, name)
        if d and primary and d.id != primary.id and not d.is_sensitive:
            out.append(d)
    return out


def set_departments(db, req, primary, secondaries, reason=None):
    req.departments.clear()
    db.flush()
    if primary:
        req.departments.append(RequestDepartment(department_id=primary.id, role="PRIMARY", reason=reason))
        req.primary_department_id = primary.id
        req.assigned_team_id = primary.id
        hist = list(req.routing_history or [])
        if not hist or hist[-1] != primary.id:
            hist.append(primary.id)
        req.routing_history = hist
    else:
        req.primary_department_id = None
        req.assigned_team_id = None
    for d in secondaries:
        req.departments.append(RequestDepartment(department_id=d.id, role="SUPPORTING", reason="Supporting department"))
    db.flush()


# ------------------------------------------------------------------ 5. workload-aware assignment
def active_case_count(db, user_id):
    return db.query(CampusSupportRequest).filter(CampusSupportRequest.assigned_staff_id == user_id,
                                                 CampusSupportRequest.status.in_(list(ACTIVE_STATUSES))).count()


def calculate_assignment_score(profile: StaffProfile, dept_id, skill, active):
    skill_match = bool(skill and skill in (profile.skills or []))
    cap = max(1, profile.max_active_cases)
    parts = {
        "skill_match": config.W_SKILL if skill_match else 0,
        "department_match": config.W_DEPARTMENT if profile.department_id == dept_id else 0,
        "availability": config.W_AVAILABILITY if profile.available else 0,
        "workload": round(config.W_WORKLOAD * max(0.0, 1 - active / cap), 1),
    }
    return round(sum(parts.values()), 1), parts, skill_match


def find_eligible_staff(db, dept, skill, level=1):
    profiles = (db.query(StaffProfile).join(User, StaffProfile.user_id == User.id).join(Role, User.role_id == Role.id)
                .filter(StaffProfile.department_id == dept.id, StaffProfile.hierarchy_level == level,
                        Role.name == "DEPARTMENT_STAFF", User.is_active.is_(True)).all())
    rows = []
    for p in profiles:
        active = active_case_count(db, p.user_id)
        score, parts, skill_match = calculate_assignment_score(p, dept.id, skill, active)
        eligible = p.available and active < p.max_active_cases
        rows.append({"user_id": p.user_id, "name": p.user.full_name, "active_cases": active, "max": p.max_active_cases,
                     "available": p.available, "skill_match": skill_match, "score": score, "parts": parts, "eligible": eligible})
    rows.sort(key=lambda r: (not r["eligible"], -r["score"], r["active_cases"], r["user_id"]))
    return rows


def assign_request(db, req, actor=None, staff_id=None, reason=None):
    dept = req.primary_department
    if not dept:
        return None
    if staff_id:
        prof = db.query(StaffProfile).filter_by(user_id=staff_id).first()
        if not prof or prof.department_id != dept.id:
            raise ValueError("Selected staff member does not belong to the owning department")
        chosen = {"user_id": staff_id, "name": prof.user.full_name}
        explanation = {"mode": "manual", "staff": prof.user.full_name,
                       "reasons": [f"Manually assigned by {actor.full_name if actor else 'system'}"] + ([reason] if reason else []), "candidates": []}
    else:
        rows = find_eligible_staff(db, dept, req.required_skill)
        elig = [r for r in rows if r["eligible"]]
        if not elig:  # fall back to department lead
            leads = find_eligible_staff(db, dept, req.required_skill, level=2) if dept.lead_id else []
            if not dept.lead_id:
                return None
            lead = db.get(User, dept.lead_id)
            chosen = {"user_id": lead.id, "name": lead.full_name}
            explanation = {"mode": "auto", "staff": lead.full_name, "score": None,
                           "reasons": ["No available level-1 staff with capacity", "Assigned to Department Lead"], "candidates": rows + leads}
        else:
            best = elig[0]
            chosen = best
            reasons = []
            if best["skill_match"]:
                reasons.append(f"Required skill matched ({req.required_skill})")
            else:
                reasons.append(f"No eligible staff has skill '{req.required_skill}'; best available generalist chosen")
            reasons += ["Department matched", "Staff available"]
            if len(elig) > 1 and best["active_cases"] <= min(r["active_cases"] for r in elig if r["skill_match"] == best["skill_match"]):
                reasons.append(f"Lowest active workload among eligible staff ({best['active_cases']} active cases)")
            else:
                reasons.append(f"Active workload: {best['active_cases']} cases")
            explanation = {"mode": "auto", "staff": best["name"], "score": best["score"], "reasons": reasons, "candidates": rows,
                           "weights": {"skill": config.W_SKILL, "department": config.W_DEPARTMENT,
                                       "availability": config.W_AVAILABILITY, "workload": config.W_WORKLOAD}}
    old = req.assigned_staff_id
    req.assigned_staff_id = chosen["user_id"]
    req.assignment_reason = explanation
    if req.status in ("NEW", "TRIAGING", "AWAITING_HUMAN_REVIEW", "REOPENED") or not old:
        req.status = "ASSIGNED"
    req.escalation_level = max(req.escalation_level or 0, 1)
    req.routed_at = req.routed_at or utcnow()
    audit(db, req, actor, "ASSIGNED" if not old else "REASSIGNED_STAFF", old, chosen["user_id"], "; ".join(explanation["reasons"]))
    notify(db, chosen["user_id"], req, f"{req.request_number} assigned to you: {req.title if not req.anonymous else 'Anonymous request'}", "ASSIGNMENT")
    db.flush()
    return explanation


# ------------------------------------------------------------------ 6. SLA
def sla_rule(db, priority):
    r = db.query(SLARule).filter_by(priority=priority).first()
    if r:
        return r.resolution_hours, r.escalation_window_hours, r.max_escalation_level
    return config.DEFAULT_SLA_RULES[priority]


def start_sla(db, req, keep_start=False):
    hours, _, _ = sla_rule(db, req.priority)
    start = req.created_at or utcnow()
    req.sla_due_at = start + timedelta(hours=hours)
    db.add(SLARecord(request_id=req.id, priority=req.priority, started_at=start, due_at=req.sla_due_at,
                     level=req.escalation_level or 1))


def sla_state(req, now=None):
    now = now or utcnow()
    if req.status in ("RESOLVED", "CLOSED"):
        met = req.resolved_at and req.sla_due_at and req.resolved_at <= req.sla_due_at
        return ("MET" if met else "RESOLVED_LATE"), None
    if req.status == "WAITING_FOR_STUDENT" or not req.sla_due_at:
        return "PAUSED" if req.status == "WAITING_FOR_STUDENT" else "NONE", None
    remaining = (req.sla_due_at - now).total_seconds()
    window = max(1.0, (req.sla_due_at - (req.escalated_at or req.created_at)).total_seconds())
    if remaining < 0:
        return "BREACHED", remaining
    if remaining < window * config.SLA_APPROACHING_FRACTION:
        return "APPROACHING", remaining
    return "WITHIN", remaining


def escalation_target(db, req, level):
    dept = req.primary_department
    if level == 2 and dept and dept.lead_id:
        return db.get(User, dept.lead_id)
    if level == 3 and dept and dept.dean_id:
        return db.get(User, dept.dean_id)
    if level >= 3:
        central = (db.query(User).join(StaffProfile, StaffProfile.user_id == User.id).join(Role, User.role_id == Role.id)
                   .filter(Role.name == "DEAN", StaffProfile.hierarchy_level == 4).first())
        return central
    return None


def escalate_request(db, req, trigger, reason, actor=None, to_level=None):
    _, window, max_level = sla_rule(db, req.priority)
    cur = req.escalation_level or 1
    nxt = to_level or cur + 1
    dept = req.primary_department
    if trigger == "SLA_BREACH" and req.priority == "CRITICAL" and dept and dept.is_emergency:
        nxt = max(nxt, 3)  # emergency path: skip straight to Dean level
        reason += " (emergency escalation path)"
    if trigger == "SLA_BREACH" and nxt > max_level:
        return None
    nxt = min(nxt, 4)
    if nxt <= cur and trigger != "MANUAL":
        return None
    target = escalation_target(db, req, nxt)
    for e in db.query(Escalation).filter_by(request_id=req.id, closed=False).all():
        e.closed, e.closed_at, e.decision_note = True, utcnow(), e.decision_note or f"Superseded by level {nxt}"
    esc = Escalation(request_id=req.id, from_level=cur, to_level=nxt, reason=reason, trigger=trigger,
                     target_user_id=target.id if target else None, actor_id=actor.id if actor else None)
    db.add(esc)
    old_status = req.status
    req.escalation_level, req.escalated_at, req.status = nxt, utcnow(), "ESCALATED"
    req.sla_due_at = utcnow() + timedelta(hours=window)
    db.add(SLARecord(request_id=req.id, priority=req.priority, started_at=utcnow(), due_at=req.sla_due_at, level=nxt))
    audit(db, req, actor, "ESCALATED", f"L{cur}/{old_status}", f"L{nxt}/ESCALATED", reason)
    label = config.ESCALATION_LEVELS[nxt]
    if target:
        notify(db, target.id, req, f"{req.request_number} escalated to you ({label}): {reason}", "ESCALATION")
    notify(db, req.assigned_staff_id, req, f"{req.request_number} escalated to {label}: {reason}", "ESCALATION")
    db.flush()
    return esc


def check_sla(db, now=None):
    now = now or utcnow()
    escalated = []
    rows = db.query(CampusSupportRequest).filter(CampusSupportRequest.status.in_(list(SLA_CLOCK_STATUSES - {"AWAITING_HUMAN_REVIEW"})),
                                                 CampusSupportRequest.sla_due_at < now).all()
    for r in rows:
        rec = db.query(SLARecord).filter_by(request_id=r.id).order_by(SLARecord.id.desc()).first()
        if rec and rec.status != "BREACHED":
            rec.status, rec.breached_at = "BREACHED", now
        esc = escalate_request(db, r, "SLA_BREACH", f"SLA breached ({r.priority} priority, due {r.sla_due_at:%d %b %H:%M} UTC)")
        if esc:
            escalated.append(r.request_number)
    # Human-review queue breaches alert all triage agents (no hierarchy jump without an owner)
    for r in db.query(CampusSupportRequest).filter(CampusSupportRequest.status == "AWAITING_HUMAN_REVIEW",
                                                  CampusSupportRequest.sla_due_at < now).all():
        if not db.query(Notification).filter_by(request_id=r.id, kind="TRIAGE_SLA").first():
            for u in users_with_role(db, "TRIAGE_AGENT"):
                notify(db, u.id, r, f"{r.request_number} has breached SLA while awaiting human triage", "TRIAGE_SLA")
    db.commit()
    return escalated


# ------------------------------------------------------------------ 7. orchestration
def routing_mismatch(req) -> bool:
    h = req.routing_history or []
    return any(h[i] == h[i + 2] and h[i] != h[i + 1] for i in range(len(h) - 2))


def build_explanation(req, dept, secondaries, n_similar, impact, mode):
    parts = []
    if mode == "auto" and dept:
        parts.append(f"Routed to {dept.name} because the issue concerns {req.subcategory.lower()}.")
    elif mode == "sensitive":
        parts.append(f"Routed directly to {dept.name} under restricted access; sensitive requests are never clustered or sent to general triage.")
    elif mode == "review_suggest":
        parts.append(f"AI confidence is {round(req.ai_confidence * 100)}%, so the suggestion ({dept.name}) must be confirmed by Human Triage before assignment.")
    else:
        parts.append(f"AI confidence is {round((req.ai_confidence or 0) * 100)}%, so the request was sent to Human Triage rather than being automatically assigned.")
    if secondaries:
        parts.append(f"Supporting: {', '.join(d.name for d in secondaries)} (primary owner remains {dept.name}).")
    if impact:
        extra = f" ({impact['affected_count']}/{impact['population']} of {impact['batch_label'] or impact['scope'].lower()}, {impact['affected_pct']}%)" if impact.get("population") else ""
        parts.append(f"{n_similar} similar non-sensitive request(s) found; cluster now affects {impact['affected_count']} student(s){extra}.")
    if req.priority_reason:
        parts.append(req.priority_reason)
    return " ".join(parts)


def student_summary(req, dept, mode, crisis):
    if crisis:
        return config.CRISIS_MESSAGE
    if mode in ("auto", "sensitive"):
        who = "the counselling team (confidential)" if dept and dept.is_sensitive else dept.name
        return f"Your request has been routed to {who}. Priority: {req.priority.title()}."
    return "Your request has been sent to a support specialist for verification before it is assigned."


def triage_and_route(db, req, actor=None):
    req.status = "TRIAGING"
    result = classify_request(db, req)
    if req.last_ai_analysis is None and config.LLM_API_KEY:
        req.embedding = get_embedding(f"{req.title}. {req.description}", config.LLM_API_KEY, config.LLM_BASE_URL,
                                      config.EMBEDDING_MODEL, config.LLM_TIMEOUT_SECONDS)
    req.last_ai_analysis = result
    req.ai_engine = result["engine"]
    req.category, req.subcategory = result["category"], result["subcategory"]
    req.required_skill = result["required_skill"]
    req.ai_confidence = result["confidence"]
    req.sensitivity_level = determine_sensitivity(result, req.privacy_mode)
    req.scope = determine_scope(result)
    req.deadline_hours = result.get("deadline_hours")
    req.batch_label = result.get("batch_label") or (req.student.batch_label if req.scope in ("CLASS", "BATCH") else None)
    audit(db, req, None, "AI_TRIAGE", None,
          f"{req.category}/{req.subcategory} conf={req.ai_confidence} sens={req.sensitivity_level} scope={req.scope}",
          f"engine={result['engine']}")

    dept, dept_note = select_primary_department(db, result)
    sensitive = req.sensitivity_level == "HIGH"
    conf = req.ai_confidence or 0
    if sensitive and dept:
        mode = "sensitive"
    elif dept and conf >= config.CONFIDENCE_AUTO_ROUTE and not result.get("conflict") and not result.get("human_review_required"):
        mode = "auto"
    elif dept and conf >= config.CONFIDENCE_SUGGEST:
        mode = "review_suggest"
    else:
        mode = "review"

    secondaries = select_secondary_departments(db, result, dept) if (dept and not sensitive and mode != "review") else []
    set_departments(db, req, dept if mode != "review" else None, secondaries, result.get("routing_reason"))
    req.primary_department = dept if mode != "review" else None

    impact, n_similar = None, 0
    if mode in ("auto", "review_suggest") and is_clusterable(req):
        cluster, n_similar, method = create_or_attach_cluster(db, req)
        impact = cluster_impact(db, cluster)
        req.affected_count = impact["affected_count"]
        audit(db, req, None, "CLUSTERED", None, f"cluster#{cluster.id} {cluster.label}", f"{n_similar} similar ({method})")
    else:
        req.affected_count = 1
        if sensitive:
            audit(db, req, None, "CLUSTERING_SKIPPED", None, None, "Sensitive request: similarity clustering bypassed")

    req.priority, req.priority_reason = calculate_priority(result["priority"], req.deadline_hours, req.affected_count,
                                                           impact["affected_pct"] if impact else None, req.scope,
                                                           result.get("is_emergency", False))
    start_sla(db, req)

    reasons = []
    if mode in ("review", "review_suggest"):
        if conf < config.CONFIDENCE_SUGGEST:
            reasons.append(f"Low AI confidence ({round(conf * 100)}%)")
        elif conf < config.CONFIDENCE_AUTO_ROUTE:
            reasons.append(f"Medium AI confidence ({round(conf * 100)}%)")
        if result.get("conflict"):
            reasons.append("Conflicting classifications")
        if not dept:
            reasons.append("No department matched")
        if len(secondaries) >= 2:
            reasons.append("Multi-department routing needs confirmation")
        req.human_review_reason = "; ".join(reasons) or "Flagged for review"
        req.status = "AWAITING_HUMAN_REVIEW"
        for u in users_with_role(db, "TRIAGE_AGENT"):
            notify(db, u.id, req, f"{req.request_number} needs human triage: {req.human_review_reason}", "TRIAGE")
    if dept_note:
        reasons.append(dept_note)

    req.ai_routing_reason = build_explanation(req, dept, secondaries, n_similar, impact, mode) + \
        (" " + dept_note if dept_note else "")
    req.student_summary = student_summary(req, dept, mode, result.get("is_crisis"))

    if mode in ("auto", "sensitive"):
        exp = assign_request(db, req, actor=None)
        if not exp:
            req.status = "AWAITING_HUMAN_REVIEW"
            req.human_review_reason = "No eligible staff in owning department"
    if req.priority == "CRITICAL" and dept and dept.is_emergency:
        for uid in {dept.lead_id, dept.dean_id} - {None}:
            notify(db, uid, req, f"EMERGENCY {req.request_number}: critical {dept.name} request received", "EMERGENCY")
    if req.cluster_id:
        recompute_cluster(db, db.get(Cluster, req.cluster_id))
    db.flush()
    return {"mode": mode, "result": result}


def create_request(db, student, title, description, privacy_mode="NORMAL", category_hint=None, created_at=None):
    privacy_mode = privacy_mode if privacy_mode in ("NORMAL", "CONFIDENTIAL", "ANONYMOUS") else "NORMAL"
    req = CampusSupportRequest(student_id=student.id, title=title.strip(), description=description.strip(),
                               category_hint=category_hint or None, privacy_mode=privacy_mode,
                               anonymous=privacy_mode == "ANONYMOUS", status="NEW", created_at=created_at or utcnow(),
                               routing_history=[])
    req.student = student
    db.add(req)
    db.flush()
    req.request_number = f"CAM{req.id:06d}"
    audit(db, req, student, "SUBMITTED", None, "NEW", f"privacy={privacy_mode}")
    triage_and_route(db, req)
    db.commit()
    db.refresh(req)
    return req


# ------------------------------------------------------------------ 8. human overrides & reassignment
def apply_override(db, req, actor, changes: dict, reason: str):
    """Human triage override. Every changed field is audited as routing feedback."""
    ai = dict(req.last_ai_analysis or {})
    for field in ("category", "subcategory", "priority", "sensitivity_level", "scope", "required_skill"):
        v = changes.get(field)
        if v and v != getattr(req, field):
            audit(db, req, actor, f"OVERRIDE_{field.upper()}", getattr(req, field), v, reason)
            setattr(req, field, v)
            if field == "priority":
                req.priority_reason = f"Priority set to {v} by {actor.full_name}: {reason}"
                start_sla(db, req, keep_start=True)
    new_primary = db.get(Department, changes["primary_department_id"]) if changes.get("primary_department_id") else req.primary_department
    if not new_primary:
        raise ValueError("A primary department is required")
    sec_ids = changes.get("secondary_department_ids")
    secondaries = [db.get(Department, i) for i in sec_ids] if sec_ids is not None else \
        [d.department for d in req.departments if d.role == "SUPPORTING"]
    secondaries = [d for d in secondaries if d and d.id != new_primary.id and not d.is_sensitive]
    if req.sensitivity_level == "HIGH":
        secondaries = []
    old_primary = req.primary_department_id
    if old_primary != new_primary.id:
        audit(db, req, actor, "OVERRIDE_PRIMARY_DEPARTMENT", old_primary, new_primary.id, reason)
    old_sec = sorted(req.secondary_department_ids)
    if sorted(d.id for d in secondaries) != old_sec:
        audit(db, req, actor, "OVERRIDE_SECONDARY_DEPARTMENTS", old_sec, sorted(d.id for d in secondaries), reason)
    set_departments(db, req, new_primary, secondaries, f"Human triage: {reason}")
    req.primary_department = new_primary
    if req.category in (None, "Unclassified"):
        req.category = new_primary.name
    ai["human_override"] = {"by": actor.full_name, "reason": reason, "at": utcnow().isoformat()}
    req.last_ai_analysis = ai
    req.human_review_reason = None

    if not is_clusterable(req):
        remove_from_cluster(db, req, actor)
    elif not req.cluster_id:
        cluster, n, _ = create_or_attach_cluster(db, req)
        recompute_cluster(db, cluster, actor)
    req.ai_routing_reason = (f"Human triage ({actor.full_name}) routed this to {new_primary.name}"
                             + (f" with support from {', '.join(d.name for d in secondaries)}" if secondaries else "")
                             + f". Reason: {reason}. Original AI confidence: {round((req.ai_confidence or 0) * 100)}%.")
    req.student_summary = student_summary(req, new_primary, "auto" if not new_primary.is_sensitive else "sensitive", False)
    exp = assign_request(db, req, actor, staff_id=changes.get("assigned_staff_id"), reason=reason)
    if not exp:
        req.status = "AWAITING_HUMAN_REVIEW"
        req.human_review_reason = "No eligible staff in selected department"
    db.commit()
    return req


def reassign(db, req, actor, department_id=None, staff_id=None, reason="", secondary_department_ids=None):
    changed_dept = department_id and department_id != req.primary_department_id
    if changed_dept:
        new = db.get(Department, department_id)
        if not new:
            raise ValueError("Unknown department")
        if new.is_sensitive and req.sensitivity_level != "HIGH" and actor.role_name == "DEPARTMENT_STAFF":
            pass  # allowed: moving a case INTO counselling is always permitted
        old = req.primary_department
        secondaries = [d.department for d in req.departments if d.role == "SUPPORTING" and d.department_id != new.id]
        if secondary_department_ids is not None:
            secondaries = [db.get(Department, i) for i in secondary_department_ids if i != new.id]
        set_departments(db, req, new, [d for d in secondaries if d], f"Reassigned: {reason}")
        req.primary_department = new
        req.reassignment_count = (req.reassignment_count or 0) + 1
        audit(db, req, actor, "REASSIGN_DEPARTMENT", old.name if old else None, new.name, reason)
        req.assigned_staff_id = None
        req.ai_routing_reason = (req.ai_routing_reason or "") + f" | Reassigned {old.name if old else '—'} → {new.name}: {reason}"
        if new.is_sensitive:
            req.sensitivity_level = "HIGH"
            remove_from_cluster(db, req, actor, "Moved to restricted department")
        if routing_mismatch(req):
            audit(db, req, actor, "ROUTING_MISMATCH", None, [h for h in req.routing_history], "Case bounced between departments")
    elif staff_id:
        req.reassignment_count = (req.reassignment_count or 0) + 1
    assign_request(db, req, actor, staff_id=staff_id, reason=reason)
    if (req.reassignment_count or 0) >= config.REASSIGNMENT_ESCALATION_THRESHOLD and (req.escalation_level or 1) < 2:
        escalate_request(db, req, "REASSIGNMENT", f"Reassigned {req.reassignment_count} times", actor, to_level=2)
    db.commit()
    return req
