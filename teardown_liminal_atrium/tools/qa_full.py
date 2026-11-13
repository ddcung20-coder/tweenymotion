#!/usr/bin/env python3
"""Full QA of the generated map: palette, files, structure, and walkability from the spawn point."""
import os, re, sys, math, json, struct, collections
import numpy as np
from scipy import ndimage
import runpy
import xml.etree.ElementTree as ET

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.chdir(ROOT)
sys.argv = ["x"]
ns = runpy.run_path("tools/build_map.py", run_name="qa")
FULL = ns["G"].copy()                 # complete world (lamps included) before export cuts lamps out
ns["export"]()
G = ns["G"]; W, H, D = G.shape; PAL = ns["PAL"]
issues = []
def report(name, ok, detail=""):
    print(f"[{'OK ' if ok else 'BAD'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok: issues.append(name)

# 1. palette: every voxel index used anywhere must be defined
used = set(np.unique(FULL).tolist()) - {0}
for arr in [p for p in ns["PROP_SHAPES"].values()] + [d["arr"] for d in ns["DOORS"]] + [e["arr"] for e in ns["ELEVATORS"]]:
    used |= set(np.unique(arr).tolist()) - {0}
undefined = sorted(i for i in used if i not in PAL)
report("palette: every used colour index is defined", not undefined, str(undefined))

# 2. files referenced by main.xml / main.lua / spawn.txt exist
refs = set(re.findall(r'MOD/([\w/.\-]+)', open("main.xml").read() + open("main.lua").read()))
refs |= {l.split(":")[0].strip() for l in open("spawn.txt") if l.strip()}
missing = sorted(r for r in refs if not os.path.exists(r) and not r.endswith("/"))
missing = [m for m in missing if not m.startswith("prefab/\" ..")]
lua_prefabs = [f"prefab/{m}.xml" for m in re.findall(r'\{ "[^"]+", "(\w+)" \}', open("main.lua").read())]
missing += [p for p in lua_prefabs if not os.path.exists(p)]
report("all referenced files exist", not missing, str(missing))

# 3. XML well-formed, vox sizes <= 256, no duplicate names
root = ET.parse("main.xml").getroot()
def vox_size(p):
    b = open(p, "rb").read(); i = 20
    while i < len(b):
        cid = b[i:i + 4]; n, c = struct.unpack("<ii", b[i + 4:i + 12])
        if cid == b"SIZE": return struct.unpack("<iii", b[i + 12:i + 24])
        i += 12 + n + c
big = [f for f in os.listdir("vox") if max(vox_size("vox/" + f)) > 256]
report("every .vox <= 256 per axis", not big, str(big))
names = [e.get("name") for e in root.iter() if e.get("name")]
dup = [n for n, c in collections.Counter(names).items() if c > 1]
report("unique entity names", not dup, str(dup[:5]))
for p_ in os.listdir("prefab"):
    ET.parse("prefab/" + p_)
report("prefab XML files parse", True)

# 4. structure (see audit_map.py): islands per shape, buried lights, props overlap
XS_MAIN = [0, ns["ax0"] + 2 * ns["SHORT_BAY_W"], W]
XS_ANNEX = [0, ns["A_X0"] - 16, ns["A_X1"] + 16, W]
az0 = ns["az0"]
BANDS = [(0, az0 + 68, XS_MAIN), (az0 + 68, az0 + 204, XS_MAIN), (az0 + 204, ns["AZ0"] - 6, XS_MAIN), (ns["AZ0"] - 6, D, XS_ANNEX)]
isl = 0
for (z0, z1, XS) in BANDS:
    for x0, x1 in zip(XS, XS[1:]):
        sub = G[x0:x1, :, z0:z1] > 0
        lab, n = ndimage.label(sub)
        grounded = set(np.unique(lab[:, 0:2, :])) - {0}
        isl += n - len(grounded)
report("no floating pieces inside any world shape", isl == 0, f"{isl} islands")
for L in ns["LAMPS"]:
    pass
buried = sum(1 for l in ns["LIGHTS"] if FULL[int(l[0]), int(l[1]), int(l[2])] > 0)
report("no light source buried in a solid voxel", buried == 0, str(buried))
ov = [n for (n, gx, gy, gz, r) in ns["PROPS"] if ((FULL[gx:gx + ns["PROP_SHAPES"][n].shape[0], gy:gy + ns["PROP_SHAPES"][n].shape[1],
      gz:gz + ns["PROP_SHAPES"][n].shape[2]] > 0) & (ns["PROP_SHAPES"][n] > 0)).any()]
report("dynamic props start clear of the world", not ov, str(ov))
blocked = sum(1 for d in ns["DOORS"] if (FULL[d["gmin"][0]:d["gmin"][0] + d["arr"].shape[0], d["gmin"][1]:d["gmin"][1] + d["arr"].shape[1],
              d["gmin"][2]:d["gmin"][2] + d["arr"].shape[2]] > 0).any())
report("every door opening is clear", blocked == 0, f"{blocked} blocked")
lamp_ok = all(len(L["lights"]) >= 1 for L in ns["LAMPS"])
report("every lamp shape carries a light", lamp_ok)

# 5. walkability: player 1.8 m tall, ~0.3 m wide, steps up to 0.2 m
print("     (walkability flood fill ...)")
solid = FULL > 0
cs = np.zeros((W, H + 1, D), np.int16)
np.cumsum(solid, axis=1, out=cs[:, 1:, :])
HEAD, KNEE = 18, 3
def window_clear(lo, hi):
    """cells whose column is empty from y+lo to y+hi-1"""
    out = np.zeros_like(solid)
    out[:, :H - hi, :] = (cs[:, hi:H, :] - cs[:, lo:H - hi + lo, :]) == 0
    return out
centre = window_clear(0, HEAD)                 # feet to head free in the player's own column
body = window_clear(KNEE, HEAD)                # around it, free above knee height (steps, kerbs, sills)
del cs
plus = np.zeros((3, 1, 3), bool); plus[1, 0, :] = True; plus[:, 0, 1] = True
clear3 = centre & ndimage.binary_erosion(body, structure=plus, border_value=0)
del centre, body
stand = np.zeros_like(solid)
stand[:, 1:, :] = solid[:, :-1, :] & clear3[:, 1:, :]
del clear3
S = stand.copy()
S[:, :-1, :] |= stand[:, 1:, :]            # mark the floor cell under each standing cell (bridges 2-voxel steps)
lab, n = ndimage.label(S, structure=np.ones((3, 3, 3), bool))
del S
sx_, sz_ = (ns["ax0"] + ns["ax1"]) // 2, az0 + 18
G0 = ns["G0"]
spawn_label = lab[sx_, G0, sz_]
report("spawn point is on walkable floor", spawn_label != 0)

def reachable(x, y, z, r=6, dy=12):
    win = lab[max(x - r, 0):x + r + 1, max(y - 3, 0):y + dy, max(z - r, 0):z + r + 1]
    st = stand[max(x - r, 0):x + r + 1, max(y - 3, 0):y + dy, max(z - r, 0):z + r + 1]
    return bool(((win == spawn_label) & st).any())

fy = ns["fy"]; FLOORS = ns["FLOORS"]
# every hotel room (centre of the room, any height up to bed level)
bad_rooms = []
for name, b, fr, bw in ns["room_frames"]():
    for k in range(FLOORS):
        if k == 0 and name == "S" and b in (1, 2):
            continue
        x, z = fr.pt(bw // 2, 22)
        if not reachable(x, fy(k), z):
            bad_rooms.append((name, b, k))
report(f"all {len(ns['room_log'])} hotel rooms reachable on foot (doors open)", not bad_rooms, str(bad_rooms[:10]))
# bathrooms
bad_bath = []
for name, b, fr, bw in ns["room_frames"]():
    for k in range(FLOORS):
        if k == 0 and name == "S" and b in (1, 2):
            continue
        for ff in (fr, fr.mirrored(ns["T_PART"], bw)):
            pass
bx0, bx1, bz0, bz1 = ns["bx0"], ns["bx1"], ns["bz0"], ns["bz1"]
checks = {
    "lobby": ((ns["ax0"] + ns["ax1"]) // 2 + 20, G0, az0 - 30),
    "main entrance outside": ((ns["ax0"] + ns["ax1"]) // 2, G0 + 1, bz0 - 15),
    "parking lot": (bx0 + 60, G0, 20),
    "pool deck": (ns["cxN"] + 80, ns["DY"], ns["iz0"] + 60),
    "spa rim area": (ns["scx"] - 20, ns["DY"], ns["scz"]),
    "pool connector top": (ns["cxN"], ns["DY"], ns["AZ0"] - 2),
}
for k in range(FLOORS):
    checks[f"corridor floor {k + 1} (west)"] = (bx0 + 13, fy(k), (bz0 + bz1) // 2)
    checks[f"corridor floor {k + 1} (east)"] = (bx1 - 13, fy(k), (bz0 + bz1) // 2)
    for key in ("SW", "NE"):
        x, z = ns["corner"][key].pt(6, 30)
        checks[f"stair landing {key} floor {k + 1}"] = (x, fy(k), z)
    for key in ("NW", "SE"):
        x, z = ns["corner"][key].pt(30, 22)
        checks[f"utility room {key} floor {k + 1}"] = (x, fy(k), z)
checks["roof (via stair penthouse)"] = (bx0 + 20, ns["ROOF_Y"], (bz0 + bz1) // 2)
for nm, (x, y, z) in checks.items():
    report(f"reachable: {nm}", reachable(int(x), int(y), int(z)))

# 6. doors swing free, elevator cabs travel free
worst = 0.0
for d in ns["DOORS"]:
    if d["kind"] != "swing": continue
    a_ = math.radians(d["ang"] * 0.85); px, pz = d["pivot"]; arr = d["arr"]; gx, gy, gz = d["gmin"]
    # the leaf hangs 5 cm (half a voxel) up: it also reaches into the row above its top row
    X, Y, Z = np.nonzero(arr); cx_ = X + gx + 0.5; cz_ = Z + gz + 0.5
    top = Y == Y.max()
    X = np.concatenate([X, X[top]]); Z = np.concatenate([Z, Z[top]]); Y = np.concatenate([Y, Y[top] + 1])
    cx_ = X + gx + 0.5; cz_ = Z + gz + 0.5
    for frac in (0.25, 0.5, 0.85):                 # check the whole swing, not just the end pose
        a_ = math.radians(d["ang"] * frac)
        rx = (cx_ - px) * math.cos(a_) + (cz_ - pz) * math.sin(a_); rz = -(cx_ - px) * math.sin(a_) + (cz_ - pz) * math.cos(a_)
        worst = max(worst, float((FULL[np.floor(px + rx).astype(int), Y + gy, np.floor(pz + rz).astype(int)] > 0).mean()))
report("every swing door opens without hitting walls/furniture", worst == 0.0, f"worst overlap {worst:.3f}")
# every hotel room fully enclosed: both party walls, the facade wall and the corridor wall are there
T_PART, ROOM_D = ns["T_PART"], ns["ROOM_D"]
open_rooms = []
for name, b, fr, bw in ns["room_frames"]():
    for k in range(FLOORS):
        if k == 0 and name == "S" and b in (1, 2):
            continue
        y = fy(k)
        walls = {"party A": (0, T_PART, 0, ROOM_D), "party B": (bw, bw + T_PART, 0, ROOM_D),
                 "corridor": (T_PART, bw, ROOM_D, ROOM_D + T_PART)}
        for wname, (u0, u1, v0, v1) in walls.items():
            x0, x1, z0, z1 = fr._rect(u0, u1, v0, v1)
            frac = float((FULL[x0:x1, y + 1:y + 20, z0:z1] > 0).mean())
            need = 0.6 if wname == "corridor" else 0.97      # the corridor wall has the entrance door in it
            if frac < need:
                open_rooms.append((name, b, k + 1, wname, round(frac, 2)))
report("every hotel room has all its walls", not open_rooms, str(open_rooms[:8]))
HANDLES = {ns["BRASS"], ns["STEEL"]}
wrong = []
for i, d in enumerate(ns["DOORS"]):
    if d["kind"] != "swing": continue
    arr = d["arr"]; gx, gy, gz = d["gmin"]
    X, Y, Z = np.nonzero(np.isin(arr, list(HANDLES)))
    if not len(X):
        wrong.append((i, "no handle")); continue
    px, pz = d["pivot"]
    hd = np.hypot(X + gx + 0.5 - px, Z + gz + 0.5 - pz).min()       # handle distance from the hinge line
    width = max(arr.shape[0], arr.shape[2])
    if hd < width * 0.6:
        wrong.append((i, round(float(hd), 1), width))
report("every door handle is on the latch side (away from the hinge)", not wrong, str(wrong[:6]))
cab = 0
for e in ns["ELEVATORS"]:
    arr = e["arr"]; gx, gy, gz = e["gmin"]; sx, sy, sz = arr.shape
    lo = gy - e["floor"] * ns["FH"]; hi = gy + (ns["FLOORS"] - 1 - e["floor"]) * ns["FH"] + sy
    cab += int((FULL[gx:gx + sx, lo:hi, gz:gz + sz] > 0).sum())
report("elevator cabs travel floor 1-6 without touching anything", cab == 0, f"{cab} voxels in the way")

# 7. sounds: decodable, not clipped, loops seamless
import soundfile as sf
LOOPS = {"elev_hum.ogg", "muzak.ogg", "ambience.ogg", "buzz.ogg", "pool_ambience.ogg", "spa_bubbles.ogg"}
for f in sorted(os.listdir("snd")):
    x, sr = sf.read("snd/" + f)
    peak = float(np.abs(x).max())
    ok = sr == 44100 and 0.05 < peak <= 1.0
    detail = f"{len(x) / sr:.1f}s peak {peak:.2f}"
    if f in LOOPS:
        jump = abs(x[0] - x[-1]); step = np.abs(np.diff(x)).max() * 1.15 + 1e-3   # seam no bigger than the signal's own steps
        ok = ok and jump < step
        detail += f" loop-seam {jump:.3f}"
    report(f"sound {f}", ok, detail)

# 8. script: Lua 5.1 syntax + behaviour in a mocked engine
try:
    import lupa.lua51 as lupa
    L = lupa.LuaRuntime()
    err = L.eval("function(s) local f,e = loadstring(s); return e end")(open("main.lua").read())
    report("main.lua compiles under Lua 5.1 (Teardown)", not err, str(err or ""))
except ImportError:
    report("main.lua syntax (lupa not installed, skipped)", True)

print()
print("ISSUES:", issues if issues else "none")
