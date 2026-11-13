#!/usr/bin/env python3
"""Convert a song (mp3/wav/flac) into the pool radio loop: mono 44.1 kHz Ogg Vorbis with soft loop edges.
usage: python3 tools/convert_song.py <song file>   ->  snd/radio_song.ogg"""
import sys, os
import numpy as np, soundfile as sf
src = sys.argv[1]
x, sr = sf.read(src, always_2d=True)
x = x.mean(axis=1)                                   # mono: positional (3D) sound in Teardown
if sr != 44100:                                      # simple resample if needed
    t_old = np.arange(len(x)) / sr
    t_new = np.arange(int(len(x) * 44100 / sr)) / 44100
    x = np.interp(t_new, t_old, x); sr = 44100
fade = int(0.6 * sr)
x[:fade] *= np.linspace(0, 1, fade)                  # soft start / end so the loop seam does not click
x[-fade:] *= np.linspace(1, 0, fade)
x = x / (np.abs(x).max() + 1e-9) * 0.9
out = os.path.join(os.path.dirname(__file__), "..", "snd", "radio_song.ogg")
with sf.SoundFile(out, "w", samplerate=sr, channels=1, format="OGG", subtype="VORBIS") as f:
    x = x.astype(np.float32)
    for i in range(0, len(x), 32768):                # chunked: libsndfile crashes on one huge Vorbis write
        f.write(x[i:i + 32768])
print("written", os.path.abspath(out), f"{len(x) / sr:.1f}s")
