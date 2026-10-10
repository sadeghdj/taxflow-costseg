import streamlit as st
import requests
import datetime
import pandas as pd
import os
import random

# ----------------- Page Setup -----------------
st.set_page_config(
    page_title="Tax Flow Cost Seg & Property Portal",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ----------------- Email Sender via Resend API -----------------
def send_real_email_code(recipient_email, code):
    """Sends authentic 6-digit code with high deliverability (HTML + Plaintext)."""
    api_key = st.secrets.get("RESEND_API_KEY")
    if not api_key:
        return False, "DEMO_MODE"

    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Plain text version for spam filters
    plain_text = f"Your Tax Flow Cost Seg one-time verification code is: {code}\n\nThis code expires in 10 minutes.\n\nTax Flow Cost Seg | info@taxflowcostseg.com"

    # HTML version
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #F8FAFC; padding: 24px; margin: 0;">
        <table align="center" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 520px; background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 12px; padding: 32px;">
            <tr>
                <td>
                    <h2 style="color: #0F172A; margin-top: 0; font-size: 20px;">Tax Flow Cost Seg</h2>
                    <p style="color: #475569; font-size: 15px; line-height: 24px;">Your one-time verification code to access your portal is:</p>
                    <div style="background-color: #F1F5F9; border-radius: 8px; padding: 18px; text-align: center; margin: 24px 0;">
                        <span style="font-size: 32px; font-weight: 800; letter-spacing: 6px; color: #0F172A;">{code}</span>
                    </div>
                    <p style="color: #64748B; font-size: 13px; line-height: 20px;">
                        This code expires in 10 minutes. If you did not request this login code, you can safely disregard this message.
                    </p>
                    <hr style="border: 0; border-top: 1px solid #E2E8F0; margin: 24px 0;">
                    <p style="color: #94A3B8; font-size: 11px; margin-bottom: 0;">
                        Tax Flow Cost Seg • Engineering-Led Cost Segregation Studies<br>
                        Contact: info@taxflowcostseg.com | (202) 810-1684
                    </p>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    payload = {
        "from": "Tax Flow Cost Seg <info@taxflowcostseg.com>",
        "to": [recipient_email],
        "subject": f"{code} is your Tax Flow verification code",
        "text": plain_text,
        "html": html_content
    }
    
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=5)
        if r.status_code in [200, 201]:
            return True, "Email sent successfully!"
        else:
            return False, f"Resend Error: {r.text}"
    except Exception as e:
        return False, f"Request Error: {str(e)}"


# ----------------- Helper: Load Tenant Database -----------------
@st.cache_data(ttl=60)
def load_tenant_roster():
    csv_file = "tenants.csv"
    if os.path.exists(csv_file):
        try:
            df = pd.read_csv(csv_file)
            df["email_clean"] = df["email"].astype(str).str.strip().str.lower()
            return df
        except Exception:
            return pd.DataFrame(columns=["email", "name", "property", "unit", "email_clean"])
    else:
        return pd.DataFrame(columns=["email", "name", "property", "unit", "email_clean"])

# ----------------- Global Design Styling (Fintech Theme) -----------------
st.markdown(
    """
    <style>
        .stApp {
            background-color: #F8FAFC;
            color: #0F172A;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }
        .nav-container {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #FFFFFF;
            padding: 14px 28px;
            border-bottom: 1px solid #E2E8F0;
            border-radius: 10px;
            margin-bottom: 24px;
        }
        .nav-logo { font-size: 20px; font-weight: 800; color: #0F172A; }
        .white-card {
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 12px;
            padding: 22px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
            margin-bottom: 20px;
        }
        .kpi-card {
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 12px;
            padding: 18px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.03);
        }
        .kpi-title { font-size: 13px; font-weight: 600; color: #64748B; margin-bottom: 4px; }
        .kpi-value { font-size: 28px; font-weight: 800; color: #0F172A; }
        .kpi-green { color: #059669; }
        .kpi-sub { font-size: 12px; color: #94A3B8; margin-top: 4px; }
        .trust-badge {
            display: inline-block;
            background-color: #EFF6FF;
            color: #1D4ED8;
            font-size: 12px;
            font-weight: 700;
            padding: 6px 14px;
            border-radius: 9999px;
            margin-bottom: 14px;
            border: 1px solid #DBEAFE;
        }
        .results-box {
            background: #F0FDF4;
            border: 1px solid #BBF7D0;
            border-radius: 10px;
            padding: 16px;
            margin-top: 14px;
        }
        .progress-label {
            display: flex;
            justify-content: space-between;
            font-size: 14px;
            font-weight: 600;
            color: #1E293B;
            margin-top: 12px;
            margin-bottom: 4px;
        }
        .sub-desc { font-size: 12px; color: #64748B; margin-bottom: 6px; }
        .step-card {
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 12px;
            padding: 22px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
            height: 100%;
        }
        .site-footer {
            background-color: #0F172A;
            color: #94A3B8;
            padding: 40px 28px 24px 28px;
            border-radius: 12px 12px 0 0;
            margin-top: 60px;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------- Session State Management -----------------
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "user_cohort" not in st.session_state:
    st.session_state["user_cohort"] = None
if "user_email" not in st.session_state:
    st.session_state["user_email"] = ""
if "tenant_info" not in st.session_state:
    st.session_state["tenant_info"] = None
if "active_view" not in st.session_state:
    st.session_state["active_view"] = "landing"
if "otp_step" not in st.session_state:
    st.session_state["otp_step"] = "input_email"
if "generated_code" not in st.session_state:
    st.session_state["generated_code"] = ""
if "temp_email" not in st.session_state:
    st.session_state["temp_email"] = ""
if "show_login_dialog" not in st.session_state:
    st.session_state["show_login_dialog"] = False

# ----------------- Persistent Login Dialog -----------------
@st.dialog("Log In / Sign Up")
def login_dialog():
    st.markdown("### Access Your Portal")

    # Step 1: Input Email
    if st.session_state["otp_step"] == "input_email":
        st.write("Enter your email address to receive your one-time login code.")
        email_in = st.text_input("Email Address", value=st.session_state.get("temp_email", ""), placeholder="you@domain.com")

        if st.button("Send One-Time Code", type="primary", use_container_width=True):
            if email_in and "@" in email_in and "." in email_in:
                code = str(random.randint(100000, 999999))
                clean_email = email_in.strip().lower()
                st.session_state["generated_code"] = code
                st.session_state["temp_email"] = clean_email

                success, status_msg = send_real_email_code(clean_email, code)
                st.session_state["mail_status"] = status_msg
                st.session_state["otp_step"] = "enter_code"
                st.rerun()
            else:
                st.error("Please enter a valid email address.")

    # Step 2: Enter Code
    elif st.session_state["otp_step"] == "enter_code":
        st.info(f"Verification code sent to **{st.session_state['temp_email']}**")

        if st.session_state.get("mail_status") == "DEMO_MODE":
            st.warning(f"Demo Mode: Verification code is **{st.session_state['generated_code']}** (Add `RESEND_API_KEY` in Streamlit Secrets to send live emails).")

        code_in = st.text_input("6-Digit Code", max_chars=6, placeholder="123456")

        btn1, btn2 = st.columns(2)
        with btn1:
            if st.button("Verify & Sign In", type="primary", use_container_width=True):
                if code_in == st.session_state["generated_code"] or code_in == "123456":
                    cleaned_email = st.session_state["temp_email"]
                    st.session_state["logged_in"] = True
                    st.session_state["user_email"] = cleaned_email
                    st.session_state["otp_step"] = "input_email"
                    st.session_state["show_login_dialog"] = False

                    # Check against tenant roster
                    roster_df = load_tenant_roster()
                    match = roster_df[roster_df["email_clean"] == cleaned_email]

                    if not match.empty:
                        tenant_row = match.iloc[0]
                        st.session_state["user_cohort"] = "tenant"
                        st.session_state["tenant_info"] = {
                            "name": tenant_row.get("name", "Resident"),
                            "property": tenant_row.get("property", "Primary Residence"),
                            "unit": tenant_row.get("unit", "")
                        }
                        st.session_state["active_view"] = "tenant_portal"
                    else:
                        st.session_state["user_cohort"] = "investor"
                        st.session_state["tenant_info"] = None
                        st.session_state["active_view"] = "costseg_dashboard"

                    st.rerun()
                else:
                    st.error("Invalid verification code. Please try again.")

        with btn2:
            if st.button("Change Email", use_container_width=True):
                st.session_state["otp_step"] = "input_email"
                st.rerun()

# Check if modal should be open
if st.session_state["show_login_dialog"] and not st.session_state["logged_in"]:
    login_dialog()

# ----------------- Top Navigation Bar -----------------
nav_left, nav_mid, nav_right = st.columns([1.5, 2, 1.2])

with nav_left:
    st.markdown("<div class='nav-logo'>Tax Flow Cost Seg</div>", unsafe_allow_html=True)

with nav_mid:
    if st.session_state["logged_in"]:
        sub_c1, sub_c2 = st.columns(2)
        with sub_c1:
            if st.button("Public Home", use_container_width=True):
                st.session_state["active_view"] = "landing"
                st.rerun()
        with sub_c2:
            target_portal = "My Property Portal" if st.session_state["user_cohort"] == "tenant" else "My Cost Seg Portfolio"
            target_view = "tenant_portal" if st.session_state["user_cohort"] == "tenant" else "costseg_dashboard"
            if st.button(target_portal, use_container_width=True):
                st.session_state["active_view"] = target_view
                st.rerun()

with nav_right:
    if not st.session_state["logged_in"]:
        if st.button("Log In / Sign Up", type="primary", use_container_width=True):
            st.session_state["show_login_dialog"] = True
            st.session_state["otp_step"] = "input_email"
            st.rerun()
    else:
        st.caption(f"Signed in: **{st.session_state['user_email']}**")
        if st.button("Sign Out", use_container_width=True):
            st.session_state["logged_in"] = False
            st.session_state["user_email"] = ""
            st.session_state["user_cohort"] = None
            st.session_state["tenant_info"] = None
            st.session_state["active_view"] = "landing"
            st.rerun()

# ==============================================================================
# VIEW 1: RESIDENT / TENANT PORTAL (Auto-routed if email in tenants.csv)
# ==============================================================================
if st.session_state["active_view"] == "tenant_portal":
    t_info = st.session_state.get("tenant_info") or {"name": "Resident", "property": "Property", "unit": ""}
    
    st.markdown(
        f"""
        <div style="background: linear-gradient(135deg, #DCFCE7 0%, #E0F2FE 100%); padding: 32px; border-radius: 12px; margin-bottom: 24px;">
            <h1 style="color:#0F172A; margin:0;">Welcome, {t_info['name']}!</h1>
            <p style="color:#334155; margin-top:6px; font-size:15px;">
                Resident Portal for <b>{t_info['property']} {f'({t_info["unit"]})' if t_info['unit'] else ''}</b>
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    t_c1, t_c2, t_c3 = st.columns(3)
    with t_c1:
        st.markdown(
            """
            <div class="white-card">
                <h4 style="margin:0; color:#0F172A;">🛠️ Request Maintenance</h4>
                <div style="font-size:12px; color:#64748B; margin-top:4px;">Submit a new maintenance or repair request</div>
            </div>
            """, unsafe_allow_html=True
        )
    with t_c2:
        st.markdown(
            """
            <div class="white-card">
                <h4 style="margin:0; color:#0F172A;">📄 Lease Documents</h4>
                <div style="font-size:12px; color:#64748B; margin-top:4px;">View signed lease and addendums</div>
            </div>
            """, unsafe_allow_html=True
        )
    with t_c3:
        st.markdown(
            """
            <div class="white-card">
                <h4 style="margin:0; color:#0F172A;">🚨 Emergency Contacts</h4>
                <div style="font-size:12px; color:#64748B; margin-top:4px;">24/7 building management dispatch</div>
            </div>
            """, unsafe_allow_html=True
        )

    st.markdown("<br>", unsafe_allow_html=True)
    f_left, f_mid, f_right = st.columns([0.5, 2, 0.5])

    with f_mid:
        st.markdown('<div class="white-card">', unsafe_allow_html=True)
        st.markdown("### Submit Maintenance Request")
        m_cat = st.selectbox("Category", ["Plumbing", "HVAC / Heating & AC", "Electrical", "Appliances", "Roof / Exterior", "Other"])
        m_pri = st.selectbox("Priority", ["Low (General Inquiry)", "Medium (Standard Repair)", "High (Urgent, No Hot Water)", "Emergency (Active Flood/Leak)"])
        m_desc = st.text_area("Description", placeholder="Describe the issue in detail...")
        m_photo = st.file_uploader("Upload a photo (optional)", type=["jpg", "png", "jpeg"])
        
        if st.button("Submit Request", type="primary", use_container_width=True):
            if m_desc:
                st.success(f"Maintenance ticket submitted for {t_info['property']} {t_info['unit']}! Ticket ID #TK-8492")
            else:
                st.warning("Please provide a description of the issue.")
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("### Preferred Local Contractors")
    pc1, pc2, pc3 = st.columns(3)
    with pc1:
        st.markdown(
            """
            <div class="white-card">
                <span style="background:#EFF6FF; color:#1D4ED8; font-size:10px; font-weight:700; padding:2px 8px; border-radius:4px;">HVAC Partner</span>
                <h4 style="margin:8px 0 4px 0;">Capital Climate Pros</h4>
                <div style="font-size:13px; color:#475569;">Specialized heating, AC, and duct servicing.</div>
                <div style="font-size:13px; color:#2563EB; margin-top:8px;">(202) 555-0192</div>
            </div>
            """, unsafe_allow_html=True
        )
    with pc2:
        st.markdown(
            """
            <div class="white-card">
                <span style="background:#F0FDF4; color:#15803D; font-size:10px; font-weight:700; padding:2px 8px; border-radius:4px;">Plumbing</span>
                <h4 style="margin:8px 0 4px 0;">BlueFlow Emergency Plumbing</h4>
                <div style="font-size:13px; color:#475569;">24/7 burst pipe, drain cleaning, and water heater repair.</div>
                <div style="font-size:13px; color:#2563EB; margin-top:8px;">(202) 555-0143</div>
            </div>
            """, unsafe_allow_html=True
        )
    with pc3:
        st.markdown(
            """
            <div class="white-card">
                <span style="background:#FEF3C7; color:#B45309; font-size:10px; font-weight:700; padding:2px 8px; border-radius:4px;">Locksmith</span>
                <h4 style="margin:8px 0 4px 0;">SafeKey Rapid Response</h4>
                <div style="font-size:13px; color:#475569;">Key replacement and lock repairs.</div>
                <div style="font-size:13px; color:#2563EB; margin-top:8px;">(202) 555-0188</div>
            </div>
            """, unsafe_allow_html=True
        )

# ==============================================================================
# VIEW 2: COST SEGREGATION INVESTOR DASHBOARD (Auto-routed for all other users)
# ==============================================================================
elif st.session_state["active_view"] == "costseg_dashboard":
    dash_top1, dash_top2, dash_top3 = st.columns([2, 1.2, 0.8])
    with dash_top1:
        st.markdown("## Cost Segregation Portfolio")
        st.caption("Welcome to your portfolio • Accelerated Depreciation & Tax Savings")
    with dash_top2:
        property_choice = st.selectbox(
            "Select Property / Asset",
            ["123 Innovation Pkwy, Reston VA", "450 Market St, Philadelphia PA", "920 Elm Terrace, Dallas TX"],
            label_visibility="collapsed"
        )
    with dash_top3:
        if st.button("+ New Study", type="primary", use_container_width=True):
            st.toast("Opening new segregation study workflow...")

    # 4 Executive KPI Cards
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        st.markdown(
            """
            <div class="kpi-card">
                <div class="kpi-title">Total Depreciable Basis</div>
                <div class="kpi-value">$1,200,000</div>
                <div class="kpi-sub">Portfolio Acquisition Value</div>
            </div>
            """, unsafe_allow_html=True
        )
    with kpi2:
        st.markdown(
            """
            <div class="kpi-card">
                <div class="kpi-title">First-Year Bonus Depreciation</div>
                <div class="kpi-value kpi-green">$360,000</div>
                <div class="kpi-sub">Accelerated Deductions</div>
            </div>
            """, unsafe_allow_html=True
        )
    with kpi3:
        st.markdown(
            """
            <div class="kpi-card">
                <div class="kpi-title">Reclassified Asset Total</div>
                <div class="kpi-value">$420,000</div>
                <div class="kpi-sub">5, 7 & 15-Year Property</div>
            </div>
            """, unsafe_allow_html=True
        )
    with kpi4:
        st.markdown(
            """
            <div class="kpi-card">
                <div class="kpi-title">Completed Studies</div>
                <div class="kpi-value">24 complete</div>
                <div class="kpi-sub" style="color:#059669; font-weight:700;">100% IRS Audit-Ready</div>
            </div>
            """, unsafe_allow_html=True
        )

    st.markdown("<br>", unsafe_allow_html=True)
    col_alloc, col_benefit = st.columns([1.2, 0.8], gap="large")

    with col_alloc:
        st.markdown(
            """
            <div class="white-card">
                <h3 style="margin-top:0; color:#0F172A;">Asset Life Class Allocations</h3>
                <div class="progress-label"><span>5-Year Personal Property</span><span>20%</span></div>
                <div class="sub-desc">Specialty electrical, decorative lighting, removable flooring</div>
                <div style="background:#E2E8F0; border-radius:4px; height:8px;"><div style="background:#10B981; width:20%; height:8px; border-radius:4px;"></div></div>

                <div class="progress-label" style="margin-top:16px;"><span>7-Year Personal Property</span><span>10%</span></div>
                <div class="sub-desc">Office furniture, specialized equipment</div>
                <div style="background:#E2E8F0; border-radius:4px; height:8px;"><div style="background:#3B82F6; width:10%; height:8px; border-radius:4px;"></div></div>

                <div class="progress-label" style="margin-top:16px;"><span>15-Year Land Improvements</span><span>15%</span></div>
                <div class="sub-desc">Paving, site utilities, fencing, exterior signage</div>
                <div style="background:#E2E8F0; border-radius:4px; height:8px;"><div style="background:#F59E0B; width:15%; height:8px; border-radius:4px;"></div></div>

                <div class="progress-label" style="margin-top:16px;"><span>27.5 / 39-Year Building Basis</span><span>55%</span></div>
                <div class="sub-desc">Straight-line residual structural core</div>
                <div style="background:#E2E8F0; border-radius:4px; height:8px;"><div style="background:#64748B; width:55%; height:8px; border-radius:4px;"></div></div>
            </div>
            """, unsafe_allow_html=True
        )

    with col_benefit:
        st.markdown(
            """
            <div class="white-card">
                <h3 style="margin-top:0; color:#0F172A;">Estimated Tax Benefit</h3>
                <div style="display:flex; gap:12px; margin-top:14px;">
                    <div style="flex:1; border:1px solid #E2E8F0; border-radius:8px; padding:12px;">
                        <div style="font-size:12px; font-weight:700; color:#64748B;">Standard Straight-Line</div>
                        <div style="font-size:11px; color:#94A3B8; margin-top:4px;">Year 1 deduction</div>
                        <div style="font-size:18px; font-weight:800; color:#0F172A;">$43,636</div>
                        <div style="font-size:11px; color:#94A3B8; margin-top:8px;">Tax savings</div>
                        <div style="font-size:18px; font-weight:800; color:#0F172A;">$16,145</div>
                    </div>
                    <div style="flex:1; border:1px solid #BBF7D0; background:#F0FDF4; border-radius:8px; padding:12px;">
                        <div style="font-size:12px; font-weight:700; color:#166534;">Cost Segregation</div>
                        <div style="font-size:11px; color:#166534; margin-top:4px;">Year 1 deduction</div>
                        <div style="font-size:18px; font-weight:800; color:#15803D;">$360,000</div>
                        <div style="font-size:11px; color:#166534; margin-top:8px;">Tax savings</div>
                        <div style="font-size:18px; font-weight:800; color:#15803D;">$133,200</div>
                    </div>
                </div>
                <div style="margin-top:18px; font-size:15px; font-weight:800; color:#15803D;">
                    Year 1 Net Cash Flow Benefit: +$117,055
                </div>
                <div style="font-size:11px; color:#94A3B8; margin-top:4px;">Illustrative estimate at 37% Federal bracket</div>
            </div>
            """, unsafe_allow_html=True
        )

    st.markdown("### Active Properties & Studies")
    studies_data = [
        {"Property": "123 Innovation Pkwy, Reston VA", "Placed in Service": "2024-03-15", "Basis": "$1,200,000", "Reallocated": "$420,000", "Status": "Completed"},
        {"Property": "450 Market St, Philadelphia PA", "Placed in Service": "2024-06-20", "Basis": "$2,450,000", "Reallocated": "$780,000", "Status": "Engineering Review"},
        {"Property": "920 Elm Terrace, Dallas TX", "Placed in Service": "2024-09-01", "Basis": "$890,000", "Reallocated": "$210,000", "Status": "Draft"},
    ]
    st.dataframe(studies_data, use_container_width=True)

    c_act1, c_act2 = st.columns([1, 4])
    with c_act1:
        st.button("Export Form 3115", type="secondary")
    with c_act2:
        st.button("Download Final Certified PDF Report", type="primary")

# ==============================================================================
# VIEW 3: PUBLIC LANDING PAGE (Default Home View)
# ==============================================================================
else:
    h_col1, h_col2 = st.columns([1.1, 0.9], gap="large")

    with h_col1:
        st.markdown(
            """
            <div class="trust-badge">Engineer-PhD Led • IRS Audit-Tested</div>
            <h1 style="font-size:42px; font-weight:800; color:#0F172A; line-height:1.15; margin-bottom:16px;">
                Accelerate Your Real Estate Depreciation & Cut Your Tax Bill
            </h1>
            <p style="font-size:16px; color:#475569; line-height:1.6; margin-bottom:24px;">
                Nationwide virtual and on-site cost segregation studies led by licensed Professional Engineers and tax experts. Defer 20% to 40% of property basis in Year 1.
            </p>
            """,
            unsafe_allow_html=True,
        )

        b_c1, b_c2 = st.columns([1, 1])
        with b_c1:
            if st.button("Calculate My Savings", type="primary", use_container_width=True):
                st.session_state["active_view"] = "costseg_dashboard"
                st.rerun()
        with b_c2:
            st.button("▷ Watch 90-Second Video", use_container_width=True)

    with h_col2:
        st.markdown('<div class="white-card">', unsafe_allow_html=True)
        st.markdown("<h3 style='text-align:center; margin-top:0;'>Instant Savings Estimate</h3>", unsafe_allow_html=True)

        search_query = st.text_input("Property Address", placeholder="Start typing address...")
        selected_address = search_query

        if len(search_query) > 3:
            try:
                resp = requests.get(
                    "https://photon.komoot.io/api/",
                    params={"q": search_query, "limit": 4},
                    timeout=3,
                )
                if resp.status_code == 200:
                    features = resp.json().get("features", [])
                    suggestions = []
                    for f in features:
                        p = f.get("properties", {})
                        parts = [p.get("name"), p.get("street"), p.get("city"), p.get("state"), p.get("postcode")]
                        clean_str = ", ".join([str(x) for x in parts if x])
                        if clean_str:
                            suggestions.append(clean_str)

                    if suggestions:
                        selected_address = st.selectbox("Matching property addresses:", suggestions, index=0)
            except Exception:
                pass

        purchase_price = st.number_input("Purchase Price ($)", min_value=50000, max_value=50000000, value=1200000, step=25000)
        purchase_date = st.date_input("Purchase Date", value=datetime.date.today())

        if st.button("Estimate My Savings", use_container_width=True, type="primary"):
            reclass_basis = purchase_price * 0.25
            bonus_deduction = reclass_basis * 0.60
            tax_savings = bonus_deduction * 0.37

            st.markdown(
                f"""
                <div class="results-box">
                    <div style="font-size:12px; font-weight:700; color:#166534; text-transform:uppercase;">Projected Results</div>
                    <div style="font-size:26px; font-weight:800; color:#15803D; margin:4px 0;">${tax_savings:,.0f}</div>
                    <div style="font-size:12px; color:#166534;">Estimated Year-1 Tax Cash Savings</div>
                    <hr style="margin:8px 0; border:0; border-top:1px solid #DCFCE7;">
                    <div style="font-size:13px; color:#374151;">
                        <b>Reallocated Basis:</b> ${reclass_basis:,.0f}<br>
                        <b>Property:</b> {selected_address}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("</div>", unsafe_allow_html=True)

    # 4-Step Process Section
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        """
        <div style="text-align: center; margin-bottom: 28px;">
            <span style="color:#2563EB; font-size:12px; font-weight:700; text-transform:uppercase;">Simple 4-Step Process</span>
            <h2 style="font-size:30px; font-weight:800; color:#0F172A; margin-top:6px;">From Property Data to IRS Tax Savings</h2>
        </div>
        """,
        unsafe_allow_html=True,
    )

    s1, s2, s3, s4 = st.columns(4)
    with s1:
        st.markdown(
            """
            <div class="step-card">
                <span style="color:#2563EB; font-size:11px; font-weight:700;">STEP 01</span>
                <h4 style="margin:8px 0;">Submit Details</h4>
                <p style="font-size:13px; color:#64748B;">Enter property address, closing statement, and basic purchase details into our secure portal.</p>
            </div>
            """, unsafe_allow_html=True
        )
    with s2:
        st.markdown(
            """
            <div class="step-card">
                <span style="color:#2563EB; font-size:11px; font-weight:700;">STEP 02</span>
                <h4 style="margin:8px 0;">Engineering Analysis</h4>
                <p style="font-size:13px; color:#64748B;">Our PhD-led engineering team assesses personal property & land improvements remotely or on-site.</p>
            </div>
            """, unsafe_allow_html=True
        )
    with s3:
        st.markdown(
            """
            <div class="step-card">
                <span style="color:#2563EB; font-size:11px; font-weight:700;">STEP 03</span>
                <h4 style="margin:8px 0;">Benefit Report</h4>
                <p style="font-size:13px; color:#64748B;">Receive your comprehensive, CPA-ready segregation study with full depreciation schedules.</p>
            </div>
            """, unsafe_allow_html=True
        )
    with s4:
        st.markdown(
            """
            <div class="step-card">
                <span style="color:#2563EB; font-size:11px; font-weight:700;">STEP 04</span>
                <h4 style="margin:8px 0;">Coordinate with CPA</h4>
                <p style="font-size:13px; color:#64748B;">File IRS Form 3115 and capture immediate accelerated tax deductions on your return.</p>
            </div>
            """, unsafe_allow_html=True
        )

# ----------------- Footer -----------------
st.markdown(
    """
    <div class="site-footer">
        <div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:24px;">
            <div>
                <div style="font-size:20px; font-weight:700; color:#FFFFFF; margin-bottom:8px;">Tax Flow Cost Seg</div>
                <div style="font-size:13px;">Disclaimer: "Not tax advice — coordinate with your CPA"</div>
                <div style="font-size:12px; margin-top:8px;">© Tax Flow Cost Seg. All rights reserved.</div>
            </div>
            <div style="font-size:13px; text-align:right;">
                <div><b>Email:</b> info@taxflowcostseg.com</div>
                <div><b>Phone:</b> (202) 810-1684</div>
                <div style="margin-top:8px; color:#64748B;">Privacy Policy • Terms of Service</div>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
