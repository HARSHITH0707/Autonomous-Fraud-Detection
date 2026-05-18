import { auth, googleProvider, signInWithEmailAndPassword, createUserWithEmailAndPassword, signInWithPopup, signOut, onAuthStateChanged } from './auth.js';

const state = {
  recentRuns: [],
};

function byId(id) {
  return document.getElementById(id);
}

function fixed(value, digits = 4) {
  return Number(value || 0).toFixed(digits);
}

// ---- Auth Logic ----
const emailInput = byId('email');
const passwordInput = byId('password');
const errorMsg = byId('auth-error');
const authSection = byId('auth-section');
const authContent = byId('authenticated-content');
const logoutBtn = byId('logout-btn');

function getValidatedEmail() {
  const rawEmail = emailInput?.value ?? '';
  const email = rawEmail.trim();
  if (emailInput && email !== rawEmail) {
    emailInput.value = email;
  }
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

byId('login-btn').addEventListener('click', async () => {
  try {
    errorMsg.textContent = '';
    const form = byId('auth-form');
    if (form && !form.reportValidity()) {
      return;
    }
    const { email } = getValidatedEmail();
    if (showEmailValidationError(email)) {
      return;
    }
    await signInWithEmailAndPassword(auth, email, passwordInput.value);
  } catch (err) {
    errorMsg.textContent = err.message;
  }
});

byId('signup-btn').addEventListener('click', async () => {
  try {
    errorMsg.textContent = '';
    const form = byId('auth-form');
    if (form && !form.reportValidity()) {
      return;
    }
    const { email } = getValidatedEmail();
    if (showEmailValidationError(email)) {
      return;
    }
    await createUserWithEmailAndPassword(auth, email, passwordInput.value);
  } catch (err) {
    errorMsg.textContent = err.message;
  }
});

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

byId('google-login-btn').addEventListener('click', async () => {
  try {
    errorMsg.textContent = '';
    await signInWithPopup(auth, googleProvider);
  } catch (err) {
    if (err?.code === 'auth/popup-closed-by-user') {
      return;
    }
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
    logoutBtn.style.display = 'block';
    byId('user-email').textContent = user.email;
    byId('user-uid').textContent = user.uid;
    initLiveFeed();

    // Redirect to dashboard if logged in on the root login page
    if (window.location.pathname === "/") {
      window.location.href = "/dashboard";
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


// ---- Live Feed Logic ----
function renderFeed() {
  const feed = byId("live-feed");
  const runs = [...state.recentRuns].reverse();
  feed.innerHTML = "";
  if (!runs.length) {
    feed.innerHTML = `<div class="live-item"><div class="live-meta">No transactions processed yet.</div></div>`;
    return;
  }
  runs.forEach((run) => {
    const item = document.createElement("article");
    item.className = "live-item";
    item.innerHTML = `
      <div class="live-row">
        <div>
          <strong>${run.transaction.transaction_id}</strong>
          <div class="live-meta">${run.transaction.sender_account} → ${run.transaction.receiver_account}</div>
        </div>
        <span class="decision-chip ${run.decision.decision}">${run.decision.decision}</span>
      </div>
      <div class="live-row">
        <div class="live-meta">${run.transaction.channel.toUpperCase()} · INR ${Number(run.transaction.amount).toLocaleString()}</div>
        <div class="live-meta">Risk ${fixed(run.risk.composite_risk)}</div>
      </div>
    `;
    feed.appendChild(item);
  });
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  return await response.json();
}

async function initLiveFeed() {
  if (window.wsSocket) return; // already connected

  const snapshot = await fetchJson("/api/dashboard/summary");
  state.recentRuns = snapshot.recent_runs || [];
  renderFeed();

  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${window.location.host}/ws/dashboard`);
  window.wsSocket = socket;

  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "snapshot") {
      state.recentRuns = message.payload.recent_runs || [];
      renderFeed();
    } else if (message.type === "transaction_processed") {
      const run = message.payload;
      state.recentRuns.push(run);
      state.recentRuns = state.recentRuns.slice(-40);
      renderFeed();
    }
  });
}
