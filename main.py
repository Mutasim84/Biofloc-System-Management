import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, timedelta

# 1. PAGE & BRANDING CONFIG
st.set_page_config(page_title="Biofloc System Management", layout="wide", page_icon="🧬")

CARBON_SOURCES = {
    "Molasses (Liquid)": 0.40, "Cassava Starch": 0.50, "Wheat Flour": 0.45,
    "Cane Sugar (Sucrose)": 0.42, "Rice Flour": 0.44, "Corn Flour": 0.48
}

if 'farm_data' not in st.session_state:
    st.session_state.farm_data = {}

# --- 2. SMART SCIENTIFIC ADVISOR (TRAFFIC LIGHT SYSTEM) ---
def scientific_advisor(label, value, ideal_min, ideal_max, danger_min, danger_max, unit=""):
    """
    Provides Green (Safe), Yellow (Warning + Advice), or Red (Emergency + Action) feedback.
    """
    if ideal_min <= value <= ideal_max:
        st.success(f"✅ {label}: {value} {unit} (Safe) - Parameters are optimal.")
    elif (danger_min <= value < ideal_min) or (ideal_max < value <= danger_max):
        st.warning(f"🟡 {label}: {value} {unit} (Warning) - Suggested Action:")
        if label == "TAN": st.info("💡 Recommendation: Increase C:N ratio to 18:1; reduce feed intake by 20%.")
        if label == "DO": st.info("💡 Recommendation: Increase aeration; check for organic waste buildup.")
        if label == "FV": st.info("💡 Recommendation: Monitor floc density; prepare for water exchange.")
    else:
        st.error(f"🚨 {label}: {value} {unit} (Danger) - EMERGENCY ACTION REQUIRED:")
        if label == "TAN": st.write("🆘 EMERGENCY: Add 20:1 Carbon dose; STOP feeding for 24 hours.")
        if label == "DO": st.write("🆘 EMERGENCY: Oxygen levels critical! Start backup aerators.")
        if label == "FV": st.write("🆘 EMERGENCY: High Floc! Discharge 15-20% water from bottom.")
        if label == "pH": st.write("🆘 EMERGENCY: pH Instability! Buffer with Sodium Bicarbonate.")

# --- 3. SIDEBAR: REGISTRATION & NAVIGATION ---
with st.sidebar:
    st.header("🚜 Farm Control Center")
    currency = st.selectbox("Currency:", ["SAR", "USD", "EGP"])
    st.divider()
    st.subheader("Register New Pond")
    sec_map = {"Nursery": "N", "Grow-out": "G", "Fattening": "F", "Quarantine": "Q"}
    sec = st.selectbox("Sector Zone:", list(sec_map.keys()))
    num = st.number_input("Pond ID:", min_value=1, step=1)
    p_id = f"{sec_map[sec]}-{num}"
    
    if st.button("Register Pond"):
        if p_id not in st.session_state.farm_data:
            st.session_state.farm_data[p_id] = {
                "sector": sec, "logs": [], 
                "settings": {"vol": 0.0, "target_w": 500, "stock_count": 1000, "mortality": 0},
                "finance": {"feed_cost": 0.0, "carbon_cost": 0.0, "misc": 0.0},
                "feed_history": {"total_feed_kg": 0.0, "protein_avg": 30.0}
            }
            st.success(f"Pond {p_id} Activated.")

# --- 4. EXECUTIVE DASHBOARD ---
st.title("📊 Biofloc System Management")
if st.session_state.farm_data:
    dash = st.columns(4)
    total_bio = sum([v['logs'][-1]['Biomass'] if v['logs'] else 0 for v in st.session_state.farm_data.values()])
    total_exp = sum([sum(v['finance'].values()) for v in st.session_state.farm_data.values()])
    
    dash[0].metric("Total Biomass", f"{total_bio:.1f} kg")
    dash[1].metric("Total Investment", f"{total_exp:,.0f} {currency}")
    dash[2].metric("Active Ponds", len(st.session_state.farm_data))
    dash[3].metric("Current Date", str(date.today()))

st.divider()

# --- 5. POND MANAGEMENT ENGINE ---
if st.session_state.farm_data:
    active_id = st.selectbox("🎯 Select Pond to Manage:", sorted(st.session_state.farm_data.keys()))
    p_ref = st.session_state.farm_data[active_id]
    
    tabs = st.tabs(["📐 Setup", "🧪 Water Analysis", "🐟 Growth & Biology", "💡 Carbon Advisor", "🌬️ Aeration", "💰 Finance"])

    # --- TAB 0: Setup ---
    with tabs[0]:
        c1, c2 = st.columns(2)
        shape = c1.radio("Geometry:", ("Circular", "Rectangular"), key=f"sh_{active_id}")
        if shape == "Circular":
            r = c1.number_input("Radius (m)", value=3.0)
            d = c1.number_input("Depth (m)", value=1.2)
            p_ref['settings']['vol'] = np.pi * (r**2) * d
        else:
            p_ref['settings']['vol'] = c1.number_input("Length") * c1.number_input("Width") * c1.number_input("Depth")
        
        p_ref['settings']['stock_count'] = c2.number_input("Initial Stock (pcs)", value=1000)
        p_ref['settings']['target_w'] = c2.number_input("Harvest Target (g)", value=500)
        p_ref['settings']['mortality'] = c2.number_input("Total Mortalities (pcs)", value=0)
        st.metric("Pond Volume", f"{p_ref['settings']['vol']:.2f} m³")

    # --- TAB 1: Water Quality ---
    with tabs[1]:
        st.subheader("Water Analysis & Advisor")
        wc = st.columns(4)
        temp = wc[0].number_input("Temp (°C)", value=28.0)
        do = wc[1].number_input("DO (Oxygen)", value=5.5)
        ph = wc[2].number_input("pH Level", value=7.5)
        fv = wc[3].number_input("Floc Vol (FV)", value=25.0)
        
        nc = st.columns(3)
        tan = nc[0].number_input("Ammonia (TAN)", value=0.1)
        no2 = nc[1].number_input("Nitrite (NO2)", value=0.0)
        alk = nc[2].number_input("Alkalinity", value=150.0)

        st.divider()
        scientific_advisor("DO", do, 5.0, 8.5, 3.5, 12.0, "mg/L")
        scientific_advisor("TAN", tan, 0.0, 0.5, 0.5, 1.2, "mg/L")
        scientific_advisor("FV", fv, 15.0, 40.0, 5.0, 60.0, "ml/L")
        scientific_advisor("pH", ph, 7.2, 8.2, 6.5, 9.0)

    # --- TAB 2: Biology (SGR, DGR, FCR, Survival) ---
    with tabs[2]:
        st.subheader("Biological Performance")
        bc1, bc2 = st.columns(2)
        s_count = bc1.number_input("Sample Count (pcs)", value=30)
        s_weight = bc2.number_input("Total Sample Weight (g)", value=0.0)
        avg_w = s_weight / s_count if s_count > 0 else 1
        
        # Survival & Biomass
        surv_rate = ((p_ref['settings']['stock_count'] - p_ref['settings']['mortality']) / p_ref['settings']['stock_count']) * 100
        biomass = ((p_ref['settings']['stock_count'] - p_ref['settings']['mortality']) * avg_w) / 1000
        
        # SGR & DGR Logic
        dgr, sgr = 0.0, 0.0
        if p_ref['logs']:
            last = p_ref['logs'][-1]
            days = (date.today() - last['Date']).days or 1
            dgr = (avg_w - last['Weight']) / days
            sgr = (np.log(avg_w) - np.log(last['Weight'])) / days * 100 if avg_w > 0 else 0
        
        # Feed Conversion Ratio (FCR)
        fcr = p_ref['feed_history']['total_feed_kg'] / biomass if biomass > 0 else 0
        
        m_col = st.columns(4)
        m_col[0].metric("Survival Rate", f"{surv_rate:.1f}%")
        m_col[1].metric("Current Biomass", f"{biomass:.1f} kg")
        m_col[2].metric("FCR", f"{fcr:.2f}")
        m_col[3].metric("Daily Growth (DGR)", f"{dgr:.2f} g/d")
        
        days_to_harvest = (p_ref['settings']['target_w'] - avg_w) / (dgr if dgr > 0 else 1.5)
        st.info(f"📅 Estimated Harvest Date: {date.today() + timedelta(days=int(days_to_harvest))}")

    # --- TAB 3: Carbon Advisor ---
    with tabs[3]:
        st.subheader("C:N Balance Advisor")
        ratio = 15
        if tan > 0.8: ratio = 20
        elif fv < 15: ratio = 18
        
        src = st.selectbox("Carbon Source:", list(CARBON_SOURCES.keys()))
        f_daily = st.number_input("Today's Feed Intake (kg)")
        prot = st.number_input("Feed Protein %", value=30.0)
        
        # Calculation Formula
        dose = (f_daily * (prot/100) * 0.16 * ratio) / CARBON_SOURCES[src]
        st.info(f"Apply **{dose:.3f} kg** of {src} to maintain C:N ratio of {ratio}:1")

    # --- TAB 4: Aeration ---
    with tabs[4]:
        st.subheader("Aeration Audit")
        hp = st.number_input("Operational HP", value=1.0)
        needed_hp = (biomass / 500) * (1.3 if fv > 30 else 1.0)
        st.metric("Scientific HP Needed", f"{needed_hp:.2f} HP")
        if hp < needed_hp: st.error("DANGER: Insufficient aeration for current biomass!")

    # --- TAB 5: Finance ---
    with tabs[5]:
        st.subheader(f"Economic Tracker ({currency})")
        new_exp = st.number_input("Add Expense Amount")
        feed_add = st.number_input("Total Feed Added (kg)", min_value=0.0)
        if st.button("Update Finance"):
            p_ref['finance']['misc'] += new_exp
            p_ref['feed_history']['total_feed_kg'] += feed_add
            st.success("Financial log updated.")
        
        st.metric("Total Pond Cost", f"{sum(p_ref['finance'].values()):,.1f} {currency}")

    if st.button(f"💾 SYNC & SAVE POND {active_id}"):
        p_ref['logs'].append({
            "Date": date.today(), "Weight": avg_w, "TAN": tan, 
            "FV": fv, "Biomass": biomass, "SGR": sgr
        })
        st.success("All biological and engineering data synchronized.")

# --- 6. EXPORT ---
st.divider()
if st.button("📥 Export Global CSV"):
    st.write("Preparing farm-wide report...")
