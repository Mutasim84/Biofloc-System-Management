import streamlit as st
import pandas as pd
import numpy as np
import json
import os
from datetime import date, timedelta
import io
from huggingface_hub import HfApi, Repository
from datasets import Dataset, DatasetDict
import tempfile

# ========================= CONFIGURATION =========================
st.set_page_config(page_title="Biofloc System Management", layout="wide", page_icon="🧬")

# Hugging Face settings - يجب تعيين هذه المتغيرات في Secrets
HF_TOKEN = st.secrets.get("HF_TOKEN", None)  # سيتم تعيينه في Space settings
REPO_ID = "YOUR_USERNAME/YOUR_DATASET_NAME"  # غيّره إلى اسم المستودع الخاص بك

DATA_FILE = "biofloc_data.json"  # سنستخدمه كنسخة مؤقتة فقط

CARBON_SOURCES = {
    "Molasses (Liquid)": 0.40,
    "Cassava Starch": 0.50,
    "Wheat Flour": 0.45,
    "Cane Sugar (Sucrose)": 0.42,
    "Rice Flour": 0.44,
    "Corn Flour": 0.48
}

# ========================= DATA PERSISTENCE (Hugging Face Datasets) =========================
def load_data_from_hf():
    """تحميل البيانات من Hugging Face Dataset إذا كان موجوداً، وإلا إنشاء بيانات افتراضية"""
    if HF_TOKEN is None:
        st.error("HF_TOKEN not found in secrets. Please add it in Space settings.")
        return {"D-1": create_demo_pond()}
    
    try:
        from datasets import load_dataset
        # محاولة تحميل dataset باسم REPO_ID
        dataset = load_dataset(REPO_ID, split="train", token=HF_TOKEN)
        if len(dataset) == 0:
            # لا توجد بيانات، نعيد الافتراضي
            return {"D-1": create_demo_pond()}
        # أول صف يحتوي على البيانات المخزنة كـ JSON
        data_str = dataset[0]["data"]
        farm_data = json.loads(data_str)
        return farm_data
    except Exception as e:
        st.warning(f"Could not load dataset from HF: {e}. Starting with default demo pond.")
        return {"D-1": create_demo_pond()}

def save_data_to_hf(farm_data):
    """حفظ البيانات إلى Hugging Face Dataset"""
    if HF_TOKEN is None:
        st.error("Cannot save: HF_TOKEN missing.")
        return False
    try:
        from datasets import Dataset
        # تحويل البيانات إلى سلسلة JSON
        data_str = json.dumps(farm_data, default=str)
        # إنشاء dataset جديد بسجل واحد
        dataset = Dataset.from_dict({"data": [data_str]})
        # دفع إلى Hugging Face (يتطلب وجود repo مسبق)
        dataset.push_to_hub(REPO_ID, token=HF_TOKEN, split="train", private=False)
        return True
    except Exception as e:
        st.error(f"Failed to save to HF: {e}")
        return False

def create_demo_pond():
    return {
        "sector": "Demo",
        "active": True,
        "settings": {
            "vol": 50.0,
            "target_w": 500,
            "stock_count": 1000,
            "mortality": 0,
            "avg_weight": 50.0
        },
        "finance": {"feed_cost": 0.0, "carbon_cost": 0.0, "misc": 0.0},
        "feed_history": {"total_feed_kg": 0.0, "protein_avg": 30.0, "daily_feed_given": 0.0},
        "logs": []
    }

# تحميل البيانات عند بدء التشغيل
if 'farm_data' not in st.session_state:
    st.session_state.farm_data = load_data_from_hf()

def save_data():
    """دالة مساعدة لحفظ البيانات الحالية إلى HF وتحديث session_state"""
    success = save_data_to_hf(st.session_state.farm_data)
    if success:
        st.success("Data saved permanently to Hugging Face Hub.")
    else:
        st.error("Failed to save data remotely. Changes may be lost on restart.")
    return success

# ========================= HELPER FUNCTIONS (لم تتغير) =========================
def calculate_biomass(stock_count, mortality, avg_weight_g):
    live_fish = stock_count - mortality
    return (live_fish * avg_weight_g) / 1000.0

def recommended_daily_feed(biomass_kg, avg_weight_g):
    if avg_weight_g < 10:
        rate = 6.0
    elif avg_weight_g < 100:
        rate = 4.0
    else:
        rate = 2.0
    return biomass_kg * (rate / 100.0)

def carbon_needed_from_tan(tan_mgL, pond_vol_m3, feed_kg, protein_pct):
    if tan_mgL < 0.3:
        target_cn = 12
    elif tan_mgL < 0.8:
        target_cn = 15
    else:
        target_cn = 20
    
    nitrogen_from_feed = feed_kg * (protein_pct / 100) * 0.16
    tan_kg = (tan_mgL * pond_vol_m3) / 1000.0
    total_nitrogen = nitrogen_from_feed + tan_kg * 0.82
    carbon_needed_kg = total_nitrogen * target_cn
    return carbon_needed_kg, target_cn

def lactobacillus_dose(pond_vol_m3, tan_mgL):
    if tan_mgL > 0.5:
        dose_ml_per_m3 = 30.0
        reason = "therapeutic (high ammonia)"
    else:
        dose_ml_per_m3 = 10.0
        reason = "prophylactic maintenance"
    total_ml = pond_vol_m3 * dose_ml_per_m3
    return total_ml / 1000.0, reason

def lactobacillus_materials(volume_liters):
    rice_kg = volume_liters * 0.1
    milk_liters = volume_liters * 0.5
    sugar_kg = volume_liters * 0.05
    water_liters = volume_liters * 0.5
    return rice_kg, milk_liters, sugar_kg, water_liters

def scientific_advisor(label, value, ideal_min, ideal_max, danger_min, danger_max, unit=""):
    if ideal_min <= value <= ideal_max:
        st.success(f"✅ {label}: {value} {unit} (Safe)")
    elif (danger_min <= value < ideal_min) or (ideal_max < value <= danger_max):
        st.warning(f"🟡 {label}: {value} {unit} (Warning)")
    else:
        st.error(f"🚨 {label}: {value} {unit} (Danger)")

def export_to_excel():
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        summary = []
        for pid, data in st.session_state.farm_data.items():
            if not data.get('active', True):
                continue
            biomass = calculate_biomass(data['settings']['stock_count'], data['settings']['mortality'], data['settings'].get('avg_weight', 50))
            summary.append({
                "Pond ID": pid,
                "Sector": data['sector'],
                "Volume (m3)": data['settings'].get('vol', 0),
                "Stock": data['settings']['stock_count'],
                "Mortality": data['settings']['mortality'],
                "Avg Weight (g)": data['settings'].get('avg_weight', 50),
                "Biomass (kg)": biomass,
                "Total Feed (kg)": data['feed_history']['total_feed_kg'],
                "Total Cost": sum(data['finance'].values())
            })
        if summary:
            pd.DataFrame(summary).to_excel(writer, sheet_name="Ponds Summary", index=False)
        all_logs = []
        for pid, data in st.session_state.farm_data.items():
            for log in data.get('logs', []):
                all_logs.append({
                    "Pond ID": pid,
                    "Date": log['Date'],
                    "Weight_g": log.get('Weight', 0),
                    "TAN_mgL": log.get('TAN', 0),
                    "FV_mlL": log.get('FV', 0),
                    "Biomass_kg": log.get('Biomass', 0)
                })
        if all_logs:
            pd.DataFrame(all_logs).to_excel(writer, sheet_name="Historical Logs", index=False)
    output.seek(0)
    return output

# ========================= SIDEBAR (تم تعديل زر الحفظ لاستخدام save_data) =========================
with st.sidebar:
    st.header("🚜 Farm Control Center")
    currency = st.selectbox("Currency:", ["SAR", "USD", "EGP"])
    st.divider()
    st.subheader("Register New Pond")
    sec_map = {"Nursery": "N", "Grow-out": "G", "Fattening": "F", "Quarantine": "Q"}
    sector = st.selectbox("Sector Zone:", list(sec_map.keys()))
    num = st.number_input("Pond ID:", min_value=1, step=1)
    new_pond_id = f"{sec_map[sector]}-{num}"
    if st.button("➕ Register Pond"):
        if new_pond_id not in st.session_state.farm_data:
            st.session_state.farm_data[new_pond_id] = {
                "sector": sector,
                "active": True,
                "settings": {"vol": 0.0, "target_w": 500, "stock_count": 1000, "mortality": 0, "avg_weight": 50.0},
                "finance": {"feed_cost": 0.0, "carbon_cost": 0.0, "misc": 0.0},
                "feed_history": {"total_feed_kg": 0.0, "protein_avg": 30.0, "daily_feed_given": 0.0},
                "logs": []
            }
            save_data()  # حفظ بعد الإضافة
            st.success(f"Pond {new_pond_id} activated.")
        else:
            st.warning("Pond ID already exists.")
    st.divider()
    st.subheader("End Pond Cycle")
    active_ponds_list = [pid for pid, data in st.session_state.farm_data.items() if data.get('active', True)]
    if active_ponds_list:
        pond_to_end = st.selectbox("Select pond to delete:", active_ponds_list)
        if st.button("❌ End Cycle & Delete"):
            del st.session_state.farm_data[pond_to_end]
            save_data()
            st.success(f"Pond {pond_to_end} deleted.")
            st.rerun()
    
    # زر إضافي للحفظ اليدوي
    if st.button("💾 Save all data to cloud (manual)"):
        save_data()

# ========================= MAIN DASHBOARD =========================
st.title("📊 Biofloc System Management (Persistent on Hugging Face)")
active_ponds = {k:v for k,v in st.session_state.farm_data.items() if v.get('active', True)}
if active_ponds:
    total_biomass = sum([calculate_biomass(v['settings']['stock_count'], v['settings']['mortality'], v['settings'].get('avg_weight', 50)) for v in active_ponds.values()])
    total_cost = sum([sum(v['finance'].values()) for v in active_ponds.values()], 0.0)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Biomass", f"{total_biomass:.1f} kg")
    c2.metric("Total Investment", f"{total_cost:,.0f} {currency}")
    c3.metric("Active Ponds", len(active_ponds))
    c4.metric("Today", str(date.today()))
else:
    st.info("No active ponds. Register one from sidebar.")
st.divider()

# ========================= POND MANAGEMENT =========================
if active_ponds:
    selected_pond = st.selectbox("🎯 Select Pond to Manage:", sorted(active_ponds.keys()))
    pond = st.session_state.farm_data[selected_pond]
    
    tabs = st.tabs(["📐 Setup", "🧪 Water Quality", "🐟 Feed & Growth", "💡 Carbon Advisor", "🦠 Probiotic Dose", "💰 Finance", "📊 Logs"])
    
    # ---------- TAB 0: Setup ----------
    with tabs[0]:
        col1, col2 = st.columns(2)
        with col1:
            shape = st.radio("Geometry:", ("Circular", "Rectangular"), key=f"shape_{selected_pond}")
            if shape == "Circular":
                r = st.number_input("Radius (m)", 3.0, key=f"rad_{selected_pond}")
                d = st.number_input("Depth (m)", 1.2, key=f"dep_{selected_pond}")
                pond['settings']['vol'] = np.pi * r**2 * d
            else:
                L = st.number_input("Length (m)", 5.0, key=f"len_{selected_pond}")
                W = st.number_input("Width (m)", 4.0, key=f"wid_{selected_pond}")
                D = st.number_input("Depth (m)", 1.2, key=f"dep2_{selected_pond}")
                pond['settings']['vol'] = L * W * D
        with col2:
            pond['settings']['stock_count'] = st.number_input("Initial Stock (pcs)", pond['settings']['stock_count'], key=f"stock_{selected_pond}")
            pond['settings']['target_w'] = st.number_input("Harvest Target (g)", pond['settings']['target_w'], key=f"target_{selected_pond}")
            pond['settings']['mortality'] = st.number_input("Total Mortalities (pcs)", pond['settings']['mortality'], key=f"mort_{selected_pond}")
            pond['settings']['avg_weight'] = st.number_input("Average Weight (g)", pond['settings']['avg_weight'], key=f"avgw_{selected_pond}")
        st.metric("Pond Volume", f"{pond['settings']['vol']:.2f} m³")
    
    # ---------- TAB 1: Water Quality ----------
    with tabs[1]:
        st.subheader("Current Water Parameters")
        cols = st.columns(4)
        temp = cols[0].number_input("Temp (°C)", 28.0, key=f"temp_{selected_pond}")
        do = cols[1].number_input("DO (mg/L)", 5.5, key=f"do_{selected_pond}")
        ph = cols[2].number_input("pH", 7.5, key=f"ph_{selected_pond}")
        fv = cols[3].number_input("Floc Vol (mL/L)", 25.0, key=f"fv_{selected_pond}")
        cols2 = st.columns(3)
        tan = cols2[0].number_input("TAN (mg/L)", 0.1, key=f"tan_{selected_pond}")
        no2 = cols2[1].number_input("Nitrite (mg/L)", 0.0, key=f"no2_{selected_pond}")
        alk = cols2[2].number_input("Alkalinity (mg/L)", 150.0, key=f"alk_{selected_pond}")
        st.divider()
        scientific_advisor("DO", do, 5.0, 8.5, 3.5, 12.0, "mg/L")
        scientific_advisor("TAN", tan, 0.0, 0.5, 0.5, 1.2, "mg/L")
        scientific_advisor("FV", fv, 15.0, 40.0, 5.0, 60.0, "mL/L")
        scientific_advisor("pH", ph, 7.2, 8.2, 6.5, 9.0, "")
    
    # ---------- TAB 2: Feed & Growth ----------
    with tabs[2]:
        st.subheader("Feeding Management")
        biomass = calculate_biomass(pond['settings']['stock_count'], pond['settings']['mortality'], pond['settings']['avg_weight'])
        rec_feed = recommended_daily_feed(biomass, pond['settings']['avg_weight'])
        st.metric("Current Biomass", f"{biomass:.2f} kg")
        st.metric("Recommended Daily Feed", f"{rec_feed:.2f} kg")
        feed_given = st.number_input("Actual Feed Given Today (kg)", rec_feed, key=f"feed_given_{selected_pond}")
        protein_pct = st.number_input("Feed Protein %", 30.0, key=f"prot_{selected_pond}")
        if st.button("Record Feeding", key=f"rec_feed_{selected_pond}"):
            pond['feed_history']['total_feed_kg'] += feed_given
            pond['feed_history']['daily_feed_given'] = feed_given
            pond['feed_history']['protein_avg'] = protein_pct
            save_data()
            st.success(f"Recorded {feed_given} kg. Total feed: {pond['feed_history']['total_feed_kg']:.2f} kg")
        if pond['logs']:
            last_log = pond['logs'][-1]
            days_diff = (date.today() - last_log['Date']).days or 1
            dgr = (pond['settings']['avg_weight'] - last_log.get('Weight', pond['settings']['avg_weight'])) / days_diff
            sgr = (np.log(pond['settings']['avg_weight']) - np.log(last_log.get('Weight', 1))) / days_diff * 100 if pond['settings']['avg_weight'] > 0 else 0
            fcr = pond['feed_history']['total_feed_kg'] / biomass if biomass > 0 else 0
            colG1, colG2, colG3 = st.columns(3)
            colG1.metric("DGR (g/day)", f"{dgr:.2f}")
            colG2.metric("SGR (%/day)", f"{sgr:.2f}")
            colG3.metric("FCR", f"{fcr:.2f}")
    
    # ---------- TAB 3: Carbon Advisor ----------
    with tabs[3]:
        st.subheader("Dynamic Carbon Requirement Based on Ammonia")
        pond_vol = pond['settings']['vol']
        daily_feed_used = pond['feed_history'].get('daily_feed_given', 0)
        prot_used = pond['feed_history'].get('protein_avg', 30)
        carbon_needed, target_cn = carbon_needed_from_tan(tan, pond_vol, daily_feed_used, prot_used)
        st.info(f"📊 Current TAN: {tan} mg/L → Recommended C:N ratio: **{target_cn}:1**")
        source = st.selectbox("Carbon Source:", list(CARBON_SOURCES.keys()), key=f"cs_{selected_pond}")
        source_kg = carbon_needed / CARBON_SOURCES[source]
        st.success(f"💧 Add **{source_kg:.3f} kg** of {source} to balance ammonia.")
        if st.button("Log Carbon Addition", key=f"carb_log_{selected_pond}"):
            pond['finance']['carbon_cost'] += source_kg * 0.5
            save_data()
            st.success("Carbon addition recorded.")
    
    # ---------- TAB 4: Probiotic Dose (Lactobacillus) ----------
    with tabs[4]:
        st.subheader("🦠 Lactobacillus Probiotic Preparation")
        st.markdown("Based on Indonesian method (rice wash + milk fermentation) - YouTube 21 min video")
        method = st.radio("Choose calculation method:", 
                          ["Amount in Liters (prepare specific volume)", 
                           "Based on Pond Size (calculate from pond volume)"])
        if method == "Amount in Liters (prepare specific volume)":
            target_liters = st.number_input("How many liters of Lactobacillus solution do you want to prepare?", 
                                            min_value=0.5, value=1.0, step=0.5, key=f"lacto_liters_{selected_pond}")
            rice, milk, sugar, water = lactobacillus_materials(target_liters)
            st.info(f"**For {target_liters:.1f} L of active Lactobacillus culture:**")
        else:
            pond_vol = pond['settings']['vol']
            if pond_vol <= 0:
                st.warning("⚠️ Pond volume not set. Please go to Setup tab and define pond dimensions first.")
                rice = milk = sugar = water = 0
                target_liters = 0
            else:
                default_ml_per_m3 = 20.0
                dose_ml_per_m3 = st.number_input("Recommended dose (ml per m³ of pond water)", 
                                                  min_value=5.0, max_value=50.0, value=default_ml_per_m3, step=1.0,
                                                  help="Scientific range: 10-30 ml/m³. Use higher dose (30) for high ammonia.")
                target_liters = (pond_vol * dose_ml_per_m3) / 1000.0
                st.info(f"📐 Pond volume: **{pond_vol:.2f} m³** → Recommended dose: **{dose_ml_per_m3} ml/m³** → Total solution needed: **{target_liters:.2f} L**")
                rice, milk, sugar, water = lactobacillus_materials(target_liters)
        if target_liters > 0:
            st.subheader("📦 Raw Materials Required (Exact Quantities)")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("🍚 Rice (or rice flour)", f"{rice:.2f} kg")
            col2.metric("🥛 Fresh Milk (or reconstituted)", f"{milk:.2f} L")
            col3.metric("🍬 Sugar (brown or molasses)", f"{sugar:.2f} kg")
            col4.metric("💧 Clean Water (chlorine-free)", f"{water:.2f} L")
            with st.expander("🔬 Step-by-Step Preparation Instructions (Indonesian method)"):
                st.markdown("""
                **Protocol for Lactobacillus culture (fermented rice wash + milk):**
                1. **Prepare rice wash:** Wash the required amount of rice with clean water. **Keep the second wash water** (milky white).
                2. **Mix ingredients:** In a clean glass or plastic container, combine:
                   - Rice wash water (from step 1)
                   - Fresh milk
                   - Sugar (dissolved in a little warm water)
                   - Additional chlorine-free water
                3. **Cover loosely:** Cover with a clean cloth or paper towel and secure with a rubber band.
                4. **Ferment:** Place in a warm, dark place (25-35°C) for **3–7 days**.
                5. **Check for completion:** You will see three layers: top yellowish liquid (whey) – **this is your probiotic**.
                6. **Separate:** Collect only the yellowish liquid (whey).
                7. **Storage:** Refrigerate for up to 2 months.
                8. **Application:** Dilute 1:20 with pond water or mix 10 ml per 1 kg of feed.
                """)
            if st.button("📝 Log Probiotic Addition to Pond", key=f"log_prob_{selected_pond}"):
                if 'probiotic_log' not in pond:
                    pond['probiotic_log'] = []
                pond['probiotic_log'].append({
                    "Date": str(date.today()),
                    "Volume_Liters": target_liters,
                    "Method": method,
                    "Rice_kg": rice,
                    "Milk_L": milk,
                    "Sugar_kg": sugar,
                    "Water_L": water
                })
                save_data()
                st.success(f"Probiotic addition of {target_liters:.2f} L logged.")
        else:
            st.info("Please set pond volume or enter a positive volume to continue.")
    
    # ---------- TAB 5: Finance ----------
    with tabs[5]:
        st.subheader(f"Expenses ({currency})")
        new_exp = st.number_input("Add Expense Amount", 0.0, key=f"exp_{selected_pond}")
        if st.button("Update Finance", key=f"fin_{selected_pond}"):
            pond['finance']['misc'] += new_exp
            save_data()
            st.success("Finance updated.")
        total_pond_cost = sum(pond['finance'].values())
        st.metric("Total Pond Cost", f"{total_pond_cost:,.2f} {currency}")
    
    # ---------- TAB 6: Logs and Save ----------
    with tabs[6]:
        st.subheader("Save Today's Data")
        if st.button(f"💾 Sync & Save Pond {selected_pond}", key=f"save_{selected_pond}"):
            pond['logs'].append({
                "Date": date.today(),
                "Weight": pond['settings']['avg_weight'],
                "TAN": tan,
                "FV": fv,
                "Biomass": biomass,
            })
            save_data()
            st.success("Data saved.")
        if pond['logs']:
            df_logs = pd.DataFrame(pond['logs'])
            st.dataframe(df_logs)

# ========================= EXPORT TO EXCEL =========================
st.divider()
col_btn, _ = st.columns([1, 3])
with col_btn:
    if st.button("📎 Export All Data to Excel (Download)"):
        excel_file = export_to_excel()
        st.download_button(
            label="📥 Download Excel File",
            data=excel_file,
            file_name=f"biofloc_export_{date.today()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
