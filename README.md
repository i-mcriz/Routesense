# RouteSense AI

**AI-Powered Disaster Evacuation Routing System for Kerala**

> ⚠️ **Prototype** — This system uses ML-based prototype road-risk classification and a simulated flood-risk layer. It is intended for academic demonstration and is NOT a certified emergency navigation system.

---

## Quick Start

### Prerequisites

- Python 3.10+
- pip packages: `flask`, `flask-cors`, `geopandas`, `networkx`, `shapely`, `scikit-learn`, `pandas`, `numpy`, `matplotlib`, `seaborn`, `joblib`

### Installation

```bash
pip install flask flask-cors geopandas networkx shapely scikit-learn pandas numpy matplotlib seaborn joblib
```

### Run the Web Application

```bash
python backend/app.py
```

Then open **http://localhost:5000** in your browser.

The server will:
1. Load the road-risk GeoJSON (~30s for 496k features)
2. Subset to the Thrissur study area (10,153 segments)
3. Build the routing graph (57,611 nodes)
4. Start serving the web interface

---

## Default Demonstration

1. Open http://localhost:5000
2. Click **"Use Demo Points"** in the Routing panel (bottom-right)
3. Click **"FIND SAFER ROUTE"**
4. Observe:
   - Blue dashed line = Normal shortest route (15.0 km)
   - Purple solid line with animated particles = RouteSense safer route (16.2 km)
   - Route Impact panel shows 80.4% risk reduction for +7.6% distance

---

## Routing Profiles

| Profile | Description | Risk Behavior |
|---|---|---|
| **General** | Balanced distance vs. safety | Moderate risk avoidance |
| **Elderly / Mobility-Limited** | Avoids steep slopes, steps, footways | Strong risk avoidance + accessibility |
| **High-Risk Emergency** | Maximum safety priority | Extreme risk avoidance |

---

## Flood Simulation

1. **Shift+click** the map to place a flood center
2. Adjust sliders:
   - **Flood Intensity** (0–1): Severity of the simulated flood
   - **Water Level** (0–5m): Simulated water depth
   - **Flood Radius** (500–5000m): Affected area size
3. Click **"Simulate Flood"**
4. RouteSense automatically recalculates routes avoiding the flooded area

### How it works

Roads within the flood radius have their risk dynamically increased based on:
- Distance from flood center (closer = higher risk)
- Road elevation (lower = more vulnerable)
- Flood intensity and water level settings

---

## Project Structure

```
Routesense/
├── backend/
│   └── app.py                      # Flask server + routing engine
├── frontend/
│   ├── index.html                  # Web interface
│   ├── style.css                   # Design system
│   └── app.js                      # Map + interaction logic
├── scripts/
│   ├── prepare_dataset.py          # Feature engineering
│   ├── train_models.py             # ML pipeline
│   ├── risk_aware_routing.py       # CLI routing tool
│   └── create_qgis_output.py       # QGIS export
├── models/
│   ├── routesense_best_model.joblib
│   ├── model_comparison.csv
│   ├── feature_importance.csv
│   ├── classification_report.txt
│   └── confusion_matrix.png
├── outputs/
│   ├── routesense_road_risk.geojson # Full risk predictions
│   └── routing/                     # CLI routing outputs
├── data/
│   ├── raw/                         # Original data
│   └── processed/                   # ML datasets
└── docs/
    ├── routing_methodology.md
    └── webapp_architecture.md
```

---

## Limitations

- Risk labels are synthetic/heuristic, not derived from verified flood history
- Flood simulation uses spatial proximity rules, not hydrological modeling
- Routing limited to Thrissur demonstration area
- Not validated for actual emergency use
