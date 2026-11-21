// Background Eraser — 추론 + 정밀 보정 엔진 (모듈 워커)
// 1) ONNX 분할 모델(BiRefNet / RMBG / MODNet)로 알파 마스크 추론 (WebGPU 또는 WASM)
// 2) 좌우 반전 TTA 평균
// 3) 고속 가이디드 필터로 원본 해상도까지 경계 업샘플링
// 4) Blur-Fusion 전경색 추정(Forte & Pitié 2021)으로 배경색 번짐 제거
// ONNX Runtime은 설정을 받은 뒤 불러온다 (사이트·아티팩트: 옆 파일 / 단일 HTML: CDN에서 받아 기기에 저장)
let ort = null;
const THREADS = self.crossOriginIsolated ? Math.max(1, Math.min(8, (navigator.hardwareConcurrency || 4) - 1)) : 1;
const here = (rel) => { try { return new URL(rel, import.meta.url).href; } catch (e) { return null; } };

const MODEL_CACHE = 'bgeraser-models-v1';
// 실행 환경 설정 (사이트: 비어 있음 / 아티팩트: 모델·런타임을 조각 파일로 받음)
let CFG = { parts: {} };
let configured, setConfigured;
configured = new Promise((r) => (setConfigured = r));
async function fetchParts(list, id, total) {
  const bufs = []; let got = 0;
  for (const u of list) {
    const r = await fetch(new URL(u, self.location.href).href);
    if (!r.ok) throw Object.assign(new Error('파일 조각을 읽지 못했습니다 (HTTP ' + r.status + ')'), { code: 'FETCH' });
    const b = new Uint8Array(await r.arrayBuffer()); bufs.push(b); got += b.length;
    if (id != null) post({ type: 'download', id, got, total: total || got });
  }
  const out = new Uint8Array(got); let o = 0; for (const b of bufs) { out.set(b, o); o += b.length; }
  return out;
}
const blobUrl = (bytes, type) => URL.createObjectURL(new Blob([bytes], { type }));
async function applyConfig(c) {
  CFG = Object.assign({ parts: {}, mirrors: {} }, c || {});
  if (CFG.ortCdn) {
    // 단일 HTML: 런타임 3개 파일을 CDN에서 한 번 받아 기기에 저장하고 blob URL로 띄움
    const base = CFG.ortCdn;
    const bundle = await fetchModel(base + 'ort.webgpu.bundle.min.mjs', 0, null, true);
    const glue = await fetchModel(base + 'ort-wasm-simd-threaded.asyncify.mjs', 0, null, true);
    const wasm = await fetchModel(base + 'ort-wasm-simd-threaded.asyncify.wasm', 28747738, 'rt', true);
    ort = await import(blobUrl(bundle, 'text/javascript'));
    ort.env.wasm.wasmPaths = { mjs: blobUrl(glue, 'text/javascript'), wasm: blobUrl(wasm, 'application/wasm') };
  } else {
    ort = await import(here('./ort/ort.webgpu.bundle.min.mjs'));
    ort.env.wasm.wasmPaths = here('./ort/');
    if (CFG.ortParts && CFG.ortParts.length) {
      const wasm = await fetchParts(CFG.ortParts);
      ort.env.wasm.wasmPaths = { mjs: here('./ort/ort-wasm-simd-threaded.asyncify.mjs'), wasm: blobUrl(wasm, 'application/wasm') };
    }
  }
  ort.env.wasm.numThreads = THREADS;
  ort.env.logLevel = 'error';
  setConfigured();
}

// ---------- 저장소: Cache API, 안 되면(file:// 등) IndexedDB ----------
let idbP = null;
function idb() {
  if (!idbP) idbP = new Promise((res, rej) => { const r = indexedDB.open('bgeraser-files', 1); r.onupgradeneeded = () => r.result.createObjectStore('f'); r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); });
  return idbP;
}
const idbReq = (mode, fn) => idb().then((db) => new Promise((res, rej) => { const t = db.transaction('f', mode); const q = fn(t.objectStore('f')); t.oncomplete = () => res(q && q.result); t.onerror = () => rej(t.error); t.onabort = () => rej(t.error); }));
async function cacheGet(url) {
  try { const c = await caches.open(MODEL_CACHE); const r = await c.match(url); if (r) return new Uint8Array(await r.arrayBuffer()); } catch (e) {}
  try { const v = await idbReq('readonly', (st) => st.get(url)); if (v) return new Uint8Array(v); } catch (e) {}
  return null;
}
async function cachePut(url, data) {
  try { const c = await caches.open(MODEL_CACHE); await c.put(url, new Response(data, { headers: { 'content-type': 'application/octet-stream' } })); return true; } catch (e) {}
  try { await idbReq('readwrite', (st) => st.put(data.buffer.byteLength === data.length ? data.buffer : data.slice().buffer, url)); return true; } catch (e) {}
  return false;
}
async function cacheKeys() {
  const out = new Set();
  try { const c = await caches.open(MODEL_CACHE); for (const r of await c.keys()) out.add(r.url); } catch (e) {}
  try { for (const k of (await idbReq('readonly', (st) => st.getAllKeys())) || []) out.add(String(k)); } catch (e) {}
  return [...out];
}
async function cacheDelete(urls) {
  try { const c = await caches.open(MODEL_CACHE); for (const u of urls) await c.delete(u); } catch (e) {}
  try { await idbReq('readwrite', (st) => { for (const u of urls) st.delete(u); }); } catch (e) {}
}
let session = null;
let sessionInfo = null; // { key, device, cfg }

const post = (msg, transfer) => self.postMessage(msg, transfer || []);
const progress = (id, stage, p) => post({ type: 'progress', id, stage, p });

// ---------- float16 helpers ----------
const HALF_TABLE = (() => {
  const t = new Float32Array(65536);
  for (let h = 0; h < 65536; h++) {
    const s = h & 0x8000 ? -1 : 1, e = (h >> 10) & 0x1f, m = h & 0x3ff;
    t[h] = e === 0 ? s * m * 5.960464477539063e-8 : e === 31 ? (m ? NaN : s * Infinity) : s * (1 + m / 1024) * Math.pow(2, e - 15);
  }
  return t;
})();
const _f = new Float32Array(1), _u = new Uint32Array(_f.buffer);
function toHalf(v) {
  _f[0] = v; const x = _u[0];
  const sign = (x >>> 16) & 0x8000; const e = ((x >>> 23) & 0xff) - 112; const m = x & 0x7fffff;
  if (e <= 0) { if (e < -10) return sign; const mm = (m | 0x800000) >> (1 - e); return sign + ((mm + 0x1000) >> 13); }
  if (e >= 31) return sign | 0x7c00;
  return sign + (e << 10) + ((m + 0x1000) >> 13);
}
function tensorToF32(t) {
  const d = t.data;
  if (d instanceof Float32Array) return d;
  if (d instanceof Uint16Array) { const o = new Float32Array(d.length); for (let i = 0; i < d.length; i++) o[i] = HALF_TABLE[d[i]]; return o; }
  return Float32Array.from(d);
}

// ---------- model loading ----------
async function fetchModel(url, bytesHint, id, quiet) {
  const hit = await cacheGet(url);
  if (hit) { if (!quiet) progress(id, 'cache', 1); return hit; }
  const base = here('./');
  const parts = CFG.parts[url] || (base && CFG.parts[url.replace(base, '')]);
  if (parts) {
    const data = await fetchParts(parts, id, bytesHint);
    await cachePut(url, data);
    return data;
  }
  let res = null;
  for (const u of [url, ...(CFG.mirrors[url] || [])]) {
    try { const r = await fetch(u, { mode: 'cors' }); if (r.ok) { res = r; break; } res = r; } catch (e) {}
  }
  if (!res) throw Object.assign(new Error('파일을 내려받지 못했습니다. 인터넷 연결을 확인해 주세요 (최초 1회 필요)'), { code: 'FETCH' });
  if (!res.ok) throw Object.assign(new Error('다운로드 실패 (HTTP ' + res.status + ')'), { code: 'FETCH' });
  const total = +res.headers.get('content-length') || bytesHint || 0;
  const reader = res.body.getReader();
  let buf = new Uint8Array(total || 64 * 1024 * 1024), got = 0, last = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    if (got + value.length > buf.length) { const nb = new Uint8Array(Math.max(buf.length * 1.5, got + value.length) | 0); nb.set(buf.subarray(0, got)); buf = nb; }
    buf.set(value, got); got += value.length;
    const now = performance.now();
    if (now - last > 120 && id != null) { last = now; post({ type: 'download', id, got, total }); }
  }
  if (id != null) post({ type: 'download', id, got, total: got });
  const data = got === buf.length ? buf : buf.slice(0, got);
  if (!(await cachePut(url, data))) post({ type: 'warn', message: '저장 공간이 부족해 파일을 저장하지 못했습니다. 다음 실행 때 다시 받아야 합니다.' });
  return data;
}

async function loadModel(msg) {
  const { id, key, url, bytes, device, cfg, buffer } = msg;
  if (sessionInfo && sessionInfo.key === key + '|' + device && session) { post({ type: 'loaded', id, device, reused: true, inputs: sessionInfo.inputs }); return; }
  if (session) { try { await session.release(); } catch (e) {} session = null; sessionInfo = null; }
  const data = buffer ? new Uint8Array(buffer) : await fetchModel(url, bytes, id);
  progress(id, 'init', 0);
  const opts = {
    executionProviders: device === 'webgpu' ? ['webgpu'] : ['wasm'],
    graphOptimizationLevel: 'all',
  };
  if (device === 'webgpu') opts.preferredOutputLocation = 'cpu';
  const t0 = performance.now();
  session = await ort.InferenceSession.create(data, opts);
  const meta = (session.inputMetadata && session.inputMetadata[0]) || {};
  const inputs = { name: session.inputNames[0], type: meta.type || 'float32', shape: meta.shape || null };
  sessionInfo = { key: key + '|' + device, device, cfg, inputs };
  post({ type: 'loaded', id, device, ms: performance.now() - t0, inputs });
}

// ---------- image helpers ----------
function canvas2d(w, h) {
  const c = new OffscreenCanvas(w, h);
  const ctx = c.getContext('2d', { willReadFrequently: true });
  ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
  return [c, ctx];
}
// 큰 비율 축소는 절반씩 단계적으로 줄여 계단/모아레를 막는다
function drawScaled(src, sw, sh, tw, th, flip, whiteBg) {
  let cur = src, cw = sw, ch = sh;
  while (cw / 2 > tw * 1.05 && ch / 2 > th * 1.05) {
    const nw = Math.max(tw, Math.round(cw / 2)), nh = Math.max(th, Math.round(ch / 2));
    const [c, x] = canvas2d(nw, nh); x.drawImage(cur, 0, 0, nw, nh); cur = c; cw = nw; ch = nh;
  }
  const [c, x] = canvas2d(tw, th);
  if (whiteBg) { x.fillStyle = '#fff'; x.fillRect(0, 0, tw, th); }
  if (flip) { x.translate(tw, 0); x.scale(-1, 1); }
  x.drawImage(cur, 0, 0, tw, th);
  return x.getImageData(0, 0, tw, th).data;
}

function modelInputSize(cfg, inputs, w, h) {
  const sh = inputs.shape;
  if (sh && typeof sh[2] === 'number' && typeof sh[3] === 'number' && sh[2] > 0) return [sh[3], sh[2]];
  if (cfg.dynamic) {
    const s = cfg.dynamic / Math.min(w, h);
    let tw = Math.max(32, Math.round((w * s) / 32) * 32), th = Math.max(32, Math.round((h * s) / 32) * 32);
    const lim = cfg.dynamic * 2; // 극단적 종횡비 제한
    if (tw > lim) tw = lim; if (th > lim) th = lim;
    return [tw, th];
  }
  return cfg.size;
}

async function infer(bitmap, W, H, cfg, flip) {
  const [tw, th] = modelInputSize(cfg, sessionInfo.inputs, W, H);
  const px = drawScaled(bitmap, W, H, tw, th, flip, true);
  const n = tw * th, mean = cfg.mean, std = cfg.std;
  const f = new Float32Array(3 * n);
  for (let i = 0, j = 0; i < n; i++, j += 4) {
    f[i] = (px[j] / 255 - mean[0]) / std[0];
    f[n + i] = (px[j + 1] / 255 - mean[1]) / std[1];
    f[2 * n + i] = (px[j + 2] / 255 - mean[2]) / std[2];
  }
  let tensor;
  if (sessionInfo.inputs.type === 'float16') {
    const u = new Uint16Array(f.length); for (let i = 0; i < f.length; i++) u[i] = toHalf(f[i]);
    tensor = new ort.Tensor('float16', u, [1, 3, th, tw]);
  } else tensor = new ort.Tensor('float32', f, [1, 3, th, tw]);
  const out = await session.run({ [sessionInfo.inputs.name]: tensor });
  const t = out[session.outputNames[0]];
  const dims = t.dims; const oh = dims[dims.length - 2], ow = dims[dims.length - 1];
  let m = tensorToF32(t);
  if (m.length !== ow * oh) m = m.subarray(0, ow * oh);
  m = Float32Array.from(m);
  for (const k in out) { try { out[k].dispose && out[k].dispose(); } catch (e) {} }
  let mn = Infinity, mx = -Infinity, bad = 0;
  for (let i = 0; i < m.length; i++) { const v = m[i]; if (v !== v) { bad++; continue; } if (v < mn) mn = v; if (v > mx) mx = v; }
  if (bad > m.length * 0.01 || !isFinite(mn)) throw Object.assign(new Error('모델 출력이 비정상(NaN)입니다'), { code: 'NAN' });
  const logits = cfg.out === 'logits' || (cfg.out === 'auto' && (mn < -0.05 || mx > 1.05));
  for (let i = 0; i < m.length; i++) {
    let v = m[i]; if (v !== v) v = 0;
    v = logits ? 1 / (1 + Math.exp(-v)) : v;
    m[i] = v < 0 ? 0 : v > 1 ? 1 : v;
  }
  if (flip) for (let y = 0; y < oh; y++) { const o = y * ow; for (let a = o, b = o + ow - 1; a < b; a++, b--) { const t2 = m[a]; m[a] = m[b]; m[b] = t2; } }
  return { m, w: ow, h: oh };
}

// ---------- numeric kernels ----------
function resizeBilinear(src, sw, sh, dw, dh, ch = 1) {
  const out = new Float32Array(dw * dh * ch);
  const x0 = new Int32Array(dw), x1 = new Int32Array(dw), fx = new Float32Array(dw);
  for (let x = 0; x < dw; x++) {
    let s = ((x + 0.5) * sw) / dw - 0.5; if (s < 0) s = 0; if (s > sw - 1) s = sw - 1;
    const i = Math.floor(s); x0[x] = i; x1[x] = Math.min(sw - 1, i + 1); fx[x] = s - i;
  }
  for (let y = 0; y < dh; y++) {
    let s = ((y + 0.5) * sh) / dh - 0.5; if (s < 0) s = 0; if (s > sh - 1) s = sh - 1;
    const y0 = Math.floor(s), y1 = Math.min(sh - 1, y0 + 1), fy = s - y0;
    const r0 = y0 * sw, r1 = y1 * sw, o = y * dw;
    for (let x = 0; x < dw; x++) {
      const a = x0[x], b = x1[x], f = fx[x];
      for (let c = 0; c < ch; c++) {
        const t = src[(r0 + a) * ch + c] + (src[(r0 + b) * ch + c] - src[(r0 + a) * ch + c]) * f;
        const u = src[(r1 + a) * ch + c] + (src[(r1 + b) * ch + c] - src[(r1 + a) * ch + c]) * f;
        out[(o + x) * ch + c] = t + (u - t) * fy;
      }
    }
  }
  return out;
}

// 분리형 박스 블러 (경계는 유효 픽셀 평균) — O(N)
function boxBlur(src, w, h, r, out) {
  out = out || new Float32Array(w * h);
  if (r < 1) { out.set(src); return out; }
  const tmp = new Float32Array(w * h);
  for (let y = 0; y < h; y++) {
    const o = y * w; let sum = 0, cnt = 0;
    for (let x = 0; x <= r && x < w; x++) { sum += src[o + x]; cnt++; }
    for (let x = 0; x < w; x++) {
      tmp[o + x] = sum / cnt;
      const add = x + r + 1, rem = x - r;
      if (add < w) { sum += src[o + add]; cnt++; }
      if (rem >= 0) { sum -= src[o + rem]; cnt--; }
    }
  }
  const col = new Float64Array(w); let cnt = 0;
  for (let y = 0; y <= r && y < h; y++) { const o = y * w; for (let x = 0; x < w; x++) col[x] += tmp[o + x]; cnt++; }
  for (let y = 0; y < h; y++) {
    const o = y * w, inv = 1 / cnt;
    for (let x = 0; x < w; x++) out[o + x] = col[x] * inv;
    const add = y + r + 1, rem = y - r;
    if (add < h) { const a = add * w; for (let x = 0; x < w; x++) col[x] += tmp[a + x]; cnt++; }
    if (rem >= 0) { const a = rem * w; for (let x = 0; x < w; x++) col[x] -= tmp[a + x]; cnt--; }
  }
  return out;
}

// 그레이 가이드 가이디드 필터 → q = a·I + b 의 a, b 반환
function guidedAB(I, p, w, h, r, eps) {
  const n = w * h;
  const Ip = new Float32Array(n), II = new Float32Array(n);
  for (let i = 0; i < n; i++) { Ip[i] = I[i] * p[i]; II[i] = I[i] * I[i]; }
  const mI = boxBlur(I, w, h, r), mp = boxBlur(p, w, h, r), mIp = boxBlur(Ip, w, h, r), mII = boxBlur(II, w, h, r, II);
  const a = Ip, b = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const cov = mIp[i] - mI[i] * mp[i], v = mII[i] - mI[i] * mI[i];
    a[i] = cov / (v + eps); b[i] = mp[i] - a[i] * mI[i];
  }
  return [boxBlur(a, w, h, r, mIp), boxBlur(b, w, h, r, mII)];
}

// Blur-Fusion 전경 추정 1회 (채널 인터리브 RGB, 0..1)
function blurFusion(img, F, B, alpha, w, h, r) {
  const n = w * h;
  const bA = boxBlur(alpha, w, h, r);
  const ch = new Float32Array(n), t = new Float32Array(n);
  const bF = new Float32Array(3 * n), bB = new Float32Array(3 * n);
  for (let c = 0; c < 3; c++) {
    for (let i = 0; i < n; i++) ch[i] = F[i * 3 + c] * alpha[i];
    boxBlur(ch, w, h, r, t);
    for (let i = 0; i < n; i++) bF[i * 3 + c] = t[i] / (bA[i] + 1e-5);
    for (let i = 0; i < n; i++) ch[i] = B[i * 3 + c] * (1 - alpha[i]);
    boxBlur(ch, w, h, r, t);
    for (let i = 0; i < n; i++) bB[i * 3 + c] = t[i] / (1 - bA[i] + 1e-5);
  }
  const Fo = new Float32Array(3 * n);
  for (let i = 0; i < n; i++) {
    const a = alpha[i];
    for (let c = 0; c < 3; c++) {
      const k = i * 3 + c;
      let v = bF[k] + a * (img[k] - a * bF[k] - (1 - a) * bB[k]);
      Fo[k] = v < 0 ? 0 : v > 1 ? 1 : v;
    }
  }
  return { F: Fo, bF, bB };
}

// ---------- full pipeline ----------
async function run(msg) {
  const { id, bitmap, opts } = msg;
  if (!session) throw new Error('모델이 아직 로드되지 않았습니다');
  const cfg = sessionInfo.cfg;
  const W = bitmap.width, H = bitmap.height, N = W * H;
  const t0 = performance.now();

  progress(id, 'infer', 0);
  let { m, w: mw, h: mh } = await infer(bitmap, W, H, cfg, false);
  if (opts.tta) {
    progress(id, 'infer', 0.5);
    const f = await infer(bitmap, W, H, cfg, true);
    if (f.w === mw && f.h === mh) for (let i = 0; i < m.length; i++) m[i] = (m[i] + f.m[i]) * 0.5;
  }
  const tInfer = performance.now() - t0;
  progress(id, 'refine', 0);

  // 원본 픽셀
  const [fc, fx] = canvas2d(W, H);
  fx.drawImage(bitmap, 0, 0);
  const orig = fx.getImageData(0, 0, W, H).data;
  let hasAlpha = false;
  for (let i = 3; i < orig.length; i += 4) if (orig[i] < 255) { hasAlpha = true; break; }

  // 저해상 작업 공간 (≤ 약 2.2MP)
  const LIM = 2.2e6;
  const ls = N > LIM ? Math.sqrt(LIM / N) : 1;
  const lw = Math.max(1, Math.round(W * ls)), lh = Math.max(1, Math.round(H * ls)), ln = lw * lh;
  const lowPx = ls === 1 ? orig : drawScaled(fc, W, H, lw, lh, false, false);
  const Ilow = new Float32Array(ln), imgLow = new Float32Array(ln * 3);
  for (let i = 0, j = 0; i < ln; i++, j += 4) {
    const r = lowPx[j] / 255, g = lowPx[j + 1] / 255, b = lowPx[j + 2] / 255;
    imgLow[i * 3] = r; imgLow[i * 3 + 1] = g; imgLow[i * 3 + 2] = b;
    Ilow[i] = 0.299 * r + 0.587 * g + 0.114 * b;
  }
  const p = resizeBilinear(m, mw, mh, lw, lh);
  m = null;

  // 정밀 경계: α = c0 + c1·I (전해상 I 사용)
  const C = 8; // [c0, c1, bF(3), bB(3)]
  const maps = new Float32Array(ln * C);
  const alphaLow = new Float32Array(ln);
  const scaleUp = Math.max(lw / mw, lh / mh, W / mw, H / mh);
  if (opts.refine) {
    const r = Math.max(2, Math.min(12, Math.round(1.5 + Math.max(lw, lh) / 512)));
    const eps = 1e-3;
    const [a, b] = guidedAB(Ilow, p, lw, lh, r, eps);
    // 불확실 경계 띠에서만 가이디드 결과 사용
    const ps = boxBlur(p, lw, lh, Math.max(2, Math.round(r * 1.5 + scaleUp)));
    for (let i = 0; i < ln; i++) {
      let u = 8 * ps[i] * (1 - ps[i]); u = u > 1 ? 1 : u;
      const k = i * C;
      maps[k] = p[i] * (1 - u) + u * b[i];
      maps[k + 1] = u * a[i];
      let al = maps[k] + maps[k + 1] * Ilow[i];
      alphaLow[i] = al < 0 ? 0 : al > 1 ? 1 : al;
    }
  } else {
    for (let i = 0; i < ln; i++) { maps[i * C] = p[i]; alphaLow[i] = p[i]; }
  }
  progress(id, 'refine', 0.4);

  if (opts.decontam) {
    const L = Math.max(lw, lh);
    const r1 = Math.max(6, Math.round(L * 0.045)), r2 = Math.max(2, Math.round(L * 0.003));
    const s1 = blurFusion(imgLow, imgLow, imgLow, alphaLow, lw, lh, r1);
    progress(id, 'refine', 0.65);
    const s2 = blurFusion(imgLow, s1.F, s1.bB, alphaLow, lw, lh, r2);
    for (let i = 0; i < ln; i++) {
      const k = i * C, j = i * 3;
      maps[k + 2] = s2.bF[j]; maps[k + 3] = s2.bF[j + 1]; maps[k + 4] = s2.bF[j + 2];
      maps[k + 5] = s2.bB[j]; maps[k + 6] = s2.bB[j + 1]; maps[k + 7] = s2.bB[j + 2];
    }
  }
  progress(id, 'refine', 0.8);

  // 전해상 합성
  const alpha = new Uint8Array(N);
  const fg = new Uint8ClampedArray(N * 4);
  const x0 = new Int32Array(W), x1 = new Int32Array(W), fxs = new Float32Array(W);
  for (let x = 0; x < W; x++) {
    let s = ((x + 0.5) * lw) / W - 0.5; if (s < 0) s = 0; if (s > lw - 1) s = lw - 1;
    const i = Math.floor(s); x0[x] = i * C; x1[x] = Math.min(lw - 1, i + 1) * C; fxs[x] = s - i;
  }
  const v = new Float32Array(C);
  const dec = !!opts.decontam;
  for (let y = 0; y < H; y++) {
    let s = ((y + 0.5) * lh) / H - 0.5; if (s < 0) s = 0; if (s > lh - 1) s = lh - 1;
    const y0 = Math.floor(s), fy = s - y0;
    const r0 = y0 * lw * C, r1 = Math.min(lh - 1, y0 + 1) * lw * C;
    const nc = dec ? C : 2;
    for (let x = 0; x < W; x++) {
      const a = x0[x], b = x1[x], f = fxs[x];
      for (let c = 0; c < nc; c++) {
        const t = maps[r0 + a + c] + (maps[r0 + b + c] - maps[r0 + a + c]) * f;
        const u = maps[r1 + a + c] + (maps[r1 + b + c] - maps[r1 + a + c]) * f;
        v[c] = t + (u - t) * fy;
      }
      const j = (y * W + x) * 4;
      const R = orig[j] / 255, G = orig[j + 1] / 255, B = orig[j + 2] / 255;
      let al = v[0] + v[1] * (0.299 * R + 0.587 * G + 0.114 * B);
      al = al < 0 ? 0 : al > 1 ? 1 : al;
      if (hasAlpha) al *= orig[j + 3] / 255;
      const A8 = Math.round(al * 255);
      alpha[y * W + x] = A8;
      if (!dec || A8 >= 253 || A8 === 0) { fg[j] = orig[j]; fg[j + 1] = orig[j + 1]; fg[j + 2] = orig[j + 2]; }
      else {
        const k = al;
        let fr = v[2] + k * (R - k * v[2] - (1 - k) * v[5]);
        let fgc = v[3] + k * (G - k * v[3] - (1 - k) * v[6]);
        let fb = v[4] + k * (B - k * v[4] - (1 - k) * v[7]);
        fg[j] = fr * 255; fg[j + 1] = fgc * 255; fg[j + 2] = fb * 255;
      }
      fg[j + 3] = A8;
    }
    if ((y & 255) === 0) progress(id, 'refine', 0.8 + 0.2 * (y / H));
  }
  bitmap.close && bitmap.close();
  post({ type: 'result', id, W, H, alpha, fg, hasAlpha, ms: performance.now() - t0, inferMs: tInfer, device: sessionInfo.device, model: [mw, mh] }, [alpha.buffer, fg.buffer]);
}

// ---------- AI 선택 브러시 (MobileSAM, 앱에 포함된 모델) ----------
const SAM = { enc: null, dec: null, emb: null, key: null, W: 0, H: 0, s: 1, nw: 0, nh: 0 };
const SAM_FILES = { enc: { bytes: 28106856 }, dec: { bytes: 16509322 } };
async function samLoad(id) {
  SAM_FILES.enc.url = (CFG.sam && CFG.sam.enc) || here('./models/mobile_sam.encoder.onnx');
  SAM_FILES.dec.url = (CFG.sam && CFG.sam.dec) || here('./models/sam_decoder.onnx');
  if (SAM.enc && SAM.dec) return;
  const opts = { executionProviders: ['wasm'], graphOptimizationLevel: 'all' };
  if (!SAM.enc) SAM.enc = await ort.InferenceSession.create(await fetchModel(SAM_FILES.enc.url, SAM_FILES.enc.bytes, id), opts);
  if (!SAM.dec) SAM.dec = await ort.InferenceSession.create(await fetchModel(SAM_FILES.dec.url, SAM_FILES.dec.bytes, id), opts);
}
async function samEmbed(msg) {
  const { id, key, bitmap } = msg;
  await samLoad(id);
  if (SAM.key === key && SAM.emb) { bitmap.close && bitmap.close(); post({ type: 'samReady', id, cached: true }); return; }
  progress(id, 'samEmbed', 0);
  const t0 = performance.now();
  const W = bitmap.width, H = bitmap.height, s = 1024 / Math.max(W, H);
  const nw = Math.max(1, Math.round(W * s)), nh = Math.max(1, Math.round(H * s));
  const px = drawScaled(bitmap, W, H, nw, nh, false, true);
  bitmap.close && bitmap.close();
  const S = 1024, n = S * S, f = new Float32Array(3 * n); // 정규화 후 0으로 패딩 (SAM 원본 방식)
  const mean = [0.485, 0.456, 0.406], std = [0.229, 0.224, 0.225];
  for (let y = 0; y < nh; y++) for (let x = 0; x < nw; x++) {
    const j = (y * nw + x) * 4, i = y * S + x;
    f[i] = (px[j] / 255 - mean[0]) / std[0]; f[n + i] = (px[j + 1] / 255 - mean[1]) / std[1]; f[2 * n + i] = (px[j + 2] / 255 - mean[2]) / std[2];
  }
  const out = await SAM.enc.run({ [SAM.enc.inputNames[0]]: new ort.Tensor('float32', f, [1, 3, S, S]) });
  const t = out[SAM.enc.outputNames[0]];
  SAM.emb = new ort.Tensor('float32', Float32Array.from(tensorToF32(t)), t.dims);
  Object.assign(SAM, { key, W, H, s, nw, nh });
  post({ type: 'samReady', id, ms: performance.now() - t0 });
}
async function samDecode(points, labels) {
  const { nw, nh, s } = SAM;
  const pc = [], pl = [];
  for (let i = 0; i < points.length; i++) { pc.push(points[i][0] * s, points[i][1] * s); pl.push(labels[i]); }
  pc.push(0, 0); pl.push(-1);
  const feeds = {
    image_embeddings: SAM.emb,
    point_coords: new ort.Tensor('float32', new Float32Array(pc), [1, pl.length, 2]),
    point_labels: new ort.Tensor('float32', new Float32Array(pl), [1, pl.length]),
    mask_input: new ort.Tensor('float32', new Float32Array(256 * 256), [1, 1, 256, 256]),
    has_mask_input: new ort.Tensor('float32', new Float32Array([0]), [1]),
    orig_im_size: new ort.Tensor('float32', new Float32Array([nh, nw]), [2]),
  };
  const nPos = labels.filter((l) => l === 1).length;
  const pick = (iou) => { if (nPos > 1) return 0; let k = 1; for (let i = 2; i < iou.length; i++) if (iou[i] > iou[k]) k = i; return k; };
  // 1차 예측 → 저해상 마스크를 다시 넣어 2차 정제 (SAM 반복 정제)
  let r = await SAM.dec.run(feeds);
  let k = pick(tensorToF32(r.iou_predictions));
  const low = r.low_res_masks, ls = 256 * 256;
  feeds.mask_input = new ort.Tensor('float32', Float32Array.from(tensorToF32(low).subarray(k * ls, (k + 1) * ls)), [1, 1, 256, 256]);
  feeds.has_mask_input = new ort.Tensor('float32', new Float32Array([1]), [1]);
  r = await SAM.dec.run(feeds);
  k = pick(tensorToF32(r.iou_predictions));
  const m = tensorToF32(r.masks), sz = r.masks.dims[2] * r.masks.dims[3];
  return Float32Array.from(m.subarray(k * sz, (k + 1) * sz));
}
async function samSegment(msg) {
  const { id, key, pos, neg } = msg;
  if (SAM.key !== key || !SAM.emb) throw new Error('선택용 이미지 분석이 준비되지 않았습니다');
  const t0 = performance.now();
  const allNeg = neg.flat(), allPos = pos.flat();
  const union = async (strokes, others) => {
    let acc = null;
    for (const st of strokes) {
      const lg = await samDecode([...st, ...others], [...st.map(() => 1), ...others.map(() => 0)]);
      if (!acc) acc = lg; else for (let i = 0; i < acc.length; i++) if (lg[i] > acc[i]) acc[i] = lg[i];
    }
    if (acc) for (let i = 0; i < acc.length; i++) acc[i] = 1 / (1 + Math.exp(-acc[i]));
    return acc;
  };
  // 남길 획: 빼기 획을 음성 점으로 / 뺄 획: 그 물체를 분할(남길 획은 음성 점)
  const p = pos.length ? await union(pos, allNeg) : null;
  const n = neg.length ? await union(neg, []) : null; // 빼기는 항상 우선
  const tr = []; if (p) tr.push(p.buffer); if (n) tr.push(n.buffer);
  post({ type: 'samResult', id, nw: SAM.nw, nh: SAM.nh, pos: p, neg: n, ms: performance.now() - t0 }, tr);
}

self.onmessage = async (e) => {
  const msg = e.data;
  if (msg.type === 'config') { applyConfig(msg).catch((err) => { post({ type: 'warn', message: 'AI 런타임을 불러오지 못했습니다: ' + err.message }); setConfigured(); }); return; }
  try {
    if (msg.type === 'cacheKeys') { post({ type: 'cacheKeys', id: msg.id, keys: await cacheKeys() }); return; }
    if (msg.type === 'cacheDelete') { await cacheDelete(msg.urls); post({ type: 'cacheDeleted', id: msg.id }); return; }
    if (msg.type === 'cachePut') { await cachePut(msg.url, new Uint8Array(msg.buffer)); post({ type: 'cachePutDone', id: msg.id }); return; }
    await configured;
    if (!ort) await applyConfig(CFG); // 처음 실패했으면(오프라인 등) 다시 시도
    if (msg.type === 'load') await loadModel(msg);
    else if (msg.type === 'run') await run(msg);
    else if (msg.type === 'samLoad') { await samLoad(msg.id); post({ type: 'samLoaded', id: msg.id }); }
    else if (msg.type === 'samEmbed') await samEmbed(msg);
    else if (msg.type === 'samSegment') await samSegment(msg);
    else if (msg.type === 'unload') { if (session) await session.release(); session = null; sessionInfo = null; post({ type: 'unloaded', id: msg.id }); }
  } catch (err) {
    post({ type: 'error', id: msg.id, op: msg.type, code: err && err.code, message: String((err && err.message) || err) });
  }
};
post({ type: 'ready', threads: THREADS, isolated: !!self.crossOriginIsolated });
