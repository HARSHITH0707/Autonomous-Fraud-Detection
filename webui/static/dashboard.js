import { auth, onAuthStateChanged } from './auth.js';
import {
  FX,
  initCinematicShell,
  pushMetricHistory,
  createSparklineSVG,
  animateOdometer,
  estimateClientRisk,
  riskHue,
  showToast,
  buildGraphFromApi,
  renderD3Graph,
  pushAgentScore,
} from './dashboard-fx.js';

const state = {
  recentRuns: [],
  latest: null,
  stopGraph: null,
};

const AGENT_META = {
  TRANSACTION_MONITOR: { icon: '🔍', label: 'Transaction Monitor' },
  BEHAVIOUR_ANALYSER: { icon: '🧠', label: 'Behaviour Analyser' },
  BEHAVIOR_ANALYSER: { icon: '🧠', label: 'Behaviour Analyser' },
  GRAPH_FRAUD_DETECTOR: { icon: '🕸', label: 'Graph Fraud Detector' },
};

const GAUGE_ARC = 173;

function byId(id) {
  return document.getElementById(id);
}

function fixed(value, digits = 4) {
  return Number(value || 0).toFixed(digits);
}

function bannerClass(decision) {
  if (decision === 'BLOCK') return 'block';
  if (decision === 'OTP') return 'otp';
  if (decision === 'ALLOW') return 'allow';
  return 'neutral';
}

function severityClass(severity) {
  const s = String(severity || '').toLowerCase();
  if (s.includes('high') || s.includes('critical')) return 'high';
  if (s.includes('medium') || s.includes('moderate')) return 'medium';
  return 'low';
}

function agentMeta(name) {
  const key = String(name || '').toUpperCase().replace(/\s+/g, '_');
  for (const [k, v] of Object.entries(AGENT_META)) {
    if (key.includes(k) || k.includes(key)) return v;
  }
  return { icon: '⚡', label: name?.replaceAll('_', ' ') || 'Agent' };
}

function readTransactionForm() {
  const form = byId('txn-form');
  const data = new FormData(form);
  return {
    transaction_id: data.get('transaction_id'),
    source: 'web',
    channel: data.get('channel'),
    sender_account: data.get('sender_account'),
    receiver_account: data.get('receiver_account'),
    amount: Number(data.get('amount')),
    currency: 'INR',
    transaction_type: String(data.get('channel')).toUpperCase(),
    device_id: data.get('device_id'),
    ip_address: data.get('ip_address'),
    login_country: data.get('login_country'),
    home_country: data.get('home_country'),
    device_mismatch: form.elements.device_mismatch.checked,
    geo_velocity_km: Number(data.get('geo_velocity_km')),
    new_beneficiary: form.elements.new_beneficiary.checked,
    beneficiary_age_days: Number(data.get('beneficiary_age_days')),
    login_velocity_10m: Number(data.get('login_velocity_10m')),
    recent_txn_count_5m: Number(data.get('recent_txn_count_5m')),
    recent_amount_5m: Number(data.get('recent_amount_5m')),
    account_tenure_days: 420,
  };
}

function updateRiskGauge() {
  const form = byId('txn-form');
  if (!form) return;
  const amount = form.elements.amount?.value;
  const geo = form.elements.geo_velocity_km?.value;
  const recent = form.elements.recent_txn_count_5m?.value;
  const risk = estimateClientRisk(amount, geo, recent);
  const arc = byId('risk-gauge-arc');
  const valEl = byId('risk-gauge-val');
  if (!arc || !valEl) return;
  const offset = GAUGE_ARC * (1 - risk);
  const color = riskHue(risk);
  arc.setAttribute('stroke-dashoffset', String(offset));
  arc.setAttribute('stroke', color);
  valEl.textContent = `${Math.round(risk * 100)}%`;
  valEl.style.color = color;
}

function updateMetricSparklines() {
  const recentSpark = byId('spark-recent');
  const riskSpark = byId('spark-risk');
  if (recentSpark && FX.metricHistory.recentTotal?.length) {
    recentSpark.innerHTML = createSparklineSVG(FX.metricHistory.recentTotal);
  }
  if (riskSpark && FX.metricHistory.avgRisk?.length) {
    riskSpark.innerHTML = createSparklineSVG(FX.metricHistory.avgRisk, '#ffb800');
  }
}

function renderDonut(score, color) {
  const pct = Math.min(Math.max(score, 0), 1);
  const r = 36;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - pct);
  return `<svg class="agent-donut" width="88" height="88" viewBox="0 0 88 88">
    <circle cx="44" cy="44" r="${r}" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="6"/>
    <circle cx="44" cy="44" r="${r}" fill="none" stroke="${color}" stroke-width="6"
      stroke-dasharray="${c}" stroke-dashoffset="${offset}" stroke-linecap="round"
      transform="rotate(-90 44 44)" style="filter: drop-shadow(0 0 6px ${color})"/>
  </svg>`;
}

function animateDonut(card, targetScore) {
  const circle = card.querySelector('.agent-donut circle:last-child');
  if (!circle) return;
  const r = 36;
  const c = 2 * Math.PI * r;
  const start = Number(card.dataset.animScore) || 0;
  const end = Math.min(Math.max(targetScore, 0), 1);
  const color = riskHue(end);
  const t0 = performance.now();
  const tick = (now) => {
    const p = Math.min((now - t0) / 800, 1);
    const eased = 1 - Math.pow(1 - p, 3);
    const val = start + (end - start) * eased;
    circle.setAttribute('stroke-dashoffset', String(c * (1 - val)));
    circle.setAttribute('stroke', color);
    card.querySelector('.agent-score-num').textContent = fixed(val);
    if (p < 1) requestAnimationFrame(tick);
    else card.dataset.animScore = String(end);
  };
  requestAnimationFrame(tick);
}

function renderSummary(snapshot) {
  const total = snapshot.recent_total ?? 0;
  const avg = snapshot.avg_risk_score ?? 0;
  byId('recent-total').textContent = total;
  byId('avg-risk').textContent = fixed(avg);
  pushMetricHistory('recentTotal', total);
  pushMetricHistory('avgRisk', avg);
  const recentEl = byId('recent-total');
  if (recentEl) recentEl.dataset.value = String(total);
  updateMetricSparklines();
  animateOdometer(byId('count-allow'), snapshot.counts?.ALLOW ?? 0);
  animateOdometer(byId('count-otp'), snapshot.counts?.OTP ?? 0);
  animateOdometer(byId('count-block'), snapshot.counts?.BLOCK ?? 0);
  state.recentRuns = snapshot.recent_runs ?? [];
  if (snapshot.latest) renderLatest(snapshot.latest);
}

function renderLatest(run) {
  state.latest = run;
  const decision = run.decision.decision;
  const stage = byId('decision-stage');
  stage.className = `decision-stage ${bannerClass(decision)}`;
  const face = stage.querySelector('.hex-face');
  face.querySelector('.decision-label').textContent = `${decision} Decision`;
  face.querySelector('.decision-score').textContent = fixed(run.risk.composite_risk);

  const reasons = byId('decision-reasons');
  reasons.innerHTML = '';
  (run.risk.explanation || ['No escalations']).forEach((reason, i) => {
    const item = document.createElement('div');
    item.className = 'reason-pill';
    item.style.animationDelay = `${i * 100}ms`;
    item.textContent = reason;
    reasons.appendChild(item);
  });

  const cards = byId('agent-cards');
  cards.innerHTML = '';
  Object.values(run.signals).forEach((signal) => {
    const meta = agentMeta(signal.agent_name);
    const score = Number(signal.score) || 0;
    const history = pushAgentScore(signal.agent_name, score);
    const color = riskHue(score);
    const card = document.createElement('article');
    card.className = 'agent-card';
    card.dataset.animScore = '0';
    const flags = (signal.flags || [])
      .map((flag, i) => `<span class="flag" style="animation-delay:${i * 50}ms">${flag}</span>`)
      .join('');
    card.innerHTML = `
      <div class="agent-head">
        <span class="agent-icon">${meta.icon}</span>
        <span class="agent-name">${meta.label}</span>
      </div>
      ${renderDonut(0, color)}
      <span class="agent-score-num">${fixed(0)}</span>
      <span class="agent-severity ${severityClass(signal.severity)}">${signal.severity}</span>
      <span class="agent-spark">${createSparklineSVG(history, color)}</span>
      <div class="agent-flags">${flags || '<span class="flag">No flags</span>'}</div>
    `;
    cards.appendChild(card);
    animateDonut(card, score);
  });
}

function renderGraphOverview(graph) {
  const container = byId('graph-overview');
  container.innerHTML = '';
  const sections = [
    ['Fraud Rings', graph.rings, (row) => `${row.members?.join(' → ') || 'No members'} · total ${Number(row.total || 0).toLocaleString()}`],
    ['Mule Chains', graph.chains, (row) => `${row.chain?.join(' → ') || 'No chain'} · hops ${row.hops}`],
    ['Coordinated Hubs', graph.hubs, (row) => `${row.hub} · ${row.senders} senders · total ${Number(row.total || 0).toLocaleString()}`],
    ['Shared Devices', graph.shared_devices, (row) => `${row.device} · ${row.cnt} linked accounts`],
  ];
  sections.forEach(([title, rows, formatter]) => {
    const card = document.createElement('article');
    card.className = 'graph-chip';
    const top = rows?.[0];
    card.innerHTML = `
      <span class="graph-title">${title}</span>
      <div class="graph-body">${top ? formatter(top) : 'No linked fraud structures available yet.'}</div>
    `;
    container.appendChild(card);
  });

  if (state.stopGraph) state.stopGraph();
  const viz = byId('graph-viz');
  if (viz) {
    state.stopGraph = renderD3Graph(viz, buildGraphFromApi(graph)) || null;
  }
}

async function fetchJson(url, options = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (auth.currentUser) {
    try {
      const token = await auth.currentUser.getIdToken();
      headers['Authorization'] = `Bearer ${token}`;
    } catch (err) {
      console.warn("Failed to retrieve ID token:", err);
    }
  }
  const response = await fetch(url, {
    ...options,
    headers: { ...headers, ...options.headers },
  });
  return await response.json();
}

function notifyDecision(run) {
  const d = run.decision?.decision;
  const score = fixed(run.risk?.composite_risk);
  if (d === 'BLOCK') showToast(`🚨 Transaction Blocked — Risk ${score}`, 'block');
  else if (d === 'OTP') showToast(`⚠ OTP Required — Risk ${score}`, 'otp');
  else if (d === 'ALLOW') showToast(`✓ Transaction Allowed — Risk ${score}`, 'allow');
}

function bindInputEffects() {
  const form = byId('txn-form');
  if (!form) return;
  form.querySelectorAll('input, select').forEach((el) => {
    el.addEventListener('focus', () => el.closest('label')?.classList.add('focused'));
    el.addEventListener('blur', () => el.closest('label')?.classList.remove('focused'));
  });
  form.querySelectorAll('.risk-input input').forEach((el) => {
    el.addEventListener('input', updateRiskGauge);
  });
  updateRiskGauge();
}

function bindKeyboardShortcuts() {
  document.addEventListener('keydown', (e) => {
    if (e.target.matches('input, textarea, select')) return;
    if (e.key === 'p' || e.key === 'P') {
      e.preventDefault();
      byId('txn-form')?.requestSubmit();
    } else if (e.key === 'r' || e.key === 'R') {
      e.preventDefault();
      byId('run-poc')?.click();
    } else if (e.key === 's' || e.key === 'S') {
      e.preventDefault();
      byId('replay-stream')?.click();
    }
  });
}

async function init() {
  initCinematicShell();
  bindInputEffects();
  bindKeyboardShortcuts();

  renderSummary(await fetchJson('/api/dashboard/summary'));
  renderGraphOverview(await fetchJson('/api/graph/overview'));

  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const token = auth.currentUser ? await auth.currentUser.getIdToken() : '';
  const socket = new WebSocket(`${protocol}://${window.location.host}/ws/dashboard?token=${encodeURIComponent(token)}`);
  socket.addEventListener('message', (event) => {
    const message = JSON.parse(event.data);
    if (message.type === 'snapshot') {
      renderSummary(message.payload);
    } else if (message.type === 'transaction_processed') {
      const run = {
        transaction: message.payload.transaction,
        signals: message.payload.signals,
        risk: message.payload.risk,
        decision: message.payload.decision,
        compliance: message.payload.compliance,
      };
      state.recentRuns.push(run);
      state.recentRuns = state.recentRuns.slice(-40);
      renderSummary({
        counts: {
          ALLOW: state.recentRuns.filter((item) => item.decision.decision === 'ALLOW').length,
          OTP: state.recentRuns.filter((item) => item.decision.decision === 'OTP').length,
          BLOCK: state.recentRuns.filter((item) => item.decision.decision === 'BLOCK').length,
        },
        recent_total: state.recentRuns.length,
        avg_risk_score: state.recentRuns.reduce((sum, item) => sum + item.risk.composite_risk, 0) / Math.max(state.recentRuns.length, 1),
        latest: run,
        recent_runs: state.recentRuns,
      });
      notifyDecision(run);
    }
  });

  byId('txn-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const result = await fetchJson('/api/transactions/process', {
      method: 'POST',
      body: JSON.stringify(readTransactionForm()),
    });
    renderLatest({
      transaction: result.transaction,
      signals: result.signals,
      risk: result.risk,
      decision: result.decision,
      compliance: result.compliance,
    });
    notifyDecision({ risk: result.risk, decision: result.decision });
  });

  byId('run-poc').addEventListener('click', async () => {
    const result = await fetchJson('/api/transactions/poc', { method: 'POST' });
    renderLatest(result.network_result);
    notifyDecision(result.network_result);
  });

  const replayBtn = byId('replay-stream');
  replayBtn.addEventListener('click', async () => {
    const spinner = replayBtn.querySelector('.spinner');
    spinner.hidden = false;
    replayBtn.classList.add('is-loading');
    replayBtn.disabled = true;
    try {
      await fetchJson('/api/transactions/replay', {
        method: 'POST',
        body: JSON.stringify({ limit: 20 }),
      });
    } finally {
      spinner.hidden = true;
      replayBtn.classList.remove('is-loading');
      replayBtn.disabled = false;
    }
  });
}

onAuthStateChanged(auth, (user) => {
  if (!user) {
    window.location.href = '/';
  } else {
    // Update navbar user profile badge
    const navProfile = byId('nav-user-profile');
    const navEmail = byId('nav-user-email');
    const navAvatar = byId('nav-avatar');
    const logoutBtn = byId('logout-btn');
    if (navProfile) navProfile.style.display = 'flex';
    if (navEmail) navEmail.textContent = user.email || user.uid.substring(0, 8);
    if (navAvatar) navAvatar.textContent = (user.email ? user.email[0] : 'U').toUpperCase();
    if (logoutBtn) {
      logoutBtn.style.display = 'inline-flex';
      logoutBtn.onclick = async () => {
        const { signOut } = await import('./auth.js');
        await signOut(auth);
      };
    }

    // Update welcome banner
    const welcomeBanner = byId('welcome-banner');
    const welcomeChar = byId('welcome-avatar-char');
    const welcomeUser = byId('welcome-user-text');
    if (welcomeBanner) welcomeBanner.style.display = 'flex';
    if (welcomeChar) welcomeChar.textContent = (user.email ? user.email[0] : 'U').toUpperCase();
    if (welcomeUser) {
      const username = user.email ? user.email.split('@')[0] : 'Operator';
      welcomeUser.innerHTML = `Welcome back, <span style="color: var(--cyan); text-shadow: var(--glow-cyan);">${username}</span>`;
    }

    init();
  }
});
