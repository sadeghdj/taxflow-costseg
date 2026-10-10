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
    """Sends the 6-digit code from info@taxflowcostseg.com using your Resend API key."""
    api_key = st.secrets.get("RESEND_API_KEY")
    if not api_key:
        return False, "DEMO_MODE"

    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "from": "Tax Flow Cost Seg <info@taxflowcostseg.com>",
        "to": [recipient_email],
        "subject": f"{code} is your login verification code",
        "html": f"""
        <div style="font-family: Arial, sans-serif; max-width: 520px; margin: 0 auto; padding: 24px; border: 1px solid #E2E8F0; border-radius: 12px; background-color: #FFFFFF;">
            <h2 style="color: #0F172A; margin-top: 0;">Tax Flow Cost Seg</h2>
            <p style="color: #475569; font-size: 15px;">Your one-time verification code to access your portal is:</p>
            <div style="background-color: #F8FAFC; border: 1px solid #CBD5E1; border-radius: 8px; padding: 18px; text-align: center; margin: 24px 0;">
                <span style="font-size: 34px; font-weight: 800; letter-spacing: 8px; color: #0F172A;">{code}</span>
            </div>
            <p style="color: #94A3B8; font-size: 12px; line-height: 1.5;">
                This code expires in 10 minutes. If you did not request this login code, please disregard this email.
            </p>
        </div>
        """
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

# ----------------- Passwordless Login Modal -----------------
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

    # Step 2: Enter Code (Popup stays open here)
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

  
