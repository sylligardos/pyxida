// Needle -- the five screens and the flow between them.
//
//   Start -> Round (x6, each followed by its Reveal) -> Summary -> Leaderboard
//
// Each screen is a function that renders into #app. The server holds the
// labels and scores; this file only draws what it is sent. Layout, copy and
// colours follow references/needle-design (the *Arcade comps).

import { SeriesChart, MapStrip, attractSeries } from './chart.js';
import { sfx, music, ambient, setMuted } from './sfx.js';

const app = document.getElementById('app');
const MAX_RANGES = 5;
// Per-series time limit: the server sets it by difficulty (?time= overrides
// it, for testing). The last WARN_S seconds tick quietly, the last HURRY_S
// faster; at zero the marks are submitted as they stand.
const TIME_OVERRIDE_S = Number(new URLSearchParams(location.search).get('time')) || 0;
const DIFFICULTY_LABEL = { easy: 'Easy', normal: 'Normal', hard: 'Hard' };
// Background while marking: march | heartbeat | sonar | drone | muffled | none.
// ?ambient=sonar in the URL tries another.
const AMBIENT = new URLSearchParams(location.search).get('ambient') || 'march';
const WARN_S = 10;
const HURRY_S = 3;
const IDLE_MS = 150 * 1000;        // walk away mid-round -> back to the board
const BOARD_REFRESH_MS = 20 * 1000;
const WORDS = ['Zero', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten'];
const ORD = ['1ST', '2ND', '3RD', '4TH', '5TH', '6TH', '7TH', '8TH', '9TH', '10TH'];
const TIER_ORDER = ['easy', 'medium', 'unsolved', 'decoy'];
const TIER_COLOR = { easy: 'var(--det)', medium: 'var(--text)', unsolved: 'var(--player)', decoy: 'var(--yellow)' };

const S = {
  screen: null,
  nick: '',
  difficulty: 'normal',
  pack: '',         // the benchmark pack to play; '' = the server's first
  dataset: '',      // one dataset of that pack; '' = any
  round: null,      // {id, nick, count, teamSize, timeLimit, idx, results[], values[], labels[], t0}
  live: [],         // charts and timers of the current screen, torn down on change
  pause: null,      // {on, off} while a Round screen's clock can be paused
};

// ------------------------------------------------------------------ helpers

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmtInt = (x) => Math.round(x).toLocaleString('en-US');
const fmtPts = (v) => (v > 0 ? '+' + v : v < 0 ? '−' + (-v) : '0');
const fmtTot = (v) => (v < 0 ? '−' + (-v) : String(v));
const mmss = (ms) => {
  const s = Math.max(0, Math.floor(ms / 1000));
  return String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0');
};

async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path}: ${res.status} ${await res.text()}`);
  return res.json();
}

function show(screen, html) {
  for (const x of S.live) {
    if (typeof x === 'number') clearInterval(x);
    else if (x && x.destroy) x.destroy();
  }
  S.live = [];
  ambient.stop();
  S.screen = screen;
  S.pause = null;
  document.body.dataset.screen = screen;
  app.innerHTML = html;
  app.querySelectorAll('[data-quit]').forEach((b) => { b.onclick = askQuit; });
  showMute();
  window.scrollTo(0, 0);
}

// Leave a round at any point, after an "are you sure". A round is only put
// on the board by /finish, so leaving drops it; the series already played
// stay in the log. On the Round screen the clock stops while asking.
function askQuit() {
  if (!['round', 'reveal'].includes(S.screen) || app.querySelector('.modal')) return;
  sfx.play('tick');
  if (S.pause) S.pause.on();
  const box = document.createElement('div');
  box.className = 'modal';
  box.innerHTML = `<div class="modal-card panel" role="dialog" aria-modal="true" aria-labelledby="quit-h">
    <h2 id="quit-h" class="display">LEAVE THIS ROUND?</h2>
    <p>Your score so far will not go on the leaderboard.${S.screen === 'round' ? ' The clock is paused.' : ''}</p>
    <div class="actions">
      <button class="btn btn-outline" type="button" data-leave>LEAVE</button>
      <button class="btn btn-primary" type="button" data-stay>KEEP PLAYING</button>
    </div></div>`;
  app.appendChild(box);
  const close = () => {
    box.remove();
    window.removeEventListener('keydown', onKey, true);
    if (S.pause) S.pause.off();
  };
  const onKey = (e) => {
    if (e.key === 'Escape') { e.stopPropagation(); sfx.play('tick'); close(); }
  };
  window.addEventListener('keydown', onKey, true);
  box.querySelector('[data-stay]').onclick = () => { sfx.play('tick'); close(); };
  box.querySelector('[data-leave]').onclick = () => {
    window.removeEventListener('keydown', onKey, true);
    sfx.play('remove');
    S.round = null;
    renderStart();
  };
  box.onclick = (e) => { if (e.target === box) close(); };
  box.querySelector('[data-stay]').focus();
}

function chart(sel, opts) {
  const c = new SeriesChart(app.querySelector(sel), opts);
  S.live.push(c);
  return c;
}

function every(ms, fn) { S.live.push(setInterval(fn, ms)); }

function fail(err) {
  console.error(err);
  show('error', `<div class="page dots" style="align-items:center;justify-content:center;text-align:center">
    <h1 class="display glitch" style="margin:0;font-size:48px">GAME OVER</h1>
    <p style="color:var(--text-2)">Something went wrong talking to the game server.</p>
    <button class="btn btn-primary" type="button" id="restart">BACK TO START</button></div>`);
  app.querySelector('#restart').onclick = () => renderStart();
}

// Idle: a player who walks away mid-round leaves the board on screen.
let lastInput = Date.now();
for (const ev of ['pointerdown', 'pointermove', 'keydown', 'wheel']) {
  window.addEventListener(ev, () => { lastInput = Date.now(); }, { passive: true });
}
setInterval(() => {
  if (['round', 'reveal', 'summary'].includes(S.screen) && Date.now() - lastInput > IDLE_MS) {
    renderBoard().catch(fail);
  }
}, 5000);

// The leaderboard rows, with the detectors' reference entry slotted in by
// score. Shared by Start (5 rows) and the Leaderboard (8 rows).
function boardRows(board, detAvg, size) {
  const rows = [];
  let placed = detAvg === null || detAvg === undefined;
  const ref = { ref: true, name: 'DETECTORS', score: detAvg };
  let k = 0;
  for (const p of board) {
    if (!placed && p.score < detAvg) { rows.push(ref); placed = true; }
    rows.push({ ...p, rank: ORD[k++] });
  }
  if (!placed) rows.push(ref);
  while (rows.length < size) rows.push({ blank: true, name: '---', score: 0, rank: ORD[k++] || '' });
  return rows.slice(0, size);
}

function fmtRef(x) {
  if (x === null || x === undefined) return '–';
  const s = Number.isInteger(x) ? String(Math.abs(x)) : Math.abs(x).toFixed(1);
  return x < 0 ? '−' + s : s;
}

// ------------------------------------------------------------------ 1. Start

async function renderStart() {
  let data = { stats: {}, leaderboard: [], team_size: 5, round_size: 10, difficulties: {}, packs: [] };
  try { data = await api('/api/stats'); } catch (e) { console.warn(e); }
  const st = data.stats;
  const mini = boardRows(data.leaderboard, st.det_avg, 5).map((r) => r.ref
    ? `<div class="mini-row ref"><span>REF</span><span>DETECTORS</span><span>${fmtRef(r.score)}</span></div>`
    : `<div class="mini-row${r.blank ? ' blank' : ''}"><span>${r.rank}</span><span>${esc(r.name)}</span><span>${r.blank ? '00' : r.score}</span></div>`).join('');
  const statline = st.humans_found_pct === null || st.humans_found_pct === undefined
    ? `<b>${st.plays ?? 0}</b> plays so far · be the first to find what the detectors miss`
    : `<b>${st.plays}</b> plays · humans found <b>${st.humans_found_pct}%</b> of what the detectors missed`;

  show('start', `<div class="page fit start-page">
    <section class="cabinet start-hero">
      <div class="start-top">
        <span style="display:flex;gap:18px;align-items:center">${location.pathname.startsWith('/play') ? '<a class="back-link" href="/">← Back to the demo</a>' : ''}<span style="color:var(--yellow)">Hi-score ${st.hi_score === null || st.hi_score === undefined ? '—' : fmtTot(st.hi_score)}</span></span>
        <span style="color:var(--text-4)">${WORDS[data.round_size].toLowerCase()} series a round</span>
        <span class="top-right"><span style="color:var(--det-soft)">${data.team_size} detectors in the pool</span>
          <button class="hud-btn help-btn" type="button" id="help" title="How Needle works" aria-label="How Needle works" hidden>?</button>
          <button class="hud-btn" type="button" data-mute title="Music and sounds on or off (M)"></button></span>
      </div>
      <div class="start-title">
        <h1>NEEDLE</h1>
        <p>Can you find what the detectors cannot?</p>
      </div>
      <div class="attract" aria-hidden="true"><div id="attract" class="grow"></div></div>
      <div class="attract-q" aria-hidden="true"><span>?</span></div>
      <div class="scanlines" aria-hidden="true"></div>
    </section>
    <div class="start-panels">
      <section class="panel">
        <h2 class="eyebrow" style="color:var(--text-4)">How to play</h2>
        <div class="step"><span class="n" style="color:var(--player)">1</span><div><b>MARK</b><span>Drag over anything that looks wrong.</span></div></div>
        <div class="step"><span class="n" style="color:var(--det)">2</span><div><b>REVEAL</b><span>See the labels and what the best detector for that series flagged.</span></div></div>
        <div class="step"><span class="n" style="color:var(--yellow)">3</span><div><b>SCORE</b><span>+1 per catch, −1 per false alarm. Beat the best.</span></div></div>
      </section>
      <section class="panel callout" style="padding:22px;gap:16px;justify-content:center">
        <form class="play-form" id="play">
          <div style="display:flex;flex-direction:column;gap:6px">
            <label for="nick">Enter your name (optional)</label>
            <input id="nick" type="text" maxlength="12" placeholder="AAA" autocomplete="off" spellcheck="false" value="${esc(S.nick)}">
          </div>
          <div style="display:flex;flex-direction:column;gap:6px">
            <label id="diff-label">Difficulty</label>
            <div class="choice" role="group" aria-labelledby="diff-label" id="difficulty">
              ${Object.keys(DIFFICULTY_LABEL).map((d) => `<button type="button" data-d="${d}" aria-pressed="${d === S.difficulty}">${DIFFICULTY_LABEL[d]}<small>${data.difficulties[d]?.time_s ?? '–'} s</small></button>`).join('')}
            </div>
          </div>
          <div class="pick-row">
            <div style="display:flex;flex-direction:column;gap:6px;flex:1">
              <label for="pack">Benchmark</label>
              <select id="pack">${data.packs.map((p) => `<option value="${esc(p.id)}"${p.id === S.pack ? ' selected' : ''}>${esc(p.id.toUpperCase())}</option>`).join('')}</select>
            </div>
            <div style="display:flex;flex-direction:column;gap:6px;flex:1">
              <label for="dataset">Dataset</label>
              <select id="dataset"></select>
            </div>
          </div>
          <button class="btn btn-primary" type="submit">PRESS PLAY</button>
        </form>
      </section>
      <section class="panel" style="gap:10px">
        <h2 class="eyebrow" style="color:var(--text-4)">High scores</h2>
        <div class="mini-board">${mini}</div>
        <p class="statline">${statline}</p>
      </section>
    </div>
  </div>`);

  chart('#attract', { mode: 'thumb', values: attractSeries(), height: 'fill', panel: 'transparent', stroke: '#22D3EE' });
  music.play();
  loadHelp().then((h) => {
    const b = app.querySelector('#help');
    if (!h || !b || S.screen !== 'start') return;
    b.hidden = false;
    b.onclick = () => { sfx.play('tick'); showHelp(h); };
  });
  const input = app.querySelector('#nick');
  input.focus();
  const diff = app.querySelector('#difficulty');
  diff.onclick = (e) => {
    const b = e.target.closest('button[data-d]');
    if (!b) return;
    S.difficulty = b.dataset.d;
    sfx.play('tick');
    for (const x of diff.querySelectorAll('button')) x.setAttribute('aria-pressed', String(x === b));
  };
  const packSel = app.querySelector('#pack'), dsSel = app.querySelector('#dataset');
  const fillDatasets = () => {
    const p = data.packs.find((x) => x.id === packSel.value) || data.packs[0];
    const ds = p ? p.datasets : [];
    dsSel.innerHTML = `<option value="">Any dataset</option>` + ds.map((d) =>
      `<option value="${esc(d.id)}"${d.id === S.dataset ? ' selected' : ''}>${esc(d.id)} · ${d.n}</option>`).join('');
    if (!ds.some((d) => d.id === S.dataset)) { S.dataset = ''; dsSel.value = ''; }
  };
  if (!data.packs.some((p) => p.id === S.pack)) S.pack = data.packs[0]?.id ?? '';
  packSel.value = S.pack;
  fillDatasets();
  packSel.onchange = () => { S.pack = packSel.value; S.dataset = ''; sfx.play('tick'); fillDatasets(); };
  dsSel.onchange = () => { S.dataset = dsSel.value; sfx.play('tick'); };
  app.querySelector('#play').onsubmit = (e) => {
    e.preventDefault();
    S.nick = input.value.trim();
    sfx.play('coin');
    startRound().catch(fail);
  };
}

// ------------------------------------------------------------------ 2. Round

async function startRound() {
  const r = await api('/api/round', { nick: S.nick, difficulty: S.difficulty, pack: S.pack || undefined, dataset: S.dataset || undefined });
  S.round = {
    id: r.round_id, nick: r.nick, count: r.count, teamSize: r.team_size,
    timeLimit: TIME_OVERRIDE_S || r.time_limit_s || 45, difficulty: r.difficulty,
    idx: 0, results: [], values: [], opponents: [], t0: Date.now(),
  };
  await renderRound(0);
}

function totals(upTo) {
  const res = S.round.results.slice(0, upTo);
  return {
    you: res.reduce((a, r) => a + r.you.round_points, 0),
    det: res.reduce((a, r) => a + r.det.round_points, 0),
  };
}

function hud(idx, { youTotal, detTotal, youDelta, detDelta, clock }) {
  const R = S.round;
  const pips = Array.from({ length: R.count }, (_, k) =>
    `<span class="pip${k < idx ? ' done' : k === idx ? ' now' : ''}"></span>`).join('');
  return `<header class="hud">
    <div class="hud-side">
      <span class="hud-1p">1P</span>
      <div style="display:flex;flex-direction:column">
        <span class="hud-who" style="color:var(--player-soft)">${esc(R.nick)}</span>
        <div style="display:flex;align-items:baseline;gap:8px">
          <span class="hud-score" style="color:var(--player)" id="you-total">${fmtTot(youTotal)}</span>
          ${youDelta !== undefined ? `<span class="hud-delta" style="color:var(--player-soft)">${fmtPts(youDelta)}</span>` : ''}
        </div>
      </div>
      <div class="hud-tools">
        <button class="hud-btn" type="button" data-mute title="Music and sounds on or off (M)"></button>
        <button class="hud-btn quit" type="button" data-quit title="Leave this round (Esc)">✕ Quit</button>
      </div>
    </div>
    <div class="hud-mid" aria-label="Series ${idx + 1} of ${R.count}">
      <span class="hud-pos">SERIES ${idx + 1} / ${R.count}</span>
      <div class="pips">${pips}</div>
    </div>
    <div class="hud-side right">
      <div style="display:flex;flex-direction:column;align-items:flex-end">
        <span class="hud-who hud-opp" style="color:var(--det-soft)">${esc(R.opponents?.[idx]?.name ?? 'Detector')}</span>
        <div style="display:flex;align-items:baseline;gap:8px">
          ${detDelta !== undefined ? `<span class="hud-delta" style="color:var(--det-soft)">${fmtPts(detDelta)}</span>` : ''}
          <span class="hud-score" style="color:var(--det)">${fmtTot(detTotal)}</span>
        </div>
      </div>
      ${clock ? `<span class="clock" id="clock">${mmss(R.timeLimit * 1000)}</span>` : ''}
    </div>
  </header>`;
}

async function renderRound(idx) {
  const R = S.round;
  R.idx = idx;
  music.stop();
  const t = totals(idx);
  show('round', `<div class="page fit round-page">
    ${hud(idx, { youTotal: t.you, detTotal: t.det, clock: true })}
    <section class="cabinet round-screen">
      <div class="round-bar">
        <div style="display:flex;align-items:baseline;gap:12px">
          <h1 id="sid">SERIES</h1><span class="pts" id="npts"></span>
        </div>
        <div class="tools">
          <span class="help">Scroll to zoom · drag the axis to pan</span>
          <span class="zoom-text" id="zoom">100%</span>
          <button class="btn-small" type="button" id="reset">Reset view</button>
        </div>
      </div>
      <div id="chart" class="grow"><div class="chart fill"><div class="chart-frame">
        <div class="chart-loading"><span id="loading-text">Loading series ${idx + 1}</span><div class="bar"><i></i></div></div>
      </div></div></div>
      <div class="map-row"><span>Map</span><div id="map" style="flex:1;min-width:0"><div class="map"></div></div></div>
      <div class="scanlines" aria-hidden="true"></div>
    </section>
    <div class="round-foot">
      <div class="hint-col">
        <p class="hint warn" id="hint">GET READY</p>
        <div class="slots-row">
          <span class="eyebrow" style="font-size:12px">Ranges</span>
          <div class="slots" id="slots"></div>
          <span class="sub-hint" id="subhint">Next series incoming.</span>
        </div>
      </div>
      <div class="actions">
        <button class="btn btn-outline" type="button" id="nothing" disabled>NOTHING HERE</button>
        <button class="btn btn-primary" type="button" id="submit" disabled>SUBMIT</button>
      </div>
    </div>
  </div>`);

  const data = await api(`/api/round/${R.id}/${idx}`);
  R.opponents[idx] = data.opponent || null;
  if (S.screen !== 'round' || R.idx !== idx) return;
  const oppEl = app.querySelector('.hud-opp');
  if (oppEl && data.opponent) oppEl.textContent = data.opponent.name;
  if (S.screen !== 'round' || R.idx !== idx) return;
  R.values[idx] = data.values;
  app.querySelector('#sid').textContent = data.label;
  app.querySelector('#npts').textContent = `${fmtInt(data.n)} pts`;

  const tStart = Date.now();
  let pausedMs = 0, pausedAt = null;
  const elapsed = () => (pausedAt ?? Date.now()) - tStart - pausedMs;
  S.pause = {
    on: () => { if (pausedAt === null) { pausedAt = Date.now(); ambient.stop(); } },
    off: () => {
      if (pausedAt === null) return;
      pausedMs += Date.now() - pausedAt;
      pausedAt = null;
      if (!sent) ambient.start(AMBIENT);
    },
  };
  const clock = app.querySelector('#clock');
  clock.textContent = mmss(R.timeLimit * 1000);
  let marks = 0;

  const zoom = app.querySelector('#zoom');
  let map = null;
  const c = chart('#chart', {
    mode: 'edit', values: data.values, height: 'fill', maxRanges: MAX_RANGES,
    onChange: (ranges) => {
      sfx.play(ranges.length > marks ? 'mark' : ranges.length < marks ? 'remove' : null);
      marks = ranges.length;
      updateMarks(ranges);
    },
    onLimit: () => {
      sfx.play('limit');
      const h = app.querySelector('#hint');
      h.classList.remove('shake'); void h.offsetWidth; h.classList.add('shake');
    },
    onWide: () => {
      sfx.play('limit');
      const h = app.querySelector('#hint'), sub = app.querySelector('#subhint');
      h.textContent = 'TOO WIDE'; h.classList.add('warn');
      sub.textContent = 'A mark covers at most a tenth of the series.';
      h.classList.remove('shake'); void h.offsetWidth; h.classList.add('shake');
    },
    onView: (v) => {
      zoom.textContent = c.isFullView() ? '100%'
        : `${fmtInt(Math.max(0, v[0] + 0.5))} to ${fmtInt(Math.min(data.n - 1, v[1] - 0.5))}`;
      if (map) map.update();
    },
  });
  map = new MapStrip(app.querySelector('#map'), c);
  S.live.push(map);
  app.querySelector('#reset').onclick = () => { sfx.play('tick'); c.resetView(); };

  const updateMarks = (ranges) => {
    const k = ranges.length;
    app.querySelector('#slots').innerHTML = Array.from({ length: MAX_RANGES }, (_, j) =>
      `<span class="slot${j < k ? ' on' : ''}">${j < k ? j + 1 : ''}</span>`).join('');
    const hint = app.querySelector('#hint'), sub = app.querySelector('#subhint');
    const full = k >= MAX_RANGES;
    hint.textContent = full ? 'OUT OF RANGES' : 'DRAG OVER WHAT LOOKS WRONG';
    hint.classList.toggle('warn', full);
    sub.textContent = full ? 'Remove one to mark another.'
      : k === 0 ? 'Nothing off? Hit Nothing here.'
        : `${MAX_RANGES - k} left. A mark covers at most a tenth of the series.`;
    app.querySelector('#submit').disabled = k === 0;
  };
  updateMarks([]);

  let sent = false;
  const go = async (nothing, timedOut = false) => {
    if (sent) return;
    sent = true;
    ambient.stop();
    if (!timedOut) sfx.play('submit');
    app.querySelector('#submit').disabled = true;
    app.querySelector('#nothing').disabled = true;
    const payload = await api(`/api/round/${R.id}/${idx}/submit`, {
      ranges: nothing ? [] : c.ranges, nothing,
      elapsed_ms: elapsed(), view: { ...c.activity, timed_out: timedOut },
    });
    if (S.round !== R) return;     // left the round while it was sent
    R.results[idx] = payload;
    renderReveal(idx);
  };
  const nothingBtn = app.querySelector('#nothing');
  nothingBtn.disabled = false;
  nothingBtn.onclick = () => go(true).catch(fail);
  app.querySelector('#submit').onclick = () => go(false).catch(fail);

  let lastSec = null;
  ambient.start(AMBIENT);
  every(200, () => {
    if (sent || pausedAt !== null) return;
    const left = Math.max(0, R.timeLimit * 1000 - elapsed());
    ambient.update(1 - left / (R.timeLimit * 1000));
    const sec = Math.ceil(left / 1000);
    clock.textContent = mmss(sec * 1000);
    clock.classList.toggle('warn', sec <= WARN_S);
    clock.classList.toggle('hurry', sec <= HURRY_S);
    if (sec !== lastSec) {
      lastSec = sec;
      if (sec > 0 && sec <= HURRY_S) sfx.play('hurry');
      else if (sec > 0 && sec <= WARN_S) sfx.play(sec % 2 ? 'clock' : 'clock2');
    }
    if (left <= 0) {
      sfx.play('timeup');
      app.querySelector('#hint').textContent = 'TIME’S UP';
      go(false, true).catch(fail);
    }
  });
}

// The benchmark file behind a window, linked into the Workbench when the
// game runs inside the demo (under /play); plain text on the standalone server.
function seriesLink(src) {
  const name = String(src.filename).replace(/\.csv$/, '');
  if (!location.pathname.startsWith('/play')) return `<span class="series-name" title="${esc(src.filename)}">${esc(name)}</span>`;
  const q = new URLSearchParams({ b: src.benchmark || 'tsb-ad', k: 'uni', s: src.filename });
  return `<a class="series-name" href="/workbench?${q}" target="_blank" rel="noopener" title="Open in the Workbench (new tab)">${esc(name)} ↗</a>`;
}

// "How Needle works": the demo serves the text at /api/help (web/lib/help.ts).
// On the standalone server there is none, and the button stays hidden.
let HELP = null;
async function loadHelp() {
  if (HELP !== null) return HELP;
  try {
    const r = await fetch('/api/help');
    const d = r.ok ? await r.json() : null;
    HELP = d && d.help && d.help['/game'] ? { sections: d.help['/game'], cites: d.cites } : false;
  } catch (e) { HELP = false; }
  return HELP;
}
function showHelp(h) {
  const used = [...new Set(h.sections.flatMap((sec) => sec.entries.flatMap((e) => e.cites || [])))].sort((a, b) => a - b);
  const rows = h.sections.flatMap((sec) => sec.entries.map((e) =>
    `<dt>${esc(e.term)}</dt><dd>${esc(e.text)}${(e.cites || []).map((n) => ` <a href="${esc(h.cites[n].url || '#')}" target="_blank" rel="noopener">[${n}]</a>`).join('')}</dd>`)).join('');
  const refs = used.map((n) => `<p>[${n}] ${h.cites[n].url ? `<a href="${esc(h.cites[n].url)}" target="_blank" rel="noopener">${esc(h.cites[n].label)}</a>` : esc(h.cites[n].label)}</p>`).join('');
  const m = document.createElement('div');
  m.className = 'modal help-modal';
  m.innerHTML = `<div class="panel modal-card help-card" role="dialog" aria-modal="true" aria-label="How Needle works">
    <div class="help-head"><h2>HOW NEEDLE WORKS</h2><button class="hud-btn" type="button" id="help-close" aria-label="Close">×</button></div>
    <dl class="help-list">${rows}</dl>
    ${refs ? `<div class="help-refs">${refs}</div>` : ''}
  </div>`;
  const close = () => { m.remove(); document.removeEventListener('keydown', onKey); };
  const onKey = (e) => { if (e.key === 'Escape') close(); };
  m.addEventListener('mousedown', (e) => { if (e.target === m) close(); });
  m.querySelector('#help-close').onclick = close;
  document.addEventListener('keydown', onKey);
  app.appendChild(m);
}

// Which sound the Reveal opens with.
function revealSound(P) {
  if (P.tier === 'decoy') return P.you.clean ? 'clean' : 'miss';
  if (P.you.hits > 0) return 'hit';
  return P.det.hits > 0 ? 'detectors' : 'miss';
}

// ------------------------------------------------------------------ 3. Reveal

function renderReveal(idx) {
  const R = S.round, P = R.results[idx];
  const t = totals(idx + 1);
  const decoy = P.tier === 'decoy';
  const row = (l, a, b) => `<span class="l">${l}</span><span class="v">${a}</span><span class="v">${b}</span>`;
  const rows = decoy
    ? row('Hits', '–', '–') + row('False alarms', P.you.false_alarms, P.det.false_alarms)
      + row('Empty decoy', P.you.clean ? '+1' : '0', P.det.clean ? '+1' : '0')
    : row('Hits', P.you.hits, P.det.hits) + row('False alarms', P.you.false_alarms, P.det.false_alarms);
  const last = idx + 1 >= R.count;
  // The opponent card: the best detector on this series, and what it did.
  const O = P.opponent || { name: 'Detectors', pool: P.detectors.length };
  const d0 = P.detectors[0] || { flags: [], caught: false };
  const did = decoy
    ? (d0.flags.length ? `took the bait: ${d0.flags.length} false alarm${d0.flags.length > 1 ? 's' : ''}` : 'left it alone')
    : (d0.caught ? 'crossed its line on the anomaly' : (d0.flags.length ? 'flagged elsewhere' : 'stayed under its line'));
  const good = decoy ? d0.flags.length === 0 : d0.caught;
  const vus = typeof O.vus_pr === 'number' && isFinite(O.vus_pr) ? O.vus_pr.toFixed(2) : null;

  show('reveal', `<div class="page fit reveal-page">
    ${hud(idx, { youTotal: t.you, detTotal: t.det, youDelta: P.you.round_points, detDelta: P.det.round_points })}
    <div class="reveal-head">
      <div class="left">
        <div class="tier-row"><span class="tier tier-${P.tier}">${P.tier.toUpperCase()}</span><span class="tier-note">${esc(P.tier_note)}</span></div>
        <h1 class="verdict">${esc(P.verdict)}</h1>
        <p class="verdict-sub">${esc(P.verdict_sub)}</p>
      </div>
      <div class="layers" role="group" aria-label="Layers">
        <button class="layer" type="button" aria-pressed="true" data-layer="label" style="--c:var(--yellow);--f:rgba(255,225,77,0.10)"><i></i>Label</button>
        <button class="layer" type="button" aria-pressed="true" data-layer="you" style="--c:var(--player);--f:rgba(255,61,154,0.10)"><i></i>You</button>
        <button class="layer" type="button" aria-pressed="true" data-layer="det" style="--c:var(--det);--f:rgba(34,211,238,0.10)"><i></i>${esc(O.name)}</button>
      </div>
    </div>
    <section class="cabinet reveal-chart"><div id="chart" class="grow"></div></section>
    <div class="panels">
      <section class="panel">
        <h2 class="eyebrow">${esc(P.label)}${P.source && P.source.filename ? ` · ${seriesLink(P.source)}` : ''}</h2>
        <div class="tally">
          <span></span><span class="h" style="color:var(--player)">YOU</span><span class="h" style="color:var(--det)">DETECTORS</span>
          ${rows}
          <span class="tot-l">This series</span>
          <span class="tot" style="color:var(--player)">${fmtPts(P.you.round_points)}</span>
          <span class="tot" style="color:var(--det)">${fmtPts(P.det.round_points)}</span>
        </div>
        <p class="note">A series counts +1 when hits beat false alarms, −1 when they don't, 0 when nothing happened. ${esc(O.name)} flags wherever its score crosses its dashed line (mean + 3 std).</p>
      </section>
      <section class="panel callout ask">
        <!-- The "Now that you've seen it" question lived here (see, cannot,
             else -> /feedback). Removed 2026-10-16: nothing used the answers
             yet, and the box raised questions at the booth. The API and the
             feedback table stay, so it can come back as it was. -->
        <h2>YOUR OPPONENT</h2>
        <div class="opp-card${good ? ' on' : ''}">
          <span class="opp-name">${esc(O.name)}</span>
          <span class="opp-sub">${O.pool ? `The best of ${O.pool} detectors on this series` : 'The best detector on this series'}${vus ? ` · VUS-PR ${vus}` : ''}</span>
          <span class="opp-did"><span class="diamond"></span>${esc(did)}</span>
        </div>
        <div class="next-row"><span id="next-hint"></span>
          <button class="btn btn-primary" type="button" id="next">${last ? 'RESULTS' : 'NEXT'}</button></div>
      </section>
    </div>
  </div>`);

  const c = chart('#chart', {
    mode: 'reveal', values: R.values[idx], height: 'fill',
    labels: P.labels, ranges: P.ranges, detRanges: P.det_ranges, detectors: P.detectors,
    // With one opponent its own lane is the scored one; the team-average lane
    // only exists when a pack still holds several detectors.
    team: P.team_score && P.detectors.length > 1 ? { score: P.team_score, threshold: P.team_threshold, flags: P.det_ranges } : null,
  });
  const wrap = () => c.wrap;
  setTimeout(() => { if (S.screen === 'reveal') sfx.play(revealSound(P)); }, 200);
  app.querySelectorAll('.layer').forEach((b) => {
    b.onclick = () => {
      sfx.play('tick');
      const on = b.getAttribute('aria-pressed') !== 'true';
      b.setAttribute('aria-pressed', String(on));
      wrap().classList.toggle('hide-' + b.dataset.layer, !on);
    };
  });

  const next = app.querySelector('#next');
  next.onclick = () => {
    sfx.play('tick');
    next.disabled = true;
    if (last) finishRound().catch(fail);
    else renderRound(idx + 1).catch(fail);
  };
}

// ------------------------------------------------------------------ 4. Summary

async function finishRound() {
  const R = S.round;
  const fin = await api(`/api/round/${R.id}/finish`, {});
  R.elapsed = Date.now() - R.t0;
  R.finish = fin;
  renderSummary();
}

const MARK = {
  found: 'diamond', partial: 'diamond', clean: 'diamond',
  missed: 'diamond hollow', 'false alarm': 'bar-mark',
};

function renderSummary() {
  const R = S.round;
  const you = R.finish.you_total, det = R.finish.det_total;
  let W = 0, L = 0, T = 0;
  const tierCount = {};
  const cards = R.results.map((P, k) => {
    tierCount[P.tier] = (tierCount[P.tier] || 0) + 1;
    const o = P.outcome;
    if (o === 'you') W++; else if (o === 'det') L++; else T++;
    const banner = {
      you: ['YOU WIN', 'var(--player)', 'var(--player-ink)'],
      det: ['DETECTORS WIN', 'var(--det)', 'var(--det-ink)'],
      both: [P.tier === 'decoy' ? 'TIE · BOTH LEFT IT CLEAN' : 'TIE · BOTH FOUND IT', 'var(--text)', '#10061A'],
      nobody: ['TIE · NOBODY FOUND IT', '#2C2754', 'var(--text-2)'],
    }[o];
    const dots = o === 'both';
    const frame = { you: 'var(--player)', det: 'var(--det)', both: 'var(--done)', nobody: '#2C2754' }[o];
    const glow = { you: '0 0 20px rgba(255,61,154,0.3)', det: '0 0 20px rgba(34,211,238,0.25)' }[o] || 'none';
    const res = (who, key, text, pts, color, fill, on) =>
      `<div class="res${on ? ' lit' : o !== 'nobody' ? ' dim' : ''}" style="--c:${color};--f:${fill}">
        <span class="${MARK[key]}"></span>
        <span class="txt"><b>${who}</b><span>${esc(text)}</span></span>
        <span class="p">${fmtPts(pts)}</span></div>`;
    return `<article class="card ${o}" style="--frame:${frame};--glow:${glow}">
      <div class="banner" style="background:${banner[1]};color:${banner[2]}">
        ${dots ? '<span class="diamond" style="background:var(--player)"></span>' : ''}<span>${banner[0]}</span>${dots ? '<span class="diamond" style="background:var(--det)"></span>' : ''}
      </div>
      <div class="card-body">
        <div class="card-id"><span>${esc(P.label)}</span><span class="tier sm tier-${P.tier}">${P.tier.toUpperCase()}</span></div>
        <div id="thumb-${k}"></div>
        <div class="res-rows">
          ${res('YOU', P.you_result, P.you_text, P.you.round_points, 'var(--player)', 'rgba(255,61,154,0.16)', o === 'you' || o === 'both')}
          ${res(P.opponent ? P.opponent.name.toUpperCase() : 'DETECTORS', P.det_result, P.det_text, P.det.round_points, 'var(--det)', 'rgba(34,211,238,0.14)', o === 'det' || o === 'both')}
        </div>
      </div>
    </article>`;
  }).join('');

  const tiers = TIER_ORDER.filter((t) => tierCount[t]).map((t) =>
    `<b style="color:${TIER_COLOR[t]}">${tierCount[t]}</b> ${t}`);
  const tierLine = tiers.length > 1 ? tiers.slice(0, -1).join(', ') + ', ' + tiers[tiers.length - 1] : tiers.join('');
  const title = you > det ? 'YOU WIN' : det > you ? 'DETECTORS WIN' : 'TIE GAME';

  show('summary', `<div class="page fit dots summary">
    <div class="sum-head">
      <span class="sum-mute"><button class="hud-btn" type="button" data-mute title="Music and sounds on or off (M)"></button></span>
      <span class="eyebrow">${WORDS[R.count] || R.count} series · ${mmss(R.elapsed)}</span>
      <h1 class="glitch">${title}</h1>
    </div>
    <div class="versus">
      <div class="side${you > det ? ' win' : ''}" style="--c:var(--player);--f:rgba(255,61,154,0.08);--g:rgba(255,61,154,0.35);--s:var(--player-soft)">
        <span class="who">${esc(R.nick)}</span><span class="big">${fmtTot(you)}</span><span class="lbl">YOU</span>
      </div>
      <div class="vs"><b>VS</b><span>${W} W · ${L} L · ${T} T</span></div>
      <div class="side${det > you ? ' win' : ''}" style="--c:var(--det);--f:rgba(34,211,238,0.06);--g:rgba(34,211,238,0.3);--s:var(--det-soft)">
        <span class="who">The best detector, each series</span><span class="big">${fmtTot(det)}</span><span class="lbl">DETECTORS</span>
      </div>
    </div>
    <p class="tiers-line">You played ${tierLine}.</p>
    <div class="cards">${cards}</div>
    <div class="sum-foot">
      <p>Each series counts +1, 0 or −1: hits against false alarms, a clean decoy counts as a hit</p>
      <div class="actions">
        <button class="btn btn-outline" type="button" id="board">LEADERBOARD</button>
        <button class="btn btn-primary" type="button" id="again">PLAY AGAIN</button>
      </div>
    </div>
  </div>`);

  R.results.forEach((P, k) => chart(`#thumb-${k}`, {
    mode: 'thumb', values: R.values[k], height: 'var(--thumb-h)', labels: P.labels,
    panel: '#07061A', stroke: '#BEB8E6',
  }));
  sfx.play(you > det ? 'win' : det > you ? 'lose' : 'detectors');
  setTimeout(() => { if (S.screen === 'summary') music.play(); }, 2200);
  app.querySelector('#board').onclick = () => { sfx.play('tick'); renderBoard(R.id).catch(fail); };
  app.querySelector('#again').onclick = () => { sfx.play('coin'); startRound().catch(fail); };
}

// ------------------------------------------------------------------ 5. Leaderboard

async function renderBoard(highlight = null) {
  const data = await api('/api/stats');
  const st = data.stats;
  const rows = boardRows(data.leaderboard, st.det_avg, 8).map((r) => {
    if (r.ref) {
      return `<div class="brow ref"><span class="rank">REF</span>
        <span class="name"><b>DETECTORS</b><span class="refnote">reference · avg per round</span></span>
        <span class="rpips"></span><span class="score">${fmtRef(r.score)}</span></div>`;
    }
    const me = highlight && r.round_id === highlight;
    const res = (r.results || '').padEnd(data.round_size, '_').split('')
      .map((c) => `<span class="diamond ${c}"></span>`).join('');
    return `<div class="brow${me ? ' me' : ''}${r.blank ? ' blank' : ''}">
      <span class="rank">${r.rank}</span>
      <span class="name"><b>${esc(r.name)}</b>${me ? '<span class="badge">YOU · NEW</span>' : ''}</span>
      <span class="rpips">${res}</span>
      <span class="score">${r.blank ? '00' : fmtTot(r.score)}</span></div>`;
  }).join('');
  const empty = data.leaderboard.length === 0;

  show('board', `<div class="page fit dots board-page">
    <header class="board-head">
      <div class="logo"><svg width="30" height="30" viewBox="0 0 24 24" aria-hidden="true" style="fill:none;stroke-width:1.8px;stroke-linecap:round;stroke-linejoin:round"><path d="M2 15 L6 13 L9 16 L12 9 L15 14 L18 12 L22 13" style="stroke:#22D3EE"/><path d="M12 2 L12 22" style="stroke:#FF3D9A"/></svg>NEEDLE</div>
      <h1 class="glitch">HIGH SCORES</h1>
      <span class="top-right"><span class="when">Today · ICDE 2027</span><button class="hud-btn" type="button" data-mute title="Music and sounds on or off (M)"></button></span>
    </header>
    <div class="board-wrap">
      <section class="cabinet board" aria-label="Leaderboard">
        <div class="brow headrow"><span>Rank</span><span>Name</span><span>Series vs detectors</span><span style="text-align:right">Score</span></div>
        ${rows}
        ${empty ? `<div class="board-empty"><b>NO SCORES YET</b><span>The detectors are waiting. Be the first to beat them.</span></div>` : ''}
        <div class="legend">
          <span><span class="diamond" style="color:var(--player)"></span>won</span>
          <span><span class="diamond hollow" style="color:var(--text-2)"></span>tie</span>
          <span><span class="diamond" style="color:var(--det)"></span>detectors won</span>
        </div>
      </section>
      <aside class="board-side">
        <section class="panel">
          <h2 class="eyebrow">Humans vs detectors</h2>
          <div style="display:flex;flex-direction:column;gap:2px">
            <span class="pct">${st.humans_found_pct ?? '--'}%</span>
            <span class="pct-txt">of the anomalies the detectors missed were found by a human.</span>
          </div>
          <div class="pills"><span style="color:var(--yellow)">${st.plays} play${st.plays === 1 ? '' : 's'}</span><span>${data.round_size} series a round</span></div>
          <div aria-hidden="true" style="filter:drop-shadow(0 0 5px rgba(34,211,238,0.7))"><div id="attract"></div></div>
        </section>
        <section class="panel callout cta">
          <b>CAN YOU FIND WHAT THE DETECTORS CANNOT?</b>
          <button class="btn btn-primary" type="button" id="play">PRESS PLAY</button>
          <span>Two minutes. No account. Plays are logged anonymously.</span>
        </section>
      </aside>
    </div>
  </div>`);

  chart('#attract', { mode: 'thumb', values: attractSeries(), height: 'var(--side-attract-h)', panel: 'transparent', stroke: '#22D3EE' });
  music.play();
  app.querySelector('#play').onclick = () => { sfx.play('tick'); S.nick = ''; renderStart(); };
  every(BOARD_REFRESH_MS, () => {
    if (Date.now() - lastInput > BOARD_REFRESH_MS) renderBoard(highlight).catch(console.warn);
  });
}

// ------------------------------------------------------------------ sound toggle

// One switch for music and sound effects, in every screen's top row; M
// toggles it too.
function showMute() {
  document.querySelectorAll('[data-mute]').forEach((b) => {
    b.setAttribute('aria-pressed', String(!sfx.muted));
    b.textContent = sfx.muted ? '♪ Sound off' : '♪ Sound on';
  });
}
function toggleMute() { setMuted(!sfx.muted); showMute(); }
document.addEventListener('click', (e) => { if (e.target.closest('[data-mute]')) toggleMute(); });
window.addEventListener('keydown', (e) => {
  if (e.target.closest('input, textarea')) return;
  if (e.key === 'm' || e.key === 'M') toggleMute();
  else if (e.key === 'Escape') askQuit();
});
showMute();

// ------------------------------------------------------------------ boot

const start = new URLSearchParams(location.search).get('screen');
if (start === 'board') renderBoard().catch(fail);
else renderStart();
