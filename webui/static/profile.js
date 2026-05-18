import {
  auth,
  googleProvider,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signInWithPopup,
  signOut,
  onAuthStateChanged,
} from './auth.js';
import { initCinematicShell, showToast } from './dashboard-fx.js';

const state = {
  recentRuns: [],
  feedKnownIds: new Set(),
};

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

const emailInput = byId('email');
const passwordInput = byId('password');
const errorMsg = byId('auth-error');
const authSection = byId('auth-section');
const authContent = byId('authenticated-content');
const logoutBtn = byId('logout-btn');

function getValidatedEmail() {
  const rawEmail = emailInput?.value ?? '';
  const email = rawEmail.trim();
  if (emailInput && email !== rawEmail) emailInput.value = email;
  return { email };
}

function showEmailValidationError(email) {
  if (!email) {
    errorMsg.textContent = 'Please enter your email address.';
    return true;
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    errorMsg.textContent = 'Please enter a valid email address.';
    return true;
  }
  return false;
}

function formatAuthError(err) {
  if (err?.code === 'auth/unauthorized-domain') {
    const host = window.location.hostname;
    if (host === '0.0.0.0') {
      return '0.0.0.0 is a server bind address, not a browser URL. Open http://localhost:8000 instead.';
    }
    return `This site (${host}) is not authorized for Firebase sign-in. Add "${host}" in Firebase Console → Authentication → Settings → Authorized domains, or use http://localhost:${window.location.port || '8000'}.`;
  }
  return err?.message || String(err);
}

byId('login-btn').addEventListener('click', async () => {
  try {
    errorMsg.textContent = '';
    const form = byId('auth-form');
    if (form && !form.reportValidity()) return;
    const { email } = getValidatedEmail();
    if (showEmailValidationError(email)) return;
    await signInWithEmailAndPassword(auth, email, passwordInput.value);
  } catch (err) {
    errorMsg.textContent = err.message;
  }
});

byId('signup-btn').addEventListener('click', async () => {
  try {
    errorMsg.textContent = '';
    const form = byId('auth-form');
    if (form && !form.reportValidity()) return;
    const { email } = getValidatedEmail();
    if (showEmailValidationError(email)) return;
    await createUserWithEmailAndPassword(auth, email, passwordInput.value);
  } catch (err) {
    errorMsg.textContent = err.message;
  }
});

byId('google-login-btn').addEventListener('click', async () => {
  try {
    errorMsg.textContent = '';
    await signInWithPopup(auth, googleProvider);
  } catch (err) {
    if (err?.code === 'auth/popup-closed-by-user') return;
    errorMsg.textContent = formatAuthError(err);
  }
});

logoutBtn.addEventListener('click', async () => {
  await signOut(auth);
});

onAuthStateChanged(auth, (user) => {
  if (user) {
    authSection.style.display = 'none';
    authContent.style.display = 'block';
    logoutBtn.style.display = 'inline-flex';
    byId('user-email').textContent = user.email;
    byId('user-uid').textContent = user.uid;
    initLiveFeed();
    if (window.location.pathname === '/') {
      window.location.href = '/dashboard';
    }
  } else {
    authSection.style.display = 'block';
    authContent.style.display = 'none';
    logoutBtn.style.display = 'none';
    if (window.wsSocket) {
      window.wsSocket.close();
      window.wsSocket = null;
    }
  }
});

function heatColor(risk) {
  if (risk < 0.35) return '#1a2030';
  if (risk < 0.65) return '#ffb800';
  return '#ff2d55';
}

function renderHeatmap() {
  const grid = byId('risk-heatmap');
  if (!grid) return;
  const buckets = Array.from({ length: 7 * 24 }, () => ({ sum: 0, count: 0 }));

  state.recentRuns.forEach((run) => {
    const t = new Date(run.transaction?.event_time || Date.now());
    const day = (t.getDay() + 6) % 7;
    const hour = t.getHours();
    const idx = day * 24 + hour;
    buckets[idx].sum += run.risk?.composite_risk ?? 0;
    buckets[idx].count += 1;
  });

  grid.innerHTML = '';
  buckets.forEach((b) => {
    const cell = document.createElement('div');
    cell.className = 'heat-cell';
    const avg = b.count ? b.sum / b.count : 0;
    cell.style.background = heatColor(avg);
    cell.title = b.count ? `Avg risk ${fixed(avg)} (${b.count} txns)` : 'No activity';
    grid.appendChild(cell);
  });
}

function createFeedItem(run, isNew) {
  const item = document.createElement('article');
  const d = run.decision?.decision || 'ALLOW';
  item.className = `live-item ${bannerClass(d)}${isNew ? ' feed-new' : ''}`;
  item.dataset.txnId = run.transaction?.transaction_id || '';
  item.innerHTML = `
    <div class="live-row">
      <div>
        <strong>${run.transaction.transaction_id}</strong>
        <div class="live-meta">${run.transaction.sender_account} → ${run.transaction.receiver_account}</div>
      </div>
      <span class="decision-chip ${d}">${d}</span>
    </div>
    <div class="live-row">
      <div class="live-meta">${String(run.transaction.channel).toUpperCase()} · INR ${Number(run.transaction.amount).toLocaleString()}</div>
      <div class="live-meta">Risk ${fixed(run.risk.composite_risk)}</div>
    </div>
  `;
  return item;
}

function notifyFeedDecision(run) {
  const d = run.decision?.decision;
  const score = fixed(run.risk?.composite_risk);
  if (d === 'BLOCK') showToast(`🚨 Transaction Blocked — Risk ${score}`, 'block');
  else if (d === 'OTP') showToast(`⚠ OTP Required — Risk ${score}`, 'otp');
  else if (d === 'ALLOW') showToast(`✓ Transaction Allowed — Risk ${score}`, 'allow');
}

function renderFeed(options = {}) {
  const feed = byId('live-feed');
  const runs = [...state.recentRuns].reverse();
  const onlyNew = options.onlyNew;

  if (!onlyNew) {
    feed.innerHTML = '';
    state.feedKnownIds.clear();
    if (!runs.length) {
      feed.innerHTML = '<article class="live-item"><div class="live-meta">No transactions processed yet.</div></article>';
      renderHeatmap();
      return;
    }
    runs.forEach((run) => {
      const id = run.transaction?.transaction_id;
      state.feedKnownIds.add(id);
      feed.appendChild(createFeedItem(run, false));
    });
    renderHeatmap();
    return;
  }

  runs.forEach((run) => {
    const id = run.transaction?.transaction_id;
    if (state.feedKnownIds.has(id)) return;
    state.feedKnownIds.add(id);
    const item = createFeedItem(run, true);
    feed.prepend(item);
    notifyFeedDecision(run);
  });
  renderHeatmap();
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  return await response.json();
}

async function initLiveFeed() {
  if (window.wsSocket) return;
  initCinematicShell();

  const snapshot = await fetchJson('/api/dashboard/summary');
  state.recentRuns = snapshot.recent_runs || [];
  renderFeed();

  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const socket = new WebSocket(`${protocol}://${window.location.host}/ws/dashboard`);
  window.wsSocket = socket;

  socket.addEventListener('message', (event) => {
    const message = JSON.parse(event.data);
    if (message.type === 'snapshot') {
      state.recentRuns = message.payload.recent_runs || [];
      renderFeed();
    } else if (message.type === 'transaction_processed') {
      const run = message.payload;
      state.recentRuns.push(run);
      state.recentRuns = state.recentRuns.slice(-40);
      renderFeed({ onlyNew: true });
    }
  });
}

initCinematicShell();
