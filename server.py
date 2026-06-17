"""
server.py — Systemic Risk Contagion Engine API
Flask backend wrapping data_loader / network_model / contagion_engine / metrics / visualization.
Serves the static frontend (HTML/CSS/JS) and a JSON API consumed by app.js.
"""

import os
import json
import logging
import threading
import webbrowser
import numpy as np
import networkx as nx
import plotly.utils
from flask import Flask, request, jsonify, send_from_directory

from data_loader import load_data, compute_var, compute_es
from network_model import (
    build_network, get_3d_layout, detect_communities,
    compute_partial_correlation, systemic_risk_index,
)
from contagion_engine import simulate_full, build_scenario, MODELS
from visualization import (
    plot_3d_network, plot_correlation_heatmap, plot_stress_trajectory,
    plot_stress_heatmap, plot_eigenvalue_spectrum, plot_risk_bars,
)
from metrics import compute_metrics, contagion_speed

logging.getLogger("werkzeug").setLevel(logging.WARNING)

app = Flask(__name__, static_folder="static", static_url_path="")

# ── in-memory cache for loaded datasets (keyed by mode/n_assets/n_days) ─────
_data_cache: dict = {}
CACHE_LIMIT = 16


def get_dataset(mode: str, n_assets: int, n_days: int):
    key = (mode, n_assets, n_days)
    if key not in _data_cache:
        if len(_data_cache) >= CACHE_LIMIT:
            _data_cache.pop(next(iter(_data_cache)))
        returns, names, meta = load_data(mode=mode, n_assets=n_assets, n_days=n_days)
        corr = np.corrcoef(returns, rowvar=False)
        var95 = compute_var(returns)
        es95 = compute_es(returns)
        _data_cache[key] = (returns, names, meta, corr, var95, es95)
    return _data_cache[key]


def fig_json(fig) -> dict:
    """Serialize a Plotly figure to a plain JSON-able dict."""
    return json.loads(json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder))


# ─────────────────────────────────────────────────────────────────────────
#  Static frontend
# ─────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ─────────────────────────────────────────────────────────────────────────
#  API — dataset / asset list (used to populate dropdowns before running)
# ─────────────────────────────────────────────────────────────────────────

@app.route("/api/assets", methods=["POST"])
def api_assets():
    body = request.get_json(force=True) or {}
    mode = body.get("data_mode", "sector")
    n_assets = int(body.get("n_assets", 20))
    n_days = int(body.get("n_days", 500))

    try:
        returns, names, meta, corr, var95, es95 = get_dataset(mode, n_assets, n_days)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    sectors = sorted(set(m.get("sector", "Other") for m in meta.values()))
    return jsonify({
        "asset_names": names,
        "meta": meta,
        "sectors": sectors,
        "n_assets_actual": len(names),
    })


# ─────────────────────────────────────────────────────────────────────────
#  API — full simulation run
# ─────────────────────────────────────────────────────────────────────────

@app.route("/api/simulate", methods=["POST"])
def api_simulate():
    body = request.get_json(force=True) or {}

    # ── data params ──
    data_mode = body.get("data_mode", "sector")
    n_assets = int(body.get("n_assets", 20))
    n_days = int(body.get("n_days", 500))

    # ── network params ──
    network_method = body.get("network_method", "threshold")
    layout_method = body.get("layout_method", "spring")
    corr_threshold = float(body.get("corr_threshold", 0.30))
    show_partial_corr = bool(body.get("show_partial_corr", False))

    # ── scenario params ──
    scenario_type = body.get("scenario_type", "single")  # single | sector | top_n | random
    shock_asset = body.get("shock_asset")
    shock_sector = body.get("shock_sector")
    top_n = int(body.get("top_n", 3))
    shock_magnitude = float(body.get("shock_magnitude", 0.50))

    # ── model params ──
    contagion_model = body.get("contagion_model", "linear")
    if contagion_model not in MODELS:
        contagion_model = "linear"
    n_steps = int(body.get("n_steps", 20))
    decay = float(body.get("decay", 0.20))
    threshold_tau = float(body.get("threshold_tau", 0.30))
    recovery_rate = float(body.get("recovery_rate", 0.10))
    amplification = float(body.get("amplification", 1.50))
    animate = bool(body.get("animate", True))

    # ── load data ──
    try:
        returns, asset_names, meta, corr_matrix, var95, es95 = get_dataset(data_mode, n_assets, n_days)
    except Exception as e:
        return jsonify({"error": f"Data load failed: {e}"}), 400

    # ── network ──
    display_corr = compute_partial_correlation(corr_matrix) if show_partial_corr else corr_matrix
    G = build_network(np.array(display_corr), list(asset_names), threshold=corr_threshold, method=network_method)
    pos = get_3d_layout(G, method=layout_method)
    communities = detect_communities(G)

    try:
        centrality = nx.eigenvector_centrality_numpy(G, weight="abs_weight")
    except Exception:
        centrality = {n: 0.0 for n in G.nodes}

    # ── build initial shock ──
    if scenario_type == "single":
        initial_shock = {shock_asset: shock_magnitude} if shock_asset in asset_names else {}
    elif scenario_type == "sector":
        initial_shock = build_scenario(asset_names, "sector", sector_map=meta,
                                       shock_sector=shock_sector, shock_magnitude=shock_magnitude)
    elif scenario_type == "top_n":
        initial_shock = build_scenario(asset_names, "top_n", top_n=top_n,
                                       centrality=centrality, shock_magnitude=shock_magnitude)
    else:
        initial_shock = build_scenario(asset_names, "random", shock_magnitude=shock_magnitude)

    if not initial_shock:
        initial_shock = {asset_names[0]: shock_magnitude}

    # ── simulate ──
    history = simulate_full(
        G, asset_names,
        shock_asset=initial_shock,
        shock_magnitude=shock_magnitude,
        decay=decay,
        n_steps=n_steps,
        model=contagion_model,
        threshold_tau=threshold_tau,
        recovery_rate=recovery_rate,
        amplification=amplification,
    )
    final_stress = history[-1]

    # ── metrics ──
    metrics = compute_metrics(
        G, final_stress, returns=returns, corr_matrix=corr_matrix,
        asset_names=asset_names, history=history,
    )
    sri = systemic_risk_index(G)
    speed = contagion_speed(history)

    # ── figures ──
    fig_network = plot_3d_network(
        G, pos, final_stress, corr_matrix, metrics,
        meta=meta, history=history if animate else None,
        animate=animate, time_step=n_steps, communities=communities,
    )
    fig_corr = plot_correlation_heatmap(display_corr, asset_names)
    fig_traj = plot_stress_trajectory(history, asset_names, meta=meta)
    fig_heat = plot_stress_heatmap(history, asset_names)
    fig_eigen = plot_eigenvalue_spectrum(corr_matrix)
    fig_bars = plot_risk_bars(metrics, asset_names, meta=meta)

    response = {
        "asset_names": asset_names,
        "meta": meta,
        "communities": [sorted(list(c)) for c in communities],
        "initial_shock": initial_shock,
        "metrics": metrics,
        "sri": round(sri, 5),
        "contagion_speed": speed,
        "history": history,
        "correlation_matrix": np.asarray(display_corr).tolist(),
        "figures": {
            "network": fig_json(fig_network),
            "correlation": fig_json(fig_corr),
            "trajectory": fig_json(fig_traj),
            "heatmap": fig_json(fig_heat),
            "eigen": fig_json(fig_eigen),
            "risk_bars": fig_json(fig_bars),
        },
    }
    return jsonify(response)


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


def _open_browser(url):
    try:
        webbrowser.open(url)
    except Exception:
        pass  # no display / headless host — harmless no-op


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    # Render (and most other hosts) set this automatically; skip auto-open there —
    # there's no local browser to open on a remote server.
    if not os.environ.get("RENDER"):
        threading.Timer(1.0, _open_browser, args=[f"http://127.0.0.1:{port}"]).start()
    app.run(host="0.0.0.0", port=port, debug=False)
