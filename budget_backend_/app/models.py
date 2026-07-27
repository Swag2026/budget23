import uuid
import enum
from sqlalchemy import (
    Column, String, Integer, Numeric, Boolean, TIMESTAMP, ForeignKey,
    SmallInteger, BigInteger, CheckConstraint, UniqueConstraint, Text, Enum
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base


def gen_uuid():
    return str(uuid.uuid4())


class UserRole(str, enum.Enum):
    admin = "admin"
    gm = "gm"
    finance = "finance"
    staff = "staff"


class BudgetStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"


class DecisionStatus(str, enum.Enum):
    draft = "draft"
    inprogress = "inprogress"
    done = "done"
    archived = "archived"


class SectionStatus(str, enum.Enum):
    todo = "todo"
    inprogress = "inprogress"
    done = "done"


# ============================================================================
# CORE
# ============================================================================

class Company(Base):
    __tablename__ = "companies"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False)
    currency = Column(String(10), nullable=False, default="ر.س")
    vat_pct = Column(Numeric(5, 2), nullable=False, default=15.00)
    sales_vat_incl = Column(Boolean, nullable=False, default=False)
    purch_vat_incl = Column(Boolean, nullable=False, default=False)
    min_cash = Column(Numeric(18, 2), nullable=False, default=0)
    expense_dist = Column(String(20), nullable=False, default="even")
    active_year = Column(Integer)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    branches = relationship("Branch", back_populates="company", cascade="all, delete-orphan")
    item_categories = relationship("ItemCategory", back_populates="company", cascade="all, delete-orphan")
    budget_years = relationship("BudgetYear", back_populates="company", cascade="all, delete-orphan")
    strategy = relationship("Strategy", back_populates="company", uselist=False, cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    username = Column(String(100), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)  # bcrypt
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    last_login_at = Column(TIMESTAMP(timezone=True))

    company_links = relationship("UserCompany", back_populates="user", cascade="all, delete-orphan")


class Branch(Base):
    __tablename__ = "branches"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id = Column(UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)

    company = relationship("Company", back_populates="branches")


class UserCompany(Base):
    __tablename__ = "user_companies"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    company_id = Column(UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    role = Column(Enum(UserRole, name="user_role"), nullable=False, default=UserRole.staff)
    branch_id = Column(UUID(as_uuid=False), ForeignKey("branches.id", ondelete="SET NULL"))
    sections = Column(ARRAY(String), nullable=False, default=list)

    can_edit = Column(Boolean, nullable=False, default=False)
    can_template = Column(Boolean, nullable=False, default=False)
    can_import = Column(Boolean, nullable=False, default=False)
    can_export = Column(Boolean, nullable=False, default=False)
    can_print = Column(Boolean, nullable=False, default=False)
    can_approve = Column(Boolean, nullable=False, default=False)
    can_unapprove = Column(Boolean, nullable=False, default=False)
    can_view_actual = Column(Boolean, nullable=False, default=False)
    can_daily_actual = Column(Boolean, nullable=False, default=False)
    can_backup_export = Column(Boolean, nullable=False, default=False)
    can_backup_import = Column(Boolean, nullable=False, default=False)
    can_add_company = Column(Boolean, nullable=False, default=False)
    can_delete_year = Column(Boolean, nullable=False, default=False)
    can_fin_consolidated = Column(Boolean, nullable=False, default=False)
    can_fin_actual = Column(Boolean, nullable=False, default=False)

    user = relationship("User", back_populates="company_links")
    company = relationship("Company")
    branch = relationship("Branch")

    __table_args__ = (UniqueConstraint("user_id", "company_id"),)


class ItemCategory(Base):
    __tablename__ = "item_categories"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id = Column(UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    icon = Column(String(10))
    sort_order = Column(Integer, nullable=False, default=0)

    company = relationship("Company", back_populates="item_categories")


# Org structure: department -> roles -> tasks (matches original defaultOrgStructure()
# shape exactly, rather than a generic tree — departments hold roles directly)
class OrgDepartment(Base):
    __tablename__ = "org_departments"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id = Column(UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)

    roles = relationship("OrgRole", back_populates="department", cascade="all, delete-orphan")


class OrgRole(Base):
    __tablename__ = "org_roles"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    department_id = Column(UUID(as_uuid=False), ForeignKey("org_departments.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, default="")
    tasks = Column(ARRAY(String), nullable=False, default=list)
    sort_order = Column(Integer, nullable=False, default=0)

    department = relationship("OrgDepartment", back_populates="roles")


# ============================================================================
# BUDGET YEARS + MODULES
# ============================================================================

class BudgetYear(Base):
    __tablename__ = "budget_years"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id = Column(UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    year = Column(Integer, nullable=False)
    is_active = Column(Boolean, nullable=False, default=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    company = relationship("Company", back_populates="budget_years")
    __table_args__ = (UniqueConstraint("company_id", "year"),)


class SalesBudget(Base):
    __tablename__ = "sales_budgets"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    budget_year_id = Column(UUID(as_uuid=False), ForeignKey("budget_years.id", ondelete="CASCADE"), nullable=False)
    branch_id = Column(UUID(as_uuid=False), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    weights = Column(JSONB, nullable=False, default=dict)   # 12 monthly seasonal weights
    month_mode = Column(String(10), nullable=False, default="weight")
    prev_year_sales = Column(Numeric(18, 2), nullable=False, default=0)
    growth_pct = Column(Numeric(6, 2), nullable=False, default=0)
    avg_invoice = Column(Numeric(18, 2), nullable=False, default=0)
    customers_count = Column(Integer, nullable=False, default=0)
    cogs_pct = Column(Numeric(6, 2), nullable=False, default=60)
    cogs_method = Column(String(10), nullable=False, default="pct")
    status = Column(Enum(BudgetStatus, name="budget_status"), nullable=False, default=BudgetStatus.draft)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (UniqueConstraint("budget_year_id", "branch_id"),)


class HRBudget(Base):
    __tablename__ = "hr_budgets"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    budget_year_id = Column(UUID(as_uuid=False), ForeignKey("budget_years.id", ondelete="CASCADE"), nullable=False)
    branch_id = Column(UUID(as_uuid=False), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    staff_now = Column(Integer, nullable=False, default=0)
    staff_next = Column(Integer, nullable=False, default=0)
    salaries = Column(Numeric(18, 2), nullable=False, default=0)
    commissions = Column(Numeric(18, 2), nullable=False, default=0)
    bonuses = Column(Numeric(18, 2), nullable=False, default=0)
    housing = Column(Numeric(18, 2), nullable=False, default=0)
    iqama_fees = Column(Numeric(18, 2), nullable=False, default=0)
    insurance = Column(Numeric(18, 2), nullable=False, default=0)
    training = Column(Numeric(18, 2), nullable=False, default=0)
    __table_args__ = (UniqueConstraint("budget_year_id", "branch_id"),)


class MarketingBudget(Base):
    __tablename__ = "marketing_budgets"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    budget_year_id = Column(UUID(as_uuid=False), ForeignKey("budget_years.id", ondelete="CASCADE"), nullable=False)
    branch_id = Column(UUID(as_uuid=False), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    campaigns = Column(Numeric(18, 2), nullable=False, default=0)
    digital = Column(Numeric(18, 2), nullable=False, default=0)
    influencers = Column(Numeric(18, 2), nullable=False, default=0)
    billboards = Column(Numeric(18, 2), nullable=False, default=0)
    events = Column(Numeric(18, 2), nullable=False, default=0)
    __table_args__ = (UniqueConstraint("budget_year_id", "branch_id"),)


class OpexBudget(Base):
    __tablename__ = "opex_budgets"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    budget_year_id = Column(UUID(as_uuid=False), ForeignKey("budget_years.id", ondelete="CASCADE"), nullable=False)
    branch_id = Column(UUID(as_uuid=False), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    rent = Column(Numeric(18, 2), nullable=False, default=0)
    electricity = Column(Numeric(18, 2), nullable=False, default=0)
    internet = Column(Numeric(18, 2), nullable=False, default=0)
    maintenance = Column(Numeric(18, 2), nullable=False, default=0)
    transport = Column(Numeric(18, 2), nullable=False, default=0)
    hospitality = Column(Numeric(18, 2), nullable=False, default=0)
    office = Column(Numeric(18, 2), nullable=False, default=0)
    gov_fees = Column(Numeric(18, 2), nullable=False, default=0)
    __table_args__ = (UniqueConstraint("budget_year_id", "branch_id"),)


class InventoryBudget(Base):
    __tablename__ = "inventory_budgets"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    budget_year_id = Column(UUID(as_uuid=False), ForeignKey("budget_years.id", ondelete="CASCADE"), nullable=False)
    branch_id = Column(UUID(as_uuid=False), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    opening = Column(Numeric(18, 2), nullable=False, default=0)
    purchases = Column(Numeric(18, 2), nullable=False, default=0)
    ending = Column(Numeric(18, 2), nullable=False, default=0)
    __table_args__ = (UniqueConstraint("budget_year_id", "branch_id"),)


class GeneralBudget(Base):
    __tablename__ = "general_budgets"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    budget_year_id = Column(UUID(as_uuid=False), ForeignKey("budget_years.id", ondelete="CASCADE"), nullable=False, unique=True)
    ga = Column(Numeric(18, 2), nullable=False, default=0)
    financing = Column(Numeric(18, 2), nullable=False, default=0)
    provisions = Column(Numeric(18, 2), nullable=False, default=0)
    zakat_pct = Column(Numeric(5, 2), nullable=False, default=2.5)
    capex = Column(Numeric(18, 2), nullable=False, default=0)
    financing_cf = Column(Numeric(18, 2), nullable=False, default=0)
    target_net_margin = Column(Numeric(6, 2), nullable=False, default=0)
    cash_open = Column(Numeric(18, 2), nullable=False, default=0)
    receivables = Column(Numeric(18, 2), nullable=False, default=0)
    payables = Column(Numeric(18, 2), nullable=False, default=0)
    other_liabilities = Column(Numeric(18, 2), nullable=False, default=0)
    equity = Column(Numeric(18, 2), nullable=False, default=0)
    scenario_low_pct = Column(Numeric(6, 2), nullable=False, default=-10)
    scenario_base_pct = Column(Numeric(6, 2), nullable=False, default=0)
    scenario_high_pct = Column(Numeric(6, 2), nullable=False, default=15)


class BSItem(Base):
    __tablename__ = "bs_items"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id = Column(UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    parent_id = Column(UUID(as_uuid=False), ForeignKey("bs_items.id", ondelete="CASCADE"))
    label = Column(String(255), nullable=False)
    sign = Column(String(1), nullable=False, default="+")
    is_group = Column(Boolean, nullable=False, default=False)
    statement_side = Column(String(10), nullable=False, default="assets")  # 'assets' | 'liabilities'
    sort_order = Column(Integer, nullable=False, default=0)


class CustomFieldDef(Base):
    __tablename__ = "custom_field_defs"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id = Column(UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    module = Column(String(20), nullable=False)  # hr|marketing|opex|inventory|general
    field_key = Column(String(100), nullable=False)
    label = Column(String(255), nullable=False)
    field_type = Column(String(20), nullable=False, default="number")
    sort_order = Column(Integer, nullable=False, default=0)


class CustomFieldValue(Base):
    __tablename__ = "custom_field_values"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    custom_field_def_id = Column(UUID(as_uuid=False), ForeignKey("custom_field_defs.id", ondelete="CASCADE"), nullable=False)
    budget_year_id = Column(UUID(as_uuid=False), ForeignKey("budget_years.id", ondelete="CASCADE"), nullable=False)
    branch_id = Column(UUID(as_uuid=False), ForeignKey("branches.id", ondelete="CASCADE"))
    value = Column(Numeric(18, 2), nullable=False, default=0)
    __table_args__ = (UniqueConstraint("custom_field_def_id", "budget_year_id", "branch_id"),)


# ============================================================================
# ACTUALS
# ============================================================================

class MonthlyActual(Base):
    __tablename__ = "monthly_actuals"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    budget_year_id = Column(UUID(as_uuid=False), ForeignKey("budget_years.id", ondelete="CASCADE"), nullable=False)
    branch_id = Column(UUID(as_uuid=False), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    month = Column(SmallInteger, nullable=False)
    sales = Column(Numeric(18, 2), nullable=False, default=0)
    cogs = Column(Numeric(18, 2), nullable=False, default=0)
    hr = Column(Numeric(18, 2), nullable=False, default=0)
    marketing = Column(Numeric(18, 2), nullable=False, default=0)
    opex = Column(Numeric(18, 2), nullable=False, default=0)
    entered_by = Column(UUID(as_uuid=False), ForeignKey("users.id"))
    entered_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    __table_args__ = (
        CheckConstraint("month BETWEEN 1 AND 12"),
        UniqueConstraint("budget_year_id", "branch_id", "month"),
    )


class BSActual(Base):
    __tablename__ = "bs_actuals"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    budget_year_id = Column(UUID(as_uuid=False), ForeignKey("budget_years.id", ondelete="CASCADE"), nullable=False)
    branch_id = Column(UUID(as_uuid=False), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    bs_item_id = Column(UUID(as_uuid=False), ForeignKey("bs_items.id", ondelete="CASCADE"), nullable=False)
    value = Column(Numeric(18, 2), nullable=False, default=0)
    __table_args__ = (UniqueConstraint("budget_year_id", "branch_id", "bs_item_id"),)


# ============================================================================
# STRATEGY
# ============================================================================

class Strategy(Base):
    __tablename__ = "strategies"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id = Column(UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, unique=True)
    vision = Column(Text, nullable=False, default="")
    mission = Column(Text, nullable=False, default="")
    core_values = Column(Text, nullable=False, default="")
    bhag = Column(Text, nullable=False, default="")
    horizon_from = Column(Integer)
    horizon_to = Column(Integer)
    swot = Column(JSONB, nullable=False, default=dict)
    pestel = Column(JSONB, nullable=False, default=dict)
    tows = Column(JSONB, nullable=False, default=dict)
    ansoff = Column(JSONB, nullable=False, default=dict)
    porter = Column(JSONB, nullable=False, default=dict)
    governance_cadence = Column(String(50), default="ربع سنوي")
    governance_assumptions = Column(Text, default="")
    governance_owner = Column(String(255), default="")

    company = relationship("Company", back_populates="strategy")
    objectives = relationship("StrategicObjective", back_populates="strategy", cascade="all, delete-orphan")


class StrategicObjective(Base):
    __tablename__ = "strategic_objectives"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    strategy_id = Column(UUID(as_uuid=False), ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(500), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)

    strategy = relationship("Strategy", back_populates="objectives")
    initiatives = relationship("StrategicInitiative", back_populates="objective", cascade="all, delete-orphan")


class StrategicInitiative(Base):
    __tablename__ = "strategic_initiatives"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    objective_id = Column(UUID(as_uuid=False), ForeignKey("strategic_objectives.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(500), nullable=False)
    impact = Column(SmallInteger, nullable=False, default=3)
    confidence = Column(SmallInteger, nullable=False, default=3)
    effort = Column(SmallInteger, nullable=False, default=3)

    objective = relationship("StrategicObjective", back_populates="initiatives")


class OKR(Base):
    __tablename__ = "okrs"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    strategy_id = Column(UUID(as_uuid=False), ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False)
    objective_title = Column(String(500), nullable=False)
    key_results = Column(JSONB, nullable=False, default=list)


class StrategicRisk(Base):
    __tablename__ = "strategic_risks"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    strategy_id = Column(UUID(as_uuid=False), ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(500), nullable=False)
    likelihood = Column(SmallInteger)
    impact = Column(SmallInteger)
    mitigation = Column(Text)


class Stakeholder(Base):
    __tablename__ = "stakeholders"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    strategy_id = Column(UUID(as_uuid=False), ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    influence = Column(SmallInteger)
    interest = Column(SmallInteger)
    notes = Column(Text)


# ============================================================================
# DECISIONS
# ============================================================================

class Decision(Base):
    __tablename__ = "decisions"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id = Column(UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"))
    title = Column(String(500), nullable=False)
    description = Column(Text)
    owner_user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"))
    owner_name_freetext = Column(String(255))
    status = Column(Enum(DecisionStatus, name="decision_status"), nullable=False, default=DecisionStatus.draft)
    final_text = Column(Text, default="")
    final_outcome = Column(String(50), default="")
    decided_by = Column(String(255), default="")
    decided_at = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    sections = relationship("DecisionSection", back_populates="decision", cascade="all, delete-orphan")


class DecisionSection(Base):
    __tablename__ = "decision_sections"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    decision_id = Column(UUID(as_uuid=False), ForeignKey("decisions.id", ondelete="CASCADE"), nullable=False)
    key = Column(String(50), nullable=False)
    label = Column(String(255), nullable=False)
    icon = Column(String(10))
    weight = Column(Numeric(5, 2), nullable=False, default=0)
    sort_order = Column(Integer, nullable=False, default=0)

    decision = relationship("Decision", back_populates="sections")
    content = relationship("DecisionContent", back_populates="section", uselist=False, cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("decision_id", "key"),)


class DecisionContent(Base):
    __tablename__ = "decision_content"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    decision_section_id = Column(UUID(as_uuid=False), ForeignKey("decision_sections.id", ondelete="CASCADE"), nullable=False, unique=True)
    status = Column(Enum(SectionStatus, name="section_status"), nullable=False, default=SectionStatus.todo)
    body_text = Column(Text, default="")
    conclusion = Column(Text, default="")
    recommendation = Column(String(50), default="")  # support|conditional|oppose
    owner_user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"))
    structured_data = Column(JSONB, nullable=False, default=dict)  # section-specific tables (financial rows, market TAM/SAM/SOM, hr rows, legal rows, ops numbers...)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    section = relationship("DecisionSection", back_populates="content")
    criteria = relationship("DecisionCriteria", back_populates="content", cascade="all, delete-orphan")


class DecisionCriteria(Base):
    __tablename__ = "decision_criteria"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    decision_content_id = Column(UUID(as_uuid=False), ForeignKey("decision_content.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    weight = Column(Numeric(5, 2), nullable=False, default=0)
    actual_score = Column(Numeric(5, 2), nullable=False, default=0)
    target_score = Column(Numeric(5, 2), nullable=False, default=100)
    sort_order = Column(Integer, nullable=False, default=0)

    content = relationship("DecisionContent", back_populates="criteria")


# ============================================================================
# ATTACHMENTS + AUDIT
# ============================================================================

class Attachment(Base):
    __tablename__ = "attachments"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id = Column(UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    decision_id = Column(UUID(as_uuid=False), ForeignKey("decisions.id", ondelete="CASCADE"))
    filename = Column(String(500), nullable=False)
    storage_url = Column(Text, nullable=False)
    mime_type = Column(String(100))
    size_bytes = Column(BigInteger)
    uploaded_by = Column(UUID(as_uuid=False), ForeignKey("users.id"))
    uploaded_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"))
    company_id = Column(UUID(as_uuid=False), ForeignKey("companies.id"))
    action = Column(String(50), nullable=False)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(UUID(as_uuid=False))
    diff = Column(JSONB)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
