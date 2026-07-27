import os
from fastapi import FastAPI, Depends, HTTPException, status, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from . import models as m
from .database import get_db, engine, Base
from .auth import verify_password, create_access_token, decode_access_token

app = FastAPI(title="نظام الموازنات التقديرية والتخطيط المالي — API")

# In production, replace "*" with your actual Netlify domain(s).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


@app.on_event("startup")
def on_startup():
    # In production prefer Alembic migrations over create_all.
    Base.metadata.create_all(bind=engine)


# ============================================================================
# AUTH
# ============================================================================

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> m.User:
    try:
        payload = decode_access_token(token)
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
    # NOTE: add RBAC check here — e.g. verify current_user's UserCompany.can_edit
    # is True for this budget_year's company before allowing writes.
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
    import seed as seed_module
    try:
        seed_module.run()
        return {"status": "ok", "message": "Seed completed (or already existed — check details below)."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


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
        return {"data": None}
    return {"data": state.data, "updated_at": state.updated_at.isoformat() if state.updated_at else None}


@app.put("/state")
def put_state(payload: dict = Body(...), db: Session = Depends(get_db),
              current_user: m.User = Depends(get_current_user)):
    state = db.query(m.AppState).filter_by(key=STATE_KEY).first()
    if not state:
        state = m.AppState(key=STATE_KEY, data=payload, updated_by=current_user.id)
        db.add(state)
    else:
        state.data = payload
        state.updated_by = current_user.id
    db.commit()
    return {"status": "ok"}
