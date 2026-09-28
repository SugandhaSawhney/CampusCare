from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from access import can_view, get_viewable, serialize_detail, serialize_row, staff_dept_id
from database import get_db
from models import CampusSupportRequest, Department, User
from security import require_roles
from services import routing_engine as eng
from services.rule_classifier import SUBCATEGORIES

router = APIRouter(tags=["triage & routing"])


class OverrideIn(BaseModel):
    category: Optional[str] = None
    subcategory: Optional[str] = None
    priority: Optional[Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]] = None
    sensitivity_level: Optional[Literal["NORMAL", "CONFIDENTIAL", "HIGH"]] = None
    scope: Optional[Literal["INDIVIDUAL", "CLASS", "BATCH", "DEPARTMENT", "CAMPUS"]] = None
    primary_department_id: int
    secondary_department_ids: Optional[List[int]] = None
    assigned_staff_id: Optional[int] = None
    reason: str = Field(min_length=3, max_length=500)


class AssignIn(BaseModel):
    staff_id: Optional[int] = None
    reason: Optional[str] = Field(default=None, max_length=500)


class ReassignIn(BaseModel):
    department_id: Optional[int] = None
    staff_id: Optional[int] = None
    secondary_department_ids: Optional[List[int]] = None
    reason: str = Field(min_length=3, max_length=500)


@router.get("/triage/queue")
def queue(db: Session = Depends(get_db), user: User = Depends(require_roles("TRIAGE_AGENT", "ADMIN"))):
    rows = (db.query(CampusSupportRequest).filter(CampusSupportRequest.status == "AWAITING_HUMAN_REVIEW",
                                                 CampusSupportRequest.sensitivity_level != "HIGH")
            .order_by(CampusSupportRequest.created_at).all())
    return [serialize_row(r, user) for r in rows]


@router.get("/triage/taxonomy")
def taxonomy(db: Session = Depends(get_db), user: User = Depends(require_roles("TRIAGE_AGENT", "DEPARTMENT_STAFF", "DEAN", "ADMIN"))):
    return {"subcategories": SUBCATEGORIES, "departments": [{"id": d.id, "name": d.name, "is_sensitive": d.is_sensitive}
                                                            for d in db.query(Department).order_by(Department.id)]}


@router.post("/triage/{request_id}")
def rerun(request_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("TRIAGE_AGENT", "ADMIN"))):
    req = get_viewable(db, user, request_id)
    if req.status not in ("NEW", "TRIAGING", "AWAITING_HUMAN_REVIEW"):
        raise HTTPException(400, "Re-triage only applies to un-assigned requests")
    eng.remove_from_cluster(db, req, user, "Re-triage")
    eng.audit(db, req, user, "RETRIAGE_REQUESTED")
    eng.triage_and_route(db, req, user)
    db.commit()
    return serialize_detail(db, req, user)


@router.post("/triage/{request_id}/override")
def override(request_id: int, body: OverrideIn, db: Session = Depends(get_db),
             user: User = Depends(require_roles("TRIAGE_AGENT", "ADMIN"))):
    req = get_viewable(db, user, request_id)
    if body.subcategory:
        dept = db.get(Department, body.primary_department_id)
        if dept and body.subcategory not in SUBCATEGORIES.get(dept.name, []):
            raise HTTPException(400, f"Subcategory not valid for {dept.name}")
    changes = body.model_dump()
    if body.subcategory:
        changes["required_skill"] = body.subcategory
    try:
        eng.apply_override(db, req, user, changes, body.reason)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return serialize_detail(db, req, user)


@router.post("/routing/{request_id}")
def preview_routing(request_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("TRIAGE_AGENT", "DEPARTMENT_STAFF", "DEAN", "ADMIN"))):
    """Transparent assignment preview: eligible staff with score breakdown for the owning department."""
    req = get_viewable(db, user, request_id)
    dept = req.primary_department
    if not dept:
        raise HTTPException(400, "No owning department yet")
    return {"department": dept.name, "required_skill": req.required_skill,
            "candidates": eng.find_eligible_staff(db, dept, req.required_skill)}


@router.get("/routing/{request_id}/staff-options")
def staff_options(request_id: int, department_id: Optional[int] = None, db: Session = Depends(get_db),
                  user: User = Depends(require_roles("TRIAGE_AGENT", "DEPARTMENT_STAFF", "DEAN", "ADMIN"))):
    req = get_viewable(db, user, request_id)
    dept = db.get(Department, department_id) if department_id else req.primary_department
    if not dept:
        return {"candidates": []}
    return {"department": dept.name, "candidates": eng.find_eligible_staff(db, dept, req.required_skill)}


@router.post("/routing/{request_id}/assign")
def assign(request_id: int, body: AssignIn, db: Session = Depends(get_db),
           user: User = Depends(require_roles("TRIAGE_AGENT", "DEPARTMENT_STAFF", "DEAN", "ADMIN"))):
    req = get_viewable(db, user, request_id)
    if user.role_name == "DEPARTMENT_STAFF" and (user.staff_profile.hierarchy_level < 2 or req.primary_department_id != staff_dept_id(user)):
        raise HTTPException(403, "Only the owning department's lead can assign")
    if not req.primary_department_id:
        raise HTTPException(400, "Set a department via triage override first")
    try:
        eng.assign_request(db, req, user, staff_id=body.staff_id, reason=body.reason)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    return serialize_detail(db, req, user)


@router.post("/routing/{request_id}/reassign")
def reassign(request_id: int, body: ReassignIn, db: Session = Depends(get_db),
             user: User = Depends(require_roles("TRIAGE_AGENT", "DEPARTMENT_STAFF", "DEAN", "ADMIN"))):
    req = get_viewable(db, user, request_id)
    if user.role_name == "DEPARTMENT_STAFF":
        if req.primary_department_id != staff_dept_id(user):
            raise HTTPException(403, "Only the owning department can reassign")
        if req.sensitivity_level == "HIGH" and body.department_id and body.department_id != req.primary_department_id:
            raise HTTPException(403, "Sensitive cases can only be transferred by a dean or admin")
    if user.role_name == "TRIAGE_AGENT" and req.sensitivity_level == "HIGH":
        raise HTTPException(403, "Restricted case")
    try:
        eng.reassign(db, req, user, body.department_id, body.staff_id, body.reason, body.secondary_department_ids)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return serialize_detail(db, req, user) if can_view(db, user, req) else {"ok": True, "moved": True}
