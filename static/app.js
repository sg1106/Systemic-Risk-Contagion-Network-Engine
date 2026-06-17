'use strict';

const $ = (id) => document.getElementById(id);

// ════════════════════════════════════════════════════════════════════
//  DOM references
// ════════════════════════════════════════════════════════════════════
const el = {
  dataMode: $('dataMode'), nAssets: $('nAssets'), nAssetsVal: $('nAssetsVal'),
  nDays: $('nDays'), nDaysVal: $('nDaysVal'),
  networkMethod: $('networkMethod'), layoutMethod: $('layoutMethod'),
  corrThreshold: $('corrThreshold'), corrThresholdVal: $('corrThresholdVal'),
  partialCorr: $('partialCorr'),
  scenarioType: $('scenarioType'),
  shockAssetRow: $('shockAssetRow'), shockAsset: $('shockAsset'),
  shockSectorRow: $('shockSectorRow'), shockSector: $('shockSector'),
  topNRow: $('topNRow'), topN: $('topN'), topNVal: $('topNVal'),
  shockMag: $('shockMag'), shockMagVal: $('shockMagVal'),
  contagionModel: $('contagionModel'),
  nSteps: $('nSteps'), nStepsVal: $('nStepsVal'),
  decay: $('decay'), decayVal: $('decayVal'),
  tauRow: $('tauRow'), tau: $('tau'), tauVal: $('tauVal'),
  recoveryRow: $('recoveryRow'), recovery: $('recovery'), recoveryVal: $('recoveryVal'),
  ampRow: $('ampRow'), amp: $('amp'), ampVal: $('ampVal'),
  animate: $('animate'),
  runBtn: $('runBtn'),
  sidebarHint: $('sidebarHint'),
  sidebar: $('sidebar'), menuBtn: $('menuBtn'),
  tabs: Array.from(document.querySelectorAll('.tab')),
  panels: Array.from(document.querySelectorAll('.panel')),
  shockBanner: $('shockBanner'),
  statusValue: $('statusValue'), liveDot: $('liveDot'),
  loadingOverlay: $('loadingOverlay'), loadingText: $('loadingText'),
  seismoLine: $('seismoLine'), seismoArea: $('seismoArea'), seismoGrid: $('seismoGrid'),
  seismoLabel: $('seismoLabel'), seismoPeak: $('seismoPeak'),
};

let latestResult = null;
let renderedPanels = new Set();

const PANEL_FIGURE_KEY = {
  network: 'network', trajectory: 'trajectory', heatmap: 'heatmap',
  correlation: 'correlation', eigen: 'eigen', rankings: 'risk_bars',
};
const PANEL_DIV_ID = {
  network: 'plot-network', trajectory: 'plot-trajectory', heatmap: 'plot-heatmap',
  correlation: 'plot-correlation', eigen: 'plot-eigen', rankings: 'plot-riskbars',
};

// ════════════════════════════════════════════════════════════════════
//  Slider live-value display
// ════════════════════════════════════════════════════════════════════
function bindRangeDisplay(rangeEl, displayEl, decimals) {
  const update = () => { displayEl.textContent = parseFloat(rangeEl.value).toFixed(decimals); };
  rangeEl.addEventListener('input', update);
  update();
}
bindRangeDisplay(el.nAssets, el.nAssetsVal, 0);
bindRangeDisplay(el.nDays, el.nDaysVal, 0);
bindRangeDisplay(el.corrThreshold, el.corrThresholdVal, 2);
bindRangeDisplay(el.topN, el.topNVal, 0);
bindRangeDisplay(el.shockMag, el.shockMagVal, 2);
bindRangeDisplay(el.nSteps, el.nStepsVal, 0);
bindRangeDisplay(el.decay, el.decayVal, 2);
bindRangeDisplay(el.tau, el.tauVal, 2);
bindRangeDisplay(el.recovery, el.recoveryVal, 2);
bindRangeDisplay(el.amp, el.ampVal, 1);

// ════════════════════════════════════════════════════════════════════
//  Conditional sidebar rows
// ════════════════════════════════════════════════════════════════════
function updateScenarioUI() {
  const t = el.scenarioType.value;
  el.shockAssetRow.classList.toggle('hidden', t !== 'single');
  el.shockSectorRow.classList.toggle('hidden', t !== 'sector');
  el.topNRow.classList.toggle('hidden', t !== 'top_n');
}
function updateModelUI() {
  const m = el.contagionModel.value;
  el.tauRow.classList.toggle('hidden', m !== 'threshold');
  el.recoveryRow.classList.toggle('hidden', m !== 'sir');
  el.ampRow.classList.toggle('hidden', m !== 'fitch');
}
el.scenarioType.addEventListener('change', updateScenarioUI);
el.contagionModel.addEventListener('change', updateModelUI);
updateScenarioUI();
updateModelUI();

// ════════════════════════════════════════════════════════════════════
//  Mobile sidebar drawer
// ════════════════════════════════════════════════════════════════════
el.menuBtn.addEventListener('click', () => el.sidebar.classList.toggle('open'));
document.addEventListener('click', (e) => {
  if (window.innerWidth <= 980 && el.sidebar.classList.contains('open')) {
    if (!el.sidebar.contains(e.target) && !el.menuBtn.contains(e.target)) {
      el.sidebar.classList.remove('open');
    }
  }
});

// ════════════════════════════════════════════════════════════════════
//  Tabs
// ════════════════════════════════════════════════════════════════════
el.tabs.forEach((tab) => {
  tab.addEventListener('click', () => {
    el.tabs.forEach((t) => t.classList.remove('active'));
    el.panels.forEach((p) => p.classList.remove('active'));
    tab.classList.add('active');
    document.querySelector(`.panel[data-panel="${tab.dataset.panel}"]`).classList.add('active');
    ensurePanelPlotted(tab.dataset.panel);
    if (window.innerWidth <= 980) el.sidebar.classList.remove('open');
  });
});

// ════════════════════════════════════════════════════════════════════
//  Asset list (populates Shock Asset / Shock Sector dropdowns)
// ════════════════════════════════════════════════════════════════════
let assetsFetchTimer = null;
function scheduleAssetsFetch() {
  clearTimeout(assetsFetchTimer);
  assetsFetchTimer = setTimeout(fetchAssets, 350);
}
[el.dataMode, el.nAssets, el.nDays].forEach((input) => {
  input.addEventListener('change', scheduleAssetsFetch);
});

async function fetchAssets() {
  const payload = {
    data_mode: el.dataMode.value,
    n_assets: parseInt(el.nAssets.value, 10),
    n_days: parseInt(el.nDays.value, 10),
  };
  try {
    const res = await fetch('/api/assets', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    populateAssetDropdowns(data.asset_names, data.sectors);
    return data;
  } catch (err) {
    console.error('Failed to fetch assets', err);
    return null;
  }
}

function populateAssetDropdowns(names, sectors) {
  const prevAsset = el.shockAsset.value;
  const prevSector = el.shockSector.value;
  el.shockAsset.innerHTML = names.map((n) => `<option value="${n}">${n}</option>`).join('');
  el.shockSector.innerHTML = sectors.map((s) => `<option value="${s}">${s}</option>`).join('');
  if (names.includes(prevAsset)) el.shockAsset.value = prevAsset;
  if (sectors.includes(prevSector)) el.shockSector.value = prevSector;
}

// ════════════════════════════════════════════════════════════════════
//  Loading overlay
// ════════════════════════════════════════════════════════════════════
const LOADING_MESSAGES = [
  'Loading market data…',
  'Computing correlation matrix…',
  'Building network topology…',
  'Detecting communities…',
  'Propagating shock…',
  'Computing systemic risk metrics…',
  'Rendering visualizations…',
];
let loadingMsgTimer = null;
function showLoading() {
  let i = 0;
  el.loadingText.textContent = LOADING_MESSAGES[0];
  el.loadingOverlay.classList.add('active');
  loadingMsgTimer = setInterval(() => {
    i = (i + 1) % LOADING_MESSAGES.length;
    el.loadingText.textContent = LOADING_MESSAGES[i];
  }, 650);
}
function hideLoading() {
  clearInterval(loadingMsgTimer);
  el.loadingOverlay.classList.remove('active');
}

function setStatus(text, cls) {
  el.statusValue.textContent = text;
  el.statusValue.className = 'status-value ' + (cls || '');
}

// ════════════════════════════════════════════════════════════════════
//  Run simulation
// ════════════════════════════════════════════════════════════════════
el.runBtn.addEventListener('click', runSimulation);

function gatherPayload() {
  return {
    data_mode: el.dataMode.value,
    n_assets: parseInt(el.nAssets.value, 10),
    n_days: parseInt(el.nDays.value, 10),
    network_method: el.networkMethod.value,
    layout_method: el.layoutMethod.value,
    corr_threshold: parseFloat(el.corrThreshold.value),
    show_partial_corr: el.partialCorr.checked,
    scenario_type: el.scenarioType.value,
    shock_asset: el.shockAsset.value,
    shock_sector: el.shockSector.value,
    top_n: parseInt(el.topN.value, 10),
    shock_magnitude: parseFloat(el.shockMag.value),
    contagion_model: el.contagionModel.value,
    n_steps: parseInt(el.nSteps.value, 10),
    decay: parseFloat(el.decay.value),
    threshold_tau: parseFloat(el.tau.value),
    recovery_rate: parseFloat(el.recovery.value),
    amplification: parseFloat(el.amp.value),
    animate: el.animate.checked,
  };
}

async function runSimulation() {
  el.runBtn.disabled = true;
  el.runBtn.textContent = 'RUNNING…';
  showLoading();
  setStatus('SIMULATING', 'loading');

  try {
    const payload = gatherPayload();
    const res = await fetch('/api/simulate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({ error: res.statusText }));
      throw new Error(errBody.error || 'Simulation failed');
    }
    const data = await res.json();
    renderResult(data);
    setStatus('NOMINAL', 'ok');
    el.sidebarHint.textContent = 'Simulation complete. Adjust parameters and run again to explore other scenarios.';
  } catch (err) {
    console.error(err);
    setStatus('ERROR', 'danger');
    el.sidebarHint.textContent = `Couldn't complete the simulation — ${err.message}. Check that the server is reachable and try again.`;
  } finally {
    hideLoading();
    el.runBtn.disabled = false;
    el.runBtn.textContent = 'RUN SIMULATION ▸';
  }
}

// ════════════════════════════════════════════════════════════════════
//  Rendering — orchestration
// ════════════════════════════════════════════════════════════════════
function fmtNum(v, d = 3) { return typeof v === 'number' ? v.toFixed(d) : '—'; }

function renderResult(data) {
  latestResult = data;
  renderedPanels = new Set();

  renderTicker(data);
  renderShockBanner(data);
  renderSeismograph(data.history);
  renderNetworkStats(data);
  renderCorrStats(data);
  renderEigenStats(data);
  renderReturnRiskStats(data);
  renderRiskTable(data);
  renderRankingTable(data);
  renderDebtRankTable(data);
  renderMetricsJson(data);
  renderPeakInfo(data);
  renderLiveDot(data);

  const activeTab = document.querySelector('.tab.active');
  ensurePanelPlotted(activeTab ? activeTab.dataset.panel : 'network');
}

function ensurePanelPlotted(panelName) {
  if (!latestResult || !PANEL_FIGURE_KEY[panelName]) return;
  const divId = PANEL_DIV_ID[panelName];
  if (renderedPanels.has(panelName)) {
    try { Plotly.Plots.resize(divId); } catch (e) { /* noop */ }
    return;
  }
  renderPlot(divId, latestResult.figures[PANEL_FIGURE_KEY[panelName]]);
  renderedPanels.add(panelName);
}

function renderPlot(divId, figJson) {
  const layout = Object.assign({}, figJson.layout, { autosize: true });
  const config = {
    responsive: true,
    displaylogo: false,
    modeBarButtonsToRemove: ['lasso2d', 'select2d'],
  };
  if (figJson.frames && figJson.frames.length) {
    Plotly.newPlot(divId, { data: figJson.data, layout, frames: figJson.frames }, config);
  } else {
    Plotly.newPlot(divId, figJson.data, layout, config);
  }
}

// ════════════════════════════════════════════════════════════════════
//  Ticker / risk badge / shock banner
// ════════════════════════════════════════════════════════════════════
function riskLevel(maxStress) {
  if (maxStress < 0.2) return ['LOW', 'low'];
  if (maxStress < 0.5) return ['MODERATE', 'medium'];
  if (maxStress < 0.75) return ['HIGH', 'high'];
  return ['CRITICAL', 'critical'];
}

function renderTicker(data) {
  const c = data.metrics.contagion || {};
  $('mTotalStress').textContent = fmtNum(c.total_stress);
  $('mMaxStress').textContent = fmtNum(c.max_stress);
  $('mDistressed').textContent = `${c.n_distressed_nodes ?? '—'}/${data.asset_names.length}`;
  $('mCritical').textContent = c.n_critical_nodes ?? '—';
  $('mSri').textContent = fmtNum(data.sri, 4);
  $('mSpeed').textContent = fmtNum(data.contagion_speed, 4);

  const [label, cls] = riskLevel(c.max_stress ?? 0);
  const badge = $('riskBadge');
  badge.textContent = label;
  badge.className = 'risk-badge ' + cls;
}

function renderShockBanner(data) {
  const entries = Object.entries(data.initial_shock || {});
  if (!entries.length) { el.shockBanner.classList.add('hidden'); return; }
  el.shockBanner.classList.remove('hidden');
  const txt = entries.map(([k, v]) => `${k} (${v.toFixed(2)})`).join(', ');
  el.shockBanner.textContent = `INITIAL SHOCK APPLIED TO: ${txt}`;
}

function renderLiveDot(data) {
  const maxStress = data.metrics.contagion?.max_stress ?? 0;
  el.liveDot.classList.toggle('danger', maxStress >= 0.5);
}

// ════════════════════════════════════════════════════════════════════
//  Seismograph — signature element
// ════════════════════════════════════════════════════════════════════
function renderSeismograph(history) {
  if (!history || !history.length) return;
  const totals = history.map((h) => {
    const vals = Object.values(h);
    return vals.reduce((a, b) => a + b, 0) / Math.max(1, vals.length);
  });
  const W = 1000, H = 90, PAD = 6;
  const n = totals.length;
  const maxV = Math.max(0.05, ...totals);
  const xStep = n > 1 ? W / (n - 1) : W;

  const points = totals.map((v, i) => {
    const x = i * xStep;
    const y = H - PAD - (v / maxV) * (H - PAD * 2);
    return [x, y];
  });

  const linePath = points.map((p, i) => (i === 0 ? `M${p[0]},${p[1]}` : `L${p[0]},${p[1]}`)).join(' ');
  const areaPath = `${linePath} L${W},${H} L0,${H} Z`;

  el.seismoLine.setAttribute('d', linePath);
  el.seismoArea.setAttribute('d', areaPath);

  const peak = Math.max(...totals);
  el.seismoLabel.textContent = `SYSTEM STRESS — t=0→${n - 1}`;
  el.seismoPeak.textContent = `PEAK ${peak.toFixed(3)}`;
}

function initSeismoGrid() {
  el.seismoGrid.innerHTML = '';
  for (let i = 1; i < 4; i++) {
    const y = (90 / 4) * i;
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', 0); line.setAttribute('x2', 1000);
    line.setAttribute('y1', y); line.setAttribute('y2', y);
    el.seismoGrid.appendChild(line);
  }
}

// ════════════════════════════════════════════════════════════════════
//  Side panel stats (Network / Correlation / Eigen / Return-risk)
// ════════════════════════════════════════════════════════════════════
function statRow(label, value) {
  return `<div><span>${label}</span><span>${value}</span></div>`;
}

function renderNetworkStats(data) {
  const net = data.metrics.network || {};
  $('networkStatsList').innerHTML = [
    statRow('Nodes', net.nodes ?? '—'),
    statRow('Edges', net.edges ?? '—'),
    statRow('Density', net.density ?? '—'),
    statRow('Avg degree', net.avg_degree ?? '—'),
    statRow('Clustering', net.avg_clustering ?? '—'),
    statRow('Components', net.n_components ?? '—'),
    statRow('Avg path', net.avg_path_length ?? '—'),
    statRow('Assortativity', net.assortativity ?? '—'),
  ].join('');

  $('communitiesList').innerHTML = (data.communities || []).slice(0, 6).map((c, i) => {
    const shown = c.slice(0, 4).join(', ');
    const extra = c.length > 4 ? ` +${c.length - 4}` : '';
    return `<div>C${i + 1}: ${shown}${extra}</div>`;
  }).join('');

  const payload = gatherPayload();
  let extra = '';
  if (payload.contagion_model === 'threshold') extra = `τ = ${payload.threshold_tau}`;
  else if (payload.contagion_model === 'sir') extra = `recovery = ${payload.recovery_rate}`;
  else if (payload.contagion_model === 'fitch') extra = `amplification = ${payload.amplification}`;
  $('modelInfo').innerHTML = `
    <div><strong>${payload.contagion_model.toUpperCase()}</strong> contagion</div>
    <div>${payload.n_steps} steps · decay=${payload.decay}</div>
    <div>${extra}</div>`;
}

function renderCorrStats(data) {
  const corr = data.correlation_matrix;
  const n = corr.length;
  let sum = 0, count = 0;
  for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) { sum += Math.abs(corr[i][j]); count++; }
  const mean = count ? sum / count : 0;
  $('corrModeLabel').textContent = gatherPayload().show_partial_corr ? 'Partial Correlation' : 'Full Correlation';
  $('corrStatsList').innerHTML = statRow('Mean |ρ|', mean.toFixed(4));
}

function renderEigenStats(data) {
  const s = data.metrics.spectral || {};
  $('eigenStats').innerHTML = [
    ['Top Eigenvalue', s.top_eigenvalue],
    ['Spectral Risk Ratio', s.spectral_risk_ratio],
    ['Significant Factors', s.n_significant_factors],
    ['Eigenvalue Entropy', s.eigenvalue_entropy],
  ].map(([label, val]) => `
    <div class="ticker-cell"><span class="ticker-label">${label}</span><span class="ticker-value">${val ?? '—'}</span></div>
  `).join('');
}

function renderReturnRiskStats(data) {
  const r = data.metrics.return_risk || {};
  $('returnRiskStats').innerHTML = [
    ['Portfolio VaR (95%)', fmtNum(r.portfolio_var_95, 4)],
    ['Portfolio ES (95%)', fmtNum(r.portfolio_es_95, 4)],
  ].map(([label, val]) => `
    <div class="ticker-cell"><span class="ticker-label">${label}</span><span class="ticker-value">${val}</span></div>
  `).join('');
}

// ════════════════════════════════════════════════════════════════════
//  Tables
// ════════════════════════════════════════════════════════════════════
function stressBarCell(s) {
  const pct = Math.min(100, Math.max(0, s * 100));
  return `<div class="stress-bar-cell"><span>${s.toFixed(4)}</span><div class="stress-bar-track"><div class="stress-bar-fill" style="width:${pct}%"></div></div></div>`;
}

function renderRiskTable(data) {
  const r = data.metrics.return_risk || {};
  const finalStress = data.history[data.history.length - 1] || {};
  const names = Object.keys(r.asset_var_95 || {});
  const rows = names.map((n) => ({
    asset: n,
    var95: r.asset_var_95?.[n] ?? 0,
    es95: r.asset_es_95?.[n] ?? 0,
    vol: r.annualized_volatility?.[n] ?? 0,
    stress: finalStress[n] ?? 0,
  })).sort((a, b) => b.stress - a.stress).slice(0, 10);

  $('riskTable').innerHTML = `
    <thead><tr><th>Asset</th><th>VaR (95%)</th><th>ES (95%)</th><th>Ann. Vol</th><th>Stress</th></tr></thead>
    <tbody>${rows.map((row) => `
      <tr>
        <td>${row.asset}</td>
        <td>${row.var95.toFixed(4)}</td>
        <td>${row.es95.toFixed(4)}</td>
        <td>${row.vol.toFixed(4)}</td>
        <td>${stressBarCell(row.stress)}</td>
      </tr>`).join('')}
    </tbody>`;
}

function renderRankingTable(data) {
  const ranking = data.metrics.contagion?.systemic_importance_ranking || [];
  const meta = data.meta || {};
  $('rankingTable').innerHTML = `
    <thead><tr><th>#</th><th>Asset</th><th>Sector</th><th>Final Stress</th></tr></thead>
    <tbody>${ranking.map(([asset, stress], i) => `
      <tr>
        <td>${i + 1}</td>
        <td>${asset}</td>
        <td>${meta[asset]?.sector ?? '—'}</td>
        <td>${stressBarCell(stress)}</td>
      </tr>`).join('')}
    </tbody>`;
}

function renderDebtRankTable(data) {
  const dr = data.metrics.node_risk?.debt_rank || {};
  const meta = data.meta || {};
  const sorted = Object.entries(dr).sort((a, b) => b[1] - a[1]).slice(0, 10);
  $('debtRankTable').innerHTML = `
    <thead><tr><th>#</th><th>Asset</th><th>Sector</th><th>DebtRank</th></tr></thead>
    <tbody>${sorted.map(([asset, score], i) => `
      <tr><td>${i + 1}</td><td>${asset}</td><td>${meta[asset]?.sector ?? '—'}</td><td>${score.toFixed(6)}</td></tr>`).join('')}
    </tbody>`;
}

function renderMetricsJson(data) {
  $('metricsJson').textContent = JSON.stringify(data.metrics, null, 2);
}

function renderPeakInfo(data) {
  const c = data.metrics.contagion || {};
  $('peakInfo').textContent = c.time_to_peak != null ? `System stress peaks at t=${c.time_to_peak}.` : '';
}

// ════════════════════════════════════════════════════════════════════
//  CSV export
// ════════════════════════════════════════════════════════════════════
function downloadCsv(filename, csvContent) {
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

$('exportStress').addEventListener('click', () => {
  if (!latestResult) return;
  const names = latestResult.asset_names;
  const rows = [['time_step', ...names]];
  latestResult.history.forEach((h, t) => rows.push([t, ...names.map((n) => (h[n] ?? 0).toFixed(6))]));
  downloadCsv('stress_history.csv', rows.map((r) => r.join(',')).join('\n'));
});

$('exportCorr').addEventListener('click', () => {
  if (!latestResult) return;
  const names = latestResult.asset_names;
  const corr = latestResult.correlation_matrix;
  const rows = [['', ...names]];
  corr.forEach((row, i) => rows.push([names[i], ...row.map((v) => v.toFixed(6))]));
  downloadCsv('correlation_matrix.csv', rows.map((r) => r.join(',')).join('\n'));
});

// ════════════════════════════════════════════════════════════════════
//  Init
// ════════════════════════════════════════════════════════════════════
(async function init() {
  initSeismoGrid();
  await fetchAssets();
  runSimulation();
})();
