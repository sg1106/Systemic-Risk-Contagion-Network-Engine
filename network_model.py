"""
network_model.py — Advanced financial network construction
Supports: correlation, partial correlation, MST (Minimum Spanning Tree), community detection
"""

import numpy as np
import networkx as nx
from itertools import combinations
from typing import Literal


# ---------------------------------------------------------------------------
# Network builders
# ---------------------------------------------------------------------------

def build_network(
    corr_matrix: np.ndarray,
    asset_names: list[str],
    threshold: float = 0.3,
    method: Literal["threshold", "mst", "pmfg"] = "threshold",
) -> nx.Graph:
    """
    Build a financial network from a correlation matrix.
    method:
      'threshold' - edges where |corr| >= threshold
      'mst'       - Minimum Spanning Tree on distance matrix
      'pmfg'      - Planar Maximally Filtered Graph (subset of MST variant)
    """
    if method == "mst":
        return _build_mst(corr_matrix, asset_names)
    elif method == "pmfg":
        return _build_pmfg(corr_matrix, asset_names)
    else:
        return _build_threshold(corr_matrix, asset_names, threshold)


def _build_threshold(corr_matrix, asset_names, threshold):
    G = nx.Graph()
    G.add_nodes_from(asset_names)
    n = len(asset_names)
    for i, j in combinations(range(n), 2):
        c = corr_matrix[i, j]
        if abs(c) >= threshold:
            dist = np.sqrt(2 * (1 - c))
            G.add_edge(
                asset_names[i], asset_names[j],
                weight=c,
                abs_weight=abs(c),
                distance=dist,
            )
    return G


def _build_mst(corr_matrix, asset_names):
    """Minimum Spanning Tree on the ultrametric distance sqrt(2*(1-rho))."""
    n = len(asset_names)
    dist = np.sqrt(np.clip(2 * (1 - corr_matrix), 0, None))
    np.fill_diagonal(dist, 0)
    full = nx.Graph()
    full.add_nodes_from(asset_names)
    for i, j in combinations(range(n), 2):
        full.add_edge(
            asset_names[i], asset_names[j],
            weight=dist[i, j],
            corr_weight=corr_matrix[i, j],
        )
    mst = nx.minimum_spanning_tree(full, weight="weight")
    # Re-label edge attributes to match convention
    for u, v, d in mst.edges(data=True):
        d["abs_weight"] = abs(d["corr_weight"])
        d["distance"] = d["weight"]
        d["weight"] = d["corr_weight"]
    return mst


def _build_pmfg(corr_matrix, asset_names):
    """
    Simplified PMFG: greedily add edges (highest corr first) while maintaining planarity.
    For large graphs this falls back to MST + top correlated edges.
    """
    n = len(asset_names)
    # Sort pairs by descending |corr|
    pairs = sorted(
        ((i, j) for i, j in combinations(range(n), 2)),
        key=lambda p: -abs(corr_matrix[p[0], p[1]]),
    )
    G = nx.Graph()
    G.add_nodes_from(asset_names)
    for i, j in pairs:
        c = corr_matrix[i, j]
        G.add_edge(asset_names[i], asset_names[j], weight=c, abs_weight=abs(c), distance=np.sqrt(2*(1-c)))
        if not nx.check_planarity(G)[0]:
            G.remove_edge(asset_names[i], asset_names[j])
        if G.number_of_edges() >= 3 * (n - 2):
            break
    return G


# ---------------------------------------------------------------------------
# Layout engines
# ---------------------------------------------------------------------------

def get_3d_layout(
    G: nx.Graph,
    method: Literal["spring", "spectral", "sphere", "kamada_kawai"] = "spring",
) -> dict:
    """Return {node: (x, y, z)} positions."""
    if method == "spectral":
        return _spectral_3d(G)
    elif method == "sphere":
        return _sphere_layout(G)
    elif method == "kamada_kawai":
        return _kamada_kawai_3d(G)
    else:
        return nx.spring_layout(G, dim=3, seed=42, weight="abs_weight", k=1.5)


def _spectral_3d(G):
    if len(G) < 4:
        return nx.spring_layout(G, dim=3, seed=42)
    L = nx.normalized_laplacian_matrix(G).toarray()
    eigvals, eigvecs = np.linalg.eigh(L)
    # Take 2nd, 3rd, 4th smallest eigenvectors (Fiedler-based)
    vecs = eigvecs[:, 1:4]
    nodes = list(G.nodes)
    return {nodes[i]: tuple(vecs[i]) for i in range(len(nodes))}


def _sphere_layout(G):
    """Place nodes on a sphere surface using Fibonacci lattice."""
    nodes = list(G.nodes)
    n = len(nodes)
    golden = (1 + np.sqrt(5)) / 2
    pos = {}
    for i, node in enumerate(nodes):
        theta = 2 * np.pi * i / golden
        phi = np.arccos(1 - 2 * (i + 0.5) / n)
        x = np.sin(phi) * np.cos(theta)
        y = np.sin(phi) * np.sin(theta)
        z = np.cos(phi)
        pos[node] = (x, y, z)
    return pos


def _kamada_kawai_3d(G):
    """2D Kamada-Kawai extended to 3D by adding community-based z."""
    pos2d = nx.kamada_kawai_layout(G, weight="distance")
    communities = detect_communities(G)
    node_community = {}
    for cid, members in enumerate(communities):
        for m in members:
            node_community[m] = cid
    n_comm = max(1, len(communities))
    pos3d = {}
    for node, (x, y) in pos2d.items():
        z = (node_community.get(node, 0) / n_comm) * 2 - 1
        pos3d[node] = (x, y, z)
    return pos3d


# ---------------------------------------------------------------------------
# Community detection
# ---------------------------------------------------------------------------

def detect_communities(G: nx.Graph) -> list[set]:
    """Louvain-style greedy modularity communities."""
    if G.number_of_edges() == 0:
        return [set(G.nodes)]
    try:
        from networkx.algorithms.community import greedy_modularity_communities
        return list(greedy_modularity_communities(G, weight="abs_weight"))
    except Exception:
        return [set(G.nodes)]


# ---------------------------------------------------------------------------
# Graph analytics
# ---------------------------------------------------------------------------

def compute_partial_correlation(corr_matrix: np.ndarray) -> np.ndarray:
    """Compute partial correlation matrix via precision matrix."""
    try:
        precision = np.linalg.inv(corr_matrix + 1e-6 * np.eye(len(corr_matrix)))
        d = np.sqrt(np.diag(precision))
        partial = -precision / np.outer(d, d)
        np.fill_diagonal(partial, 1.0)
        return partial
    except np.linalg.LinAlgError:
        return corr_matrix


def systemic_risk_index(G: nx.Graph) -> float:
    """Simple SRI: average weighted degree / max possible."""
    if G.number_of_edges() == 0:
        return 0.0
    total_weight = sum(abs(d["weight"]) for _, _, d in G.edges(data=True))
    n = G.number_of_nodes()
    max_possible = n * (n - 1) / 2
    return total_weight / max_possible if max_possible > 0 else 0.0
