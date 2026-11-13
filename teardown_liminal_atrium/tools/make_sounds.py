#!/usr/bin/env python3
"""Synthesizes every sound of the Liminal Atrium map (all original, procedural) into ../snd/*.ogg."""
import os
import numpy as np
import soundfile as sf

SR = 44100
OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "snd"))
rng = np.random.default_rng(3)

def t(sec):
    return np.arange(int(sec * SR)) / SR

def lowpass(x, cutoff):
    """zero-phase FFT low-pass (circular -> keeps loops seamless)."""
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X *= 1 / (1 + (f / cutoff) ** 4)
    return np.fft.irfft(X, len(x))

def bandpass(x, lo, hi):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X *= (1 / (1 + (f / hi) ** 4)) * (1 / (1 + (lo / np.maximum(f, 1)) ** 4))
    return np.fft.irfft(X, len(x))

def loop_noise(sec, color=1.0):
    """noise with random phases built in the frequency domain: loops perfectly."""
    n = int(sec * SR)
    f = np.fft.rfftfreq(n, 1 / SR)
    mag = 1 / np.maximum(f, 20) ** (color / 2)
    X = mag * np.exp(2j * np.pi * rng.random(len(f)))
    X[0] = 0
    x = np.fft.irfft(X, n)
    return x / np.abs(x).max()

def env(n, a, d):
    """attack / exponential decay envelope (seconds)."""
    tt = np.arange(n) / SR
    return np.minimum(tt / max(a, 1e-4), 1) * np.exp(-tt / d)

def norm(x, peak=0.9):
    return x / (np.abs(x).max() + 1e-9) * peak

def save(name, x, peak=0.9):
    os.makedirs(OUT, exist_ok=True)
    sf.write(os.path.join(OUT, name), norm(x, peak).astype(np.float32), SR, format="OGG", subtype="VORBIS")

def bell(freq, sec, decay):
    tt = t(sec)
    partials = [(1.0, 1.0), (2.0, 0.45), (2.76, 0.25), (5.4, 0.12), (8.9, 0.05)]
    x = sum(a * np.sin(2 * np.pi * freq * r * tt) * np.exp(-tt / (decay / r ** 0.6)) for r, a in partials)
    return x * np.minimum(tt / 0.004, 1)

# --- elevator arrival chime: two descending bell notes -------------------------------
ding = np.zeros(int(2.4 * SR))
n1 = bell(1318.5, 2.4, 0.9)                 # E6
n2 = bell(1046.5, 2.0, 1.1)                 # C6
ding += n1
off = int(0.42 * SR)
ding[off:off + len(n2)] += n2[:len(ding) - off]
save("elev_ding.ogg", ding, 0.8)

# --- elevator motor hum (seamless 4 s loop) -------------------------------------------
L = 4.0
tt = t(L)
hum = (0.6 * np.sin(2 * np.pi * 50 * tt) + 0.35 * np.sin(2 * np.pi * 100 * tt) + 0.18 * np.sin(2 * np.pi * 150 * tt)
       + 0.08 * np.sin(2 * np.pi * 300 * tt))
hum *= 1 + 0.08 * np.sin(2 * np.pi * 0.5 * tt)                    # slow wobble (integer cycles in 4 s)
hum += 0.35 * lowpass(loop_noise(L, 2.0), 400)                     # cable / car rumble
hum += 0.05 * bandpass(loop_noise(L, 1.0), 2000, 4000) * (1 + np.sin(2 * np.pi * 2 * tt))  # rail whisper
save("elev_hum.ogg", hum, 0.7)

# --- elevator door slide: rumble + rollers, soft bump at the end ----------------------
sec = 1.4
n = int(sec * SR)
tt = t(sec)
shape = np.sin(np.pi * np.clip(tt / 1.15, 0, 1)) ** 0.7
slide = lowpass(rng.standard_normal(n), 700) * shape
slide += 0.25 * bandpass(rng.standard_normal(n), 1500, 3500) * shape * (0.6 + 0.4 * np.sin(2 * np.pi * 23 * tt))
bump = np.zeros(n); k0 = int(1.12 * SR)
bump[k0:] = np.sin(2 * np.pi * 85 * tt[:n - k0]) * env(n - k0, 0.002, 0.08) * 2.5
save("elev_door.ogg", slide + bump, 0.75)

# --- button click -------------------------------------------------------------------
n = int(0.12 * SR)
click = bandpass(rng.standard_normal(n), 1500, 6000) * env(n, 0.0005, 0.008)
click += 0.6 * np.sin(2 * np.pi * 2200 * t(0.12)) * env(n, 0.0005, 0.02)
save("btn_click.ogg", click, 0.8)

# --- wooden door: latch click + short creak ----------------------------------------
sec = 1.0
n = int(sec * SR)
tt = t(sec)
latch = bandpass(rng.standard_normal(n), 800, 5000) * env(n, 0.0005, 0.012) * 1.5
f0 = 180 + 90 * np.sin(2 * np.pi * 1.3 * tt) + 40 * np.sin(2 * np.pi * 7 * tt)
phase = 2 * np.pi * np.cumsum(f0) / SR
saw = 2 * ((phase / (2 * np.pi)) % 1) - 1
creak = bandpass(saw * (0.5 + 0.5 * np.sign(np.sin(2 * np.pi * 31 * tt))), 300, 2500)
creak *= np.clip((tt - 0.05) / 0.1, 0, 1) * np.exp(-np.clip(tt - 0.15, 0, None) / 0.35) * 0.5
save("door_open.ogg", latch + creak, 0.7)

sec = 0.8
n = int(sec * SR)
tt = t(sec)
thud = np.sin(2 * np.pi * (70 + 40 * np.exp(-tt / 0.03)) * tt) * env(n, 0.001, 0.09) * 1.6
thud += lowpass(rng.standard_normal(n), 900) * env(n, 0.001, 0.05)
latch2 = np.zeros(n); k0 = int(0.03 * SR)
latch2[k0:] = bandpass(rng.standard_normal(n - k0), 1500, 6000) * env(n - k0, 0.0005, 0.01)
save("door_close.ogg", thud + latch2, 0.8)

# --- building ambience: air handling + faint mains hum (seamless 12 s loop) ---------
L = 12.0
tt = t(L)
air = lowpass(loop_noise(L, 1.6), 900)
mains = 0.05 * np.sin(2 * np.pi * 60 * tt) + 0.03 * np.sin(2 * np.pi * 120 * tt) + 0.015 * np.sin(2 * np.pi * 180 * tt)
swell = 1 + 0.25 * np.sin(2 * np.pi * tt / L) + 0.1 * np.sin(2 * np.pi * 3 * tt / L)
amb = air * 0.5 * swell + mains
save("ambience.ogg", amb, 0.6)

# --- fluorescent buzz for flickering lights (seamless 2 s loop) --------------------
L = 2.0
tt = t(L)
buzz = sum(np.sin(2 * np.pi * 120 * h * tt) / h ** 1.2 for h in range(1, 14))
buzz = np.tanh(2.5 * buzz) + 0.2 * bandpass(loop_noise(L, 0.5), 3000, 8000)
save("buzz.ogg", buzz, 0.6)

# --- elevator music: soft electric-piano loop (original chord progression) ---------
BPM = 76
beat = 60 / BPM
bars = 8
L = bars * 4 * beat
n = int(L * SR)
mus = np.zeros(n + int(2.5 * SR))      # room for decaying tails, wrapped to the start below
def ep_note(freq, dur):
    tt_ = t(dur)
    tone = np.sin(2 * np.pi * freq * tt_ + 1.2 * np.sin(2 * np.pi * freq * 1.0 * tt_) * np.exp(-tt_ / 0.4))
    tone += 0.25 * np.sin(2 * np.pi * freq * 2 * tt_) * np.exp(-tt_ / 0.6)
    return tone * env(len(tt_), 0.005, 1.4)
def midi(m):
    return 440 * 2 ** ((m - 69) / 12)
chords = [[53, 57, 60, 64], [52, 55, 59, 62], [50, 53, 57, 60], [48, 52, 55, 59],   # Fmaj7 Em7 Dm7 Cmaj7
          [46, 50, 53, 57], [45, 48, 52, 55], [50, 53, 57, 60], [43, 47, 50, 53]]   # Bbmaj7 Am7 Dm7 G7
melody = [72, 71, 69, 67, 69, 67, 65, 64, 65, 64, 62, 60, 62, 64, 65, 67]
for bi, ch in enumerate(chords):
    start = int(bi * 4 * beat * SR)
    for rep in (0, 2):                                        # chord on beats 1 and 3
        s0 = start + int(rep * beat * SR)
        for m in ch:
            note = ep_note(midi(m), 2.2) * 0.22
            mus[s0:s0 + len(note)] += note
    for mi in range(2):                                        # two melody notes per bar
        m = melody[(bi * 2 + mi) % len(melody)]
        s0 = start + int((mi * 2 + 0.5) * beat * SR)
        note = ep_note(midi(m), 1.6) * 0.3
        mus[s0:s0 + len(note)] += note
# wrap the decaying tail around so the loop is seamless, then tape wobble + warm low-pass
wrapped = mus[:n].copy()
wrapped[:len(mus) - n] += mus[n:]
mus = wrapped
tt = t(L)
idx = (np.arange(n) + 18 * np.sin(2 * np.pi * 0.37 * tt)).astype(int) % n
mus = lowpass(mus[idx], 3500) + 0.02 * lowpass(loop_noise(L, 1.0), 6000)
save("muzak.ogg", mus, 0.7)

print("sounds written to", OUT, sorted(os.listdir(OUT)))

# --- indoor pool ambience: lapping water + drips with a tiled-room echo (seamless 10 s loop) -----
L = 10.0
n = int(L * SR)
tt = t(L)
lap = bandpass(loop_noise(L, 1.2), 150, 1200) * (0.55 + 0.45 * np.sin(2 * np.pi * 0.3 * tt) * np.sin(2 * np.pi * 0.1 * tt))
lap += 0.25 * bandpass(loop_noise(L, 0.8), 2000, 6000) * (0.5 + 0.5 * np.sin(2 * np.pi * 0.7 * tt))
drips = np.zeros(n)
for k in range(9):
    s0 = int(rng.uniform(0, L - 0.4) * SR)
    f = rng.uniform(900, 1800)
    m = int(0.25 * SR)
    d = np.sin(2 * np.pi * (f + 600 * np.exp(-t(0.25) / 0.02)) * t(0.25)) * env(m, 0.001, 0.05)
    drips[s0:s0 + m] += d * rng.uniform(0.4, 1.0)
echo = drips.copy()
for delay, g in ((0.11, 0.5), (0.23, 0.35), (0.37, 0.25), (0.61, 0.15)):   # hard tiled room
    echo += g * np.roll(drips, int(delay * SR))
save("pool_ambience.ogg", lap * 0.6 + echo * 0.5, 0.6)

# --- spa bubbles (seamless 4 s loop) ------------------------------------------------------------
L = 4.0
n = int(L * SR)
bub = 0.4 * bandpass(loop_noise(L, 1.0), 200, 900)
for k in range(140):
    s0 = int(rng.uniform(0, L) * SR)
    f = rng.uniform(300, 1400)
    m = int(0.06 * SR)
    b = np.sin(2 * np.pi * (f * (1 + 2.5 * t(0.06))) * t(0.06)) * env(m, 0.002, 0.015)
    idx = (np.arange(m) + s0) % n
    bub[idx] += b * rng.uniform(0.2, 0.7)
save("spa_bubbles.ogg", bub, 0.6)
print("pool sounds written")
