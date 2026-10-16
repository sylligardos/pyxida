// Needle -- the series chart. One class for every place a series is drawn:
//
//   edit     Round: zoom, pan, and mark up to five ranges (strong highlights)
//   reveal   Reveal: labels, player ranges, detector flags, one score lane
//            per detector with its threshold
//   thumb    Summary cards, the Map strip, the attract screens: line only
//
// The line goes on a canvas, min-max decimated to one column per pixel, so
// 10k points stay smooth. Ranges are DOM boxes over it, which keeps the
// handles, tags and remove buttons ordinary clickable elements.
//
// Positions are in continuous index units: point i sits at x = i and owns
// [i - 0.5, i + 0.5]; the full view is [-0.5, n - 0.5].

const COLORS = {
  line: '#ECE8FF', grid: '#1F1B45', det: '#22D3EE', detArea: 'rgba(34, 211, 238, 0.28)',
};
const MIN_SPAN = 30;          // the deepest zoom, in points
const CLICK_PX = 4;           // a drag shorter than this is a click
const CLICK_HALF_PX = 3;      // a click marks +-3 px around the point
export const MAX_RANGE_FRACTION = 0.10;   // scoring.py: a range wider than this share of the window is a false alarm

const fmtInt = (x) => Math.round(x).toLocaleString('en-US');

function niceTicks(lo, hi, count = 4) {
  const raw = (hi - lo) / count;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map((x) => x * mag).find((x) => x >= raw) || raw;
  const out = [];
  for (let y = Math.ceil(lo / step) * step; y <= hi; y += step) out.push(+y.toFixed(6));
  return out;
}

function el(tag, cls, parent) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (parent) parent.appendChild(e);
  return e;
}

export function overlaps(r, s) { return r[0] <= s[1] && r[1] >= s[0]; }

export function cleanRanges(ranges, n) {
  const out = ranges
    .map(([a, b]) => [Math.max(0, Math.min(a, b)), Math.min(n - 1, Math.max(a, b))])
    .filter(([a, b]) => b >= a)
    .sort((x, y) => x[0] - y[0]);
  const merged = [];
  for (const [a, b] of out) {
    if (merged.length && a <= merged[merged.length - 1][1] + 1) {
      merged[merged.length - 1][1] = Math.max(merged[merged.length - 1][1], b);
    } else merged.push([a, b]);
  }
  return merged;
}

// Draw values[i0..i1] into a canvas context, x mapped by xOf, y by yOf.
// One min-max pair per pixel column when the view is dense.
function drawLine(ctx, values, view, w, yOf, opts = {}) {
  const n = values.length;
  const [v0, v1] = view;
  const i0 = Math.max(0, Math.floor(v0)), i1 = Math.min(n - 1, Math.ceil(v1));
  const xOf = (i) => (i - v0) / (v1 - v0) * w;
  ctx.beginPath();
  const dense = (i1 - i0) > w * 2;
  if (!dense) {
    for (let i = i0; i <= i1; i++) {
      const x = xOf(i), y = yOf(values[i]);
      if (i === i0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
  } else {
    const per = (v1 - v0) / w;
    let first = true;
    for (let px = 0; px < w; px++) {
      const a = Math.max(i0, Math.floor(v0 + px * per));
      const b = Math.min(i1, Math.floor(v0 + (px + 1) * per));
      if (b < a) continue;
      let mi = a, ma = a;
      for (let i = a; i <= b; i++) {
        if (values[i] < values[mi]) mi = i;
        if (values[i] > values[ma]) ma = i;
      }
      const [p, q] = mi < ma ? [mi, ma] : [ma, mi];
      if (first) { ctx.moveTo(px, yOf(values[p])); first = false; } else ctx.lineTo(px, yOf(values[p]));
      if (q !== p) ctx.lineTo(px + 0.5, yOf(values[q]));
    }
  }
  if (opts.close) {
    ctx.lineTo(w, opts.close); ctx.lineTo(0, opts.close); ctx.closePath();
  }
}

function sizeCanvas(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
  }
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  return { ctx, w, h };
}

export class SeriesChart {
  constructor(root, opts) {
    this.root = root;
    this.o = Object.assign({
      mode: 'thumb', height: 380, values: [], stroke: COLORS.line, panel: null,
      labels: [], ranges: [], detRanges: [], detectors: null, team: null, maxRanges: 5,
      truthLabel: true, lineWidth: null, onChange: null, onView: null, onLimit: null, onWide: null,
    }, opts);
    this.n = this.o.values.length;
    this.view = [-0.5, this.n - 0.5];
    this.ranges = this.o.ranges.map((r) => r.slice());
    this.activity = { zooms: 0, pans: 0, min_span: this.n };
    this.drag = null;
    this.build();
    this.ro = new ResizeObserver(() => this.render());
    this.ro.observe(this.frame);
  }

  get axes() { return this.o.mode !== 'thumb'; }

  build() {
    const r = this.root;
    r.innerHTML = '';
    // height 'fill': the chart takes whatever height its container has,
    // so a screen can give it the space left over (see .chart.fill).
    const fill = this.o.height === 'fill';
    this.wrap = el('div', `chart ${this.o.mode}${fill ? ' fill' : ''}`, r);
    this.frame = el('div', 'chart-frame' + (this.axes ? '' : ' bare'), this.wrap);
    if (!fill) this.frame.style.height = typeof this.o.height === 'number' ? this.o.height + 'px' : this.o.height;
    if (this.o.panel) this.frame.style.background = this.o.panel;
    if (this.axes) this.yticks = el('div', 'chart-yticks', this.frame);
    this.plot = el('div', 'chart-plot', this.frame);
    this.canvas = el('canvas', '', this.plot);
    this.layer = el('div', 'chart-layer', this.plot);
    if (this.axes) {
      this.xaxis = el('div', 'chart-xaxis', this.wrap);
      this.bindPan(this.xaxis, () => this.plot.clientWidth, 1);
      this.plot.addEventListener('wheel', (e) => this.onWheel(e), { passive: false });
    }
    if (this.o.mode === 'reveal' && this.o.detectors) {
      const s = el('div', 'score-strip', this.wrap);
      s.innerHTML = '<header><span>Anomaly scores</span>'
        + '<span><i class="thr-key"></i>threshold: mean + 3 std</span></header>';
      const lane = (d, cls, name) => {
        const box = el('div', cls, s);
        const canvas = el('canvas', '', box);
        const layer = el('div', 'chart-layer', box);
        el('span', 'name', box).textContent = name;
        return { d, canvas, layer };
      };
      // The team average is what the detectors are scored on (when the
      // server sends one); the five lanes under it are each detector alone.
      const team = this.o.team;
      this.lanes = (team ? [lane({ ...team, caught: false, team: true }, 'lane team', 'Team average · scored')] : [])
        .concat(this.o.detectors.map((d) =>
          lane(d, 'lane' + (team ? ' solo' : '') + (d.caught ? ' lit' : ''), d.name + (d.caught ? ' · caught it' : ''))));
    }
    if (this.o.mode === 'edit') this.bindEdit();
  }

  destroy() { this.ro.disconnect(); }

  // ------------------------------------------------------------ view

  setView(v0, v1, source) {
    const full = this.n;
    let span = Math.max(Math.min(MIN_SPAN, full), Math.min(full, v1 - v0));
    let a = v0, b = v0 + span;
    if (a < -0.5) { a = -0.5; b = a + span; }
    if (b > full - 0.5) { b = full - 0.5; a = b - span; }
    this.view = [a, b];
    this.activity.min_span = Math.min(this.activity.min_span, Math.round(b - a));
    this.render();
    if (this.o.onView) this.o.onView(this.view, source);
  }

  resetView() { this.setView(-0.5, this.n - 0.5, 'reset'); }

  isFullView() { return this.view[1] - this.view[0] >= this.n - 0.01; }

  onWheel(e) {
    e.preventDefault();
    const rect = this.plot.getBoundingClientRect();
    const f = (e.clientX - rect.left) / rect.width;
    const [v0, v1] = this.view, span = v1 - v0;
    if (Math.abs(e.deltaX) > Math.abs(e.deltaY) && !e.ctrlKey) {
      const d = e.deltaX / rect.width * span;
      this.activity.pans++;
      this.setView(v0 + d, v1 + d, 'pan');
      return;
    }
    const k = Math.exp(e.deltaY * (e.ctrlKey ? 0.01 : 0.0015));
    const at = v0 + f * span;
    const ns = span * k;
    this.activity.zooms++;
    this.setView(at - f * ns, at - f * ns + ns, 'zoom');
  }

  // Drag on `target` pans the view; `scale` is +1 for the axis (drag right
  // to see earlier points) and -n/width for the map (drag the window).
  bindPan(target, widthOf, mode) {
    target.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      target.setPointerCapture(e.pointerId);
      const x0 = e.clientX, start = this.view.slice();
      const move = (ev) => {
        const w = widthOf();
        const dx = ev.clientX - x0;
        const d = mode === 1 ? -dx / w * (start[1] - start[0]) : dx / w * this.n;
        this.setView(start[0] + d, start[1] + d, 'pan');
      };
      const up = () => {
        this.activity.pans++;
        target.removeEventListener('pointermove', move);
        target.removeEventListener('pointerup', up);
        target.removeEventListener('pointercancel', up);
      };
      target.addEventListener('pointermove', move);
      target.addEventListener('pointerup', up);
      target.addEventListener('pointercancel', up);
    });
  }

  // ------------------------------------------------------------ editing

  xToIdx(clientX) {
    const rect = this.plot.getBoundingClientRect();
    const [v0, v1] = this.view;
    return v0 + (clientX - rect.left) / rect.width * (v1 - v0);
  }

  pxToIdx(px) { return px / this.plot.clientWidth * (this.view[1] - this.view[0]); }
  maxLen() { return Math.max(1, Math.floor(this.n * MAX_RANGE_FRACTION)); }

  bindEdit() {
    const plot = this.plot;
    plot.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      const t = e.target.closest('[data-act]');
      const act = t ? t.dataset.act : 'new';
      const k = t ? Number(t.dataset.k) : -1;
      if (act === 'rm') return;   // handled on click
      if (act === 'new' && this.ranges.length >= this.o.maxRanges) {
        if (this.o.onLimit) this.o.onLimit();
        return;
      }
      e.preventDefault();
      plot.setPointerCapture(e.pointerId);
      const at = this.xToIdx(e.clientX);
      this.drag = { act, k, x0: e.clientX, at0: at, orig: k >= 0 ? this.ranges[k].slice() : null, cur: null,
        before: this.ranges.map((r) => r.slice()) };
    });
    plot.addEventListener('pointermove', (e) => {
      const d = this.drag;
      if (!d) return;
      const at = this.xToIdx(e.clientX);
      const n = this.n;
      const span = this.maxLen() - 1;   // a range may be at most maxLen points long
      if (d.act === 'new') {
        d.cur = [Math.max(Math.min(d.at0, at), d.at0 - span), Math.min(Math.max(d.at0, at), d.at0 + span)];
      } else if (d.act === 'l') {
        this.ranges[d.k] = [Math.max(Math.min(Math.round(at), d.orig[1]), d.orig[1] - span), d.orig[1]];
      } else if (d.act === 'r') {
        this.ranges[d.k] = [d.orig[0], Math.min(Math.max(Math.round(at), d.orig[0]), d.orig[0] + span)];
      } else if (d.act === 'move') {
        const len = d.orig[1] - d.orig[0];
        let a = Math.round(d.orig[0] + at - d.at0);
        a = Math.max(0, Math.min(n - 1 - len, a));
        this.ranges[d.k] = [a, a + len];
      }
      this.renderBands();
    });
    const end = (e) => {
      const d = this.drag;
      if (!d) return;
      this.drag = null;
      if (d.act === 'new') {
        if (Math.abs(e.clientX - d.x0) < CLICK_PX) {
          const half = Math.max(0, this.pxToIdx(CLICK_HALF_PX));
          this.ranges.push([Math.round(d.at0 - half), Math.round(d.at0 + half)]);
        } else if (d.cur) {
          this.ranges.push([Math.round(d.cur[0]), Math.round(d.cur[1])]);
        }
      }
      this.ranges = cleanRanges(this.ranges, this.n);
      // Two marks that touch merge into one; if that one is too wide, the
      // edit is undone rather than scored as a false alarm.
      if (this.ranges.some((r) => r[1] - r[0] + 1 > this.maxLen())) {
        this.ranges = d.before;
        if (this.o.onWide) this.o.onWide();
      }
      this.renderBands();
      if (this.o.onChange) this.o.onChange(this.ranges);
    };
    plot.addEventListener('pointerup', end);
    plot.addEventListener('pointercancel', end);
    plot.addEventListener('click', (e) => {
      const t = e.target.closest('[data-act="rm"]');
      if (!t) return;
      this.ranges.splice(Number(t.dataset.k), 1);
      this.renderBands();
      if (this.o.onChange) this.o.onChange(this.ranges);
    });
  }

  setRanges(ranges) {
    this.ranges = cleanRanges(ranges, this.n);
    this.renderBands();
  }

  // ------------------------------------------------------------ drawing

  place(a, b) {
    // [a, b] inclusive point indices -> left/width in % of the plot, or null
    // when off screen.
    const [v0, v1] = this.view, span = v1 - v0;
    const L = (a - 0.5 - v0) / span * 100, R = (b + 0.5 - v0) / span * 100;
    if (R < 0 || L > 100) return null;
    const l = Math.max(0, L), r = Math.min(100, R);
    return { left: l, width: Math.max(0, r - l), cutL: L < 0, cutR: R > 100 };
  }

  band(cls, a, b, parent = this.layer) {
    const p = this.place(a, b);
    if (!p) return null;
    const d = el('div', 'band ' + cls, parent);
    d.style.left = p.left + '%';
    d.style.width = p.width + '%';
    return { d, p };
  }

  render() {
    if (!this.frame.isConnected) return;
    this.renderLine();
    this.renderBands();
    if (this.lanes) this.renderLanes();
  }

  renderLine() {
    const values = this.o.values;
    const { ctx, w, h } = sizeCanvas(this.canvas);
    if (!w || !h || !this.n) return;
    const [v0, v1] = this.view;
    const i0 = Math.max(0, Math.floor(v0)), i1 = Math.min(this.n - 1, Math.ceil(v1));
    let lo = Infinity, hi = -Infinity;
    for (let i = i0; i <= i1; i++) { if (values[i] < lo) lo = values[i]; if (values[i] > hi) hi = values[i]; }
    const pad = (hi - lo) * 0.08 || 1;
    lo -= pad; hi += pad;
    const yOf = (y) => (hi - y) / (hi - lo) * h;

    if (this.axes) {
      const ticks = niceTicks(lo, hi);
      ctx.strokeStyle = COLORS.grid;
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (const t of ticks) { const y = Math.round(yOf(t)) + 0.5; ctx.moveTo(0, y); ctx.lineTo(w, y); }
      ctx.stroke();
      this.yticks.innerHTML = ticks.map((t) =>
        `<span style="top:${(yOf(t) / h * 100).toFixed(2)}%">${+t.toFixed(4)}</span>`).join('');
      this.xaxis.innerHTML = [0, 0.2, 0.4, 0.6, 0.8, 1].map((f) => {
        const shift = f === 0 ? 0 : f === 1 ? -100 : -50;
        const idx = Math.min(this.n - 1, Math.max(0, v0 + f * (v1 - v0)));
        return `<span style="left:${f * 100}%;transform:translateX(${shift}%)">${fmtInt(idx)}</span>`;
      }).join('');
    }

    ctx.strokeStyle = this.o.stroke;
    ctx.lineWidth = this.o.lineWidth || (h < 90 ? 1 : 1.25);
    ctx.lineJoin = 'round';
    drawLine(ctx, values, this.view, w, yOf);
    ctx.stroke();
  }

  renderBands() {
    const L = this.layer;
    L.innerHTML = '';
    const showTruth = this.o.mode !== 'edit';
    if (showTruth) {
      for (const [a, b] of this.o.labels) {
        const t = this.band('truth', a, b);
        if (t && this.o.truthLabel && this.axes) {
          const chip = el('span', 'chip', t.d);
          chip.textContent = a === b ? `Point anomaly · t ${fmtInt(a)}` : 'Labeled anomaly';
        }
      }
    }
    if (this.o.mode === 'reveal') {
      for (const [a, b] of this.o.detRanges) this.band('det', a, b);
    }
    if (this.o.mode === 'edit' || this.o.mode === 'reveal') {
      let lastTagX = -1e9, tagRow = 0;
      this.ranges.forEach(([a, b], k) => {
        const edit = this.o.mode === 'edit';
        const t = this.band('player' + (edit ? ' edit' : ''), a, b);
        if (!t) return;
        const tag = el('span', 'tag', t.d);
        if (edit) {
          t.d.dataset.act = 'move';
          t.d.dataset.k = k;
          tag.textContent = String(k + 1);
          if (t.d.getBoundingClientRect().width < 44) t.d.classList.add('narrow');
          if (!t.p.cutL) Object.assign(el('span', 'handle l', t.d).dataset, { act: 'l', k });
          if (!t.p.cutR) Object.assign(el('span', 'handle r', t.d).dataset, { act: 'r', k });
          const rm = el('button', 'rm', t.d);
          rm.type = 'button';
          Object.assign(rm.dataset, { act: 'rm', k });
          rm.setAttribute('aria-label', `Remove range ${k + 1}`);
          rm.innerHTML = '<svg width="10" height="10" viewBox="0 0 10 10" style="fill:none;stroke:currentColor;stroke-width:1.6px;stroke-linecap:round"><path d="M2 2 L8 8 M8 2 L2 8"/></svg>';
        } else {
          const hit = this.o.labels.some((l) => overlaps([a, b], l));
          tag.textContent = `${k + 1} · ${hit ? 'hit' : 'false alarm'}`;
          // Ranges close together: step the tag down so they do not overlap.
          const x = t.d.offsetLeft;
          if (k > 0 && x - lastTagX < 120) tagRow = (tagRow + 1) % 3; else tagRow = 0;
          tag.style.top = (14 + 24 * tagRow) + 'px';
          lastTagX = x;
        }
      });
    }
    if (this.drag && this.drag.act === 'new' && this.drag.cur) {
      const [a, b] = this.drag.cur;
      this.band('drag', Math.round(a), Math.round(b));
    }
  }

  renderLanes() {
    for (const { d, canvas, layer } of this.lanes) {
      layer.innerHTML = '';
      for (const [a, b] of this.o.labels) this.band('truth', a, b, layer);
      for (const [a, b] of d.flags) this.band('det', a, b, layer);
      const { ctx, w, h } = sizeCanvas(canvas);
      if (!w) continue;
      // Detector scores are 0..pack.SCORE_SCALE; the average rarely reaches
      // the top, so its lane is scaled to its own peak.
      let top = 1000;
      if (d.team) { top = 1; for (const x of d.score) if (x > top) top = x; }
      const yOf = (y) => h - (0.04 + 0.9 * y / top) * h;
      ctx.globalAlpha = d.team || d.caught ? 1 : 0.75;
      ctx.fillStyle = COLORS.detArea;
      ctx.strokeStyle = COLORS.det;
      ctx.lineWidth = 1.6;
      drawLine(ctx, d.score, this.view, w, yOf, { close: h });
      ctx.fill();
      drawLine(ctx, d.score, this.view, w, yOf);
      ctx.stroke();
      ctx.globalAlpha = 1;
      const y = Math.round(yOf(d.threshold)) + 0.5;
      ctx.strokeStyle = 'rgba(236, 232, 255, 0.6)';
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
      ctx.setLineDash([]);
    }
  }
}

// The Map strip under the Round chart: the whole series, a box for the
// zoomed window; drag the box or click anywhere to move it.
export class MapStrip {
  constructor(root, chart) {
    this.chart = chart;
    root.innerHTML = '';
    this.box = el('div', 'map', root);
    this.canvas = el('canvas', '', this.box);
    this.win = el('div', 'win', this.box);
    this.box.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      const rect = this.box.getBoundingClientRect();
      const n = chart.n;
      const [v0, v1] = chart.view, span = v1 - v0;
      if (e.target !== this.win) {
        const c = (e.clientX - rect.left) / rect.width * n - 0.5;
        chart.setView(c - span / 2, c + span / 2, 'map');
      }
    });
    chart.bindPan(this.box, () => this.box.clientWidth, -1);
    this.ro = new ResizeObserver(() => this.render());
    this.ro.observe(this.box);
  }

  render() {
    const c = this.chart;
    const { ctx, w, h } = sizeCanvas(this.canvas);
    if (!w) return;
    const v = c.o.values;
    let lo = Infinity, hi = -Infinity;
    for (const x of v) { if (x < lo) lo = x; if (x > hi) hi = x; }
    const pad = (hi - lo) * 0.08 || 1;
    const yOf = (y) => 4 + (hi + pad - y) / (hi - lo + 2 * pad) * (h - 8);
    ctx.strokeStyle = '#7D76AE';
    ctx.lineWidth = 1;
    drawLine(ctx, v, [-0.5, c.n - 0.5], w, yOf);
    ctx.stroke();
    this.update();
  }

  update() {
    const c = this.chart;
    const full = c.isFullView();
    this.win.style.display = full ? 'none' : '';
    const [a, b] = c.view;
    this.win.style.left = ((a + 0.5) / c.n * 100) + '%';
    this.win.style.width = Math.max(0.6, (b - a) / c.n * 100) + '%';
  }

  destroy() { this.ro.disconnect(); }
}

// Synthetic signal, the same as the design comps' Chart.dc.html, for the
// decorative charts on Start and the Leaderboard: no real series on screen
// before a round starts.
export function attractSeries(seed = 5, n = 6000, anomaly = [0.62, 0.68], period = 140) {
  let s = (seed * 2654435761) >>> 0 || 1;
  const rnd = () => { s = (Math.imul(s, 1664525) + 1013904223) >>> 0; return s / 4294967296; };
  const ai = Math.round(anomaly[0] * (n - 1)), bi = Math.round(anomaly[1] * (n - 1));
  const v = new Array(n);
  let ph = rnd() * 6.28, drift = 0, ar = 0;
  for (let i = 0; i < n; i++) {
    const inA = i >= ai && i <= bi;
    ph += 2 * Math.PI * (inA ? 1.55 : 1) / period;
    drift = drift * 0.998 + (rnd() - 0.5) * 0.03;
    ar = ar * 0.6 + (rnd() - 0.5) * 0.3;
    v[i] = 40 + 9 * (Math.sin(ph) + 0.32 * Math.sin(ph * 3 + 0.7) + drift + ar);
  }
  return v;
}
