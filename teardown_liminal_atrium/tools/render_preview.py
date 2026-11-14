#!/usr/bin/env python3
"""Photoreal preview renders of the map (path traced with Mitsuba 3).

    pip install mitsuba
    python3 tools/render_preview.py exterior|atrium|helipad [--w 1920 --h 1080 --spp 256] [--out file.jpg]

The voxel world (+ street, doors, curtains, helicopter, parked cars, water) is turned into merged
quads per palette colour; each colour gets a material from its Teardown finish (matte / glossy /
metal / glass / emissive). Every light of the map is a real light (rooms lit as in the game at start).
Post: depth fog, bloom, filmic tone mapping, vignette, light grain."""
import os, sys, json, math, runpy, argparse, tempfile
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ap = argparse.ArgumentParser()
ap.add_argument("shot", choices=["exterior", "atrium", "helipad"])
ap.add_argument("--w", type=int, default=1280); ap.add_argument("--h", type=int, default=720)
ap.add_argument("--spp", type=int, default=128); ap.add_argument("--out", default=None)
ap.add_argument("--debug", default="")          # nolights / noemit / nosky (diagnostics)
args = ap.parse_args()

import mitsuba as mi
mi.set_variant("llvm_ad_rgb")

# ---------------------------------------------------------------- build the map in memory
os.chdir(ROOT)
argv_ = sys.argv; sys.argv = ["x"]
ns = runpy.run_path(os.path.join(ROOT, "tools", "build_map.py"), run_name="render")
sys.argv = argv_
FULL = ns["G"].copy()
ns["export"]()                                    # fills LAMPS (lamp voxels + their light tags)
PAL = ns["PAL"]; W, H, D = FULL.shape; RD = ns["RD"]
STATE = {i: r[3] for i, r in enumerate(ns["room_log"])}

# combined grid: street in front (z offset RD), extra headroom for the helicopter rotor
HN = H + 16
Gc = np.zeros((W, HN, D + RD), np.uint8)
Gc[:, :H, RD:] = FULL
Gc[:, :ns["ROAD"].shape[1], :RD] = ns["ROAD"]
def stamp(arr, gm, dz=0):
    gx, gy, gz = gm[0], gm[1], gm[2] + RD + dz
    sx, sy, sz = arr.shape
    x0, y0, z0 = max(gx, 0), max(gy, 0), max(gz, 0)
    reg = Gc[x0:gx + sx, y0:gy + sy, z0:gz + sz]
    a = arr[x0 - gx:x0 - gx + reg.shape[0], y0 - gy:y0 - gy + reg.shape[1], z0 - gz:z0 - gz + reg.shape[2]]
    reg[a > 0] = a[a > 0]
for d in ns["DOORS"]:
    stamp(d["arr"], d["gmin"])
for c in ns["CURTAINS"]:
    dx, dz = c["slide"] if c["start_open"] else (0, 0)
    stamp(c["arr"], (c["gmin"][0] + dx, c["gmin"][1], c["gmin"][2] + dz))
for e in ns["ELEVATORS"]:
    stamp(e["arr"], e["gmin"])
for (arr, gm, *_r) in ns["ROOM_SWITCHES"]:
    stamp(arr, gm)
stamp(ns["BELL"]["arr"], ns["BELL"]["gmin"]); stamp(ns["RADIO"]["arr"], ns["RADIO"]["gmin"])
for (nm, arr, gm, l) in ns["ROOF_SHAPES"]:
    stamp(arr, gm)
for (arr, gm, l) in ns["ROAD_LAMPS"]:
    stamp(arr, gm)
Hh = ns["HELI"]
stamp(ns["HELI_BODY"], Hh["gmin"]); stamp(ns["HELI_ROTOR"], Hh["rotor_gmin"]); stamp(ns["HELI_TAIL"], Hh["tail_gmin"])
PS = ns["PROP_SHAPES"]
for (pname, gx, gy, gz, roty) in ns["PROPS"]:
    stamp(PS[pname], (gx, gy, gz))
for (kind, fb, gx, gy, gz, ry) in ns["CAR_SPOTS"]:
    stamp(PS[fb], (gx, gy, gz))                           # (in game: base-game vehicles; here our own car model)

# lamps of dark rooms / switched-off TVs are not glowing at the start
dark_lamp = np.zeros(Gc.shape, bool)
on_lights = []
for L in ns["LAMPS"]:
    tags = L["lights"][0][6]
    t = dict(kv.split("=") for kv in tags.split() if "=" in kv)
    on = True
    if "room" in t:
        st = STATE.get(int(t["room"]), "dark_closed")
        on = (st == "tv") if t.get("rl") == "tv" else st.startswith("lit")
    if not on:
        V = np.array(L["vox"]); dark_lamp[V[:, 0], V[:, 1], V[:, 2] + RD] = True
    else:
        on_lights += [l for l in L["lights"]]
LIGHTS = [l for l in ns["LIGHTS"] if "room=" not in l[6]] + [l for l in on_lights if "room=" in l[6]]
LIGHTS += [(q[0], q[1], q[2], (1.0, 0.75, 0.45), 6.0, 0.3, "") for (a, g, q) in ns["ROAD_LAMPS"]]
for (nm, arr, gm, lts) in ns["ROOF_SHAPES"]:
    LIGHTS += [(l[0], l[1], l[2], l[3], l[4], l[5], "") for l in lts]

# ---------------------------------------------------------------- shots (grid units; z of the combined grid)
ax0, ax1, az0, az1, bx0, bx1, bz0, bz1 = (ns[k] for k in ("ax0", "ax1", "az0", "az1", "bx0", "bx1", "bz0", "bz1"))
G0, ROOF_Y, RT = ns["G0"], ns["ROOF_Y"], ns["RT"]
cx = (bx0 + bx1) / 2
SHOTS = {
    # from the far side of the street, low, looking up at the lit facade, cars and lamps in front
    "exterior": dict(cam=(cx - 300, G0 + 150, -330), look=(cx - 10, G0 + 85, bz0 + RD + 90), fov=50,
                     crop=(0, W, 0, HN, 0, D + RD), sky=(0.05, 0.038, 0.095), moon=0.6, fog=(0.10, 0.08, 0.16, 260.0)),
    # inside the atrium: from the lobby floor looking up across the purple-lit galleries
    "atrium": dict(cam=(ax0 + 22, G0 + 16, az0 + RD + 16), look=(ax1 - 40, G0 + 120, az1 + RD - 60), fov=74,
                   crop=(bx0 - 4, bx1 + 4, 0, HN, bz0 + RD - 4, bz1 + RD + 4), sky=(0.02, 0.015, 0.04), moon=0.0, fog=(0.05, 0.035, 0.08, 400.0)),
    # the helipad at night, helicopter in the floodlights
    "helipad": dict(cam=(ax1 + 40, RT + 46, az0 + RD - 40), look=((ax0 + ax1) / 2, RT + 8, (az0 + az1) / 2 + RD), fov=55,
                    crop=(0, W, ROOF_Y - 30, HN, 0, D + RD), sky=(0.035, 0.028, 0.07), moon=0.5, fog=(0.10, 0.08, 0.16, 300.0)),
}
# which lights matter for each shot (Mitsuba picks lights uniformly: far-away ones would only add noise;
# room interiors still glow through the windows by their emissive curtains / lamps)
def outdoor(gx, gy, gz):
    return gx < bx0 - 1 or gx > bx1 + 1 or gz < bz0 - 1 or gz > bz1 + 1 or gy >= ROOF_Y - 2
def in_atrium(gx, gy, gz):
    return ax0 - 2 <= gx <= ax1 + 2 and az0 - 2 <= gz <= az1 + 2
SHOTS["exterior"]["lights"] = lambda gx, gy, gz: outdoor(gx, gy, gz) and gz < bz1
SHOTS["atrium"]["lights"] = in_atrium
SHOTS["helipad"]["lights"] = lambda gx, gy, gz: gy >= ROOF_Y - 2
S = SHOTS[args.shot]
x0, x1, y0, y1, z0, z1 = S["crop"]
sub = Gc[x0:x1, y0:y1, z0:z1]
dsub = dark_lamp[x0:x1, y0:y1, z0:z1]
print("crop", sub.shape, "solid", int((sub > 0).sum()))

# ---------------------------------------------------------------- faces -> merged quads per colour
GLASS_IDX = {i for i, v in PAL.items() if v[1] == "glass"}
glass_m = np.isin(sub, list(GLASS_IDX))
solid = sub > 0
def faces(axis, sign):
    """visible faces of voxels whose neighbour in (axis, sign) is empty, or glass seen from non-glass."""
    nb = np.zeros_like(solid); ng = np.zeros_like(solid)
    sl_src = [slice(None)] * 3; sl_dst = [slice(None)] * 3
    if sign > 0:
        sl_src[axis] = slice(1, None); sl_dst[axis] = slice(0, -1)
    else:
        sl_src[axis] = slice(0, -1); sl_dst[axis] = slice(1, None)
    nb[tuple(sl_dst)] = solid[tuple(sl_src)]; ng[tuple(sl_dst)] = glass_m[tuple(sl_src)]
    vis = solid & (~nb | (ng & ~glass_m))
    return vis
quads = {}   # colour key -> list of (corner arrays)
def add_quads(axis, sign):
    vis = faces(axis, sign)
    X, Y, Z = np.nonzero(vis)
    if not len(X):
        return
    C = sub[X, Y, Z].astype(np.int32)
    C = np.where(dsub[X, Y, Z], C + 1000, C)                 # dark (switched-off) lamps: own key
    P = np.stack([X, Y, Z], 1)
    # merge runs along one in-plane axis: u = run axis, v = other in-plane axis
    u_ax = 2 if axis != 2 else 0
    v_ax = 3 - axis - u_ax
    order = np.lexsort((P[:, u_ax], P[:, v_ax], P[:, axis], C))
    P, C = P[order], C[order]
    brk = np.ones(len(P), bool)
    brk[1:] = (C[1:] != C[:-1]) | (P[1:, axis] != P[:-1, axis]) | (P[1:, v_ax] != P[:-1, v_ax]) | (P[1:, u_ax] != P[:-1, u_ax] + 1)
    starts = np.nonzero(brk)[0]
    ends = np.append(starts[1:], len(P)) - 1
    S0, E0, CC = P[starts], P[ends], C[starts]
    plane = S0[:, axis] + (1 if sign > 0 else 0)
    lo_u, hi_u = S0[:, u_ax], E0[:, u_ax] + 1
    lo_v, hi_v = S0[:, v_ax], S0[:, v_ax] + 1
    for col in np.unique(CC):
        m = CC == col
        n = int(m.sum())
        corners = np.zeros((n, 4, 3), np.float32)
        for k, (uu, vv) in enumerate(((lo_u, lo_v), (hi_u, lo_v), (hi_u, hi_v), (lo_u, hi_v))):
            corners[:, k, axis] = plane[m]
            corners[:, k, u_ax] = uu[m]
            corners[:, k, v_ax] = vv[m]
        # winding so the normal points along (axis, sign)
        if (sign > 0) != ((u_ax, v_ax) in ((1, 2), (2, 0), (0, 1))):
            corners = corners[:, ::-1, :]
        quads.setdefault(int(col), []).append(corners)
for axis in range(3):
    for sign in (1, -1):
        add_quads(axis, sign)
print("colours", len(quads), "quads", sum(sum(len(q) for q in v) for v in quads.values()))

# ---------------------------------------------------------------- materials
def lin(c):
    c = np.array(c, float) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
tmp = tempfile.mkdtemp(prefix="liminal_pt_")
def write_ply(path, corners):
    # grow every quad by 1 mm in its plane: neighbouring quads overlap, so no ray slips through the seams
    ctr = corners.mean(axis=1, keepdims=True)
    corners = corners + np.sign(corners - ctr) * 0.012
    V = corners.reshape(-1, 3) * 0.1
    V[:, 0] += x0 * 0.1; V[:, 1] += y0 * 0.1; V[:, 2] += z0 * 0.1
    nq = len(corners)
    F = np.zeros((nq * 2, 3), np.int32)
    base = np.arange(nq) * 4
    F[0::2] = np.stack([base, base + 1, base + 2], 1); F[1::2] = np.stack([base, base + 2, base + 3], 1)
    with open(path, "wb") as f:
        f.write((f"ply\nformat binary_little_endian 1.0\nelement vertex {len(V)}\nproperty float x\nproperty float y\nproperty float z\n"
                 f"element face {len(F)}\nproperty list uchar int vertex_indices\nend_header\n").encode())
        f.write(V.astype("<f4").tobytes())
        rec = np.zeros(len(F), dtype=[("n", "u1"), ("i", "<i4", 3)]); rec["n"] = 3; rec["i"] = F
        f.write(rec.tobytes())
scene = {"type": "scene",
         "integrator": {"type": "aov", "aovs": "dd.y:depth,aa:albedo,nn:sh_normal",
                        "integrator": {"type": "path", "max_depth": 8, "rr_depth": 4}},
         "sensor": {"type": "perspective", "fov": S["fov"], "fov_axis": "x",
                    "to_world": mi.ScalarTransform4f().look_at(origin=[c * 0.1 for c in S["cam"]], target=[c * 0.1 for c in S["look"]], up=[0, 1, 0]),
                    "sampler": {"type": "multijitter", "sample_count": args.spp},
                    "film": {"type": "hdrfilm", "width": args.w, "height": args.h, "rfilter": {"type": "gaussian"}}},
         "sky": {"type": "constant", "radiance": {"type": "rgb", "value": list(S["sky"])}}}
if S["moon"]:
    scene["moon"] = {"type": "directional", "direction": [0.45, -0.55, 0.7], "irradiance": {"type": "rgb", "value": [0.20 * S["moon"], 0.22 * S["moon"], 0.36 * S["moon"]]}}
for col, lst in quads.items():
    corners = np.concatenate(lst)
    p = os.path.join(tmp, f"c{col}.ply"); write_ply(p, corners)
    dark = col >= 1000
    idx = col - 1000 if dark else col
    rgb, fin, kw = PAL.get(idx, ((128, 128, 128), "diffuse", {}))
    c = lin(rgb).tolist()
    shape = {"type": "ply", "filename": p, "face_normals": True}
    if fin == "emit" and not dark and "noemit" not in args.debug:
        strength = 2.5 * kw.get("flux", 2) * kw.get("weight", 0.6)     # the real light comes from the point lights
        shape["emitter"] = {"type": "area", "radiance": {"type": "rgb", "value": [v * strength for v in c]}}
        shape["bsdf"] = {"type": "diffuse", "reflectance": {"type": "rgb", "value": c}}
    elif fin == "glass":
        shape["bsdf"] = {"type": "thindielectric", "int_ior": 1.5,
                         "specular_transmittance": {"type": "rgb", "value": [min(1, 0.55 + 0.6 * v) for v in c]}}
    elif fin == "metal":
        metal, rough = kw.get("metal", 0.5), kw.get("rough", 0.5)
        if metal >= 0.5:
            shape["bsdf"] = {"type": "roughconductor", "material": "none", "alpha": max(0.03, rough * 0.6),
                             "specular_reflectance": {"type": "rgb", "value": c}}
        else:
            shape["bsdf"] = {"type": "roughplastic", "alpha": max(0.04, rough * 0.5), "int_ior": 1.5,
                             "diffuse_reflectance": {"type": "rgb", "value": c}}
    else:
        shape["bsdf"] = {"type": "diffuse", "reflectance": {"type": "rgb", "value": c}}
    if shape["bsdf"]["type"] != "thindielectric":
        shape["bsdf"] = {"type": "twosided", "bsdf": shape["bsdf"]}
    scene[f"c{col}"] = shape
# water surfaces
for i, pool in enumerate(ns["POOLS"]):
    sy, dep, pts = pool[:3]
    xs = [q[0] for q in pts]; zs = [q[1] for q in pts]
    cxp, czp = (min(xs) + max(xs)) / 2 * 0.1, (min(zs) + max(zs)) / 2 * 0.1 + RD * 0.1
    sx_, sz_ = (max(xs) - min(xs)) * 0.05, (max(zs) - min(zs)) * 0.05
    scene[f"water{i}"] = {"type": "rectangle", "to_world": mi.ScalarTransform4f().translate([cxp, sy * 0.1, czp]).rotate([1, 0, 0], -90).scale([sx_, sz_, 1]),
                          "bsdf": {"type": "dielectric", "int_ior": 1.33}}
# point lights (in the crop, plus a margin)
nl = 0
for (gx, gy, gz, rgb, scale, size, tags) in ([] if "nolights" in args.debug else LIGHTS):
    gz2 = gz + RD
    if not (x0 - 40 <= gx < x1 + 40 and y0 - 40 <= gy < y1 + 40 and z0 - 40 <= gz2 < z1 + 40):
        continue
    if Gc[int(gx) % W, int(gy) % HN, int(gz2) % (D + RD)] > 0 or not S["lights"](gx, gy, gz):
        continue
    # small spherical bulbs instead of points: no singular light right next to lamp fixtures (fireflies)
    I = 2.2 * scale
    rad = max(0.08, min(size, 0.25))
    L_ = I / (math.pi * rad * rad)
    scene[f"l{nl}"] = {"type": "sphere", "center": [gx * 0.1, gy * 0.1, gz2 * 0.1], "radius": rad,
                       "emitter": {"type": "area", "radiance": {"type": "rgb", "value": [L_ * v for v in rgb]}},
                       "bsdf": {"type": "diffuse", "reflectance": {"type": "rgb", "value": [0, 0, 0]}}}
    nl += 1
print("lights", nl)

sc = mi.load_dict(scene)
img = np.array(mi.render(sc))
rgb, depth = img[:, :, :3], img[:, :, 3]
albedo, normal = img[:, :, 4:7], img[:, :, 7:10]
if args.debug:
    np.save((args.out or "dbg") + ".npy", img)

# ---------------------------------------------------------------- post: fireflies, fog, bloom, tone map, AI denoise, vignette, grain
from scipy.ndimage import gaussian_filter, median_filter
lum = rgb @ np.array([0.2126, 0.7152, 0.0722])
med = median_filter(lum, size=5)
cap = np.maximum(med * 4.0, 0.6)
rgb = rgb * np.minimum(1.0, cap / np.maximum(lum, 1e-6))[..., None]            # clamp isolated fireflies
fr, fg, fb, fd = S["fog"]
f = 1 - np.exp(-np.where(depth > 0, depth, 1e4) / fd)
rgb = rgb * (1 - f[..., None] * 0.85) + np.array([fr, fg, fb]) * f[..., None] * 0.35
def blur(a, s_):
    return np.stack([gaussian_filter(a[..., k], s_) for k in range(3)], -1)
bright = np.clip(rgb - 0.9, 0, None)
bloom = 0.35 * blur(bright, args.w / 160) + 0.25 * blur(bright, args.w / 40)
expo = {"exterior": 1.6, "atrium": 1.5, "helipad": 1.5}[args.shot]
def aces(x):
    a_, b_, c_, d_, e_ = 2.51, 0.03, 2.43, 0.59, 0.14
    return np.clip((x * (a_ * x + b_)) / (x * (c_ * x + d_) + e_), 0, 1)
def srgb(x):
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(np.clip(x, 0, 1), 1 / 2.4) - 0.055)
x = srgb(aces(rgb * expo)).astype(np.float32)
try:                                                   # Intel Open Image Denoise (albedo + normal guided)
    import ctypes
    for lib in ("/usr/local/lib/libtbb.so.12",):
        if os.path.exists(lib):
            ctypes.CDLL(lib, mode=ctypes.RTLD_GLOBAL)
    import oidn
    dev = oidn.NewDevice(); oidn.CommitDevice(dev)
    flt = oidn.NewFilter(dev, "RT")
    out_ = np.zeros_like(x)
    alb = np.ascontiguousarray(np.clip(albedo, 0, 1).astype(np.float32))
    nrm = np.ascontiguousarray(normal.astype(np.float32))
    oidn.SetSharedFilterImage(flt, "color", np.ascontiguousarray(x), oidn.FORMAT_FLOAT3, args.w, args.h)
    oidn.SetSharedFilterImage(flt, "albedo", alb, oidn.FORMAT_FLOAT3, args.w, args.h)
    oidn.SetSharedFilterImage(flt, "normal", nrm, oidn.FORMAT_FLOAT3, args.w, args.h)
    oidn.SetSharedFilterImage(flt, "output", out_, oidn.FORMAT_FLOAT3, args.w, args.h)
    oidn.CommitFilter(flt); oidn.ExecuteFilter(flt)
    if oidn.GetDeviceError(dev) == 0 and np.isfinite(out_).all() and out_.max() > 0:
        x = out_
        print("denoised (OIDN)")
except Exception as e_:
    print("OIDN not available:", e_)
x = np.clip(x + srgb(aces(bloom * expo)) * 0.6, 0, 1)
yy, xx = np.mgrid[0:args.h, 0:args.w]
vig = 1 - 0.28 * (((xx - args.w / 2) / (args.w / 2)) ** 2 + ((yy - args.h / 2) / (args.h / 2)) ** 2)
x = x * vig[..., None]
x = x + np.random.default_rng(1).normal(0, 0.006, x.shape)
from PIL import Image
out = args.out or os.path.join(ROOT, "previews", f"render_{args.shot}.jpg")
Image.fromarray((np.clip(x, 0, 1) * 255).astype(np.uint8)).save(out, quality=90)
print("saved", out)
