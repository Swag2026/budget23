# نظام الموازنات التقديرية — Backend

Tested end-to-end locally (login → data fetch → decision detail with full
merger case-study content). Ready to deploy to Railway.

## Local setup

```bash
pip install -r requirements.txt
cp .env.example .env   # then edit DATABASE_URL / JWT_SECRET
export DATABASE_URL="postgresql://user:pass@localhost:5432/budget_db"

# Creates tables + inserts the exact default data from the original HTML app
python seed.py

# Run the API
uvicorn app.main:app --reload
```

Then open http://localhost:8000/docs for interactive API testing (Swagger UI).

## Default users (same as original app, now bcrypt-hashed)

| username | password  | role    |
|----------|-----------|---------|
| admin    | admin123  | admin   |
| gm       | gm123     | gm      |
| finance  | fin123    | finance |
| sales    | sales123  | staff (sales section) |
| hr       | hr123     | staff (hr section) |

**Change these before going to production.**

## Deploying to Railway

1. Push this folder to a GitHub repo (or a `backend/` folder in your monorepo).
2. In Railway: New Project → Deploy from GitHub → select repo.
3. Add a PostgreSQL plugin — Railway auto-injects `DATABASE_URL`.
4. Add environment variable `JWT_SECRET` (long random string).
5. Set the start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
6. After first deploy, run `python seed.py` once (Railway's shell / a one-off job) to populate default data.

## What's implemented vs. what's a starting point

**Implemented and tested:**
- Full schema (30 tables) as SQLAlchemy models
- bcrypt password hashing + JWT login (`/auth/login`)
- Seed script with the exact original data: company, 3 branches, 5 categories,
  5 users, 6-department org chart, and the full merger decision case study
  (all financial/market/HR/legal/strategic/ops content + weighted criteria)
- Working endpoints: login, list companies, list branches, get/update sales
  budget, list/get decisions

**Starting point — extend following the same pattern:**
- HR/marketing/opex/inventory/general budget endpoints (copy the sales
  budget GET/PUT pair in `main.py` and swap the model)
- Actuals endpoints (monthly_actuals, bs_actuals)
- Strategy module endpoints (objectives, initiatives, OKRs, risks, stakeholders)
- RBAC enforcement in endpoints (the `UserCompany.can_edit` etc. flags exist
  in the schema — endpoints need to check them; noted with a comment in
  `upsert_sales_budget`)
- Attachments → S3/object storage upload endpoint
- Audit log write on every mutating endpoint (pattern shown in `upsert_sales_budget`)

## Note on sales weights (seasonalWeights)

The original app computes monthly sales weights from the Islamic (Hijri)
calendar at runtime — Ramadan/Eid boosts, winter/summer adjustments, etc.
That's a *formula*, not stored data, so `seed.py` inserts equal placeholder
weights. Port the `seasonalWeights(year)` JS logic into Python (or keep it
client-side in the React frontend) rather than freezing one year's computed
output into the database.
