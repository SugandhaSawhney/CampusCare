"""Backend RBAC: who can see which request, and what each role is allowed to see of it."""
from fastapi import HTTPException
from sqlalchemy import false, or_, select, true
from sqlalchemy.orm import Session

import config
from database import iso
from models import CampusSupportRequest, Department, Escalation, InternalNote, RequestDepartment, RequestMessage, StaffProfile, User
from services.routing_engine import cluster_impact, routing_mismatch, sla_state

HIDDEN_FROM_DEPT = ("NEW", "TRIAGING", "AWAITING_HUMAN_REVIEW")


def staff_dept_id(user: User):
    return user.staff_profile.department_id if user.staff_profile else None


def dean_dept_ids(db, user):
    return [d.id for d in db.query(Department).filter(Department.dean_id == user.id).all()]


def is_central(user):
    return user.staff_profile is not None and user.staff_profile.hierarchy_level >= 4


def can_view(db: Session, user: User, req: CampusSupportRequest) -> bool:
    role = user.role_name
    if role == "ADMIN":
        return True
    if role == "STUDENT":
        return req.student_id == user.id
    if role == "TRIAGE_AGENT":
        return req.sensitivity_level != "HIGH"
    if role == "DEPARTMENT_STAFF":
        did = staff_dept_id(user)
        if req.status in HIDDEN_FROM_DEPT or not did:
            return False
        if req.sensitivity_level == "HIGH":
            # need-to-know only: assigned staff, owning dept lead, or current escalation target
            if req.primary_department_id != did:
                return False
            lead = user.staff_profile.hierarchy_level >= 2
            target = db.query(Escalation).filter_by(request_id=req.id, target_user_id=user.id).first()
            return req.assigned_staff_id == user.id or lead or bool(target)
        return any(d.department_id == did for d in req.departments)
    if role == "DEAN":
        if is_central(user):
            return (req.escalation_level or 0) >= 3
        in_scope = req.primary_department_id in dean_dept_ids(db, user)
        min_level = 3 if req.sensitivity_level == "HIGH" else 2
        return in_scope and (req.escalation_level or 0) >= min_level
    return False


def get_viewable(db, user, request_id) -> CampusSupportRequest:
    req = db.get(CampusSupportRequest, request_id)
    if not req or not can_view(db, user, req):
        raise HTTPException(404, "Request not found")  # 404 (not 403) avoids leaking existence
    return req


def scoped_query(db, user):
    q = db.query(CampusSupportRequest)
    role = user.role_name
    C = CampusSupportRequest
    if role == "ADMIN":
        return q
    if role == "STUDENT":
        return q.filter(C.student_id == user.id)
    if role == "TRIAGE_AGENT":
        return q.filter(C.sensitivity_level != "HIGH")
    if role == "DEPARTMENT_STAFF":
        did = staff_dept_id(user)
        lead = user.staff_profile and user.staff_profile.hierarchy_level >= 2
        esc_ids = [e.request_id for e in db.query(Escalation).filter_by(target_user_id=user.id).all()]
        normal = C.id.in_(select(RequestDepartment.request_id).where(RequestDepartment.department_id == did))
        sens_ok = (C.primary_department_id == did) & (
            (C.assigned_staff_id == user.id) | (C.id.in_(esc_ids)) | (true() if lead else false()))
        return q.filter(~C.status.in_(HIDDEN_FROM_DEPT)).filter(
            or_((C.sensitivity_level != "HIGH") & normal, (C.sensitivity_level == "HIGH") & sens_ok))
    if role == "DEAN":
        if is_central(user):
            return q.filter(C.escalation_level >= 3)
        ids = dean_dept_ids(db, user)
        return q.filter(C.primary_department_id.in_(ids)).filter(
            or_((C.sensitivity_level != "HIGH") & (C.escalation_level >= 2), (C.sensitivity_level == "HIGH") & (C.escalation_level >= 3)))
    return q.filter(false())


def is_staff_view(user):
    return user.role_name in ("TRIAGE_AGENT", "DEPARTMENT_STAFF", "DEAN", "ADMIN")


def _sla(req):
    st, remaining = sla_state(req)
    return {"due_at": iso(req.sla_due_at), "status": st, "seconds_remaining": int(remaining) if remaining is not None else None}


def _depts(req):
    prim = next((d.department for d in req.departments if d.role == "PRIMARY"), None)
    sup = [d.department for d in req.departments if d.role == "SUPPORTING"]
    return prim, sup


def serialize_row(req, user):
    """Compact row for tables; staff-only."""
    prim, sup = _depts(req)
    st, _ = sla_state(req)
    return {
        "id": req.id, "request_number": req.request_number, "title": "Anonymous sensitive request" if (req.anonymous and req.sensitivity_level == "HIGH" and user.role_name != "ADMIN" and req.assigned_staff_id != user.id) else req.title,
        "category": req.category, "subcategory": req.subcategory, "priority": req.priority,
        "sensitivity": req.sensitivity_level, "scope": req.scope, "affected_count": req.affected_count,
        "ai_confidence": req.ai_confidence, "primary_department": prim.name if prim else None,
        "suggested_department": (req.last_ai_analysis or {}).get("primary_department"),
        "supporting_departments": [d.name for d in sup],
        "assigned_staff": req.assigned_staff.full_name if req.assigned_staff else None,
        "status": req.status, "sla_status": st, "sla_due_at": iso(req.sla_due_at), "escalation_level": req.escalation_level,
        "created_at": iso(req.created_at), "cluster_id": req.cluster_id if req.sensitivity_level == "NORMAL" else None,
        "anonymous": req.anonymous, "human_review_reason": req.human_review_reason,
        "reassignment_count": req.reassignment_count, "routing_mismatch": routing_mismatch(req),
    }


def timeline(db, req):
    steps = [("Submitted", req.created_at), ("AI Triaged", req.created_at), ("Assigned", req.routed_at),
             ("In Progress", None), ("Resolved", req.resolved_at)]
    from models import AuditLog
    prog = db.query(AuditLog).filter(AuditLog.request_id == req.id, AuditLog.action == "STATUS_CHANGE",
                                     AuditLog.new_value == "IN_PROGRESS").order_by(AuditLog.timestamp).first()
    order = ["NEW", "TRIAGING", "AWAITING_HUMAN_REVIEW", "ASSIGNED", "IN_PROGRESS", "WAITING_FOR_STUDENT", "ESCALATED", "RESOLVED", "CLOSED"]
    out = []
    for name, ts in steps:
        if name == "In Progress":
            ts = prog.timestamp if prog else None
        done = ts is not None or (name == "In Progress" and req.status in ("RESOLVED", "CLOSED"))
        out.append({"step": name, "at": iso(ts), "done": done})
    if req.status == "AWAITING_HUMAN_REVIEW":
        out.insert(2, {"step": "Specialist verification", "at": None, "done": False, "current": True})
    return out


def serialize_detail(db, req, user):
    prim, sup = _depts(req)
    base = {
        "id": req.id, "request_number": req.request_number, "title": req.title, "description": req.description,
        "status": req.status, "priority": req.priority, "category": req.category, "subcategory": req.subcategory,
        "privacy_mode": req.privacy_mode, "anonymous": req.anonymous, "created_at": iso(req.created_at),
        "updated_at": iso(req.updated_at), "resolved_at": iso(req.resolved_at), "resolution_note": req.resolution_note,
        "resolution_confirmed": req.resolution_confirmed, "reopen_requested": req.reopen_requested,
        "sla": _sla(req), "timeline": timeline(db, req),
        "messages": [{"id": m.id, "from_staff": m.from_staff,
                      "author": ("Support team" if m.from_staff else "You") if user.role_name == "STUDENT" else
                      ("Student" if (req.anonymous and not m.from_staff) else m.author.full_name),
                      "body": m.body, "created_at": iso(m.created_at)}
                     for m in db.query(RequestMessage).filter_by(request_id=req.id).order_by(RequestMessage.created_at)],
    }
    if user.role_name == "STUDENT":
        # Student-safe projection: no internal reasoning, notes, scoring, cluster or staff-identity for sensitive/anon cases.
        base.update({
            "primary_department": (prim.name if prim else None) if req.status != "AWAITING_HUMAN_REVIEW" else None,
            "supporting_departments": [d.name for d in sup] if req.status != "AWAITING_HUMAN_REVIEW" else [],
            "ai_confidence": req.ai_confidence, "human_review": req.status == "AWAITING_HUMAN_REVIEW",
            "summary": req.student_summary,
            "assigned_to": None if (req.anonymous or req.sensitivity_level == "HIGH" or not req.assigned_staff)
            else req.assigned_staff.full_name.split()[0] + " (" + (prim.name if prim else "Support") + ")",
            "is_crisis": (req.last_ai_analysis or {}).get("is_crisis", False),
        })
        return base

    impact = None
    if req.cluster_id and req.sensitivity_level == "NORMAL" and req.cluster:
        impact = {"cluster_id": req.cluster_id, "label": req.cluster.label, **cluster_impact(db, req.cluster)}
    student = None
    if not req.anonymous:
        s = req.student
        student = {"name": s.full_name, "email": s.email, "batch": s.batch_label}
    ai = dict(req.last_ai_analysis or {})
    if req.sensitivity_level == "HIGH":
        ai.pop("matched_signals", None)
    escalations = db.query(Escalation).filter_by(request_id=req.id).order_by(Escalation.escalated_at).all()
    base.update({
        "student": student, "student_label": "Anonymous student (identity protected)" if req.anonymous else student["name"],
        "sensitivity": req.sensitivity_level, "scope": req.scope, "batch_label": req.batch_label,
        "deadline_hours": req.deadline_hours, "ai_confidence": req.ai_confidence, "ai_engine": req.ai_engine,
        "required_skill": req.required_skill, "routing_reason": req.ai_routing_reason, "priority_reason": req.priority_reason,
        "human_review_reason": req.human_review_reason, "ai_analysis": ai,
        "primary_department": {"id": prim.id, "name": prim.name} if prim else None,
        "supporting_departments": [{"id": d.id, "name": d.name} for d in sup],
        "assigned_staff": {"id": req.assigned_staff.id, "name": req.assigned_staff.full_name} if req.assigned_staff else None,
        "assignment_reason": req.assignment_reason, "impact": impact, "affected_count": req.affected_count,
        "escalation_level": req.escalation_level, "escalation_label": config.ESCALATION_LEVELS.get(req.escalation_level or 1),
        "next_authority": config.ESCALATION_LEVELS.get((req.escalation_level or 1) + 1),
        "escalations": [{"id": e.id, "from_level": e.from_level, "to_level": e.to_level, "reason": e.reason, "trigger": e.trigger,
                         "target": e.target_user.full_name if e.target_user else None, "at": iso(e.escalated_at),
                         "closed": e.closed, "decision_note": e.decision_note} for e in escalations],
        "reassignment_count": req.reassignment_count, "routing_mismatch": routing_mismatch(req),
        "routing_history": [db.get(Department, i).name for i in (req.routing_history or []) if db.get(Department, i)],
        "notes": [{"id": n.id, "author": n.author.full_name, "body": n.body, "created_at": iso(n.created_at)}
                  for n in db.query(InternalNote).filter_by(request_id=req.id).order_by(InternalNote.created_at)],
    })
    return base
