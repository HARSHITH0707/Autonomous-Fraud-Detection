/** Shared cinematic UI utilities for Fraud Shield Console */
export const FX = {
  metricHistory: { recentTotal: [], avgRisk: [] },
  agentSparkHistory: {},
};

const DECISION_COLORS = {
  ALLOW: '#39ff14',
  OTP: '#ffb800',
  BLOCK: '#ff2d55',
  neutral: '#00f5ff',
};

export function decisionColor(decision) {
  return DECISION_COLORS[decision] || DECISION_COLORS.neutral;
}

export function pushMetricHistory(key, value, max = 10) {
  const arr = FX.metricHistory[key] || (FX.metricHistory[key] = []);
  arr.push(Number(value) || 0);
  if (arr.length > max) arr.shift();
  return arr;
}

export function pushAgentScore(agentName, score, max = 10) {
  const key = agentName || 'unknown';
  const arr = FX.agentSparkHistory[key] || (FX.agentSparkHistory[key] = []);
  arr.push(Number(score) || 0);
  if (arr.length > max) arr.shift();
  return arr;
}

export function createSparklineSVG(values, color = '#00f5ff', w = 120, h = 28) {
  const data = values?.length ? values : [0];
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const pts = data.map((v, i) => {
    const x = (i / Math.max(data.length - 1, 1)) * w;
    const y = h - ((v - min) / range) * (h - 4) - 2;
    return `${x},${y}`;
  }).join(' ');
  return `<svg class="sparkline" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true">
    <polyline fill="none" stroke="${color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" points="${pts}"/>
  </svg>`;
}

export function animateOdometer(el, target, duration = 600) {
  if (!el) return;
  const end = Math.round(Number(target) || 0);
  const start = Number(el.dataset.value) || 0;
  if (start === end) {
    el.textContent = String(end);
    el.dataset.value = String(end);
    return;
  }
  const t0 = performance.now();
  const tick = (now) => {
    const p = Math.min((now - t0) / duration, 1);
    const eased = 1 - Math.pow(1 - p, 3);
    const val = Math.round(start + (end - start) * eased);
    el.textContent = String(val);
    if (p < 1) requestAnimationFrame(tick);
    else el.dataset.value = String(end);
  };
  requestAnimationFrame(tick);
}

export function estimateClientRisk(amount, geoVelocity, recentTxn) {
  const amt = Math.min(Number(amount) || 0, 500000) / 500000;
  const geo = Math.min(Number(geoVelocity) || 0, 5000) / 5000;
  const vel = Math.min(Number(recentTxn) || 0, 20) / 20;
  return Math.min(1, amt * 0.35 + geo * 0.4 + vel * 0.25);
}

export function riskHue(risk) {
  if (risk < 0.45) return '#39ff14';
  if (risk < 0.7) return '#ffb800';
  return '#ff2d55';
}

export function initCinematicShell() {
  initParticles();
  initThemeToggle();
  initPanelScans();
  ensureToastStack();
}

function ensureToastStack() {
  if (document.getElementById('toast-stack')) return;
  const stack = document.createElement('div');
  stack.id = 'toast-stack';
  stack.className = 'toast-stack';
  stack.setAttribute('aria-live', 'polite');
  document.body.appendChild(stack);
}

export function showToast(message, type = 'neutral', duration = 4000) {
  ensureToastStack();
  const stack = document.getElementById('toast-stack');
  const toast = document.createElement('div');
  toast.className = `toast toast-${type.toLowerCase()}`;
  toast.textContent = message;
  stack.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add('toast-visible'));
  setTimeout(() => {
    toast.classList.remove('toast-visible');
    setTimeout(() => toast.remove(), 320);
  }, duration);
}

export function initThemeToggle() {
  const btn = document.getElementById('theme-toggle');
  if (!btn) return;
  const saved = localStorage.getItem('fraud-shield-theme') || 'dark';
  document.documentElement.setAttribute('data-theme', saved);
  btn.setAttribute('aria-pressed', saved === 'light' ? 'true' : 'false');
  btn.textContent = saved === 'light' ? '◐ Dark' : '◑ Light';
  btn.addEventListener('click', () => {
    const next = document.documentElement.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('fraud-shield-theme', next);
    btn.setAttribute('aria-pressed', next === 'light' ? 'true' : 'false');
    btn.textContent = next === 'light' ? '◐ Dark' : '◑ Light';
  });
}

export function initPanelScans() {
  document.querySelectorAll('.panel.scan-panel').forEach((panel, i) => {
    panel.style.setProperty('--scan-delay', `${i * 0.12}s`);
    panel.classList.add('panel-mounted');
  });
}

export function initParticles() {
  const canvas = document.getElementById('particle-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  let w = 0;
  let h = 0;
  const dots = [];
  const COUNT = 50;
  const LINK = 120;

  function resize() {
    w = canvas.width = window.innerWidth;
    h = canvas.height = window.innerHeight;
  }

  function seed() {
    dots.length = 0;
    for (let i = 0; i < COUNT; i += 1) {
      dots.push({
        x: Math.random() * w,
        y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.35,
        vy: (Math.random() - 0.5) * 0.35,
      });
    }
  }

  function frame() {
    ctx.clearRect(0, 0, w, h);
    const cyan = getComputedStyle(document.documentElement).getPropertyValue('--cyan').trim() || '#00f5ff';
    dots.forEach((d) => {
      d.x += d.vx;
      d.y += d.vy;
      if (d.x < 0 || d.x > w) d.vx *= -1;
      if (d.y < 0 || d.y > h) d.vy *= -1;
      ctx.beginPath();
      ctx.arc(d.x, d.y, 1.2, 0, Math.PI * 2);
      ctx.fillStyle = cyan;
      ctx.globalAlpha = 0.35;
      ctx.fill();
    });
    for (let i = 0; i < dots.length; i += 1) {
      for (let j = i + 1; j < dots.length; j += 1) {
        const dx = dots[i].x - dots[j].x;
        const dy = dots[i].y - dots[j].y;
        const dist = Math.hypot(dx, dy);
        if (dist < LINK) {
          ctx.beginPath();
          ctx.moveTo(dots[i].x, dots[i].y);
          ctx.lineTo(dots[j].x, dots[j].y);
          ctx.strokeStyle = cyan;
          ctx.globalAlpha = (1 - dist / LINK) * 0.12;
          ctx.lineWidth = 0.6;
          ctx.stroke();
        }
      }
    }
    ctx.globalAlpha = 1;
    requestAnimationFrame(frame);
  }

  resize();
  seed();
  window.addEventListener('resize', () => { resize(); seed(); });
  requestAnimationFrame(frame);
}

export function buildGraphFromApi(graph) {
  const nodes = new Map();
  const links = [];

  function addNode(id, type = 'normal', volume = 0) {
    if (!id) return;
    const existing = nodes.get(id);
    if (existing) {
      existing.volume += volume;
      if (type === 'hub') existing.type = 'hub';
      else if (type === 'ring' && existing.type !== 'hub') existing.type = 'ring';
    } else {
      nodes.set(id, { id, type, volume });
    }
  }

  (graph.rings || []).forEach((ring) => {
    const members = ring.members || [];
    members.forEach((m) => addNode(m, 'ring', ring.total / Math.max(members.length, 1)));
    for (let i = 0; i < members.length; i += 1) {
      links.push({ source: members[i], target: members[(i + 1) % members.length] });
    }
  });

  (graph.chains || []).forEach((chain) => {
    const path = chain.chain || [];
    path.forEach((n) => addNode(n, 'ring', (chain.amounts || []).reduce((a, b) => a + b, 0) / Math.max(path.length, 1)));
    for (let i = 0; i < path.length - 1; i += 1) {
      links.push({ source: path[i], target: path[i + 1] });
    }
  });

  (graph.hubs || []).forEach((hub) => {
    addNode(hub.hub, 'hub', hub.total || 0);
    (hub.top_senders || []).forEach((s) => {
      addNode(s, 'normal', 0);
      links.push({ source: s, target: hub.hub });
    });
  });

  if (!nodes.size) {
    ['ACC-PRIMARY', 'ACC-MERCHANT-001', 'ACC-MULE-01'].forEach((id) => addNode(id, 'normal', 1000));
    links.push({ source: 'ACC-PRIMARY', target: 'ACC-MERCHANT-001' });
  }

  return {
    nodes: [...nodes.values()],
    links,
  };
}

export function renderD3Graph(container, graphData) {
  if (!window.d3 || !container) return () => {};
  container.innerHTML = '';
  const width = container.clientWidth || 400;
  const height = 220;
  const svg = window.d3.select(container).append('svg')
    .attr('width', width)
    .attr('height', height)
    .attr('viewBox', `0 0 ${width} ${height}`);

  const g = svg.append('g');
  const colorOf = (t) => (t === 'hub' ? '#ff2d55' : t === 'ring' ? '#ffb800' : '#00f5ff');

  const simulation = window.d3.forceSimulation(graphData.nodes)
    .force('link', window.d3.forceLink(graphData.links).id((d) => d.id).distance(55))
    .force('charge', window.d3.forceManyBody().strength(-140))
    .force('center', window.d3.forceCenter(width / 2, height / 2))
    .force('collision', window.d3.forceCollide(18));

  const link = g.append('g').selectAll('line')
    .data(graphData.links)
    .join('line')
    .attr('class', 'graph-edge');

  const node = g.append('g').selectAll('circle')
    .data(graphData.nodes)
    .join('circle')
    .attr('r', (d) => 6 + Math.min(d.volume / 50000, 8))
    .attr('fill', (d) => colorOf(d.type))
    .attr('class', 'graph-node')
    .call(window.d3.drag()
      .on('start', (event, d) => {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
      })
      .on('drag', (event, d) => {
        d.fx = event.x;
        d.fy = event.y;
      })
      .on('end', (event, d) => {
        if (!event.active) simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
      }));

  const tip = document.createElement('div');
  tip.className = 'graph-tooltip';
  tip.hidden = true;
  container.appendChild(tip);

  node
    .on('mouseenter', (event, d) => {
      tip.hidden = false;
      tip.textContent = `${d.id} · vol ${Math.round(d.volume).toLocaleString()}`;
      tip.style.left = `${event.offsetX + 12}px`;
      tip.style.top = `${event.offsetY + 12}px`;
    })
    .on('mousemove', (event) => {
      tip.style.left = `${event.offsetX + 12}px`;
      tip.style.top = `${event.offsetY + 12}px`;
    })
    .on('mouseleave', () => { tip.hidden = true; });

  simulation.on('tick', () => {
    link
      .attr('x1', (d) => d.source.x)
      .attr('y1', (d) => d.source.y)
      .attr('x2', (d) => d.target.x)
      .attr('y2', (d) => d.target.y);
    node.attr('cx', (d) => d.x).attr('cy', (d) => d.y);
  });

  return () => simulation.stop();
}
