import { PRODUCTS, TOPOLOGY_ROUTES, QUICKSTART_TABS } from './data.js';
import { createHeroScene } from './scene.js';
import { initTerminal } from './terminal.js';
import { initLowerBackground } from './background.js';

const heroEl = document.getElementById('hero');
const canvas = document.getElementById('scene');
const loaderEl = document.getElementById('loader');

const sceneCtrl = createHeroScene({
  canvas,
  heroEl,
  loaderEl
});

// ============================================================================
// 2. Render 4 Core Ecosystem Product Cards (2x2 Grid, Cached Tilt on Fine Pointer)
// ============================================================================
function renderEcosystemCards() {
  const grid = document.getElementById('ecosystem-grid');
  if (!grid) return;

  grid.innerHTML = PRODUCTS.map(
    (s) => `
    <article class="project-card" id="card-${s.id}" style="--card-accent: ${s.accent}">
      <div>
        <div class="project-card-top">
          <span class="project-index">${s.count}</span>
          <span class="project-badge">${s.category} • ${s.version}</span>
        </div>
        <h3 class="project-title">${s.title}</h3>
        <p class="project-summary">${s.summary}</p>
        <div class="project-metrics">
          ${s.metrics
            .map(
              (m) => `
            <div class="metric-box">
              <span class="metric-label">${m.label}</span>
              <span class="metric-value">${m.value}</span>
            </div>
          `
            )
            .join('')}
        </div>
        <ul class="project-features">
          ${s.features.map((f) => `<li>${f}</li>`).join('')}
        </ul>
      </div>
      <div class="project-footer">
        <span class="project-repo">${s.repoPath}</span>
      </div>
    </article>
  `
  ).join('');

  const canTilt =
    window.matchMedia && window.matchMedia('(hover: hover) and (pointer: fine)').matches;
  if (!canTilt) return;

  const cards = grid.querySelectorAll('.project-card');
  cards.forEach((card) => {
    let rect = null;
    card.addEventListener('pointerenter', () => {
      rect = card.getBoundingClientRect();
    });
    card.addEventListener('pointermove', (e) => {
      if (!rect) rect = card.getBoundingClientRect();
      const x = (e.clientX - rect.left) / Math.max(1, rect.width) - 0.5;
      const y = (e.clientY - rect.top) / Math.max(1, rect.height) - 0.5;
      card.style.setProperty('--rx', `${(-y * 4.5).toFixed(2)}deg`);
      card.style.setProperty('--ry', `${(x * 4.5).toFixed(2)}deg`);
    });
    card.addEventListener('pointerleave', () => {
      rect = null;
      card.style.setProperty('--rx', '0deg');
      card.style.setProperty('--ry', '0deg');
    });
  });
}

// ============================================================================
// 3. Interactive Topology Route Switcher + Zero-Lag GPU Draggable HTML Nodes
// ============================================================================
function initTopology() {
  const routeListEl = document.getElementById('route-list');
  const descEl = document.getElementById('topology-desc');
  const packetEl = document.getElementById('topology-packet');
  const stageEl = document.getElementById('topology-stage');
  const canvasBox = document.getElementById('topology-canvas');
  const svgEl = document.getElementById('topology-svg');
  const resetBtn = document.getElementById('topo-reset-btn');

  if (!routeListEl || !canvasBox || !svgEl) return;

  // Normalized coordinates (0..1 within free drag bounds of canvasBox)
  const DESKTOP_NORM = {
    ai: { nx: 0.04, ny: 0.06 },
    linux: { nx: 0.18, ny: 0.44 },
    phone: { nx: 0.03, ny: 0.86 },
    rpi: { nx: 0.50, ny: 0.80 },
    windows: { nx: 0.96, ny: 0.44 }
  };

  const COMPACT_NORM = {
    ai: { nx: 0.04, ny: 0.02 },
    linux: { nx: 0.96, ny: 0.24 },
    rpi: { nx: 0.04, ny: 0.49 },
    windows: { nx: 0.96, ny: 0.74 },
    phone: { nx: 0.04, ny: 0.98 }
  };

  const LINKS = [
    { id: 'link-lan', from: 'linux', to: 'windows', arch: -44 },
    { id: 'link-mcp', from: 'ai', to: 'linux', arch: 0 },
    { id: 'link-bastion', from: 'ai', to: 'rpi', arch: -24 },
    { id: 'link-wifi', from: 'phone', to: 'rpi', arch: 14 },
    { id: 'link-eth-win', from: 'rpi', to: 'windows', arch: 18 },
    { id: 'link-eth-lin', from: 'rpi', to: 'linux', arch: 14 }
  ];

  const nodes = {};
  const PAD = 10;
  let canvasW = 1;
  let canvasH = 1;
  let hasUserDragged = false;
  let topZ = 5;
  let linkRafPending = false;

  const pathCache = {};
  for (const link of LINKS) {
    pathCache[link.id] = document.getElementById(link.id);
  }

  function getDefaultNorms() {
    return canvasW < 560 ? COMPACT_NORM : DESKTOP_NORM;
  }

  // Register all HTML node elements & measure them cleanly
  canvasBox.querySelectorAll('.topo-node').forEach((el) => {
    const id = el.dataset.node;
    nodes[id] = {
      el,
      nx: DESKTOP_NORM[id]?.nx ?? 0.5,
      ny: DESKTOP_NORM[id]?.ny ?? 0.5,
      x: 0,
      y: 0,
      w: el.offsetWidth || 160,
      h: el.offsetHeight || 60
    };
  });

  function updateLinksImmediate() {
    linkRafPending = false;
    for (const link of LINKS) {
      const pathEl = pathCache[link.id];
      const a = nodes[link.from];
      const b = nodes[link.to];
      if (!pathEl || !a || !b) continue;

      const ax = a.x + a.w * 0.5;
      const ay = a.y + a.h * 0.5;
      const bx = b.x + b.w * 0.5;
      const by = b.y + b.h * 0.5;
      const mx = (ax + bx) * 0.5;
      const my = (ay + by) * 0.5 + link.arch;

      pathEl.setAttribute(
        'd',
        `M ${ax.toFixed(1)} ${ay.toFixed(1)} Q ${mx.toFixed(1)} ${my.toFixed(1)}, ${bx.toFixed(1)} ${by.toFixed(1)}`
      );
    }
  }

  function scheduleLinksUpdate() {
    if (!linkRafPending) {
      linkRafPending = true;
      requestAnimationFrame(updateLinksImmediate);
    }
  }

  function applyPositionsFromNorms() {
    for (const n of Object.values(nodes)) {
      const maxX = Math.max(PAD, canvasW - n.w - PAD);
      const maxY = Math.max(PAD, canvasH - n.h - PAD);
      n.x = PAD + n.nx * (maxX - PAD);
      n.y = PAD + n.ny * (maxY - PAD);
      n.el.style.transform = `translate3d(${n.x.toFixed(1)}px, ${n.y.toFixed(1)}px, 0)`;
    }
    updateLinksImmediate();
  }

  function measureAndSync({ resetToDefault = false } = {}) {
    canvasW = Math.max(240, canvasBox.clientWidth);
    canvasH = Math.max(220, canvasBox.clientHeight);
    svgEl.setAttribute('viewBox', `0 0 ${canvasW} ${canvasH}`);

    for (const n of Object.values(nodes)) {
      n.w = n.el.offsetWidth || 150;
      n.h = n.el.offsetHeight || 56;
    }

    if (resetToDefault || !hasUserDragged) {
      const defaults = getDefaultNorms();
      for (const [id, n] of Object.entries(nodes)) {
        n.nx = defaults[id].nx;
        n.ny = defaults[id].ny;
      }
    }

    applyPositionsFromNorms();
  }

  // Zero-lag Pointer Dragging on HTML .topo-node elements
  for (const [id, n] of Object.entries(nodes)) {
    const el = n.el;
    let dragging = false;
    let pointerId = null;
    let startClientX = 0;
    let startClientY = 0;
    let origX = 0;
    let origY = 0;
    let maxX = 0;
    let maxY = 0;

    el.addEventListener('pointerdown', (e) => {
      if (e.button !== undefined && e.button !== 0 && e.pointerType === 'mouse') return;
      e.preventDefault();
      e.stopPropagation();

      dragging = true;
      pointerId = e.pointerId;
      hasUserDragged = true;

      // Refresh container & node sizes once at drag start (never inside pointermove)
      canvasW = Math.max(240, canvasBox.clientWidth);
      canvasH = Math.max(220, canvasBox.clientHeight);
      n.w = el.offsetWidth;
      n.h = el.offsetHeight;
      maxX = Math.max(PAD, canvasW - n.w - PAD);
      maxY = Math.max(PAD, canvasH - n.h - PAD);

      startClientX = e.clientX;
      startClientY = e.clientY;
      origX = n.x;
      origY = n.y;

      // Raise via CSS z-index (never detach/append DOM nodes while dragging!)
      el.style.zIndex = String(++topZ);
      el.classList.add('dragging');

      try {
        el.setPointerCapture(e.pointerId);
      } catch {
        // Ignore if unavailable
      }
    });

    el.addEventListener('pointermove', (e) => {
      if (!dragging || e.pointerId !== pointerId) return;

      const dx = e.clientX - startClientX;
      const dy = e.clientY - startClientY;

      n.x = Math.max(PAD, Math.min(maxX, origX + dx));
      n.y = Math.max(PAD, Math.min(maxY, origY + dy));

      const spanX = Math.max(1, maxX - PAD);
      const spanY = Math.max(1, maxY - PAD);
      n.nx = (n.x - PAD) / spanX;
      n.ny = (n.y - PAD) / spanY;

      el.style.transform = `translate3d(${n.x.toFixed(1)}px, ${n.y.toFixed(1)}px, 0)`;
      scheduleLinksUpdate();
    });

    const endDrag = (e) => {
      if (!dragging || (e.pointerId !== undefined && e.pointerId !== pointerId)) return;
      dragging = false;
      el.classList.remove('dragging');
      try {
        if (pointerId !== null && el.hasPointerCapture(pointerId)) {
          el.releasePointerCapture(pointerId);
        }
      } catch {
        // Ignore
      }
      pointerId = null;
      updateLinksImmediate();
    };

    el.addEventListener('pointerup', endDrag);
    el.addEventListener('pointercancel', endDrag);
    el.addEventListener('lostpointercapture', endDrag);
  }

  if (resetBtn) {
    resetBtn.addEventListener('click', () => {
      hasUserDragged = false;
      measureAndSync({ resetToDefault: true });
    });
  }

  if (typeof ResizeObserver !== 'undefined') {
    const ro = new ResizeObserver(() => measureAndSync());
    ro.observe(canvasBox);
  } else {
    window.addEventListener('resize', () => measureAndSync());
  }

  // Render route buttons
  routeListEl.innerHTML = TOPOLOGY_ROUTES.map(
    (r, idx) => `
    <button type="button" class="route-btn ${idx === 0 ? 'active' : ''}" data-route-idx="${idx}" style="--route-accent: ${r.accent}">
      <div class="route-btn-title">${r.title}</div>
      <div class="route-btn-proto">${r.protocol}</div>
    </button>
  `
  ).join('');

  function activateRoute(idx) {
    const route = TOPOLOGY_ROUTES[idx] || TOPOLOGY_ROUTES[0];
    if (stageEl) stageEl.style.setProperty('--topo-accent', route.accent);
    if (descEl) descEl.textContent = route.description;
    if (packetEl) {
      packetEl.textContent = route.packetLabel;
      packetEl.style.color = route.accent;
    }

    routeListEl.querySelectorAll('.route-btn').forEach((b, i) => {
      b.classList.toggle('active', i === idx);
    });

    for (const [id, n] of Object.entries(nodes)) {
      n.el.classList.toggle('active', route.activeNodes.includes(id));
    }

    for (const link of LINKS) {
      const pathEl = pathCache[link.id];
      if (pathEl) {
        pathEl.classList.toggle('active', route.activeLinks.includes(link.id));
      }
    }
  }

  routeListEl.querySelectorAll('.route-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      activateRoute(parseInt(btn.dataset.routeIdx, 10));
    });
  });

  measureAndSync({ resetToDefault: true });
  activateRoute(0);
}

// ============================================================================
// 4. Quickstart Tabs & Copy to Clipboard
// ============================================================================
function initQuickstart() {
  const tabsEl = document.getElementById('qs-tabs');
  const descEl = document.getElementById('qs-desc');
  const codeEl = document.getElementById('qs-code');
  const copyBtn = document.getElementById('qs-copy-btn');

  if (!tabsEl || !codeEl) return;

  let activeIdx = 0;

  tabsEl.innerHTML = QUICKSTART_TABS.map(
    (t, i) => `
    <button type="button" class="qs-tab-btn ${i === 0 ? 'active' : ''}" data-qs-idx="${i}">
      ${t.label}
    </button>
  `
  ).join('');

  function setTab(idx) {
    activeIdx = idx;
    const item = QUICKSTART_TABS[idx] || QUICKSTART_TABS[0];
    if (descEl) descEl.textContent = item.description;
    codeEl.textContent = item.code;
    tabsEl.querySelectorAll('.qs-tab-btn').forEach((b, i) => {
      b.classList.toggle('active', i === idx);
    });
  }

  tabsEl.querySelectorAll('.qs-tab-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      setTab(parseInt(btn.dataset.qsIdx, 10));
    });
  });

  if (copyBtn) {
    copyBtn.addEventListener('click', () => {
      const text = QUICKSTART_TABS[activeIdx].code;
      navigator.clipboard.writeText(text).then(() => {
        const orig = copyBtn.textContent;
        copyBtn.textContent = 'Скопировано ✓';
        setTimeout(() => {
          copyBtn.textContent = orig;
        }, 1800);
      });
    });
  }

  setTab(0);
}

// Initialize everything
initLowerBackground();
renderEcosystemCards();
initTopology();
initTerminal();
initQuickstart();
sceneCtrl.start();
