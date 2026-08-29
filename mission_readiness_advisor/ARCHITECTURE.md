# Mission Readiness Advisor — Architecture Summary

> IBM August Challenge · AI-powered Launch Risk Assessment

---

## สรุปภาพรวมของระบบ

**Mission Readiness Advisor** คือระบบ AI ที่ใช้ประเมิน **ความพร้อมและความเสี่ยงของการปล่อยจรวด (Launch Readiness)** โดยรวบรวมข้อมูลจากหลายแหล่งพร้อมกัน ได้แก่ สภาพอากาศผิวพื้น, สภาพอวกาศ (Space Weather) และประวัติการปล่อยในอดีต แล้วคำนวณเป็น "คะแนนความเสี่ยงในการล่าช้า" พร้อมคำแนะนำ **GO / CAUTION / NO-GO** ให้กับผู้บัญชาการภารกิจ

---

## Frameworks & Libraries หลัก

| ประเภท | Library / Framework | รุ่น | หน้าที่ |
|--------|---------------------|------|---------|
| **UI / Dashboard** | [Streamlit](https://streamlit.io/) | ≥ 1.35.0 | หน้าเว็บ interactive dashboard ทั้งหมด |
| **Charts** | Plotly | ≥ 5.22.0 | Gauge chart, Bar chart, Line chart แสดงผล |
| **Data Processing** | Pandas + NumPy | ≥ 2.0 / ≥ 1.26 | โหลดและกรองข้อมูล CSV |
| **ML Model** | XGBoost + scikit-learn | ≥ 2.0 / ≥ 1.4 | สำหรับโมเดล predictive (train ใน notebook) |
| **HTTP Client** | Requests | ≥ 2.31.0 | เรียก external API ทั้งหมด |
| **Config / Env** | python-dotenv | ≥ 1.0.0 | โหลด API keys จาก `.env` file |
| **LLM** | IBM watsonx.ai (`ibm-watsonx-ai`) | ≥ 1.0.4 | ใช้ IBM Granite สร้างข้อความอธิบายผล (optional) |

---

## โครงสร้างไฟล์ (File Structure)

```
mission_readiness_advisor/
│
├── app.py                      ← Entry point: Streamlit Dashboard
├── config.py                   ← API keys, launch sites, risk weights, dataset paths
├── llm_advisor.py              ← IBM Granite / watsonx.ai integration
├── requirements.txt            ← Python dependencies
├── .env.example                ← Template สำหรับ API keys
│
├── api_clients/                ← ชั้น External Data Fetchers
│   ├── weather_client.py       ← OpenWeatherMap API
│   ├── donki_client.py         ← NASA DONKI Space Weather API
│   └── mission_history.py      ← Launch Library 2 API (historical launches)
│
├── core/                       ← ชั้น Business Logic / Risk Engine
│   ├── risk_engine.py          ← Aggregation engine หลัก → สร้าง MissionRiskReport
│   ├── lcc_rules.py            ← Launch Commit Criteria (NASA-STD-4010A + Eastern Range)
│   └── space_weather_risk.py   ← Space weather scoring จาก datasets + live API
│
└── assets/
    └── NASA_STD_4010B_2026.pdf ← เอกสารมาตรฐาน NASA อ้างอิง
```

---

## สถาปัตยกรรมระบบ (System Architecture)

```
┌─────────────────────────────────────────────────────────────┐
│                      app.py (Streamlit UI)                  │
│  Sidebar: mission params │ Main: charts + tables + advisory  │
└────────────┬────────────────────────────────────────────────┘
             │  calls
             ▼
┌─────────────────────────────────────────────────────────────┐
│              core/risk_engine.py                             │
│         evaluate_mission_readiness()                         │
│                                                             │
│   ┌──────────────┐  ┌─────────────────┐  ┌──────────────┐  │
│   │  Weather     │  │  Space Weather  │  │  Historical  │  │
│   │  Dimension   │  │  Dimension      │  │  Dimension   │  │
│   │  (weight 45%)│  │  (weight 35%)   │  │  (weight 20%)│  │
│   └──────┬───────┘  └────────┬────────┘  └──────┬───────┘  │
└──────────┼──────────────────┼──────────────────┼───────────┘
           │                  │                  │
     ┌─────▼──────┐    ┌──────▼──────┐    ┌──────▼──────┐
     │ core/      │    │ core/       │    │ api_clients/│
     │ lcc_rules  │    │ space_wx_   │    │ mission_    │
     │ .py        │    │ risk.py     │    │ history.py  │
     └─────┬──────┘    └──────┬──────┘    └──────┬──────┘
           │                  │                  │
     ┌─────▼──────┐    ┌──────▼──────┐    ┌──────▼──────┐
     │ api_clients│    │ api_clients/│    │ Launch      │
     │ /weather_  │    │ donki_      │    │ Library 2   │
     │ client.py  │    │ client.py   │    │ API (REST)  │
     └─────┬──────┘    └──────┬──────┘    └─────────────┘
           │                  │
     ┌─────▼──────┐    ┌──────▼──────┐
     │ OpenWeather│    │ NASA DONKI  │
     │ Map API    │    │ API         │
     │ (live)     │    │ (live)      │
     └────────────┘    └──────┬──────┘
                              │ + local CSV datasets
                        ┌─────▼──────────────────────┐
                        │ ../Datasets/*.csv           │
                        │  - solar_flares.csv         │
                        │  - geomagnetic_storms.csv   │
                        │  - cme_events_2year.csv     │
                        │  - daily_solar_data.csv     │
                        │  - daily_geomagnetic_data   │
                        │  - high_speed_streams.csv   │
                        └────────────────────────────┘
```

---

## การทำงานของระบบ (How It Works)

### 1. UI Layer — `app.py`

- ผู้ใช้เลือก **Launch Site** (KSC / Vandenberg / Cape Canaveral / Baikonur / Jiuquan) และ **วันปล่อย**
- กรอกค่าสภาพอากาศด้วยตนเอง (wind, visibility, temperature, humidity, precipitation)
- ติ๊กเลือก Cloud Rules จาก NASA-STD-4010A (cumulonimbus, anvil clouds ฯลฯ)
- กด **"Evaluate Mission Readiness"** → ระบบรันการประเมินผ่าน `cached_evaluate()` (cache 5 นาที)

### 2. Risk Engine — `core/risk_engine.py`

ฟังก์ชันหลัก `evaluate_mission_readiness()` รวมคะแนน 3 มิติ:

| มิติ | น้ำหนัก | แหล่งข้อมูล |
|------|---------|------------|
| Weather Risk | **45%** | LCC Rules Engine + manual input |
| Space Weather Risk | **35%** | NASA DONKI API + local CSV datasets |
| Historical Risk | **20%** | Launch Library 2 API |

ผลลัพธ์รวมเป็น `MissionRiskReport` ที่มี:
- `overall_score` (0.0–1.0)
- `recommendation`: **GO** (< 35%) / **CAUTION** (35–65%) / **NO-GO** (> 65% หรือมี SCRUB rule)
- `confidence`: HIGH / MEDIUM / LOW (ขึ้นกับว่าได้ข้อมูล real-time มากแค่ไหน)

### 3. Launch Commit Criteria — `core/lcc_rules.py`

ระบบตรวจสอบ **15 กฎ** ตามมาตรฐาน NASA-STD-4010A และ Eastern Range:

| กฎ | มาตรฐานอ้างอิง | ตัวอย่างเงื่อนไข SCRUB |
|----|---------------|----------------------|
| W1 – Surface Winds | Eastern Range | > 30 knots |
| W2 – Lightning | STD-4010A §3.1 | ฟ้าผ่าในรัศมี 10 NM |
| W3 – Temperature | Eastern Range | < -0.6°C หรือ > 43.3°C |
| W4 – Precipitation | Eastern Range | ≥ 25 mm/hr หรือมีลูกเห็บ |
| W5 – Visibility | Eastern Range | < 3 miles |
| W6 – Humidity | Eastern Range | > 95% (CAUTION) |
| §3.2 – Cumulus Top | STD-4010A | > 25,000 ft MSL |
| §3.3 – Cumulonimbus | STD-4010A | ภายใน 20 NM |
| §3.4/3.7 – Attached Anvil | STD-4010A | อยู่ในเส้นทางบิน |
| §3.5 – Debris Cloud | STD-4010A | อยู่ในเส้นทางบิน |
| §3.6 – Cloud Thickness | STD-4010A | > 4,500 ft |
| §3.8 – Detached Anvil | STD-4010A | อยู่ในเส้นทางบิน |
| §3.9 – Tropical Storm | STD-4010A | ภายใน 300 NM |

> กฎใดถูก Violate ในระดับ SCRUB จะบังคับ NO-GO ทันที โดยไม่สนใจคะแนนรวม

### 4. Space Weather Scoring — `core/space_weather_risk.py`

คำนวณความเสี่ยงจากปัจจัย 4 ด้าน:

| ปัจจัย | น้ำหนัก | ข้อมูล |
|--------|---------|-------|
| Geomagnetic Storm (Kp Index) | 45% | `daily_geomagnetic_data.csv` + NASA DONKI GST API |
| Solar Flare Class (A→X) | 30% | `solar_flares.csv` + NASA DONKI FLR API |
| CME Events (speed + geo-effectiveness) | 15% | `cme_events_2year.csv` + NASA DONKI CMEAnalysis API |
| High-Speed Streams (HSS) | 10% | `high_speed_streams.csv` + NASA DONKI HSS API |

- ระดับ Kp ≥ 4 = G1+ → เริ่มนับเป็น risk
- ถ้าเปิดใช้ Live DONKI API: ค่า real-time จะ **override** ค่าจาก dataset เมื่อสูงกว่า

### 5. Historical Risk — `api_clients/mission_history.py`

- เรียก **Launch Library 2 API** (`https://ll.thespacedevs.com/2.2.0/`)
- ดึงประวัติการปล่อยล่าสุด 40 ครั้งจาก pad นั้น
- คำนวณ **scrub rate** และ **seasonal modifier** (เดือนนั้นๆ มีประวัติ scrub มากกว่าค่าเฉลี่ยหรือไม่)
- ใช้ `lru_cache` เพื่อลด API calls ซ้ำ (15 req/hr free tier)

### 6. LLM Advisory — `llm_advisor.py`

- สร้าง prompt จาก `MissionRiskReport` (ผลประเมินทั้งหมด) แล้วส่งให้ **IBM Granite 13B Instruct v2** ผ่าน watsonx.ai
- หาก credentials ไม่ครบหรือ watsonx SDK ไม่ถูก install → **fallback** เป็น rule-based template อัตโนมัติ
- Output: ข้อความภาษาอังกฤษสรุปสถานการณ์พร้อม recommendation ≤ 200 คำ

---

## แหล่งข้อมูล (Data Sources)

| แหล่งข้อมูล | ประเภท | ใช้สำหรับ |
|-------------|--------|----------|
| **OpenWeatherMap API** | Live REST API | สภาพอากาศปัจจุบันและ 5-day forecast ณ launch site |
| **NASA DONKI API** | Live REST API | Solar flares, Geomagnetic storms, CME, HSS แบบ real-time |
| **Launch Library 2 API** | Live REST API | ประวัติการปล่อยและ scrub rate ของแต่ละ pad |
| **`solar_flares.csv`** | Local dataset | ข้อมูลเหตุการณ์ solar flare 2023–2025 |
| **`geomagnetic_storms.csv`** | Local dataset | ข้อมูลพายุแม่เหล็กโลก |
| **`cme_events_2year.csv`** | Local dataset | ข้อมูล CME events 2 ปี |
| **`daily_solar_data.csv`** | Local dataset | ข้อมูลสุริยะรายวัน |
| **`daily_geomagnetic_data.csv`** | Local dataset | ค่า Kp index รายวัน (3-hr resolution) |
| **`high_speed_streams.csv`** | Local dataset | ข้อมูล HSS events |
| **`space_weather_unified.csv`** | Local dataset | ข้อมูล fallback รวม |
| **`city_weather_dataset.csv`** | Local dataset | ข้อมูลสภาพอากาศเมือง (สำหรับ ML model) |
| **NASA-STD-4010B_2026.pdf** | Reference document | มาตรฐาน NASA ที่ระบบอ้างอิง |

---

## Environment Variables ที่ต้องการ

```env
NASA_API_KEY=          # NASA DONKI API (ฟรี จาก api.nasa.gov)
OWM_API_KEY=           # OpenWeatherMap API (ฟรี tier มีอยู่)
WATSONX_API_KEY=       # IBM watsonx.ai (optional, สำหรับ Granite LLM)
WATSONX_PROJECT_ID=    # IBM watsonx.ai Project ID
WATSONX_URL=https://us-south.ml.cloud.ibm.com
```

> ระบบยังทำงานได้ **โดยไม่มี API keys** โดยจะ fallback เป็น mock/demo data และ template advisory อัตโนมัติ

---

## Launch Sites ที่รองรับ

| Site | ตำแหน่ง |
|------|---------|
| Kennedy Space Center (KSC), FL | 28.57°N, 80.65°W |
| Cape Canaveral SFS, FL | 28.49°N, 80.58°W |
| Vandenberg SFB, CA | 34.74°N, 120.57°W |
| Baikonur Cosmodrome, KZ | 45.92°N, 63.34°E |
| Jiuquan, China | 40.96°N, 100.30°E |

---

## วิธีรันระบบ

```bash
# 1. ติดตั้ง dependencies
pip install -r requirements.txt

# 2. สร้างไฟล์ .env จาก template
copy .env.example .env
# แล้วใส่ API keys ที่ต้องการ

# 3. รัน Streamlit dashboard
streamlit run app.py
```

---

## สรุป Data Flow

```
ผู้ใช้กรอก parameters (sidebar)
         │
         ▼
   cached_evaluate() ─────────────────────────────────────────┐
         │                                                     │
         ├── evaluate_lcc()          ← LCC rules (15 ข้อ)      │
         │       └── WeatherSnapshot (manual input)            │
         │                                                     │
         ├── evaluate_space_weather()                          │
         │       ├── local CSV datasets (primary)              │
         │       └── NASA DONKI API  (real-time override)      │
         │                                                     │
         └── historical_scrub_risk()                           │
                 └── Launch Library 2 API                      │
                                                               │
                    MissionRiskReport ◄────────────────────────┘
                         │
                         ├── Gauge Chart + Bar Chart (Plotly)
                         ├── LCC Rule Table (Streamlit dataframe)
                         ├── Space Weather metrics
                         ├── Historical context
                         └── LLM Advisory (IBM Granite / fallback template)
```

---

*Generated by IBM Bob · Mission Readiness Advisor Architecture Analysis*
