"""
visualization.py — High-contrast, readable Plotly visualizations
"""

import numpy as np
import plotly.graph_objs as go
from plotly.subplots import make_subplots
import networkx as nx
from typing import Optional

# ── Theme constants ──────────────────────────────────────────────────────────
BG        = "#111318"
BG_PANEL  = "#1A1D26"
TEXT      = "#F0F2F8"
TEXT_DIM  = "#AAAAAA"
ACCENT    = "#F97316"
GRID      = "rgba(255,255,255,0.06)"

# Stress colour ramp: green → yellow → orange → red (very readable on dark bg)
STRESS_SCALE = [
    [0.00, "#1a9850"],
    [0.25, "#91cf60"],
    [0.50, "#fee08b"],
    [0.75, "#fc8d59"],
    [1.00, "#d73027"],
]

CORR_SCALE = "RdBu_r"


# ════════════════════════════════════════════════════════════════════════════
#  3-D Network
# ════════════════════════════════════════════════════════════════════════════

def plot_3d_network(
    G: nx.Graph,
    pos: dict,
    stress_levels: dict,
    corr_matrix: np.ndarray,
    metrics: dict,
    meta: Optional[dict] = None,
    history: Optional[list] = None,
    animate: bool = True,
    time_step: int = 10,
    communities: Optional[list] = None,
) -> go.Figure:
    if animate and history and len(history) > 1:
        return _animated_network(G, pos, history, meta, communities)
    return _static_network(G, pos, stress_levels, meta, communities)


def _centrality(G):
    try:
        return nx.eigenvector_centrality_numpy(G, weight="abs_weight")
    except Exception:
        return {n: 0.3 for n in G.nodes}


def _make_edge_traces(G, pos, stress):
    """Edges bucketed by correlation strength so colour is informative."""
    buckets = {
        "strong+": ("#F97316", 3.0),   # strong positive corr
        "mid+":    ("#94A3B8", 1.5),   # moderate positive
        "neg":     ("#60A5FA", 1.5),   # negative corr
    }
    coords = {k: ([], [], []) for k in buckets}

    for u, v, data in G.edges(data=True):
        w = data.get("weight", 0.0)
        key = "strong+" if w >= 0.6 else ("neg" if w < 0 else "mid+")
        x0, y0, z0 = pos[u]
        x1, y1, z1 = pos[v]
        xs, ys, zs = coords[key]
        xs += [x0, x1, None]
        ys += [y0, y1, None]
        zs += [z0, z1, None]

    labels_map = {
        "strong+": "Strong corr (ρ≥0.6)",
        "mid+":    "Mid corr",
        "neg":     "Negative corr",
    }
    traces = []
    for key, (col, w) in buckets.items():
        xs, ys, zs = coords[key]
        if not xs:
            continue
        traces.append(go.Scatter3d(
            x=xs, y=ys, z=zs,
            mode="lines",
            line=dict(color=col, width=w),
            opacity=0.50,
            hoverinfo="none",
            name=labels_map[key],
            showlegend=True,
        ))
    return traces


def _make_node_trace(G, pos, stress, meta, communities):
    cent = _centrality(G)

    comm_map = {}
    if communities:
        for cid, members in enumerate(communities):
            for m in members:
                comm_map[m] = cid

    nodes = list(G.nodes)
    xs = [pos[n][0] for n in nodes]
    ys = [pos[n][1] for n in nodes]
    zs = [pos[n][2] for n in nodes]
    stress_vals = [max(0.0, min(1.0, stress.get(n, 0.0))) for n in nodes]
    sizes = [max(14, 16 + 44 * stress.get(n, 0) + 18 * cent.get(n, 0)) for n in nodes]

    hovers = []
    for n in nodes:
        s   = stress.get(n, 0.0)
        c   = cent.get(n, 0.0)
        sec = meta.get(n, {}).get("sector", "—") if meta else "—"
        cid = comm_map.get(n, "—")
        deg = G.degree(n)
        bar = "█" * int(s * 10) + "░" * (10 - int(s * 10))
        hovers.append(
            f"<b>{n}</b><br>"
            f"Sector: {sec}<br>"
            f"Stress: {s:.3f}  {bar}<br>"
            f"Centrality: {c:.3f}<br>"
            f"Degree: {deg}<br>"
            f"Community: {cid}"
        )

    return go.Scatter3d(
        x=xs, y=ys, z=zs,
        mode="markers+text",
        marker=dict(
            size=sizes,
            color=stress_vals,
            colorscale=STRESS_SCALE,
            cmin=0, cmax=1,
            colorbar=dict(
                title=dict(text="Stress", font=dict(color=TEXT, size=12)),
                tickfont=dict(color=TEXT, size=11),
                thickness=16,
                len=0.55,
                x=1.02,
                bgcolor="rgba(26,29,38,0.8)",
                bordercolor="#2A2D3A",
                tickvals=[0, 0.25, 0.5, 0.75, 1.0],
                ticktext=["0.0 Safe", "0.25", "0.50", "0.75", "1.0 Crit"],
            ),
            line=dict(width=2, color="rgba(255,255,255,0.7)"),
            opacity=1.0,
        ),
        text=[str(n) for n in nodes],
        textposition="top center",
        textfont=dict(size=12, color="#FFFFFF", family="IBM Plex Mono, monospace"),
        hovertext=hovers,
        hoverinfo="text",
        hoverlabel=dict(
            bgcolor="#1A1D26",
            bordercolor=ACCENT,
            font=dict(color="#FFFFFF", size=12),
        ),
        name="Assets",
        showlegend=False,
    )


def _scene():
    ax = dict(
        showbackground=True,
        backgroundcolor="rgba(17,19,24,0.95)",
        gridcolor="rgba(255,255,255,0.07)",
        zerolinecolor="rgba(255,255,255,0.12)",
        showticklabels=False,
        color=TEXT_DIM,
    )
    return dict(bgcolor=BG, xaxis=ax, yaxis=ax, zaxis=ax,
                camera=dict(eye=dict(x=1.6, y=1.0, z=0.75)))


def _base_layout(title, **extra):
    d = dict(
        title=dict(text=title, font=dict(size=15, color=TEXT, family="IBM Plex Mono"), x=0.5),
        showlegend=True,
        legend=dict(bgcolor="rgba(26,29,38,0.92)", bordercolor="#2A2D3A",
                    font=dict(color=TEXT, size=11), x=0, y=0.98),
        margin=dict(l=0, r=0, b=40, t=55),
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        scene=_scene(),
        font=dict(color=TEXT, size=12),
    )
    d.update(extra)
    return d


def _static_network(G, pos, stress, meta, communities):
    data = _make_edge_traces(G, pos, stress) + [_make_node_trace(G, pos, stress, meta, communities)]
    return go.Figure(data=data, layout=go.Layout(**_base_layout("3D Systemic Risk Contagion Network")))


def _animated_network(G, pos, history, meta, communities):
    frames = [
        go.Frame(
            data=_make_edge_traces(G, pos, s) + [_make_node_trace(G, pos, s, meta, communities)],
            name=str(t),
        )
        for t, s in enumerate(history)
    ]

    init = history[0]
    data = _make_edge_traces(G, pos, init) + [_make_node_trace(G, pos, init, meta, communities)]

    layout = _base_layout("3D Contagion — Animated  (▶ Play to watch shock propagate)")
    layout["updatemenus"] = [dict(
        type="buttons",
        showactive=False,
        y=-0.04, x=0.5, xanchor="center",
        bgcolor=BG_PANEL,
        bordercolor=ACCENT,
        font=dict(color="#FFFFFF", size=12),
        buttons=[
            dict(label="▶  Play", method="animate",
                 args=[None, dict(frame=dict(duration=350, redraw=True), fromcurrent=True)]),
            dict(label="⏸  Pause", method="animate",
                 args=[[None], dict(frame=dict(duration=0, redraw=False), mode="immediate")]),
        ],
    )]
    layout["sliders"] = [dict(
        steps=[dict(args=[[f.name], dict(frame=dict(duration=350, redraw=True), mode="immediate")],
                    label=f"t={f.name}", method="animate") for f in frames],
        active=0, y=0.02, x=0.05, len=0.9, xanchor="left",
        currentvalue=dict(prefix="Step: ", font=dict(color=TEXT, size=12), visible=True),
        font=dict(color=TEXT),
        bgcolor=BG_PANEL, bordercolor="#2A2D3A", activebgcolor=ACCENT,
    )]

    return go.Figure(data=data, frames=frames, layout=go.Layout(**layout))


# ════════════════════════════════════════════════════════════════════════════
#  Correlation heatmap
# ════════════════════════════════════════════════════════════════════════════

def plot_correlation_heatmap(corr_matrix: np.ndarray, asset_names: list) -> go.Figure:
    fig = go.Figure(go.Heatmap(
        z=corr_matrix, x=asset_names, y=asset_names,
        colorscale=CORR_SCALE, zmin=-1, zmax=1,
        colorbar=dict(title=dict(text="ρ", font=dict(color=TEXT)), tickfont=dict(color=TEXT)),
        hovertemplate="%{y} / %{x}<br>ρ = %{z:.3f}<extra></extra>",
    ))
    fig.update_layout(
        title=dict(text="Correlation Matrix", font=dict(color=TEXT, size=15, family="IBM Plex Mono"), x=0.5),
        paper_bgcolor=BG, plot_bgcolor=BG, font=dict(color=TEXT),
        xaxis=dict(tickangle=-45, tickfont=dict(size=10, color=TEXT)),
        yaxis=dict(tickfont=dict(size=10, color=TEXT)),
        margin=dict(l=80, r=20, t=60, b=100),
    )
    return fig


# ════════════════════════════════════════════════════════════════════════════
#  Stress trajectory
# ════════════════════════════════════════════════════════════════════════════

def plot_stress_trajectory(history: list, asset_names: list, meta: Optional[dict] = None) -> go.Figure:
    n = len(history)
    fig = go.Figure()
    totals = [sum(h.values()) / max(1, len(h)) for h in history]
    fig.add_trace(go.Scatter(
        x=list(range(n)), y=totals, mode="lines",
        name="⚡ System Avg", line=dict(color=ACCENT, width=3, dash="dot"),
    ))
    final = history[-1]
    top = sorted(final, key=final.get, reverse=True)[:8]
    palette = ["#818CF8","#34D399","#F472B6","#FBBF24","#38BDF8","#FB923C","#A78BFA","#4ADE80"]
    for i, asset in enumerate(top):
        col = meta.get(asset, {}).get("color", palette[i % 8]) if meta else palette[i % 8]
        fig.add_trace(go.Scatter(
            x=list(range(n)), y=[h.get(asset, 0) for h in history],
            mode="lines", name=asset, line=dict(width=2, color=col),
        ))
    fig.update_layout(
        title=dict(text="Stress Propagation Over Time", font=dict(color=TEXT, size=15, family="IBM Plex Mono"), x=0.5),
        paper_bgcolor=BG, plot_bgcolor=BG, font=dict(color=TEXT),
        xaxis=dict(title="Time Step", gridcolor=GRID, color=TEXT, tickfont=dict(color=TEXT)),
        yaxis=dict(title="Stress", gridcolor=GRID, color=TEXT, range=[0, 1.05], tickfont=dict(color=TEXT)),
        legend=dict(bgcolor="rgba(26,29,38,0.9)", bordercolor="#2A2D3A", font=dict(color=TEXT, size=11)),
        margin=dict(l=60, r=20, t=60, b=60),
    )
    return fig


# ════════════════════════════════════════════════════════════════════════════
#  Stress heatmap
# ════════════════════════════════════════════════════════════════════════════

def plot_stress_heatmap(history: list, asset_names: list) -> go.Figure:
    matrix = np.array([[h.get(a, 0.0) for a in asset_names] for h in history])
    fig = go.Figure(go.Heatmap(
        z=matrix, x=asset_names, y=[f"t={t}" for t in range(len(history))],
        colorscale=STRESS_SCALE, zmin=0, zmax=1,
        colorbar=dict(title=dict(text="Stress", font=dict(color=TEXT)), tickfont=dict(color=TEXT)),
        hovertemplate="%{x}<br>%{y}<br>Stress: %{z:.3f}<extra></extra>",
    ))
    fig.update_layout(
        title=dict(text="Contagion Heatmap — Time × Asset", font=dict(color=TEXT, size=15, family="IBM Plex Mono"), x=0.5),
        paper_bgcolor=BG, plot_bgcolor=BG, font=dict(color=TEXT),
        xaxis=dict(tickangle=-45, tickfont=dict(size=9, color=TEXT)),
        yaxis=dict(tickfont=dict(size=9, color=TEXT), autorange="reversed"),
        margin=dict(l=70, r=20, t=60, b=100),
    )
    return fig


# ════════════════════════════════════════════════════════════════════════════
#  Eigenvalue spectrum
# ════════════════════════════════════════════════════════════════════════════

def plot_eigenvalue_spectrum(corr_matrix: np.ndarray) -> go.Figure:
    eigvals = np.sort(np.linalg.eigvalsh(corr_matrix))[::-1]
    n = len(eigvals)
    mp = (1 + np.sqrt(1 / max(1, n))) ** 2 * 2
    colors = ["#D73027" if v > mp else "#4575B4" for v in eigvals]
    fig = go.Figure(go.Bar(
        x=list(range(1, n + 1)), y=eigvals,
        marker=dict(color=colors, line=dict(width=0)),
        hovertemplate="Factor %{x}<br>Eigenvalue: %{y:.4f}<extra></extra>",
    ))
    fig.add_hline(y=mp, line_dash="dash", line_color=ACCENT, line_width=2,
                  annotation_text=f"  M-P bound ({mp:.2f})",
                  annotation_font_color=ACCENT, annotation_font_size=12)
    fig.update_layout(
        title=dict(text="Eigenvalue Spectrum  (red bars = genuine market factors)", font=dict(color=TEXT, size=15, family="IBM Plex Mono"), x=0.5),
        paper_bgcolor=BG, plot_bgcolor=BG, font=dict(color=TEXT),
        xaxis=dict(title="Factor #", gridcolor=GRID, color=TEXT, tickfont=dict(color=TEXT)),
        yaxis=dict(title="Eigenvalue", gridcolor=GRID, color=TEXT, tickfont=dict(color=TEXT)),
        margin=dict(l=60, r=20, t=60, b=60),
    )
    return fig


# ════════════════════════════════════════════════════════════════════════════
#  Risk bar chart
# ════════════════════════════════════════════════════════════════════════════

def plot_risk_bars(metrics: dict, asset_names: list, meta: Optional[dict] = None) -> go.Figure:
    node_risk = metrics.get("node_risk", {})
    debt_rank = node_risk.get("debt_rank", {})
    eigen_c   = node_risk.get("eigenvector_centrality", {})
    if not debt_rank:
        return go.Figure()

    names   = sorted(debt_rank, key=debt_rank.get, reverse=True)[:15]
    dr_vals = [debt_rank[n] for n in names]
    ec_vals = [eigen_c.get(n, 0) for n in names]
    sector_palette = {"Banks":"#F97316","Insurance":"#38BDF8","Asset Managers":"#FBBF24","FinTech":"#34D399"}
    colors = [sector_palette.get(meta.get(n, {}).get("sector",""), "#818CF8") if meta else "#818CF8" for n in names]

    fig = make_subplots(rows=1, cols=2, subplot_titles=["DebtRank Score", "Eigenvector Centrality"])
    fig.add_trace(go.Bar(x=names, y=dr_vals, marker_color=colors,
                         hovertemplate="%{x}: %{y:.4f}<extra></extra>", name="DebtRank"), row=1, col=1)
    fig.add_trace(go.Bar(x=names, y=ec_vals, marker_color=colors,
                         hovertemplate="%{x}: %{y:.4f}<extra></extra>", name="Centrality"), row=1, col=2)
    fig.update_layout(
        title=dict(text="Systemic Importance", font=dict(color=TEXT, size=15, family="IBM Plex Mono"), x=0.5),
        paper_bgcolor=BG, plot_bgcolor=BG, font=dict(color=TEXT),
        showlegend=False, margin=dict(l=40, r=20, t=80, b=100),
    )
    for i in [1, 2]:
        fig.update_xaxes(tickangle=-45, tickfont=dict(size=10, color=TEXT), gridcolor=GRID, row=1, col=i)
        fig.update_yaxes(tickfont=dict(color=TEXT), gridcolor=GRID, row=1, col=i)
    for ann in fig.layout.annotations:
        ann.font.color = TEXT
        ann.font.size = 13
    return fig
