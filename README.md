# 🚀 Mission Readiness Advisor

> **IBM August Challenge — Space Exploration Theme**  
> AI-powered launch risk assessment that combines surface weather, space weather, and historical mission data to answer: *"Should we launch today?"*

---

## 🎯 Problem Statement

Rocket launches are extremely sensitive to both surface weather conditions and space weather events. A single violated Launch Commit Criteria (LCC) rule — wind too strong, visibility too low, lightning within range — can scrub a mission costing millions. Similarly, solar flares and geomagnetic storms can damage satellite electronics and disrupt communications during launch. Mission directors need a rapid, data-driven tool that aggregates all these risk factors into a single, explainable recommendation.

## 💡 Solution Description

**Mission Readiness Advisor** is a Streamlit web application that evaluates three risk dimensions for any launch date and site:

| Dimension | Data Source | Rules |
|-----------|------------|-------|
| 🌦️ **Surface Weather** | OpenWeatherMap API | KSC Launch Commit Criteria (45th Space Wing) |
| ☀️ **Space Weather** | NASA DONKI API + historical datasets | Kp/G-level, solar flares, CME events, HSS |
| 📚 **Mission History** | Launch Library 2 API | Historical scrub rate + seasonal patterns |

The three scores are combined into a single **Delay Risk %** with an **GO / CAUTION / NO-GO** recommendation, explained in plain language by **IBM Granite** via watsonx.ai.

### Demo Scenario
> *"Planning a launch from Kennedy Space Center on August 15 with 25-knot gusts and a G2 geomagnetic storm in progress → **NO-GO, 78% delay risk** — wind exceeds 30-kt LCC limit; elevated Kp may affect avionics communication links"*

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Streamlit Dashboard (app.py)               │
└──────────────┬───────────────┬──────────────────┬────────────┘
               │               │                  │
      ┌────────▼──────┐ ┌──────▼──────┐  ┌────────▼─────────┐
      │ Weather Layer  │ │Space Weather│  │ Historical Layer  │
      │ weather_client │ │space_weather│  │ mission_history   │
      │ + lcc_rules    │ │ _risk       │  │ (Launch Lib 2)    │
      └────────┬───────┘ └──────┬──────┘  └────────┬─────────┘
               │               │                  │
      ┌────────▼───────────────▼──────────────────▼─────────┐
      │           risk_engine.py — Weighted Aggregation       │
      └────────────────────────────┬────────────────────────┘
                                   │
                        ┌──────────▼──────────┐
                        │ llm_advisor.py       │
                        │ IBM Granite (watsonx)│
                        └─────────────────────┘
```

---

## 🤖 AI Approach

1. **Rule-Based Engine** (`lcc_rules.py`): Implements 9 KSC Launch Commit Criteria as deterministic rules — no ML needed, 100% explainable.

2. **ML-Enhanced Space Weather** (`space_weather_risk.py`): Loads pre-trained feature data from `ml_ready_dataset.csv` (trained with XGBoost in `train_fixed.ipynb`). Uses physics-based risk mapping for Kp, flare class, CME speed, and high-speed streams.

3. **IBM Granite LLM** (`llm_advisor.py`): Receives the risk breakdown as a structured JSON prompt → generates a human-readable advisory briefing via watsonx.ai. Falls back to a rule-based text template when credentials are unavailable.

4. **Weighted Risk Aggregation**: Weather (45%) + Space Weather (35%) + Historical (20%) → single delay probability score.

---

## 📁 Project Structure

```
mission_readiness_advisor/
├── app.py                          # Streamlit dashboard (entry point)
├── config.py                       # API keys, site configs, thresholds
├── llm_advisor.py                  # IBM Granite / watsonx.ai integration
├── requirements.txt                # Python dependencies
├── .env.example                    # Environment variables template
├── core/
│   ├── lcc_rules.py                # Launch Commit Criteria rule engine
│   ├── space_weather_risk.py       # Space weather risk scorer
│   └── risk_engine.py              # Aggregation engine → MissionRiskReport
└── api_clients/
    ├── weather_client.py           # OpenWeatherMap API client
    ├── donki_client.py             # NASA DONKI API client
    └── mission_history.py          # Launch Library 2 API client

Datasets/                           # Historical space weather data
├── solar_flares.csv                # NASA DONKI solar flares (2023–2025)
├── geomagnetic_storms.csv          # Geomagnetic storm events
├── cme_events_2year.csv            # CME events with speed & direction
├── daily_solar_data.csv            # Daily solar indices (1997–2025)
├── daily_geomagnetic_data.csv      # 3-hr Kp data (1997–2025)
├── high_speed_streams.csv          # HSS events
└── city_weather_dataset.csv        # Sample weather data

train_fixed.ipynb                   # XGBoost training notebook (space weather ML)
etl_pipeline.py                     # Data ETL pipeline
ml_ready_dataset.csv                # ML-ready feature dataset
```

---

## 🚀 How to Run

### 1. Install Dependencies
```bash
cd IBM_august_challenge/mission_readiness_advisor
pip install -r requirements.txt
```

### 2. Set Up API Keys
```bash
cp .env.example .env
# Edit .env and add your keys:
# NASA_API_KEY=your_key_here         (from api.nasa.gov — free)
# OWM_API_KEY=your_key_here          (from openweathermap.org — free)
# WATSONX_API_KEY=...                (from cloud.ibm.com — for LLM)
# WATSONX_PROJECT_ID=...
```

### 3. Launch the App
```bash
streamlit run app.py
```
Open http://localhost:8501 in your browser.

### 4. Without API Keys (Demo Mode)
The app works without any API keys — it uses:
- Manual weather sliders (no OWM needed)
- Historical dataset files for space weather (no DONKI needed)
- Rule-based text advisory (no watsonx needed)

---

## 🔑 How IBM Bob Was Used

IBM Bob (AI-assisted development tool) was the **primary development tool** throughout this project:

- **Architecture design**: Bob helped design the 3-layer risk architecture and suggested the weighted aggregation approach
- **Code generation**: All modules (`lcc_rules.py`, `risk_engine.py`, `app.py`, etc.) were created with Bob
- **Integration guidance**: Bob provided watsonx.ai SDK integration patterns and prompt engineering for Granite
- **Debugging**: Bob identified and fixed data type issues in the ETL pipeline (`etl_pipeline.py`)
- **Testing**: Bob suggested edge cases for LCC rule validation

---

## 🛠️ Technologies Used

| Technology | Purpose |
|------------|---------|
| **IBM Bob** | Primary development tool |
| **IBM Granite** via watsonx.ai | LLM advisory generation |
| **Python / Streamlit** | Dashboard framework |
| **Plotly** | Interactive charts |
| **XGBoost** | Space weather ML model |
| **NASA DONKI API** | Real-time space weather |
| **OpenWeatherMap API** | Surface weather data |
| **Launch Library 2 API** | Historical launch data |
| **pandas / numpy** | Data processing |

---

## 📊 Selected Challenge Theme

**AI-Powered Mission Planning Assistants** — The solution directly addresses the challenge theme by providing an AI assistant that helps mission directors make data-driven GO/NO-GO decisions, transforming complex multi-source data into clear, actionable insights.

---

## 🌍 Real-World Impact

- Reduces unnecessary scrubs caused by missed risk signals
- Saves launch preparation costs (estimated $500K–$2M per scrub at KSC)
- Makes space weather risk accessible to non-specialist mission planners
- Explainable AI (LLM + rule breakdown) builds trust in AI recommendations

---

*IBM August Challenge 2025 · Space Exploration Theme*
