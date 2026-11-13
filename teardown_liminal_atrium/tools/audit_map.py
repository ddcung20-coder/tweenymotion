"""Automated bug audit of the generated map."""
import numpy as np, runpy, sys, collections
from scipy import ndimage
sys.argv = ['x']
ns = runpy.run_path("tools/build_map.py", run_name="chk"); ns["export"]()   # audit the world as exported (lamps cut out)
G = ns['G']; W, H, D = G.shape; PAL = ns['PAL']
inv = {}
for k, v in ns.items():
    if isinstance(v, int) and k.isupper() and v in PAL and k not in inv.values():
        inv.setdefault(v, k)
G0 = ns['G0']

# 1) floating islands per shape (Teardown judges support per shape)
XS_MAIN = [0, ns['ax0'] + 2 * ns['SHORT_BAY_W'], W]
XS_ANNEX = [0, ns['A_X0'] - 16, ns['A_X1'] + 16, W]
az0, bz1 = ns['az0'], ns['bz1']
BANDS = [(0, az0 + 68, XS_MAIN), (az0 + 68, az0 + 204, XS_MAIN), (az0 + 204, ns["AZ0"] - 6, XS_MAIN), (ns["AZ0"] - 6, D, XS_ANNEX)]
islands = []
for (z0, z1, XS) in BANDS:
    for x0, x1 in zip(XS, XS[1:]):
        sub = G[x0:x1, :, z0:z1] > 0
        lab, n = ndimage.label(sub)        # 6-connectivity (faces), like Teardown
        if n == 0: continue
        sizes = ndimage.sum(sub, lab, range(1, n + 1))
        # components touching y<=1 (bedrock/ground) are supported
        grounded = set(np.unique(lab[:, 0:2, :])) - {0}
        for i in range(1, n + 1):
            if i not in grounded:
                idx = np.argwhere(lab == i)
                c = idx[0]
                cols = collections.Counter(G[x0 + idx[:, 0], idx[:, 1], z0 + idx[:, 2]].tolist()).most_common(2)
                islands.append((int(sizes[i - 1]), (x0 + c[0], c[1], z0 + c[2]), [(inv.get(k, k), m) for k, m in cols]))
islands.sort(reverse=True)
print(f"[1] floating islands (not connected to the ground inside their shape): {len(islands)}")
for it in islands[:25]:
    print("    ", it)

# 2) dynamic props overlapping the world at load
bad = []
for (name, gx, gy, gz, r) in ns['PROPS']:
    a = ns['PROP_SHAPES'][name]; sx, sy, sz = a.shape
    reg = G[gx:gx + sx, gy:gy + sy, gz:gz + sz]
    ov = int(((reg > 0) & (a > 0)).sum())
    if ov: bad.append((name, (gx, gy, gz), ov))
print(f"[2] props overlapping world voxels: {bad}")

# 3) lights buried inside solid voxels
buried = [(round(l[0]), round(l[1]), round(l[2])) for l in ns['LIGHTS'] if G[int(l[0]), int(l[1]), int(l[2])] > 0]
print(f"[3] lights inside solid voxels: {len(buried)} {buried[:10]}")

# 4) spawn point clear (player ~ 0.4 x 1.8 x 0.4 m)
ax0, ax1 = ns['ax0'], ns['ax1']
sx_, sz_ = (ax0 + ax1) // 2, az0 + 18
print("[4] spawn column clear:", not (G[sx_ - 2:sx_ + 3, G0:G0 + 19, sz_ - 2:sz_ + 3] > 0).any())

# 5) doorways passable: closed door openings must be empty in the world grid, 1.9 m clear
blocked = 0
for d in ns['DOORS']:
    gx, gy, gz = d['gmin']; sx, sy, sz = d['arr'].shape
    if (G[gx:gx + sx, gy:gy + sy, gz:gz + sz] > 0).any(): blocked += 1
print(f"[5] door openings with world voxels inside: {blocked} / {len(ns['DOORS'])}")

hist = collections.Counter()
vox = collections.Counter()
for size, pos, cols in islands:
    hist[cols[0][0]] += 1; vox[cols[0][0]] += size
print("[1b] islands by dominant material:", hist.most_common(30))
bur = collections.Counter()
for l in ns['LIGHTS']:
    c = G[int(l[0]), int(l[1]), int(l[2])]
    if c: bur[(inv.get(int(c), c), round(l[1]))] += 1
print("[3b] buried lights by material/height:", bur.most_common(20))
