import streamlit as st
import requests

# Page Configuration
st.set_page_config(
    page_title="Tax Flow Cost Seg | Nationwide Cost Segregation Studies",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Custom Styling to match the Bubble fintech aesthetic (Navy #0F172A, Slate #F8FAFC, Emerald #059669)
st.markdown(
    """
    <style>
        /* Global Page Background */
        .stApp {
            background-color: #F8FAFC;
            color: #0F172A;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }

        /* Top Header Navbar */
        .nav-container {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #FFFFFF;
            padding: 16px 32px;
            border-bottom: 1px solid #E2E8F0;
            margin-bottom: 24px;
            border-radius: 8px;
        }
        .nav-logo {
            font-size: 22px;
            font-weight: 700;
            color: #0F172A;
            text-decoration: none;
        }
        .nav-links {
            display: flex;
            gap: 24px;
            align-items: center;
            font-size: 14px;
            font-weight: 500;
            color: #475569;
        }

        /* Trust Badge Pill */
        .trust-badge {
            display: inline-block;
            background-color: #EFF6FF;
            color: #1D4ED8;
            font-size: 12px;
            font-weight: 700;
            padding: 6px 14px;
            border-radius: 9999px;
            margin-bottom: 16px;
            border: 1px solid #DBEAFE;
        }

        /* Hero Typography */
        .hero-title {
            font-size: 42px;
            font-weight: 800;
            color: #0F172A;
            line-height: 1.15;
            margin-bottom: 16px;
        }
        .hero-sub {
            font-size: 16px;
            color: #475569;
            line-height: 1.6;
            margin-bottom: 24px;
        }

        /* Estimator Card Container */
        .calc-card {
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 16px;
            padding: 28px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05);
        }
        .calc-title {
            font-size: 20px;
            font-weight: 700;
            color: #0F172A;
            margin-bottom: 20px;
            text-align: center;
        }

        /* Results Box inside Estimator */
        .results-box {
            background: #F0FDF4;
            border: 1px solid #BBF7D0;
            border-radius: 10px;
            padding: 16px;
            margin-top: 16px;
        }

        /* Step Card */
        .step-card {
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 12px;
            padding: 24px;
            height: 100%;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }
        .step-num {
            color: #2563EB;
            font-size: 12px;
            font-weight: 700;
            text-transform: uppercase;
            margin-bottom: 8px;
        }
        .step-heading {
            font-size: 17px;
            font-weight: 700;
            color: #0F172A;
            margin-bottom: 8px;
        }
        .step-text {
            font-size: 14px;
            color: #64748B;
            line-height: 1.5;
        }

        /* Dark Footer */
        .site-footer {
            background-color: #0F172A;
            color: #94A3B8;
            padding: 48px 32px 24px 32px;
            border-radius: 12px 12px 0 0;
            margin-top: 64px;
        }
        .footer-logo {
            font-size: 20px;
            font-weight: 700;
            color: #FFFFFF;
            margin-bottom: 8px;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------- 1. Top Navbar -----------------
st.markdown(
    """
    <div class="nav-container">
        <div class="nav-logo">Tax Flow Cost Seg</div>
        <div class="nav-links">
            <span>How It Works</span>
            <span>Services</span>
            <span>Log In</span>
            <span style="background:#0F172A; color:#FFFFFF; padding:8px 16px; border-radius:8px;">Get Free Estimate</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ----------------- 2. Split Hero Section -----------------
hero_col1, hero_col2 = st.columns([1.1, 0.9], gap="large")

with hero_col1:
    st.markdown(
        """
        <div class="trust-badge">Engineer-PhD Led • IRS Audit-Tested</div>
        <div class="hero-title">Accelerate Your Real Estate Depreciation & Cut Your Tax Bill</div>
        <div class="hero-sub">
            Nationwide virtual and on-site cost segregation studies led by licensed Professional Engineers and tax experts. Defer 20% to 40% of property basis in Year 1.
        </div>
        """,
        unsafe_allow_html=True,
    )

    btn_c1, btn_c2 = st.columns([1, 1])
    with btn_c1:
        st.button("Calculate My Savings", type="primary", use_container_width=True)
    with btn_c2:
        st.button("▷ Watch 90-Second Video", use_container_width=True)

with hero_col2:
    st.markdown('<div class="calc-card">', unsafe_allow_html=True)
    st.markdown('<div class="calc-title">Instant Savings Estimate</div>', unsafe_allow_html=True)

    # 100% Free Address Autocomplete using OpenStreetMap Photon API
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
                    parts = [
                        p.get("name"),
                        p.get("street"),
                        p.get("city"),
                        p.get("state"),
                        p.get("postcode"),
                    ]
                    clean_str = ", ".join([str(x) for x in parts if x])
                    if clean_str:
                        suggestions.append(clean_str)

                if suggestions:
                    selected_address = st.selectbox(
                        "Suggested matching properties:", suggestions, index=0
                    )
        except Exception:
            pass  # Fallback gracefully to typed text if lookup fails

    purchase_price = st.number_input(
        "Purchase Price ($)", min_value=50000, max_value=50000000, value=1200000, step=25000
    )
    purchase_date = st.date_input("Purchase Date")

    estimate_clicked = st.button("Estimate My Savings", use_container_width=True, type="primary")

    if estimate_clicked:
        # Standard conservative cost segregation metrics:
        # ~25% reclassified into 5/7/15-yr assets; 37% federal tax bracket
        reclassified_basis = purchase_price * 0.25
        est_first_year_depreciation = reclassified_basis * 0.60  # Assuming 60% bonus
        est_tax_savings = est_first_year_depreciation * 0.37

        st.markdown(
            f"""
            <div class="results-box">
                <div style="font-size: 13px; font-weight:700; color:#166534; text-transform:uppercase;">Projected Results</div>
                <div style="font-size: 26px; font-weight:800; color:#15803D; margin: 4px 0;">${est_tax_savings:,.0f}</div>
                <div style="font-size: 12px; color:#166534;">Estimated Year-1 Tax Cash Savings</div>
                <hr style="margin: 8px 0; border: 0; border-top: 1px solid #DCFCE7;">
                <div style="font-size: 13px; color:#374151;">
                    <b>Reallocated Basis (5/15-yr):</b> ${reclassified_basis:,.0f}<br>
                    <b>Selected Property:</b> {selected_address}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)

# ----------------- 3. "How Cost Seg Works" Section -----------------
st.markdown("<br><br>", unsafe_allow_html=True)
st.markdown(
    """
    <div style="text-align: center; margin-bottom: 32px;">
        <span style="color:#2563EB; font-size:12px; font-weight:700; letter-spacing:0.05em; text-transform:uppercase;">Simple 4-Step Process</span>
        <h2 style="font-size:32px; font-weight:800; color:#0F172A; margin-top:8px;">From Property Data to IRS Tax Savings</h2>
    </div>
    """,
    unsafe_allow_html=True,
)

c1, c2, c3, c4 = st.columns(4)

with c1:
    st.markdown(
        """
        <div class="step-card">
            <div class="step-num">Step 01</div>
            <div class="step-heading">Submit Details</div>
            <div class="step-text">Enter property address, closing statement, and basic purchase details into our secure portal.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c2:
    st.markdown(
        """
        <div class="step-card">
            <div class="step-num">Step 02</div>
            <div class="step-heading">Engineering Analysis</div>
            <div class="step-text">Our PhD-led engineering team assesses personal property & land improvements remotely or on-site.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c3:
    st.markdown(
        """
        <div class="step-card">
            <div class="step-num">Step 03</div>
            <div class="step-heading">Benefit Report</div>
            <div class="step-text">Receive your comprehensive, CPA-ready segregation study with full depreciation schedules.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c4:
    st.markdown(
        """
        <div class="step-card">
            <div class="step-num">Step 04</div>
            <div class="step-heading">Coordinate with CPA</div>
            <div class="step-text">File IRS Form 3115 and capture immediate accelerated tax deductions on your return.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ----------------- 4. Footer Section -----------------
st.markdown(
    """
    <div class="site-footer">
        <div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:24px;">
            <div>
                <div class="footer-logo">Tax Flow Cost Seg</div>
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
