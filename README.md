# 3D Systemic Risk Contagion Engine

A quant-style dashboard that simulates how financial shocks propagate through
a network of correlated assets — 3D network visualization, four contagion
models (linear/DebtRank, SIR, threshold cascade, Fitch-style amplification),
three network construction methods (threshold, MST, PMFG), and a full suite
of risk metrics (DebtRank, centrality, spectral analysis, VaR/ES).

The backend is plain Python (Flask). The frontend is hand-built HTML/CSS/JS —
no Streamlit, no frontend framework, no build step. There is no YAML file
anywhere in this project.

## Project structure

```
risk-engine/
├── server.py              Flask app — REST API + static file serving
├── data_loader.py         Synthetic / sector-structured / yfinance data
├── network_model.py       Network construction, layouts, community detection
├── contagion_engine.py    The 4 contagion simulation models
├── metrics.py             Risk metrics (DebtRank, centrality, spectral, VaR/ES)
├── visualization.py       Plotly figure builders
├── requirements.txt       Python dependencies
├── Procfile                Process command for Render / Heroku-style hosts
└── static/
    ├── index.html          Page structure
    ├── style.css           Styling ("terminal/seismograph" theme)
    └── app.js              All frontend logic + API calls
```

## Running locally

```bash
pip install -r requirements.txt
python server.py
```

Then open **http://127.0.0.1:5000** in your browser. The app auto-runs a
demo simulation on load.

To use a different port locally:

```bash
PORT=8000 python server.py
```

## Deploying to Render.com (no YAML required)

Render lets you configure a service entirely through its dashboard, so a
`render.yaml` is optional — this project intentionally doesn't include one.

1. Push this project to a GitHub/GitLab repo.
2. In the Render dashboard: **New → Web Service** → connect the repo.
3. Settings:
   - **Environment**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn server:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
     (this is also exactly what's in the `Procfile`, so most Render setups
     will pick it up automatically without you typing anything)
4. Deploy. Render sets the `PORT` environment variable automatically;
   `server.py` reads it directly.

No `.yaml` / `.yml` file is required at any point in this flow.

## API endpoints

- `GET /` — serves the frontend (`static/index.html`)
- `GET /api/health` — `{"status": "ok"}` liveness check
- `POST /api/assets` — returns the asset universe for a given data mode (used
  to populate the asset/sector dropdowns before running a simulation)
- `POST /api/simulate` — runs the full pipeline (data → network → contagion →
  metrics → figures) and returns a single JSON bundle the frontend renders

## Data modes

- **Synthetic · Sector-structured** (`sector`) — assets grouped into
  Banks / Insurance / Asset Managers / FinTech, driven by market + sector +
  idiosyncratic factors.
- **Synthetic · Random** (`synthetic`) — randomly correlated assets, no
  sector structure.
- **Real · yfinance (live)** (`real`) — pulls live price history via
  `yfinance` and falls back to synthetic data if the network/tickers are
  unavailable.

## Notes

- All five backend logic files (`data_loader.py` through `visualization.py`)
  are unchanged from their standalone Python form — they have no UI
  framework dependency, so `server.py` calls them directly.
- The frontend never touches `localStorage`/`sessionStorage`; all state
  lives in memory in `app.js` for the current page session.
