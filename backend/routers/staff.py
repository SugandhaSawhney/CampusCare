from collections import Counter
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

import config
from access import can_view, dean_dept_ids, is_central, scoped_query, serialize_row, staff_dept_id
from database import get_db, iso, utcnow
from models import (CampusSupportRequest, Cluster, ClusterMember, Department, Escalation, Notification, RequestDepartment,
                    StaffProfile, User)
from security import get_current_user, require_roles
from services import routing_engine as eng

router = APIRouter(tags=["staff"])
STAFFISH = ("TRIAGE_AGENT", "DEPARTMENT_STAFF", "DEAN", "ADMIN")


def visible_clusters(db, user):
    q = db.query(Cluster)
    role = user.role_name
    if role == "DEPARTMENT_STAFF":
        did = staff_dept_id(user)
        q = q.filter(Cluster.id.in_(select(CampusSupportRequest.cluster_id).join(
            RequestDepartment, RequestDepartment.request_id == CampusSupportRequest.id).where(RequestDepartment.department_id == did)))
    elif role == "DEAN" and not is_central(user):
        q = q.filter(Cluster.primary_department_id.in_(dean_dept_ids(db, user)))
    return q.all()


def cluster_out(db, c):
    imp = eng.cluster_impact(db, c)
    return {"id": c.id, "label": c.label, "category": c.category, "subcategory": c.subcategory,
            "primary_department": c.primary_department.name if c.primary_department else None,
            "status": c.status if imp["open_count"] else "RESOLVED", "priority": c.priority,
            "created_at": iso(c.created_at), "updated_at": iso(c.updated_at), **imp}


@router.get("/departments")
def departments(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [{"id": d.id, "name": d.name, "code": d.code, "is_sensitive": d.is_sensitive} for d in db.query(Department).order_by(Department.id)]


@router.get("/staff/requests")
def list_requests(department: Optional[str] = None, priority: Optional[str] = None, status: Optional[str] = None,
                  sensitivity: Optional[str] = None, scope: Optional[str] = None, sla: Optional[str] = None,
                  min_conf: Optional[float] = None, max_conf: Optional[float] = None, q: Optional[str] = None,
                  mine: bool = False, db: Session = Depends(get_db), user: User = Depends(require_roles(*STAFFISH))):
    qry = scoped_query(db, user)
    C = CampusSupportRequest
    if priority:
        qry = qry.filter(C.priority == priority)
    if status:
        qry = qry.filter(C.status == status)
    if sensitivity:
        qry = qry.filter(C.sensitivity_level == sensitivity)
    if scope:
        qry = qry.filter(C.scope == scope)
    if min_conf is not None:
        qry = qry.filter(C.ai_confidence >= min_conf)
    if max_conf is not None:
        qry = qry.filter(C.ai_confidence < max_conf)
    if department:
        qry = qry.join(Department, Department.id == C.primary_department_id).filter(Department.name == department)
    if mine:
        qry = qry.filter(C.assigned_staff_id == user.id)
    if q:
        qry = qry.filter((C.request_number.ilike(f"%{q}%")) | (C.title.ilike(f"%{q}%")))
    rows = [serialize_row(r, user) for r in qry.order_by(C.created_at.desc()).limit(500).all()]
    if sla:
        rows = [r for r in rows if r["sla_status"] == sla]
    return rows


@router.get("/staff/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(require_roles(*STAFFISH))):
    eng.check_sla(db)
    reqs = scoped_query(db, user).all()
    open_r = [r for r in reqs if r.status in eng.OPEN_STATUSES]
    states = Counter(eng.sla_state(r)[0] for r in open_r)
    clusters = [cluster_out(db, c) for c in visible_clusters(db, user)]
    active_clusters = [c for c in clusters if c["request_count"] >= config.MIN_CLUSTER_DISPLAY and c["open_count"]]
    triaged = [r for r in reqs if r.last_ai_analysis]
    human = [r for r in triaged if (r.last_ai_analysis or {}).get("human_override") or r.status == "AWAITING_HUMAN_REVIEW"]
    ids = [r.id for r in reqs]
    breach_esc = db.query(Escalation).filter(Escalation.trigger == "SLA_BREACH", Escalation.request_id.in_(ids)).all()
    breached_open = {e.request_id for e in breach_esc} & {r.id for r in open_r} | {r.id for r in open_r if eng.sla_state(r)[0] == "BREACHED"}
    routed = [r for r in reqs if r.routed_at and r.created_at]
    avg_route_min = round(sum((r.routed_at - r.created_at).total_seconds() for r in routed) / len(routed) / 60, 1) if routed else None
    by_dept = Counter((r.primary_department.name if r.primary_department else "Unrouted") for r in reqs)
    all_sensitive = db.query(CampusSupportRequest).filter(CampusSupportRequest.sensitivity_level == "HIGH").count()
    mismatches = [serialize_row(r, user) for r in reqs if eng.routing_mismatch(r)]
    return {
        "cards": {
            "total_open": len(open_r),
            "human_review": sum(1 for r in open_r if r.status == "AWAITING_HUMAN_REVIEW"),
            "high_priority": sum(1 for r in open_r if r.priority in ("HIGH", "CRITICAL")),
            "sla_at_risk": states.get("APPROACHING", 0),
            "sla_breached": len(breached_open),
            "active_clusters": len(active_clusters),
            "escalated": sum(1 for r in open_r if r.status == "ESCALATED"),
        },
        "analytics": {
            "by_department": [{"name": k, "count": v} for k, v in by_dept.most_common()],
            "by_priority": [{"name": p, "count": sum(1 for r in reqs if r.priority == p)} for p in config.PRIORITIES],
            "human_fallback_rate": round(100 * len(human) / len(triaged), 1) if triaged else 0,
            "auto_route_rate": round(100 * (len(triaged) - len(human)) / len(triaged), 1) if triaged else 0,
            "avg_routing_minutes": avg_route_min,
            "sla_breach_count": len(breach_esc),
            "reassignment_count": sum(r.reassignment_count or 0 for r in reqs),
            "multi_department_cases": sum(1 for r in reqs if len(r.departments) > 1),
            "sensitive_cases_total": all_sensitive,  # aggregate only - never itemised in analytics
            "top_clusters": sorted(active_clusters, key=lambda c: -c["affected_count"])[:5],
            "routing_mismatches": mismatches[:10],
            "engine": "LLM" if config.LLM_API_KEY else "Deterministic fallback (no API key)",
        },
    }


@router.get("/staff/clusters")
def clusters(all: bool = False, db: Session = Depends(get_db), user: User = Depends(require_roles(*STAFFISH))):
    out = [cluster_out(db, c) for c in visible_clusters(db, user)]
    if not all:
        out = [c for c in out if c["request_count"] >= config.MIN_CLUSTER_DISPLAY]
    return sorted(out, key=lambda c: (-c["open_count"], -c["affected_count"]))


@router.get("/staff/clusters/{cluster_id}")
def cluster_detail(cluster_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(*STAFFISH))):
    c = next((c for c in visible_clusters(db, user) if c.id == cluster_id), None)
    if not c:
        raise HTTPException(404, "Cluster not found")
    members = [m for m in c.members if m.request.sensitivity_level == "NORMAL" and can_view(db, user, m.request)]
    return {**cluster_out(db, c), "members": [{**serialize_row(m.request, user), "similarity": m.similarity, "method": m.method}
                                              for m in sorted(members, key=lambda m: m.added_at)]}


class ClusterStatusIn(BaseModel):
    status: str = Field(pattern="^(INVESTIGATING|ROOT_CAUSE_FOUND|FIX_DEPLOYED|MONITORING)$")


@router.post("/staff/clusters/{cluster_id}/status")
def cluster_status(cluster_id: int, body: ClusterStatusIn, db: Session = Depends(get_db),
                   user: User = Depends(require_roles("DEPARTMENT_STAFF", "TRIAGE_AGENT", "DEAN", "ADMIN"))):
    c = next((c for c in visible_clusters(db, user) if c.id == cluster_id), None)
    if not c:
        raise HTTPException(404, "Cluster not found")
    eng.audit(db, None, user, "CLUSTER_STATUS", c.status, body.status, f"cluster#{c.id}")
    c.status = body.status
    db.commit()
    return cluster_out(db, c)


@router.get("/staff/escalations")
def escalations(include_closed: bool = False, db: Session = Depends(get_db), user: User = Depends(require_roles(*STAFFISH))):
    ids = [r.id for r in scoped_query(db, user).all()]
    q = db.query(Escalation).filter(Escalation.request_id.in_(ids))
    if not include_closed:
        q = q.filter(Escalation.closed.is_(False))
    out = []
    for e in q.order_by(Escalation.escalated_at.desc()).all():
        r = e.request
        st, rem = eng.sla_state(r)
        out.append({"id": e.id, "request_id": r.id, "request_number": r.request_number,
                    "title": "Anonymous sensitive request" if r.anonymous else r.title,
                    "department": r.primary_department.name if r.primary_department else None,
                    "level": e.to_level, "level_label": config.ESCALATION_LEVELS.get(e.to_level),
                    "next_authority": config.ESCALATION_LEVELS.get((e.to_level or 1) + 1, "— (top of hierarchy)"),
                    "target": e.target_user.full_name if e.target_user else None, "reason": e.reason, "trigger": e.trigger,
                    "escalated_at": iso(e.escalated_at), "sla_status": st, "priority": r.priority, "status": r.status,
                    "closed": e.closed, "decision_note": e.decision_note, "is_mine": e.target_user_id == user.id})
    return out


class CloseEscIn(BaseModel):
    decision_note: str = Field(min_length=3, max_length=1000)


@router.post("/staff/escalations/{esc_id}/close")
def close_escalation(esc_id: int, body: CloseEscIn, db: Session = Depends(get_db),
                     user: User = Depends(require_roles("DEPARTMENT_STAFF", "DEAN", "ADMIN"))):
    e = db.get(Escalation, esc_id)
    if not e or not can_view(db, user, e.request):
        raise HTTPException(404, "Escalation not found")
    if user.role_name != "ADMIN" and e.target_user_id != user.id:
        raise HTTPException(403, "Only the escalation authority can close it")
    e.closed, e.closed_at, e.decision_note = True, utcnow(), body.decision_note
    r = e.request
    if r.status == "ESCALATED":
        r.status = "IN_PROGRESS"
        _, window, _ = eng.sla_rule(db, r.priority)
        r.sla_due_at = utcnow() + timedelta(hours=window)
        r.escalated_at = utcnow()
    eng.audit(db, r, user, "ESCALATION_CLOSED", f"L{e.to_level}", "IN_PROGRESS", body.decision_note)
    eng.notify(db, r.assigned_staff_id, r, f"{r.request_number}: escalation decision by {user.full_name}: {body.decision_note}", "ESCALATION")
    db.commit()
    return {"ok": True}


@router.get("/staff/directory")
def directory(department_id: Optional[int] = None, db: Session = Depends(get_db), user: User = Depends(require_roles(*STAFFISH))):
    q = db.query(StaffProfile).join(User, StaffProfile.user_id == User.id)
    if department_id:
        q = q.filter(StaffProfile.department_id == department_id)
    return [{"user_id": p.user_id, "name": p.user.full_name, "department_id": p.department_id, "level": p.hierarchy_level,
             "skills": p.skills, "available": p.available, "active_cases": eng.active_case_count(db, p.user_id)}
            for p in q.all() if p.department_id]


@router.get("/notifications")
def notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(Notification).filter_by(user_id=user.id).order_by(Notification.created_at.desc()).limit(30).all()
    return [{"id": n.id, "message": n.message, "kind": n.kind, "read": n.read, "request_id": n.request_id,
             "created_at": iso(n.created_at)} for n in rows]


@router.post("/notifications/read-all")
def read_all(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db.query(Notification).filter_by(user_id=user.id, read=False).update({"read": True})
    db.commit()
    return {"ok": True}


@router.post("/sla/check")
def run_sla_check(db: Session = Depends(get_db), user: User = Depends(require_roles("TRIAGE_AGENT", "DEAN", "ADMIN"))):
    return {"escalated": eng.check_sla(db)}


@router.post("/demo/simulate-breach/{request_id}")
def simulate_breach(request_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("TRIAGE_AGENT", "ADMIN"))):
    """Demo helper: fast-forwards one case's SLA clock so the escalation path can be shown live."""
    if not config.DEMO_MODE:
        raise HTTPException(404, "Not found")
    r = db.get(CampusSupportRequest, request_id)
    if not r or not can_view(db, user, r) and user.role_name != "ADMIN":
        raise HTTPException(404, "Request not found")
    r.sla_due_at = utcnow() - timedelta(minutes=1)
    eng.audit(db, r, user, "DEMO_SLA_FAST_FORWARD", None, None, "Demo mode: SLA clock fast-forwarded")
    db.commit()
    return {"escalated": eng.check_sla(db), "escalation_level": db.get(CampusSupportRequest, request_id).escalation_level}
