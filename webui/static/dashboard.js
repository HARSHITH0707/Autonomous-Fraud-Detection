const state = {
  recentRuns: [],
  latest: null,
};

function byId(id) {
  return document.getElementById(id);
}

function fixed(value, digits = 4) {
  return Number(value || 0).toFixed(digits);
}

function bannerClass(decision) {
  if (decision === "BLOCK") return "block";
  if (decision === "OTP") return "otp";
  if (decision === "ALLOW") return "allow";
  return "neutral";
}

function readTransactionForm() {
  const form = byId("txn-form");
  const data = new FormData(form);
  return {
    transaction_id: data.get("transaction_id"),
    source: "web",
    channel: data.get("channel"),
    sender_account: data.get("sender_account"),
    receiver_account: data.get("receiver_account"),
    amount: Number(data.get("amount")),
    currency: "INR",
    transaction_type: String(data.get("channel")).toUpperCase(),
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
    recent_amount_5m: Number(data.get("recent_amount_5m")),
    account_tenure_days: 420,
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
}

function renderLatest(run) {
  state.latest = run;
  const decision = run.decision.decision;
  const banner = byId("decision-banner");
  banner.className = `decision-banner ${bannerClass(decision)}`;
  banner.querySelector(".decision-label").textContent = `${decision} Decision`;
  banner.querySelector(".decision-score").textContent = fixed(run.risk.composite_risk);

  const reasons = byId("decision-reasons");
  reasons.innerHTML = "";
  (run.risk.explanation || ["No escalations"]).forEach((reason) => {
    const item = document.createElement("div");
    item.className = "reason-pill";
    item.textContent = reason;
    reasons.appendChild(item);
  });

  const cards = byId("agent-cards");
  cards.innerHTML = "";
  Object.values(run.signals).forEach((signal) => {
    const flags = (signal.flags || [])
      .map((flag) => `<span class="flag">${flag}</span>`)
      .join("");
    const card = document.createElement("article");
    card.className = "agent-card";
    card.innerHTML = `
      <span class="agent-name">${signal.agent_name.replaceAll("_", " ")}</span>
      <div class="agent-score-row">
        <strong class="agent-score">${fixed(signal.score)}</strong>
        <span class="agent-severity">${signal.severity}</span>
      </div>
      <div class="bar"><div class="bar-fill" style="width:${Math.min(signal.score * 100, 100)}%"></div></div>
      <div class="agent-flags">${flags || '<span class="flag">No flags</span>'}</div>
    `;
    cards.appendChild(card);
  });
}



function renderGraphOverview(graph) {
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

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  return await response.json();
}

async function init() {
  renderSummary(await fetchJson("/api/dashboard/summary"));
  renderGraphOverview(await fetchJson("/api/graph/overview"));

  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${window.location.host}/ws/dashboard`);
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "snapshot") {
      renderSummary(message.payload);
    } else if (message.type === "transaction_processed") {
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
          ALLOW: state.recentRuns.filter((item) => item.decision.decision === "ALLOW").length,
          OTP: state.recentRuns.filter((item) => item.decision.decision === "OTP").length,
          BLOCK: state.recentRuns.filter((item) => item.decision.decision === "BLOCK").length,
        },
        recent_total: state.recentRuns.length,
        avg_risk_score: state.recentRuns.reduce((sum, item) => sum + item.risk.composite_risk, 0) / Math.max(state.recentRuns.length, 1),
        latest: run,
        recent_runs: state.recentRuns,
      });
    }
  });

  byId("txn-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const result = await fetchJson("/api/transactions/process", {
      method: "POST",
      body: JSON.stringify(readTransactionForm()),
    });
    renderLatest({
      transaction: result.transaction,
      signals: result.signals,
      risk: result.risk,
      decision: result.decision,
      compliance: result.compliance,
    });
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

import { auth, onAuthStateChanged } from './auth.js';

onAuthStateChanged(auth, (user) => {
  if (!user) {
    window.location.href = "/";
  } else {
    init();
  }
});
