// Background Eraser — 추론 + 정밀 보정 엔진 (모듈 워커)
// 1) ONNX 분할 모델(BiRefNet / RMBG / MODNet)로 알파 마스크 추론 (WebGPU 또는 WASM)
// 2) 좌우 반전 TTA 평균
// 3) 고속 가이디드 필터로 원본 해상도까지 경계 업샘플링
// 4) Blur-Fusion 전경색 추정(Forte & Pitié 2021)으로 배경색 번짐 제거
import * as ort from './ort/ort.webgpu.bundle.min.mjs';

const ORT_DIR = new URL('./ort/', import.meta.url).href;
ort.env.wasm.wasmPaths = ORT_DIR;
ort.env.wasm.numThreads = self.crossOriginIsolated ? Math.max(1, Math.min(8, (navigator.hardwareConcurrency || 4) - 1)) : 1;
ort.env.logLevel = 'error';

const MODEL_CACHE = 'bgeraser-models-v1';
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
async function fetchModel(url, bytesHint, id) {
  const cache = await caches.open(MODEL_CACHE);
  const hit = await cache.match(url);
  if (hit) { progress(id, 'cache', 1); return new Uint8Array(await hit.arrayBuffer()); }
  let res;
  try { res = await fetch(url, { mode: 'cors' }); } catch (e) { throw Object.assign(new Error('모델을 내려받지 못했습니다. 인터넷 연결을 확인해 주세요 (최초 1회 필요)'), { code: 'FETCH' }); }
  if (!res.ok) throw Object.assign(new Error('모델 다운로드 실패 (HTTP ' + res.status + ')'), { code: 'FETCH' });
  const total = +res.headers.get('content-length') || bytesHint || 0;
  const reader = res.body.getReader();
  let buf = new Uint8Array(total || 64 * 1024 * 1024), got = 0, last = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    if (got + value.length > buf.length) { const nb = new Uint8Array(Math.max(buf.length * 1.5, got + value.length) | 0); nb.set(buf.subarray(0, got)); buf = nb; }
    buf.set(value, got); got += value.length;
    const now = performance.now();
    if (now - last > 120) { last = now; post({ type: 'download', id, got, total }); }
  }
  post({ type: 'download', id, got, total: got });
  const data = got === buf.length ? buf : buf.slice(0, got);
  try { await cache.put(url, new Response(data, { headers: { 'content-type': 'application/octet-stream', 'content-length': String(got) } })); } catch (e) { post({ type: 'warn', message: '저장 공간이 부족해 모델을 캐시하지 못했습니다. 다음 실행 때 다시 받아야 합니다.' }); }
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

self.onmessage = async (e) => {
  const msg = e.data;
  try {
    if (msg.type === 'load') await loadModel(msg);
    else if (msg.type === 'run') await run(msg);
    else if (msg.type === 'unload') { if (session) await session.release(); session = null; sessionInfo = null; post({ type: 'unloaded', id: msg.id }); }
  } catch (err) {
    post({ type: 'error', id: msg.id, op: msg.type, code: err && err.code, message: String((err && err.message) || err) });
  }
};
post({ type: 'ready', threads: ort.env.wasm.numThreads, isolated: !!self.crossOriginIsolated });
