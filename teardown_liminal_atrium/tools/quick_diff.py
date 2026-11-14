#!/usr/bin/env python3
"""Quick "what changed" pictures (seconds, no ray tracing): builds the map grid for a base git revision and for
the working tree, finds the regions whose voxels differ, and draws each as a small isometric cut-away,
before | after, with the changed voxels in magenta (everything else greyed).

    python3 tools/quick_diff.py [--base HEAD~1] [--out previews/changes.jpg] [--max 6]
"""
import os, sys, subprocess, tempfile, shutil, argparse
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def snapshot(root, out):
    """run build_map.py at `root` (no export, nothing written) and save the world grid with the separate
    shapes (doors, lamps, glass bodies, roof shapes, ...) stamped in, plus the palette colours."""
    import runpy
    sys.argv = ["x"]
    cwd = os.getcwd(); os.chdir(root)
    try:
        ns = runpy.run_path(os.path.join(root, "tools", "build_map.py"), run_name="quickdiff")
    finally:
        os.chdir(cwd)
    G = ns["G"]
    def stamp(arr, gmin):
        gx, gy, gz = (int(v) for v in gmin); sx, sy, sz = arr.shape
        reg = G[gx:gx + sx, gy:gy + sy, gz:gz + sz]
        a = arr[:reg.shape[0], :reg.shape[1], :reg.shape[2]]
        reg[a > 0] = a[a > 0]
    get = lambda k: ns.get(k) or []
    for d in get("DOORS"): stamp(d["arr"], d["gmin"])
    for c in get("CURTAINS"): stamp(c["arr"], c["gmin"])
    for w in get("ROOM_SWITCHES"): stamp(w[0], w[1])
    for g in get("SWITCHGEAR"): stamp(g["arr"], g["gmin"])
    for e in get("ELEVATORS"): stamp(e["arr"], e["gmin"])
    for t in get("TAGGED_SHAPES"): stamp(t[1], t[2])
    for r in get("ROOF_SHAPES"): stamp(r[1], r[2])
    for s in get("SMART_GLASS"):
        if not s["frost"]: stamp(s["arr"], s["gmin"])
    if "HELI" in ns:
        H_ = ns["HELI"]
        stamp(ns["HELI_BODY"], H_["gmin"]); stamp(ns["HELI_ROTOR"], H_["rotor_gmin"]); stamp(ns["HELI_TAIL"], H_["tail_gmin"])
    pal = np.zeros((256, 3), np.uint8)
    for i, v in ns["PAL"].items():
        pal[i] = v[0]
    glass = np.zeros(256, bool)
    for i, v in ns["PAL"].items():
        glass[i] = v[1] == "glass"
    noise = np.zeros(256, bool)
    noise[9:25] = True                                   # plants (their shapes are hashed on y)
    for k in ("SOIL", "BEDROCK"):
        noise[ns[k]] = True                              # earth
    np.savez(out, G=G, pal=pal, glass=glass, G0=ns["G0"], noise=noise)


def iso(reg, hot, pal, glass, cut_y, maxw=760, tint=True):
    """isometric view from the south-west, above; voxels above cut_y removed; hot voxels tinted red."""
    from PIL import Image
    reg = reg.copy(); reg[:, cut_y:, :] = 0
    sx, sy, sz = reg.shape
    s = max(1, min(5, maxw // max(1, sx + sz)))
    solid = reg > 0
    pad = np.pad(solid, 1)
    # draw only voxels with a face toward the viewer (-x, -z, +y)
    vis = solid & ~(pad[:-2, 1:-1, 1:-1] & pad[1:-1, 2:, 1:-1] & pad[1:-1, 1:-1, :-2])
    X, Y, Z = np.nonzero(vis)
    if len(X) == 0:
        return Image.new("RGB", (200, 120), (24, 24, 32))
    c = pal[reg[X, Y, Z]].astype(np.float32)
    top = ~pad[X + 1, Y + 2, Z + 1]
    left = ~pad[X, Y + 1, Z + 1]
    shade = np.where(top, 1.0, np.where(left, 0.78, 0.62))
    c *= shade[:, None]
    gl = glass[reg[X, Y, Z]]
    c[gl] = c[gl] * 0.5 + np.array([170, 210, 235]) * 0.5
    h = hot[X, Y, Z] if tint else np.zeros(len(X), bool)
    if not tint:
        c *= 1.15                                         # (natural colours, a little brighter)
    g_ = c.mean(1, keepdims=True)                    # unchanged: greyed and dimmed, changed: vivid magenta
    if tint:
        c[~h] = (c[~h] * 0.35 + g_[~h] * 0.65) * 0.75
    c[h] = c[h] * 0.3 + np.array([255, 30, 220]) * 0.7
    u = (Z - X + sx) * s
    v = (sy - Y) * s + ((sx - X) + (sz - Z)) * s // 2
    depth = -X - Z + Y * 0.999                       # larger = nearer the viewer
    Wd, Hd = (sx + sz + 2) * s, (sy + (sx + sz) // 2 + 3) * s
    img = np.zeros((Hd, Wd, 3), np.uint8); img[:] = (22, 22, 30)
    order = np.argsort(depth)
    for i in range(s):
        for j in range(s):
            pu, pv = u + j, v + i
            ok = (pu >= 0) & (pu < Wd) & (pv >= 0) & (pv < Hd)
            pix = (pv * Wd + pu)
            o = order[ok[order]]
            p = pix[o][::-1]
            _, first = np.unique(p, return_index=True)   # nearest voxel per pixel
            sel = o[::-1][first]
            img.reshape(-1, 3)[pix[sel]] = np.clip(c[sel], 0, 255).astype(np.uint8)
    im = Image.fromarray(img)
    nz = np.argwhere((img != (22, 22, 30)).any(2))
    if len(nz):
        (y0, x0), (y1, x1) = nz.min(0), nz.max(0) + 1
        im = im.crop((max(0, x0 - 6), max(0, y0 - 6), min(Wd, x1 + 6), min(Hd, y1 + 6)))
    return im


def clusters(diff, maxn):
    from scipy import ndimage
    f = 4
    W, H, D = diff.shape
    small = np.zeros(((W + f - 1) // f, (H + f - 1) // f, (D + f - 1) // f), bool)
    X, Y, Z = np.nonzero(diff)
    small[X // f, Y // f, Z // f] = True
    small = ndimage.binary_dilation(small, iterations=3)
    lab, n = ndimage.label(small)
    out = []
    for i, sl in enumerate(ndimage.find_objects(lab)):
        box = [(sl[a].start * f, min(diff.shape[a], sl[a].stop * f)) for a in range(3)]
        cnt = int(diff[box[0][0]:box[0][1], box[1][0]:box[1][1], box[2][0]:box[2][1]].sum())
        if cnt:
            out.append((cnt, box))
    out.sort(key=lambda t: -t[0])
    return out[:maxn], len(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="HEAD~1")
    ap.add_argument("--out", default=os.path.join(ROOT, "previews", "changes.jpg"))
    ap.add_argument("--max", type=int, default=6)
    ap.add_argument("--snapshot", nargs=2, metavar=("ROOT", "OUT"))
    a = ap.parse_args()
    if a.snapshot:
        snapshot(*a.snapshot); return
    tmp = tempfile.mkdtemp(prefix="quickdiff_")
    wt = os.path.join(tmp, "base")
    me = os.path.abspath(__file__)
    try:
        subprocess.run(["git", "worktree", "add", "--detach", "-q", wt, a.base], cwd=ROOT, check=True)
        sub = os.path.relpath(ROOT, subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=ROOT, capture_output=True, text=True).stdout.strip())
        for (r, o) in ((os.path.join(wt, sub), os.path.join(tmp, "a.npz")), (ROOT, os.path.join(tmp, "b.npz"))):
            subprocess.run([sys.executable, me, "--snapshot", r, o], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        A = np.load(os.path.join(tmp, "a.npz")); B = np.load(os.path.join(tmp, "b.npz"))
        GA, GB = A["G"], B["G"]
        dy = int(B["G0"]) - int(A["G0"]) if "G0" in A.files else 0
        if dy > 0:                     # the map was raised (a storey added below): line the old grid up
            GA = np.pad(GA, ((0, 0), (dy, 0), (0, 0)))
        pal = B["pal"].copy(); pal[A["pal"].any(1) & ~B["pal"].any(1)] = A["pal"][A["pal"].any(1) & ~B["pal"].any(1)]
        glass = A["glass"] | B["glass"]
        sh = tuple(min(p, q) for p, q in zip(GA.shape, GB.shape))
        GA, GB = GA[:sh[0], :sh[1], :sh[2]], GB[:sh[0], :sh[1], :sh[2]]
        # after a shift the colour noise (hashed on y) moves too: compare solid / empty only
        diff = (GA > 0) != (GB > 0) if dy else GA != GB
        if dy and "noise" in B.files:                    # ...and leave out new earth and re-grown plants
            nz_ = B["noise"] | A["noise"]
            diff &= ~(nz_[GA] | nz_[GB])
        cl, total = clusters(diff, a.max + 8)
        if dy:                                           # (after a shift: drop specks of hashed-texture noise)
            cl = [c for c in cl if c[0] >= 500]
        cl = cl[:a.max]
        print(f"{int(diff.sum())} voxels changed in {total} regions; drawing {len(cl)}")
        from PIL import Image, ImageDraw, ImageFont
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
        except OSError:
            font = ImageFont.load_default()
        rows = []
        for k, (cnt, box) in enumerate(cl):
            (x0, x1), (y0, y1), (z0, z1) = box
            m = 14
            x0, z0, y0 = max(0, x0 - m), max(0, z0 - m), max(0, y0 - 6)
            x1, z1, y1 = min(sh[0], x1 + m), min(sh[2], z1 + m), min(sh[1], y1 + 4)
            d = diff[x0:x1, y0:y1, z0:z1]
            cnt_y = d.sum((0, 2)).cumsum()
            cut = int(np.searchsorted(cnt_y, cnt_y[-1] * 0.85)) + 3 if cnt_y[-1] else y1 - y0   # cut-away above most of the change
            ia = iso(GA[x0:x1, y0:y1, z0:z1], d & (GA[x0:x1, y0:y1, z0:z1] > 0), pal, glass, cut)
            added = d & (GB[x0:x1, y0:y1, z0:z1] > 0) & (GA[x0:x1, y0:y1, z0:z1] == 0)
            new_area = added.sum() > 0.8 * d.sum()           # a whole new area: show it in its own colours
            ib = iso(GB[x0:x1, y0:y1, z0:z1], d & (GB[x0:x1, y0:y1, z0:z1] > 0), pal, glass, cut, tint=not new_area)
            hh = max(ia.height, ib.height) + 26
            row = Image.new("RGB", (ia.width + ib.width + 30, hh), (14, 14, 20))
            row.paste(ia, (0, 26)); row.paste(ib, (ia.width + 30, 26))
            dr = ImageDraw.Draw(row)
            dr.text((4, 4), f"#{k + 1} BEFORE  ({a.base})", fill=(200, 200, 210), font=font)
            dr.text((ia.width + 34, 4), ("NEW  " if new_area else "") + f"AFTER   x {x0}-{x1}  z {z0}-{z1}  y {y0}-{y1}  ({cnt} voxels)", fill=(255, 110, 230), font=font)
            rows.append(row)
        if not rows:
            print("no voxel changes"); return
        Wt = max(r.width for r in rows); Ht = sum(r.height + 8 for r in rows)
        sheet = Image.new("RGB", (Wt, Ht), (14, 14, 20)); y = 0
        for r in rows:
            sheet.paste(r, (0, y)); y += r.height + 8
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        sheet.save(a.out, quality=88)
        print("saved", a.out, sheet.size)
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", wt], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
