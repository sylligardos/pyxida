// Needle -- sound effects, synthesised in the browser with Web Audio.
// No audio files and no licences: every sound is a few oscillators.
//
// Three styles to choose from (see /static/audition.html):
//   arcade   square waves, short and bright, the coin-op classic
//   neon     triangle and sine with an echo, softer, synthwave
//   laser    saw sweeps and noise, more aggressive
//
//   import { sfx, music } from './sfx.js';
//   sfx.play('hit');            // in the current style
//   sfx.play('hit', 'neon');    // in a given style
//   music.play(); music.stop(); // the attract-screen loop, faded
//
// Browsers allow sound only after the first click or key press; until then
// everything here is silently skipped.

let ctx = null, master = null, echo = null;

function audio() {
  if (!ctx) {
    ctx = new (window.AudioContext || window.webkitAudioContext)();
    master = ctx.createGain();
    master.gain.value = 0.35;
    master.connect(ctx.destination);
    // A short feedback delay, used by the neon style.
    echo = ctx.createDelay();
    echo.delayTime.value = 0.14;
    const fb = ctx.createGain();
    fb.gain.value = 0.32;
    const wet = ctx.createGain();
    wet.gain.value = 0.45;
    echo.connect(fb); fb.connect(echo); echo.connect(wet); wet.connect(master);
  }
  if (ctx.state === 'suspended') ctx.resume();
  return ctx;
}

const STYLES = {
  arcade: { wave: 'square', attack: 0.003, gain: 0.5, echo: false, slide: 0 },
  neon: { wave: 'triangle', attack: 0.01, gain: 0.9, echo: true, slide: 0 },
  laser: { wave: 'sawtooth', attack: 0.002, gain: 0.35, echo: false, slide: 1 },
};

// One note: frequency f (sliding to f1), starting `at` seconds from now.
function tone(st, { f, f1 = f, at = 0, dur = 0.1, vol = 1, wave }) {
  const c = audio();
  const t = c.currentTime + at;
  const o = c.createOscillator();
  const g = c.createGain();
  o.type = wave || st.wave;
  o.frequency.setValueAtTime(f, t);
  if (f1 !== f) o.frequency.exponentialRampToValueAtTime(f1, t + dur);
  const peak = st.gain * vol;
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(peak, t + st.attack);
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  o.connect(g);
  g.connect(master);
  if (st.echo) g.connect(echo);
  o.start(t);
  o.stop(t + dur + 0.02);
}

function noise(st, { at = 0, dur = 0.15, vol = 0.4, from = 4000, to = 300 }) {
  const c = audio();
  const t = c.currentTime + at;
  const buf = c.createBuffer(1, Math.ceil(c.sampleRate * dur), c.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  const src = c.createBufferSource();
  src.buffer = buf;
  const filt = c.createBiquadFilter();
  filt.type = 'lowpass';
  filt.frequency.setValueAtTime(from, t);
  filt.frequency.exponentialRampToValueAtTime(to, t + dur);
  const g = c.createGain();
  g.gain.setValueAtTime(vol * st.gain, t);
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  src.connect(filt); filt.connect(g); g.connect(master);
  src.start(t);
}

const N = (semis) => 440 * Math.pow(2, (semis - 9) / 12);   // semitones from C4 -> Hz, C4 = 0
const seq = (st, notes, step, dur, opts = {}) =>
  notes.forEach((n, k) => n !== null && tone(st, { f: N(n), at: k * step, dur, ...opts }));

// Each event, written once; the style changes the timbre and a few details.
const EVENTS = {
  tick: (st) => tone(st, { f: N(24), dur: 0.04, vol: 0.5 }),
  coin: (st) => {                         // PRESS PLAY: the coin-drop "bling"
    tone(st, { f: N(23), dur: 0.08 });
    tone(st, { f: N(28), at: 0.08, dur: st.echo ? 0.5 : 0.35 });
  },
  mark: (st) => tone(st, { f: N(19), f1: st.slide ? N(31) : N(26), dur: 0.07, vol: 0.7 }),
  remove: (st) => tone(st, { f: N(24), f1: N(12), dur: 0.08, vol: 0.6 }),
  limit: (st) => {                        // out of ranges
    tone(st, { f: N(-5), dur: 0.12, vol: 0.7, wave: st.wave === 'triangle' ? 'square' : st.wave });
    tone(st, { f: N(-6), at: 0.13, dur: 0.16, vol: 0.7, wave: st.wave === 'triangle' ? 'square' : st.wave });
  },
  submit: (st) => {
    tone(st, { f: N(12), f1: N(36), dur: 0.22, vol: 0.7 });
    if (st.slide) noise(st, { dur: 0.25, vol: 0.25, from: 800, to: 6000 });
  },
  hit: (st) => seq(st, [12, 16, 19, 24, 28], 0.06, 0.12),     // you found it: up-arpeggio
  detectors: (st) => seq(st, [7, 7, 0], 0.11, 0.14, { vol: 0.7 }),   // the detectors got it, you did not
  miss: (st) => {                         // false alarm / nobody found it: the "wah wah"
    tone(st, { f: N(7), f1: N(5), dur: 0.22, vol: 0.7 });
    tone(st, { f: N(5), f1: N(-2), at: 0.24, dur: 0.4, vol: 0.7 });
  },
  clean: (st) => seq(st, [24, 31, 36, 31, 36], 0.05, 0.1, { vol: 0.6 }),   // decoy left clean: sparkle
  win: (st) => {                          // round won: fanfare
    seq(st, [12, 12, 12, 16, null, 14, 16, null, 19], 0.1, 0.12);
    tone(st, { f: N(24), at: 0.95, dur: 0.6 });
    tone(st, { f: N(19), at: 0.95, dur: 0.6, vol: 0.5 });
  },
  clock: (st) => tone(st, { f: N(-12), dur: 0.05, vol: 0.35 }),       // last seconds: "tick"
  clock2: (st) => tone(st, { f: N(-17), dur: 0.05, vol: 0.35 }),      // ...and "tock"
  hurry: (st) => tone(st, { f: N(0), dur: 0.05, vol: 0.4 }),          // last three seconds
  timeup: (st) => {                       // time is up: a short buzzer
    tone(st, { f: N(-10), dur: 0.35, vol: 0.6, wave: 'square' });
    tone(st, { f: N(-9.5), dur: 0.35, vol: 0.4, wave: 'sawtooth' });
  },
  lose: (st) => {                         // round lost
    seq(st, [7, 6, 5], 0.22, 0.2, { vol: 0.7 });
    tone(st, { f: N(4), f1: N(-8), at: 0.66, dur: 0.7, vol: 0.7 });
    if (st.slide) noise(st, { at: 0.66, dur: 0.6, vol: 0.2, from: 2000, to: 100 });
  },
};

const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* private window */ } },
};

export const sfx = {
  style: 'arcade',
  muted: store.get('needle-muted') === '1',
  events: Object.keys(EVENTS),
  styles: Object.keys(STYLES),
  play(event, style = this.style) {
    if (this.muted || !EVENTS[event]) return;
    try { EVENTS[event](STYLES[style]); } catch (e) { console.warn(e); }
  },
};

// The attract-screen music: one looped track, faded in and out.
const MUSIC_VOLUME = 0.28;
export const music = {
  el: null,
  wanted: false,
  fade: null,
  load() {
    if (!this.el) {
      this.el = new Audio('/static/audio/battle-loop.ogg');
      this.el.loop = true;
      this.el.volume = 0;
    }
    return this.el;
  },
  ramp(to, ms, then) {
    const el = this.load();
    clearInterval(this.fade);
    const from = el.volume, t0 = performance.now();
    this.fade = setInterval(() => {
      const k = Math.min(1, (performance.now() - t0) / ms);
      el.volume = from + (to - from) * k;
      if (k >= 1) { clearInterval(this.fade); if (then) then(); }
    }, 40);
  },
  play() {
    this.wanted = true;
    if (sfx.muted) return;
    const el = this.load();
    el.play().then(() => { if (this.wanted) this.ramp(MUSIC_VOLUME, 800); else el.pause(); })
      .catch(() => { /* waits for a click */ });
  },
  stop(ms = 600) {
    this.wanted = false;
    if (!this.el) return;
    this.ramp(0, ms, () => this.el.pause());
  },
};

export function setMuted(m) {
  sfx.muted = m;
  store.set('needle-muted', m ? '1' : '0');
  if (m && music.el) { clearInterval(music.fade); music.el.pause(); }
  if (m) ambient.halt();
  if (!m && music.wanted) music.play();
  if (!m && ambient.wanted) ambient.resume();
}

// The first click or key unlocks audio; start the music if a screen wants it.
for (const ev of ['pointerdown', 'keydown']) {
  window.addEventListener(ev, () => {
    audio();
    if (music.wanted && music.el && music.el.paused && !sfx.muted) music.play();
  }, { capture: true });
}

// ---------------------------------------------------------------------------
// In-round background: something quiet that says "the clock is running".
// Each kind reacts to urgency, 0 at the start of a series and 1 at time up.
//
//   ambient.start('march'); ambient.update(0.4); ambient.stop();
// ---------------------------------------------------------------------------

const lerp = (a, b, k) => a + (b - a) * k;

// Urgency mostly builds in the last third, so the start of a series is calm.
const curve = (u) => Math.pow(Math.min(1, Math.max(0, u)), 1.8);

const AMBIENT = {
  // Four descending bass notes, Space Invaders style; tempo is the timer.
  march: {
    beat: (k, u) => {
      const st = STYLES.arcade;
      tone(st, { f: N([-22, -24, -26, -27][k % 4]), dur: 0.09, vol: 0.32 });
      return lerp(620, 190, curve(u));
    },
  },
  // Lub-dub, quickening.
  heartbeat: {
    beat: (k, u) => {
      const st = { ...STYLES.neon, echo: false };
      tone(st, { f: 58, f1: 40, dur: 0.12, vol: 0.9, wave: 'sine' });
      tone(st, { f: 52, f1: 38, at: 0.18, dur: 0.14, vol: 0.7, wave: 'sine' });
      return lerp(1150, 430, curve(u));
    },
  },
  // A scanner ping with echo; closer together, a little higher.
  sonar: {
    beat: (k, u) => {
      const st = STYLES.neon;
      const f = lerp(1180, 1580, curve(u));
      tone(st, { f, dur: 0.5, vol: 0.18, wave: 'sine' });
      return lerp(2600, 700, curve(u));
    },
  },
  // Two detuned saws through a low-pass; pitch and brightness rise.
  drone: {
    start() {
      const c = audio();
      const g = c.createGain(); g.gain.value = 0.0001;
      const filt = c.createBiquadFilter(); filt.type = 'lowpass'; filt.frequency.value = 220; filt.Q.value = 6;
      const lfo = c.createOscillator(); lfo.frequency.value = 0.25;
      const lfoGain = c.createGain(); lfoGain.gain.value = 0.02;
      const oscs = [0, 7].map((det) => {
        const o = c.createOscillator(); o.type = 'sawtooth'; o.frequency.value = N(-27); o.detune.value = det;
        o.connect(filt); o.start(); return o;
      });
      lfo.connect(lfoGain); lfoGain.connect(g.gain); lfo.start();
      filt.connect(g); g.connect(master);
      g.gain.exponentialRampToValueAtTime(0.06, c.currentTime + 1.5);
      return { g, filt, lfo, oscs };
    },
    update(n, u) {
      const t = audio().currentTime, k = curve(u);
      n.filt.frequency.setTargetAtTime(lerp(220, 1400, k), t, 0.3);
      n.oscs.forEach((o) => o.frequency.setTargetAtTime(N(lerp(-27, -15, k)), t, 0.3));
      n.lfo.frequency.setTargetAtTime(lerp(0.25, 6, k), t, 0.3);
    },
    stop(n) {
      const t = audio().currentTime;
      n.g.gain.setTargetAtTime(0.0001, t, 0.15);
      setTimeout(() => { n.oscs.forEach((o) => o.stop()); n.lfo.stop(); }, 600);
    },
  },
  // The attract track, as if from the next room; clearer as time runs out.
  muffled: {
    start() {
      const c = audio();
      const el = new Audio('/static/audio/battle-loop.ogg');
      el.loop = true;
      const src = c.createMediaElementSource(el);
      const filt = c.createBiquadFilter(); filt.type = 'lowpass'; filt.frequency.value = 350;
      const g = c.createGain(); g.gain.value = 0.0001;
      src.connect(filt); filt.connect(g); g.connect(master);
      el.play().catch(() => {});
      g.gain.exponentialRampToValueAtTime(0.5, c.currentTime + 1.2);
      return { el, g, filt };
    },
    update(n, u) {
      const t = audio().currentTime, k = curve(u);
      n.filt.frequency.setTargetAtTime(lerp(350, 2600, k), t, 0.4);
      n.el.playbackRate = lerp(1, 1.12, k);
    },
    stop(n) {
      n.g.gain.setTargetAtTime(0.0001, audio().currentTime, 0.15);
      setTimeout(() => n.el.pause(), 600);
    },
  },
};

export const ambient = {
  kinds: Object.keys(AMBIENT),
  kind: null, node: null, u: 0, timer: null, k: 0,
  wanted: null,     // the kind a screen asked for; muting halts it, unmuting resumes it
  start(kind) {
    this.stop();
    this.wanted = AMBIENT[kind] ? kind : null;
    this.u = 0;
    this.resume();
  },
  resume() {
    const kind = this.wanted;
    this.halt();
    if (!kind || sfx.muted) return;
    this.kind = kind; this.k = 0;
    const A = AMBIENT[kind];
    if (A.start) this.node = A.start();
    if (A.beat) {
      const step = () => {
        if (this.kind !== kind || sfx.muted) return;
        const wait = A.beat(this.k++, this.u);
        this.timer = setTimeout(step, wait);
      };
      step();
    }
  },
  update(u) {
    this.u = u;
    const A = AMBIENT[this.kind];
    if (A && A.update && this.node) A.update(this.node, u);
  },
  stop() {
    this.wanted = null;
    this.halt();
  },
  halt() {
    const A = AMBIENT[this.kind];
    clearTimeout(this.timer);
    if (A && A.stop && this.node) A.stop(this.node);
    this.kind = null; this.node = null;
  },
};
