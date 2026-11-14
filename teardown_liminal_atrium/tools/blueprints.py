#!/usr/bin/env python3
"""Blueprint floor plans of the map, one sheet per level (B1, 1F-6F, roof) plus a combined PDF.

    python3 tools/blueprints.py            -> blueprints/A-1xx_*.png + blueprints/LiminalAtrium_blueprints.pdf

Each plan is a horizontal cut 1.2 m above that level's floor: cut walls are outlined and hatched,
glass is drawn thin, everything lower (furniture, stairs, kerbs) is a light outline, floor markings
are faint, water is ruled. Doors from the door shapes, with swing arcs. Labels, structural grid,
dimensions, north arrow, scale bar and a title block are added on a classic blueprint ground."""
import os, sys, math, runpy, datetime
import numpy as np
from scipy import ndimage
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "blueprints")
os.chdir(ROOT)
argv_ = sys.argv; sys.argv = ["x"]
ns = runpy.run_path(os.path.join(ROOT, "tools", "build_map.py"), run_name="blueprints")
sys.argv = argv_
G = ns["G"]; W, H, D = G.shape; PAL = ns["PAL"]
for sg_ in ns["SMART_GLASS"]:                  # the penthouse's smart glass (static bodies): clear panes in the plan
    if not sg_["frost"]:
        gx_, gy_, gz_ = sg_["gmin"]; a_ = sg_["arr"]
        G[gx_:gx_ + a_.shape[0], gy_:gy_ + a_.shape[1], gz_:gz_ + a_.shape[2]][a_ > 0] = a_[a_ > 0]
g = lambda k: ns[k]
bx0, bx1, bz0, bz1, ax0, ax1, az0, az1 = (g(k) for k in ("bx0", "bx1", "bz0", "bz1", "ax0", "ax1", "az0", "az1"))
G0, YB, FH, FLOORS, ROOF_Y, RT = (g(k) for k in ("G0", "YB", "FH", "FLOORS", "ROOF_Y", "RT"))
T_EXT, COR_W, CB, T_PART = (g(k) for k in ("T_EXT", "COR_W", "CB", "T_PART"))
fy = g("fy")
GLASS_IDX = np.array([i for i, v in PAL.items() if v[1] == "glass"], np.uint8)
MARK_IDX = np.array([g("PAINT_LINE"), g("YELLOW_PAINT")], np.uint8)

# ---------------------------------------------------------------- style (drawn at S px / voxel, saved at half)
S = 6
BG = (17, 60, 126); GRID1 = (28, 76, 146); GRID5 = (42, 94, 166)
INK = (236, 244, 255); SOFT = (170, 200, 240); CYAN = (150, 222, 255); YEL = (255, 226, 140)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONTB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONTM = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
_fc = {}
def font(sz, f=FONTB):
    if (sz, f) not in _fc:
        _fc[(sz, f)] = ImageFont.truetype(f, sz)
    return _fc[(sz, f)]

class Sheet:
    def __init__(self, x0, x1, z0, z1, title, sub, sheet):
        self.x0, self.x1, self.z0, self.z1 = x0, x1, z0, z1
        self.ml, self.mr, self.mt, self.mb = 230, 150, 250, 420
        self.wpx, self.hpx = (x1 - x0) * S, (z1 - z0) * S
        self.Wc, self.Hc = self.wpx + self.ml + self.mr, self.hpx + self.mt + self.mb
        self.im = Image.new("RGB", (self.Wc, self.Hc), BG)
        self.title, self.sub, self.sheet = title, sub, sheet
        self.d = ImageDraw.Draw(self.im, "RGBA")

    def P(self, x, z):                    # grid (x, z) -> pixel; +z up the sheet. Teardown is right-handed with y up,
        return self.ml + (self.x1 - x) * S, self.mt + (self.z1 - z) * S       # so seen from above +x runs to the LEFT

    def grid(self):
        d = self.d
        for x in range(self.x0 - self.x0 % 10, self.x1 + 1, 10):
            if x < self.x0:
                continue
            px, _ = self.P(x, 0)
            d.line([(px, self.mt), (px, self.mt + self.hpx)], fill=GRID5 if x % 50 == 0 else GRID1, width=2 if x % 50 == 0 else 1)
        for z in range(self.z0 - self.z0 % 10, self.z1 + 1, 10):
            if z < self.z0:
                continue
            _, pz = self.P(0, z)
            d.line([(self.ml, pz), (self.ml + self.wpx, pz)], fill=GRID5 if z % 50 == 0 else GRID1, width=2 if z % 50 == 0 else 1)

    def layer(self, mask, color, alpha, mode="fill", width=3, hatch=None):
        """mask over the sheet's (x, z) window -> pixels."""
        m = np.flipud(np.fliplr(mask.T))                           # rows = z descending, cols = x descending
        big = np.kron(m, np.ones((S, S), bool))
        if mode == "outline":
            big = big & ~ndimage.binary_erosion(big, iterations=width, border_value=0)
        if hatch:
            yy, xx = np.indices(big.shape)
            big = big & (((xx + yy) % hatch) < 2)
        a = Image.fromarray((big * alpha).astype(np.uint8), "L")
        tile = Image.new("RGB", a.size, color)
        self.im.paste(tile, (self.ml, self.mt), a)
        self.d = ImageDraw.Draw(self.im, "RGBA")

    def text(self, x, z, s, sz=24, col=INK, rot=0, f=FONTB, anchor="mm", alpha=255):
        px, pz = self.P(x, z) if not isinstance(x, tuple) else x
        if rot == 0:
            self.d.text((px, pz), s, font=font(sz, f), fill=col + (alpha,), anchor=anchor)
            return
        fnt = font(sz, f)
        bb = fnt.getbbox(s)
        t = Image.new("RGBA", (bb[2] + 8, bb[3] + 8), (0, 0, 0, 0))
        ImageDraw.Draw(t).text((4, 4), s, font=fnt, fill=col + (alpha,))
        t = t.rotate(rot, expand=True)
        self.im.paste(t, (int(px - t.size[0] / 2), int(pz - t.size[1] / 2)), t)
        self.d = ImageDraw.Draw(self.im, "RGBA")

    def label(self, x, z, main, sub=None, sz=26, rot=0):
        if sub and rot == 0:
            self.text(x, z, main, sz, INK, 0)
            px, pz = self.P(x, z)
            self.text((px, pz + sz * 0.95), None, sub, int(sz * 0.6), SOFT, 0, FONT)
        else:
            self.text(x, z, main, sz, INK, rot)

    def dashed(self, a, b, col=SOFT, width=2, dash=14, gap=10):
        (xa, ya), (xb, yb) = a, b
        L = math.hypot(xb - xa, yb - ya)
        if L == 0:
            return
        ux, uy = (xb - xa) / L, (yb - ya) / L
        t = 0
        while t < L:
            e = min(t + dash, L)
            self.d.line([(xa + ux * t, ya + uy * t), (xa + ux * e, ya + uy * e)], fill=col, width=width)
            t = e + gap

    def dashed_rect(self, x0, x1, z0, z1, cross=False, col=SOFT):
        p = [self.P(x0, z0), self.P(x1, z0), self.P(x1, z1), self.P(x0, z1)]
        for i in range(4):
            self.dashed(p[i], p[(i + 1) % 4], col)
        if cross:
            self.dashed(p[0], p[2], col); self.dashed(p[1], p[3], col)

    def arrow(self, a, b, col=INK, width=3, head=16):
        self.d.line([a, b], fill=col, width=width)
        ang = math.atan2(b[1] - a[1], b[0] - a[0])
        for s_ in (2.6, -2.6):
            self.d.line([b, (b[0] + head * math.cos(ang + s_), b[1] + head * math.sin(ang + s_))], fill=col, width=width)

    # ---- sheet furniture: structural grid, dimensions, north arrow, scale bar, title block
    def struct_grid(self, xs, zs):
        top, left = self.mt - 70, self.ml - 70
        for i, x in enumerate(sorted(xs, reverse=True)):            # numbered left to right on the sheet
            px, _ = self.P(x, 0)
            self.dashed((px, top + 22), (px, self.mt + self.hpx), (90, 140, 210), 1, 18, 8)
            self.d.ellipse([px - 22, top - 22, px + 22, top + 22], outline=INK, width=3)
            self.text((px, top), None, str(i + 1), 22)
        for i, z in enumerate(zs):
            _, pz = self.P(0, z)
            self.dashed((left + 22, pz), (self.ml + self.wpx, pz), (90, 140, 210), 1, 18, 8)
            self.d.ellipse([left - 22, pz - 22, left + 22, pz + 22], outline=INK, width=3)
            self.text((left, pz), None, chr(ord("A") + len(zs) - 1 - i), 22)

    def dim(self, a, b, offset, horizontal=True, txt=None):
        if horizontal:
            (xa, _), (xb, _) = self.P(a, 0), self.P(b, 0)
            y = offset
            self.d.line([(xa, y), (xb, y)], fill=INK, width=2)
            for x_ in (xa, xb):
                self.d.line([(x_, y - 12), (x_, y + 12)], fill=INK, width=2)
                self.d.line([(x_ - 7, y + 7), (x_ + 7, y - 7)], fill=INK, width=3)
            self.text(((xa + xb) / 2, y - 18), None, txt or f"{(b - a) / 10:.1f} m", 20)
        else:
            (_, ya), (_, yb) = self.P(0, a), self.P(0, b)
            x = offset
            self.d.line([(x, ya), (x, yb)], fill=INK, width=2)
            for y_ in (ya, yb):
                self.d.line([(x - 12, y_), (x + 12, y_)], fill=INK, width=2)
                self.d.line([(x - 7, y_ + 7), (x + 7, y_ - 7)], fill=INK, width=3)
            self.text(((x - 20), (ya + yb) / 2), None, txt or f"{(b - a) / 10:.1f} m", 20, rot=90)

    def frame_and_title(self, notes=()):
        d = self.d
        d.rectangle([20, 20, self.Wc - 20, self.Hc - 20], outline=INK, width=4)
        d.rectangle([32, 32, self.Wc - 32, self.Hc - 32], outline=INK, width=1)
        y0 = self.Hc - 330
        d.rectangle([32, y0, self.Wc - 32, self.Hc - 32], outline=INK, width=3)
        c1, c2 = int(self.Wc * 0.46), int(self.Wc * 0.72)
        d.line([(c1, y0), (c1, self.Hc - 32)], fill=INK, width=2); d.line([(c2, y0), (c2, self.Hc - 32)], fill=INK, width=2)
        self.text((60, y0 + 60), None, "LIMINAL ATRIUM HOTEL", 50, anchor="lm")
        self.text((60, y0 + 125), None, self.title, 36, YEL, anchor="lm")
        self.text((60, y0 + 175), None, self.sub, 22, SOFT, f=FONT, anchor="lm")
        for i, n in enumerate(notes):
            self.text((60, y0 + 215 + i * 28), None, n, 18, SOFT, f=FONT, anchor="lm")
        # scale bar + north arrow
        sx = c1 + 40; sy = y0 + 200
        for i in range(4):
            x_ = sx + i * 25 * S
            d.rectangle([x_, sy, x_ + 25 * S, sy + 14], fill=INK if i % 2 == 0 else None, outline=INK, width=2)
            self.text((x_, sy + 36), None, f"{i * 2.5:g}", 18, f=FONT)
        self.text((sx + 100 * S, sy + 36), None, "10 m", 18, f=FONT)
        self.text((sx, sy - 40), None, "SCALE 1:100  (1 voxel = 10 cm)", 20, anchor="lm")
        nx, ny = c2 - 90, y0 + 120
        d.ellipse([nx - 60, ny - 60, nx + 60, ny + 60], outline=INK, width=3)
        d.polygon([(nx, ny - 56), (nx - 20, ny + 30), (nx, ny + 14)], fill=INK)
        d.polygon([(nx, ny - 56), (nx + 20, ny + 30), (nx, ny + 14)], outline=INK, width=2)
        self.text((nx, ny - 82), None, "N", 30)
        # sheet cell
        self.text((c2 + 40, y0 + 55), None, "SHEET", 18, SOFT, f=FONT, anchor="lm")
        self.text((c2 + 40, y0 + 105), None, self.sheet, 56, anchor="lm")
        self.text((c2 + 40, y0 + 175), None, f"DATE  {datetime.date.today().isoformat()}", 20, f=FONT, anchor="lm")
        self.text((c2 + 40, y0 + 210), None, "DRAWN  Claude  |  SOURCE  tools/build_map.py", 20, f=FONT, anchor="lm")
        self.text((c2 + 40, y0 + 245), None, "Teardown map mod - Liminal Atrium", 20, f=FONT, anchor="lm")

    def save(self, path):
        im = self.im.resize((self.Wc // 2, self.Hc // 2), Image.LANCZOS)
        im.save(path, quality=95)
        return im


def plan(sheet, floor_y, z_extra=None):
    """draw the cut plan. floor_y: level floor y, or a (W, D) array of floor y per column."""
    x0, x1, z0, z1 = sheet.x0, sheet.x1, sheet.z0, sheet.z1
    fl = np.full((x1 - x0, z1 - z0), floor_y, int) if np.isscalar(floor_y) else floor_y[x0:x1, z0:z1]
    ylo, yhi = int(fl.min()), int(fl.max()) + 14
    sub = G[x0:x1, ylo - 1:yhi, z0:z1]
    yy = np.arange(ylo - 1, yhi)[None, :, None]
    flb = fl[:, None, :]
    cut_i = (fl + 12 - (ylo - 1))
    cut = np.take_along_axis(sub, cut_i[:, None, :], 1)[:, 0, :]
    # doors / switchgear (own shapes) at the cut
    door_m = np.zeros(cut.shape, bool)
    for dd in ns["DOORS"]:
        gx, gy, gz = dd["gmin"]; a = dd["arr"]
        for xi in range(a.shape[0]):
            for zi in range(a.shape[2]):
                X, Z = gx + xi - x0, gz + zi - z0
                if 0 <= X < cut.shape[0] and 0 <= Z < cut.shape[1]:
                    yc = fl[X, Z] + 12
                    if gy <= yc < gy + a.shape[1] or (dd["kind"] == "swing" and gy <= fl[X, Z] + 3 < gy + a.shape[1]):
                        door_m[X, Z] = True
    glass = np.isin(cut, GLASS_IDX)
    earth = np.isin(cut, np.array([g("SOIL"), g("BEDROCK")], np.uint8))      # ground around the basement
    wall = (cut > 0) & ~glass & ~earth
    low = ((sub > 0) & (yy > flb) & (yy < flb + 12)).any(1) & ~wall & ~glass & ~earth
    floor_layer = np.take_along_axis(sub, (fl - 1 - (ylo - 1))[:, None, :], 1)[:, 0, :]
    marks = np.isin(floor_layer, MARK_IDX) & ~wall & ~low
    for sg in ns["SWITCHGEAR"]:
        gx, gy, gz = sg["gmin"]; a = sg["arr"]
        for xi in range(a.shape[0]):
            for zi in range(a.shape[2]):
                X, Z = gx + xi - x0, gz + zi - z0
                if 0 <= X < cut.shape[0] and 0 <= Z < cut.shape[1] and gy <= fl[X, Z] + 6 < gy + a.shape[1] and a[xi, :, zi].any():
                    low[X, Z] = True
    sheet.grid()
    if earth.any():
        sheet.layer(earth, SOFT, 28)
        yy2, xx2 = np.indices(earth.shape)
        sheet.layer(earth & ((xx2 * 7 + yy2 * 13) % 23 == 0), SOFT, 110)    # stipple
    sheet.layer(marks, YEL, 70)
    sheet.layer(low, SOFT, 40)
    sheet.layer(low, SOFT, 150, "outline", 2)
    # water
    for p_ in ns["POOLS"]:
        sy_, dep, pts = p_[:3]
        if not (fl.min() - 30 <= sy_ <= fl.max() + 10):
            continue
        poly = [sheet.P(px_, pz_) for (px_, pz_) in pts]
        wim = Image.new("L", sheet.im.size, 0)
        ImageDraw.Draw(wim).polygon(poly, fill=255)
        wa = np.array(wim) > 0
        yy_, xx_ = np.indices(wa.shape)
        rule = wa & ((yy_ % 14) < 2)
        sheet.im.paste(Image.new("RGB", sheet.im.size, CYAN), (0, 0), Image.fromarray((rule * 120 + wa * 30).astype(np.uint8)))
        sheet.d = ImageDraw.Draw(sheet.im, "RGBA")
        sheet.d.polygon(poly, outline=CYAN + (220,), width=3)
    sheet.layer(wall, INK, 45)
    sheet.layer(wall, INK, 120, hatch=14)
    sheet.layer(wall, INK, 255, "outline", 3)
    sheet.layer(glass, CYAN, 120)
    sheet.layer(glass, CYAN, 255, "outline", 2)
    sheet.layer(door_m, INK, 230)
    # swing arcs
    for dd in ns["DOORS"]:
        if dd["kind"] != "swing":
            continue
        gx, gy, gz = dd["gmin"]; a = dd["arr"]
        cx_, cz_ = gx + a.shape[0] / 2, gz + a.shape[2] / 2
        if not (x0 <= cx_ < x1 and z0 <= cz_ < z1):
            continue
        X, Z = int(cx_) - x0, int(cz_) - z0
        yc = fl[min(max(X, 0), fl.shape[0] - 1), min(max(Z, 0), fl.shape[1] - 1)] + 3
        if not (gy <= yc < gy + a.shape[1] + 1):
            continue
        px, pz = dd["pivot"]
        if a.shape[0] >= a.shape[2]:
            far = (gx + a.shape[0], cz_) if abs(px - gx) < abs(px - (gx + a.shape[0])) else (gx, cz_)
        else:
            far = (cx_, gz + a.shape[2]) if abs(pz - gz) < abs(pz - (gz + a.shape[2])) else (cx_, gz)
        dx, dz = far[0] - px, far[1] - pz
        an = math.radians(dd["ang"])
        ox, oz = px + dx * math.cos(an) + dz * math.sin(an), pz - dx * math.sin(an) + dz * math.cos(an)
        P0, P1, PO = sheet.P(px, pz), sheet.P(*far), sheet.P(ox, oz)
        r = math.hypot(P1[0] - P0[0], P1[1] - P0[1])
        a1 = math.degrees(math.atan2(P1[1] - P0[1], P1[0] - P0[0])); a2 = math.degrees(math.atan2(PO[1] - P0[1], PO[0] - P0[0]))
        lo_, hi_ = (a1, a2) if (a2 - a1) % 360 <= 180 else (a2, a1)
        sheet.d.arc([P0[0] - r, P0[1] - r, P0[0] + r, P0[1] + r], lo_, hi_, fill=SOFT + (200,), width=2)
        sheet.d.line([P0, PO], fill=INK + (230,), width=3)


def common(sheet):
    xs = [bx0] + [ax0 + i * g("SHORT_BAY_W") for i in range(g("SHORT_BAYS") + 1)] + [bx1]
    zs = [bz0] + [az0 + i * g("LONG_BAY_W") for i in range(g("LONG_BAYS") + 1)] + [bz1]
    sheet.struct_grid(xs, zs)
    sheet.dim(bx0, bx1, sheet.mt - 130)
    sheet.dim(bz0, bz1, sheet.ml - 130, horizontal=False)

def rooms(sheet, k):
    n = 0
    for (name, b, fr, bw) in ns["room_frames"]():
        n += 1
        if k == 0 and (name == "S" and b in (1, 2) or name == "N"):
            continue
        xa, xb, za, zb = fr._rect(T_PART, bw, 0, g("ROOM_D"))
        sheet.label((xa + xb) / 2, (za + zb) / 2 + 4, f"{(k + 1) * 100 + n}", sz=30)
        px, pz = sheet.P((xa + xb) / 2, (za + zb) / 2 + 4)
        sheet.text((px, pz + 30), None, "GUEST ROOM", 15, SOFT, f=FONT)

def cores(sheet, k_label=True, elec=True):
    co = ns["corner"]
    for key in ("SW", "NE"):
        x, z = co[key].pt(22, 22)
        sheet.label(x, z, "STAIR", sz=24)
        px, pz = sheet.P(x, z); sheet.text((px, pz + 28), None, "UP / DN", 15, SOFT, f=FONT)
    for key in ("NW", "SE"):
        x, z = co[key].pt(10, 22)
        sheet.text(x, z, "ELEV", 20, rot=90)
        if elec:
            x, z = co[key].pt(33, 26)
            sheet.label(x, z, "ELEC", sz=20)

def corridors(sheet, text="CORRIDOR"):
    cw = T_EXT + COR_W / 2
    sheet.text(bx0 + cw, (bz0 + bz1) / 2, text, 22, SOFT, rot=90)
    sheet.text(bx1 - cw, (bz0 + bz1) / 2, text, 22, SOFT, rot=90)
    sheet.text((bx0 + bx1) / 2 + 60, bz0 + cw, text, 22, SOFT)
    sheet.text((bx0 + bx1) / 2 - 60, bz1 - cw, text, 22, SOFT)


os.makedirs(OUT, exist_ok=True)
pages = []
M = 24
# ---------------------------------------------------------------- B1
s = Sheet(0, bx1 + M, bz0 - M - 30, bz1 + M, "LEVEL B1 - CAR PARK & LUXURY ARCADE", "Floor -3.6 m. Cut at +1.2 m above floor.", "A-100")
plan(s, YB)
common(s)
s.label((g("IX0") + g("PX1")) / 2, 300 - 40, "CAR PARK", sz=34)
for (lbl_, bays_, west_) in (("A", g("WEST_BAYS"), True), ("B", g("EAST_BAYS"), False)):
    for i, z in enumerate(bays_):
        x = g("IX0") + 12 if west_ else g("PX1") - 14
        s.text(x, z + g("BAY_W") / 2, f"{lbl_}{i + 1}", 16, YEL)
s.label((g("RX0") + g("RX1")) / 2, (g("RZ_TOP") + g("RZ_BOT")) / 2, "RAMP", sz=24)
s.arrow(s.P((g("RX0") + g("RX1")) / 2, g("RZ_BOT") - 40), s.P((g("RX0") + g("RX1")) / 2, g("RZ_TOP") + 20))
s.text((g("RX0") + g("RX1")) / 2, g("RZ_TOP") + 8, "UP TO STREET", 16, SOFT)
for (nm_, kind_, sx_, sz_) in ns["SHOPS"]:
    s.label(sx_, sz_, nm_, sz=24)
    px, pz = s.P(sx_, sz_); s.text((px, pz + 26), None, kind_.upper(), 14, SOFT, f=FONT)
s.label((g("FX0") + g("FX1")) / 2, g("FZ1") + 8, "FOUNTAIN", sz=18)
s.text((g("PRM0") + g("PRM1")) / 2, 360, "PROMENADE", 22, SOFT, rot=90)
s.text(g("PX1") + 14, 248, "AUTO DOOR", 14, YEL, rot=90)
s.text(184, g("PZ1") + 8, "AUTO DOOR", 14, YEL)
cores(s, elec=False)
s.frame_and_title(["Parking: 17 bays 2.5 x 5.0 m (A1-A6, B1-B11), 90-degree, reverse in.",
                   "Columns 0.6 x 0.6 m on the aisle edge. Hatched: no parking."])
pages.append(("A-100_B1", s))

# ---------------------------------------------------------------- 1F (with the pool annex)
fl1 = np.full((W, D), G0, int)
fl1[:, g("AZ0") - 2:] = g("DY")
s = Sheet(bx0 - M - 40, bx1 + M + 40, bz0 - M - 60, g("AZ1") + M, "LEVEL 1 - LOBBY, GUEST ROOMS & POOLROOMS",
          "Floor +/-0.0 (pool hall deck +2.0 m). Cut at +1.2 m above floor.", "A-101")
plan(s, fl1)
common(s)
rooms(s, 0)
cores(s)
corridors(s)
s.label((ax0 + ax1) / 2, (az0 + az1) / 2, "ATRIUM", sz=40)
px, pz = s.P((ax0 + ax1) / 2, (az0 + az1) / 2); s.text((px, pz + 40), None, "6 storeys, open to the roof lantern", 18, SOFT, f=FONT)
s.label((g("lx0") + g("lx1")) / 2, (g("lz0") + g("lz1")) / 2, "LOBBY", sz=34)
for (nm_, x0_, x1_, z0_, z1_) in ns["BOH"]:
    s.label((x0_ + x1_) / 2, (z0_ + z1_) / 2 + 4, nm_.upper(), sz=26)
    px, pz = s.P((x0_ + x1_) / 2, (z0_ + z1_) / 2 + 4); s.text((px, pz + 28), None, "STAFF ONLY", 15, SOFT, f=FONT)
s.arrow(s.P((bx0 + bx1) / 2, bz0 - 50), s.P((bx0 + bx1) / 2, bz0 - 6))
s.text((bx0 + bx1) / 2, bz0 - 58, "MAIN ENTRANCE", 20)
s.label(g("cxN"), g("pz0") - 12, "POOL", sz=30)
s.label(g("scx"), g("scz") + 22, "SPA", sz=22)
s.label(g("cxN"), g("iz1") - 20, "POOL HALL", sz=26)
s.text(g("cxN") + 30, (bz1 + g("AZ0")) / 2, "GLASS CONNECTOR", 18, SOFT, rot=90)
s.frame_and_title(["Room numbers are drawing references (floor x 100 + room).", "Pool hall deck is 2.0 m above the ground floor; shown cut at +1.2 m from the deck."])
pages.append(("A-101_1F", s))

# ---------------------------------------------------------------- 2F - 6F
for k in range(1, FLOORS):
    s = Sheet(bx0 - M, bx1 + M, bz0 - M, bz1 + M, f"LEVEL {k + 1} - GUEST FLOOR",
              f"Floor +{(fy(k) - G0) / 10:.1f} m. Cut at +1.2 m above floor. Corridor theme: {ns['THEMES'][k]['motif']}.", f"A-10{k + 1}")
    plan(s, fy(k))
    common(s)
    rooms(s, k)
    cores(s)
    corridors(s)
    s.dashed_rect(ax0, ax1, az0, az1, cross=True)
    s.label((ax0 + ax1) / 2, (az0 + az1) / 2 + 30, "OPEN TO", sz=30)
    s.label((ax0 + ax1) / 2, (az0 + az1) / 2 - 10, "ATRIUM BELOW", sz=30)
    s.frame_and_title(["Room numbers are drawing references (floor x 100 + room).",
                       "Electrical rooms by the elevators feed this floor (E: switch, destroyed: blackout)."])
    pages.append((f"A-10{k + 1}_{k + 1}F", s))

# ---------------------------------------------------------------- roof
s = Sheet(bx0 - M, bx1 + M, bz0 - M, bz1 + M, "ROOF PLAN - GLASSHOUSE & HELIPAD",
          f"Roof +{(ROOF_Y - G0) / 10:.1f} m, upper roof / helipad +{(RT - G0) / 10:.1f} m. Cut at +1.2 m above the roof.", "A-107")
plan(s, ROOF_Y)
up = G[s.x0:s.x1, RT - 1, s.z0:s.z1]
s.layer(np.isin(up, MARK_IDX), YEL, 150)
common(s)
s.dashed_rect(ax0 - 4, ax1 + 4, az0 - 4, az1 + 4, col=YEL)
s.label(g("HCX"), g("HCZ") + 80, "UPPER ROOF +2.6 m", sz=22)
s.label(g("HCX"), g("HCZ") - 84, "HELIPAD", sz=30)
GH = ns["GLASSHOUSE"]
s.text((GH["x0"] + GH["x1"]) / 2, GH["z0"] + 40, "GLASSHOUSE  \"FLORA\"", 26, rot=90)
s.label(GH["plaza"][0], GH["plaza"][1] + 16, "POND", sz=16)
s.text((GH["x0"] + GH["x1"]) / 2, GH["z0"] - 10, "ENTRANCE", 14, SOFT)
s.text(g("STX0") + 6, g("STZ_TOP") - 50, "STAIRS UP", 16, YEL)
for key in ("SW", "NE"):
    x, z = ns["corner"][key].pt(22, 22); s.label(x, z, "STAIR", sz=20)
    px, pz = s.P(x, z); s.text((px, pz + 24), None, "PENTHOUSE", 14, SOFT, f=FONT)
for key in ("NW", "SE"):
    x, z = ns["corner"][key].pt(10, 22); s.text(x, z, "LIFTS (ROOF STOP)", 14, rot=90)
for (hx, hz) in ns["HVAC_SPOTS"]:
    s.text(hx + 11, hz + 9, "HVAC", 14, SOFT)
PHb = ns["PENTHOUSE"]
s.text((PHb["x0"] + PHb["x1"]) / 2, (PHb["z0"] + PHb["z1"]) / 2, "PENTHOUSE SUITE", 22, rot=90)
s.text((PHb["x0"] + PHb["x1"]) / 2, (PHb["terrace_z0"] + PHb["z0"]) / 2 + 14, "TERRACE", 14, SOFT)
s.label((g("RE_X0") + g("RE_X1")) / 2, (g("RE_Z0") + g("RE_Z1")) / 2, "ELEC", sz=14)
s.frame_and_title(["Glasshouse: glass barrel vault with lantern cupola (not shown), lily pond, palms, beds.",
                   "Penthouse: all glass is smart glass (privacy switch by the entrance). ELEC: roof switchgear.",
                   "Yellow: helipad markings on the upper roof (dashed outline = upper roof edge)."])
pages.append(("A-107_ROOF", s))

ims = []
for name, sh in pages:
    path = os.path.join(OUT, name + ".png")
    ims.append(sh.save(path).convert("RGB"))
    print("saved", path)
pdf = os.path.join(OUT, "LiminalAtrium_blueprints.pdf")
ims[0].save(pdf, save_all=True, append_images=ims[1:], resolution=150)
print("saved", pdf)
