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
checks["roof (via stair penthouse)"] = (bx0 + 20, ns["ROOF_Y"], 172)
GH_ = ns["GLASSHOUSE"]
checks["rooftop glasshouse: entrance foyer"] = ((GH_["x0"] + GH_["x1"]) // 2, ns["ROOF_Y"], GH_["z0"] + 8)
checks["rooftop glasshouse: pond plaza"] = (GH_["plaza"][0], ns["ROOF_Y"], GH_["plaza"][1] - 16)
checks["rooftop glasshouse: north terrace"] = ((GH_["x0"] + GH_["x1"]) // 2 - 16, ns["ROOF_Y"], GH_["z1"] - 13)
YB = ns["YB"]
checks["B1 car-park ramp (top, street level)"] = (30, G0, 66)
checks["B1 car-park ramp (bottom)"] = (30, YB, 280)
checks["B1 car park"] = (162, YB, 200)
checks["B1 arcade promenade (through automatic door 1)"] = (310, YB, 250)
checks["B1 arcade corridor (through automatic door 2)"] = (184, YB, 412)
checks["B1 SE elevator hall"] = (374, YB, 130)
checks["B1 NW elevator lobby"] = (96, YB, 452)
checks["B1 lounge"] = (366, YB, 470)
for (nm_, kind_, sx_, sz_) in ns["SHOPS"]:
    checks[f"B1 {kind_} '{nm_}' (inside)"] = (sx_, YB, sz_)
for nm, (x, y, z) in checks.items():
    report(f"reachable: {nm}", reachable(int(x), int(y), int(z), r=8))
# each stairwell on its own (nothing outside the core counts) joins the B1 landing to the ground floor
for key in ("SW", "NE"):
    fr = ns["corner"][key]
    xa, xb, za, zb = fr._rect(-ns["T_PART"] - 1, ns["CB"], -ns["T_PART"] - 1, ns["CB"])
    ya, yb_ = YB - 3, G0 + 20
    sub = lab[xa:xb, ya:yb_, za:zb] > 0
    sl, _ = ndimage.label(sub, structure=np.ones((3, 3, 3), bool))
    def comp(u, v, y):
        x, z = fr.pt(u, v)
        w = sl[max(x - xa - 3, 0):x - xa + 4, y - ya - 2:y - ya + 6, max(z - za - 3, 0):z - za + 4]
        st = stand[xa:xb, ya:yb_, za:zb][max(x - xa - 3, 0):x - xa + 4, y - ya - 2:y - ya + 6, max(z - za - 3, 0):z - za + 4]
        return set(np.unique(w[st & (w > 0)]).tolist())
    b1, g = comp(6, 30, YB), comp(6, 30, G0)
    report(f"{key} stairwell walks from B1 up to the ground floor", bool(b1 & g), f"B1 {b1} ground {g}")

# 5b. both sides of every swing door are reachable (rooms, bathrooms, stairwells, lobby, entrance)
side_bad = []
for i, d in enumerate(ns["DOORS"]):
    if d["kind"] != "swing": continue
    arr = d["arr"]; gx, gy, gz = d["gmin"]; sx, sy, sz = arr.shape
    cxd, czd = gx + sx / 2, gz + sz / 2
    nx, nz = (0, 1) if sx > sz else (1, 0)                 # door normal (thin axis)
    for sgn in (-1, 1):
        px_, pz_ = int(cxd + sgn * nx * 5), int(czd + sgn * nz * 5)
        if not reachable(px_, gy, pz_, r=3, dy=8):
            side_bad.append((i, sgn))
report("both sides of every door are reachable", not side_bad, f"{len(side_bad)} door sides: {side_bad[:6]}")

# 5c. door hinges: each joint point touches a door voxel and a world voxel
joint_bad = []
for i, d in enumerate(ns["DOORS"]):
    if d["kind"] != "swing": continue
    px, pz = d["pivot"]; gx, gy, gz = d["gmin"]; arr = d["arr"]
    for yy in (gy + 2, gy + arr.shape[1] - 2):
        near = [(int(math.floor(px + ox)), yy, int(math.floor(pz + oz))) for ox in (-0.5, 0.5) for oz in (-0.5, 0.5)]
        door_touch = any(0 <= c[0] - gx < arr.shape[0] and 0 <= c[2] - gz < arr.shape[2] and arr[c[0] - gx, c[1] - gy, c[2] - gz] > 0 for c in near)
        wall_touch = any(FULL[c] > 0 for c in near)
        if not (door_touch and wall_touch):
            joint_bad.append((i, yy - gy, door_touch, wall_touch))
report("every door hinge joint touches both the door and the wall", not joint_bad, str(joint_bad[:6]))

# 5d. doors that start open never overlap each other (dynamic bodies overlapping at load would explode)
def door_cells(d, frac):
    a_ = math.radians(d["ang"] * frac); px, pz = d["pivot"]; arr = d["arr"]; gx, gy, gz = d["gmin"]
    X, Y, Z = np.nonzero(arr); cx_ = X + gx + 0.5; cz_ = Z + gz + 0.5
    rx = (cx_ - px) * math.cos(a_) + (cz_ - pz) * math.sin(a_); rz = -(cx_ - px) * math.sin(a_) + (cz_ - pz) * math.cos(a_)
    return set(zip(np.floor(px + rx).astype(int).tolist(), (Y + gy).tolist(), np.floor(pz + rz).astype(int).tolist()))
occupied = {}
clash = []
for i, d in enumerate(ns["DOORS"]):
    if d["kind"] != "swing": continue
    cells = door_cells(d, 0.85 if d["start_open"] else 0.0)
    for c in cells:
        if c in occupied and occupied[c] != i:
            clash.append((occupied[c], i)); break
        occupied[c] = i
report("no two doors overlap at load", not clash, str(clash[:6]))

# 5e. every lamp is attached to the building (face-adjacent to a world voxel)
float_lamps = []
for li, L in enumerate(ns["LAMPS"]):
    V = np.array(L["vox"])
    touch = False
    for dvec in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)):
        nb = V + np.array(dvec)
        ok = (nb[:, 0] >= 0) & (nb[:, 0] < W) & (nb[:, 1] >= 0) & (nb[:, 1] < H) & (nb[:, 2] >= 0) & (nb[:, 2] < D)
        if (G[nb[ok, 0], nb[ok, 1], nb[ok, 2]] > 0).any():
            touch = True; break
    if not touch:
        float_lamps.append(li)
report("every lamp is attached to the building", not float_lamps, str(float_lamps[:8]))

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
# every room window is glazed (no open hole to the atrium)
GLASS_IDS = [ns["GLASS"]]
unglazed = []
WIN_W, WIN_H, SILL, T_FAC = ns["WIN_W"], ns["WIN_H"], ns["SILL"], ns["T_FAC"]
for name, b, fr, bw in ns["room_frames"]():
    for k in range(FLOORS):
        if k == 0 and name == "S" and b in (1, 2):
            continue
        u0 = bw // 2 - WIN_W // 2 + 1
        x0, x1, z0, z1 = fr._rect(u0 + 1, u0 + WIN_W - 1, -T_FAC, 0)
        pane = FULL[x0:x1, fy(k) + SILL + 1:fy(k) + SILL + WIN_H - 1, z0:z1]
        if int(np.isin(pane, GLASS_IDS).sum()) < (WIN_W - 3) * (WIN_H - 2):
            unglazed.append((name, b, k + 1))
report("every room window has its glass", not unglazed, str(unglazed[:6]))
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
    lo = ns["YB"] - 2; hi = gy + (ns["FLOORS"] - 1 - e["floor"]) * ns["FH"] + sy     # B1 .. floor 6
    cab += int((FULL[gx:gx + sx, lo:hi, gz:gz + sz] > 0).sum())
report("elevator cabs travel B1 - floor 6 without touching anything", cab == 0, f"{cab} voxels in the way")

# 6b. mission + curtains (separate static bodies moved by main.lua)
def body_hits(arr, gmin, dx=0, dz=0, world=FULL):
    gx, gy, gz = gmin; sx, sy, sz = arr.shape
    gx += dx; gz += dz
    reg = world[gx:gx + sx, gy:gy + sy, gz:gz + sz]
    return int(((reg > 0) & (arr > 0)).sum())
door_occ = set()
for d in ns["DOORS"]:
    if d["kind"] != "swing": continue
    for frac in (0.0, 0.25, 0.5, 0.85):
        door_occ |= door_cells(d, frac)
def cells_of(arr, gmin, dx=0, dz=0):
    X, Y, Z = np.nonzero(arr); gx, gy, gz = gmin
    return set(zip((X + gx + dx).tolist(), (Y + gy).tolist(), (Z + gz + dz).tolist()))
cur_bad, cur_cells = [], {}
for i, c in enumerate(ns["CURTAINS"]):
    for (dx, dz) in ((0, 0), c["slide"]):
        if body_hits(c["arr"], c["gmin"], dx, dz):
            cur_bad.append((i, (dx, dz)))
    for cc in cells_of(c["arr"], c["gmin"]) | cells_of(c["arr"], c["gmin"], *c["slide"]):
        if cc in cur_cells and cur_cells[cc] // 2 != i // 2:
            cur_bad.append((i, "overlaps curtain", cur_cells[cc])); break
        cur_cells[cc] = i
groups = collections.Counter(c["cid"] for c in ns["CURTAINS"])
report(f"all {len(ns['CURTAINS'])} curtain panels slide open/shut without hitting anything", not cur_bad, str(cur_bad[:6]))
report("every window has exactly two curtain panels", set(groups.values()) == {2} and len(groups) == len(ns["room_log"]))
kc_bad = []
for i, k_ in enumerate(ns["KEYCARDS"]):
    arr, (gx, gy, gz) = k_["arr"], k_["gmin"]
    under = FULL[gx:gx + arr.shape[0], gy - 1, gz:gz + arr.shape[2]]
    if body_hits(arr, k_["gmin"]) or not (under[arr[:, 0, :] > 0] > 0).all():
        kc_bad.append(i)
report("6 memories (one per floor) lie clear on a desk", not kc_bad and sorted(k_["floor"] for k_ in ns["KEYCARDS"]) == list(range(FLOORS)), str(kc_bad))
bell = ns["BELL"]; bx_, by_, bz_ = bell["gmin"]
report("front-desk bell sits clear on the desk", body_hits(bell["arr"], bell["gmin"]) == 0 and FULL[bx_, by_ - 1, bz_] > 0)
ms = ns["MISSION_START"]
report("mission start / respawn point is walkable and reachable", reachable(int(ms[0]), int(ms[1]), int(ms[2]), r=3, dy=6))
mq_bad = []
for i, m in enumerate(ns["MANNEQUINS"]):
    (ax_, az_), (bx2, bz2) = m["seg"]
    arr, (gx, gy, gz) = m["arr"], m["gmin"]
    sx, sy, sz = arr.shape
    # the body is moved (and turned) along the segment: test a 6x6 footprint column around each point
    nstep = int(max(abs(bx2 - ax_), abs(bz2 - az_))) + 1
    hit = 0
    for t in np.linspace(0, 1, nstep):
        px_, pz_ = ax_ + (bx2 - ax_) * t, az_ + (bz2 - az_) * t
        x0, z0 = int(math.floor(px_ - 2.5)), int(math.floor(pz_ - 2.5))
        hit += int((FULL[x0:x0 + 5, gy:gy + sy, z0:z0 + 5] > 0).sum())
        if any((x, y, z) in door_occ for x in range(x0, x0 + 5) for z in range(z0, z0 + 5) for y in (gy + 5, gy + 15)):
            hit += 1
    for (px_, pz_) in ((ax_, az_), (bx2, bz2)):
        if not reachable(int(px_), gy, int(pz_), r=2, dy=6):
            hit += 1000
    if hit:
        mq_bad.append((i, m["floor"], hit))
report(f"all {len(ns['MANNEQUINS'])} dreamers have a clear corridor path", not mq_bad, str(mq_bad[:6]))
dec_bad = []
door_xz = {(x, z) for (x, _, z) in door_occ}
for i, m in enumerate(ns["DECOR_MQ"]):
    gx, gy, gz = m["gmin"]; arr = m["arr"]
    feet = arr[:, 0, :] > 0
    if body_hits(arr, m["gmin"]) or not (FULL[gx:gx + arr.shape[0], gy - 1, gz:gz + arr.shape[2]][feet] > 0).all() \
            or any((c[0], c[2]) in door_xz for c in cells_of(arr, m["gmin"])):
        dec_bad.append(i)
report(f"all {len(ns['DECOR_MQ'])} decorative dreamers stand clear on the floor", not dec_bad and len(ns["DECOR_MQ"]) >= 2, str(dec_bad))
ad_bad = []
for i, d in enumerate(ns["DOORS"]):
    if not d["tag"].startswith("autodoor"): continue
    dx_, dz_ = d["slide"]
    for f_ in (0.5, 1.0):
        if body_hits(d["arr"], d["gmin"], int(round(dx_ * f_)), int(round(dz_ * f_))):
            ad_bad.append((i, f_))
n_ad = sum(1 for d in ns["DOORS"] if d["tag"].startswith("autodoor"))
report(f"automatic doors: {n_ad} glass leaves slide fully open without hitting anything", n_ad == 4 and not ad_bad, str(ad_bad))
calls_b1 = sorted(c[2] for c in ns["CALLS"] if c[3] == -1)
report("all 4 elevators stop at B1 (landing door + call button)", len(calls_b1) == 4 and
       sum(1 for d in ns["DOORS"] if "elevdoor" in d["tag"] and "floor=-1" in d["tag"]) == 4, str(calls_b1))
mall = [sp for sp in ns["SOUND_SPOTS"] if sp[0] == "mall"]
report(f"{len(mall)} arcade music speakers sit in open air in B1", len(mall) >= 5 and all(FULL[int(x), int(y), int(z)] == 0 and y < G0 for (_, x, y, z) in mall))
sw_bad = []
for (sarr, smin, rid, on, tv) in ns["ROOM_SWITCHES"]:
    if body_hits(sarr, smin) or any(c in door_occ for c in cells_of(sarr, smin)) \
            or not reachable(int(smin[0]), int(smin[1]) - 11, int(smin[2]), r=4, dy=4):
        sw_bad.append(rid)
report(f"{len(ns['ROOM_SWITCHES'])} room light switches: clear of walls / doors and within reach", not sw_bad and len(ns["ROOM_SWITCHES"]) == len(ns["room_log"]), str(sw_bad[:8]))
per = collections.Counter()
for l in ns["LIGHTS"]:
    t = dict(kv.split("=") for kv in l[6].split() if "=" in kv)
    if "room" in t: per[(t["room"], t["rl"])] += 1
NS = ns["ROOM_NSTANDS"]
kinds_ok = all(per[(str(i), k)] == 1 for i in range(len(ns["room_log"])) for k in ("ceil", "bath", "tv")) and \
           all(per[(str(i), "lamp")] == NS[i] >= 1 for i in range(len(ns["room_log"])))
lamp_rooms = sum(1 for L in ns["LAMPS"] if any("room=" in lt[6] for lt in L["lights"]))
need = sum(3 + NS[i] for i in range(len(ns["room_log"])))
mixed = [i for i, L in enumerate(ns["LAMPS"]) if len({lt[6] for lt in L["lights"]}) > 1 and any("room=" in lt[6] for lt in L["lights"])]
report("every room: ceiling, EVERY bedside lamp, bathroom light + TV, each its own switchable lamp", kinds_ok and not mixed and lamp_rooms == need,
       f"{lamp_rooms}/{need} room lamps, {sum(1 for v in NS.values() if v > 1)} rooms with 2 bedside lamps, mixed {mixed[:4]}")
pd_bad = []
for i, (poly, cells) in enumerate(ns["PUDDLES"]):
    if not all(FULL[x, YB - 1, z] == ns["PUDDLE"] and FULL[x, YB, z] == 0 for (x, z) in cells):
        pd_bad.append(i)
report(f"{len(ns['PUDDLES'])} car-park puddles: glossy standing-water surface flush with the floor", len(ns["PUDDLES"]) >= 6 and not pd_bad, str(pd_bad))
hidden = collections.Counter()
for (c_, f_, txt) in ns["SIGN_CELLS"]:
    if FULL[c_] == 0 or FULL[f_] != 0:
        hidden[txt] += 1
report(f"all {len(set(t for _, _, t in ns['SIGN_CELLS']))} wall signs readable (every letter there, nothing in front of it)", not hidden, str(dict(hidden)))
car_bad = []
for (kind_, fb_, gx_, gy_, gz_, ry_) in ns["CAR_SPOTS"]:
    # room for the biggest pick (2.4 x 2.2 x 5.2 m) around the bay centre, solid ground below it
    cx_, cz_ = int(gx_ + 10), int(gz_ + 22)
    hx_, hz_ = (26, 12) if abs(ry_) == 90 else (12, 26)       # turned 90 degrees: long axis along x
    reg = FULL[cx_ - hx_:cx_ + hx_, gy_ + 1:gy_ + 22, cz_ - hz_:cz_ + hz_]
    ground = FULL[cx_ - hx_ + 4:cx_ + hx_ - 4, gy_ - 1, cz_ - hz_ + 4:cz_ + hz_ - 4]
    if (reg > 0).any() or not (ground > 0).all() or cx_ - 12 < 0 or cz_ - 26 < 0:
        car_bad.append(kind_)
# car park: every bay clear of columns / walls, parked cars sit inside one bay
YB_ = ns["YB"]; bay_bad = []
for (bays_, xa_, xb_, wa_, wb_) in ((ns["WEST_BAYS"], ns["IX0"], ns["AISLE0"], 3, 0), (ns["EAST_BAYS"], ns["AISLE1"], ns["PX1"] - 2, 0, 3)):
    for z0_ in bays_:          # (wall signs / fire cabinet within 0.3 m of the end wall are fine)
        if (FULL[xa_ + wa_:xb_ - wb_, YB_ + 2:YB_ + 18, z0_ + 1:z0_ + ns["BAY_W"] - 1] > 0).any() or (~np.isin(FULL[xa_:xb_, YB_ - 1, z0_], [ns["PAINT_LINE"], ns["PUDDLE"], ns["ROOF"], ns["ROOF2"]])).sum() > 2:
            bay_bad.append(z0_)
    for (cx0, cz0) in ns["COLS"]:
        if xa_ - 3 < cx0 < xb_ + 3 and any(z0_ - 3 < cz0 < z0_ + ns["BAY_W"] + 3 for z0_ in bays_) and xa_ + 3 <= cx0 < xb_ - 3:
            bay_bad.append(("col", cx0, cz0))
for (kind_, fb_, gx_, gy_, gz_, ry_) in ns["CAR_SPOTS"]:
    if gy_ == YB_:
        czc = gz_ + 22
        if not any(z0_ + 6 <= czc <= z0_ + ns["BAY_W"] - 6 for z0_ in ns["WEST_BAYS"] + ns["EAST_BAYS"]) or abs(ry_) != 90:
            bay_bad.append(kind_)
report(f"car park: {len(ns['WEST_BAYS']) + len(ns['EAST_BAYS'])} bays painted, free of columns/walls; parked cars inside a bay", not bay_bad, str(bay_bad))
# rooftop glasshouse: path clear to walk, vault on its eave beams, plants grown, pond water inside its basin
GH_ = ns["GLASSHOUSE"]; RY_ = ns["ROOF_Y"]; gx_c, gz_c = GH_["plaza"]
path_block = 0
for z in range(GH_["z0"] + 16, GH_["z1"] - 16):        # (foyer / terrace have urns, a planter, benches)
    if abs(z - gz_c) > 21:
        path_block += int((G[ns["PW0"] + 1:ns["PW1"] - 1, RY_:RY_ + 17, z] > 0).sum())
LEAFS = [ns[k] for k in ("LEAF", "LEAF2", "LEAF3", "LAWN")]
FLOWERS = [ns[k] for k in ("ROSE", "DREAM_PINK", "DREAM_LILAC", "DREAM_CLOUD", "WALL_BLUE", "WALL_MAUVE")]
sub_ = FULL[GH_["x0"]:GH_["x1"], RY_:GH_["eave"], GH_["z0"]:GH_["z1"]]
n_leaf, n_flower = int(np.isin(sub_, LEAFS).sum()), int(np.isin(sub_, FLOWERS).sum())
pond = [p_ for p_ in ns["POOLS"] if abs(p_[0] - (RY_ + 4.5)) < 0.01]
pond_ok = len(pond) == 1 and all(np.hypot(px_ - gx_c, pz_ - gz_c) < 10.5 for (px_, pz_) in pond[0][2])
report(f"rooftop glasshouse: path clear, {n_leaf} leaf + {n_flower} flower voxels, pond water inside its rim",
       path_block == 0 and n_leaf > 4000 and n_flower > 800 and pond_ok, f"path_block={path_block} pond_ok={pond_ok}")
RYq = ns["ROOF_Y"]; rbad = 0
for (a_, b_, c_, d_) in ns["CORNER_RECTS"]:
    rbad += int(np.isin(FULL[a_ - 2:b_ + 2, RYq:RYq + 16, c_ - 2:d_ + 2], [ns["HVAC"]]).sum())
report(f"roof: {len(ns['HVAC_SPOTS'])} HVAC units, ducts and vents clear of the stair penthouses / lift machine rooms", rbad == 0, f"{rbad} voxels")
# a van (2.2 m wide, up to 3.0 m tall) drives street -> ramp -> tunnel -> car-park aisle without touching anything
YBq, A0q, A1q = ns["YB"], ns["AISLE0"], ns["AISLE1"]
van_path = [("tunnel", FULL[ns["RX1"]:ns["IX0"], YBq:YBq + 31, ns["TZ0"] + 4:ns["TZ1"] - 4]),
            ("ramp bottom", FULL[ns["RX0"] + 2:ns["RX1"] - 2, YBq:YBq + 31, ns["RZ_BOT"]:ns["RZ_END"]]),
            ("aisle", FULL[A0q + 7:A1q - 7, YBq:YBq + 31, 162:ns["PZ1"] - 2]),
            ("aisle by the stair core", FULL[158:A1q - 7, YBq:YBq + 31, ns["IZ0"] + 2:162])]
ramp_bad = 0
for zq in range(ns["RZ_TOP"] - 4, ns["RZ_BOT"]):
    ry_ = ns["ramp_y"](zq)
    ramp_bad += int((FULL[ns["RX0"] + 2:ns["RX1"] - 2, ry_:ry_ + 31, zq] > 0).sum())
van_bad = [n_ for (n_, r_) in van_path if (r_ > 0).any()] + (["ramp"] if ramp_bad else [])
RO_ = ns["ROAD"]; G0q = ns["G0"]
drive_ok = not (RO_[ns["RX0"]:ns["RX1"], G0q:G0q + 2, ns["NC0"]:] > 0).any()
report("van clearance 3.0 m: street driveway, ramp, tunnel, car-park aisle", not van_bad and drive_ok, f"{van_bad} driveway_ok={drive_ok}")
report(f"{len(ns['CAR_SPOTS'])} car spots: free space + ground for a base-game vehicle", not car_bad and len(ns["CAR_SPOTS"]) >= 7, str(car_bad))
RO = ns["ROAD"]; RD_ = ns["RD"]
r_isl = 0
for x0_, x1_ in zip(XS_MAIN, XS_MAIN[1:]):
    lab_r, n_r = ndimage.label(RO[x0_:x1_] > 0)
    r_isl += n_r - len(set(np.unique(lab_r[:, 0:2, :])) - {0})
report("street: no floating pieces in its shapes", r_isl == 0, f"{r_isl} islands")
report("street surface meets the parking lot at the same height (no step)",
       bool((RO[:, G0 - 1, RD_ - 1] > 0).all() and (G[:, G0 - 1, 0] > 0).all() and not (G[:, G0, 0] > 0).all()))
lamp_ok = True
for (arr_, (lx_, ly_, lz_), q_) in ns["ROAD_LAMPS"]:
    lzl = lz_ + RD_
    above = RO[lx_:lx_ + arr_.shape[0], ly_ + arr_.shape[1], lzl:lzl + arr_.shape[2]]
    inside = RO[lx_:lx_ + arr_.shape[0], ly_:ly_ + arr_.shape[1], lzl:lzl + arr_.shape[2]]
    lamp_ok &= bool((above > 0).any() and not (inside > 0).any())
report(f"{len(ns['ROAD_LAMPS'])} street lamps hang from their arms", lamp_ok)
van_ok = True
for (k_, fb_, cx_, cy_, cz_, ry_) in ns["ROAD_CARS"]:
    czl = cz_ + RD_
    van_ok &= not (RO[cx_ - 30:cx_ + 30, cy_ + 1:cy_ + 26, czl - 13:czl + 13] > 0).any() and bool((RO[cx_ - 20:cx_ + 20, cy_ - 1, czl - 8:czl + 8] > 0).all())
report("parked van on the street has room", van_ok)
H_ = ns["HELI"]
def hits(arr_, gm):
    gx, gy, gz = gm; sx, sy, sz = arr_.shape
    reg = FULL[gx:gx + sx, gy:gy + sy, gz:gz + sz]          # (the grid ends at H; above it is open sky)
    return int(((reg > 0) & (arr_[:reg.shape[0], :reg.shape[1], :reg.shape[2]] > 0)).sum())
hb_ = ns["HELI_BODY"]
under = FULL[H_["gmin"][0]:H_["gmin"][0] + hb_.shape[0], H_["gmin"][1] - 1, H_["gmin"][2]:H_["gmin"][2] + hb_.shape[2]][hb_[:, 0, :] > 0]
lab_h, n_h = ndimage.label(hb_ > 0)
rc = (H_["rotor_gmin"][0] + 50, H_["rotor_gmin"][1] + 8, H_["rotor_gmin"][2] + 50)
sweep = FULL[rc[0] - 51:rc[0] + 52, rc[1]:rc[1] + 3, rc[2] - 51:rc[2] + 52] > 0
report("helicopter: one solid piece, parked clear on the helipad (skids on the pad), rotor disc free all round",
       n_h == 1 and hits(hb_, H_["gmin"]) == 0 and hits(ns["HELI_ROTOR"], H_["rotor_gmin"]) == 0 and hits(ns["HELI_TAIL"], H_["tail_gmin"]) == 0
       and (under > 0).all() and not sweep.any(), f"pieces {n_h}, under {(under > 0).mean():.2f}, sweep {int(sweep.sum())}")
tg = H_["tail_gmin"]
rs_bad = [nm for (nm, arr_, gm_, l_) in ns["ROOF_SHAPES"] if hits(arr_, gm_) or not (FULL[gm_[0]:gm_[0] + arr_.shape[0], gm_[1] - 1, gm_[2]:gm_[2] + arr_.shape[2]][arr_[:, 0, :] > 0] > 0).all()]
report("windsock + floodlights stand on the roof, clear of everything", not rs_bad, str(rs_bad))
def body_cell(gm, a, b, c):
    x, y, z = gm[0] + a - H_["gmin"][0], gm[1] + b - H_["gmin"][1], gm[2] + c - H_["gmin"][2]
    return 0 <= x < hb_.shape[0] and 0 <= y < hb_.shape[1] and 0 <= z < hb_.shape[2] and hb_[x, y, z] > 0
def joints_ok(arr_, gm, pts):
    return all(arr_[a, b, c] > 0 and body_cell(gm, a, b, c) for (a, b, c) in pts)
RO_, TA_ = ns["HELI_ROTOR"], ns["HELI_TAIL"]
def hard_frac(arr_):
    v = arr_[arr_ > 0]
    return float(np.isin(v, list(range(41, 57)) + list(range(121, 153)) + list(range(169, 185))).mean())
report("helicopter is breakable (mostly plastic / glass: metal only for skids, mast and shafts)",
       hard_frac(hb_) < 0.15 and hard_frac(ns["HELI_ROTOR"][:, 8, :]) < 0.1 and hard_frac(ns["HELI_TAIL"][4]) < 0.25,          # (the small tail hub is metal)
       f"body {hard_frac(hb_):.0%} hard, blades {hard_frac(ns['HELI_ROTOR'][:, 8, :]):.0%} hard")
report("main rotor: shaft in the mast, both joint points inside rotor + mast", joints_ok(RO_, H_["rotor_gmin"], [(50, 2, 50), (50, 5, 50)]))
report("tail rotor: shaft in the fin gearbox, both joint points inside rotor + gearbox", joints_ok(TA_, H_["tail_gmin"], [(0, 10, 10), (3, 10, 10)]))
blade_hit = sum(1 for (a, b, c) in zip(*np.nonzero(RO_)) if b >= 8 and body_cell(H_["rotor_gmin"], a, b, c)) + \
            sum(1 for (a, b, c) in zip(*np.nonzero(TA_)) if a >= 4 and body_cell(H_["tail_gmin"], a, b, c))
report("rotor blades clear the helicopter body (only the shafts sit inside)", blade_hit == 0, f"{blade_hit} cells")
report("stairs lead from the room-ring roof up to the helipad roof", reachable(255, ns["ROOF_Y"], 125, r=4) and reachable(255, ns["RT"], 170, r=6) and reachable(ns["HCX"] + 40, ns["RT"], ns["HCZ"], r=6))
zones_ = []
for loc in root.iter("location"):
    t = loc.get("tags", "")
    if t.startswith("soundzone"):
        kv = dict(x.split("=") for x in t.split()[1:])
        zones_.append((kv["kind"], *(float(kv[k]) for k in ("x0", "x1", "y0", "y1", "z0", "z1"))))
CXq, CZq = W * 0.05, D * 0.05
def in_zone(gx, gy, gz):
    wx, wy, wz = gx * 0.1 - CXq, gy * 0.1, gz * 0.1 - CZq
    return [k for (k, x0_, x1_, y0_, y1_, z0_, z1_) in zones_ if x0_ <= wx <= x1_ and y0_ <= wy <= y1_ and z0_ <= wz <= z1_]
pool_src = [sp for sp in ns["SOUND_SPOTS"] if sp[0] in ("pool", "spa")]
rgx, rgy, rgz = ns["RADIO"]["gmin"]
outside = [((ns["ax0"] + ns["ax1"]) // 2, G0 + 2, (az0 + ns["az1"]) // 2), ((ns["ax0"] + ns["ax1"]) // 2 + 20, G0 + 2, az0 - 30), (310, ns["YB"] + 2, 250)]
report("pool water / spa / radio are heard only in the pool hall (+ quieter in its connector)",
       all(in_zone(x, y, z) == ["hall"] for (_, x, y, z) in pool_src) and in_zone(rgx, rgy, rgz) == ["hall"] and not any(in_zone(*p_) for p_ in outside),
       str([in_zone(x, y, z) for (_, x, y, z) in pool_src]))
report("respawn point exists (lobby spawn)", any(l.get("tags") == "respawn" for l in root.iter("location")))
sg_bad = [i for i, g in enumerate(ns["SWITCHGEAR"]) if body_hits(g["arr"], g["gmin"])]
fl_ = collections.Counter(g["floor"] for g in ns["SWITCHGEAR"])
report("electrical rooms: 2 switchgears per floor, clear of walls", not sg_bad and all(fl_[k] == 2 for k in range(FLOORS)), str(sg_bad))
pw_ = collections.Counter()
for l in ns["LIGHTS"]:
    for kv in l[6].split():
        if kv.startswith("pw="):
            pw_[int(kv[3:])] += 1
room_pw = all(("pw=" in l[6]) for l in ns["LIGHTS"] if "room=" in l[6])
report("every floor's lights are on its power circuit (rooms, corridors, electrical rooms)",
       all(pw_[k] > 40 for k in range(FLOORS)) and room_pw, str(dict(pw_)))
report("two dreamers per floor", sorted(collections.Counter(m["floor"] for m in ns["MANNEQUINS"]).values()) == [2] * FLOORS)

# 7. sounds: decodable, not clipped, loops seamless
import soundfile as sf
LOOPS = {"elev_hum.ogg", "muzak.ogg", "ambience.ogg", "pool_ambience.ogg", "spa_bubbles.ogg", "dream_pad.ogg", "garage_drips.ogg", "heli_rotor.ogg"}
for f in sorted(os.listdir("snd")):
    x, sr = sf.read("snd/" + f)
    peak = float(np.abs(x).max())
    ok = sr == 44100 and 0.05 < peak <= 1.0
    detail = f"{len(x) / sr:.1f}s peak {peak:.2f}"
    if f in LOOPS:
        jump = abs(x[0] - x[-1]); step = max(np.abs(np.diff(x)).max() * 1.15 + 1e-3, 0.012)   # seam no bigger than the signal's own steps (Vorbis edge error ~0.005)
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
