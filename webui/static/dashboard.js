import { initializeApp } from "https://www.gstatic.com/firebasejs/10.8.0/firebase-app.js";
import { getAuth, onAuthStateChanged, signOut } from "https://www.gstatic.com/firebasejs/10.8.0/firebase-auth.js";

// Firebase Config (Must match login.html)
const firebaseConfig = {
  apiKey: "AIzaSyClCYZnnlzZRZwcqYfurZT6Pa8tRSHfhUs",
  authDomain: "fraud-shield-663a9.firebaseapp.com",
  projectId: "fraud-shield-663a9",
  storageBucket: "fraud-shield-663a9.firebasestorage.app",
  messagingSenderId: "923454719714",
  appId: "1:923454719714:web:6a55b0155ca9eddabdc0bb"
};

let isDemoMode = firebaseConfig.apiKey === "YOUR_API_KEY" || localStorage.getItem("demo_auth") === "true";

let app, auth;
if (!isDemoMode) {
  try {
    app = initializeApp(firebaseConfig);
    auth = getAuth(app);
  } catch (err) {
    console.warn("Firebase initialization failed, falling back to Demo Mode:", err);
    isDemoMode = true;
  }
}

const state = {
  recentRuns: [],
  latest: null,
  userToken: null
};

// ... helper functions ...
function byId(id) { return document.getElementById(id); }
function fixed(value, digits = 4) { return Number(value || 0).toFixed(digits); }

function renderAlert(title, body) {
  const container = byId("alert-container");
  const alert = document.createElement("div");
  alert.className = "alert-card";
  alert.innerHTML = `
    <div>
      <span class="alert-title">🚨 ${title}</span>
      <span class="alert-body">${body}</span>
    </div>
    <button class="ghost small" onclick="this.parentElement.remove()">Dismiss</button>
  `;
  container.prepend(alert);
  setTimeout(() => alert.remove(), 8000);
}

function bannerClass(decision) {
  if (decision === "BLOCK") return "block";
  if (decision === "OTP") return "otp";
  if (decision === "ALLOW") return "allow";
  return "neutral";
}

function renderLatest(run) {
  if (!run) return;
  state.latest = run;
  const decision = run.decision?.decision || run.decision || "UNKNOWN";
  const banner = byId("decision-banner");
  banner.className = `decision-banner ${bannerClass(decision)}`;
  banner.querySelector(".decision-label").textContent = `${decision} Decision`;
  banner.querySelector(".decision-score").textContent = fixed(run.risk?.composite_risk || run.composite_risk || 0);

  const behaviourSignal = run.signals?.behaviour_analyser;
  if (behaviourSignal && behaviourSignal.flags?.includes("IMPOSSIBLE_TRAVEL")) {
    const velocity = behaviourSignal.evidence?.calculated_velocity_kmh || 0;
    renderAlert("CRITICAL FRAUD: Impossible Travel", `Velocity of ${fixed(velocity, 0)} km/h detected. Physically impossible travel between login points.`);
  }

  const reasons = byId("decision-reasons");
  reasons.innerHTML = "";
  (run.risk?.explanation || run.explanation || ["No escalations recorded"]).forEach((reason) => {
    const item = document.createElement("div");
    item.className = "reason-pill";
    item.textContent = reason;
    reasons.appendChild(item);
  });

  const cards = byId("agent-cards");
  cards.innerHTML = "";
  
  // Fallback to forensic_snapshot.component_scores if signals are missing (historical items)
  let signalData = run.signals;
  if (!signalData && run.forensic_snapshot?.component_scores) {
    signalData = {};
    Object.entries(run.forensic_snapshot.component_scores).forEach(([name, score]) => {
      signalData[name] = { agent_name: name, score: score, severity: score > 0.7 ? "HIGH" : "LOW", flags: [] };
    });
  }

  Object.values(signalData || {}).forEach((signal) => {
    const flags = (signal.flags || [])
      .map((flag) => `<span class="flag">${flag}</span>`)
      .join("");
    const card = document.createElement("article");
    card.className = "agent-card";
    card.innerHTML = `
      <span class="agent-name">${(signal.agent_name || "Agent").replaceAll("_", " ")}</span>
      <div class="agent-score-row">
        <strong class="agent-score">${fixed(signal.score)}</strong>
        <span class="agent-severity">${signal.severity || "N/A"}</span>
      </div>
      <div class="bar"><div class="bar-fill" style="width:${Math.min((signal.score || 0) * 100, 100)}%"></div></div>
      <div class="agent-flags">${flags || '<span class="flag">No flags</span>'}</div>
    `;
    cards.appendChild(card);
  });
}

async function fetchJson(url, options = {}) {
  const headers = { "Content-Type": "application/json" };
  if (state.userToken) {
    headers["Authorization"] = `Bearer ${state.userToken}`;
  }
  const response = await fetch(url, { ...options, headers });
  if (response.status === 401) {
    window.location.href = "/login";
  }
  return await response.json();
}

async function bootDashboard() {
  // Load initial state
  renderSummary(await fetchJson("/api/dashboard/summary"));
  try {
      renderGraphOverview(await fetchJson("/api/graph/overview"));
  } catch(e) { console.warn("Graph overview skipped", e); }

  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const wsUrl = `${protocol}://${window.location.host}/ws/dashboard${state.userToken ? `?token=${state.userToken}` : ""}`;
  const socket = new WebSocket(wsUrl);
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "snapshot") {
      renderSummary(message.payload);
    } else if (message.type === "transaction_processed") {
      state.recentRuns.unshift(message.payload);
      state.recentRuns = state.recentRuns.slice(0, 40);
      renderSummary({
        counts: {
          ALLOW: state.recentRuns.filter((item) => (item.decision.decision || item.decision) === "ALLOW").length,
          OTP: state.recentRuns.filter((item) => (item.decision.decision || item.decision) === "OTP").length,
          BLOCK: state.recentRuns.filter((item) => (item.decision.decision || item.decision) === "BLOCK").length,
        },
        recent_total: state.recentRuns.length,
        avg_risk_score: state.recentRuns.reduce((sum, item) => sum + (item.risk?.composite_risk || item.composite_risk), 0) / Math.max(state.recentRuns.length, 1),
        latest: message.payload,
        recent_runs: state.recentRuns,
      });
    }
  });

  byId("sign-out").addEventListener("click", () => {
    if (isDemoMode) {
      localStorage.removeItem("demo_auth");
      window.location.href = "/login";
    } else {
      signOut(auth).then(() => window.location.href = "/login");
    }
  });

  byId("txn-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const result = await fetchJson("/api/transactions/process", {
      method: "POST",
      body: JSON.stringify(readTransactionForm()),
    });
    renderLatest(result);
  });

  byId("run-poc").addEventListener("click", async () => {
    const result = await fetchJson("/api/transactions/poc", { method: "POST" });
    renderLatest(result.network_result);
  });

  byId("replay-stream").addEventListener("click", async () => {
    await fetchJson("/api/transactions/replay", {
      method: "POST",
      body: JSON.stringify({ limit: 20 }),
    });
  });
}

async function init() {
  if (isDemoMode) {
    if (!localStorage.getItem("demo_auth")) {
      window.location.href = "/login";
      return;
    }
    state.userToken = "demo-token";
    bootDashboard();
  } else {
    onAuthStateChanged(auth, async (user) => {
      if (!user) {
        window.location.href = "/login";
      } else {
        state.userToken = await user.getIdToken();
        bootDashboard();
      }
    });
  }
}

function readTransactionForm() {
  const form = byId("txn-form");
  const data = new FormData(form);
  return {
    transaction_id: data.get("transaction_id"),
    sender_account: data.get("sender_account"),
    receiver_account: data.get("receiver_account"),
    amount: Number(data.get("amount")),
    transaction_type: data.get("channel").toUpperCase(),
    device_id: data.get("device_id"),
    ip_address: data.get("ip_address"),
    login_country: data.get("login_country"),
    home_country: data.get("home_country"),
    device_mismatch: form.elements.device_mismatch.checked,
    geo_velocity_km: Number(data.get("geo_velocity_km")),
    new_beneficiary: form.elements.new_beneficiary.checked,
    beneficiary_age_days: Number(data.get("beneficiary_age_days")),
    login_velocity_10m: Number(data.get("login_velocity_10m")),
    recent_txn_count_5m: Number(data.get("recent_txn_count_5m")),
  };
}

function renderSummary(snapshot) {
  byId("recent-total").textContent = snapshot.recent_total ?? 0;
  byId("avg-risk").textContent = fixed(snapshot.avg_risk_score ?? 0);
  byId("count-allow").textContent = snapshot.counts?.ALLOW ?? 0;
  byId("count-otp").textContent = snapshot.counts?.OTP ?? 0;
  byId("count-block").textContent = snapshot.counts?.BLOCK ?? 0;
  state.recentRuns = snapshot.recent_runs ?? [];
  if (snapshot.latest) {
    renderLatest(snapshot.latest);
  }
  renderFeed();
}

function renderFeed() {
  const feed = byId("live-feed");
  const runs = state.recentRuns;
  feed.innerHTML = "";
  if (!runs.length) {
    feed.innerHTML = `<div class="live-item"><div class="live-meta">No transactions processed yet.</div></div>`;
    return;
  }
  runs.forEach((run) => {
    const item = document.createElement("article");
    item.className = "live-item";
    const decision = run.decision?.decision || run.decision || "UNKNOWN";
    const transaction = run.transaction || { transaction_id: run.transaction_id || "TXN-???", sender_account: "Account Info N/A", receiver_account: "N/A", transaction_type: "N/A", amount: 0 };
    const behaviourEvidence = run.signals?.behaviour_analyser?.evidence || {};
    const displayName = behaviourEvidence.display_name || null;
    const loginCount = behaviourEvidence.login_count ?? null;

    const senderLabel = displayName
      ? `<strong class="user-name">${displayName}</strong><span class="live-meta">${transaction.sender_account}</span>`
      : `<strong>${transaction.sender_account}</strong>`;

    const loginBadge = loginCount !== null
      ? `<span class="login-badge" title="Total logins for this account">🔑 ${loginCount} login${loginCount !== 1 ? "s" : ""}</span>`
      : "";

    item.innerHTML = `
      <div class="live-row">
        <div class="live-user">
          ${senderLabel}
        </div>
        <span class="decision-chip ${decision}">${decision}</span>
      </div>
      <div class="live-row">
        <div class="live-meta">→ ${transaction.receiver_account}</div>
        ${loginBadge}
      </div>
      <div class="live-row">
        <div class="live-meta">${transaction.transaction_type} · INR ${Number(transaction.amount).toLocaleString()}</div>
        <div class="live-meta">Risk ${fixed(run.risk?.composite_risk || run.composite_risk || 0)}</div>
      </div>
    `;
    item.addEventListener("click", () => renderLatest(run));
    feed.appendChild(item);
  });
}

function renderGraphOverview(graph) {
  if (!graph) return;
  const container = byId("graph-overview");
  container.innerHTML = "";
  const sections = [
    ["Fraud Rings", graph.rings, (row) => `${row.members?.join(" → ") || "No members"} · total ${Number(row.total || 0).toLocaleString()}`],
    ["Mule Chains", graph.chains, (row) => `${row.chain?.join(" → ") || "No chain"} · hops ${row.hops}`],
    ["Coordinated Hubs", graph.hubs, (row) => `${row.hub} · ${row.senders} senders · total ${Number(row.total || 0).toLocaleString()}`],
    ["Shared Devices", graph.shared_devices, (row) => `${row.device} · ${row.cnt} linked accounts`],
  ];
  sections.forEach(([title, rows, formatter]) => {
    const card = document.createElement("article");
    card.className = "graph-card";
    const top = rows?.[0];
    card.innerHTML = `
      <span class="graph-title">${title}</span>
      <div class="graph-body">${top ? formatter(top) : "No linked fraud structures available yet."}</div>
    `;
    container.appendChild(card);
  });
}

init();
