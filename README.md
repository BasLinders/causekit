# Causekit

Causal inference toolkit for CRO teams. Causekit makes it possible to analyze the impact of interventions that couldn't be randomized — launches, rollouts, policy changes, and other real-world events where an A/B test wasn't feasible.

Built with Streamlit. Analysis engines are UI-agnostic and importable independently of the interface.

---

## Why

Randomized controlled experiments are the gold standard, but they aren't always possible. When a feature ships to everyone, a market gets treated differently, or historical data is all you have, standard experiment analysis doesn't apply. Causal inference methods fill that gap — but they're technically demanding and easy to misapply.

Causekit lowers that barrier. It handles data ingestion, cleaning, and wrangling in a shared layer, surfaces assumption violations before analysis runs, and outputs results in plain language alongside statistical detail.

---

## Methods

| Module | Use case |
|---|---|
| **Causal Impact** | Estimate the effect of an intervention on a time series metric without a control group |
| **Difference-in-Differences** | Compare a treated and control group across a before/after period |
| **Propensity Score Matching** | Construct comparable groups from observational data to reduce selection bias |
| **Regression Discontinuity** | Estimate effects at a hard assignment threshold (tier cutoffs, score limits) |
| **Synthetic Control** | Build a weighted counterfactual from donor units when a single unit is treated |
| **Mediation Analysis** | Decompose a total effect into direct and indirect paths through a mediator |

---

## Architecture

```
causeway/
├── app.py                              # Streamlit entry point / home page
├── requirements.txt
├── .streamlit/
│   └── config.toml
│
├── core/                               # UI-agnostic engines
│   ├── ingestion/
│   │   ├── loader.py                   # CSV, DataFrame, BigQuery connectors
│   │   ├── cleaner.py                  # Nulls, type coercion, deduplication
│   │   ├── wrangler.py                 # Panel construction, reshaping, time alignment
│   │   └── validator.py                # Schema checks, required columns, date parsing
│   │
│   ├── assumptions/                    # Per-method assumption diagnostics
│   │   ├── parallel_trends.py          # DiD
│   │   ├── balance.py                  # PSM / IPW
│   │   ├── continuity.py               # RDD
│   │   ├── stationarity.py             # CausalImpact
│   │   └── donor_pool.py               # Synthetic control
│   │
│   ├── methods/
│   │   ├── causal_impact.py
│   │   ├── diff_in_diff.py
│   │   ├── propensity_matching.py
│   │   ├── regression_discontinuity.py
│   │   ├── synthetic_control.py
│   │   └── mediation.py
│   │
│   └── results/
│       └── models.py                   # Standardized result dataclasses across methods
│
├── pages/
│   ├── 01_causal_impact.py
│   ├── 02_diff_in_diff.py
│   ├── 03_propensity_matching.py
│   ├── 04_regression_discontinuity.py
│   ├── 05_synthetic_control.py
│   └── 06_mediation.py
│
└── components/                         # Shared Streamlit UI components
    ├── ingestion_ui.py                 # Reusable upload + connection widget
    ├── assumption_panel.py             # Standardized assumption check display
    ├── results_panel.py                # Standardized output rendering
    └── debug.py                        # Debug logger, consistent with your other apps
```

### Core layer

`core/` is fully UI-agnostic. All engines can be imported and called independently of Streamlit.

**Ingestion** is a shared pipeline across all methods:
- `loader.py` — accepts CSV uploads or BigQuery connections
- `cleaner.py` — handles nulls, type coercion, and deduplication
- `wrangler.py` — reshapes data into the structure each method requires (panel, time series, cross-sectional)
- `validator.py` — checks required columns, types, and date formats before any analysis runs

**Assumptions** are surfaced as a distinct step before analysis, not buried inside method output. Each module corresponds to a method and returns structured diagnostics that the UI renders in a standardized panel.

**Results** are returned as dataclasses from `core/results/models.py`, giving all methods a consistent output contract regardless of their internal approach.

### Component layer

`components/` contains shared Streamlit UI elements:
- `ingestion_ui.py` — reusable data upload and connection widget
- `assumption_panel.py` — standardized assumption check display
- `results_panel.py` — standardized output rendering
- `debug.py` — toggleable debug logger

---

## Getting started

```bash
git clone https://github.com/happyhorizon/causekit.git
cd causekit
pip install -r requirements.txt
streamlit run app.py
```

---

## Data input

Causekit accepts:
- CSV file upload via the UI
- BigQuery via the shared ingestion layer (requires appropriate credentials)

Each method's ingestion step documents the required columns and data shape before asking for analysis parameters.

---

## Dependencies

- `streamlit`
- `pandas`
- `numpy`
- `scipy`
- `scikit-learn`
- `statsmodels`
- `tfcausalimpact`
- `pingouin`

---
