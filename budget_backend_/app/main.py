import os
from fastapi import FastAPI, Depends, HTTPException, status, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from . import models as m
from .database import get_db, engine, Base
from .auth import verify_password, hash_password, create_access_token, decode_access_token

app = FastAPI(title="نظام الموازنات التقديرية والتخطيط المالي — API")

# Restricted to known frontend origins. Add more Netlify/Cloudflare/custom domains here as needed.
ALLOWED_ORIGINS = [
    "https://clever-semolina-d36545.netlify.app",
    "https://budget234.cloud-admin-847.workers.dev",
    "http://localhost:3000",   # local dev
    "http://localhost:5173",   # local dev (vite)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


@app.on_event("startup")
def on_startup():
    # In production prefer Alembic migrations over create_all.
    Base.metadata.create_all(bind=engine)


# ============================================================================
# AUTH
# ============================================================================

def get_current_user(token: Optional[str] = Depends(oauth2_scheme), token_qs: Optional[str] = None,
                      db: Session = Depends(get_db)) -> m.User:
    tok = token or token_qs
    if not tok:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_access_token(tok)
        user_id = payload.get("sub")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db.query(m.User).filter(m.User.id == user_id).first()
    if not user or not user.active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


@app.post("/auth/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(m.User).filter(m.User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="اسم المستخدم أو كلمة المرور غير صحيحة")
    if not user.active:
        raise HTTPException(status_code=403, detail="الحساب غير مفعل")

    links = db.query(m.UserCompany).filter(m.UserCompany.user_id == user.id).all()
    token = create_access_token({"sub": user.id, "username": user.username})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id, "username": user.username, "name": user.name,
            "companies": [
                {"company_id": l.company_id, "role": l.role.value, "branch_id": l.branch_id, "sections": l.sections}
                for l in links
            ],
        },
    }


@app.get("/auth/me")
def me(current_user: m.User = Depends(get_current_user)):
    return {"id": current_user.id, "username": current_user.username, "name": current_user.name}


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


@app.post("/auth/change-password")
def change_password(payload: ChangePasswordIn, db: Session = Depends(get_db),
                     current_user: m.User = Depends(get_current_user)):
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="كلمة المرور الحالية غير صحيحة")
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="كلمة المرور الجديدة يجب أن تكون 8 أحرف على الأقل")
    current_user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"status": "ok", "message": "تم تغيير كلمة المرور بنجاح"}


# ============================================================================
# ADMIN: USER MANAGEMENT
# The app's own "Users" screen only edited the shared DB blob (role/section
# display data) — it never touched real backend login credentials. These
# endpoints let admin/gm users actually create/reset/deactivate the real
# login accounts, wired up from the frontend's user-management screen.
# ============================================================================

def require_admin_or_gm(db: Session, current_user: m.User) -> m.UserCompany:
    link = (db.query(m.UserCompany)
            .filter(m.UserCompany.user_id == current_user.id)
            .filter(m.UserCompany.role.in_([m.UserRole.admin, m.UserRole.gm]))
            .first())
    if not link:
        raise HTTPException(status_code=403, detail="هذا الإجراء متاح فقط لمدير النظام أو المدير العام")
    return link


class CreateUserIn(BaseModel):
    username: str
    password: str
    name: str
    role: str = "staff"


@app.post("/admin/users")
def admin_create_user(payload: CreateUserIn, db: Session = Depends(get_db),
                       current_user: m.User = Depends(get_current_user)):
    link = require_admin_or_gm(db, current_user)
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="كلمة المرور يجب أن تكون 6 أحرف على الأقل")
    existing = db.query(m.User).filter_by(username=payload.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="اسم المستخدم مُستخدَم بالفعل في نظام الدخول")
    role = payload.role if payload.role in ("admin", "gm", "finance", "staff") else "staff"
    u = m.User(username=payload.username, name=payload.name, password_hash=hash_password(payload.password))
    db.add(u)
    db.flush()
    db.add(m.UserCompany(user_id=u.id, company_id=link.company_id, role=role))
    db.commit()
    return {"status": "ok", "id": u.id}


class ResetPasswordIn(BaseModel):
    username: str
    new_password: str


@app.post("/admin/users/reset-password")
def admin_reset_password(payload: ResetPasswordIn, db: Session = Depends(get_db),
                          current_user: m.User = Depends(get_current_user)):
    require_admin_or_gm(db, current_user)
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="كلمة المرور يجب أن تكون 6 أحرف على الأقل")
    target = db.query(m.User).filter_by(username=payload.username).first()
    if not target:
        # لا يوجد حساب دخول حقيقي بهذا الاسم بعد — أنشئه بدل الفشل الصامت
        target = m.User(username=payload.username, name=payload.username, password_hash=hash_password(payload.new_password))
        db.add(target)
        db.flush()
        link = require_admin_or_gm(db, current_user)
        db.add(m.UserCompany(user_id=target.id, company_id=link.company_id, role="staff"))
    else:
        target.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"status": "ok"}


class RenameUserIn(BaseModel):
    old_username: str
    new_username: str


@app.post("/admin/users/rename")
def admin_rename_user(payload: RenameUserIn, db: Session = Depends(get_db),
                       current_user: m.User = Depends(get_current_user)):
    require_admin_or_gm(db, current_user)
    if payload.old_username == payload.new_username:
        return {"status": "ok"}
    target = db.query(m.User).filter_by(username=payload.old_username).first()
    if not target:
        return {"status": "ok", "note": "no matching backend login account (nothing to rename)"}
    clash = db.query(m.User).filter_by(username=payload.new_username).first()
    if clash:
        raise HTTPException(status_code=400, detail="اسم المستخدم الجديد مُستخدَم بالفعل")
    target.username = payload.new_username
    db.commit()
    return {"status": "ok"}


class DeactivateUserIn(BaseModel):
    username: str
    active: bool = False


@app.post("/admin/users/set-active")
def admin_set_active(payload: DeactivateUserIn, db: Session = Depends(get_db),
                      current_user: m.User = Depends(get_current_user)):
    require_admin_or_gm(db, current_user)
    if payload.username == current_user.username and not payload.active:
        raise HTTPException(status_code=400, detail="لا يمكنك تعطيل حسابك الخاص أثناء تسجيل الدخول به — سجّل دخولاً بحساب آخر أولاً")
    target = db.query(m.User).filter_by(username=payload.username).first()
    if not target:
        return {"status": "ok", "note": "no matching backend login account (nothing to deactivate)"}
    if not payload.active:
        # حماية: لا تسمح بتعطيل آخر حساب دخول نشط بصلاحية admin/gm — حتى لو
        # طُلب ذلك بالخطأ من الواجهة، لتفادي القفل الكامل خارج النظام
        target_link = (db.query(m.UserCompany)
                       .filter(m.UserCompany.user_id == target.id)
                       .filter(m.UserCompany.role.in_([m.UserRole.admin, m.UserRole.gm]))
                       .first())
        if target_link:
            other_active_admins = (db.query(m.User)
                                    .join(m.UserCompany, m.UserCompany.user_id == m.User.id)
                                    .filter(m.UserCompany.role.in_([m.UserRole.admin, m.UserRole.gm]))
                                    .filter(m.User.active == True)
                                    .filter(m.User.id != target.id)
                                    .count())
            if other_active_admins == 0:
                raise HTTPException(status_code=400, detail="لا يمكن تعطيل آخر حساب دخول نشط بصلاحية مدير/مدير عام")
    target.active = payload.active
    db.commit()
    return {"status": "ok"}


# ============================================================================
# COMPANIES / BRANCHES
# ============================================================================

@app.get("/companies")
def list_companies(db: Session = Depends(get_db), current_user: m.User = Depends(get_current_user)):
    links = db.query(m.UserCompany).filter(m.UserCompany.user_id == current_user.id).all()
    company_ids = [l.company_id for l in links]
    companies = db.query(m.Company).filter(m.Company.id.in_(company_ids)).all()
    return [{"id": c.id, "name": c.name, "currency": c.currency, "active_year": c.active_year} for c in companies]


@app.get("/companies/{company_id}/branches")
def list_branches(company_id: str, db: Session = Depends(get_db), current_user: m.User = Depends(get_current_user)):
    branches = db.query(m.Branch).filter(m.Branch.company_id == company_id).order_by(m.Branch.sort_order).all()
    return [{"id": b.id, "name": b.name, "active": b.active} for b in branches]


# ============================================================================
# BUDGETS (sales shown as a full example; hr/marketing/opex/inventory follow
# the identical pattern — copy this block and swap the model class)
# ============================================================================

class SalesBudgetIn(BaseModel):
    weights: dict
    month_mode: str = "weight"
    prev_year_sales: float = 0
    growth_pct: float = 0
    avg_invoice: float = 0
    customers_count: int = 0
    cogs_pct: float = 60
    cogs_method: str = "pct"
    status: str = "draft"


@app.get("/budget-years/{budget_year_id}/sales/{branch_id}")
def get_sales_budget(budget_year_id: str, branch_id: str, db: Session = Depends(get_db),
                      current_user: m.User = Depends(get_current_user)):
    sb = db.query(m.SalesBudget).filter_by(budget_year_id=budget_year_id, branch_id=branch_id).first()
    if not sb:
        raise HTTPException(status_code=404, detail="Not found")
    return {
        "id": sb.id, "weights": sb.weights, "month_mode": sb.month_mode,
        "prev_year_sales": float(sb.prev_year_sales), "growth_pct": float(sb.growth_pct),
        "avg_invoice": float(sb.avg_invoice), "customers_count": sb.customers_count,
        "cogs_pct": float(sb.cogs_pct), "cogs_method": sb.cogs_method, "status": sb.status.value,
    }


@app.put("/budget-years/{budget_year_id}/sales/{branch_id}")
def upsert_sales_budget(budget_year_id: str, branch_id: str, payload: SalesBudgetIn,
                         db: Session = Depends(get_db), current_user: m.User = Depends(get_current_user)):
    by = db.query(m.BudgetYear).filter_by(id=budget_year_id).first()
    if not by:
        raise HTTPException(status_code=404, detail="Budget year not found")
    link = db.query(m.UserCompany).filter_by(user_id=current_user.id, company_id=by.company_id).first()
    if not link or not (link.can_edit or link.role in ("admin", "gm")):
        raise HTTPException(status_code=403, detail="ليس لديك صلاحية التعديل على هذه البيانات")

    sb = db.query(m.SalesBudget).filter_by(budget_year_id=budget_year_id, branch_id=branch_id).first()
    if not sb:
        sb = m.SalesBudget(budget_year_id=budget_year_id, branch_id=branch_id)
        db.add(sb)
    for field, value in payload.dict().items():
        setattr(sb, field, value)
    db.commit()
    db.refresh(sb)

    db.add(m.AuditLog(user_id=current_user.id, action="update", entity_type="sales_budget", entity_id=sb.id))
    db.commit()
    return {"status": "ok", "id": sb.id}


# ============================================================================
# DECISIONS
# ============================================================================

@app.get("/decisions")
def list_decisions(company_id: Optional[str] = None, db: Session = Depends(get_db),
                    current_user: m.User = Depends(get_current_user)):
    q = db.query(m.Decision)
    if company_id:
        q = q.filter(m.Decision.company_id == company_id)
    decisions = q.all()
    return [{"id": d.id, "title": d.title, "status": d.status.value, "owner_name": d.owner_name_freetext} for d in decisions]


@app.get("/decisions/{decision_id}")
def get_decision(decision_id: str, db: Session = Depends(get_db), current_user: m.User = Depends(get_current_user)):
    d = db.query(m.Decision).filter(m.Decision.id == decision_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Not found")
    sections = []
    for s in sorted(d.sections, key=lambda x: x.sort_order):
        c = s.content
        sections.append({
            "key": s.key, "label": s.label, "icon": s.icon, "weight": float(s.weight),
            "content": {
                "status": c.status.value if c else "todo",
                "text": c.body_text if c else "",
                "conclusion": c.conclusion if c else "",
                "recommendation": c.recommendation if c else "",
                "data": c.structured_data if c else {},
                "criteria": [
                    {"name": cr.name, "weight": float(cr.weight), "actual": float(cr.actual_score), "target": float(cr.target_score)}
                    for cr in (c.criteria if c else [])
                ],
            } if c else None,
        })
    return {
        "id": d.id, "title": d.title, "description": d.description,
        "owner_name": d.owner_name_freetext, "status": d.status.value, "sections": sections,
    }


@app.get("/")
def root():
    return {"status": "ok", "service": "budget-planning-api"}


# ============================================================================
# ONE-TIME SEED (browser-triggerable, no CLI needed)
# Visit https://<your-backend-url>/admin/seed?key=<SEED_KEY> once after first
# deploy to populate default company/users/decision data. Safe to re-visit —
# it checks whether seeding already happened and skips if so.
# ============================================================================

SEED_KEY = os.getenv("SEED_KEY", "change-me-seed-key")


@app.get("/admin/seed")
def run_seed(key: str, db: Session = Depends(get_db)):
    if key != SEED_KEY:
        raise HTTPException(status_code=403, detail="Invalid seed key")
    # Already seeded? Don't re-run or leak whether seeding is possible again.
    existing = db.query(m.Company).filter_by(name="شركة لاروش التجارية").first()
    if existing:
        return {"status": "already_seeded", "message": "تم إعداد البيانات مسبقاً. لا حاجة لتكرار هذا."}
    import seed as seed_module
    try:
        seed_module.run()
        return {"status": "ok", "message": "Seed completed. IMPORTANT: change default passwords now via /auth/change-password, then remove/rotate SEED_KEY."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/admin/emergency-unlock")
def emergency_unlock(key: str, username: str, db: Session = Depends(get_db)):
    # Escape hatch for accidental lockouts (e.g. an admin account getting
    # deactivated). Protected by the same SEED_KEY. Re-activates the given
    # backend login account.
    if key != SEED_KEY:
        raise HTTPException(status_code=403, detail="Invalid key")
    target = db.query(m.User).filter_by(username=username).first()
    if not target:
        raise HTTPException(status_code=404, detail=f"No login account found for username '{username}'")
    target.active = True
    db.commit()
    return {"status": "ok", "message": f"User '{username}' reactivated."}


@app.get("/admin/emergency-reset-password")
def emergency_reset_password(key: str, username: str, new_password: str, db: Session = Depends(get_db)):
    # Same idea as emergency-unlock, but resets the password directly — for
    # total lockouts where the password itself is the problem, not just the
    # active flag. Protected by SEED_KEY only (no login needed, since the
    # whole point is you can't log in).
    if key != SEED_KEY:
        raise HTTPException(status_code=403, detail="Invalid key")
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    target = db.query(m.User).filter_by(username=username).first()
    if not target:
        raise HTTPException(status_code=404, detail=f"No login account found for username '{username}'")
    target.active = True
    target.password_hash = hash_password(new_password)
    db.commit()
    return {"status": "ok", "message": f"Password for '{username}' reset and account reactivated."}


# ============================================================================
# APP STATE (full-blob sync — see AppState model docstring in models.py)
# This is what the original HTML app's load()/save() now call instead of
# localStorage.getItem/setItem.
# ============================================================================

STATE_KEY = "main"


@app.get("/state")
def get_state(db: Session = Depends(get_db), current_user: m.User = Depends(get_current_user)):
    state = db.query(m.AppState).filter_by(key=STATE_KEY).first()
    if not state:
        return {"data": None, "version": None}
    return {"data": state.data, "version": state.updated_at.isoformat() if state.updated_at else None}


@app.put("/state")
def put_state(payload: dict = Body(...), expected_version: Optional[str] = None,
              db: Session = Depends(get_db), current_user: m.User = Depends(get_current_user)):
    state = db.query(m.AppState).filter_by(key=STATE_KEY).first()
    if not state:
        state = m.AppState(key=STATE_KEY, data=payload, updated_by=current_user.id)
        db.add(state)
    else:
        # Optimistic concurrency: if the caller knows what version they last read,
        # and the server has moved on since then, someone else saved in between —
        # reject instead of silently overwriting their change.
        current_version = state.updated_at.isoformat() if state.updated_at else None
        if expected_version and current_version and expected_version != current_version:
            raise HTTPException(
                status_code=409,
                detail="تم تعديل البيانات من جهاز آخر منذ آخر تحميل. أعد تحميل الصفحة قبل الحفظ.",
            )
        state.data = payload
        state.updated_by = current_user.id
    db.commit()
    db.refresh(state)
    return {"status": "ok", "version": state.updated_at.isoformat() if state.updated_at else None}


@app.post("/state/beacon")
async def put_state_beacon(request: Request, token_qs: Optional[str] = None, db: Session = Depends(get_db)):
    # navigator.sendBeacon only supports POST and can't set custom headers, so the
    # frontend calls this endpoint (with the token as a query param) as a
    # best-effort save when the tab is closing. No conflict check here — this is
    # a last-resort flush, not the primary save path.
    if not token_qs:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload_obj = decode_access_token(token_qs)
        user_id = payload_obj.get("sub")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(m.User).filter(m.User.id == user_id, m.User.active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    body = await request.json()
    state = db.query(m.AppState).filter_by(key=STATE_KEY).first()
    if not state:
        state = m.AppState(key=STATE_KEY, data=body, updated_by=user.id)
        db.add(state)
    else:
        state.data = body
        state.updated_by = user.id
    db.commit()
    return {"status": "ok"}
