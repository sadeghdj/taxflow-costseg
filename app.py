import streamlit as st
import streamlit.components.v1 as components
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

# ----------------- Session State Initialization -----------------
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

# Start with completely clean portfolio (no hardcoded properties)
if "user_studies" not in st.session_state:
    st.session_state["user_studies"] = []

# Synchronized Autopopulation State for Estimator
if "est_price" not in st.session_state:
    st.session_state["est_price"] = 1200000
if "est_sqft" not in st.session_state:
    st.session_state["est_sqft"] = 3200
if "est_year" not in st.session_state:
    st.session_state["est_year"] = 2018
if "est_type" not in st.session_state:
    st.session_state["est_type"] = "Commercial / Multi-Family"

# Modal dynamic fields state
if "modal_price" not in st.session_state:
    st.session_state["modal_price"] = 1200000
if "modal_type_index" not in st.session_state:
    st.session_state["modal_type_index"] = 0
if "modal_selected_addr" not in st.session_state:
    st.session_state["modal_selected_addr"] = ""

# ----------------- Video Modal Dialog -----------------
@st.dialog(" ", width="large")
def video_dialog():
    st.video("https://youtu.be/O2Icd-i_Ixw")

# ----------------- Property Data Fetcher (Autopopulation Engine) -----------------
def fetch_property_specs(address_str):
    """Fetches real specs via RentCast API or generates realistic location-based values."""
    rentcast_key = st.secrets.get("RENTCAST_API_KEY")
    if rentcast_key and len(address_str) > 6:
        try:
            url = "https://api.rentcast.io/v1/properties"
            headers = {"X-Api-Key": rentcast_key, "Accept": "application/json"}
            res = requests.get(url, headers=headers, params={"address": address_str}, timeout=4)
            if res.status_code == 200:
                data = res.json()
                if data and len(data) > 0:
                    p = data[0]
                    return {
                        "price": int(p.get("lastSalePrice") or p.get("assessedValue") or 1350000),
                        "sqft": int(p.get("squareFootage") or 3400),
                        "year_built": int(p.get("yearBuilt") or 2019),
                        "prop_type": p.get("propertyType") or "Residential / Multi-Family"
                    }
        except Exception:
            pass

    # Location-based heuristic so different addresses generate distinct realistic specs
    seed = sum(ord(c) for c in address_str)
    pseudo_price = 750000 + (seed % 15) * 50000
    pseudo_sqft = 2200 + (seed % 12) * 200
    pseudo_year = 2010 + (seed % 14)
    return {
        "price": pseudo_price,
        "sqft": pseudo_sqft,
        "year_built": pseudo_year,
        "prop_type": "Commercial / Multi-Family"
    }

# ----------------- New Study Creation Modal Workflow -----------------
@st.dialog("Create New Cost Segregation Study", width="large")
def new_study_dialog():
    st.markdown("Enter property details to initialize an IRS-compliant virtual cost segregation study.")
    
    new_addr_query = st.text_input(
        "Property Address", 
        placeholder="Type address & press Enter (e.g., 6733 Willow St, Reston VA)...",
        help="Type at least the street number and name, then press Enter to see suggestions."
    )
    
    if len(new_addr_query.strip()) >= 4:
        try:
            r = requests.get("https://photon.komoot.io/api/", params={"q": new_addr_query, "limit": 5}, timeout=3)
            if r.status_code == 200:
                suggs = []
                for f in r.json().get("features", []):
                    p = f.get("properties", {})
                    parts = [p.get("housenumber"), p.get("street"), p.get("city"), p.get("state"), p.get("postcode")]
                    clean_str = ", ".join([str(v) for v in parts if v])
                    if clean_str and clean_str not in suggs:
                        suggs.append(clean_str)

                if suggs:
                    def on_modal_addr_select():
                        chosen = st.session_state["modal_addr_select_key"]
                        st.session_state["modal_selected_addr"] = chosen
                        specs = fetch_property_specs(chosen)
                        st.session_state["modal_price"] = int(specs["price"])
                        st.session_state["modal_type_index"] = 0 if "Commercial" in specs["prop_type"] else 1

                    st.selectbox(
                        "Suggested matching properties (select to auto-fill specs):",
                        suggs,
                        index=0,
                        key="modal_addr_select_key",
                        on_change=on_modal_addr_select
                    )
        except Exception:
            pass

    selected_addr = st.session_state.get("modal_selected_addr") or new_addr_query

    c1, c2 = st.columns(2)
    with c1:
        new_price = st.number_input(
            "Purchase Price / Basis ($)",
            min_value=50000,
            max_value=50000000,
            value=int(st.session_state["modal_price"]),
            step=25000
        )
        new_date = st.date_input("Placed in Service Date", value=datetime.date.today())

    with c2:
        prop_types = ["Commercial / Office", "Residential Multi-Family", "Short-Term Rental / Airbnb", "Industrial / Warehouse", "Retail"]
        new_type = st.selectbox(
            "Asset Classification",
            prop_types,
            index=st.session_state["modal_type_index"]
        )
        new_bonus = st.selectbox(
            "Bonus Depreciation Rate", 
            ["60% (Tax Year 2024)", "80% (Tax Year 2023)", "100% (Pre-2023)", "40% (Tax Year 2025)"]
        )

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Initialize Study & Add to Portfolio", type="primary", use_container_width=True):
        if selected_addr and len(selected_addr.strip()) > 5:
            reclass_rate = 0.30 if ("Short-Term" in new_type or "Commercial" in new_type) else 0.22
            reallocated_val = new_price * reclass_rate
            
            new_record = {
                "Property": selected_addr,
                "Placed in Service": str(new_date),
                "Basis": f"${new_price:,.0f}",
                "Reallocated": f"${reallocated_val:,.0f}",
                "Status": "Engineering Review",
                "raw_price": new_price,
                "raw_reclass": reallocated_val
            }
            st.session_state["user_studies"].append(new_record)
            st.success("New study created successfully!")
            st.rerun()
        else:
            st.error("Please enter a valid property address.")

# ----------------- Email Sender via Resend API -----------------
def send_real_email_code(recipient_email, code):
    api_key = st.secrets.get("RESEND_API_KEY")
    if not api_key:
        return False, "DEMO_MODE"

    url = "https://api.resend.com/emails"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    plain_text = f"Your Tax Flow Cost Seg verification code is: {code}\n\nExpires in 10 minutes."
    html_content = f"""
    <div style="font-family: sans-serif; max-width: 500px; padding: 24px; border: 1
