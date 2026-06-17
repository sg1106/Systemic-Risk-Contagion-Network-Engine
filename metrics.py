"""
metrics.py — Comprehensive systemic risk metrics
Covers: Network topology, DebtRank, VaR/ES, Spectral risk, Contagion impact
"""

import math
import warnings
import numpy as np
import networkx as nx
from typing import Optional


# ---------------------------------------------------------------------------
# Main compute function
# ---------------------------------------------------------------------------

def compute_metrics(
    G: nx.Graph,
    stress_levels: dict[str, float],
    returns: Optional[np.ndarray] = None,
    corr_matrix: Optional[np.ndarray] = None,
    asset_names: Optional[list[str]] = None,
    history: Optional[list[dict]] = None,
) -> dict:
    metrics = {}

    # --- Network topology ---
    metrics["network"] = _network_metrics(G)

    # --- Stress / contagion ---
    metrics["contagion"] = _contagion_metrics(stress_levels, history)

    # --- Node-level risk ---
    metrics["node_risk"] = _node_risk(G, stress_levels)

    # --- Spectral (if corr_matrix provided) ---
    if corr_matrix is not None:
        metrics["spectral"] = _spectral_metrics(corr_matrix)

    # --- Return-based risk (if returns provided) ---
    if returns is not None and asset_names is not None:
        metrics["return_risk"] = _return_metrics(returns, asset_names)

    return metrics


# ---------------------------------------------------------------------------
# Network topology
# ---------------------------------------------------------------------------

def _network_metrics(G: nx.Graph) -> dict:
    n = G.number_of_nodes()
    e = G.number_of_edges()
    if n == 0:
        return {}

    density = nx.density(G)
    avg_degree = (2 * e) / n if n > 0 else 0

    # Clustering
    try:
        avg_clustering = nx.average_clustering(G, weight="abs_weight")
    except Exception:
        avg_clustering = 0.0

    # Assortativity — degenerate when the graph has uniform degree (e.g. a
    # cycle, a regular graph, or an MST on a small/symmetric correlation
    # set): networkx hits a 0/0 divide internally and returns NaN instead of
    # raising, so a plain try/except won't catch it. We guard explicitly.
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            assortativity = nx.degree_assortativity_coefficient(G)
        if assortativity is None or not math.isfinite(assortativity):
            assortativity = 0.0
    except Exception:
        assortativity = 0.0

    # Connected components
    n_components = nx.number_connected_components(G)
    largest_cc = len(max(nx.connected_components(G), key=len)) / n if n > 0 else 0

    # Average path length (largest component)
    try:
        lcc = G.subgraph(max(nx.connected_components(G), key=len))
        avg_path = nx.average_shortest_path_length(lcc) if len(lcc) > 1 else 0
    except Exception:
        avg_path = 0.0

    # Total edge weight (connectedness)
    total_weight = sum(abs(d.get("weight", 0)) for _, _, d in G.edges(data=True))

    return {
        "nodes": n,
        "edges": e,
        "density": round(density, 4),
        "avg_degree": round(avg_degree, 3),
        "avg_clustering": round(avg_clustering, 4),
        "assortativity": round(assortativity, 4),
        "n_components": n_components,
        "largest_cc_fraction": round(largest_cc, 3),
        "avg_path_length": round(avg_path, 4),
        "total_edge_weight": round(total_weight, 3),
    }


# ---------------------------------------------------------------------------
# Contagion metrics
# ---------------------------------------------------------------------------

def _contagion_metrics(stress: dict[str, float], history: Optional[list] = None) -> dict:
    vals = np.array(list(stress.values()))
    if len(vals) == 0:
        return {}

    total_stress = float(vals.sum())
    max_stress = float(vals.max())
    mean_stress = float(vals.mean())
    n_distressed = int((vals > 0.5).sum())
    n_critical = int((vals > 0.8).sum())

    # Ranking
    ranking = sorted(stress.items(), key=lambda x: x[1], reverse=True)

    # Time to peak (from history)
    time_to_peak = None
    peak_stress_trajectory = None
    if history:
        totals = [sum(h.values()) for h in history]
        time_to_peak = int(np.argmax(totals))
        peak_stress_trajectory = [round(t, 4) for t in totals]

    return {
        "total_stress": round(total_stress, 4),
        "max_stress": round(max_stress, 4),
        "mean_stress": round(mean_stress, 4),
        "n_distressed_nodes": n_distressed,
        "n_critical_nodes": n_critical,
        "systemic_importance_ranking": [(a, round(s, 4)) for a, s in ranking[:10]],
        "time_to_peak": time_to_peak,
        "stress_trajectory": peak_stress_trajectory,
    }


# ---------------------------------------------------------------------------
# Node-level risk
# ---------------------------------------------------------------------------

def _node_risk(G: nx.Graph, stress: dict[str, float]) -> dict:
    if G.number_of_nodes() == 0:
        return {}

    # Eigenvector centrality
    try:
        eigen_c = nx.eigenvector_centrality_numpy(G, weight="abs_weight")
    except Exception:
        eigen_c = {n: 0.0 for n in G.nodes}

    # Betweenness centrality
    try:
        between_c = nx.betweenness_centrality(G, weight="distance", normalized=True)
    except Exception:
        between_c = {n: 0.0 for n in G.nodes}

    # Degree (weighted)
    deg = dict(G.degree(weight="abs_weight"))

    # Combine: DebtRank-like importance = stress * centrality
    debt_rank = {
        n: round(stress.get(n, 0) * eigen_c.get(n, 0), 6)
        for n in G.nodes
    }

    return {
        "eigenvector_centrality": {k: round(v, 5) for k, v in eigen_c.items()},
        "betweenness_centrality": {k: round(v, 5) for k, v in between_c.items()},
        "weighted_degree": {k: round(v, 4) for k, v in deg.items()},
        "debt_rank": debt_rank,
        "top_systemic_nodes": sorted(debt_rank, key=debt_rank.get, reverse=True)[:5],
    }


# ---------------------------------------------------------------------------
# Spectral metrics
# ---------------------------------------------------------------------------

def _spectral_metrics(corr_matrix: np.ndarray) -> dict:
    eigvals = np.linalg.eigvalsh(corr_matrix)
    eigvals = np.sort(eigvals)[::-1]

    n = len(eigvals)
    # Marchenko-Pastur upper bound (rough, assuming T>>N)
    lambda_max_mp = (1 + np.sqrt(1 / max(1, n))) ** 2 * 2
    n_significant = int((eigvals > lambda_max_mp).sum())

    # Spectral risk: ratio of top eigenvalue to trace
    spectral_risk_ratio = float(eigvals[0] / eigvals.sum()) if eigvals.sum() > 0 else 0

    # Entropy of eigenvalue distribution
    ev_norm = eigvals / eigvals.sum()
    entropy = float(-np.sum(ev_norm * np.log(ev_norm + 1e-12)))

    return {
        "top_eigenvalue": round(float(eigvals[0]), 4),
        "spectral_risk_ratio": round(spectral_risk_ratio, 4),
        "n_significant_factors": n_significant,
        "eigenvalue_entropy": round(entropy, 4),
        "eigenvalues_top10": [round(float(v), 4) for v in eigvals[:10]],
    }


# ---------------------------------------------------------------------------
# Return-based risk
# ---------------------------------------------------------------------------

def _return_metrics(returns: np.ndarray, asset_names: list[str]) -> dict:
    var_95 = -np.quantile(returns, 0.05, axis=0)
    var_99 = -np.quantile(returns, 0.01, axis=0)

    es_95 = np.array([
        -returns[returns[:, i] <= np.quantile(returns[:, i], 0.05), i].mean()
        for i in range(returns.shape[1])
    ])

    # Portfolio-level (equal weight)
    port_returns = returns.mean(axis=1)
    port_var_95 = float(-np.quantile(port_returns, 0.05))
    port_es_95 = float(-port_returns[port_returns <= np.quantile(port_returns, 0.05)].mean())

    # Volatility
    vol = returns.std(axis=0) * np.sqrt(252)

    return {
        "portfolio_var_95": round(port_var_95, 5),
        "portfolio_es_95": round(port_es_95, 5),
        "asset_var_95": {a: round(float(v), 5) for a, v in zip(asset_names, var_95)},
        "asset_es_95": {a: round(float(v), 5) for a, v in zip(asset_names, es_95)},
        "annualized_volatility": {a: round(float(v), 4) for a, v in zip(asset_names, vol)},
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def stress_heatmap_matrix(history: list[dict], asset_names: list[str]) -> np.ndarray:
    """Return (n_steps × n_assets) matrix of stress values for heatmap."""
    return np.array([[h.get(a, 0.0) for a in asset_names] for h in history])


def contagion_speed(history: list[dict]) -> float:
    """How fast does total stress rise? Slope of first half."""
    totals = [sum(h.values()) for h in history]
    half = max(1, len(totals) // 2)
    if half < 2:
        return 0.0
    slope = np.polyfit(range(half), totals[:half], 1)[0]
    return round(float(slope), 5)