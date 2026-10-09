import streamlit as st
import requests
import datetime

# ----------------- Page Setup -----------------
st.set_page_config(
    page_title="Tax Flow Cost Seg & Property Portal",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ----------------- Global Design Styling (Fintech Theme) -----------------
st.markdown(
    """
    <style>
        .stApp {
            background-color: #F8FAFC;
            color: #0F172A;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }

        /* Nav Container */
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
        .nav-logo {
            font-size: 20px;
            font-weight: 800;
            color: #0F172A;
        }

        /* Cards & Surfaces */
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

        /* Trust Badge */
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

        /* Results Card */
        .results-box {
            background: #F0FDF4;
            border: 1px solid #BBF7D0;
            border-radius: 10px;
            padding: 16px;
            margin-top: 14px;
        }

        /* Progress Bar Custom Container */
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

        /* Step Card */
        .step-card {
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 12px;
            padding: 22px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
            height: 100%;
        }

        /* Footer */
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
if "active_view" not in st.session_state:
    st.session_state["active_view"] = "landing"

# ----------------- Passwordless Login Modal / Dialog -----------------
@st.dialog("Log In / Sign Up")
def login_dialog():
    st.markdown("### Welcome back!")
    st.markdown("Enter your email address to access your secure portal.")
    
    email = st.text_input("Email Address", placeholder="name@domain.com")
    cohort = st.radio(
        "Select Portal Type:",
        ["Cost Segregation Investor", "Tenant / Property Portal"],
        horizontal=True
    )
    
    # Passwordless flow (One-Time Verification Code)
    if "otp_sent" not in st.session_state:
        st.session_state["otp_sent"] = False
        
    if not st.session_state["otp_sent"]:
        if st.button("Send One-Time Code", type="primary", use_container_width=True):
            if email and "@" in email:
                st.session_state["otp_sent"] = True
                st.session_state["temp_email"] = email
                st.session_state["temp_cohort"] = cohort
                st.success("Verification code sent to your email! (For testing, use code: 123456)")
                st.rerun()
            else:
                st.error("Please enter a valid email address.")
    else:
        st.info(f"Verification code sent to {st.session_state.get('temp_email')}")
        code = st.text_input("6-Digit Code", placeholder="123456", max_chars=6)
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Verify & Sign In", type="primary", use_container_width=True):
                # Demo verification check
                if code == "123456" or len(code) == 6:
                    st.session_state["logged_in"] = True
                    st.session_state["user_email"] = st.session_state["temp_email"]
                    st.session_state["user_cohort"] = st.session_state["temp_cohort"]
                    st.session_state["active_view"] = (
                        "costseg_dashboard" if "Investor" in st.session_state["temp_cohort"] else "tenant_portal"
                    )
                    st.session_state["otp_sent"] = False
                    st.rerun()
                else:
                    st.error("Invalid code. Please try 123456.")
        with c2:
            if st.button("Resend / Back", use_container_width=True):
                st.session_state["otp_sent"] = False
                st.rerun()

# ----------------- Top Navigation Bar -----------------
nav_left, nav_mid, nav_right = st.columns([1.5, 2, 1.2])

with nav_left:
    st.markdown("<div class='nav-logo'>Tax Flow Cost Seg</div>", unsafe_allow_html=True)

with nav_mid:
    if st.session_state["logged_in"]:
        sub_c1, sub_c2, sub_c3 = st.columns(3)
        with sub_c1:
            if st.button("Public Home", use_container_width=True):
                st.session_state["active_view"] = "landing"
                st.rerun()
        with sub_c2:
            if st.button("Cost Seg Portal", use_container_width=True):
                st.session_state["active_view"] = "costseg_dashboard"
                st.rerun()
        with sub_c3:
            if st.button("Tenant Portal", use_container_width=True):
                st.session_state["active_view"] = "tenant_portal"
                st.rerun()

with nav_right:
    if not st.session_state["logged_in"]:
        if st.button("Log In / Sign Up", type="primary", use_container_width=True):
            login_dialog()
    else:
        st.caption(f"Signed in as: **{st.session_state['user_email']}**")
        if st.button("Sign Out", use_container_width=True):
            st.session_state["logged_in"] = False
            st.session_state["user_email"] = ""
            st.session_state["active_view"] = "landing"
            st.rerun()

# ==============================================================================
# VIEW 1: COST SEGREGATION INVESTOR DASHBOARD (Matches Screenshot 2)
# ==============================================================================
if st.session_state["active_view"] == "costseg_dashboard":
    # Top Action Bar
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

    # 4 Executive KPI Cards Row
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

    # Split Panel: Asset Class Allocations vs. Tax Benefit Comparison
    col_alloc, col_benefit = st.columns([1.2, 0.8], gap="large")

    with col_alloc:
        st.markdown(
            """
            <div class="white-card">
                <h3 style="margin-top:0; color:#0F172A;">Asset Life Class Allocations</h3>
                
                <div class="progress-label"><span>5-Year Personal Property</span><span>20%</span></div>
                <div class="sub-desc">Specialty electrical, decorative lighting, removable flooring</div>
                <div style="background:#E2E8F0; border-radius:4px; height:8px;">
                    <div style="background:#10B981; width:20%; height:8px; border-radius:4px;"></div>
                </div>

                <div class="progress-label" style="margin-top:16px;"><span>7-Year Personal Property</span><span>10%</span></div>
                <div class="sub-desc">Office furniture, specialized equipment</div>
                <div style="background:#E2E8F0; border-radius:4px; height:8px;">
                    <div style="background:#3B82F6; width:10%; height:8px; border-radius:4px;"></div>
                </div>

                <div class="progress-label" style="margin-top:16px;"><span>15-Year Land Improvements</span><span>15%</span></div>
                <div class="sub-desc">Paving, site utilities, fencing, exterior signage</div>
                <div style="background:#E2E8F0; border-radius:4px; height:8px;">
                    <div style="background:#F59E0B; width:15%; height:8px; border-radius:4px;"></div>
                </div>

                <div class="progress-label" style="margin-top:16px;"><span>27.5 / 39-Year Building Basis</span><span>55%</span></div>
                <div class="sub-desc">Straight-line residual structural core</div>
                <div style="background:#E2E8F0; border-radius:4px; height:8px;">
                    <div style="background:#64748B; width:55%; height:8px; border-radius:4px;"></div>
                </div>
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

    # Active Properties & Studies Table
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
# VIEW 2: TENANT / PROPERTY PORTAL (Matches Screenshot 1)
# ==============================================================================
elif st.session_state["active_view"] == "tenant_portal":
    st.markdown(
        """
        <div style="background: linear-gradient(135deg, #DCFCE7 0%, #E0F2FE 100%); padding: 32px; border-radius: 12px; margin-bottom: 24px;">
            <h1 style="color:#0F172A; margin:0;">Resident Property Portal</h1>
            <p style="color:#334155; margin-top:6px; font-size:15px;">Manage maintenance requests, lease documents, and contractor support.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 3 Top Quick-Action Cards
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
                <div style="font-size:12px; color:#64748B; margin-top:4px;">View signed lease, addendums, and community rules</div>
            </div>
            """, unsafe_allow_html=True
        )
    with t_c3:
        st.markdown(
            """
            <div class="white-card">
                <h4 style="margin:0; color:#0F172A;">🚨 Emergency Contacts</h4>
                <div style="font-size:12px; color:#64748B; margin-top:4px;">24/7 building management and utility dispatch</div>
            </div>
            """, unsafe_allow_html=True
        )

    # Centered Maintenance Request Form
    st.markdown("<br>", unsafe_allow_html=True)
    f_left, f_mid, f_right = st.columns([0.5, 2, 0.5])

    with f_mid:
        st.markdown('<div class="white-card">', unsafe_allow_html=True)
        st.markdown("### Request Maintenance")
        
        m_cat = st.selectbox("Category", ["Plumbing", "HVAC / Heating & AC", "Electrical", "Appliances", "Roof / Exterior", "Other"])
        m_pri = st.selectbox("Priority", ["Low (General Inquiry)", "Medium (Standard Repair)", "High (Urgent, No Hot Water)", "Emergency (Active Flood/Leak)"])
        m_desc = st.text_area("Description", placeholder="Describe the issue in detail...")
        m_photo = st.file_uploader("Upload a photo (optional)", type=["jpg", "png", "jpeg"])
        
        if st.button("Submit Request", type="primary", use_container_width=True):
            if m_desc:
                st.success("Maintenance ticket submitted successfully! Dispatch ticket ID #TK-8492")
            else:
                st.warning("Please provide a description of the issue.")
        st.markdown('</div>', unsafe_allow_html=True)

    # Preferred Contractors Section
    st.markdown("### Preferred Local Contractors")
    pc1, pc2, pc3 = st.columns(3)
    with pc1:
        st.markdown(
            """
            <div class="white-card">
                <span style="background:#EFF6FF; color:#1D4ED8; font-size:10px; font-weight:700; padding:2px 8px; border-radius:4px;">HVAC Partner</span>
                <h4 style="margin:8px 0 4px 0;">Capital Climate Pros</h4>
                <div style="font-size:13px; color:#475569;">Specialized heating, AC, and duct servicing.</div>
                <div style="font-size:13px; color:#2563EB; margin-top:8px;">(202) 555-0192 • info@capitalclimate.com</div>
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
                <div style="font-size:13px; color:#2563EB; margin-top:8px;">(202) 555-0143 • service@blueflow.com</div>
            </div>
            """, unsafe_allow_html=True
        )
    with pc3:
        st.markdown(
            """
            <div class="white-card">
                <span style="background:#FEF3C7; color:#B45309; font-size:10px; font-weight:700; padding:2px 8px; border-radius:4px;">Locksmith</span>
                <h4 style="margin:8px 0 4px 0;">SafeKey Rapid Response</h4>
                <div style="font-size:13px; color:#475569;">Key replacement, lock repairs, and smart lock reprogramming.</div>
                <div style="font-size:13px; color:#2563EB; margin-top:8px;">(202) 555-0188 • help@safekey.com</div>
            </div>
            """, unsafe_allow_html=True
        )

# ==============================================================================
# VIEW 3: PUBLIC LANDING PAGE (Default Home View)
# ==============================================================================
else:
    # Split Hero Section
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

        # 100% Free Photon OpenStreetMap Address Autocomplete
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
