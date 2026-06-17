"""
contagion_engine.py — Multi-model financial contagion engine

Models:
  'linear'    - Linear DebtRank-inspired propagation
  'sir'       - SIR (Susceptible-Infected-Recovered) on the network
  'threshold' - Threshold cascade (node distresses when neighbour stress > tau)
  'fitch'     - Non-linear loss-given-default with amplification
"""

import numpy as np
import networkx as nx
from typing import Literal

MODELS = ["linear", "sir", "threshold", "fitch"]


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------

def propagate_shock(
    G: nx.Graph,
    asset_names: list[str],
    shock_asset: str,
    shock_magnitude: float,
    decay: float,
    time_step: int,
    model: str = "linear",
    threshold_tau: float = 0.3,
    recovery_rate: float = 0.1,
    amplification: float = 1.5,
) -> dict[str, float]:
    """Return final stress levels at t=time_step."""
    history = simulate_full(
        G, asset_names, shock_asset, shock_magnitude, decay, time_step,
        model=model, threshold_tau=threshold_tau,
        recovery_rate=recovery_rate, amplification=amplification,
    )
    return history[-1]


def simulate_full(
    G: nx.Graph,
    asset_names: list[str],
    shock_asset: str | list[str],
    shock_magnitude: float | dict,
    decay: float,
    n_steps: int,
    model: str = "linear",
    threshold_tau: float = 0.3,
    recovery_rate: float = 0.1,
    amplification: float = 1.5,
) -> list[dict[str, float]]:
    """
    Simulate contagion for n_steps and return full history.
    history[t] = {node: stress_value} for t in 0..n_steps
    """
    # Initialise from BOTH asset_names AND G.nodes so every node has an entry
    all_nodes = set(asset_names) | set(G.nodes)
    stress = {name: 0.0 for name in all_nodes}

    # Accept single or multiple shocked assets
    if isinstance(shock_asset, str):
        stressed = {shock_asset: shock_magnitude}
    elif isinstance(shock_asset, list):
        stressed = {a: shock_magnitude for a in shock_asset}
    else:
        stressed = shock_asset  # dict

    for node, val in stressed.items():
        if node in stress:
            stress[node] = float(np.clip(val, 0.0, 1.0))

    history = [stress.copy()]

    dispatch = {
        "linear": _step_linear,
        "sir": _step_sir,
        "threshold": _step_threshold,
        "fitch": _step_fitch,
    }
    step_fn = dispatch.get(model, _step_linear)

    extra = dict(
        threshold_tau=threshold_tau,
        recovery_rate=recovery_rate,
        amplification=amplification,
    )

    recovered = {name: False for name in asset_names}  # for SIR

    for t in range(n_steps):
        stress, recovered = step_fn(G, stress, decay, recovered, **extra)
        # Clamp to [0, 1]
        stress = {k: float(np.clip(v, 0.0, 1.0)) for k, v in stress.items()}
        history.append(stress.copy())

    return history


# ---------------------------------------------------------------------------
# Step functions
# ---------------------------------------------------------------------------

def _step_linear(G, stress, decay, recovered, **kw):
    new_stress = {n: stress.get(n, 0.0) * (1 - decay * 0.3) for n in G.nodes}
    for i, j, data in G.edges(data=True):
        w = abs(data.get("weight", 0.0))
        spread_ij = stress.get(i, 0.0) * w * (1 - decay)
        spread_ji = stress.get(j, 0.0) * w * (1 - decay)
        new_stress[j] = new_stress.get(j, 0.0) + spread_ij
        new_stress[i] = new_stress.get(i, 0.0) + spread_ji
    return new_stress, recovered


def _step_sir(G, stress, decay, recovered, recovery_rate=0.1, **kw):
    INFECT_THRESHOLD = 0.15
    new_stress = {n: stress.get(n, 0.0) for n in G.nodes}
    for node in G.nodes:
        if recovered.get(node, False):
            new_stress[node] *= 0.95
            continue
        s = stress.get(node, 0.0)
        if s >= INFECT_THRESHOLD:
            for nbr in G.neighbors(node):
                if not recovered.get(nbr, False):
                    w = abs(G[node][nbr].get("weight", 0.0))
                    infection = s * w * 0.4 * (1 - decay)
                    new_stress[nbr] = min(1.0, new_stress.get(nbr, 0.0) + infection)
            if np.random.random() < recovery_rate:
                recovered[node] = True
        else:
            new_stress[node] *= (1 - decay * 0.2)
    return new_stress, recovered


def _step_threshold(G, stress, decay, recovered, threshold_tau=0.3, **kw):
    new_stress = {n: stress.get(n, 0.0) * (1 - decay * 0.1) for n in G.nodes}
    for node in G.nodes:
        if stress.get(node, 0.0) >= 0.9:
            continue
        neighbours = list(G.neighbors(node))
        if not neighbours:
            continue
        weighted = sum(
            stress.get(nbr, 0.0) * abs(G[node][nbr].get("weight", 0.0))
            for nbr in neighbours
        )
        avg = weighted / len(neighbours)
        if avg >= threshold_tau:
            new_stress[node] = min(1.0, new_stress.get(node, 0.0) + avg * 0.8)
    return new_stress, recovered


def _step_fitch(G, stress, decay, recovered, amplification=1.5, **kw):
    new_stress = {n: stress.get(n, 0.0) * (1 - decay * 0.25) for n in G.nodes}
    for i, j, data in G.edges(data=True):
        w = abs(data.get("weight", 0.0))
        contrib_ij = (stress.get(i, 0.0) ** amplification) * w * (1 - decay) * 0.5
        contrib_ji = (stress.get(j, 0.0) ** amplification) * w * (1 - decay) * 0.5
        new_stress[j] = new_stress.get(j, 0.0) + contrib_ij
        new_stress[i] = new_stress.get(i, 0.0) + contrib_ji
    return new_stress, recovered


# ---------------------------------------------------------------------------
# Multi-shock scenario builder
# ---------------------------------------------------------------------------

def build_scenario(
    asset_names: list[str],
    scenario: Literal["single", "sector", "random", "top_n"],
    shock_asset: str = None,
    sector_map: dict = None,
    shock_sector: str = None,
    shock_magnitude: float = 0.5,
    top_n: int = 3,
    centrality: dict = None,
) -> dict[str, float]:
    """Return initial shock dict {asset: magnitude}."""
    if scenario == "single":
        return {shock_asset: shock_magnitude} if shock_asset else {}

    elif scenario == "sector" and sector_map and shock_sector:
        return {
            name: shock_magnitude
            for name in asset_names
            if sector_map.get(name, {}).get("sector") == shock_sector
        }

    elif scenario == "top_n" and centrality:
        top = sorted(centrality, key=centrality.get, reverse=True)[:top_n]
        return {a: shock_magnitude for a in top}

    elif scenario == "random":
        rng = np.random.default_rng()
        chosen = rng.choice(asset_names, size=min(3, len(asset_names)), replace=False)
        return {a: shock_magnitude * rng.uniform(0.5, 1.0) for a in chosen}

    return {}
