"""
TaxFlow Cost Seg — client portal
Cost segregation estimates and studies + property management (residents, rent, maintenance, contractors).

Run locally:   streamlit run app.py
Deploy:        Streamlit Community Cloud (add requirements.txt and .streamlit/config.toml)

Secrets (Streamlit Cloud > App settings > Secrets), all optional except where noted:
    RESEND_API_KEY      = "re_..."                      # sign-in codes + notifications
    EMAIL_FROM          = "TaxFlow Cost Seg <info@taxflowcostseg.com>"   # verified Resend domain
    GOOGLE_MAPS_API_KEY = "AIza..."                     # Maps JavaScript API + Places API (New)
    RENTCAST_API_KEY    = "..."                         # property records: sale price/date, sq ft, year built
    DATABASE_URL        = "postgresql://..."            # recommended (e.g. Supabase). Falls back to local SQLite.
    ADMIN_EMAILS        = "you@taxflowcostseg.com"      # comma-separated; these emails get the management console
    APP_URL             = "https://taxflowcostseg.com"  # used in email links
    EMERGENCY_PHONE     = "(xxx) xxx-xxxx"              # shown to residents
    PAYMENT_INSTRUCTIONS = "Pay by Zelle to ..."        # shown to residents
    RENT_PAYMENT_LINK   = "https://..."                 # optional online rent payment link
    PAYMENT_LINK_DETAILED / PAYMENT_LINK_VIRTUAL / PAYMENT_LINK_ONSITE = "https://buy.stripe.com/..."  # optional
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import html as html_lib
import io
import os
import re
import secrets as pysecrets
import time
import uuid

import altair as alt
import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from sqlalchemy import create_engine, text

st.set_page_config(
    page_title="TaxFlow Cost Seg",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="collapsed",
)

APP_DIR = os.path.dirname(os.path.abspath(__file__))
TODAY = dt.date.today()

# ============================================================================
# BUSINESS CONFIG — edit copy, contact info and pricing here
# ============================================================================
BRAND = {
    "name": "TaxFlow Cost Seg",
    "email": "info@taxflowcostseg.com",
    "phone": "(202) 810-1684",
    "video_url": "https://youtu.be/O2Icd-i_Ixw",
    "trust_line": "Engineer-led studies for residential and commercial owners, nationwide",
}

TIERS = [
    {"id": "quick", "name": "Quick Estimate", "price": 0, "audit": False,
     "desc": "Instant estimate from public records and your purchase details.", "link_secret": None},
    {"id": "detailed", "name": "Detailed Analysis", "price": 495, "audit": False,
     "desc": "Engineer-reviewed study built from your closing statement, photos and plans, with schedules your CPA can file.",
     "link_secret": "PAYMENT_LINK_DETAILED"},
    {"id": "virtual", "name": "Virtual Engineer Tour", "price": 997, "audit": True,
     "desc": "A live video walkthrough with an engineer for a finer component breakdown. Includes audit assistance.",
     "link_secret": "PAYMENT_LINK_VIRTUAL"},
    {"id": "onsite", "name": "Full On-Site Assessment", "price": 1997, "audit": True,
     "desc": "An engineer inspects the property in person. Best for larger or complex buildings. Includes audit assistance.",
     "link_secret": "PAYMENT_LINK_ONSITE"},
]
TIER_BY_NAME = {t["name"]: t for t in TIERS}

STUDY_FLOW = ["Estimate", "Submitted", "Documents received", "Engineering review", "Report delivered"]
WO_STATUSES = ["New", "Assigned", "In progress", "Completed", "Closed"]
WO_OPEN = ["New", "Assigned", "In progress"]
WO_PRIORITIES = ["Emergency", "Urgent", "Routine", "Low"]
WO_CATEGORIES = ["Plumbing", "Heating & AC", "Electrical", "Appliance", "Roof & exterior",
                 "Doors, windows & locks", "Pests", "Landscaping", "Other"]
PAY_METHODS = ["Zelle", "ACH / bank transfer", "Check", "Cash", "Card", "Other"]

# ============================================================================
# SMALL HELPERS
# ============================================================================
def secret(name: str, default=None):
    """Read from Streamlit secrets, then environment variables."""
    try:
        val = st.secrets.get(name)
        if val not in (None, ""):
            return val
    except Exception:
        pass
    return os.environ.get(name, default)


def admin_emails() -> set[str]:
    raw = secret("ADMIN_EMAILS", "") or ""
    items = raw if isinstance(raw, (list, tuple)) else str(raw).split(",")
    return {str(e).strip().lower() for e in items if str(e).strip()}


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def money(x, dash="—") -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return dash
    return f"-${abs(x):,.0f}" if x < 0 else f"${x:,.0f}"


def esc(s) -> str:
    return html_lib.escape(str(s if s is not None else ""))


def parse_date(s):
    if not s:
        return None
    if isinstance(s, dt.date):
        return s
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def fmt_date(s) -> str:
    d = parse_date(s)
    return f"{d:%b} {d.day}, {d.year}" if d else "—"


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_email(e: str) -> bool:
    return bool(e and EMAIL_RE.match(e.strip()))


def period_label(p: str) -> str:
    return dt.datetime.strptime(p, "%Y-%m").strftime("%B %Y")


def recent_periods(n=12) -> list[str]:
    out, y, m = [], TODAY.year, TODAY.month
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


# ============================================================================
# STORAGE (Postgres via DATABASE_URL, otherwise local SQLite)
# ============================================================================
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS users (email TEXT PRIMARY KEY, name TEXT, created_at TEXT, last_login TEXT)""",
    """CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, email TEXT, expires_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS studies (
        id TEXT PRIMARY KEY, owner_email TEXT, address TEXT, property_type TEXT,
        purchase_price REAL, closing_costs REAL, improvements REAL, land_pct REAL,
        acquired_on TEXT, in_service_on TEXT, sqft INTEGER, year_built INTEGER,
        tax_rate REAL, bonus_mode TEXT, tier TEXT, status TEXT, notes TEXT,
        created_at TEXT, updated_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY, parent_type TEXT, parent_id TEXT, kind TEXT, filename TEXT,
        mime TEXT, size INTEGER, data {blob}, uploaded_by TEXT, uploaded_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS properties (
        id TEXT PRIMARY KEY, name TEXT, address TEXT, property_type TEXT, notes TEXT, created_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS units (
        id TEXT PRIMARY KEY, property_id TEXT, label TEXT, beds REAL, baths REAL,
        market_rent REAL, created_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS tenants (
        id TEXT PRIMARY KEY, email TEXT, name TEXT, phone TEXT, unit_id TEXT,
        lease_start TEXT, lease_end TEXT, rent REAL, deposit REAL, due_day INTEGER,
        status TEXT, created_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS payments (
        id TEXT PRIMARY KEY, tenant_id TEXT, period TEXT, amount REAL, paid_on TEXT,
        method TEXT, note TEXT, created_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS contractors (
        id TEXT PRIMARY KEY, email TEXT, name TEXT, company TEXT, trade TEXT, phone TEXT, created_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS work_orders (
        id TEXT PRIMARY KEY, unit_id TEXT, tenant_id TEXT, category TEXT, priority TEXT,
        description TEXT, access_notes TEXT, status TEXT, contractor_id TEXT, cost REAL,
        notes TEXT, created_at TEXT, updated_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS leads (
        id TEXT PRIMARY KEY, email TEXT, address TEXT, purchase_price REAL,
        est_deduction REAL, est_savings REAL, created_at TEXT)""",
]


@st.cache_resource(show_spinner=False)
def get_engine():
    url = secret("DATABASE_URL") or "sqlite:///" + os.path.join(APP_DIR, "taxflow.db")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    kwargs = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    eng = create_engine(url, **kwargs)
    blob = "BYTEA" if eng.dialect.name == "postgresql" else "BLOB"
    real = " DOUBLE PRECISION" if eng.dialect.name == "postgresql" else " REAL"
    with eng.begin() as conn:
        for ddl in SCHEMA:
            conn.execute(text(ddl.replace("{blob}", blob).replace(" REAL", real)))
    return eng


def db_all(sql: str, **params) -> list[dict]:
    with get_engine().connect() as conn:
        return [dict(r._mapping) for r in conn.execute(text(sql), params)]


def db_one(sql: str, **params):
    rows = db_all(sql, **params)
    return rows[0] if rows else None


def db_exec(sql: str, **params) -> None:
    with get_engine().begin() as conn:
        conn.execute(text(sql), params)


def is_sqlite() -> bool:
    return get_engine().dialect.name == "sqlite"


def save_document(parent_type, parent_id, kind, uploaded_file, uploaded_by) -> bool:
    data = uploaded_file.getvalue()
    if len(data) > 15 * 1024 * 1024:
        st.error(f"{uploaded_file.name} is larger than 15 MB. Compress it or split it and upload again.")
        return False
    db_exec(
        """INSERT INTO documents (id, parent_type, parent_id, kind, filename, mime, size, data, uploaded_by, uploaded_at)
           VALUES (:id, :pt, :pid, :kind, :fn, :mime, :size, :data, :by, :at)""",
        id=new_id(), pt=parent_type, pid=parent_id, kind=kind, fn=uploaded_file.name,
        mime=uploaded_file.type or "application/octet-stream", size=len(data), data=data,
        by=uploaded_by, at=now_iso(),
    )
    return True


def list_documents(parent_type, parent_id, kind=None) -> list[dict]:
    sql = """SELECT id, kind, filename, mime, size, uploaded_by, uploaded_at FROM documents
             WHERE parent_type=:pt AND parent_id=:pid"""
    params = {"pt": parent_type, "pid": parent_id}
    if kind:
        sql += " AND kind=:kind"
        params["kind"] = kind
    return db_all(sql + " ORDER BY uploaded_at DESC", **params)


def document_bytes(doc_id) -> bytes:
    row = db_one("SELECT data FROM documents WHERE id=:id", id=doc_id)
    return bytes(row["data"]) if row and row["data"] is not None else b""


def render_documents(docs, key_prefix, show_images=False):
    if not docs:
        st.caption("No files yet.")
        return
    for d in docs:
        c1, c2 = st.columns([3, 1])
        c1.markdown(
            f"**{esc(d['filename'])}**  \n<span class='tf-muted'>{d['kind'].replace('_', ' ').capitalize()}, "
            f"{(d['size'] or 0) / 1024:,.0f} KB, {fmt_date(d['uploaded_at'])}</span>",
            unsafe_allow_html=True,
        )
        data = document_bytes(d["id"])
        c2.download_button("Download", data=data, file_name=d["filename"], mime=d["mime"],
                           key=f"{key_prefix}_dl_{d['id']}", use_container_width=True)
        if show_images and (d["mime"] or "").startswith("image/"):
            st.image(data, width=320)


# ============================================================================
# EMAIL (Resend)
# ============================================================================
def email_shell(inner_html: str) -> str:
    return f"""
    <div style="font-family:Arial,Helvetica,sans-serif;max-width:560px;margin:0 auto;padding:28px;
                border:1px solid #DCE3E8;border-radius:12px;background:#FFFFFF;color:#10243E">
      <div style="font-size:18px;font-weight:800;margin-bottom:18px">{BRAND['name']}</div>
      {inner_html}
      <div style="border-top:1px solid #DCE3E8;margin-top:24px;padding-top:12px;font-size:12px;color:#5B6878">
        {BRAND['name']} | {BRAND['email']} | {BRAND['phone']}<br>
        Not tax advice. Review all figures with your CPA.
      </div>
    </div>"""


def send_email(to, subject: str, inner_html: str, text_body: str | None = None):
    key = secret("RESEND_API_KEY")
    if not key:
        return False, "not_configured"
    recipients = [to] if isinstance(to, str) else [t for t in to if t]
    if not recipients:
        return False, "no_recipient"
    payload = {
        "from": secret("EMAIL_FROM", f"{BRAND['name']} <{BRAND['email']}>"),
        "to": recipients,
        "subject": subject,
        "html": email_shell(inner_html),
    }
    if text_body:
        payload["text"] = text_body
    try:
        r = requests.post("https://api.resend.com/emails", json=payload,
                          headers={"Authorization": f"Bearer {key}"}, timeout=8)
        return r.status_code in (200, 201, 202), r.text[:300]
    except requests.RequestException as exc:
        return False, str(exc)


def notify_admins(subject: str, inner_html: str):
    admins = sorted(admin_emails())
    if admins:
        send_email(admins, subject, inner_html)


def app_link(label="Open the portal") -> str:
    url = secret("APP_URL", "https://taxflowcostseg.com")
    return (f'<a href="{url}" style="display:inline-block;background:#10243E;color:#fff;padding:10px 16px;'
            f'border-radius:8px;text-decoration:none;font-weight:700">{label}</a>')


# ============================================================================
# AUTH — email one-time code, optional "stay signed in" link token
# ============================================================================
OTP_TTL_SECONDS = 600
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN = 30
SESSION_DAYS = 14


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def start_otp(email: str):
    now = time.time()
    prev = st.session_state.get("otp")
    if prev and prev["email"] == email and now - prev["sent_at"] < OTP_RESEND_COOLDOWN:
        wait = int(OTP_RESEND_COOLDOWN - (now - prev["sent_at"])) + 1
        return False, f"Wait {wait} seconds before requesting another code."
    code = f"{pysecrets.randbelow(1_000_000):06d}"
    st.session_state["otp"] = {"email": email, "hash": _sha(email + code), "expires": now + OTP_TTL_SECONDS,
                               "attempts": 0, "sent_at": now}
    ok, info = send_email(
        email,
        f"{code} is your {BRAND['name']} sign-in code",
        f"""<p style="color:#5B6878">Use this code to sign in. It expires in 10 minutes.</p>
            <div style="background:#F4F6F5;border-radius:8px;padding:16px;text-align:center;margin:16px 0">
              <span style="font-size:32px;font-weight:800;letter-spacing:6px">{code}</span></div>
            <p style="color:#5B6878;font-size:13px">If you didn't request this, you can ignore this email.</p>""",
        text_body=f"Your {BRAND['name']} sign-in code is {code}. It expires in 10 minutes.",
    )
    if not ok and info == "not_configured":
        st.session_state["otp"]["demo_code"] = code
        return True, "demo"
    if not ok:
        st.session_state.pop("otp", None)
        return False, "The code email couldn't be sent. Check the address, or try again in a minute."
    return True, "sent"


def verify_otp(code: str):
    otp = st.session_state.get("otp")
    if not otp:
        return False, "Request a new code to continue."
    if time.time() > otp["expires"]:
        return False, "This code has expired. Request a new one."
    if otp["attempts"] >= OTP_MAX_ATTEMPTS:
        return False, "Too many attempts. Request a new code."
    otp["attempts"] += 1
    if hmac.compare_digest(otp["hash"], _sha(otp["email"] + (code or "").strip())):
        return True, otp["email"]
    left = OTP_MAX_ATTEMPTS - otp["attempts"]
    return False, f"That code doesn't match. {left} attempt{'s' if left != 1 else ''} left."


def roles_for(email: str) -> list[str]:
    roles = []
    if email in admin_emails():
        roles.append("admin")
    if db_one("SELECT id FROM tenants WHERE email=:e AND status='Active'", e=email):
        roles.append("tenant")
    if db_one("SELECT id FROM contractors WHERE email=:e", e=email):
        roles.append("contractor")
    roles.append("investor")
    return roles


ROLE_LABEL = {"admin": "Management console", "tenant": "Resident portal",
              "contractor": "Work orders", "investor": "Cost seg studies"}


def set_signed_in(email: str):
    st.session_state["user_email"] = email
    st.session_state["roles"] = roles_for(email)
    st.session_state["view"] = st.session_state["roles"][0]


def complete_login(email: str):
    ts = now_iso()
    db_exec("""INSERT INTO users (email, created_at, last_login) VALUES (:e, :t, :t)
               ON CONFLICT (email) DO UPDATE SET last_login = excluded.last_login""", e=email, t=ts)
    token = pysecrets.token_urlsafe(32)
    expires = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")
    db_exec("INSERT INTO sessions (token_hash, email, expires_at) VALUES (:h, :e, :x)",
            h=_sha(token), e=email, x=expires)
    st.query_params["s"] = token
    set_signed_in(email)
    pending = st.session_state.pop("pending_study", None)
    if pending:
        sid = insert_study(email, pending, tier="Quick Estimate", status="Estimate")
        st.session_state["view"] = "investor"
        st.session_state["inv_goto"] = sid


def restore_session():
    if st.session_state.get("user_email"):
        return
    if "s" not in st.query_params:
        return
    token = st.query_params["s"]

    row = db_one("SELECT email, expires_at FROM sessions WHERE token_hash=:h", h=_sha(token))
    if row and row["expires_at"] > now_iso():
        set_signed_in(row["email"])
    else:
        del st.query_params["s"]


def sign_out():
    if "s" in st.query_params:
        token = st.query_params["s"]
        db_exec("DELETE FROM sessions WHERE token_hash=:h", h=_sha(token))
        del st.query_params["s"]
    for k in ["user_email", "roles", "otp", "login_step"]:
        st.session_state.pop(k, None)
    st.session_state["view"] = "landing"


# ============================================================================
# COST SEGREGATION ENGINE
# Allocation percentages are typical ranges for an estimate, not study results.
# ============================================================================
PROPERTY_TYPES = {
    "Single-family rental":           {"life": 27.5, "alloc": {5: 0.15, 7: 0.00, 15: 0.08}},
    "Condo or townhome rental":       {"life": 27.5, "alloc": {5: 0.16, 7: 0.00, 15: 0.04}},
    "Small multifamily (2–4 units)":  {"life": 27.5, "alloc": {5: 0.15, 7: 0.00, 15: 0.09}},
    "Apartment complex (5+ units)":   {"life": 27.5, "alloc": {5: 0.13, 7: 0.01, 15: 0.11}},
    "Short-term rental (furnished)":  {"life": 39.0, "alloc": {5: 0.24, 7: 0.01, 15: 0.08}},
    "Office":                         {"life": 39.0, "alloc": {5: 0.09, 7: 0.03, 15: 0.10}},
    "Retail":                         {"life": 39.0, "alloc": {5: 0.12, 7: 0.02, 15: 0.13}},
    "Industrial / warehouse":         {"life": 39.0, "alloc": {5: 0.06, 7: 0.04, 15: 0.11}},
    "Medical office":                 {"life": 39.0, "alloc": {5: 0.14, 7: 0.04, 15: 0.09}},
    "Hotel / hospitality":            {"life": 39.0, "alloc": {5: 0.18, 7: 0.07, 15: 0.09}},
    "Self storage":                   {"life": 39.0, "alloc": {5: 0.06, 7: 0.02, 15: 0.20}},
}
TYPE_NOTES = {
    "Short-term rental (furnished)":
        "Rentals with an average guest stay of 7 days or less are nonresidential, so the building is 39-year property.",
}
RENTCAST_TYPE_MAP = {
    "Single Family": "Single-family rental", "Manufactured": "Single-family rental",
    "Condo": "Condo or townhome rental", "Townhouse": "Condo or townhome rental",
    "Multi-Family": "Small multifamily (2–4 units)", "Apartment": "Apartment complex (5+ units)",
}
CLASS_LABEL = {5: "5-year", 7: "7-year", 15: "15-year"}
CLASS_EXAMPLES = {
    5: "Appliances, carpet, cabinets, specialty electrical and plumbing",
    7: "Furniture, fixtures and equipment",
    15: "Driveways, parking, fencing, landscaping, site utilities",
}
# IRS MACRS tables, half-year convention (Rev. Proc. 87-57, Table A-1)
MACRS_HY = {
    5: [0.20, 0.32, 0.192, 0.1152, 0.1152, 0.0576],
    7: [0.1429, 0.2449, 0.1749, 0.1249, 0.0893, 0.0892, 0.0893, 0.0446],
    15: [0.05, 0.095, 0.0855, 0.077, 0.0693, 0.0623, 0.059, 0.059, 0.0591, 0.059,
         0.0591, 0.059, 0.0591, 0.059, 0.0591, 0.0295],
}
BONUS_OPTIONS = ["Auto (based on dates)", "100%", "80%", "60%", "40%", "20%", "0% (elect out)"]
TAX_RATES = ["22%", "24%", "32%", "35%", "37%"]
OBBBA_CUTOFF = dt.date(2025, 1, 19)


def auto_bonus_rate(acquired: dt.date, in_service: dt.date) -> float:
    """Federal bonus depreciation by acquisition / placed-in-service date."""
    if acquired > OBBBA_CUTOFF and in_service > OBBBA_CUTOFF:
        return 1.0  # One Big Beautiful Bill Act: permanent 100%
    if acquired < dt.date(2017, 9, 28):
        return {2015: 0.5, 2016: 0.5, 2017: 0.5, 2018: 0.4, 2019: 0.3}.get(in_service.year, 0.0)
    if in_service.year <= 2022:
        return 1.0
    return {2023: 0.8, 2024: 0.6, 2025: 0.4, 2026: 0.2}.get(in_service.year, 0.0)


def bonus_from_mode(mode: str, acquired, in_service) -> float:
    if not mode or mode.startswith("Auto"):
        return auto_bonus_rate(acquired, in_service)
    return float(mode.split("%")[0]) / 100


def sl_mid_month(basis: float, life: float, in_service: dt.date, years: int) -> list[float]:
    annual = basis / life
    first = annual * (12 - in_service.month + 0.5) / 12
    out, remaining = [], basis
    for i in range(years):
        amt = max(0.0, min(first if i == 0 else annual, remaining))
        out.append(amt)
        remaining -= amt
    return out


def run_study_math(price, acquired, prop_type, land_pct=20.0, closing_costs=0.0, improvements=0.0,
                   in_service=None, tax_rate=0.37, bonus_mode="Auto", today=None, horizon=41) -> dict:
    today = today or dt.date.today()
    in_service = in_service or acquired
    cfg = PROPERTY_TYPES.get(prop_type, PROPERTY_TYPES["Single-family rental"])
    price, closing_costs, improvements = float(price or 0), float(closing_costs or 0), float(improvements or 0)
    land = (price + closing_costs) * float(land_pct or 0) / 100
    basis = max(price + closing_costs + improvements - land, 0.0)
    alloc = {c: basis * p for c, p in cfg["alloc"].items()}
    short_life = sum(alloc.values())
    building = basis - short_life
    rate = bonus_from_mode(bonus_mode, acquired, in_service)

    with_cs = [0.0] * horizon
    bonus_total = 0.0
    for cls, amt in alloc.items():
        if amt <= 0:
            continue
        bonus = amt * rate
        bonus_total += bonus
        with_cs[0] += bonus
        for i, pct in enumerate(MACRS_HY[cls][:horizon]):
            with_cs[i] += (amt - bonus) * pct
    for i, amt in enumerate(sl_mid_month(building, cfg["life"], in_service, horizon)):
        with_cs[i] += amt
    standard = sl_mid_month(basis, cfg["life"], in_service, horizon)

    first_year = in_service.year
    # Bought this year or last year: claim in the first year. Older: catch-up this year via Form 3115.
    tax_year = first_year if first_year >= today.year - 1 else today.year
    k = min(max(0, tax_year - first_year), horizon - 1)
    extra = sum(with_cs[: k + 1]) - sum(standard[: k + 1])
    return {
        "price": price, "land": land, "basis": basis, "alloc": alloc, "short_life": short_life,
        "building": building, "life": cfg["life"], "bonus_rate": rate, "bonus_total": bonus_total,
        "with_cs": with_cs, "standard": standard, "years": list(range(first_year, first_year + horizon)),
        "tax_year": tax_year, "catch_up": k > 0, "extra": extra, "tax_rate": tax_rate,
        "savings": extra * tax_rate, "acquired": acquired, "in_service": in_service,
        "short_pct": short_life / basis if basis else 0.0,
    }


def recommended_tier(basis: float) -> str:
    if basis < 350_000:
        return "Detailed Analysis"
    if basis < 1_500_000:
        return "Virtual Engineer Tour"
    return "Full On-Site Assessment"


def calc_for_study(s: dict) -> dict | None:
    acquired = parse_date(s.get("acquired_on"))
    if not acquired or not s.get("purchase_price"):
        return None
    return run_study_math(
        s["purchase_price"], acquired, s.get("property_type"), s.get("land_pct") or 20,
        s.get("closing_costs") or 0, s.get("improvements") or 0, parse_date(s.get("in_service_on")),
        s.get("tax_rate") or 0.37, s.get("bonus_mode") or "Auto",
    )


def insert_study(email, inputs: dict, tier: str, status: str) -> str:
    sid, ts = new_id(), now_iso()
    db_exec(
        """INSERT INTO studies (id, owner_email, address, property_type, purchase_price, closing_costs,
               improvements, land_pct, acquired_on, in_service_on, sqft, year_built, tax_rate, bonus_mode,
               tier, status, notes, created_at, updated_at)
           VALUES (:id, :e, :addr, :pt, :price, :cc, :imp, :land, :acq, :pis, :sqft, :yb, :tr, :bm,
               :tier, :status, '', :ts, :ts)""",
        id=sid, e=email, addr=inputs.get("address") or "Address not provided", pt=inputs["type"],
        price=inputs["price"], cc=inputs.get("closing", 0), imp=inputs.get("improve", 0),
        land=inputs.get("land", 20), acq=str(inputs["acquired"]),
        pis=str(inputs["in_service"]) if inputs.get("in_service") else None,
        sqft=inputs.get("sqft"), yb=inputs.get("year_built"), tr=inputs.get("tax_rate", 0.37),
        bm=inputs.get("bonus", "Auto"), tier=tier, status=status, ts=ts,
    )
    return sid


# ============================================================================
# PROPERTY RECORDS (RentCast)
# ============================================================================
def clean_address(addr: str) -> str:
    return re.sub(r",\s*(USA|United States)$", "", (addr or "").strip())


@st.cache_data(ttl=86_400, show_spinner=False)
def lookup_property(address: str) -> dict:
    """Returns public-record details used to pre-fill the estimate. Never invents values."""
    out = {"address": address, "connected": False, "found": False, "price": None, "price_source": None,
           "sale_date": None, "sqft": None, "year_built": None, "beds": None, "baths": None,
           "type": None, "land_pct": None, "error": None}
    key = secret("RENTCAST_API_KEY")
    if not key:
        return out
    out["connected"] = True
    headers = {"X-Api-Key": key, "Accept": "application/json"}
    assessed = None
    try:
        r = requests.get("https://api.rentcast.io/v1/properties", params={"address": address},
                         headers=headers, timeout=8)
        if r.ok:
            data = r.json()
            rec = data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) and data.get("id") else None)
            if rec:
                out["found"] = True
                out["sqft"] = rec.get("squareFootage")
                out["year_built"] = rec.get("yearBuilt")
                out["beds"] = rec.get("bedrooms")
                out["baths"] = rec.get("bathrooms")
                out["type"] = RENTCAST_TYPE_MAP.get(rec.get("propertyType"))
                if rec.get("lastSalePrice"):
                    out["price"] = float(rec["lastSalePrice"])
                    out["price_source"] = "last recorded sale"
                out["sale_date"] = parse_date(rec.get("lastSaleDate"))
                assessments = rec.get("taxAssessments") or {}
                if assessments:
                    latest = assessments[max(assessments.keys())]
                    value, land = latest.get("value"), latest.get("land")
                    if value:
                        assessed = float(value)
                        if land:
                            out["land_pct"] = int(round(min(max(land / value, 0.05), 0.60) * 100))
        elif r.status_code not in (404,):
            out["error"] = f"Property records returned {r.status_code}"
        if not out["price"]:
            r2 = requests.get("https://api.rentcast.io/v1/avm/value", params={"address": address},
                              headers=headers, timeout=8)
            if r2.ok and (r2.json() or {}).get("price"):
                out["price"] = float(r2.json()["price"])
                out["price_source"] = "estimated current value (sale price isn't public in this state)"
        if not out["price"] and assessed:
            out["price"] = assessed
            out["price_source"] = "county assessed value"
    except requests.RequestException as exc:
        out["error"] = str(exc)
    return out


# ============================================================================
# ADDRESS AUTOCOMPLETE — bidirectional Streamlit component (no page reload)
# ============================================================================
PLACES_HTML = r"""<!doctype html>
<html><head><meta charset="utf-8">
<style>
  html,body{margin:0;padding:0;background:transparent;font-family:"Public Sans",system-ui,-apple-system,sans-serif}
  #wrap{padding:2px}
  gmp-place-autocomplete{width:100%;display:block;color-scheme:light}
  #msg{display:none;margin:6px 2px 0;font-size:13px;color:#8A1C1C}
</style></head>
<body><div id="wrap"></div><div id="msg"></div>
<script>
const COLLAPSED = 58, EXPANDED = 330;
let started = false, lastH = 0;
function post(type, extra){ window.parent.postMessage(Object.assign({isStreamlitMessage:true, type:type}, extra||{}), "*"); }
function setHeight(h){ if(h !== lastH){ lastH = h; post("streamlit:setFrameHeight", {height:h}); } }
function setValue(v){ post("streamlit:setComponentValue", {value:v, dataType:"json"}); }
function showMsg(t){ const m=document.getElementById("msg"); m.textContent=t; m.style.display="block"; setHeight(COLLAPSED+36); }
window.gm_authFailure = function(){ showMsg("Address search is unavailable right now. Use 'Enter the address manually' below."); setValue({error:"auth", nonce:Date.now()}); };
function loadMaps(key){
  return new Promise((resolve, reject) => {
    if (window.google && google.maps && google.maps.importLibrary) { resolve(); return; }
    window.__mapsReady = () => resolve();
    const s = document.createElement("script");
    s.src = "https://maps.googleapis.com/maps/api/js?key=" + encodeURIComponent(key) + "&v=weekly&loading=async&callback=__mapsReady";
    s.async = true; s.onerror = () => reject(new Error("Google Maps failed to load"));
    document.head.appendChild(s);
  });
}
async function emitPlace(place){
  await place.fetchFields({fields:["formattedAddress","location","addressComponents"]});
  const comps = {};
  (place.addressComponents||[]).forEach(c => (c.types||[]).forEach(t => { comps[t] = c.shortText || c.longText; }));
  setValue({address: place.formattedAddress, components: comps,
            lat: place.location ? place.location.lat() : null, lng: place.location ? place.location.lng() : null,
            nonce: Date.now()});
  setHeight(COLLAPSED);
}
async function start(args){
  started = true;
  try {
    await loadMaps(args.api_key);
    const { PlaceAutocompleteElement } = await google.maps.importLibrary("places");
    let el;
    try { el = new PlaceAutocompleteElement({ includedRegionCodes: ["us"] }); }
    catch (e) { el = new PlaceAutocompleteElement({ componentRestrictions: { country: ["us"] } }); }
    if (args.placeholder) el.setAttribute("placeholder", args.placeholder);
    document.getElementById("wrap").appendChild(el);
    el.addEventListener("focusin", () => setHeight(EXPANDED));
    el.addEventListener("input", () => setHeight(EXPANDED));
    el.addEventListener("focusout", () => setTimeout(() => setHeight(COLLAPSED), 300));
    // Current API event
    el.addEventListener("gmp-select", async (ev) => {
      try { await emitPlace(ev.placePrediction.toPlace()); } catch (e) { showMsg("That address couldn't be read: " + e.message); }
    });
    // Older API event (kept for compatibility)
    el.addEventListener("gmp-placeselect", async (ev) => {
      try { await emitPlace(ev.place); } catch (e) { showMsg("That address couldn't be read: " + e.message); }
    });
    setHeight(COLLAPSED);
  } catch (e) {
    showMsg("Address search is unavailable (" + e.message + "). Use 'Enter the address manually' below.");
    setValue({error: String(e.message), nonce: Date.now()});
  }
}
window.addEventListener("message", (ev) => {
  const d = ev.data;
  if (!d || d.type !== "streamlit:render") return;
  if (!started) start(d.args || {});
});
post("streamlit:componentReady", {apiVersion: 1});
setHeight(COLLAPSED);
</script></body></html>"""

_COMPONENT_DIR = os.path.join(APP_DIR, ".st_components", "places_autocomplete")


def _places_component():
    path = os.path.join(_COMPONENT_DIR, "index.html")
    try:
        os.makedirs(_COMPONENT_DIR, exist_ok=True)
        current = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
        if current != PLACES_HTML:
            with open(path, "w", encoding="utf-8") as f:
                f.write(PLACES_HTML)
    except OSError:
        return None
    return components.declare_component("places_autocomplete", path=_COMPONENT_DIR)


PLACES = _places_component()


def address_search(key: str, placeholder: str = "Start typing the property address") -> str | None:
    """Renders the address search. Returns a newly selected address once, else None."""
    picked = None
    gkey = secret("GOOGLE_MAPS_API_KEY")
    if gkey and PLACES is not None:
        val = PLACES(api_key=gkey, placeholder=placeholder, key=key, default=None)
        nonce_key = f"{key}__nonce"
        if isinstance(val, dict) and val.get("address") and val.get("nonce") != st.session_state.get(nonce_key):
            st.session_state[nonce_key] = val["nonce"]
            picked = clean_address(val["address"])
    with st.expander("Enter the address manually", expanded=not gkey):
        with st.form(f"{key}_manual", border=False):
            manual = st.text_input("Street address, city, state ZIP", key=f"{key}_manual_text",
                                   placeholder="3326 Lakeway Ln, Pearland, TX 77584")
            if st.form_submit_button("Look up this address"):
                if manual and len(manual.strip()) > 8:
                    picked = clean_address(manual)
                else:
                    st.error("Enter the full street address, city and state.")
    return picked


# ============================================================================
# STYLE
# Ink navy for structure, one green for money, class colors carried from the split bar.
# ============================================================================
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600;700;800&display=swap');
:root{
  --ink:#10243E; --ink-2:#1E3A5F; --paper:#F4F6F5; --surface:#FFFFFF; --line:#DCE3E8; --muted:#5B6878;
  --save:#0B7A5C; --c5:#0B7A5C; --c7:#2F6FB0; --c15:#C7861A; --bld:#8A97A6; --land:#D3DAE0; --warn:#9A5B00;
}
html, body, .stApp, .stApp p, .stApp label, .stApp input, .stApp textarea, .stApp button, .stApp li {
  font-family:'Public Sans', system-ui, -apple-system, sans-serif;
}
.stApp{background:#FFFFFF;}
header[data-testid="stHeader"], #MainMenu, footer, [data-testid="stToolbar"], .stDeployButton{display:none !important;}
.block-container{padding-top:1rem; padding-bottom:0; max-width:1180px;}
h1,h2,h3,h4{color:var(--ink); letter-spacing:-0.02em;}
[data-testid="stExpander"] details{background:var(--surface); border-color:var(--line);}
.tf-muted{color:var(--muted); font-size:0.88rem;}
.tf-num{font-variant-numeric:tabular-nums;}

/* Nav */
.st-key-nav_brand button{background:transparent !important; border:none !important; padding:0 !important;
  font-size:1.3rem !important; font-weight:800 !important; color:var(--ink) !important; box-shadow:none !important;}
.st-key-nav_brand button p{font-size:1.3rem !important; font-weight:800 !important;}
.tf-navline{border-bottom:1px solid var(--line); margin:0.25rem 0 1.5rem 0;}

/* Hero */
.tf-hero h1{font-size:clamp(2.1rem, 4.2vw, 3.3rem); line-height:1.04; font-weight:800; letter-spacing:-0.035em;
  margin:0.4rem 0 1rem 0; max-width:15ch;}
.tf-hero p.lead{font-size:1.08rem; line-height:1.6; color:#33465C; max-width:52ch;}
.tf-trust{font-size:0.92rem; color:var(--muted); margin-top:0.8rem;}
.tf-law{border-left:3px solid var(--save); padding:0.5rem 0 0.5rem 0.9rem; margin:1.3rem 0; color:#24384F;
  font-size:0.95rem; line-height:1.55; max-width:52ch;}

/* Results */
.tf-big{font-size:2.6rem; font-weight:800; letter-spacing:-0.03em; color:var(--save); line-height:1.05;
  font-variant-numeric:tabular-nums;}
.tf-biglabel{color:#24384F; font-weight:600; font-size:0.98rem;}
.tf-sub{color:var(--muted); font-size:0.92rem; margin-top:0.25rem;}
.tf-split{display:flex; height:46px; border-radius:6px; overflow:hidden; margin:1rem 0 0.6rem 0;
  border:1px solid var(--line);}
.tf-split .seg{display:flex; align-items:center; justify-content:center; color:#fff; font-size:0.78rem;
  font-weight:700; white-space:nowrap; overflow:hidden;}
.tf-split .seg.light{color:#33465C;}
.tf-legend{display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:0.5rem 1rem; margin-top:0.4rem;}
.tf-legend div{font-size:0.83rem; color:#33465C; line-height:1.35;}
.tf-legend b{display:block; font-size:0.95rem; color:var(--ink); font-variant-numeric:tabular-nums;}
.tf-sw{display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:6px; vertical-align:middle;}

/* KPIs */
.tf-kpi{background:var(--paper); border:1px solid transparent; border-radius:10px; padding:16px 18px; height:100%;}
.tf-kpi .l{font-size:0.85rem; color:var(--muted); font-weight:600;}
.tf-kpi .v{font-size:1.65rem; font-weight:800; color:var(--ink); margin-top:2px; font-variant-numeric:tabular-nums;}
.tf-kpi .v.good{color:var(--save);} .tf-kpi .v.warn{color:var(--warn);}
.tf-kpi .n{font-size:0.8rem; color:var(--muted); margin-top:2px;}

/* Status pills and stepper */
.tf-pill{display:inline-block; padding:2px 10px; border-radius:999px; font-size:0.78rem; font-weight:700;
  background:#E8EEF3; color:var(--ink-2);}
.tf-pill.good{background:#DDF1EA; color:#0A5E47;} .tf-pill.warn{background:#FBEBD3; color:#7A4700;}
.tf-pill.bad{background:#F8DEDE; color:#8A1C1C;}
.tf-steps{display:flex; gap:0; margin:0.4rem 0 1.2rem 0; flex-wrap:wrap;}
.tf-step{flex:1; min-width:120px; display:flex; align-items:center; gap:8px; padding:8px 10px 8px 0;
  font-size:0.85rem; color:var(--muted); border-top:3px solid var(--line);}
.tf-step .dot{width:22px; height:22px; border-radius:50%; background:var(--line); color:var(--ink);
  display:inline-flex; align-items:center; justify-content:center; font-size:0.75rem; font-weight:700; flex:none;}
.tf-step.done{border-top-color:var(--save); color:var(--ink);}
.tf-step.done .dot{background:var(--save); color:#fff;}
.tf-step.now{border-top-color:var(--ink); color:var(--ink); font-weight:700;}
.tf-step.now .dot{background:var(--ink); color:#fff;}

/* Sections */
.tf-section{margin-top:4.5rem;}
.tf-section h2{font-size:clamp(1.6rem, 2.8vw, 2.2rem); font-weight:800; margin-bottom:0.4rem;}
.tf-section p.intro{color:#33465C; max-width:60ch; font-size:1.02rem; line-height:1.6;}
.tf-step-card{border-top:3px solid var(--ink); padding-top:0.9rem;}
.tf-step-card .n{font-weight:800; color:var(--save); font-size:0.95rem;}
.tf-step-card h4{margin:0.3rem 0 0.4rem 0; font-size:1.08rem;}
.tf-step-card p{color:#33465C; font-size:0.94rem; line-height:1.55;}
.tf-tier{background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:20px; height:100%;}
.tf-tier.rec{border:2px solid var(--ink);}
.tf-tier h4{margin:0; font-size:1.05rem;}
.tf-tier .p{font-size:2rem; font-weight:800; color:var(--ink); margin:0.4rem 0; font-variant-numeric:tabular-nums;}
.tf-tier p{color:#33465C; font-size:0.92rem; line-height:1.5;}
.tf-tier .a{font-size:0.83rem; color:var(--save); font-weight:700;}
.tf-footer{background:var(--ink); color:#B8C4D2; padding:36px 28px 26px; border-radius:12px 12px 0 0;
  margin-top:5rem; font-size:0.9rem; line-height:1.6;}
.tf-footer b{color:#fff;} .tf-footer .brand{font-size:1.15rem; font-weight:800; color:#fff;}
.tf-footer .cols{display:flex; justify-content:space-between; flex-wrap:wrap; gap:24px;}
.tf-footer .fine{border-top:1px solid #2B4566; margin-top:20px; padding-top:14px; font-size:0.8rem; color:#8FA0B4;}
</style>
""",
    unsafe_allow_html=True,
)


# ============================================================================
# UI BUILDING BLOCKS
# ============================================================================
def kpi(col, label, value, note="", tone=""):
    col.markdown(
        f'<div class="tf-kpi"><div class="l">{esc(label)}</div><div class="v {tone}">{value}</div>'
        f'<div class="n">{esc(note)}</div></div>',
        unsafe_allow_html=True,
    )


def pill(text_, tone=""):
    return f'<span class="tf-pill {tone}">{esc(text_)}</span>'


def status_tone(status):
    if status in ("Report delivered", "Completed", "Closed", "Paid", "Active"):
        return "good"
    if status in ("Emergency", "Overdue", "New"):
        return "bad"
    if status in ("Urgent", "Partial", "Due", "Submitted", "Assigned"):
        return "warn"
    return ""


def study_stepper(status):
    idx = STUDY_FLOW.index(status) if status in STUDY_FLOW else 0
    parts = []
    for i, s in enumerate(STUDY_FLOW):
        cls = "done" if i < idx else ("now" if i == idx else "")
        mark = "✓" if i < idx else str(i + 1)
        parts.append(f'<div class="tf-step {cls}"><span class="dot">{mark}</span><span>{esc(s)}</span></div>')
    st.markdown(f'<div class="tf-steps">{"".join(parts)}</div>', unsafe_allow_html=True)


def split_bar(calc):
    """The signature visual: where the purchase price goes."""
    total = calc["land"] + calc["basis"]
    if total <= 0:
        return
    life = "27.5" if calc["life"] == 27.5 else "39"
    segs = [("Land", calc["land"], "var(--land)", True, "Not depreciable")]
    for cls in (5, 7, 15):
        amt = calc["alloc"].get(cls, 0)
        if amt > 0:
            segs.append((CLASS_LABEL[cls], amt, f"var(--c{cls})", False, CLASS_EXAMPLES[cls]))
    segs.append((f"{life}-year building", calc["building"], "var(--bld)", False, "Structure, deducted evenly"))
    bar = "".join(
        f'<div class="seg {"light" if light else ""}" style="flex:{max(amt / total, 0.001):.4f};background:{color}" '
        f'title="{esc(name)}: {money(amt)}">{esc(name) if amt / total > 0.11 else ""}</div>'
        for name, amt, color, light, _ in segs
    )
    legend = "".join(
        f'<div><span class="tf-sw" style="background:{color}"></span>{esc(name)}'
        f'<b>{money(amt)}</b>{esc(desc)}</div>'
        for name, amt, color, _, desc in segs
    )
    st.markdown(f'<div class="tf-split">{bar}</div><div class="tf-legend">{legend}</div>', unsafe_allow_html=True)


def headline_result(calc, compact=False):
    when = f"on your {calc['tax_year']} return"
    st.markdown(
        f'<div class="tf-biglabel">Extra deduction {when}</div>'
        f'<div class="tf-big">{money(calc["extra"])}</div>'
        f'<div class="tf-sub">About <b>{money(calc["savings"])}</b> less federal tax at a '
        f'{calc["tax_rate"] * 100:.0f}% bracket. Bonus depreciation: {calc["bonus_rate"] * 100:.0f}%.</div>',
        unsafe_allow_html=True,
    )
    if calc["catch_up"]:
        st.caption(
            f"Placed in service in {calc['in_service'].year}, so the missed depreciation is caught up in "
            f"{calc['tax_year']} with IRS Form 3115. No amended returns needed."
        )
    if not compact:
        split_bar(calc)


def savings_chart(calc, years=10, height=260):
    ys = calc["years"][:years]
    cs = pd.Series(calc["with_cs"][:years]).cumsum()
    sl = pd.Series(calc["standard"][:years]).cumsum()
    df = pd.DataFrame({"Year": ys, "With cost segregation": cs, "Standard depreciation": sl})
    long = df.melt("Year", var_name="Method", value_name="Total deducted")
    chart = (
        alt.Chart(long)
        .mark_line(point=True, strokeWidth=2.5)
        .encode(
            x=alt.X("Year:O", axis=alt.Axis(labelAngle=0, title=None)),
            y=alt.Y("Total deducted:Q", axis=alt.Axis(format="$,.0f", title=None)),
            color=alt.Color("Method:N",
                            scale=alt.Scale(domain=["With cost segregation", "Standard depreciation"],
                                            range=["#0B7A5C", "#8A97A6"]),
                            legend=alt.Legend(orient="bottom", title=None)),
            tooltip=["Year", "Method", alt.Tooltip("Total deducted:Q", format="$,.0f")],
        )
        .properties(height=height)
    )
    st.altair_chart(chart, use_container_width=True)


def schedule_frame(calc, years=15) -> pd.DataFrame:
    ys = calc["years"][:years]
    cs, sl = calc["with_cs"][:years], calc["standard"][:years]
    df = pd.DataFrame({"Tax year": ys, "With cost segregation": cs, "Standard": sl})
    df["Difference"] = df["With cost segregation"] - df["Standard"]
    df["Cumulative difference"] = df["Difference"].cumsum()
    return df


def money_cols(cols):
    return {c: st.column_config.NumberColumn(c, format="$%,.0f") for c in cols}


# ============================================================================
# ESTIMATE INPUTS (shared by the landing estimator and the New study dialog)
# ============================================================================
EST_FIELDS = ["address", "record", "price", "acquired", "type", "rate", "land", "closing", "improve",
              "pis_diff", "pis", "bonus", "tier"]


def init_estimate_state(prefix):
    defaults = {"address": "", "record": None, "price": None, "acquired": None,
                "type": "Single-family rental", "rate": "37%", "land": 20, "closing": 0.0,
                "improve": 0.0, "pis_diff": False, "pis": None, "bonus": BONUS_OPTIONS[0]}
    for f, v in defaults.items():
        st.session_state.setdefault(f"{prefix}_{f}", v)


def keep_estimate_state():
    """Keeps estimator values when the estimator isn't on screen (Streamlit drops unrendered widget state)."""
    for prefix in ("est", "ns"):
        for f in EST_FIELDS:
            k = f"{prefix}_{f}"
            if k in st.session_state:
                st.session_state[k] = st.session_state[k]


def reset_estimate_state(prefix):
    for f in EST_FIELDS:
        st.session_state.pop(f"{prefix}_{f}", None)
    st.session_state.pop(f"{prefix}_places_manual_text", None)


def apply_lookup(prefix, info):
    st.session_state[f"{prefix}_address"] = info["address"]
    st.session_state[f"{prefix}_record"] = info
    if info.get("price"):
        st.session_state[f"{prefix}_price"] = float(round(info["price"], -3))
    if info.get("sale_date"):
        st.session_state[f"{prefix}_acquired"] = info["sale_date"]
    if info.get("type") in PROPERTY_TYPES:
        st.session_state[f"{prefix}_type"] = info["type"]
    if info.get("land_pct"):
        st.session_state[f"{prefix}_land"] = int(info["land_pct"])


def record_summary(prefix):
    addr = st.session_state.get(f"{prefix}_address")
    if not addr:
        return
    rec = st.session_state.get(f"{prefix}_record") or {}
    facts = []
    if rec.get("sqft"):
        facts.append(f"{int(rec['sqft']):,} sq ft")
    if rec.get("year_built"):
        facts.append(f"built {rec['year_built']}")
    if rec.get("beds"):
        facts.append(f"{rec['beds']:g} bd / {rec.get('baths') or 0:g} ba")
    with st.container(border=True):
        st.markdown(f"**{esc(addr)}**" + (f"  \n<span class='tf-muted'>{', '.join(facts)}</span>" if facts else ""),
                    unsafe_allow_html=True)
        if not rec.get("connected"):
            st.caption("Enter the purchase price and date from your closing statement.")
        elif not rec.get("found") and not rec.get("price"):
            st.caption("No public record matched this address. Enter the price and date from your closing statement.")
        else:
            notes = []
            if rec.get("price"):
                notes.append(f"Price filled from the {rec['price_source']}")
            if rec.get("sale_date"):
                notes.append("purchase date from the last recorded sale")
            if rec.get("land_pct"):
                notes.append("land share from the county assessment")
            if notes:
                st.caption("; ".join(notes).capitalize() + ". Replace anything that differs from your closing statement.")
            if rec.get("price") and not rec.get("sale_date"):
                st.caption("The sale date isn't on record. Add your purchase date below.")


def property_inputs(prefix, search_key):
    init_estimate_state(prefix)
    picked = address_search(search_key)
    if picked:
        with st.spinner("Looking up property records…"):
            apply_lookup(prefix, lookup_property(picked))
    record_summary(prefix)

    c1, c2 = st.columns(2)
    c1.number_input("Purchase price", key=f"{prefix}_price", min_value=0.0, step=5000.0, format="%.0f",
                    placeholder="e.g. 450000")
    c2.date_input("Purchase date", key=f"{prefix}_acquired", min_value=dt.date(1987, 1, 1),
                  max_value=dt.date(TODAY.year + 1, 12, 31), format="MM/DD/YYYY")
    c3, c4 = st.columns(2)
    c3.selectbox("Property type", list(PROPERTY_TYPES), key=f"{prefix}_type")
    c4.selectbox("Federal tax bracket", TAX_RATES, key=f"{prefix}_rate")
    note = TYPE_NOTES.get(st.session_state[f"{prefix}_type"])
    if note:
        st.caption(note)
    with st.expander("Fine-tune assumptions"):
        st.slider("Land value, % of purchase price", 0, 60, key=f"{prefix}_land",
                  help="Land can't be depreciated. Your county appraisal shows the land and improvement split.")
        a, b = st.columns(2)
        a.number_input("Closing costs", key=f"{prefix}_closing", min_value=0.0, step=500.0, format="%.0f")
        b.number_input("Improvements since purchase", key=f"{prefix}_improve", min_value=0.0, step=1000.0,
                       format="%.0f")
        st.checkbox("Placed in service on a different date than purchase", key=f"{prefix}_pis_diff",
                    help="For example, if renovations delayed renting it out.")
        if st.session_state[f"{prefix}_pis_diff"]:
            st.date_input("Placed-in-service date", key=f"{prefix}_pis", min_value=dt.date(1987, 1, 1),
                          max_value=dt.date(TODAY.year + 1, 12, 31), format="MM/DD/YYYY")
        st.selectbox("Bonus depreciation", BONUS_OPTIONS, key=f"{prefix}_bonus",
                     help="Auto applies 100% for property acquired and placed in service after January 19, 2025, "
                          "and the phase-down rates for earlier property.")
    return collect_inputs(prefix)


def collect_inputs(prefix):
    g = lambda f: st.session_state.get(f"{prefix}_{f}")  # noqa: E731
    if not g("price") or not g("acquired"):
        return None
    rec = g("record") or {}
    pis = g("pis") if g("pis_diff") and g("pis") else None
    return {
        "address": g("address"), "price": float(g("price")), "acquired": g("acquired"), "in_service": pis,
        "type": g("type"), "tax_rate": float(g("rate").rstrip("%")) / 100, "land": float(g("land")),
        "closing": float(g("closing") or 0), "improve": float(g("improve") or 0),
        "bonus": g("bonus") or "Auto", "sqft": rec.get("sqft"), "year_built": rec.get("year_built"),
    }


def calc_from_inputs(inp):
    return run_study_math(inp["price"], inp["acquired"], inp["type"], inp["land"], inp["closing"],
                          inp["improve"], inp["in_service"], inp["tax_rate"], inp["bonus"])


# ============================================================================
# DIALOGS
# ============================================================================
@st.dialog(" ", width="large")
def video_dialog():
    st.video(BRAND["video_url"])


@st.dialog("Sign in")
def login_dialog():
    step = st.session_state.get("login_step", "email")
    if step == "email":
        st.write("Enter your email and we'll send a 6-digit sign-in code. No password needed.")
        with st.form("login_email_form", border=False):
            email = st.text_input("Email", placeholder="you@example.com")
            go = st.form_submit_button("Email me a code", type="primary", use_container_width=True)
        if go:
            e = (email or "").strip().lower()
            if not valid_email(e):
                st.error("Enter a valid email address, like name@example.com.")
            else:
                ok, msg = start_otp(e)
                if ok:
                    st.session_state["login_step"] = "code"
                    st.rerun(scope="fragment")
                st.error(msg)
    else:
        otp = st.session_state.get("otp") or {}
        st.write(f"We sent a code to **{esc(otp.get('email', ''))}**. It expires in 10 minutes.")
        if otp.get("demo_code"):
            st.info(f"Email sending isn't set up yet (no RESEND_API_KEY), so here is the code: **{otp['demo_code']}**")
        with st.form("login_code_form", border=False):
            code = st.text_input("6-digit code", max_chars=6, placeholder="123456")
            go = st.form_submit_button("Sign in", type="primary", use_container_width=True)
        if go:
            ok, res = verify_otp(code)
            if ok:
                complete_login(res)
                st.session_state.pop("otp", None)
                st.session_state["login_step"] = "email"
                st.rerun()
            st.error(res)
        c1, c2 = st.columns(2)
        if c1.button("Use a different email", use_container_width=True):
            st.session_state["login_step"] = "email"
            st.rerun(scope="fragment")
        if c2.button("Send a new code", use_container_width=True):
            ok, msg = start_otp(otp.get("email", ""))
            (st.success("A new code is on its way.") if ok else st.error(msg))


@st.dialog("New cost segregation study", width="large")
def new_study_dialog():
    st.caption("Search the address to fill in property records, then confirm the numbers.")
    inputs = property_inputs("ns", "ns_places")
    calc = calc_from_inputs(inputs) if inputs else None
    tier_names = [t["name"] for t in TIERS]
    if calc:
        with st.container(border=True):
            headline_result(calc, compact=True)
        rec = recommended_tier(calc["basis"])
        st.session_state.setdefault("ns_tier", rec)
        st.caption(f"Recommended for this property: {rec}")
    st.radio("Service level", tier_names, key="ns_tier", horizontal=True,
             format_func=lambda n: f"{n} ({money(TIER_BY_NAME[n]['price']) if TIER_BY_NAME[n]['price'] else 'Free'})")
    if st.button("Create study", type="primary", use_container_width=True):
        if not st.session_state.get("ns_address"):
            st.error("Search for the property address, or enter it manually, before creating the study.")
            return
        if not inputs:
            st.error("Add the purchase price and purchase date.")
            return
        tier = st.session_state.get("ns_tier") or "Quick Estimate"
        status = "Estimate" if tier == "Quick Estimate" else "Submitted"
        email = st.session_state["user_email"]
        sid = insert_study(email, inputs, tier, status)
        if status == "Submitted":
            notify_admins(f"New study request: {inputs['address']}",
                          f"<p><b>{esc(email)}</b> requested a <b>{esc(tier)}</b> for "
                          f"<b>{esc(inputs['address'])}</b> ({money(inputs['price'])}).</p>")
        reset_estimate_state("ns")
        st.session_state["inv_goto"] = sid
        st.rerun()


# ============================================================================
# VIEW: PUBLIC LANDING PAGE (single consolidated estimator)
# ============================================================================
def start_study_from_estimate(inputs):
    if st.session_state.get("user_email"):
        sid = insert_study(st.session_state["user_email"], inputs, "Quick Estimate", "Estimate")
        st.session_state["view"] = "investor"
        st.session_state["inv_goto"] = sid
        st.rerun()
    else:
        st.session_state["pending_study"] = inputs
        st.session_state["login_step"] = "email"
        login_dialog()


def email_estimate_form(inputs, calc):
    with st.form("lead_form", border=False):
        email = st.text_input("Email", placeholder="you@example.com")
        sent = st.form_submit_button("Send my estimate", type="primary", use_container_width=True)
    if sent:
        e = (email or "").strip().lower()
        if not valid_email(e):
            st.error("Enter a valid email address.")
            return
        db_exec("""INSERT INTO leads (id, email, address, purchase_price, est_deduction, est_savings, created_at)
                   VALUES (:id, :e, :a, :p, :d, :s, :t)""",
                id=new_id(), e=e, a=inputs.get("address") or "", p=inputs["price"], d=calc["extra"],
                s=calc["savings"], t=now_iso())
        rows = "".join(
            f"<tr><td style='padding:4px 12px 4px 0;color:#5B6878'>{k}</td><td><b>{v}</b></td></tr>"
            for k, v in [
                ("Property", esc(inputs.get("address") or "Not provided")),
                ("Purchase price", money(inputs["price"])),
                ("Depreciable basis", money(calc["basis"])),
                ("Shorter-life property identified", money(calc["short_life"])),
                (f"Extra deduction ({calc['tax_year']})", money(calc["extra"])),
                (f"Estimated federal tax savings at {calc['tax_rate'] * 100:.0f}%", money(calc["savings"])),
            ])
        ok, _ = send_email(e, "Your cost segregation estimate",
                           f"<p>Here is the estimate you ran on our site.</p><table>{rows}</table>"
                           f"<p style='color:#5B6878;font-size:13px'>A study confirms these numbers with an "
                           f"engineer's component breakdown.</p>{app_link('Start a study')}")
        notify_admins(f"New estimate lead: {inputs.get('address') or e}",
                      f"<p><b>{esc(e)}</b> ran an estimate.</p><table>{rows}</table>")
        st.success("Sent. Check your inbox." if ok else "Saved. We'll follow up by email.")


def view_landing():
    left, right = st.columns([1.0, 1.05], gap="large")
    with left:
        st.markdown(
            f"""
            <div class="tf-hero">
              <h1>Your building isn't one asset. Stop depreciating it like one.</h1>
              <p class="lead">A cost segregation study splits a property into 5-, 7- and 15-year parts so you
              deduct more of it now instead of over 27.5 or 39 years.</p>
              <div class="tf-law">Property acquired and placed in service after January 19, 2025 qualifies for
              permanent 100% bonus depreciation on those shorter-life parts. Bought earlier? You can still catch up
              missed depreciation this year without amending past returns.</div>
              <div class="tf-trust">{esc(BRAND['trust_line'])}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("▶  Watch the 90-second explainer"):
            video_dialog()

    with right:
        with st.container(border=True):
            st.markdown("#### Estimate your savings")
            inputs = property_inputs("est", "est_places")
            if not inputs:
                st.caption("Enter a purchase price and date to see your estimate.")
            else:
                calc = calc_from_inputs(inputs)
                st.divider()
                headline_result(calc)
                c1, c2 = st.columns(2)
                if c1.button("Start my study", type="primary", use_container_width=True):
                    start_study_from_estimate(inputs)
                with c2.popover("Email me this estimate", use_container_width=True):
                    email_estimate_form(inputs, calc)
                st.caption("Estimate based on typical allocations for this property type. "
                           "Not tax advice; review with your CPA.")

    # How it works
    st.markdown(
        """<div class="tf-section"><h2>How a study works</h2>
        <p class="intro">You send the purchase details. An engineer identifies every component that qualifies for a
        shorter recovery period. Your CPA files the result.</p></div>""",
        unsafe_allow_html=True,
    )
    steps = [
        ("Send your details", "Address, closing statement and any photos or plans, uploaded in your portal."),
        ("Engineering review", "Components are identified and costed remotely, by video tour, or on site."),
        ("Get your report", "A study with asset classes, costs and multi-year depreciation schedules."),
        ("File with your CPA", "Claim it on this year's return, or catch up prior years with Form 3115."),
    ]
    cols = st.columns(4, gap="medium")
    for i, (col, (title, body)) in enumerate(zip(cols, steps), start=1):
        col.markdown(f'<div class="tf-step-card"><div class="n">Step {i}</div><h4>{title}</h4><p>{body}</p></div>',
                     unsafe_allow_html=True)

    # Pricing
    st.markdown(
        """<div class="tf-section"><h2>Pricing</h2>
        <p class="intro">Flat fees, quoted before any work starts. Pick the depth that matches the property.</p></div>""",
        unsafe_allow_html=True,
    )
    est_inputs = collect_inputs("est")
    rec = recommended_tier(calc_from_inputs(est_inputs)["basis"]) if est_inputs else None
    cols = st.columns(4, gap="medium")
    for col, t in zip(cols, TIERS):
        price = "Free" if not t["price"] else money(t["price"])
        is_rec = t["name"] == rec
        col.markdown(
            f'<div class="tf-tier {"rec" if is_rec else ""}"><h4>{t["name"]}</h4><div class="p">{price}</div>'
            f'<p>{t["desc"]}</p>{"<div class=a>Includes audit assistance</div>" if t["audit"] else ""}'
            f'{"<div class=a>Fits the property you entered</div>" if is_rec else ""}</div>',
            unsafe_allow_html=True,
        )

    # Property management
    st.markdown(
        """<div class="tf-section"><h2>Property management</h2>
        <p class="intro">For the rentals we manage, residents pay rent, request repairs and find their lease in one
        place, and owners see occupancy, collections and maintenance as it happens.</p></div>""",
        unsafe_allow_html=True,
    )
    pm = st.columns(3, gap="medium")
    for col, (title, body) in zip(pm, [
        ("Residents", "Submit a repair request with photos, track its status, see what you owe and your payment history."),
        ("Owners", "Rent roll, collections, lease renewals and maintenance costs for every unit, updated live."),
        ("Contractors", "Assigned jobs with access notes and photos. Update status and costs from your phone."),
    ]):
        col.markdown(f'<div class="tf-step-card"><h4>{title}</h4><p>{body}</p></div>', unsafe_allow_html=True)

    # FAQ
    st.markdown('<div class="tf-section"><h2>Common questions</h2></div>', unsafe_allow_html=True)
    faqs = [
        ("Does cost segregation work for a single-family rental?",
         "Yes. Residential rentals typically move 15–30% of the building cost into 5- and 15-year property. "
         "The estimate above shows the split for your property type."),
        ("What changed with bonus depreciation in 2025?",
         "The One Big Beautiful Bill Act, signed July 4, 2025, made 100% bonus depreciation permanent for property "
         "acquired and placed in service after January 19, 2025. Earlier acquisitions use the phase-down rates "
         "(80% for 2023, 60% for 2024, 40% for 2025)."),
        ("I bought my property years ago. Is it too late?",
         "No. A study on a property already in service lets you claim all the depreciation you missed in the current "
         "year through a change in accounting method (Form 3115). No amended returns."),
        ("Can I use the deduction against my W-2 income?",
         "It depends on passive activity rules. Real estate professionals, and short-term rental owners who "
         "materially participate, can often use it against other income. Others may carry it forward. Ask your CPA."),
        ("What happens if I'm audited?",
         "Virtual Engineer Tour and Full On-Site Assessment include audit assistance: we explain and support the "
         "study's methodology and documentation if the IRS asks."),
    ]
    for q, a in faqs:
        with st.expander(q):
            st.write(a)


# ============================================================================
# VIEW: COST SEG CLIENT (investor)
# ============================================================================
def view_investor():
    email = st.session_state["user_email"]
    studies = db_all("SELECT * FROM studies WHERE owner_email=:e ORDER BY created_at DESC", e=email)

    h1, h2 = st.columns([3, 1])
    h1.markdown("## Your cost segregation studies")
    if h2.button("New study", type="primary", use_container_width=True):
        reset_estimate_state("ns")
        new_study_dialog()

    if not studies:
        with st.container(border=True):
            st.markdown("#### No studies yet")
            st.write("Add a property to see what a study could save you. It takes about a minute.")
            if st.button("Add your first property", type="primary"):
                reset_estimate_state("ns")
                new_study_dialog()
        return

    calcs = {s["id"]: calc_for_study(s) for s in studies}
    valid = [c for c in calcs.values() if c]
    k = st.columns(4)
    kpi(k[0], "Properties", f"{len(studies)}")
    kpi(k[1], "Depreciable basis", money(sum(c["basis"] for c in valid)))
    kpi(k[2], "Extra deductions identified", money(sum(c["extra"] for c in valid)), tone="good")
    kpi(k[3], "Estimated federal tax savings", money(sum(c["savings"] for c in valid)), tone="good")
    st.write("")

    table = pd.DataFrame([{
        "Property": s["address"], "Type": s["property_type"], "Purchased": fmt_date(s["acquired_on"]),
        "Service": s["tier"], "Status": s["status"],
        "Extra deduction": (calcs[s["id"]] or {}).get("extra"),
    } for s in studies])
    st.dataframe(table, hide_index=True, use_container_width=True, column_config=money_cols(["Extra deduction"]))

    ids = [s["id"] for s in studies]
    goto = st.session_state.pop("inv_goto", None)
    if goto in ids:
        st.session_state["inv_sel"] = goto
    if st.session_state.get("inv_sel") not in ids:
        st.session_state["inv_sel"] = ids[0]
    by_id = {s["id"]: s for s in studies}
    sid = st.selectbox("Open a study", ids, key="inv_sel", format_func=lambda i: by_id[i]["address"])
    study_detail(by_id[sid], calcs[sid])


def study_detail(s, calc):
    st.markdown(f"### {esc(s['address'])}")
    study_stepper(s["status"])
    reports = list_documents("study", s["id"], kind="report")
    if reports:
        with st.container(border=True):
            st.markdown("#### Your report is ready")
            render_documents(reports, f"rep_{s['id']}")

    if calc:
        a, b = st.columns([1, 1], gap="large")
        with a:
            headline_result(calc)
        with b:
            st.markdown("**Total deducted over 10 years**")
            savings_chart(calc)

    tabs = st.tabs(["Next steps", "Documents", "Depreciation schedule", "Edit details"])
    with tabs[0]:
        study_next_steps(s, calc)
    with tabs[1]:
        st.write("Upload your closing statement (HUD-1 or ALTA), plus photos, plans, appraisal, "
                 "and invoices for any improvements.")
        upk = st.session_state.setdefault(f"upk_{s['id']}", 0)
        with st.form(f"up_form_{s['id']}", border=False):
            files = st.file_uploader("Add files", accept_multiple_files=True, key=f"up_{s['id']}_{upk}",
                                     type=["pdf", "jpg", "jpeg", "png", "heic", "xlsx", "xls", "csv", "doc", "docx"])
            go = st.form_submit_button("Upload files", type="primary")
        if go and files:
            saved = sum(save_document("study", s["id"], "client_upload", f, st.session_state["user_email"])
                        for f in files)
            if saved:
                if s["status"] == "Submitted":
                    db_exec("UPDATE studies SET status='Documents received', updated_at=:t WHERE id=:id",
                            t=now_iso(), id=s["id"])
                notify_admins(f"Documents uploaded: {s['address']}",
                              f"<p>{esc(st.session_state['user_email'])} uploaded {saved} file(s) for "
                              f"<b>{esc(s['address'])}</b>.</p>")
                st.session_state[f"upk_{s['id']}"] = upk + 1
                st.rerun()
        render_documents(list_documents("study", s["id"], kind="client_upload"), f"cd_{s['id']}")
    with tabs[2]:
        if calc:
            df = schedule_frame(calc)
            st.dataframe(df, hide_index=True, use_container_width=True,
                         column_config={**money_cols(df.columns[1:]),
                                        "Tax year": st.column_config.NumberColumn(format="%d")})
            st.download_button("Download schedule (CSV)", df.to_csv(index=False).encode(),
                               file_name=f"depreciation_schedule_{s['id']}.csv", mime="text/csv")
            st.caption("Estimated schedule using MACRS half-year tables for 5-, 7- and 15-year property and "
                       "mid-month straight-line for the building. Your final report replaces these figures.")
    with tabs[3]:
        study_edit_form(s)


def study_next_steps(s, calc):
    status = s["status"]
    if status == "Estimate":
        st.write("This is an estimate. Order a study to have an engineer confirm the numbers and produce "
                 "a report your CPA can file.")
        names = [t["name"] for t in TIERS if t["price"]]
        rec = recommended_tier(calc["basis"]) if calc else names[0]
        tier = st.radio("Service level", names, index=names.index(rec), key=f"tier_{s['id']}", horizontal=True,
                        format_func=lambda n: f"{n} ({money(TIER_BY_NAME[n]['price'])})")
        st.caption(TIER_BY_NAME[tier]["desc"])
        c1, c2 = st.columns(2)
        if c1.button("Order this study", type="primary", key=f"order_{s['id']}", use_container_width=True):
            db_exec("UPDATE studies SET tier=:t, status='Submitted', updated_at=:u WHERE id=:id",
                    t=tier, u=now_iso(), id=s["id"])
            notify_admins(f"New study order: {s['address']}",
                          f"<p><b>{esc(s['owner_email'])}</b> ordered a <b>{esc(tier)}</b> for "
                          f"<b>{esc(s['address'])}</b>.</p>")
            st.rerun()
        if c2.button("Delete this estimate", key=f"del_{s['id']}", use_container_width=True):
            db_exec("DELETE FROM studies WHERE id=:id", id=s["id"])
            st.session_state.pop("inv_sel", None)
            st.rerun()
        return
    msgs = {
        "Submitted": "We received your order. Upload your closing statement in the Documents tab so the engineer can start.",
        "Documents received": "We have your documents. An engineer will contact you to schedule the review if your service includes a tour or site visit.",
        "Engineering review": "An engineer is reviewing the property. Your report usually follows within 1–2 weeks.",
        "Report delivered": "Your report is ready to download above. Share it with your CPA to file.",
    }
    st.write(msgs.get(status, ""))
    tier = TIER_BY_NAME.get(s["tier"])
    link = secret(tier["link_secret"]) if tier and tier.get("link_secret") else None
    if link and status in ("Submitted", "Documents received"):
        st.link_button(f"Pay for {tier['name']} ({money(tier['price'])})", link, type="primary")
    if s.get("notes"):
        st.info(s["notes"])


def study_edit_form(s):
    locked = s["status"] not in ("Estimate", "Submitted")
    if locked:
        st.caption("Details are locked while the engineer works on the study. Email us if something changed.")
    with st.form(f"edit_{s['id']}"):
        a, b = st.columns(2)
        addr = a.text_input("Address", s["address"], disabled=locked)
        types = list(PROPERTY_TYPES)
        ptype = b.selectbox("Property type", types,
                            index=types.index(s["property_type"]) if s["property_type"] in types else 0,
                            disabled=locked)
        c, d, e = st.columns(3)
        price = c.number_input("Purchase price", value=float(s["purchase_price"] or 0), min_value=0.0, step=5000.0,
                               format="%.0f", disabled=locked)
        closing = d.number_input("Closing costs", value=float(s["closing_costs"] or 0), min_value=0.0, step=500.0,
                                 format="%.0f", disabled=locked)
        improve = e.number_input("Improvements", value=float(s["improvements"] or 0), min_value=0.0, step=1000.0,
                                 format="%.0f", disabled=locked)
        f, g, h = st.columns(3)
        acq = f.date_input("Purchase date", parse_date(s["acquired_on"]) or TODAY, min_value=dt.date(1987, 1, 1),
                           format="MM/DD/YYYY", disabled=locked)
        pis = g.date_input("Placed in service", parse_date(s["in_service_on"]) or parse_date(s["acquired_on"]) or TODAY,
                           min_value=dt.date(1987, 1, 1), format="MM/DD/YYYY", disabled=locked)
        land = h.slider("Land %", 0, 60, int(s["land_pct"] or 20), disabled=locked)
        i, j = st.columns(2)
        rate_lbl = f"{(s['tax_rate'] or 0.37) * 100:.0f}%"
        rate = i.selectbox("Federal tax bracket", TAX_RATES,
                           index=TAX_RATES.index(rate_lbl) if rate_lbl in TAX_RATES else len(TAX_RATES) - 1)
        bonus = j.selectbox("Bonus depreciation", BONUS_OPTIONS,
                            index=BONUS_OPTIONS.index(s["bonus_mode"]) if s["bonus_mode"] in BONUS_OPTIONS else 0,
                            disabled=locked)
        if st.form_submit_button("Save changes", type="primary"):
            db_exec(
                """UPDATE studies SET address=:a, property_type=:pt, purchase_price=:p, closing_costs=:c,
                       improvements=:i, acquired_on=:acq, in_service_on=:pis, land_pct=:l, tax_rate=:r,
                       bonus_mode=:b, updated_at=:u WHERE id=:id""",
                a=addr, pt=ptype, p=price, c=closing, i=improve, acq=str(acq),
                pis=str(pis) if pis != acq else None, l=land, r=float(rate.rstrip("%")) / 100, b=bonus,
                u=now_iso(), id=s["id"],
            )
            st.success("Changes saved.")
            st.rerun()


# ============================================================================
# VIEW: RESIDENT PORTAL
# ============================================================================
def tenant_record(email):
    return db_one(
        """SELECT t.*, u.label AS unit_label, p.name AS property_name, p.address AS property_address
           FROM tenants t LEFT JOIN units u ON u.id = t.unit_id LEFT JOIN properties p ON p.id = u.property_id
           WHERE t.email = :e AND t.status = 'Active' ORDER BY t.created_at DESC""", e=email)


def rent_status(t, period):
    paid = db_one("SELECT COALESCE(SUM(amount), 0) AS s FROM payments WHERE tenant_id=:t AND period=:p",
                  t=t["id"], p=period)["s"] or 0
    rent = t["rent"] or 0
    balance = rent - paid
    if balance <= 0:
        label = "Paid"
    elif paid > 0:
        label = "Partial"
    elif period == TODAY.strftime("%Y-%m") and TODAY.day <= int(t["due_day"] or 1):
        label = "Due"
    else:
        label = "Overdue"
    return rent, paid, balance, label


def view_tenant():
    t = tenant_record(st.session_state["user_email"])
    if not t:
        st.warning("We couldn't find an active lease for this email. Contact management if you think this is a mistake.")
        return
    where = " ".join(x for x in [t.get("property_name"), t.get("unit_label")] if x)
    st.markdown(f"## Welcome home, {esc((t['name'] or 'Resident').split(' ')[0])}")
    st.markdown(f"<span class='tf-muted'>{esc(where)}{' — ' + esc(t['property_address']) if t.get('property_address') else ''}</span>",
                unsafe_allow_html=True)
    st.write("")
    period = TODAY.strftime("%Y-%m")
    rent, paid, balance, label = rent_status(t, period)
    lease_end = parse_date(t["lease_end"])
    k = st.columns(4)
    kpi(k[0], f"{period_label(period)} rent", money(rent), f"Due on day {t['due_day'] or 1}")
    kpi(k[1], "Paid this month", money(paid), label, tone="good" if label == "Paid" else "")
    kpi(k[2], "Balance", money(max(balance, 0)), "", tone="warn" if label == "Overdue" else "")
    kpi(k[3], "Lease ends", fmt_date(lease_end),
        f"{(lease_end - TODAY).days} days left" if lease_end and lease_end >= TODAY else "")
    st.write("")

    tabs = st.tabs(["Repairs", "Rent", "Lease", "Contacts"])
    with tabs[0]:
        emergency = secret("EMERGENCY_PHONE", BRAND["phone"])
        st.info(f"For fire, gas smell or active flooding, call 911 first, then our emergency line at {emergency}.")
        wk = st.session_state.setdefault("wo_formkey", 0)
        with st.form(f"wo_form_{wk}"):
            a, b = st.columns(2)
            cat = a.selectbox("What needs attention?", WO_CATEGORIES)
            pri = b.selectbox("How urgent is it?", WO_PRIORITIES, index=2,
                              help="Emergency: active leak, no heat in freezing weather, no power, security issue.")
            desc = st.text_area("Describe the problem", placeholder="What's happening, where, and since when?")
            access = st.text_input("Access notes (optional)", placeholder="Best times, pets, OK to enter if I'm not home?")
            photos = st.file_uploader("Photos (optional)", type=["jpg", "jpeg", "png", "heic"], accept_multiple_files=True)
            go = st.form_submit_button("Submit request", type="primary")
        if go:
            if not desc or len(desc.strip()) < 5:
                st.error("Add a short description so the technician knows what to bring.")
            else:
                wid, ts = new_id(), now_iso()
                db_exec("""INSERT INTO work_orders (id, unit_id, tenant_id, category, priority, description,
                               access_notes, status, contractor_id, cost, notes, created_at, updated_at)
                           VALUES (:id, :u, :t, :c, :p, :d, :a, 'New', NULL, NULL, '', :ts, :ts)""",
                        id=wid, u=t["unit_id"], t=t["id"], c=cat, p=pri, d=desc.strip(), a=access, ts=ts)
                for f in photos or []:
                    save_document("work_order", wid, "photo", f, t["email"])
                notify_admins(f"[{pri}] {cat} request: {where}",
                              f"<p><b>{esc(t['name'])}</b> ({esc(where)}) reported:</p><p>{esc(desc)}</p>"
                              f"<p>Access: {esc(access or 'Not specified')}</p>")
                st.session_state["wo_formkey"] = wk + 1
                st.session_state["wo_flash"] = f"Request #{wid[:6].upper()} submitted. We'll update you here and by email."
                st.rerun()
        if st.session_state.get("wo_flash"):
            st.success(st.session_state.pop("wo_flash"))
        st.markdown("#### Your requests")
        wos = db_all("SELECT * FROM work_orders WHERE tenant_id=:t ORDER BY created_at DESC", t=t["id"])
        if not wos:
            st.caption("No requests yet.")
        for w in wos:
            with st.container(border=True):
                st.markdown(f"**{esc(w['category'])}** {pill(w['status'], status_tone(w['status']))} "
                            f"<span class='tf-muted'>#{w['id'][:6].upper()}, opened {fmt_date(w['created_at'])}</span>",
                            unsafe_allow_html=True)
                st.write(w["description"])
    with tabs[1]:
        instructions = secret("PAYMENT_INSTRUCTIONS",
                              f"Contact {BRAND['email']} for payment options. Include your unit in the memo.")
        st.markdown("#### How to pay")
        st.write(instructions)
        link = secret("RENT_PAYMENT_LINK")
        if link:
            st.link_button("Pay rent online", link, type="primary")
        st.markdown("#### Payment history")
        pays = db_all("SELECT period, amount, paid_on, method FROM payments WHERE tenant_id=:t ORDER BY paid_on DESC",
                      t=t["id"])
        if pays:
            df = pd.DataFrame(pays)
            df["period"] = df["period"].map(period_label)
            df["paid_on"] = df["paid_on"].map(fmt_date)
            df.columns = ["For", "Amount", "Paid on", "Method"]
            st.dataframe(df, hide_index=True, use_container_width=True, column_config=money_cols(["Amount"]))
        else:
            st.caption("No payments recorded yet.")
    with tabs[2]:
        c = st.columns(3)
        kpi(c[0], "Lease start", fmt_date(t["lease_start"]))
        kpi(c[1], "Monthly rent", money(t["rent"]))
        kpi(c[2], "Security deposit", money(t["deposit"]))
        st.markdown("#### Lease documents")
        render_documents(list_documents("tenant", t["id"]), f"lease_{t['id']}")
    with tabs[3]:
        st.markdown(f"**Management office**  \n{BRAND['email']}  \n{BRAND['phone']}")
        st.markdown(f"**After-hours emergencies**  \n{secret('EMERGENCY_PHONE', BRAND['phone'])}")


# ============================================================================
# VIEW: CONTRACTOR
# ============================================================================
def work_order_rows(where_sql="1=1", **params):
    return db_all(
        f"""SELECT w.*, u.label AS unit_label, p.name AS property_name, p.address AS property_address,
                   t.name AS tenant_name, t.phone AS tenant_phone, t.email AS tenant_email,
                   c.name AS contractor_name, c.email AS contractor_email
            FROM work_orders w
            LEFT JOIN units u ON u.id = w.unit_id
            LEFT JOIN properties p ON p.id = u.property_id
            LEFT JOIN tenants t ON t.id = w.tenant_id
            LEFT JOIN contractors c ON c.id = w.contractor_id
            WHERE {where_sql} ORDER BY w.created_at DESC""", **params)


def notify_tenant_status(w, new_status):
    if w.get("tenant_email") and new_status != w["status"]:
        send_email(w["tenant_email"], f"Update on your {w['category'].lower()} request",
                   f"<p>Your request #{w['id'][:6].upper()} is now <b>{esc(new_status)}</b>.</p>{app_link()}")


def view_contractor():
    c = db_one("SELECT * FROM contractors WHERE email=:e", e=st.session_state["user_email"])
    if not c:
        st.warning("This email isn't registered as a contractor.")
        return
    st.markdown(f"## Work orders for {esc(c['company'] or c['name'])}")
    show_done = st.toggle("Show completed jobs", value=False)
    statuses = WO_STATUSES if show_done else WO_OPEN
    wos = [w for w in work_order_rows("w.contractor_id = :cid", cid=c["id"]) if w["status"] in statuses]
    if not wos:
        st.info("No open jobs right now.")
    for w in wos:
        title = f"{w['priority']} — {w['category']} at {w.get('property_name') or ''} {w.get('unit_label') or ''}"
        with st.expander(title, expanded=w["priority"] in ("Emergency", "Urgent")):
            st.markdown(f"{pill(w['status'], status_tone(w['status']))} <span class='tf-muted'>Opened "
                        f"{fmt_date(w['created_at'])}</span>", unsafe_allow_html=True)
            st.write(w["description"])
            st.markdown(f"**Address:** {esc(w.get('property_address') or '—')}  \n"
                        f"**Resident:** {esc(w.get('tenant_name') or '—')} {esc(w.get('tenant_phone') or '')}  \n"
                        f"**Access:** {esc(w.get('access_notes') or 'Not specified')}")
            render_documents(list_documents("work_order", w["id"]), f"cw_{w['id']}", show_images=True)
            with st.form(f"cwo_{w['id']}"):
                a, b = st.columns(2)
                opts = ["Assigned", "In progress", "Completed"]
                new_status = a.selectbox("Status", opts, index=opts.index(w["status"]) if w["status"] in opts else 0)
                cost = b.number_input("Cost to date", value=float(w["cost"] or 0), min_value=0.0, step=25.0,
                                      format="%.2f")
                notes = st.text_area("Notes for management", value=w["notes"] or "")
                if st.form_submit_button("Save update", type="primary"):
                    db_exec("UPDATE work_orders SET status=:s, cost=:c, notes=:n, updated_at=:u WHERE id=:id",
                            s=new_status, c=cost, n=notes, u=now_iso(), id=w["id"])
                    notify_tenant_status(w, new_status)
                    notify_admins(f"Work order {new_status.lower()}: {w['category']}",
                                  f"<p>{esc(c['name'])} set #{w['id'][:6].upper()} to <b>{esc(new_status)}</b>. "
                                  f"Cost: {money(cost)}.</p><p>{esc(notes)}</p>")
                    st.rerun()


# ============================================================================
# VIEW: MANAGEMENT CONSOLE (admin)
# ============================================================================
def units_with_occupancy():
    return db_all(
        """SELECT u.*, p.name AS property_name, p.address AS property_address,
                  t.id AS tenant_id, t.name AS tenant_name, t.email AS tenant_email, t.rent AS lease_rent,
                  t.lease_end AS lease_end
           FROM units u
           LEFT JOIN properties p ON p.id = u.property_id
           LEFT JOIN tenants t ON t.unit_id = u.id AND t.status = 'Active'
           ORDER BY p.name, u.label""")


def active_tenants():
    return db_all(
        """SELECT t.*, u.label AS unit_label, p.name AS property_name
           FROM tenants t LEFT JOIN units u ON u.id = t.unit_id LEFT JOIN properties p ON p.id = u.property_id
           WHERE t.status = 'Active' ORDER BY p.name, u.label""")


def unit_label(u):
    return f"{u.get('property_name') or 'Property'} — {u.get('label') or 'Unit'}"


def view_admin():
    st.markdown("## Management console")
    tabs = st.tabs(["Overview", "Properties", "Residents", "Rent", "Maintenance", "Contractors", "Cost seg", "Leads"])
    with tabs[0]:
        admin_overview()
    with tabs[1]:
        admin_properties()
    with tabs[2]:
        admin_residents()
    with tabs[3]:
        admin_rent()
    with tabs[4]:
        admin_maintenance()
    with tabs[5]:
        admin_contractors()
    with tabs[6]:
        admin_costseg()
    with tabs[7]:
        admin_leads()


def admin_overview():
    units = units_with_occupancy()
    tenants = active_tenants()
    period = TODAY.strftime("%Y-%m")
    rent_rows = [(t, *rent_status(t, period)) for t in tenants]
    due = sum(r[1] for r in rent_rows)
    collected = sum(r[2] for r in rent_rows)
    open_wos = work_order_rows("w.status IN ('New','Assigned','In progress')")
    soon = (TODAY + dt.timedelta(days=60)).isoformat()
    expiring = [t for t in tenants if t["lease_end"] and TODAY.isoformat() <= t["lease_end"][:10] <= soon]
    studies_open = db_one("SELECT COUNT(*) AS n FROM studies WHERE status NOT IN ('Estimate','Report delivered')")["n"]
    leads_30 = db_one("SELECT COUNT(*) AS n FROM leads WHERE created_at >= :d",
                      d=(dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)).isoformat(timespec="seconds"))["n"]
    occupied = sum(1 for u in units if u["tenant_id"])

    k = st.columns(4)
    kpi(k[0], "Occupancy", f"{occupied}/{len(units)}" if units else "—",
        f"{occupied / len(units) * 100:.0f}% occupied" if units else "Add units to start")
    kpi(k[1], f"Collected, {period_label(period)}", money(collected), f"of {money(due)} due",
        tone="good" if due and collected >= due else "")
    kpi(k[2], "Open work orders", str(len(open_wos)),
        f"{sum(1 for w in open_wos if w['priority'] in ('Emergency', 'Urgent'))} urgent or emergency",
        tone="warn" if any(w["priority"] == "Emergency" for w in open_wos) else "")
    kpi(k[3], "Cost seg pipeline", str(studies_open), f"{leads_30} new leads in 30 days")
    st.write("")

    a, b = st.columns(2, gap="large")
    with a:
        st.markdown("#### Rent not yet paid")
        late = [r for r in rent_rows if r[4] in ("Overdue", "Partial", "Due")]
        if late:
            st.dataframe(pd.DataFrame([{"Resident": r[0]["name"], "Unit": f"{r[0]['property_name'] or ''} {r[0]['unit_label'] or ''}",
                                        "Balance": r[3], "Status": r[4]} for r in late]),
                         hide_index=True, use_container_width=True, column_config=money_cols(["Balance"]))
        else:
            st.caption("Everyone is paid up for this month.")
        st.markdown("#### Leases ending in 60 days")
        if expiring:
            st.dataframe(pd.DataFrame([{"Resident": t["name"], "Unit": f"{t['property_name'] or ''} {t['unit_label'] or ''}",
                                        "Ends": fmt_date(t["lease_end"])} for t in expiring]),
                         hide_index=True, use_container_width=True)
        else:
            st.caption("No leases ending soon.")
    with b:
        st.markdown("#### Open work orders")
        if open_wos:
            st.dataframe(pd.DataFrame([{"Priority": w["priority"], "Issue": w["category"],
                                        "Unit": f"{w['property_name'] or ''} {w['unit_label'] or ''}",
                                        "Status": w["status"], "Assigned": w["contractor_name"] or "—",
                                        "Opened": fmt_date(w["created_at"])} for w in open_wos]),
                         hide_index=True, use_container_width=True)
        else:
            st.caption("No open work orders.")


def admin_properties():
    props = db_all("SELECT * FROM properties ORDER BY name")
    a, b = st.columns(2, gap="large")
    with a:
        st.markdown("#### Add a property")
        with st.form("add_prop", clear_on_submit=True):
            name = st.text_input("Name", placeholder="Lakeway Duplex")
            addr = st.text_input("Address", placeholder="3326 Lakeway Ln, Pearland, TX 77584")
            ptype = st.selectbox("Type", list(PROPERTY_TYPES))
            if st.form_submit_button("Add property", type="primary"):
                if not name or not addr:
                    st.error("Add a name and address.")
                else:
                    db_exec("INSERT INTO properties (id, name, address, property_type, notes, created_at) "
                            "VALUES (:id, :n, :a, :t, '', :ts)", id=new_id(), n=name, a=addr, t=ptype, ts=now_iso())
                    st.rerun()
    with b:
        st.markdown("#### Add a unit")
        if not props:
            st.caption("Add a property first.")
        else:
            with st.form("add_unit", clear_on_submit=True):
                pid = st.selectbox("Property", [p["id"] for p in props],
                                   format_func=lambda i: next(p["name"] for p in props if p["id"] == i))
                label = st.text_input("Unit", placeholder="Unit A, or Main house")
                c1, c2, c3 = st.columns(3)
                beds = c1.number_input("Beds", min_value=0.0, step=1.0, value=2.0)
                baths = c2.number_input("Baths", min_value=0.0, step=0.5, value=1.0)
                mrent = c3.number_input("Market rent", min_value=0.0, step=50.0, format="%.0f")
                if st.form_submit_button("Add unit", type="primary"):
                    db_exec("INSERT INTO units (id, property_id, label, beds, baths, market_rent, created_at) "
                            "VALUES (:id, :p, :l, :b, :ba, :r, :ts)",
                            id=new_id(), p=pid, l=label or "Main", b=beds, ba=baths, r=mrent, ts=now_iso())
                    st.rerun()

    units = units_with_occupancy()
    st.markdown("#### Units")
    if units:
        st.dataframe(pd.DataFrame([{
            "Property": u["property_name"], "Unit": u["label"], "Beds": u["beds"], "Baths": u["baths"],
            "Market rent": u["market_rent"], "Resident": u["tenant_name"] or "Vacant",
            "Lease rent": u["lease_rent"], "Lease ends": fmt_date(u["lease_end"]) if u["lease_end"] else "—",
        } for u in units]), hide_index=True, use_container_width=True,
            column_config=money_cols(["Market rent", "Lease rent"]))
        with st.expander("Edit a unit"):
            uid = st.selectbox("Unit", [u["id"] for u in units],
                               format_func=lambda i: unit_label(next(u for u in units if u["id"] == i)), key="edit_unit_sel")
            u = next(x for x in units if x["id"] == uid)
            with st.form(f"edit_unit_{uid}"):
                label = st.text_input("Unit", u["label"])
                c1, c2, c3 = st.columns(3)
                beds = c1.number_input("Beds", value=float(u["beds"] or 0), min_value=0.0, step=1.0)
                baths = c2.number_input("Baths", value=float(u["baths"] or 0), min_value=0.0, step=0.5)
                mrent = c3.number_input("Market rent", value=float(u["market_rent"] or 0), min_value=0.0, step=50.0,
                                        format="%.0f")
                s1, s2 = st.columns(2)
                if s1.form_submit_button("Save unit", type="primary"):
                    db_exec("UPDATE units SET label=:l, beds=:b, baths=:ba, market_rent=:r WHERE id=:id",
                            l=label, b=beds, ba=baths, r=mrent, id=uid)
                    st.rerun()
                if s2.form_submit_button("Delete unit"):
                    if u["tenant_id"]:
                        st.error("End the active lease on this unit before deleting it.")
                    else:
                        db_exec("DELETE FROM units WHERE id=:id", id=uid)
                        st.rerun()
    else:
        st.caption("No units yet.")


def admin_residents():
    units = units_with_occupancy()
    a, b = st.columns([1.1, 0.9], gap="large")
    with a:
        st.markdown("#### Add a resident and lease")
        if not units:
            st.caption("Add a property and unit first.")
        else:
            with st.form("add_tenant", clear_on_submit=True):
                uid = st.selectbox("Unit", [u["id"] for u in units],
                                   format_func=lambda i: (lambda u: unit_label(u) + ("" if not u["tenant_id"] else
                                                          f" (occupied by {u['tenant_name']})"))(
                                       next(x for x in units if x["id"] == i)))
                c1, c2 = st.columns(2)
                name = c1.text_input("Full name")
                email = c2.text_input("Email (used to sign in)")
                c3, c4, c5 = st.columns(3)
                phone = c3.text_input("Phone")
                rent = c4.number_input("Monthly rent", min_value=0.0, step=50.0, format="%.0f")
                deposit = c5.number_input("Deposit", min_value=0.0, step=50.0, format="%.0f")
                c6, c7, c8 = st.columns(3)
                start = c6.date_input("Lease start", TODAY, format="MM/DD/YYYY")
                end = c7.date_input("Lease end", TODAY + dt.timedelta(days=365), format="MM/DD/YYYY")
                due_day = c8.number_input("Rent due day", min_value=1, max_value=28, value=1, step=1)
                welcome = st.checkbox("Email a welcome note with the portal link", value=True)
                if st.form_submit_button("Add resident", type="primary"):
                    e = (email or "").strip().lower()
                    if not name or not valid_email(e):
                        st.error("Add the resident's name and a valid email.")
                    elif end <= start:
                        st.error("The lease end must be after the start.")
                    else:
                        db_exec("""INSERT INTO tenants (id, email, name, phone, unit_id, lease_start, lease_end, rent,
                                       deposit, due_day, status, created_at)
                                   VALUES (:id, :e, :n, :ph, :u, :s, :end, :r, :d, :dd, 'Active', :ts)""",
                                id=new_id(), e=e, n=name.strip(), ph=phone, u=uid, s=str(start), end=str(end),
                                r=rent, d=deposit, dd=int(due_day), ts=now_iso())
                        if welcome:
                            send_email(e, f"Your resident portal at {BRAND['name']}",
                                       f"<p>Hi {esc(name.split(' ')[0])},</p><p>You can now pay rent, request "
                                       f"repairs and find your lease online. Sign in with this email address; we'll "
                                       f"send you a one-time code each time.</p>{app_link('Open the resident portal')}")
                        st.rerun()
    with b:
        st.markdown("#### End a lease")
        tenants = active_tenants()
        if tenants:
            with st.form("end_lease"):
                tid = st.selectbox("Resident", [t["id"] for t in tenants],
                                   format_func=lambda i: next(f"{t['name']} ({t['property_name'] or ''} {t['unit_label'] or ''})"
                                                              for t in tenants if t["id"] == i))
                if st.form_submit_button("Mark as moved out"):
                    db_exec("UPDATE tenants SET status='Past' WHERE id=:id", id=tid)
                    st.rerun()
            st.markdown("#### Upload a lease document")
            lk = st.session_state.setdefault("lease_upk", 0)
            with st.form("lease_upload"):
                tid2 = st.selectbox("Resident", [t["id"] for t in tenants], key="lease_doc_tenant",
                                    format_func=lambda i: next(t["name"] for t in tenants if t["id"] == i))
                f = st.file_uploader("Lease or addendum (PDF)", type=["pdf", "docx", "jpg", "png"], key=f"lease_file_{lk}")
                if st.form_submit_button("Upload", type="primary") and f:
                    if save_document("tenant", tid2, "lease", f, st.session_state["user_email"]):
                        st.session_state["lease_upk"] = lk + 1
                        st.rerun()
        else:
            st.caption("No active residents.")

    st.markdown("#### Active residents")
    tenants = active_tenants()
    if tenants:
        st.dataframe(pd.DataFrame([{
            "Name": t["name"], "Email": t["email"], "Phone": t["phone"],
            "Unit": f"{t['property_name'] or ''} {t['unit_label'] or ''}", "Rent": t["rent"],
            "Lease start": fmt_date(t["lease_start"]), "Lease end": fmt_date(t["lease_end"]),
        } for t in tenants]), hide_index=True, use_container_width=True, column_config=money_cols(["Rent"]))

    with st.expander("Import residents from CSV"):
        st.caption("Columns: email, name, property, unit. Optional: phone, rent, lease_start, lease_end. "
                   "Missing properties and units are created.")
        up = st.file_uploader("CSV file", type=["csv"], key="tenant_csv")
        if up is not None and st.button("Import residents", type="primary"):
            try:
                df = pd.read_csv(up)
            except Exception as exc:  # noqa: BLE001
                st.error(f"That file couldn't be read as CSV: {exc}")
                return
            df.columns = [c.strip().lower() for c in df.columns]
            missing = {"email", "name", "property", "unit"} - set(df.columns)
            if missing:
                st.error(f"Missing columns: {', '.join(sorted(missing))}")
                return
            added = 0
            for _, r in df.iterrows():
                e = str(r["email"]).strip().lower()
                if not valid_email(e) or db_one("SELECT id FROM tenants WHERE email=:e AND status='Active'", e=e):
                    continue
                prop = db_one("SELECT id FROM properties WHERE name=:n", n=str(r["property"]))
                pid = prop["id"] if prop else new_id()
                if not prop:
                    db_exec("INSERT INTO properties (id, name, address, property_type, notes, created_at) "
                            "VALUES (:id, :n, '', 'Single-family rental', '', :ts)", id=pid, n=str(r["property"]), ts=now_iso())
                unit = db_one("SELECT id FROM units WHERE property_id=:p AND label=:l", p=pid, l=str(r["unit"]))
                uid = unit["id"] if unit else new_id()
                if not unit:
                    db_exec("INSERT INTO units (id, property_id, label, beds, baths, market_rent, created_at) "
                            "VALUES (:id, :p, :l, NULL, NULL, NULL, :ts)", id=uid, p=pid, l=str(r["unit"]), ts=now_iso())
                get = lambda c: (None if c not in df.columns or pd.isna(r[c]) else r[c])  # noqa: E731
                db_exec("""INSERT INTO tenants (id, email, name, phone, unit_id, lease_start, lease_end, rent, deposit,
                               due_day, status, created_at)
                           VALUES (:id, :e, :n, :ph, :u, :s, :end, :r, NULL, 1, 'Active', :ts)""",
                        id=new_id(), e=e, n=str(r["name"]), ph=get("phone"), u=uid,
                        s=str(parse_date(get("lease_start")) or "") or None,
                        end=str(parse_date(get("lease_end")) or "") or None,
                        r=float(get("rent")) if get("rent") is not None else None, ts=now_iso())
                added += 1
            st.success(f"Imported {added} resident(s).")


def admin_rent():
    tenants = active_tenants()
    periods = recent_periods(12)
    period = st.selectbox("Month", periods, format_func=period_label, key="rent_period")
    rows = []
    for t in tenants:
        rent, paid, balance, label = rent_status(t, period)
        rows.append({"Resident": t["name"], "Unit": f"{t['property_name'] or ''} {t['unit_label'] or ''}",
                     "Rent": rent, "Paid": paid, "Balance": max(balance, 0), "Status": label})
    if rows:
        df = pd.DataFrame(rows)
        k = st.columns(3)
        kpi(k[0], "Rent due", money(df["Rent"].sum()))
        kpi(k[1], "Collected", money(df["Paid"].sum()), tone="good")
        kpi(k[2], "Outstanding", money(df["Balance"].sum()), tone="warn" if df["Balance"].sum() > 0 else "")
        st.write("")
        st.dataframe(df, hide_index=True, use_container_width=True, column_config=money_cols(["Rent", "Paid", "Balance"]))
        st.download_button("Download rent roll (CSV)", df.to_csv(index=False).encode(),
                           file_name=f"rent_roll_{period}.csv", mime="text/csv")
    else:
        st.caption("No active residents yet.")
        return

    st.markdown("#### Record a payment")
    with st.form("record_payment", clear_on_submit=True):
        c1, c2 = st.columns(2)
        tid = c1.selectbox("Resident", [t["id"] for t in tenants],
                           format_func=lambda i: next(f"{t['name']} ({t['property_name'] or ''} {t['unit_label'] or ''})"
                                                      for t in tenants if t["id"] == i))
        pper = c2.selectbox("Applies to", periods, format_func=period_label)
        c3, c4, c5 = st.columns(3)
        amount = c3.number_input("Amount", min_value=0.0, step=50.0, format="%.2f")
        paid_on = c4.date_input("Received on", TODAY, format="MM/DD/YYYY")
        method = c5.selectbox("Method", PAY_METHODS)
        note = st.text_input("Note (optional)")
        receipt = st.checkbox("Email a receipt to the resident", value=True)
        if st.form_submit_button("Record payment", type="primary"):
            if amount <= 0:
                st.error("Enter the amount received.")
            else:
                db_exec("INSERT INTO payments (id, tenant_id, period, amount, paid_on, method, note, created_at) "
                        "VALUES (:id, :t, :p, :a, :d, :m, :n, :ts)",
                        id=new_id(), t=tid, p=pper, a=amount, d=str(paid_on), m=method, n=note, ts=now_iso())
                t = next(x for x in tenants if x["id"] == tid)
                if receipt:
                    send_email(t["email"], f"Payment received for {period_label(pper)}",
                               f"<p>We received {money(amount)} by {esc(method)} on {fmt_date(paid_on)} for "
                               f"{period_label(pper)} rent. Thank you.</p>")
                st.rerun()


def admin_maintenance():
    contractors = db_all("SELECT * FROM contractors ORDER BY name")
    tenants = active_tenants()
    with st.expander("Create a work order"):
        units = units_with_occupancy()
        if not units:
            st.caption("Add a unit first.")
        else:
            with st.form("admin_new_wo", clear_on_submit=True):
                uid = st.selectbox("Unit", [u["id"] for u in units],
                                   format_func=lambda i: unit_label(next(u for u in units if u["id"] == i)))
                c1, c2 = st.columns(2)
                cat = c1.selectbox("Category", WO_CATEGORIES)
                pri = c2.selectbox("Priority", WO_PRIORITIES, index=2)
                desc = st.text_area("Description")
                if st.form_submit_button("Create work order", type="primary") and desc:
                    u = next(x for x in units if x["id"] == uid)
                    ts = now_iso()
                    db_exec("""INSERT INTO work_orders (id, unit_id, tenant_id, category, priority, description,
                                   access_notes, status, contractor_id, cost, notes, created_at, updated_at)
                               VALUES (:id, :u, :t, :c, :p, :d, '', 'New', NULL, NULL, '', :ts, :ts)""",
                            id=new_id(), u=uid, t=u["tenant_id"], c=cat, p=pri, d=desc, ts=ts)
                    st.rerun()

    statuses = st.multiselect("Show", WO_STATUSES, default=WO_OPEN, key="wo_filter")
    wos = [w for w in work_order_rows() if w["status"] in statuses]
    order = {p: i for i, p in enumerate(WO_PRIORITIES)}
    wos.sort(key=lambda w: (order.get(w["priority"], 9), w["created_at"]))
    if not wos:
        st.caption("No work orders match this filter.")
    cmap = {c["id"]: c for c in contractors}
    for w in wos:
        title = f"{w['priority']} — {w['category']}, {w.get('property_name') or ''} {w.get('unit_label') or ''} ({w['status']})"
        with st.expander(title, expanded=w["priority"] == "Emergency" and w["status"] == "New"):
            st.markdown(f"<span class='tf-muted'>#{w['id'][:6].upper()}, opened {fmt_date(w['created_at'])}, "
                        f"reported by {esc(w.get('tenant_name') or 'management')}</span>", unsafe_allow_html=True)
            st.write(w["description"])
            if w.get("access_notes"):
                st.caption(f"Access: {w['access_notes']}")
            render_documents(list_documents("work_order", w["id"]), f"aw_{w['id']}", show_images=True)
            with st.form(f"awo_{w['id']}"):
                c1, c2, c3 = st.columns(3)
                c_ids = [None] + [c["id"] for c in contractors]
                cid = c1.selectbox("Contractor", c_ids,
                                   index=c_ids.index(w["contractor_id"]) if w["contractor_id"] in c_ids else 0,
                                   format_func=lambda i: "Unassigned" if i is None else
                                   f"{cmap[i]['name']} ({cmap[i]['trade'] or 'general'})")
                status = c2.selectbox("Status", WO_STATUSES, index=WO_STATUSES.index(w["status"]))
                cost = c3.number_input("Cost", value=float(w["cost"] or 0), min_value=0.0, step=25.0, format="%.2f")
                notes = st.text_area("Internal notes", value=w["notes"] or "")
                if st.form_submit_button("Save", type="primary"):
                    if cid and status == "New":
                        status = "Assigned"
                    db_exec("UPDATE work_orders SET contractor_id=:c, status=:s, cost=:co, notes=:n, updated_at=:u "
                            "WHERE id=:id", c=cid, s=status, co=cost, n=notes, u=now_iso(), id=w["id"])
                    if cid and cid != w["contractor_id"]:
                        send_email(cmap[cid]["email"], f"New job: {w['priority']} {w['category'].lower()}",
                                   f"<p>You've been assigned work order #{w['id'][:6].upper()} at "
                                   f"<b>{esc(w.get('property_address') or w.get('property_name') or '')}</b> "
                                   f"{esc(w.get('unit_label') or '')}.</p><p>{esc(w['description'])}</p>"
                                   f"{app_link('View the job')}")
                    notify_tenant_status(w, status)
                    st.rerun()


def admin_contractors():
    a, b = st.columns([0.9, 1.1], gap="large")
    with a:
        st.markdown("#### Add a contractor")
        with st.form("add_contractor", clear_on_submit=True):
            name = st.text_input("Contact name")
            company = st.text_input("Company")
            email = st.text_input("Email (used to sign in)")
            c1, c2 = st.columns(2)
            trade = c1.selectbox("Trade", ["General handyman"] + WO_CATEGORIES[:-1])
            phone = c2.text_input("Phone")
            if st.form_submit_button("Add contractor", type="primary"):
                e = (email or "").strip().lower()
                if not name or not valid_email(e):
                    st.error("Add a name and a valid email.")
                else:
                    db_exec("INSERT INTO contractors (id, email, name, company, trade, phone, created_at) "
                            "VALUES (:id, :e, :n, :c, :t, :p, :ts)",
                            id=new_id(), e=e, n=name, c=company, t=trade, p=phone, ts=now_iso())
                    st.rerun()
    with b:
        st.markdown("#### Contractors")
        rows = db_all("""SELECT c.name, c.company, c.trade, c.phone, c.email,
                                SUM(CASE WHEN w.status IN ('Assigned','In progress') THEN 1 ELSE 0 END) AS open_jobs,
                                COALESCE(SUM(w.cost), 0) AS billed
                         FROM contractors c LEFT JOIN work_orders w ON w.contractor_id = c.id
                         GROUP BY c.id, c.name, c.company, c.trade, c.phone, c.email ORDER BY c.name""")
        if rows:
            df = pd.DataFrame(rows)
            df.columns = ["Name", "Company", "Trade", "Phone", "Email", "Open jobs", "Total cost"]
            st.dataframe(df, hide_index=True, use_container_width=True, column_config=money_cols(["Total cost"]))
        else:
            st.caption("No contractors yet.")


def admin_costseg():
    studies = db_all("SELECT * FROM studies ORDER BY updated_at DESC")
    if not studies:
        st.caption("No studies yet.")
        return
    calcs = {s["id"]: calc_for_study(s) for s in studies}
    df = pd.DataFrame([{
        "Client": s["owner_email"], "Property": s["address"], "Service": s["tier"], "Status": s["status"],
        "Basis": (calcs[s["id"]] or {}).get("basis"), "Extra deduction": (calcs[s["id"]] or {}).get("extra"),
        "Updated": fmt_date(s["updated_at"]),
    } for s in studies])
    show_est = st.toggle("Include unpaid estimates", value=False)
    view = df if show_est else df[df["Status"] != "Estimate"]
    st.dataframe(view, hide_index=True, use_container_width=True, column_config=money_cols(["Basis", "Extra deduction"]))

    by_id = {s["id"]: s for s in studies}
    sid = st.selectbox("Work on a study", list(by_id), key="admin_study",
                       format_func=lambda i: f"{by_id[i]['address']} ({by_id[i]['owner_email']}, {by_id[i]['status']})")
    s, calc = by_id[sid], calcs[sid]
    study_stepper(s["status"])
    if calc:
        c = st.columns(4)
        kpi(c[0], "Depreciable basis", money(calc["basis"]))
        kpi(c[1], "Shorter-life property", money(calc["short_life"]), f"{calc['short_pct'] * 100:.0f}% of basis")
        kpi(c[2], f"Extra deduction {calc['tax_year']}", money(calc["extra"]), tone="good")
        kpi(c[3], "Bonus rate", f"{calc['bonus_rate'] * 100:.0f}%", "Catch-up via Form 3115" if calc["catch_up"] else "")
    st.markdown("#### Client documents")
    render_documents(list_documents("study", sid, kind="client_upload"), f"acd_{sid}")
    st.markdown("#### Update the study")
    rk = st.session_state.setdefault("report_upk", 0)
    with st.form(f"admin_study_{sid}"):
        c1, c2 = st.columns(2)
        status = c1.selectbox("Status", STUDY_FLOW, index=STUDY_FLOW.index(s["status"]) if s["status"] in STUDY_FLOW else 0)
        tier = c2.selectbox("Service", [t["name"] for t in TIERS],
                            index=[t["name"] for t in TIERS].index(s["tier"]) if s["tier"] in TIER_BY_NAME else 0)
        notes = st.text_area("Message shown to the client", value=s["notes"] or "")
        report = st.file_uploader("Final report (PDF)", type=["pdf", "xlsx"], key=f"report_{rk}")
        if st.form_submit_button("Save update", type="primary"):
            if report is not None:
                save_document("study", sid, "report", report, st.session_state["user_email"])
                st.session_state["report_upk"] = rk + 1
                if status != "Report delivered":
                    status = "Report delivered"
            db_exec("UPDATE studies SET status=:sts, tier=:t, notes=:n, updated_at=:u WHERE id=:id",
                    sts=status, t=tier, n=notes, u=now_iso(), id=sid)
            if status != s["status"]:
                send_email(s["owner_email"], f"Your cost segregation study: {status}",
                           f"<p>Your study for <b>{esc(s['address'])}</b> is now <b>{esc(status)}</b>.</p>"
                           + (f"<p>{esc(notes)}</p>" if notes else "") + app_link("View your study"))
            st.rerun()


def admin_leads():
    leads = db_all("SELECT email, address, purchase_price, est_deduction, est_savings, created_at FROM leads "
                   "ORDER BY created_at DESC")
    if not leads:
        st.caption("Leads appear here when visitors email themselves an estimate.")
        return
    df = pd.DataFrame(leads)
    df["created_at"] = df["created_at"].map(fmt_date)
    df.columns = ["Email", "Property", "Purchase price", "Extra deduction", "Est. savings", "Date"]
    st.dataframe(df, hide_index=True, use_container_width=True,
                 column_config=money_cols(["Purchase price", "Extra deduction", "Est. savings"]))
    st.download_button("Download leads (CSV)", df.to_csv(index=False).encode(), file_name="leads.csv", mime="text/csv")


# ============================================================================
# APP SHELL: state, navigation, routing, footer
# ============================================================================
st.session_state.setdefault("view", "landing")
keep_estimate_state()
restore_session()

user = st.session_state.get("user_email")
roles = st.session_state.get("roles", [])

nav_l, nav_r = st.columns([1.4, 1])
with nav_l:
    if st.button(BRAND["name"], key="nav_brand"):
        st.session_state["view"] = "landing"
        st.rerun()
with nav_r:
    if not user:
        _, signin = st.columns([1, 1])
        if signin.button("Sign in", type="primary", use_container_width=True):
            st.session_state["login_step"] = "email"
            login_dialog()
    else:
        c1, c2 = st.columns([1.6, 1])
        options = ["landing"] + roles
        current = st.session_state["view"] if st.session_state["view"] in options else roles[0]
        choice = c1.selectbox("Go to", options, index=options.index(current), label_visibility="collapsed",
                              format_func=lambda v: "Home" if v == "landing" else ROLE_LABEL[v])
        if choice != st.session_state["view"]:
            st.session_state["view"] = choice
            st.rerun()
        if c2.button("Sign out", use_container_width=True):
            sign_out()
            st.rerun()
st.markdown('<div class="tf-navline"></div>', unsafe_allow_html=True)

view = st.session_state["view"]
if user and view in roles:
    {"admin": view_admin, "tenant": view_tenant, "contractor": view_contractor, "investor": view_investor}[view]()
else:
    view_landing()

st.markdown(
    f"""
    <div class="tf-footer">
      <div class="cols">
        <div><div class="brand">{BRAND['name']}</div>
             <div>Cost segregation studies and property management.</div></div>
        <div><b>Email</b> {BRAND['email']}<br><b>Phone</b> {BRAND['phone']}</div>
      </div>
      <div class="fine">Estimates use typical allocations for each property type and current federal bonus
      depreciation rules; actual results depend on the engineering study. Not tax or legal advice. Coordinate
      with your CPA. © {TODAY.year} {BRAND['name']}.</div>
    </div>
    """,
    unsafe_allow_html=True,
)
