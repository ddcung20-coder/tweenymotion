#!/usr/bin/env python3
"""
Liminal Atrium - Teardown sandbox map generator (v2, high detail).

Builds the whole building as one voxel grid (1 voxel = 0.1 m), applies surface
texturing (brick bond, stone tiles, panel tone variation, carpet / wood noise),
cuts the grid into <=128^3 chunks, writes MagicaVoxel .vox files that use the
Teardown palette material ranges, writes dynamic props (cars, carts) as
separate bodies and writes main.xml with lights, spawn point and boundary.

Global grid axes == Teardown axes: gx -> +X, gy -> +Y (up), gz -> +Z.
North = +Z (the far wall in the reference photo).
"""
import os, struct, random, json, sys
import numpy as np

OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VOXDIR = os.path.join(OUT, "vox")
rng = random.Random(7)

# ----------------------------------------------------------------------------
# Palette. Teardown decides the physical material by index range:
#   1-8 glass | 9-24 grass | 25-40 dirt | 41-56 rock | 57-72 wood
#   73-88 concrete | 89-104 brick | 105-120 plaster | 121-136 weak metal
#   137-152 heavy metal | 153-168 plastic | 169-176 hard metal | 177-184 hard masonry
# The MATL finish (diffuse / metal / glass / emit) only changes the look.
# ----------------------------------------------------------------------------
PAL = {}
def P(i, rgb, fin="diffuse", **kw):
    assert i not in PAL, i
    PAL[i] = (rgb, fin, kw)
    return i

# glass (1-8): windows + every lamp (lamps shatter like real bulbs)
GLASS      = P(1, (150, 172, 192), "glass")
GLASS_EXT  = P(2, (95, 115, 135), "glass")
GLASS_DOOR = P(3, (170, 190, 200), "glass")
CEIL_LAMP  = P(4, (255, 238, 205), "emit", flux=2, weight=0.8)
COVE_LAMP  = P(5, (220, 196, 255), "emit", flux=2, weight=0.7)
STREET_LMP = P(6, (255, 210, 150), "emit", flux=3, weight=1.0)
EXIT_SIGN  = P(7, (60, 220, 90), "emit", flux=2, weight=0.7)
TV_SCREEN  = P(8, (110, 150, 255), "emit", flux=2, weight=0.6)
# grass (9-24): carpets, rugs, plants (soft)
CARP_A     = P(9, (96, 86, 76));   CARP_A2 = P(10, (88, 79, 70))
CARP_B     = P(11, (72, 80, 90));  CARP_B2 = P(12, (65, 72, 82))
COR_CARP   = P(13, (108, 36, 42)); COR_CARP2 = P(14, (97, 31, 37))
COR_GOLD   = P(15, (168, 128, 62))
RUG        = P(16, (30, 38, 34));  RUG2 = P(17, (35, 44, 39))
RUG_BRD    = P(18, (46, 56, 48))
LEAF       = P(19, (52, 92, 48));  LEAF2 = P(20, (70, 112, 58)); LEAF3 = P(21, (40, 74, 40))
LAWN       = P(22, (58, 84, 44));  LAWN2 = P(23, (66, 92, 48))
BATHMAT    = P(24, (200, 200, 195))
# dirt / rock
SOIL       = P(25, (70, 52, 38))
BEDROCK    = P(41, (80, 78, 75))
# wood (57-72)
WOOD_DARK  = P(57, (88, 60, 42));  WOOD_DARK2 = P(58, (80, 54, 38))
WOOD_MED   = P(59, (128, 90, 58)); WOOD_MED2 = P(60, (118, 83, 53))
WOOD_DOOR  = P(61, (112, 78, 50))
WOOD_HEAD  = P(62, (66, 48, 38))
WOOD_LIGHT = P(63, (165, 125, 85))
WAINS      = P(64, (120, 88, 62)); WAINS2 = P(65, (108, 78, 55))
CHAIR_RAIL = P(66, (86, 60, 42))
PICFRAME   = P(67, (150, 118, 60))
PLANTER    = P(68, (70, 50, 36))
TRUNK      = P(69, (78, 60, 44))
PARQUET    = P(70, (140, 98, 62)); PARQUET2 = P(71, (126, 88, 56))
LOUNGER    = P(72, (234, 230, 222))
# concrete (73-88)
SLAB       = P(73, (128, 126, 122))
FLOOR_STN  = P(74, (150, 124, 96)); FLOOR_STN2 = P(75, (142, 117, 90)); FLOOR_STN3 = P(76, (158, 132, 103))
FLOOR_MED  = P(77, (196, 180, 152))
FLOOR_BRD  = P(78, (112, 92, 72))
ASPHALT    = P(79, (52, 52, 56)); ASPHALT2 = P(80, (58, 58, 62))
PAINT_LINE = P(81, (200, 198, 186))
ROOF       = P(82, (92, 92, 96)); ROOF2 = P(83, (100, 100, 104))
STAIR_CONC = P(84, (150, 148, 142))
TILE       = P(85, (228, 231, 231))
TILE_DARK  = P(86, (150, 158, 160))
CURB       = P(87, (150, 150, 145))
GROUT      = P(88, (118, 100, 80))
# brick (89-104): exterior
BRICK      = P(89, (128, 72, 58)); BRICK2 = P(90, (116, 64, 52)); BRICK3 = P(91, (138, 82, 66))
EXT_TRIM   = P(93, (176, 166, 150)); EXT_TRIM2 = P(94, (165, 156, 141))
PAVER      = P(95, (120, 116, 110)); PAVER2 = P(96, (108, 104, 99))
LINTEL     = P(97, (186, 176, 160))
GROUT_TILE = P(92, (184, 194, 198))
WHITE_TILE = P(99, (236, 240, 240)); WHITE_TILE2 = P(100, (225, 231, 232))
POOL_TILE  = P(101, (122, 198, 224)); POOL_TILE2 = P(102, (104, 182, 212))
POOL_LINE  = P(103, (30, 60, 124))
COPING     = P(104, (214, 208, 196))
EXT_WALL   = P(98, (172, 162, 148))
# plaster (105-120)
ATR_WALL   = P(105, (216, 210, 224)); ATR_WALL2 = P(106, (209, 203, 218)); ATR_WALL3 = P(107, (222, 217, 230))
ATR_SEAM   = P(108, (198, 192, 208))
ROOM_WALL  = P(109, (214, 203, 178)); ROOM_WALL_B = P(110, (190, 198, 186)); ROOM_WALL_C = P(119, (205, 190, 196))
CEIL       = P(111, (226, 224, 219))
COR_WALL   = P(112, (198, 184, 160)); COR_STRIPE = P(113, (184, 168, 144))
ATR_GRID   = P(114, (186, 182, 196)); ATR_PANEL = P(115, (224, 222, 230))
STAIR_WALL = P(116, (182, 182, 176)); STAIR_WALL2 = P(117, (150, 152, 148))
CORNICE    = P(118, (206, 201, 214))
LOBBY_WALL = P(120, (196, 176, 146))
# weak metal (121-136)
FRAME      = P(121, (36, 36, 42), "metal", rough=0.6, metal=0.4)
STEEL      = P(122, (160, 160, 166), "metal", rough=0.4, metal=0.8)
ELEV_DOOR  = P(123, (176, 176, 182), "metal", rough=0.25, metal=0.9)
BRASS      = P(124, (182, 146, 70), "metal", rough=0.3, metal=0.9)
RADIATOR   = P(125, (204, 204, 198), "metal", rough=0.7, metal=0.2)
MIRROR     = P(126, (205, 214, 220), "metal", rough=0.05, metal=1.0)
HVAC       = P(127, (138, 140, 144), "metal", rough=0.6, metal=0.5)
DARK_METAL = P(128, (70, 70, 76), "metal", rough=0.5, metal=0.6)
CABLE      = P(129, (30, 30, 30), "metal", rough=0.8, metal=0.3)
TV_BODY    = P(130, (22, 22, 24), "metal", rough=0.4, metal=0.2)
FRIDGE     = P(131, (225, 225, 220), "metal", rough=0.5, metal=0.1)
CHROME     = P(132, (196, 200, 206), "metal", rough=0.1, metal=1.0)
CAR_A      = P(133, (58, 72, 96), "metal", rough=0.25, metal=0.6)
CAR_B      = P(134, (168, 168, 172), "metal", rough=0.25, metal=0.7)
CAR_C      = P(135, (112, 30, 34), "metal", rough=0.25, metal=0.6)
SWITCH     = P(136, (232, 230, 222), "metal", rough=0.7, metal=0.0)
# heavy metal
ELEV_RAIL  = P(137, (90, 90, 95), "metal", rough=0.5, metal=0.8)
# plastic (153-168)
CURT_LIT   = P(153, (238, 192, 112), "emit", flux=1, weight=0.35)
CURT_LIT2  = P(154, (214, 164, 88), "emit", flux=1, weight=0.25)
CURT_DARK  = P(155, (96, 88, 74));  CURT_DARK2 = P(156, (80, 73, 62))
SHEET      = P(157, (226, 226, 220))
BLANKET_A  = P(158, (150, 128, 104)); BLANKET_B = P(159, (120, 40, 48)); BLANKET_C = P(160, (44, 54, 84))
PILLOW     = P(161, (236, 236, 230))
UPHOL      = P(162, (72, 80, 96)); UPHOL2 = P(163, (112, 96, 80))
CERAMIC    = P(164, (236, 236, 236))
LAMPSHADE  = P(165, (250, 226, 172), "emit", flux=2, weight=0.6)
TOWEL      = P(166, (240, 240, 236))
ART1       = P(167, (60, 92, 122)); ART2 = P(168, (172, 112, 70))
# hard metal / hard masonry
RED        = P(169, (176, 30, 30), "metal", rough=0.4, metal=0.3)
TIRE       = P(170, (24, 24, 24), "metal", rough=0.9, metal=0.0)
DUMPSTER   = P(171, (40, 82, 52), "metal", rough=0.6, metal=0.4)
POOL_LAMP  = P(172, (150, 232, 255), "emit", flux=2, weight=0.8)
BASE_STONE = P(177, (122, 118, 112)); BASE_STONE2 = P(178, (110, 106, 100))
PILLAR     = P(179, (196, 188, 172))

# ----------------------------------------------------------------------------
# Dimensions (voxels)
# ----------------------------------------------------------------------------
M = 84                      # site around the building (sidewalk, lawn, parking)
T_FAC, ROOM_D, T_PART, COR_W, T_EXT = 4, 44, 2, 18, 4
T = T_FAC + ROOM_D + T_PART + COR_W + T_EXT     # ring thickness = 72
LONG_BAYS, LONG_BAY_W = 8, 34
SHORT_BAYS, SHORT_BAY_W = 4, 40
AX = SHORT_BAYS * SHORT_BAY_W        # atrium X size 160 (16 m)
AZ = LONG_BAYS * LONG_BAY_W          # atrium Z size 272 (27.2 m)
BX, BZ = AX + 2 * T, AZ + 2 * T
W, D = BX + 2 * M, BZ + 2 * M
FLOORS, FH, SLAB_T = 6, 30, 3
G0 = 4                               # ground floor surface y
ROOF_Y = G0 + FLOORS * FH            # 184: roof surface of the room ring
ATR_TOP = ROOF_Y + 22                # 206: atrium ceiling underside
H = ATR_TOP + 3 + 4 + 2 + 30         # + rooftop sign

bx0, bz0 = M, M
bx1, bz1 = M + BX, M + BZ
ax0, az0 = bx0 + T, bz0 + T
ax1, az1 = ax0 + AX, az0 + AZ
AZ0 = bz1 + 40                        # pool annex (north of the hotel)
AZ1 = AZ0 + 200
D = AZ1 + 30

G = np.zeros((W, H, D), dtype=np.uint8)
LIGHTS = []   # (gx, gy, gz, rgb, scale, size)
PROPS = []    # (name, gx, gy, gz, rot_y)

def box(x0, x1, y0, y1, z0, z1, c):
    """fill [x0,x1) x [y0,y1) x [z0,z1) (bounds in any order)."""
    xa, xb = sorted((int(x0), int(x1))); ya, yb = sorted((int(y0), int(y1))); za, zb = sorted((int(z0), int(z1)))
    G[max(xa, 0):max(xb, 0), max(ya, 0):max(yb, 0), max(za, 0):max(zb, 0)] = c

def paint(x0, x1, y0, y1, z0, z1, c, only=None):
    """recolor existing (non-empty) voxels in the box; optionally only those in `only`."""
    xa, xb = sorted((int(x0), int(x1))); ya, yb = sorted((int(y0), int(y1))); za, zb = sorted((int(z0), int(z1)))
    s = G[max(xa, 0):max(xb, 0), max(ya, 0):max(yb, 0), max(za, 0):max(zb, 0)]
    m = s > 0 if only is None else np.isin(s, only)
    s[m] = c

def light(gx, gy, gz, rgb, scale=1.0, size=0.1, tags=""):
    LIGHTS.append((gx, gy, gz, rgb, scale, size, tags))

def fy(k):
    return G0 + k * FH

# ----------------------------------------------------------------------------
# Local frame helper: build things in (u, v, y) space.
#   u runs along a wall, v runs perpendicular (from atrium outward).
# ----------------------------------------------------------------------------
class Frame:
    def __init__(self, ox, oz, ux, uz, vx, vz):
        self.ox, self.oz, self.ux, self.uz, self.vx, self.vz = ox, oz, ux, uz, vx, vz
    def pt(self, u, v):
        return self.ox + self.ux * u + self.vx * v, self.oz + self.uz * u + self.vz * v
    def _rect(self, u0, u1, v0, v1):
        xa, za = self.pt(u0, v0); xb, zb = self.pt(u1 - 1, v1 - 1)
        return min(xa, xb), max(xa, xb) + 1, min(za, zb), max(za, zb) + 1
    def box(self, u0, u1, y0, y1, v0, v1, c):
        if u1 <= u0 or v1 <= v0 or y1 <= y0:
            return
        x0, x1, z0, z1 = self._rect(u0, u1, v0, v1)
        box(x0, x1, y0, y1, z0, z1, c)
    def paint(self, u0, u1, y0, y1, v0, v1, c, only=None):
        if u1 <= u0 or v1 <= v0 or y1 <= y0:
            return
        x0, x1, z0, z1 = self._rect(u0, u1, v0, v1)
        paint(x0, x1, y0, y1, z0, z1, c, only)
    def light(self, u, y, v, rgb, scale=1.0, size=0.1, tags=""):
        x, z = self.pt(u, v)
        light(x + 0.5, y, z + 0.5, rgb, scale, size, tags)
    def mirrored(self, a, b):
        """frame with u' = a + b - 1 - u (mirror across the range [a, b))."""
        x, z = self.pt(a + b - 1, 0)
        return Frame(x, z, -self.ux, -self.uz, self.vx, self.vz)

def hash3(x, y, z, seed=0):
    h = (x.astype(np.int64) * 73856093) ^ (y.astype(np.int64) * 19349663) ^ (z.astype(np.int64) * 83492791) ^ (seed * 2654435761)
    h = (h ^ (h >> 13)) * 1274126177
    return ((h ^ (h >> 16)) & 0xFFFF) / 65535.0

# ----------------------------------------------------------------------------
# Interactive doors: separate static bodies animated by MOD/doors.lua (press E).
# ----------------------------------------------------------------------------
DOORS = []
WORLD = Frame(0, 0, 1, 0, 0, 1)

def cont(fr, U, V):
    """continuous frame point -> continuous grid point (x, z)."""
    return (fr.ox + 0.5 + fr.ux * (U - 0.5) + fr.vx * (V - 0.5),
            fr.oz + 0.5 + fr.uz * (U - 0.5) + fr.vz * (V - 0.5))

def frame_shape(fr, u0, u1, y0, y1, v0, v1, style):
    """build a separate shape for a frame box: style(a, b, c, A, B, C) -> colour (0 = empty)."""
    x0, x1, z0, z1 = fr._rect(u0, u1, v0, v1)
    arr = np.zeros((x1 - x0, y1 - y0, z1 - z0), np.uint8)
    A, B, C = u1 - u0, y1 - y0, v1 - v0
    for u in range(u0, u1):
        for v in range(v0, v1):
            x, z = fr.pt(u, v)
            for yy in range(y0, y1):
                arr[x - x0, yy - y0, z - z0] = style(u - u0, yy - y0, v - v0, A, B, C)
    return arr, (x0, y0, z0)

ELEVATORS = []     # dynamic cars driven by MOD/elevator.lua
CALLS = []         # landing call buttons (static shapes)

def add_door(fr, u0, u1, y0, y1, v0, v1, style, hinge=None, open_dir=None, slide=None, start_open=False, tag="hoteldoor"):
    """door leaf occupying a frame box; style(a, b, c, A, B, C) colours local cell
    (a along u, b up, c along v).  Swing: hinge = frame corner (U, V), open_dir = (du, dv).
    Slide: slide = (du, dv) frame offset in voxels."""
    x0, x1, z0, z1 = fr._rect(u0, u1, v0, v1)
    arr = np.zeros((x1 - x0, y1 - y0, z1 - z0), np.uint8)
    A, B, C = u1 - u0, y1 - y0, v1 - v0
    for u in range(u0, u1):
        for v in range(v0, v1):
            x, z = fr.pt(u, v)
            for yy in range(y0, y1):
                arr[x - x0, yy - y0, z - z0] = style(u - u0, yy - y0, v - v0, A, B, C)
    box(x0, x1, y0, y1, z0, z1, 0)       # keep the opening clear in the world grid
    if slide is None:                    # physical swing door: 10 cm clearance under and over the leaf
        arr = arr[:, 1:-1, :]
        y0 += 1
    d = dict(arr=arr, gmin=(x0, y0, z0), start_open=start_open, tag=tag)
    if slide is not None:
        d["kind"] = "slide"
        d["slide"] = (fr.ux * slide[0] + fr.vx * slide[1], fr.uz * slide[0] + fr.vz * slide[1])
    else:
        d["kind"] = "swing"
        px, pz = cont(fr, *hinge)
        cxm, czm = cont(fr, (u0 + u1) / 2, (v0 + v1) / 2)
        want = (fr.ux * open_dir[0] + fr.vx * open_dir[1], fr.uz * open_dir[0] + fr.vz * open_dir[1])
        best = None
        for ang in (90, -90):
            a = np.radians(ang)
            rx = (cxm - px) * np.cos(a) + (czm - pz) * np.sin(a)      # Teardown QuatEuler(0,a,0):
            rz = -(cxm - px) * np.sin(a) + (czm - pz) * np.cos(a)     # +X -> -Z for +90
            score = rx * want[0] + rz * want[1]
            if best is None or score > best[0]:
                best = (score, ang)
        d["pivot"] = (px, pz)
        d["ang"] = best[1]
    DOORS.append(d)

def wood_door(a, b, c, A, B, C):
    if (a, b) in ((A - 2, 10), (A - 2, 11)):
        return BRASS                                   # handle
    if (a in (1, A - 2) or b in (1, 2, B - 2, 10)) and 0 < a < A - 1:
        return WOOD_DARK                               # stiles / rails (panel look)
    return WOOD_DOOR

def glass_door(a, b, c, A, B, C):
    if a in (0, A - 1) or b in (0, 1, B - 1):
        return FRAME
    if b in (9, 10) and a in (1, A - 2):
        return BRASS
    return GLASS_DOOR

def steel_door(a, b, c, A, B, C):
    if b in (10, 11) and a == A - 2:
        return STEEL
    return DARK_METAL if a in (0, A - 1) or b in (0, B - 1) else HVAC

def elev_door(a, b, c, A, B, C):
    return FRAME if a == 0 else ELEV_DOOR

def keep_connected(mask, seeds):
    """boolean 3D mask -> only the part face-connected to any seed (list of index tuples)."""
    reach = np.zeros_like(mask)
    for sd in seeds:
        if mask[sd]:
            reach[sd] = True
    while True:
        grow = reach.copy()
        grow[1:] |= reach[:-1]; grow[:-1] |= reach[1:]
        grow[:, 1:] |= reach[:, :-1]; grow[:, :-1] |= reach[:, 1:]
        grow[:, :, 1:] |= reach[:, :, :-1]; grow[:, :, :-1] |= reach[:, :, 1:]
        grow &= mask
        if (grow == reach).all():
            return reach
        reach = grow

# ============================================================================
# 1. Site: ground, sidewalk, lawns, trees, parking
# ============================================================================
box(0, W, 0, 1, 0, D, BEDROCK)
box(0, W, 1, G0, 0, D, ASPHALT)
SW = 26   # sidewalk width
# sidewalk ring (raised 1 voxel), curb, lawn strip with trees
box(bx0 - SW, bx1 + SW, G0, G0 + 1, bz0 - SW, bz1 + SW, PAVER)
box(bx0, bx1, G0, G0 + 1, bz0, bz1, 0)          # (sidewalk only outside the building)
box(bx0 - SW - 2, bx1 + SW + 2, G0 - 1, G0 + 1, bz0 - SW - 2, bz0 - SW, CURB)
box(bx0 - SW - 2, bx1 + SW + 2, G0 - 1, G0 + 1, bz1 + SW, bz1 + SW + 2, CURB)
box(bx0 - SW - 2, bx0 - SW, G0 - 1, G0 + 1, bz0 - SW - 2, bz1 + SW + 2, CURB)
box(bx1 + SW, bx1 + SW + 2, G0 - 1, G0 + 1, bz0 - SW - 2, bz1 + SW + 2, CURB)
# lawn beds along the east / west / north sides
for (x0, x1, z0, z1) in [(bx0 - SW + 4, bx0 - 6, bz0 + 30, bz1 - 30), (bx1 + 6, bx1 + SW - 4, bz0 + 30, bz1 - 30),
                         (bx0 + 30, bx1 - 30, bz1 + 6, bz1 + SW - 4)]:
    box(x0, x1, G0, G0 + 2, z0, z1, LAWN)
    box(x0 - 1, x1 + 1, G0, G0 + 2, z0 - 1, z0, CURB); box(x0 - 1, x1 + 1, G0, G0 + 2, z1, z1 + 1, CURB)
    box(x0 - 1, x0, G0, G0 + 2, z0, z1, CURB); box(x1, x1 + 1, G0, G0 + 2, z0, z1, CURB)

def tree(x, z, h=None):
    h = h or rng.randint(42, 58)
    box(x - 1, x + 1, G0 + 2, G0 + h, z - 1, z + 1, TRUNK)
    cy = G0 + h
    R = 16
    xs = np.arange(x - R, x + R); ys = np.arange(cy - R, cy + R); zs = np.arange(z - R, z + R)
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    canopy = np.zeros(X.shape, bool)
    for _ in range(9):
        ox, oy, oz = rng.randint(-6, 6), rng.randint(-4, 5), rng.randint(-6, 6)
        r = rng.randint(5, 8)
        canopy |= ((X - x - ox) ** 2 + (Y - cy - oy) ** 2 * 1.3 + (Z - z - oz) ** 2) <= r * r
    canopy &= hash3(X, Y, Z, 5) > 0.18
    # the trunk top is the anchor: only foliage connected to it survives (no floating leaves)
    canopy[R - 1:R + 1, :R + 1, R - 1:R + 1] = True
    canopy = keep_connected(canopy, [(R, R - 1, R)])
    ok = (X >= 0) & (X < W) & (Y >= 0) & (Y < H) & (Z >= 0) & (Z < D) & canopy
    t = hash3(X[ok], Y[ok], Z[ok], 9)
    G[X[ok], Y[ok], Z[ok]] = np.where(t < 0.4, LEAF, np.where(t < 0.75, LEAF3, LEAF2))

for z in range(bz0 + 50, bz1 - 40, 70):
    tree(bx0 - SW // 2 - 2, z); tree(bx1 + SW // 2 + 2, z)
for x in range(bx0 + 50, bx1 - 40, 70):
    tree(x, bz1 + SW // 2 + 2)
# parking lot (south): bays, wheel stops
for i in range(13):
    x = bx0 - 30 + i * 30
    if abs(x - (bx0 + bx1) // 2) < 30:
        continue
    box(x, x + 1, G0 - 1, G0, 4, bz0 - SW - 4, PAINT_LINE)
    box(x + 8, x + 22, G0, G0 + 1, bz0 - SW - 9, bz0 - SW - 7, CURB)
# foundation slab
box(bx0, bx1, 1, G0, bz0, bz1, SLAB)

# ============================================================================
# 2. Structure shell: floor slabs, brick exterior, roof
# ============================================================================
for k in range(1, FLOORS + 1):
    y = fy(k)
    box(bx0, bx1, y - SLAB_T, y, bz0, bz1, SLAB)
box(ax0, ax1, G0 + 1, ATR_TOP, az0, az1, 0)   # atrium void

PAR = 10
for (x0, x1, z0, z1) in [(bx0, bx1, bz0, bz0 + T_EXT), (bx0, bx1, bz1 - T_EXT, bz1),
                         (bx0, bx0 + T_EXT, bz0, bz1), (bx1 - T_EXT, bx1, bz0, bz1)]:
    box(x0, x1, G0, ROOF_Y + PAR, z0, z1, BRICK)
    box(x0, x1, G0, ROOF_Y + PAR, z0, z1, BRICK)
# inner face of the exterior wall is plaster (painted later by the corridors)
box(bx0 + T_EXT - 1, bx1 - T_EXT + 1, G0, ROOF_Y, bz0 + T_EXT - 1, bz0 + T_EXT, COR_WALL)
box(bx0 + T_EXT - 1, bx1 - T_EXT + 1, G0, ROOF_Y, bz1 - T_EXT, bz1 - T_EXT + 1, COR_WALL)
box(bx0 + T_EXT - 1, bx0 + T_EXT, G0, ROOF_Y, bz0 + T_EXT, bz1 - T_EXT, COR_WALL)
box(bx1 - T_EXT, bx1 - T_EXT + 1, G0, ROOF_Y, bz0 + T_EXT, bz1 - T_EXT, COR_WALL)

def outer(x0, x1, y0, y1, depth_out, c):
    """ring on the outside face of the building, protruding depth_out voxels."""
    box(bx0 - depth_out, bx1 + depth_out, y0, y1, bz0 - depth_out, bz0, c)
    box(bx0 - depth_out, bx1 + depth_out, y0, y1, bz1, bz1 + depth_out, c)
    box(bx0 - depth_out, bx0, y0, y1, bz0, bz1, c)
    box(bx1, bx1 + depth_out, y0, y1, bz0, bz1, c)

outer(0, 0, G0, G0 + 10, 1, BASE_STONE)                     # stone plinth
outer(0, 0, G0 + 10, G0 + 11, 2, EXT_TRIM2)                 # plinth cap
for k in range(1, FLOORS):
    outer(0, 0, fy(k) - 3, fy(k) - 1, 1, EXT_TRIM)          # string course at each floor
outer(0, 0, ROOF_Y - 4, ROOF_Y, 1, EXT_TRIM)                # cornice (stepped)
outer(0, 0, ROOF_Y, ROOF_Y + 2, 2, EXT_TRIM)
for (x0, x1, z0, z1) in [(bx0 - 1, bx1 + 1, bz0 - 1, bz0 + T_EXT), (bx0 - 1, bx1 + 1, bz1 - T_EXT, bz1 + 1),
                         (bx0 - 1, bx0 + T_EXT, bz0 - 1, bz1 + 1), (bx1 - T_EXT, bx1 + 1, bz0 - 1, bz1 + 1)]:
    box(x0, x1, ROOF_Y + PAR, ROOF_Y + PAR + 1, z0, z1, LINTEL)                     # parapet coping (caps the wall)
# corner quoins (alternating long / short stones)
for west in (True, False):
    for south in (True, False):
        cxo = bx0 - 1 if west else bx1
        czo = bz0 - 1 if south else bz1
        dx = 1 if west else -1
        dz = 1 if south else -1
        for y in range(G0 + 11, ROOF_Y - 4, 6):
            L = 10 if (y // 6) % 2 == 0 else 6
            box(cxo, cxo + dx * (L + 1), y, y + 5, czo, czo + 1, EXT_TRIM)
            box(cxo, cxo + 1, y, y + 5, czo, czo + dz * (L + 1), EXT_TRIM)
# roof membrane over the room ring
box(bx0 + T_EXT, bx1 - T_EXT, ROOF_Y - 1, ROOF_Y, bz0 + T_EXT, bz1 - T_EXT, ROOF)
box(ax0, ax1, ROOF_Y - SLAB_T, ROOF_Y, az0, az1, 0)

# ============================================================================
# 3. Atrium: facade walls, windows, ceiling, floor
# ============================================================================
box(ax0 - T_FAC, ax0, G0, ATR_TOP + 3, az0 - T_FAC, az1 + T_FAC, ATR_WALL)
box(ax1, ax1 + T_FAC, G0, ATR_TOP + 3, az0 - T_FAC, az1 + T_FAC, ATR_WALL)
box(ax0 - T_FAC, ax1 + T_FAC, G0, ATR_TOP + 3, az0 - T_FAC, az0, ATR_WALL)
box(ax0 - T_FAC, ax1 + T_FAC, G0, ATR_TOP + 3, az1, az1 + T_FAC, ATR_WALL)
# outside face of the lantern above the roof
box(ax0 - T_FAC, ax0 - T_FAC + 1, ROOF_Y, ATR_TOP + 3, az0 - T_FAC, az1 + T_FAC, EXT_WALL)
box(ax1 + T_FAC - 1, ax1 + T_FAC, ROOF_Y, ATR_TOP + 3, az0 - T_FAC, az1 + T_FAC, EXT_WALL)
box(ax0 - T_FAC, ax1 + T_FAC, ROOF_Y, ATR_TOP + 3, az0 - T_FAC, az0 - T_FAC + 1, EXT_WALL)
box(ax0 - T_FAC, ax1 + T_FAC, ROOF_Y, ATR_TOP + 3, az1 + T_FAC - 1, az1 + T_FAC, EXT_WALL)
# clerestory louvres on the lantern
for x in range(ax0 + 6, ax1 - 6, 14):
    for z_ in (az0 - T_FAC, az1 + T_FAC - 1):
        box(x, x + 8, ROOF_Y + 6, ROOF_Y + 16, z_, z_ + 1, DARK_METAL)
        for yy in range(ROOF_Y + 7, ROOF_Y + 16, 2):
            box(x, x + 8, yy, yy + 1, z_ - (1 if z_ < az0 else -1), z_ + (0 if z_ < az0 else 2), HVAC)

def atrium_face_frames():
    """(frame, length, bay width, name): v=0 is the atrium-side face layer, v>0 into the wall."""
    return [
        (Frame(ax0 - 1, az0, 0, 1, -1, 0), AZ, LONG_BAY_W, "W"),
        (Frame(ax1, az1 - 1, 0, -1, 1, 0), AZ, LONG_BAY_W, "E"),
        (Frame(ax1 - 1, az0 - 1, -1, 0, 0, -1), AX, SHORT_BAY_W, "S"),
        (Frame(ax0, az1, 1, 0, 0, 1), AX, SHORT_BAY_W, "N"),
    ]

for fr, L, bw, name in atrium_face_frames():
    for k in range(FLOORS + 1):
        y = fy(k) - 2
        fr.box(0, L, y, y + 1, 0, 1, ATR_SEAM)
    for b in range(0, L, bw):
        fr.box(b, b + 1, G0, ATR_TOP, 0, 1, ATR_SEAM)
    # cornice + cove light strip
    fr.box(0, L, ATR_TOP - 7, ATR_TOP - 6, -1, 0, CORNICE)
    fr.box(0, L, ATR_TOP - 6, ATR_TOP - 4, -2, 0, CORNICE)
    fr.box(0, L, ATR_TOP - 4, ATR_TOP - 3, -2, -1, COVE_LAMP)
    fr.box(0, L, ATR_TOP - 3, ATR_TOP, -1, 0, CORNICE)
    # low skirting + floor grilles every bay
    fr.box(0, L, G0, G0 + 2, -1, 0, ATR_SEAM)
    for b in range(bw // 2 - 4, L, bw):
        fr.box(b, b + 8, G0 + 3, G0 + 6, -1, 0, DARK_METAL)
        for u in range(b, b + 8, 2):
            fr.box(u, u + 1, G0 + 3, G0 + 6, -1, 0, HVAC)
    # sprinkler heads + smoke detectors near the top
    for u in range(bw // 2, L, bw):
        fr.box(u, u + 1, ATR_TOP - 9, ATR_TOP - 8, -1, 0, CHROME)

# ceiling: square grid of panels (photo: fine square grid)
box(ax0, ax1, ATR_TOP, ATR_TOP + 3, az0, az1, ATR_PANEL)
for x in range(ax0, ax1, 12):
    box(x, x + 1, ATR_TOP, ATR_TOP + 1, az0, az1, ATR_GRID)
for z in range(az0, az1, 12):
    box(ax0, ax1, ATR_TOP, ATR_TOP + 1, z, z + 1, ATR_GRID)
box(ax0 - T_FAC, ax1 + T_FAC, ATR_TOP + 3, ATR_TOP + 4, az0 - T_FAC, az1 + T_FAC, ROOF)
for (x0, x1, z0, z1) in [(ax0 - T_FAC, ax1 + T_FAC, az0 - T_FAC, az0 - T_FAC + 1), (ax0 - T_FAC, ax1 + T_FAC, az1 + T_FAC - 1, az1 + T_FAC),
                         (ax0 - T_FAC, ax0 - T_FAC + 1, az0 - T_FAC, az1 + T_FAC), (ax1 + T_FAC - 1, ax1 + T_FAC, az0 - T_FAC, az1 + T_FAC)]:
    box(x0, x1, ATR_TOP + 4, ATR_TOP + 6, z0, z1, EXT_TRIM)
for i in range(3):
    for j in range(5):
        cx = ax0 + 30 + i * 50; cz = az0 + 28 + j * 54
        box(cx - 2, cx + 2, ATR_TOP - 1, ATR_TOP, cz - 2, cz + 2, COVE_LAMP)
        box(cx - 3, cx + 3, ATR_TOP - 1, ATR_TOP, cz - 3, cz - 2, CHROME)
        box(cx - 3, cx + 3, ATR_TOP - 1, ATR_TOP, cz + 2, cz + 3, CHROME)

# floor: stone tiles 12x12 with grout, dark border, 2x2 rugs, round medallion
cxA, czA = (ax0 + ax1) / 2, (az0 + az1) / 2
XS, ZS = np.meshgrid(np.arange(ax0, ax1), np.arange(az0, az1), indexing="ij")
tile_id = hash3((XS - ax0) // 12, np.zeros_like(XS), (ZS - az0) // 12, 3)
fl = np.where(tile_id < 0.33, FLOOR_STN, np.where(tile_id < 0.66, FLOOR_STN2, FLOOR_STN3)).astype(np.uint8)
fl[((XS - ax0) % 12 == 0) | ((ZS - az0) % 12 == 0)] = GROUT
edge = (XS < ax0 + 6) | (XS >= ax1 - 6) | (ZS < az0 + 6) | (ZS >= az1 - 6)
fl[edge] = FLOOR_BRD
path = 22
for sx in (-1, 1):
    for sz in (-1, 1):
        xa, xb = sorted((cxA + sx * path / 2, cxA + sx * (AX / 2 - 16)))
        za, zb = sorted((czA + sz * path / 2, czA + sz * (AZ / 2 - 26)))
        rr = (XS >= xa) & (XS < xb) & (ZS >= za) & (ZS < zb)
        fl[rr] = RUG_BRD
        inner = (XS >= xa + 2) & (XS < xb - 2) & (ZS >= za + 2) & (ZS < zb - 2)
        fl[inner] = RUG
        # thin inner border line (woven look)
        line = inner & ~((XS >= xa + 4) & (XS < xb - 4) & (ZS >= za + 4) & (ZS < zb - 4))
        fl[line & ((XS == np.floor(xa) + 3) | (XS == np.ceil(xb) - 4) | (ZS == np.floor(za) + 3) | (ZS == np.ceil(zb) - 4))] = RUG_BRD
e = ((XS + 0.5 - cxA) / 30) ** 2 + ((ZS + 0.5 - czA) / 22) ** 2
fl[e <= 1.0] = FLOOR_BRD
fl[e <= 0.86] = FLOOR_MED
fl[(e <= 0.55) & (e > 0.45)] = FLOOR_BRD
fl[e <= 0.12] = FLOOR_STN3
G[ax0:ax1, G0 - 1, az0:az1] = fl

# the long cables + window-cleaning cradle (right side of the far wall, as in the photo)
box(ax0 + 21, ax0 + 22, G0 + 12, ATR_TOP, az1 - 3, az1 - 2, CABLE)
box(ax0 + 13, ax0 + 14, G0 + 12, ATR_TOP, az1 - 3, az1 - 2, CABLE)
box(ax0 + 10, ax0 + 25, G0 + 8, G0 + 9, az1 - 6, az1 - 1, STEEL)
box(ax0 + 10, ax0 + 25, G0 + 9, G0 + 12, az1 - 6, az1 - 5, STEEL)
box(ax0 + 10, ax0 + 25, G0 + 12, G0 + 13, az1 - 6, az1 - 1, STEEL)
box(ax0 + 10, ax0 + 11, G0, G0 + 12, az1 - 6, az1 - 1, STEEL)
box(ax0 + 24, ax0 + 25, G0, G0 + 12, az1 - 6, az1 - 1, STEEL)
box(ax0 + 12, ax0 + 15, G0 + 9, G0 + 11, az1 - 4, az1 - 2, RED)      # control box
# benches
for (bxx, bzz) in [(ax0 + 14, czA - 6), (ax1 - 20, czA - 6)]:
    box(bxx, bxx + 6, G0 + 3, G0 + 5, bzz, bzz + 12, WOOD_MED)
    for zz in range(int(bzz), int(bzz) + 12, 2):
        box(bxx, bxx + 6, G0 + 4, G0 + 5, zz, zz + 1, WOOD_MED2)
    box(bxx, bxx + 1, G0, G0 + 3, bzz, bzz + 12, DARK_METAL)
    box(bxx + 5, bxx + 6, G0, G0 + 3, bzz, bzz + 12, DARK_METAL)

def leaf_blob(cx_, cy_, cz_, r, seed, col=LEAF, anchor=None, squash=1.4, keep=0.35):
    xs = np.arange(cx_ - r - 1, cx_ + r + 2); ys = np.arange(cy_ - r - 1, cy_ + r + 2); zs = np.arange(cz_ - r - 1, cz_ + r + 2)
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    m = (((X - cx_) ** 2 + ((Y - cy_) * squash) ** 2 + (Z - cz_) ** 2) <= r * r) & (hash3(X, Y, Z, seed) > keep)
    ax_, ay_, az_ = anchor if anchor else (cx_, cy_ - r, cz_)
    sd = (ax_ - xs[0], ay_ - ys[0], az_ - zs[0])
    if 0 <= sd[0] < m.shape[0] and 0 <= sd[1] < m.shape[1] and 0 <= sd[2] < m.shape[2]:
        m[sd] = True
        m = keep_connected(m, [sd])
    G[X[m], Y[m], Z[m]] = col

def potted_plant(x, z, h=28, pot=8):
    box(x - pot // 2, x + pot // 2, G0, G0 + 8, z - pot // 2, z + pot // 2, PLANTER)
    box(x - pot // 2 + 1, x + pot // 2 - 1, G0 + 7, G0 + 8, z - pot // 2 + 1, z + pot // 2 - 1, SOIL)
    box(x, x + 1, G0 + 8, G0 + h - 6, z, z + 1, TRUNK)
    cy = G0 + h - 6
    leaf_blob(x, cy, z, 7, 11, LEAF, anchor=(x, G0 + h - 7, z))

for (px, pz) in [(ax0 + 10, az0 + 10), (ax1 - 10, az0 + 10), (ax1 - 10, az1 - 12)]:
    potted_plant(px, pz)

# luggage cart (dynamic prop) near the far wall
PROPS.append(("luggage_cart", ax0 + 46, G0, az1 - 14, 15))

# atrium lights (purple, as in the photo)
# one light right under every ceiling downlight (same grid as the fixtures above)
for i in range(3):
    for j in range(5):
        light(ax0 + 30 + i * 50, ATR_TOP - 1.5, az0 + 28 + j * 54, (0.8, 0.66, 1.0), 2.6, 0.25)
# cove strip: a light every bay, just in front of the glowing strip, so it reads as one continuous line
for fr, L, bw, name in atrium_face_frames():
    for u in range(bw // 2, L, bw):
        x, z = fr.pt(u, -3)
        light(x + 0.5, ATR_TOP - 4.5, z + 0.5, (0.85, 0.7, 1.0), 1.1, 0.15)

# ============================================================================
# 4. Hotel rooms
# ============================================================================
STATES = (["lit_closed"] * 20 + ["lit_open"] * 8 + ["dark_closed"] * 30 + ["dark_open"] * 22 +
          ["dark_blinds"] * 8 + ["tv"] * 12)
room_log = []

def room_frames():
    F = []
    for b in range(LONG_BAYS):
        F.append(("W", b, Frame(ax0 - T_FAC - 1, az0 + b * LONG_BAY_W, 0, 1, -1, 0), LONG_BAY_W))
    for b in range(LONG_BAYS):
        F.append(("E", b, Frame(ax1 + T_FAC, az1 - 1 - b * LONG_BAY_W, 0, -1, 1, 0), LONG_BAY_W))
    for b in range(SHORT_BAYS):
        F.append(("S", b, Frame(ax1 - 1 - b * SHORT_BAY_W, az0 - T_FAC - 1, -1, 0, 0, -1), SHORT_BAY_W))
    for b in range(SHORT_BAYS):
        F.append(("N", b, Frame(ax0 + b * SHORT_BAY_W, az1 + T_FAC, 1, 0, 0, 1), SHORT_BAY_W))
    return F

WIN_W, WIN_H, SILL = 16, 14, 9
WALLS_ROOM = [ROOM_WALL, ROOM_WALL_B, ROOM_WALL_C, ATR_WALL, COR_WALL]

def window_in_facade(fr, bw, y):
    """facade occupies v in [-T_FAC, 0)."""
    u0 = bw // 2 - WIN_W // 2 + 1
    fr.box(u0, u0 + WIN_W, y + SILL, y + SILL + WIN_H, -T_FAC, 0, 0)
    fr.box(u0, u0 + WIN_W, y + SILL, y + SILL + 1, -T_FAC, -1, FRAME)
    fr.box(u0, u0 + WIN_W, y + SILL + WIN_H - 1, y + SILL + WIN_H, -T_FAC, -1, FRAME)
    fr.box(u0, u0 + 1, y + SILL, y + SILL + WIN_H, -T_FAC, -1, FRAME)
    fr.box(u0 + WIN_W - 1, u0 + WIN_W, y + SILL, y + SILL + WIN_H, -T_FAC, -1, FRAME)
    fr.box(u0 + 1, u0 + WIN_W - 1, y + SILL + 1, y + SILL + WIN_H - 1, -T_FAC + 1, -T_FAC + 2, GLASS)
    fr.box(u0 + WIN_W // 2, u0 + WIN_W // 2 + 1, y + SILL + 1, y + SILL + WIN_H - 1, -T_FAC + 2, -T_FAC + 3, FRAME)  # sash
    fr.box(u0 - 1, u0 + WIN_W + 1, y + SILL - 1, y + SILL, -1, 1, WOOD_LIGHT)                                   # inner sill
    return u0

def curtains(fr, u0, y, state):
    cu0, cu1 = u0 - 4, u0 + WIN_W + 4
    top, bot = y + SILL + WIN_H + 3, y + SILL - 3
    fr.box(cu0 - 1, cu1 + 1, top, top + 1, 1, 3, BRASS)
    fr.box(cu0 - 2, cu0 - 1, top - 1, top + 2, 1, 2, BRASS)
    fr.box(cu1 + 1, cu1 + 2, top - 1, top + 2, 1, 2, BRASS)
    if state == "dark_blinds":
        for yy in range(y + SILL + 1, y + SILL + WIN_H - 1, 2):
            fr.box(u0 - 1, u0 + WIN_W + 1, yy, yy + 1, 0, 1, SWITCH)
        spans = [(cu0, cu0 + 5), (cu1 - 5, cu1)]
        a, b = CURT_DARK, CURT_DARK2
    else:
        lit = state.startswith("lit")
        a, b = (CURT_LIT, CURT_LIT2) if lit else (CURT_DARK, CURT_DARK2)
        spans = [(cu0, cu1)] if state.endswith("closed") else [(cu0, cu0 + 6), (cu1 - 6, cu1)]
    for s0, s1 in spans:
        fr.box(s0, s1, bot, top + 1, 2, 3, b)                       # continuous back layer (holds the folds)
        for u in range(s0, s1):
            if (u // 2) % 2 == 0:
                fr.box(u, u + 1, bot, top, 1, 2, a)                 # front folds
        # tie-back sag at the bottom of open panels
        if len(spans) == 2:
            fr.box(s0, s1, bot, bot + 1, 1, 2, 0)

def wall_art(fr, u_face, y0, v0, w, h, along_v=True, plane=None):
    """picture on a wall plane. u_face: the wall layer (u) to hang on, v0..v0+w along v."""
    fr.box(u_face, u_face + 1, y0, y0 + h, v0, v0 + w, PICFRAME)
    cols = rng.choice([(ART1, ART2, CEIL), (ART2, BLANKET_A, ART1), (LEAF, ART1, CEIL), (BLANKET_B, ART2, BLANKET_A)])
    for yy in range(y0 + 1, y0 + h - 1):
        for vv in range(v0 + 1, v0 + w - 1):
            t = ((yy - y0) * 3 + (vv - v0) * 2 + rng.randint(0, 2)) // max(1, (h + w) // 3)
            fr.box(u_face, u_face + 1, yy, yy + 1, vv, vv + 1, cols[t % 3])

def furnish_room(fr, bw, k, state, twin, blanket, carpet):
    y = fy(k)
    U0, U1 = T_PART, bw
    lit = state.startswith("lit")
    # carpet with fibre noise is applied in the texture pass; base colour here
    fr.box(U0, U1, y - 1, y, 0, ROOM_D, carpet)
    # skirting boards
    fr.paint(U0 - 1, U0, y, y + 1, 0, ROOM_D, WOOD_DARK, WALLS_ROOM)
    fr.paint(U1, U1 + 1, y, y + 1, 0, ROOM_D, WOOD_DARK, WALLS_ROOM)
    fr.paint(U0, U1, y, y + 1, ROOM_D, ROOM_D + 1, WOOD_DARK, WALLS_ROOM)
    fr.paint(U0, U1, y, y + 1, -1, 0, WOOD_DARK, WALLS_ROOM)
    # radiator under the window
    fr.box(bw // 2 - 8, bw // 2 + 9, y + 1, y + 6, 0, 2, RADIATOR)
    for u in range(bw // 2 - 8, bw // 2 + 9, 2):
        fr.box(u, u + 1, y + 1, y + 5, 2, 3, RADIATOR)
    fr.box(bw // 2 - 8, bw // 2 - 7, y, y + 1, 0, 2, RADIATOR)
    fr.box(bw // 2 + 8, bw // 2 + 9, y, y + 1, 0, 2, RADIATOR)
    # ---- beds: head against the u = U1 partition
    bl = 19
    bu1 = U1; bu0 = U1 - bl
    if twin:
        beds = [(4, 10), (19, 10)]          # (v0, width)
        stands = [(15, 3)]
    else:
        beds = [(9, 16)]
        stands = [(4, 4), (26, 4)]
    unmade = rng.random() < 0.3
    for (bv0, bwid) in beds:
        fr.box(bu0, bu1, y + 1, y + 3, bv0, bv0 + bwid, WOOD_DARK)            # frame
        for (lu, lv) in ((bu0, bv0), (bu0, bv0 + bwid - 1), (bu1 - 2, bv0), (bu1 - 2, bv0 + bwid - 1)):
            fr.box(lu, lu + 1, y, y + 1, lv, lv + 1, WOOD_DARK)                # legs
        fr.box(bu0, bu1 - 1, y + 3, y + 6, bv0, bv0 + bwid, SHEET)             # mattress
        if unmade:
            fr.box(bu0, bu1 - 11, y + 6, y + 7, bv0, bv0 + bwid, blanket)
            fr.box(bu1 - 13, bu1 - 10, y + 6, y + 8, bv0, bv0 + bwid, blanket)   # folded-back lump
            fr.box(bu0 + 3, bu0 + 7, y + 7, y + 8, bv0 + 2, bv0 + bwid - 3, blanket)
        else:
            fr.box(bu0, bu1 - 7, y + 6, y + 7, bv0, bv0 + bwid, blanket)
            fr.box(bu0, bu0 + 1, y + 3, y + 7, bv0, bv0 + bwid, blanket)
            fr.box(bu1 - 9, bu1 - 7, y + 6, y + 7, bv0, bv0 + bwid, SHEET)   # turned-down sheet
            fr.box(bu0 + 4, bu0 + 7, y + 6, y + 7, bv0, bv0 + bwid, BLANKET_B if blanket != BLANKET_B else BLANKET_A)  # bed runner
        if bwid >= 14:
            fr.box(bu1 - 6, bu1 - 2, y + 6, y + 8, bv0 + 1, bv0 + 7, PILLOW)
            fr.box(bu1 - 6, bu1 - 2, y + 6, y + 8, bv0 + 9, bv0 + 15, PILLOW)
        else:
            fr.box(bu1 - 6, bu1 - 2, y + 6, y + 8, bv0 + 1, bv0 + bwid - 1, PILLOW)
        fr.box(bu1 - 1, bu1, y, y + 14, bv0 - 1, bv0 + bwid + 1, WOOD_HEAD)   # headboard
        fr.box(bu1 - 1, bu1, y + 13, y + 14, bv0 - 1, bv0 + bwid + 1, WOOD_DARK)
    for (nv, nw) in stands:
        fr.box(U1 - 5, U1, y, y + 6, nv, nv + nw, WOOD_MED)
        fr.box(U1 - 5, U1 - 4, y + 2, y + 3, nv, nv + nw, WOOD_DARK)          # drawer line
        fr.box(U1 - 3, U1 - 2, y + 6, y + 9, nv + 1, nv + 2, BRASS)
        fr.box(U1 - 4, U1 - 1, y + 9, y + 12, nv, nv + 3, LAMPSHADE if lit else UPHOL2)
        fr.box(U1 - 3, U1 - 2, y + 10, y + 11, nv + 1, nv + 2, 0)            # hollow: the bulb lives here
    fr.box(U1 - 5, U1 - 3, y + 6, y + 7, stands[0][0] + 2, stands[0][0] + 4, TV_BODY)   # phone
    if lit:
        fr.light(U1 - 3, y + 10.5, stands[0][0] + 1, (1.0, 0.78, 0.45), 1.6, 0.1)
    # art above the bed(s)
    wall_art(fr, U1 - 1 + 1, y + 16, beds[0][0] + (1 if not twin else 4), 14, 7)
    # ---- desk + TV + mirror on the opposite wall (u = U0)
    fr.box(U0, U0 + 6, y + 7, y + 8, 13, 30, WOOD_MED)
    fr.box(U0, U0 + 6, y, y + 7, 13, 14, WOOD_MED)
    fr.box(U0, U0 + 6, y, y + 7, 29, 30, WOOD_MED)
    fr.box(U0, U0 + 5, y + 1, y + 7, 24, 29, FRIDGE)                          # minibar
    fr.box(U0 + 5, U0 + 6, y + 4, y + 5, 25, 28, CHROME)
    fr.box(U0, U0 + 1, y + 10, y + 19, 15, 28, TV_BODY)
    fr.box(U0 + 1, U0 + 2, y + 11, y + 18, 16, 27, TV_SCREEN if state == "tv" else TV_BODY)
    fr.box(U0, U0 + 3, y + 8, y + 10, 20, 23, TV_BODY)                        # stand (touches the TV)
    if state == "tv":
        fr.light(U0 + 3, y + 14, 21.5, (0.45, 0.6, 1.0), 1.0, 0.2)
    fr.box(U0 + 2, U0 + 4, y + 8, y + 9, 14, 17, CERAMIC)                     # kettle tray
    fr.box(U0 + 2, U0 + 3, y + 9, y + 11, 15, 16, STEEL)
    fr.box(U0 + 3, U0 + 5, y, y + 4, 14, 16, DARK_METAL)                      # trash bin
    fr.box(U0 + 3, U0 + 5, y + 1, y + 4, 14, 16, 0)
    fr.box(U0 + 3, U0 + 5, y, y + 1, 14, 16, DARK_METAL)
    # chair (pushed in or pulled out)
    co = rng.choice([0, 2, 4])
    fr.box(U0 + 7 + co, U0 + 11 + co, y + 4, y + 5, 19, 24, UPHOL)
    fr.box(U0 + 10 + co, U0 + 11 + co, y + 5, y + 11, 19, 24, UPHOL)
    for cu in (U0 + 7 + co, U0 + 10 + co):
        for cv in (19, 23):
            fr.box(cu, cu + 1, y, y + 4, cv, cv + 1, DARK_METAL)
    # armchair + side table by the window
    fr.box(U0 + 2, U0 + 9, y + 1, y + 4, 3, 9, UPHOL2)
    fr.box(U0 + 2, U0 + 3, y + 4, y + 11, 3, 9, UPHOL2)
    fr.box(U0 + 2, U0 + 9, y + 4, y + 7, 3, 4, UPHOL2)
    fr.box(U0 + 2, U0 + 9, y + 4, y + 7, 8, 9, UPHOL2)
    fr.box(U0 + 3, U0 + 8, y + 4, y + 5, 4, 8, UPHOL)                          # cushion
    fr.box(U0 + 2, U0 + 3, y, y + 1, 3, 4, WOOD_DARK); fr.box(U0 + 8, U0 + 9, y, y + 1, 8, 9, WOOD_DARK)
    fr.box(U0 + 2, U0 + 3, y, y + 1, 8, 9, WOOD_DARK); fr.box(U0 + 8, U0 + 9, y, y + 1, 3, 4, WOOD_DARK)
    fr.box(U0 + 2, U0 + 5, y + 5, y + 6, 10, 13, WOOD_MED)                     # side table
    fr.box(U0 + 3, U0 + 4, y, y + 5, 11, 12, WOOD_DARK)
    # ---- bathroom (corridor-side corner, u high side)
    bu0b = U1 - 13
    v0b = ROOM_D - 13
    fr.box(bu0b, bu0b + 1, y, y + FH - SLAB_T, v0b, ROOM_D, ROOM_WALL)
    fr.box(bu0b, U1, y, y + FH - SLAB_T, v0b, v0b + 1, ROOM_WALL)
    add_door(fr, bu0b, bu0b + 1, y, y + 21, v0b + 2, v0b + 10, lambda a, b, c, A, B, C: wood_door(c, b, a, C, B, A),
             hinge=(bu0b, v0b + 2), open_dir=(-1, 0), start_open=rng.random() < 0.6)
    fr.box(bu0b, bu0b + 1, y + 21, y + 22, v0b + 1, v0b + 11, WOOD_DARK)
    fr.box(bu0b + 1, U1, y - 1, y, v0b + 1, ROOM_D, TILE)
    for uu in range(bu0b + 1, U1, 3):                                           # floor tile grout
        fr.box(uu, uu + 1, y - 1, y, v0b + 1, ROOM_D, TILE_DARK)
    fr.box(bu0b + 1, U1, y, y + 12, ROOM_D - 1, ROOM_D, TILE)
    fr.box(U1 - 1, U1, y, y + 12, v0b + 1, ROOM_D, TILE)
    fr.box(bu0b + 1, U1, y + 12, y + 13, ROOM_D - 1, ROOM_D, TILE_DARK)
    fr.box(U1 - 1, U1, y + 12, y + 13, v0b + 1, ROOM_D, TILE_DARK)
    # toilet (against the u = U1 wall)
    fr.box(U1 - 4, U1 - 1, y, y + 4, v0b + 2, v0b + 6, CERAMIC)
    fr.box(U1 - 3, U1 - 2, y + 3, y + 4, v0b + 3, v0b + 5, 0)
    fr.box(U1 - 2, U1, y + 4, y + 10, v0b + 2, v0b + 6, CERAMIC)
    fr.box(U1 - 1, U1, y + 7, y + 8, v0b + 7, v0b + 9, CHROME)                  # paper holder
    fr.box(U1 - 2, U1 - 1, y + 6, y + 8, v0b + 7, v0b + 9, TOWEL)
    # bathtub along the back wall + shower
    fr.box(bu0b + 1, bu0b + 10, y, y + 6, v0b + 6, ROOM_D - 1, CERAMIC)
    fr.box(bu0b + 2, bu0b + 9, y + 2, y + 6, v0b + 7, ROOM_D - 2, 0)
    fr.box(bu0b + 5, bu0b + 6, y + 18, y + 22, ROOM_D - 1, ROOM_D, CHROME)       # shower head (on the wall)
    fr.box(bu0b + 1, bu0b + 10, y + 23, y + 24, v0b + 6, v0b + 7, CHROME)        # curtain rod
    fr.box(bu0b + 1, bu0b + 4, y + 7, y + 23, v0b + 6, v0b + 7, TOWEL)           # shower curtain (pulled aside)
    fr.box(bu0b + 1, bu0b + 2, y + 16, y + 17, v0b + 7, ROOM_D - 2, CHROME)      # towel bar over the tub
    fr.box(bu0b + 1, bu0b + 2, y + 11, y + 16, v0b + 8, v0b + 11, TOWEL)
    # vanity against the bathroom front wall (v = v0b), mirror above
    fr.box(bu0b + 3, bu0b + 8, y, y + 9, v0b + 1, v0b + 4, WOOD_DARK)
    fr.box(bu0b + 3, bu0b + 9, y + 9, y + 10, v0b + 1, v0b + 5, CERAMIC)
    fr.box(bu0b + 4, bu0b + 7, y + 9, y + 10, v0b + 2, v0b + 4, 0)
    fr.box(bu0b + 5, bu0b + 6, y + 10, y + 12, v0b + 1, v0b + 2, CHROME)
    fr.box(bu0b + 3, bu0b + 9, y + 13, y + 22, v0b, v0b + 1, MIRROR)
    fr.box(bu0b + 3, bu0b + 9, y, y + 1, v0b + 4, v0b + 6, BATHMAT)
    fr.box(bu0b + 5, bu0b + 8, y + 26, y + 27, v0b + 5, v0b + 8, CEIL_LAMP if lit else CEIL)
    # ---- wardrobe with open hanging rail, luggage rack
    fr.box(U0, U0 + 6, y, y + 22, ROOM_D - 12, ROOM_D - 1, WOOD_DARK)
    fr.box(U0 + 1, U0 + 6, y + 1, y + 21, ROOM_D - 11, ROOM_D - 2, 0)             # hollow
    fr.box(U0 + 3, U0 + 4, y + 18, y + 19, ROOM_D - 11, ROOM_D - 2, CHROME)        # rail
    for hv in range(ROOM_D - 10, ROOM_D - 3, 2):
        fr.box(U0 + 2, U0 + 5, y + 17, y + 18, hv, hv + 1, WOOD_LIGHT)             # hangers
    if rng.random() < 0.5:
        fr.box(U0 + 2, U0 + 5, y + 8, y + 17, ROOM_D - 9, ROOM_D - 7, rng.choice([UPHOL, BLANKET_C, BLANKET_B]))  # coat
    fr.box(U0 + 1, U0 + 6, y + 6, y + 7, ROOM_D - 11, ROOM_D - 2, WOOD_MED)        # shelf
    fr.box(U0 + 6, U0 + 7, y, y + 22, ROOM_D - 12, ROOM_D - 7, WOOD_MED)          # one door closed
    fr.box(U0 + 6, U0 + 7, y + 10, y + 12, ROOM_D - 8, ROOM_D - 7, BRASS)
    if rng.random() < 0.4:    # suitcase lying at the foot of the bed
        sb = beds[0][0]
        fr.box(bu0 + 1, bu0 + 9, y + 7, y + 10, sb + 2, sb + 8, rng.choice([TV_BODY, CAR_C, CAR_A, UPHOL]))
        fr.box(bu0 + 4, bu0 + 6, y + 10, y + 11, sb + 3, sb + 7, CHROME)
    # ---- entrance door (corridor partition: v in [ROOM_D, ROOM_D+T_PART))
    du0 = U0 + 8
    fr.box(du0, du0 + 9, y, y + 21, ROOM_D, ROOM_D + T_PART, 0)
    fr.box(du0 - 1, du0 + 10, y + 21, y + 22, ROOM_D, ROOM_D + T_PART + 1, WOOD_DARK)
    fr.box(du0 - 1, du0, y, y + 21, ROOM_D + T_PART, ROOM_D + T_PART + 1, WOOD_DARK)
    fr.box(du0 + 9, du0 + 10, y, y + 21, ROOM_D + T_PART, ROOM_D + T_PART + 1, WOOD_DARK)
    fr.box(du0, du0 + 9, y - 1, y, ROOM_D, ROOM_D + T_PART, WOOD_DARK)          # threshold
    # real door leaf in the room-side layer of the partition, hinged on the wardrobe side, opens inward
    add_door(fr, du0, du0 + 9, y, y + 21, ROOM_D, ROOM_D + 1, wood_door,
             hinge=(du0, ROOM_D), open_dir=(0, -1), start_open=rng.random() < 0.25)
    fr.box(du0 + 11, du0 + 14, y + 15, y + 17, ROOM_D + T_PART, ROOM_D + T_PART + 1, BRASS)   # number plate
    fr.box(du0 - 3, du0 - 2, y + 11, y + 13, ROOM_D - 1, ROOM_D, SWITCH)         # light switch (inside)
    fr.box(du0 - 3, du0 - 2, y + 15, y + 17, ROOM_D - 1, ROOM_D, SWITCH)         # thermostat
    # corridor-side clutter: room service tray / do-not-disturb sign
    r = rng.random()
    if r < 0.15:
        fr.box(du0 + 1, du0 + 7, y, y + 1, ROOM_D + T_PART, ROOM_D + T_PART + 4, STEEL)
        fr.box(du0 + 2, du0 + 4, y + 1, y + 2, ROOM_D + T_PART + 1, ROOM_D + T_PART + 3, CERAMIC)
        fr.box(du0 + 5, du0 + 6, y + 1, y + 3, ROOM_D + T_PART + 1, ROOM_D + T_PART + 2, GLASS_DOOR)
    # ceiling: fixture, smoke detector, AC grille
    cu = (U0 + U1) // 2
    fr.box(cu - 2, cu + 2, y + FH - SLAB_T - 1, y + FH - SLAB_T, 18, 22, CEIL_LAMP if lit else CEIL)
    fr.box(cu - 3, cu + 3, y + FH - SLAB_T - 1, y + FH - SLAB_T, 17, 18, BRASS)
    fr.box(cu, cu + 1, y + FH - SLAB_T - 1, y + FH - SLAB_T, 30, 31, SWITCH)
    fr.box(U0 + 9, U0 + 17, y + FH - SLAB_T - 1, y + FH - SLAB_T, ROOM_D - 5, ROOM_D - 2, HVAC)
    if lit:
        fr.light(cu, y + FH - SLAB_T - 2, 20, (1.0, 0.82, 0.55), 2.2, 0.3)

def build_rooms():
    for name, b, fr, bw in room_frames():
        for k in range(FLOORS):
            y = fy(k)
            fr.box(0, T_PART, y - SLAB_T, y + FH - SLAB_T, 0, ROOM_D, ROOM_WALL)                     # party wall
            fr.box(0, bw, y - SLAB_T if k else G0, y + FH - SLAB_T, ROOM_D, ROOM_D + 1, ROOM_WALL)   # corridor wall
            fr.box(0, bw, y - SLAB_T if k else G0, y + FH - SLAB_T, ROOM_D + 1, ROOM_D + T_PART, COR_WALL)
        if b == (LONG_BAYS if name in "WE" else SHORT_BAYS) - 1:
            fr.box(bw, bw + T_PART, G0, ROOF_Y - SLAB_T, 0, ROOM_D, ROOM_WALL)
    for name, b, fr, bw in room_frames():
        for k in range(FLOORS):
            y = fy(k)
            if k == 0 and name == "S" and b in (1, 2):
                continue
            u0 = window_in_facade(fr, bw, y)
            state = rng.choice(STATES)
            wall = rng.choice([ROOM_WALL, ROOM_WALL, ROOM_WALL_B, ROOM_WALL_C])
            # paint this room's own wall faces with its wallpaper colour
            fr.paint(1, 2, y, y + FH - SLAB_T, 0, ROOM_D, wall, [ROOM_WALL])
            fr.paint(bw, bw + 1, y, y + FH - SLAB_T, 0, ROOM_D, wall, [ROOM_WALL])
            fr.paint(T_PART, bw, y, y + FH - SLAB_T, ROOM_D, ROOM_D + 1, wall, [ROOM_WALL])
            fr.paint(T_PART, bw, y, y + FH - SLAB_T, -1, 0, wall, [ATR_WALL])
            curtains(fr, u0, y, state)
            twin = bw >= 40 and rng.random() < 0.6
            blanket = rng.choice([BLANKET_A, BLANKET_A, BLANKET_B, BLANKET_C])
            carpet = rng.choice([CARP_A, CARP_A, CARP_B])
            ff = fr.mirrored(T_PART, bw) if rng.random() < 0.5 else fr
            furnish_room(ff, bw, k, state, twin, blanket, carpet)
            room_log.append((name, b, k, state))

# ============================================================================
# 5. Corridors (ring between the room partition and the exterior wall)
# ============================================================================
cor_frames = [
    ("W", Frame(bx0 + T_EXT + COR_W - 1, bz0 + T_EXT, 0, 1, -1, 0), BZ - 2 * T_EXT),
    ("E", Frame(bx1 - T_EXT - COR_W, bz1 - T_EXT - 1, 0, -1, 1, 0), BZ - 2 * T_EXT),
    ("S", Frame(bx1 - T_EXT - 1, bz0 + T_EXT + COR_W - 1, -1, 0, 0, -1), BX - 2 * T_EXT),
    ("N", Frame(bx0 + T_EXT, bz1 - T_EXT - COR_W, 1, 0, 0, 1), BX - 2 * T_EXT),
]
COR_PAINTABLE = [COR_WALL, ROOM_WALL, STAIR_WALL, EXT_WALL]

SEAMS_X = [ax0 + 2 * SHORT_BAY_W]                     # shape seams (see export)
SEAMS_Z = [az0 + 2 * LONG_BAY_W, az0 + 6 * LONG_BAY_W, AZ0 - 6]

def build_corridors():
    for name, fr, L in cor_frames:
        for k in range(FLOORS):
            y = fy(k)
            # carpet runner: red field, gold border, repeating medallions
            fr.box(0, L, y - 1, y, 0, COR_W, COR_CARP)
            fr.box(0, L, y - 1, y, 2, 3, COR_GOLD)
            fr.box(0, L, y - 1, y, COR_W - 3, COR_W - 2, COR_GOLD)
            for u in range(6, L, 12):
                for d in range(4):
                    fr.box(u + d, u + d + 1, y - 1, y, 9 - d, 9 + d, COR_GOLD)
                    fr.box(u + 7 - d, u + 8 - d, y - 1, y, 9 - d, 9 + d, COR_GOLD)
                fr.box(u + 3, u + 5, y - 1, y, 8, 10, COR_CARP2)
            # dropped ceiling + crown moulding + lamps + sprinklers
            fr.box(0, L, y + 24, y + 25, 0, COR_W, CEIL)
            for side in (-1, COR_W):
                fr.paint(0, L, y + 23, y + 24, side, side + 1, CEIL, COR_PAINTABLE)
            fr.box(0, L, y + 23, y + 24, 0, 1, CEIL); fr.box(0, L, y + 23, y + 24, COR_W - 1, COR_W, CEIL)
            for u in range(17, L - 5, 34):
                fr.box(u - 2, u + 2, y + 23, y + 24, 7, 11, CEIL_LAMP)
                fr.box(u - 3, u + 3, y + 23, y + 24, 6, 7, BRASS); fr.box(u - 3, u + 3, y + 23, y + 24, 11, 12, BRASS)
            for u in range(0, L, 17):
                fr.box(u, u + 1, y + 23, y + 24, 3, 4, CHROME)
            for u in range(51, L - 5, 68):          # aligned with a ceiling lamp
                fr.light(u, y + 21, 9, (1.0, 0.86, 0.62), 2.0, 0.25, "flicker" if rng.random() < 0.18 else "")
            # both walls: striped wallpaper above a wood wainscot with chair rail
            for side in (-1, COR_W):
                for u in range(0, L, 6):
                    fr.paint(u, u + 3, y + 10, y + 23, side, side + 1, COR_STRIPE, COR_PAINTABLE)
                fr.paint(0, L, y + 10, y + 23, side, side + 1, COR_WALL, [ROOM_WALL, EXT_WALL, STAIR_WALL])
                fr.paint(0, L, y + 1, y + 9, side, side + 1, WAINS, COR_PAINTABLE + [COR_STRIPE])
                for u in range(0, L, 12):
                    fr.paint(u, u + 1, y + 1, y + 9, side, side + 1, WAINS2, [WAINS])
                fr.paint(0, L, y + 9, y + 10, side, side + 1, CHAIR_RAIL, COR_PAINTABLE + [COR_STRIPE, WAINS])
                fr.paint(0, L, y, y + 1, side, side + 1, WOOD_DARK, COR_PAINTABLE + [COR_STRIPE, WAINS, WAINS2])
            # wall sconces on the exterior side (between the windows)
            for u in range(12, L - 6, 34):
                xa_, za_ = fr.pt(u, 0); xb_, zb_ = fr.pt(u + 1, 0)
                if any(min(xa_, xb_) < sx_ <= max(xa_, xb_) for sx_ in SEAMS_X) or \
                   any(min(za_, zb_) < sz_ <= max(za_, zb_) for sz_ in SEAMS_Z):
                    u += 3                                                         # keep it inside one shape
                xs_, zs_ = fr.pt(u, 0)
                if k == 0 and name in ("S", "N") and abs(xs_ - (ax0 + 2 * SHORT_BAY_W)) < 22:
                    continue                                                       # entrance / pool connector doorway
                fr.box(u, u + 2, y + 14, y + 16, COR_W - 2, COR_W, BRASS)         # bracket under the shade
                fr.box(u, u + 2, y + 16, y + 19, COR_W - 2, COR_W - 1, LAMPSHADE)
            # small exterior windows with stone lintel + sill
            for u in range(30, L - 20, 68):
                fr.box(u, u + 8, y + 10, y + 22, COR_W, COR_W + T_EXT, 0)
                fr.box(u, u + 8, y + 10, y + 22, COR_W + 2, COR_W + 3, GLASS_EXT)
                fr.box(u + 3, u + 5, y + 10, y + 22, COR_W + 2, COR_W + 3, FRAME)
                fr.box(u - 1, u + 9, y + 9, y + 10, COR_W - 1, COR_W + T_EXT + 1, LINTEL)
                fr.box(u - 1, u + 9, y + 22, y + 24, COR_W + 1, COR_W + T_EXT + 1, LINTEL)
            # fire extinguisher cabinet near each end
            for u in (24, L - 30):
                fr.box(u, u + 5, y + 8, y + 18, COR_W, COR_W + 1, 0)
                fr.box(u, u + 5, y + 8, y + 18, COR_W + 1, COR_W + 2, RED)
                fr.box(u + 1, u + 4, y + 9, y + 17, COR_W, COR_W + 1, GLASS_DOOR)
                fr.box(u + 2, u + 3, y + 9, y + 15, COR_W + 1, COR_W + 2, RED)

build_rooms()
build_corridors()

# ============================================================================
# 6. Ground floor lobby (south side, bays 1-2) + main entrance
# ============================================================================
lx0, lx1 = ax0 + SHORT_BAY_W, ax0 + 3 * SHORT_BAY_W
lz0, lz1 = az0 - T_FAC - ROOM_D, az0
y = G0
cx = (lx0 + lx1) // 2
box(lx0, lx1, y, y + FH - SLAB_T, lz0, lz1 - T_FAC, 0)
box(lx0, lx1, y, y + FH - SLAB_T, lz0, lz0 + 1, LOBBY_WALL)
for xx in range(lx0, lx1):    # herringbone-ish parquet
    for zz in range(lz0, lz1 - T_FAC):
        G[xx, y - 1, zz] = PARQUET if ((xx // 2 + zz // 6) % 2 == 0) == ((zz // 2 + xx // 6) % 2 == 0) else PARQUET2
box(lx0 + 4, lx1 - 4, y - 1, y, lz0 + 4, lz1 - 8, RUG_BRD)
box(lx0 + 6, lx1 - 6, y - 1, y, lz0 + 6, lz1 - 10, COR_CARP)
for xx in range(lx0 + 8, lx1 - 8, 8):
    box(xx, xx + 2, y - 1, y, lz0 + 8, lz1 - 12, COR_GOLD)
# wood panelled lower walls
paint(lx0, lx1, y, y + 10, lz0, lz0 + 1, WAINS)
paint(lx0, lx1, y + 10, y + 11, lz0, lz0 + 1, CHAIR_RAIL)
# columns
for px_ in (lx0 + 22, lx1 - 24):
    for pz_ in (lz0 + 6, lz1 - 12):
        box(px_, px_ + 4, y, y + FH - SLAB_T, pz_, pz_ + 4, PILLAR)
        box(px_ - 1, px_ + 5, y, y + 2, pz_ - 1, pz_ + 5, BASE_STONE)
        box(px_ - 1, px_ + 5, y + 24, y + 26, pz_ - 1, pz_ + 5, CORNICE)
# glass double doors to the atrium
box(cx - 14, cx + 14, y, y + 22, az0 - T_FAC, az0, FRAME)
box(cx - 13, cx + 13, y, y + 21, az0 - T_FAC, az0, 0)
add_door(WORLD, cx - 13, cx, y, y + 21, az0 - 3, az0 - 2, glass_door, hinge=(cx - 13, az0 - 2), open_dir=(0, 1))
add_door(WORLD, cx, cx + 13, y, y + 21, az0 - 3, az0 - 2, lambda a, b, c, A, B, C: glass_door(A - 1 - a, b, c, A, B, C),
         hinge=(cx + 13, az0 - 2), open_dir=(0, 1))
box(cx - 4, cx + 4, y + 23, y + 26, az0 - 5, az0 - 4, EXIT_SIGN)
# reception desk with key cubbies behind it
box(lx0 + 8, lx0 + 36, y, y + 11, lz0 + 14, lz0 + 20, WOOD_DARK)
for xx in range(lx0 + 9, lx0 + 36, 4):
    box(xx, xx + 2, y + 2, y + 9, lz0 + 19, lz0 + 20, WOOD_MED)
box(lx0 + 8, lx0 + 36, y + 11, y + 12, lz0 + 13, lz0 + 21, WOOD_LIGHT)
box(lx0 + 12, lx0 + 14, y + 12, y + 14, lz0 + 16, lz0 + 18, BRASS)          # bell
box(lx0 + 26, lx0 + 31, y + 12, y + 16, lz0 + 15, lz0 + 17, TV_BODY)       # monitor
box(lx0 + 27, lx0 + 30, y + 13, y + 15, lz0 + 17, lz0 + 18, TV_SCREEN)
box(lx0 + 8, lx0 + 36, y + 8, y + 22, lz0 + 1, lz0 + 3, WOOD_DARK)
for xx in range(lx0 + 9, lx0 + 35, 3):
    for yy in range(y + 9, y + 21, 3):
        box(xx, xx + 2, yy, yy + 2, lz0 + 2, lz0 + 3, 0)
        if rng.random() < 0.7:
            box(xx, xx + 1, yy, yy + 1, lz0 + 1, lz0 + 2, BRASS)              # keys
# sofas + coffee table + plants + chandelier
for sz, back in ((lz0 + 10, lz0 + 10), (lz0 + 28, lz0 + 34)):
    box(lx1 - 30, lx1 - 10, y, y + 5, sz, sz + 7, UPHOL)
    box(lx1 - 30, lx1 - 10, y + 5, y + 11, back, back + 1, UPHOL)
    box(lx1 - 31, lx1 - 30, y, y + 8, sz, sz + 7, UPHOL); box(lx1 - 10, lx1 - 9, y, y + 8, sz, sz + 7, UPHOL)
box(lx1 - 26, lx1 - 14, y + 3, y + 4, lz0 + 19, lz0 + 25, GLASS_DOOR)
box(lx1 - 26, lx1 - 14, y, y + 3, lz0 + 21, lz0 + 23, BRASS)
for (ppx, ppz) in [(lx0 + 4, lz1 - 12), (lx1 - 6, lz1 - 12), (lx1 - 6, lz0 + 6)]:   # corners, out of the walkway
    box(ppx - 3, ppx + 3, y, y + 8, ppz - 3, ppz + 3, PLANTER)
    box(ppx, ppx + 1, y + 8, y + 10, ppz, ppz + 1, TRUNK)
    leaf_blob(ppx, y + 15, ppz, 6, 21, LEAF, anchor=(ppx, y + 9, ppz), squash=0.8, keep=0.4)
box(lx0 + 2, lx1 - 2, y + 26, y + 27, lz0 + 2, lz1 - 6, CEIL)
ccx, ccz = cx + 12, lz0 + 24          # off the shape seam at cx so the whole chandelier is one piece
box(ccx, ccx + 1, y + 23, y + 27, ccz, ccz + 1, BRASS)      # short stem: chandelier sits high (2.2 m+)
for (ox_, oz_) in [(-6, 0), (6, 0), (0, -6), (0, 6), (-4, -4), (4, 4), (-4, 4), (4, -4)]:
    box(ccx + ox_, ccx + ox_ + 1, y + 22, y + 24, ccz + oz_, ccz + oz_ + 1, CEIL_LAMP)
    box(min(ccx, ccx + ox_), max(ccx, ccx + ox_) + 1, y + 24, y + 25, min(ccz, ccz + oz_), max(ccz, ccz + oz_) + 1, BRASS)
light(ccx + 0.5, y + 21, ccz + 0.5, (1.0, 0.85, 0.6), 3.5, 0.4)
for i in (0, 2):
    xx = lx0 + 14 + i * 26
    box(xx - 2, xx + 2, y + 26, y + 27, lz0 + 20, lz0 + 24, CEIL_LAMP)
    light(xx + 0.5, y + 24, lz0 + 22.5, (1.0, 0.85, 0.65), 2.0, 0.3)
# lobby <-> corridor doorway and main entrance through the exterior wall
box(cx - 14, cx + 14, y, y + 22, lz0 - T_PART, lz0 + 1, 0)
box(cx - 15, cx + 15, y + 22, y + 23, lz0 - T_PART, lz0 + 1, WOOD_DARK)
box(cx - 16, cx + 16, y, y + 25, bz0 - 1, bz0 + T_EXT, LINTEL)
box(cx - 15, cx + 15, y, y + 23, bz0 - 3, bz0 + T_EXT, 0)   # also cut the plinth / plinth cap in front of the door
add_door(WORLD, cx - 15, cx, y, y + 23, bz0 + 1, bz0 + 2, glass_door, hinge=(cx - 15, bz0 + 1), open_dir=(0, -1))
add_door(WORLD, cx, cx + 15, y, y + 23, bz0 + 1, bz0 + 2, lambda a, b, c, A, B, C: glass_door(A - 1 - a, b, c, A, B, C),
         hinge=(cx + 15, bz0 + 1), open_dir=(0, -1))
box(cx - 20, cx + 20, G0, G0 + 1, bz0 - 14, bz0, RUG_BRD)                    # door mat
box(cx - 8, cx + 8, G0, G0 + 1, bz0 - 12, bz0 - 2, COR_CARP)
# entrance canopy with brass posts, lamps and sign
box(cx - 30, cx + 30, y + 32, y + 35, bz0 - 24, bz0, DARK_METAL)
box(cx - 31, cx + 31, y + 35, y + 36, bz0 - 25, bz0, LINTEL)
box(cx - 28, cx + 28, y + 31, y + 32, bz0 - 22, bz0 - 2, CEIL)
for sx in (-28, 26):
    box(cx + sx, cx + sx + 2, G0, y + 32, bz0 - 22, bz0 - 20, BRASS)
    box(cx + sx - 1, cx + sx + 3, G0, G0 + 2, bz0 - 23, bz0 - 19, BASE_STONE)
for i in range(4):
    xx = cx - 21 + i * 14
    box(xx, xx + 2, y + 31, y + 32, bz0 - 13, bz0 - 11, CEIL_LAMP)
light(cx + 0.5, y + 29, bz0 - 12, (1.0, 0.85, 0.65), 4.0, 0.4)
# planters flanking the door
for sx in (-26, 22):
    box(cx + sx, cx + sx + 6, G0, G0 + 7, bz0 - 8, bz0 - 2, BASE_STONE)
    box(cx + sx + 1, cx + sx + 5, G0 + 6, G0 + 7, bz0 - 7, bz0 - 3, SOIL)
    leaf_blob(cx + sx + 3, G0 + 10, bz0 - 5, 4, 31, LEAF2, anchor=(cx + sx + 3, G0 + 7, bz0 - 5), squash=1.2, keep=0.3)

# ============================================================================
# 7. Corner blocks: SW & NE stairwells, NW & SE elevators + utility room
# ============================================================================
CB = T_FAC + ROOM_D
corner = {
    "SW": Frame(bx0 + T_EXT + COR_W + T_PART, bz0 + T_EXT + COR_W + T_PART, 1, 0, 0, 1),
    "NE": Frame(bx1 - T_EXT - COR_W - T_PART - 1, bz1 - T_EXT - COR_W - T_PART - 1, -1, 0, 0, -1),
    "NW": Frame(bx0 + T_EXT + COR_W + T_PART, bz1 - T_EXT - COR_W - T_PART - 1, 1, 0, 0, -1),
    "SE": Frame(bx1 - T_EXT - COR_W - T_PART - 1, bz0 + T_EXT + COR_W + T_PART, -1, 0, 0, 1),
}
for key, fr in corner.items():
    fr.box(-T_PART, CB, G0, ROOF_Y - SLAB_T, -T_PART, 0, STAIR_WALL)
    fr.box(-T_PART, 0, G0, ROOF_Y - SLAB_T, -T_PART, CB, STAIR_WALL)
    fr.box(CB - T_FAC, CB, G0, ROOF_Y - SLAB_T, 0, CB, STAIR_WALL)
    fr.box(0, CB, G0, ROOF_Y - SLAB_T, CB - T_FAC, CB, STAIR_WALL)

def stairwell(fr):
    for k in range(FLOORS + 1):
        y = fy(k)
        if k < FLOORS:
            fr.box(0, CB - T_FAC, y, y + FH - SLAB_T, 0, CB - T_FAC, 0)
            # two-tone walls + painted floor number
            fr.paint(-1, 0, y, y + 10, 0, CB - T_FAC, STAIR_WALL2, [STAIR_WALL])
            fr.paint(CB - T_FAC, CB - T_FAC + 1, y, y + 10, 0, CB - T_FAC, STAIR_WALL2, [STAIR_WALL])
            fr.paint(0, CB - T_FAC, y, y + 10, -1, 0, STAIR_WALL2, [STAIR_WALL])
            fr.paint(0, CB - T_FAC, y, y + 10, CB - T_FAC, CB - T_FAC + 1, STAIR_WALL2, [STAIR_WALL])
        if k > 0:
            fr.box(15, CB - T_FAC, y - SLAB_T, y, 0, CB - T_FAC, 0)
        fr.box(0, 15, y - 1, y, 0, CB - T_FAC, STAIR_CONC)
        fr.box(0, 15, y - 1, y, 0, 1, RED)           # safety line
        if k < FLOORS:
            fr.box(-T_PART, 0, y, y + 21, 26, 36, 0)
            fr.box(-T_PART - 1, -T_PART, y + 22, y + 25, 28, 34, EXIT_SIGN)
            fr.box(0, 1, y + 21, y + 22, 25, 37, DARK_METAL)
            add_door(fr, -1, 0, y, y + 21, 26, 36, lambda a, b, c, A, B, C: steel_door(c, b, a, C, B, A),
                     hinge=(0, 36), open_dir=(1, 0))
            fr.light(4, y + 24, 22, (1.0, 0.95, 0.85), 1.6, 0.2)
            fr.box(2, 6, y + 26, y + 27, 20, 24, CEIL_LAMP)
            # big painted floor number (simple 3x5 digit font scaled x2)
            digit = DIGITS[str(k + 1)]
            for r_, row in enumerate(digit):
                for c_, ch in enumerate(row):
                    if ch == "#":
                        fr.box(CB - T_FAC, CB - T_FAC + 1, y + 20 - r_ * 2, y + 22 - r_ * 2, 4 + c_ * 2, 6 + c_ * 2, RED)
    for k in range(FLOORS):
        y = fy(k)
        for s in range(8):
            p0 = 12 + s * 3
            fr.box(p0, p0 + 3, y + s * 2 - 2, y + s * 2 + 2, 2, 22, STAIR_CONC)
            fr.box(p0, p0 + 1, y + s * 2 + 1, y + s * 2 + 2, 2, 22, DARK_METAL)       # nosing
        fr.box(36, CB - T_FAC, y + 14, y + 16, 0, CB - T_FAC, STAIR_CONC)
        for s in range(7):
            p1 = 36 - s * 3
            top = y + 16 + (s + 1) * 2
            fr.box(p1 - 3, p1, top - 4, top, 24, 44, STAIR_CONC)
            fr.box(p1 - 3, p1 - 2, top - 1, top, 24, 44, DARK_METAL)
        # balustrade: posts + sloped rail on the stair well side
        for p in range(12, 37, 4):
            hA = y + int((p - 12) / 3) * 2 + 2
            fr.box(p, p + 1, hA, hA + 9, 21, 22, STEEL)
            hB = y + 30 - int((p - 15) / 3) * 2 if p >= 15 else y + 30
            fr.box(p, p + 1, hB, hB + 9, 24, 25, STEEL)
        for p in range(12, 36):
            fr.box(p, p + 1, y + int((p - 12) / 3) * 2 + 10, y + int((p - 12) / 3) * 2 + 13, 21, 22, STEEL)
        for p in range(15, 36):
            fr.box(p, p + 1, y + 30 - int((p - 15) / 3) * 2 + 8, y + 30 - int((p - 15) / 3) * 2 + 11, 24, 25, STEEL)
        # wall handrail
        for p in range(12, 36):
            fr.box(p, p + 1, y + int((p - 12) / 3) * 2 + 9, y + int((p - 12) / 3) * 2 + 12, 0, 1, WOOD_MED)
    y = ROOF_Y
    fr.box(-T_PART, CB, y, y + 28, -T_PART, CB, STAIR_WALL)
    fr.paint(-T_PART, CB, y, y + 28, -T_PART, CB, BRICK, [STAIR_WALL])
    fr.box(0, CB - T_FAC, y, y + 26, 0, CB - T_FAC, 0)
    fr.box(-T_PART - 1, CB + 1, y + 28, y + 30, -T_PART - 1, CB + 1, EXT_TRIM)
    fr.box(-T_PART, CB, y + 30, y + 31, -T_PART, CB, ROOF)
    fr.box(20, 30, y, y + 21, CB - T_FAC, CB, 0)
    fr.box(19, 31, y + 21, y + 23, CB - 1, CB + 1, LINTEL)
    fr.box(23, 27, y + 23, y + 25, CB, CB + 1, CEIL_LAMP)
    fr.light(10, y + 24, 10, (1.0, 0.95, 0.85), 1.6, 0.2)

DIGITS = {
    "1": [".#.", "##.", ".#.", ".#.", "###"], "2": ["##.", "..#", ".#.", "#..", "###"],
    "3": ["##.", "..#", ".#.", "..#", "##."], "4": ["#.#", "#.#", "###", "..#", "..#"],
    "5": ["###", "#..", "##.", "..#", "##."], "6": [".##", "#..", "###", "#.#", "###"],
}

CAR_P0, CAR_P1 = 1, 18          # car footprint inside a shaft (p), 1-voxel running clearance
CAR_H = 28                      # floor (2) + cabin (24) + roof (2)

def car_style(a, b, c, A, B, C):
    """elevator cab, local a = depth (0 = door side), b = height, c = width."""
    floor_top, roof = 2, B - 2
    inside_a = 1 <= a <= A - 2
    inside_c = 1 <= c <= C - 2
    if b < floor_top:                                       # floor: steel pan + carpet inlay
        if b == 1 and inside_a and inside_c:
            return COR_GOLD if (a in (1, A - 2) or c in (1, C - 2)) else COR_CARP
        return DARK_METAL
    if b >= roof:                                           # roof with hoist beam
        if b == B - 1 and 7 <= c <= C - 8:
            return ELEV_RAIL
        return DARK_METAL
    if b == roof - 1:                                       # ceiling: light panel in a brass frame
        if 5 <= a <= A - 5 and 5 <= c <= C - 6:
            return CEIL_LAMP if (6 <= a <= A - 6 and 6 <= c <= C - 7) else BRASS
        return CEIL if (inside_a and inside_c) else WAINS2
    if a == A - 1:                                          # back wall: big mirror over wood
        if 3 <= c <= C - 4 and 9 <= b <= 22:
            return MIRROR
        return WAINS if b != 8 else CHAIR_RAIL
    if c in (0, C - 1):                                     # side walls: raised wood panels
        if b == 8:
            return CHAIR_RAIL
        if (b - 3) % 7 in (0,) or a % 5 == 0:
            return WAINS2
        return WAINS
    if a == 0:                                              # front wall around the open doorway
        if 3 <= c <= C - 4 and b < 24:
            return 0
        if c in (2, C - 3) or b == 24:
            return BRASS
        return ELEV_DOOR
    if b == 11 and c in (1, C - 2) and 2 <= a <= A - 3:     # brass handrails (inside)
        return BRASS
    if a == 1 and c == C - 2 and 7 <= b <= 20:              # button panel next to the door
        return CHROME
    if a == 1 and b == 23 and 5 <= c <= C - 6:              # floor indicator strip
        return TV_BODY
    return 0

def elevators(fr, key):
    for k in range(FLOORS):
        y = fy(k)
        fr.box(0, CB - T_FAC, y, y + FH - SLAB_T, 0, CB - T_FAC, 0)
        fr.box(0, CB - T_FAC, y - 1, y, 0, CB - T_FAC, TILE_DARK)
    fr.box(0, 22, G0, ROOF_Y + 12, 0, CB - T_FAC, SLAB)
    for qi, q0 in enumerate((2, 24)):
        shaft = f"{key}{qi}"
        fr.box(0, 20, 1, ROOF_Y, q0, q0 + 18, 0)                                  # hollow shaft + pit
        # guide rails + brackets on the back wall (behind the car, not touching it)
        for qq in (q0 + 3, q0 + 14):
            fr.box(19, 20, 1, ROOF_Y, qq, qq + 1, ELEV_RAIL)
            for yy in range(G0, ROOF_Y, 15):
                fr.box(19, 20, yy, yy + 1, qq - 1, qq + 2, ELEV_RAIL)
        for qq in (q0 + 2, q0 + 15):                                            # pit buffers (outside the car footprint)
            fr.box(19, 20, 1, 3, qq, qq + 1, RED)
        # counterweight hint + hoist sheave at the top
        fr.box(6, 14, ROOF_Y - 3, ROOF_Y - 1, q0 + 7, q0 + 11, DARK_METAL)
        fr.box(9, 11, ROOF_Y - 1, ROOF_Y, q0 + 8, q0 + 10, ELEV_RAIL)
        start = rng.randrange(FLOORS)
        yb = fy(start) - 2
        arr, gmin = frame_shape(fr, CAR_P0, CAR_P1, yb, yb + CAR_H, q0 + 1, q0 + 17, car_style)
        # car buttons: one per floor, stacked on the chrome panel (separate shapes)
        buttons = []
        for f in range(FLOORS):
            by = yb + 2 + 8 + f * 2
            barr, bmin = frame_shape(fr, CAR_P0 + 2, CAR_P0 + 3, by, by + 1, q0 + 1 + 14, q0 + 1 + 15,
                                     lambda *a_: CEIL_LAMP)
            buttons.append((barr, bmin, f))
        cxl, czl = cont(fr, (CAR_P0 + CAR_P1) / 2, q0 + 9)
        ELEVATORS.append(dict(arr=arr, gmin=gmin, shaft=shaft, floor=start, buttons=buttons,
                              light=(cxl, yb + CAR_H - 5, czl)))
        for k in range(FLOORS):
            y = fy(k)
            fr.box(-T_PART, 0, y, y + 22, q0 + 4, q0 + 14, 0)
            # support points inside the wall (left jamb, right of the pocket, above the header):
            # main.lua drops the door when these are blown away
            sup = []
            for (P, Q, Y) in ((-1, q0 + 2, y + 11), (-1, q0 + 19, y + 11), (-1, q0 + 9, y + 25)):
                wx_, wz_ = cont(fr, P + 0.5, Q + 0.5)
                sup.append(f"{wx_ * 0.1 - W * 0.05:.3f},{(Y + 0.5) * 0.1:.3f},{wz_ * 0.1 - D * 0.05:.3f}")
            add_door(fr, -T_PART, -T_PART + 1, y, y + 22, q0 + 4, q0 + 14,
                     lambda a, b, c, A, B, C: elev_door(c, b, a, C, B, A), slide=(0, 10),
                     tag=f"elevdoor shaft={shaft} floor={k} s1={sup[0]} s2={sup[1]} s3={sup[2]}")
            # brass portal, lantern and call button panel
            fr.box(-T_PART - 1, -T_PART, y, y + 23, q0 + 3, q0 + 4, BRASS)
            fr.box(-T_PART - 1, -T_PART, y, y + 23, q0 + 14, q0 + 15, BRASS)
            fr.box(-T_PART - 1, -T_PART, y + 22, y + 23, q0 + 3, q0 + 15, BRASS)
            fr.box(-T_PART - 1, -T_PART, y + 23, y + 26, q0 + 6, q0 + 12, DARK_METAL)
            for f in range(FLOORS):                                              # floor dial dots
                fr.box(-T_PART - 2, -T_PART - 1, y + 24, y + 25, q0 + 6 + f, q0 + 7 + f, CEIL_LAMP if f == k else BRASS)
            fr.box(-T_PART - 1, -T_PART, y + 9, y + 15, q0 + 15, q0 + 17, BRASS)
            barr, bmin = frame_shape(fr, -T_PART - 2, -T_PART - 1, y + 11, y + 13, q0 + 15, q0 + 16,
                                     lambda *a_: CEIL_LAMP)
            CALLS.append((barr, bmin, shaft, k))
    fr.box(-T_PART, 22, ROOF_Y + 10, ROOF_Y + 14, -T_PART, CB - T_FAC, SLAB)
    for k in range(FLOORS):
        y = fy(k)
        # utility / ice machine room
        fr.box(26, 35, y, y + 21, -T_PART, 0, 0)
        fr.box(28, 44, y, y + 18, 34, 42, RADIATOR)
        fr.box(29, 33, y + 12, y + 15, 33, 34, TV_SCREEN)
        fr.box(35, 41, y + 2, y + 9, 33, 34, DARK_METAL)
        fr.box(36, 43, y, y + 22, 2, 8, STEEL)
        for sy in range(y + 5, y + 22, 6):
            fr.box(36, 43, sy, sy + 1, 2, 8, WOOD_LIGHT)
            fr.box(37, 42, sy + 1, sy + 3, 3, 7, TOWEL)
        fr.box(24, 32, y, y + 12, 4, 14, STEEL)                                 # housekeeping cart
        fr.box(25, 31, y + 2, y + 11, 5, 13, 0)
        fr.box(25, 31, y + 4, y + 5, 5, 13, STEEL); fr.box(25, 31, y + 8, y + 9, 5, 13, STEEL)
        fr.box(26, 30, y + 5, y + 7, 6, 12, TOWEL)
        fr.box(24, 32, y + 12, y + 13, 4, 14, STEEL)
        fr.box(30, 34, y + 26, y + 27, 18, 22, CEIL_LAMP)
        fr.light(32, y + 24, 20, (0.85, 0.95, 1.0), 1.2, 0.2)
    y = ROOF_Y
    fr.box(-T_PART, 24, y, y + 14, -T_PART, CB - T_FAC + 2, BRICK)              # machine room
    fr.box(-T_PART - 1, 25, y + 14, y + 16, -T_PART - 1, CB - T_FAC + 3, EXT_TRIM)
    fr.box(4, 14, y, y + 18, CB - T_FAC + 2, CB - T_FAC + 3, DARK_METAL)

stairwell(corner["SW"]); stairwell(corner["NE"])
elevators(corner["NW"], "NW"); elevators(corner["SE"], "SE")

# ============================================================================
# 8. Roof: HVAC, ducts, vents, rooftop sign
# ============================================================================
for i in range(5):
    hx = bx0 + 20 + i * 60
    for hz in (bz0 + 14, bz1 - 34):
        box(hx, hx + 22, ROOF_Y, ROOF_Y + 12, hz, hz + 18, HVAC)
        box(hx - 1, hx + 23, ROOF_Y, ROOF_Y + 2, hz - 1, hz + 19, DARK_METAL)
        box(hx + 3, hx + 19, ROOF_Y + 12, ROOF_Y + 13, hz + 3, hz + 15, DARK_METAL)
        for gx in range(hx + 2, hx + 21, 3):
            box(gx, gx + 1, ROOF_Y + 2, ROOF_Y + 10, hz - 1, hz, DARK_METAL)
        # fan on top
        cxf, czf = hx + 11, hz + 9
        for a in range(-5, 6):
            box(cxf + a, cxf + a + 1, ROOF_Y + 13, ROOF_Y + 14, czf - 5 + abs(a) // 2, czf + 5 - abs(a) // 2, CABLE)
box(ax0 - 24, ax0 - T_FAC, ROOF_Y + 2, ROOF_Y + 8, bz0 + 30, bz0 + 36, HVAC)
box(ax1 + T_FAC, ax1 + 24, ROOF_Y + 2, ROOF_Y + 8, bz1 - 36, bz1 - 30, HVAC)
for (vx, vz) in [(bx0 + 30, bz0 + 70), (bx1 - 30, bz0 + 120), (bx0 + 30, bz1 - 120), (bx1 - 30, bz1 - 80)]:
    box(vx, vx + 4, ROOF_Y, ROOF_Y + 8, vz, vz + 4, STEEL)
    box(vx - 1, vx + 5, ROOF_Y + 8, ROOF_Y + 9, vz - 1, vz + 5, STEEL)
# rooftop sign "HOTEL" on the south edge (5x7 font, x2)
FONT = {
    "H": ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "O": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "T": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    "E": ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
    "L": ["#....", "#....", "#....", "#....", "#....", "#....", "#####"],
}
word = "HOTEL"
sx0 = (bx0 + bx1) // 2 - (len(word) * 12) // 2
sz_ = bz0 + 8
box(sx0 - 4, sx0 + len(word) * 12, ROOF_Y, ROOF_Y + 22, sz_ + 2, sz_ + 3, DARK_METAL)   # backing panel holds the letters
for i in range(sx0 - 2, sx0 + len(word) * 12, 10):
    box(i, i + 1, ROOF_Y, ROOF_Y + 22, sz_ + 3, sz_ + 4, DARK_METAL)
for li, ch in enumerate(word):
    for r_, row in enumerate(FONT[ch]):
        for c_, cc in enumerate(row):
            if cc == "#":
                xx = sx0 + (len(word) - 1 - li) * 12 + (4 - c_) * 2   # mirrored: read from the south
                yy = ROOF_Y + 6 + (6 - r_) * 2
                lamp = STREET_LMP if not (li == 3 and r_ in (2, 3)) else 0   # one flickering-dead letter part
                box(xx, xx + 2, yy, yy + 2, sz_, sz_ + 2, lamp if lamp else DARK_METAL)
light((bx0 + bx1) / 2, ROOF_Y + 14, sz_ - 4, (1.0, 0.75, 0.45), 5.0, 0.5)

# street lamps
for (sx, sz) in [(bx0 - 14, bz0 - 14), (bx1 + 12, bz0 - 14), (bx0 - 14, bz1 + 12), (bx1 + 12, bz1 + 12),
                 (bx0 - 14, (bz0 + bz1) // 2), (bx1 + 12, (bz0 + bz1) // 2)]:
    box(sx - 1, sx + 3, G0, G0 + 3, sz - 1, sz + 3, DARK_METAL)
    box(sx, sx + 2, G0, G0 + 50, sz, sz + 2, DARK_METAL)
    box(sx - 2, sx + 4, G0 + 50, G0 + 52, sz - 2, sz + 4, DARK_METAL)
    box(sx - 1, sx + 3, G0 + 49, G0 + 50, sz - 1, sz + 3, STREET_LMP)
    light(sx + 1, G0 + 48.5, sz - 0.5, (1.0, 0.75, 0.45), 6.0, 0.3)
# dumpster + fire hydrant by the north-east
box(bx1 + 8, bx1 + 22, G0 + 1, G0 + 12, bz1 - 40, bz1 - 22, DUMPSTER)
box(bx1 + 7, bx1 + 23, G0 + 12, G0 + 13, bz1 - 41, bz1 - 21, DARK_METAL)
box(bx1 + 9, bx1 + 11, G0, G0 + 1, bz1 - 39, bz1 - 37, TIRE); box(bx1 + 19, bx1 + 21, G0, G0 + 1, bz1 - 25, bz1 - 23, TIRE)
box(bx0 - 8, bx0 - 5, G0 + 1, G0 + 8, bz0 + 20, bz0 + 23, RED)
box(bx0 - 9, bx0 - 4, G0 + 5, G0 + 6, bz0 + 21, bz0 + 22, RED)
# parked cars (dynamic props)
CAR_Z = bz0 - SW - 9 - 44
PROPS.append(("car_a", bx0 + 5, G0, CAR_Z, 0))
PROPS.append(("car_b", bx0 + 65, G0, CAR_Z, 0))
PROPS.append(("car_c", bx1 - 55, G0, CAR_Z, 0))
PROPS.append(("car_b", bx1 + 5, G0, CAR_Z, 0))

# ============================================================================
# 8b. Pool annex ("poolrooms"): glazed connector from the ground-floor north
#     corridor, tiled hall with a real water pool, spa, loungers, lifeguard chair
# ============================================================================
cxN = (ax0 + ax1) // 2
A_X0, A_X1 = cxN - 100, cxN + 100            # 20 m wide
DY = G0 + 20                                  # pool deck level (2 m up, the basin sits below it)
HALL_H = 60
POOLS = []                                    # water polygons: (surface_y_grid, depth_grid, [(x, z), ...])

def tile_face(x0, x1, y0, y1, z0, z1, base=WHITE_TILE, alt=WHITE_TILE2, grout=GROUT_TILE, size=6, only=None):
    """paint existing voxels in a box as square tiles with grout lines (works on any face orientation)."""
    xa, xb = sorted((x0, x1)); ya, yb = sorted((y0, y1)); za, zb = sorted((z0, z1))
    sub = G[xa:xb, ya:yb, za:zb]
    X, Y, Z = np.meshgrid(np.arange(xa, xb), np.arange(ya, yb), np.arange(za, zb), indexing="ij")
    mask = sub > 0 if only is None else np.isin(sub, only)
    grout_m = ((X % size == 0) & (xb - xa > 1)) | ((Y % size == 0) & (yb - ya > 1)) | ((Z % size == 0) & (zb - za > 1))
    t = hash3(X // size, Y // size, Z // size, 77)
    col = np.where(grout_m, grout, np.where(t < 0.8, base, alt)).astype(np.uint8)
    sub[mask] = col[mask]

# --- site: clear a strip through the north lawn and build the connector -----------------------
CW = 14                                        # half width of the connector (outer)
box(cxN - CW - 2, cxN + CW + 2, G0, G0 + 60, bz1, AZ0 + T_EXT, 0)        # outside the hotel wall only
box(cxN - CW, cxN + CW, 1, G0, bz1, AZ0, SLAB)
# door through the hotel's north exterior wall (ground floor corridor)
box(cxN - 12, cxN + 12, G0, G0 + 22, bz1 - T_EXT - 1, bz1 + 1, 0)
box(cxN - 13, cxN + 13, G0 + 22, G0 + 24, bz1 - T_EXT - 1, bz1, LINTEL)
# stairs: 10 risers of 2 voxels, treads 3 voxels -> +2.0 m to the pool deck
for s in range(10):
    zs = bz1 + 6 + s * 3
    box(cxN - CW + 2, cxN + CW - 2, G0, G0 + 2 * (s + 1), zs, AZ0, STAIR_CONC)
    box(cxN - CW + 2, cxN + CW - 2, G0 + 2 * (s + 1) - 1, G0 + 2 * (s + 1), zs, zs + 1, DARK_METAL)   # nosing
box(cxN - CW + 2, cxN + CW - 2, G0 - 1, G0, bz1, bz1 + 6, WHITE_TILE)
tile_face(cxN - CW + 2, cxN + CW - 2, DY - 1, DY, bz1 + 36, AZ0)
# glazed side walls: mullions every 8, glass between, solid base following the stairs
for z in range(bz1, AZ0):
    s_top = G0 + min(10, max(0, (z - (bz1 + 6)) // 3 + 1)) * 2
    for xw in (cxN - CW, cxN + CW - 2):
        box(xw, xw + 2, G0, s_top + 3, z, z + 1, EXT_WALL)
        c = FRAME if (z - bz1) % 8 == 0 else GLASS_EXT
        box(xw, xw + 2, s_top + 3, DY + 26, z, z + 1, FRAME if c == FRAME else 0)
        if c != FRAME:
            box(xw + 1 if xw < cxN else xw, xw + 2 if xw < cxN else xw + 1, s_top + 3, DY + 26, z, z + 1, GLASS_EXT)
    # handrails along the stairs
    box(cxN - CW + 2, cxN - CW + 3, s_top + 9, s_top + 10, z, z + 1, CHROME)
    box(cxN + CW - 3, cxN + CW - 2, s_top + 9, s_top + 10, z, z + 1, CHROME)
box(cxN - CW, cxN + CW, DY + 26, DY + 28, bz1, AZ0 + T_EXT, ROOF)
box(cxN - CW + 2, cxN + CW - 2, DY + 25, DY + 26, bz1, AZ0, CEIL)
for z in range(bz1 + 8, AZ0, 12):
    box(cxN - 3, cxN + 3, DY + 25, DY + 26, z, z + 3, CEIL_LAMP)
light(cxN, DY + 22, bz1 + 14, (0.9, 0.95, 1.0), 2.0, 0.3)
light(cxN, DY + 22, bz1 + 32, (0.9, 0.95, 1.0), 2.0, 0.3)

# --- hall shell ---------------------------------------------------------------------------------
box(A_X0, A_X1, 1, DY, AZ0, AZ1, SLAB)                                  # podium / basin structure
box(A_X0, A_X1, G0, DY + HALL_H + 4, AZ0, AZ1, EXT_WALL)                # walls + roof block
box(A_X0 + T_EXT, A_X1 - T_EXT, DY, DY + HALL_H, AZ0 + T_EXT, AZ1 - T_EXT, 0)
box(A_X0 - 1, A_X1 + 1, G0, DY, AZ0 - 1, AZ1 + 1, BASE_STONE)          # stone podium skin (outside only)
box(A_X0, A_X1, G0, DY, AZ0, AZ1, SLAB)
box(A_X0 - 2, A_X1 + 2, DY + HALL_H + 4, DY + HALL_H + 6, AZ0 - 2, AZ1 + 2, LINTEL)   # roof coping
box(A_X0, A_X1, DY + HALL_H + 3, DY + HALL_H + 4, AZ0, AZ1, ROOF)
# connector opening into the hall
box(cxN - 12, cxN + 12, DY, DY + 24, AZ0, AZ0 + T_EXT, 0)
# interior tiling: walls (white with a blue band), floor, ceiling
ix0, ix1, iz0, iz1 = A_X0 + T_EXT, A_X1 - T_EXT, AZ0 + T_EXT, AZ1 - T_EXT
for (x0, x1, z0, z1) in [(ix0 - 1, ix0, iz0, iz1), (ix1, ix1 + 1, iz0, iz1), (ix0, ix1, iz0 - 1, iz0), (ix0, ix1, iz1, iz1 + 1)]:
    tile_face(x0, x1, DY, DY + HALL_H, z0, z1)
    tile_face(x0, x1, DY + 12, DY + 18, z0, z1, POOL_TILE, POOL_TILE2, POOL_LINE, size=3)
    tile_face(x0, x1, DY, DY + 2, z0, z1, POOL_LINE, POOL_LINE, POOL_LINE)
tile_face(ix0, ix1, DY - 1, DY, iz0, iz1)
tile_face(ix0, ix1, DY + HALL_H, DY + HALL_H + 1, iz0, iz1, WHITE_TILE, WHITE_TILE, GROUT_TILE, size=12)
# ceiling light boxes (the bright, shadowless poolrooms look)
for x in range(ix0 + 16, ix1 - 10, 32):
    for z in range(iz0 + 16, iz1 - 10, 32):
        box(x, x + 12, DY + HALL_H - 1, DY + HALL_H, z, z + 12, CEIL_LAMP)
        box(x - 1, x + 13, DY + HALL_H - 1, DY + HALL_H, z - 1, z, CHROME)
        box(x - 1, x + 13, DY + HALL_H - 1, DY + HALL_H, z + 12, z + 13, CHROME)
        light(x + 6, DY + HALL_H - 3, z + 6, (0.92, 0.97, 1.0), 2.4, 0.5)
# clerestory windows on the long walls
for z in range(iz0 + 10, iz1 - 14, 24):
    for (xw0, xw1) in ((A_X0, A_X0 + T_EXT), (A_X1 - T_EXT, A_X1)):
        box(xw0, xw1, DY + 40, DY + 54, z, z + 14, FRAME)
        box(xw0, xw1, DY + 41, DY + 53, z + 1, z + 13, 0)
        box(xw0 + 1, xw0 + 2, DY + 41, DY + 53, z + 1, z + 13, GLASS_EXT)
        box(xw0 + 1, xw0 + 2, DY + 41, DY + 53, z + 7, z + 8, FRAME)

# --- main pool ------------------------------------------------------------------------------------
px0, px1 = cxN - 60, cxN + 60                 # 12 m
pz0, pz1 = iz0 + 56, iz0 + 126                # 7 m
SHALLOW, DEEP = 9, 16
box(px0, px1, DY - DEEP - 1, DY, pz0, pz1, 0)
box(px0, px1, DY - DEEP - 1, DY - DEEP, pz0, pz1, POOL_TILE)            # floor (deep end)
for z in range(pz0, pz1):                                                # shallow end + slope
    t_ = (z - pz0) / (pz1 - pz0)
    depth = SHALLOW if t_ < 0.35 else (DEEP if t_ > 0.6 else int(SHALLOW + (DEEP - SHALLOW) * (t_ - 0.35) / 0.25))
    box(px0, px1, DY - DEEP - 1, DY - depth, z, z + 1, SLAB)
    box(px0, px1, DY - depth - 1, DY - depth, z, z + 1, POOL_TILE)
# tile the basin (walls + floor) and add lane lines
tile_face(px0 - 1, px1 + 1, DY - DEEP - 1, DY, pz0 - 1, pz1 + 1, POOL_TILE, POOL_TILE2, GROUT_TILE, size=4,
          only=[SLAB, POOL_TILE, WHITE_TILE, WHITE_TILE2, GROUT_TILE])
for lane in range(1, 5):
    lx = px0 + lane * 24
    for z in range(pz0 + 6, pz1 - 6):
        t_ = (z - pz0) / (pz1 - pz0)
        depth = SHALLOW if t_ < 0.35 else (DEEP if t_ > 0.6 else int(SHALLOW + (DEEP - SHALLOW) * (t_ - 0.35) / 0.25))
        box(lx - 1, lx + 1, DY - depth - 1, DY - depth, z, z + 1, POOL_LINE)
    box(lx - 3, lx + 3, DY - DEEP - 1, DY - DEEP, pz1 - 8, pz1 - 6, POOL_LINE)        # T at the deep end
    box(lx - 1, lx + 1, DY - 8, DY - 3, pz1, pz1 + 1, POOL_LINE)                       # wall target
    box(lx - 3, lx + 3, DY - 6, DY - 5, pz1, pz1 + 1, POOL_LINE)
# coping + overflow grate around the pool
box(px0 - 4, px1 + 4, DY - 1, DY, pz0 - 4, pz1 + 4, COPING)
box(px0, px1, DY - 1, DY, pz0, pz1, 0)
for (x0, x1, z0, z1) in [(px0 - 3, px1 + 3, pz0 - 3, pz0 - 2), (px0 - 3, px1 + 3, pz1 + 2, pz1 + 3),
                         (px0 - 3, px0 - 2, pz0 - 3, pz1 + 3), (px1 + 2, px1 + 3, pz0 - 3, pz1 + 3)]:
    box(x0, x1, DY - 1, DY, z0, z1, DARK_METAL)
# underwater lights (emissive tiles + real lights) along the long walls
for z in range(pz0 + 10, pz1 - 4, 18):
    for xw in (px0 - 1, px1):
        box(xw, xw + 1, DY - 7, DY - 4, z, z + 3, POOL_LAMP)
        light(xw + (1.5 if xw < cxN else -0.5), DY - 5.5, z + 1.5, (0.45, 0.85, 1.0), 1.6, 0.2)
# ladders: two chrome rails + rungs at the four corners
for (lx, lz, dz) in [(px0 + 8, pz0, 1), (px1 - 12, pz0, 1), (px0 + 8, pz1 - 1, -1), (px1 - 12, pz1 - 1, -1)]:
    for rx in (lx, lx + 4):
        box(rx, rx + 1, DY - 12, DY + 9, lz, lz + 1, CHROME)                         # against the pool wall
        box(rx, rx + 1, DY + 8, DY + 9, min(lz - dz * 3, lz + dz), max(lz - dz * 3, lz + dz) + 1, CHROME)
        box(rx, rx + 1, DY - 1, DY + 9, lz - dz * 3, lz - dz * 3 + 1, CHROME)
    for ry in range(DY - 11, DY, 3):
        box(lx, lx + 5, ry, ry + 1, lz + dz, lz + dz + 1, CHROME)
# starting blocks at the deep end
for lane in range(5):
    sx_ = px0 + 6 + lane * 24
    box(sx_, sx_ + 12, DY, DY + 7, pz1 + 4, pz1 + 12, LOUNGER)
    box(sx_, sx_ + 12, DY + 7, DY + 8, pz1 + 3, pz1 + 12, POOL_TILE)
    box(sx_ + 5, sx_ + 7, DY + 3, DY + 6, pz1 + 3, pz1 + 4, POOL_LINE)        # lane number plate
POOLS.append((DY - 2, DEEP - 2, [(px0, pz0), (px1, pz0), (px1, pz1), (px0, pz1)]))

# --- spa (round hot tub with raised rim) near the entrance --------------------------------------
scx, scz, sr = cxN + 66, iz0 + 26, 13
X, Z = np.meshgrid(np.arange(scx - sr - 4, scx + sr + 4), np.arange(scz - sr - 4, scz + sr + 4), indexing="ij")
rr = np.sqrt((X - scx + 0.5) ** 2 + (Z - scz + 0.5) ** 2)
rim = (rr <= sr + 3) & (rr > sr)
inner = rr <= sr
G[X[rim], DY:DY + 4, Z[rim]] = COPING
for yy in range(DY - 6, DY + 4):
    G[X[inner], yy, Z[inner]] = 0
G[X[inner], DY - 7, Z[inner]] = POOL_TILE2
seat = inner & (rr > sr - 4)
G[X[seat], DY - 3, Z[seat]] = POOL_TILE
for a in range(0, 360, 45):
    gx_ = int(round(scx - 0.5 + (sr + 1.0) * np.cos(np.radians(a)))); gz_ = int(round(scz - 0.5 + (sr + 1.0) * np.sin(np.radians(a))))
    G[gx_, DY - 5, gz_] = POOL_LAMP
light(scx, DY - 2, scz, (0.5, 0.9, 1.0), 1.4, 0.3)
POOLS.append((DY + 2, 8, [(scx + sr * np.cos(np.radians(a)), scz + sr * np.sin(np.radians(a))) for a in range(0, 360, 30)]))

# --- deck furniture --------------------------------------------------------------------------------
def lounger(x, z, back=True):
    box(x, x + 7, DY + 3, DY + 4, z, z + 18, LOUNGER)
    for k in range(z + 1, z + 18, 2):
        box(x, x + 7, DY + 4, DY + 5, k, k + 1, LOUNGER)
    for (lx, lz) in ((x, z + 1), (x + 6, z + 1), (x, z + 16), (x + 6, z + 16)):
        box(lx, lx + 1, DY, DY + 3, lz, lz + 1, CHROME)
    if back:
        for i in range(6):
            box(x, x + 7, DY + 5 + i, DY + 6 + i, z + 16 - i, z + 18 - i, LOUNGER)
    if rng.random() < 0.5:
        box(x + 1, x + 6, DY + 5, DY + 6, z + 2, z + 12, rng.choice([TOWEL, ART1, BLANKET_B]))
for i in range(8):
    lounger(px0 + 4 + i * 14, pz1 + 22)
for i in range(4):
    lounger(px0 - 26, pz0 + 6 + i * 20, back=False)
# lifeguard chair (east side, mid pool)
lgx, lgz = px1 + 12, (pz0 + pz1) // 2
for (lx, lz) in ((lgx, lgz - 4), (lgx + 6, lgz - 4), (lgx, lgz + 4), (lgx + 6, lgz + 4)):
    box(lx, lx + 1, DY, DY + 22, lz, lz + 1, LOUNGER)
for ry in range(DY + 3, DY + 21, 4):
    box(lgx, lgx + 7, ry, ry + 1, lgz + 4, lgz + 5, LOUNGER)
box(lgx - 1, lgx + 8, DY + 22, DY + 23, lgz - 5, lgz + 6, LOUNGER)
box(lgx + 6, lgx + 8, DY + 23, DY + 32, lgz - 5, lgz + 6, LOUNGER)
box(lgx + 3, lgx + 4, DY + 23, DY + 40, lgz, lgz + 1, CHROME)                 # umbrella pole
box(lgx - 4, lgx + 11, DY + 40, DY + 41, lgz - 7, lgz + 8, RED)
box(lgx - 2, lgx + 9, DY + 41, DY + 42, lgz - 5, lgz + 6, CERAMIC)
box(lgx - 1, lgx, DY + 8, DY + 20, lgz - 4, lgz + 2, RED)                     # rescue tube (hangs on the leg)
# wall clock, changing-room doors (to nowhere), signs, drinking fountain, plants
ckx, cky = cxN + 40, DY + 34
for dx in range(-5, 6):
    for dy in range(-5, 6):
        r_ = (dx * dx + dy * dy) ** 0.5
        if r_ <= 5:
            box(ckx + dx, ckx + dx + 1, cky + dy, cky + dy + 1, iz1, iz1 + 1, TV_BODY if r_ > 4.2 else CERAMIC)
box(ckx, ckx + 1, cky, cky + 4, iz1 - 1, iz1, TV_BODY); box(ckx, ckx + 3, cky, cky + 1, iz1 - 1, iz1, TV_BODY)
for i, dxs in enumerate((-70, -50)):
    dx_ = cxN + dxs
    box(dx_ - 1, dx_ + 11, DY, DY + 23, iz0 - 1, iz0, FRAME)
    box(dx_, dx_ + 10, DY, DY + 22, iz0 - 1, iz0, WOOD_DOOR)
    box(dx_ + 8, dx_ + 9, DY + 10, DY + 12, iz0, iz0 + 1, BRASS)
    box(dx_ + 3, dx_ + 7, DY + 25, DY + 29, iz0 - 1, iz0, ART1 if i == 0 else BLANKET_B)    # pictogram plate
box(ix0, ix0 + 4, DY, DY + 10, iz0 + 40, iz0 + 46, CHROME)                         # drinking fountain
box(ix0, ix0 + 5, DY + 10, DY + 11, iz0 + 39, iz0 + 47, CHROME)
for (sx_, sz_) in ((px0 - 6, pz0 - 12), (px1 - 4, pz0 - 12)):                      # NO DIVING signs (red/white)
    box(sx_, sx_ + 10, DY, DY + 1, sz_, sz_ + 6, RED)
for (ppx, ppz) in ((ix0 + 8, iz1 - 10), (ix1 - 10, iz1 - 10), (ix0 + 8, iz0 + 10)):
    box(ppx - 3, ppx + 3, DY, DY + 8, ppz - 3, ppz + 3, CERAMIC)
    box(ppx, ppx + 1, DY + 8, DY + 10, ppz, ppz + 1, TRUNK)
    leaf_blob(ppx, DY + 16, ppz, 6, 61, LEAF2, anchor=(ppx, DY + 9, ppz), squash=0.7, keep=0.42)
# roof plant on the annex
box(cxN - 20, cxN + 20, DY + HALL_H + 4, DY + HALL_H + 14, AZ1 - 50, AZ1 - 30, HVAC)
box(cxN - 18, cxN + 18, DY + HALL_H + 14, DY + HALL_H + 15, AZ1 - 48, AZ1 - 32, DARK_METAL)
# floating toys (dynamic: plastic floats in Teardown water)
PROPS.append(("beach_ball", cxN - 30, DY - 6, pz0 + 30, 0))
PROPS.append(("beach_ball", cxN + 34, DY - 6, pz0 + 52, 0))
PROPS.append(("swim_ring", cxN - 6, DY - 4, pz0 + 18, 0))
PROPS.append(("swim_ring", cxN + 14, DY - 4, pz0 + 44, 30))
PROPS.append(("kickboard", cxN - 44, DY - 3, pz0 + 46, 20))
PROPS.append(("kickboard", cxN + 46, DY - 3, pz0 + 20, -15))
SOUND_SPOTS = [("pool", cxN, DY, (pz0 + pz1) // 2), ("spa", scx, DY, scz)]

# ============================================================================
# 9. Texture pass: per-voxel / per-panel colour variation
# ============================================================================
def vary(base, variants, cell=(1, 1, 1), seed=0, mix=0.0, weights=None):
    """replace `base` voxels with one of `variants` chosen by a hash of their cell;
    `mix` adds per-voxel noise on top of the per-cell choice."""
    X, Y, Z = np.nonzero(G == base)
    if len(X) == 0:
        return
    t = hash3(X // cell[0], Y // cell[1], Z // cell[2], seed)
    if mix:
        t = (1 - mix) * t + mix * hash3(X, Y, Z, seed + 101)
    w = np.cumsum(weights if weights else [1] * len(variants)); w = w / w[-1]
    idx = np.searchsorted(w, t, side="right").clip(0, len(variants) - 1)
    G[X, Y, Z] = np.array(variants, np.uint8)[idx]

def brick_bond():
    X, Y, Z = np.nonzero(G == BRICK)
    along = X + Z                       # one of the two is constant on a wall face
    off = (Y % 2) * 1                   # stagger every other course
    t = hash3((along + off) // 3, Y, np.zeros_like(Y), 41)
    G[X, Y, Z] = np.where(t < 0.45, BRICK, np.where(t < 0.8, BRICK2, BRICK3))

brick_bond()
vary(ATR_WALL, [ATR_WALL, ATR_WALL2, ATR_WALL3], cell=(17, 15, 17), seed=2, mix=0.15, weights=[5, 3, 2])
vary(ASPHALT, [ASPHALT, ASPHALT2], seed=3, weights=[3, 1])
vary(PAVER, [PAVER, PAVER2], cell=(6, 1, 6), seed=4)
vary(LAWN, [LAWN, LAWN2], seed=5)
vary(CARP_A, [CARP_A, CARP_A2], seed=6, weights=[2, 1])
vary(CARP_B, [CARP_B, CARP_B2], seed=7, weights=[2, 1])
vary(COR_CARP, [COR_CARP, COR_CARP2], seed=8, weights=[4, 1])
vary(RUG, [RUG, RUG2], seed=9, weights=[3, 1])
vary(WOOD_DARK, [WOOD_DARK, WOOD_DARK2], cell=(1, 3, 1), seed=10, weights=[2, 1])
vary(WOOD_MED, [WOOD_MED, WOOD_MED2], cell=(1, 3, 1), seed=11, weights=[2, 1])
vary(ROOF, [ROOF, ROOF2], cell=(8, 1, 8), seed=12)
vary(EXT_TRIM, [EXT_TRIM, EXT_TRIM2], cell=(4, 2, 4), seed=13, weights=[3, 1])
vary(BASE_STONE, [BASE_STONE, BASE_STONE2], cell=(6, 3, 6), seed=14)

# ============================================================================
# 10. Props (separate dynamic bodies)
# ============================================================================
def make_car(paint_c):
    a = np.zeros((20, 15, 44), np.uint8)       # x, y, z  (front = +z)
    a[1:19, 3:9, 1:43] = paint_c
    a[2:18, 9:14, 11:31] = paint_c
    a[1:19, 9:13, 12:30] = GLASS_EXT           # side windows
    a[2:18, 9:13, 11:12] = GLASS_EXT; a[2:18, 9:13, 30:31] = GLASS_EXT
    a[2:18, 13:14, 12:30] = paint_c            # roof
    a[1:19, 9:13, 20:21] = paint_c             # B pillar
    a[3:17, 3:9, 0:1] = DARK_METAL; a[3:17, 3:9, 43:44] = DARK_METAL   # bumpers
    a[2:6, 6:8, 43:44] = STREET_LMP; a[14:18, 6:8, 43:44] = STREET_LMP # headlights
    a[2:6, 6:8, 0:1] = RED; a[14:18, 6:8, 0:1] = RED                   # tail lights
    a[1:19, 8:9, 1:43] = DARK_METAL            # trim line
    for wz in (8, 34):
        a[0:3, 0:6, wz - 3:wz + 3] = TIRE; a[17:20, 0:6, wz - 3:wz + 3] = TIRE
        a[0:1, 2:4, wz - 1:wz + 1] = CHROME; a[19:20, 2:4, wz - 1:wz + 1] = CHROME
        a[3:17, 0:3, wz - 3:wz + 3] = 0
    a[3:17, 2:3, 4:40] = DARK_METAL            # underbody
    return a

def make_cart():
    a = np.zeros((12, 21, 7), np.uint8)
    a[:, 2:3, :] = BRASS
    for (x, z) in ((0, 0), (11, 0), (0, 6), (11, 6)):
        a[x, 0:21, z] = BRASS
    a[:, 20, 0] = BRASS; a[:, 20, 6] = BRASS
    a[1:6, 3:9, 1:6] = UPHOL; a[6:11, 3:7, 2:6] = TV_BODY; a[2:9, 9:12, 2:5] = CAR_C
    a[0, 0, 0] = TIRE; a[11, 0, 0] = TIRE; a[0, 0, 6] = TIRE; a[11, 0, 6] = TIRE
    return a

def make_ball(r=4):
    n = 2 * r + 1
    a = np.zeros((n, n, n), np.uint8)
    cols = [BLANKET_B, CERAMIC, BLANKET_C, ART2, CERAMIC, ART1]
    for x in range(n):
        for y in range(n):
            for z in range(n):
                if (x - r) ** 2 + (y - r) ** 2 + (z - r) ** 2 <= r * r + 1:
                    ang = (np.degrees(np.arctan2(z - r, x - r)) + 360) % 360
                    a[x, y, z] = cols[int(ang // 60)] if abs(y - r) < r - 0.5 else CERAMIC
    return a

def make_ring(R=6, t=2):
    n = 2 * (R + t) + 1
    a = np.zeros((n, 2 * t + 1, n), np.uint8)
    c = R + t
    for x in range(n):
        for z in range(n):
            d = ((x - c) ** 2 + (z - c) ** 2) ** 0.5
            for y in range(2 * t + 1):
                if (d - R) ** 2 + (y - t) ** 2 <= t * t + 0.5:
                    ang = (np.degrees(np.arctan2(z - c, x - c)) + 360) % 360
                    a[x, y, z] = BLANKET_B if int(ang // 45) % 2 == 0 else PILLOW
    return a

def make_kickboard():
    a = np.zeros((8, 1, 12), np.uint8)
    a[:, :, :] = ART1
    a[0, :, 0] = a[7, :, 0] = 0
    return a

def make_crate(n=10):
    a = np.zeros((n, n, n), np.uint8)
    a[:, :, :] = WOOD_LIGHT
    for i in range(n):
        for j in range(n):
            for k in range(n):
                edge = sum(v in (0, n - 1) for v in (i, j, k)) >= 2
                if edge or (j in (n // 2,) and (i in (0, n - 1) or k in (0, n - 1))):
                    a[i, j, k] = WOOD_MED
    a[1:-1, 1:-1, 1:-1] = 0
    return a

def make_barrel(r=3, h=9):
    a = np.zeros((2 * r + 1, h, 2 * r + 1), np.uint8)
    for x in range(2 * r + 1):
        for z in range(2 * r + 1):
            if (x - r) ** 2 + (z - r) ** 2 <= r * r + 1:
                a[x, :, z] = RED
                a[x, 2, z] = DARK_METAL; a[x, h - 3, z] = DARK_METAL
    a[1:-1, 1:-1, 1:-1][a[1:-1, 1:-1, 1:-1] > 0] = 0
    a[:, 0, :][a[:, 1, :] == 0] = 0
    return a

def make_sofa():
    a = np.zeros((20, 9, 8), np.uint8)
    a[:, 0:4, :] = UPHOL
    a[:, 4:9, 6:8] = UPHOL
    a[0:2, 4:7, :] = UPHOL; a[18:20, 4:7, :] = UPHOL
    a[2:18, 4:5, 0:6] = UPHOL2
    for (x, z) in ((0, 0), (19, 0), (0, 7), (19, 7)):
        a[x, 0, z] = WOOD_DARK
    return a

def make_crt():
    a = np.zeros((8, 7, 7), np.uint8)
    a[:, :, :] = TV_BODY
    a[1:7, 1:6, 0] = TV_SCREEN
    a[2:6, 0, 3:7] = DARK_METAL
    return a

PROP_SHAPES = {"car_a": make_car(CAR_A), "car_b": make_car(CAR_B), "car_c": make_car(CAR_C), "luggage_cart": make_cart(),
               "beach_ball": make_ball(), "swim_ring": make_ring(), "kickboard": make_kickboard(),
               "crate": make_crate(), "barrel": make_barrel(), "sofa": make_sofa(), "crt_tv": make_crt()}
SPAWNABLE = [("car_a", "Car (blue)"), ("car_b", "Car (silver)"), ("car_c", "Car (red)"), ("luggage_cart", "Luggage cart"),
             ("beach_ball", "Beach ball"), ("swim_ring", "Swim ring"), ("kickboard", "Kickboard"),
             ("crate", "Wooden crate"), ("barrel", "Red barrel"), ("sofa", "Lobby sofa"), ("crt_tv", "Old TV")]

# ============================================================================
# 11. Export: chunks -> .vox, main.xml
# ============================================================================
def matl_dict(i):
    rgb, fin, kw = PAL.get(i, ((128, 128, 128), "diffuse", {}))
    base = {"_type": "_diffuse", "_weight": "1", "_rough": "0.1", "_spec": "0.5", "_spec_p": "0.5",
            "_ior": "0.3", "_att": "0", "_g0": "-0.5", "_g1": "0.8", "_gw": "0.7", "_flux": "0", "_ldr": "0"}
    if fin == "glass":
        base.update({"_type": "_glass", "_weight": "0.5", "_rough": "0.05"})
    elif fin == "metal":
        base.update({"_type": "_metal", "_weight": str(kw.get("metal", 0.5)), "_rough": str(kw.get("rough", 0.5))})
    elif fin == "emit":
        base.update({"_type": "_emit", "_weight": str(kw.get("weight", 0.5)), "_flux": str(kw.get("flux", 2))})
    else:
        base.update({"_rough": "0.9"})
    return base

def vox_dict(d):
    b = struct.pack("<i", len(d))
    for k, v in d.items():
        kb, vb = k.encode(), str(v).encode()
        b += struct.pack("<i", len(kb)) + kb + struct.pack("<i", len(vb)) + vb
    return b

def chunk(cid, content, children=b""):
    return cid + struct.pack("<ii", len(content), len(children)) + content + children

def write_vox(path, sub):
    """sub: array indexed [x, y(up), z] in Teardown axes. Writes MV axes (x, -z, y)."""
    sx, sy, sz = sub.shape
    xs, ys, zs = np.nonzero(sub)
    cols = sub[xs, ys, zs]
    xyzi = np.stack([xs.astype(np.uint8), (sz - 1 - zs).astype(np.uint8), ys.astype(np.uint8),
                     cols.astype(np.uint8)], axis=1).tobytes()
    size_c = chunk(b"SIZE", struct.pack("<iii", sx, sz, sy))
    xyzi_c = chunk(b"XYZI", struct.pack("<i", len(xs)) + xyzi)
    ntrn0 = chunk(b"nTRN", struct.pack("<i", 0) + vox_dict({}) + struct.pack("<iiii", 1, -1, -1, 1) + vox_dict({}))
    ngrp = chunk(b"nGRP", struct.pack("<i", 1) + vox_dict({}) + struct.pack("<ii", 1, 2))
    ntrn2 = chunk(b"nTRN", struct.pack("<i", 2) + vox_dict({"_name": "shape"}) + struct.pack("<iiii", 3, -1, 0, 1)
                  + vox_dict({"_t": "0 0 0"}))
    nshp = chunk(b"nSHP", struct.pack("<i", 3) + vox_dict({}) + struct.pack("<ii", 1, 0) + vox_dict({}))
    rgba = bytearray()
    for i in range(1, 257):
        r, g, b_ = PAL[i][0] if i in PAL else (128, 128, 128)
        rgba += bytes((r, g, b_, 255))
    rgba_c = chunk(b"RGBA", bytes(rgba))
    matls = b"".join(chunk(b"MATL", struct.pack("<i", i) + vox_dict(matl_dict(i))) for i in range(1, 256) if i in PAL)
    main = chunk(b"MAIN", b"", size_c + xyzi_c + ntrn0 + ngrp + ntrn2 + nshp + rgba_c + matls)
    with open(path, "wb") as f:
        f.write(b"VOX " + struct.pack("<i", 150) + main)
    return len(xs)

def export():
    os.makedirs(VOXDIR, exist_ok=True)
    for fn in os.listdir(VOXDIR):
        if fn.endswith(".vox"):
            os.remove(os.path.join(VOXDIR, fn))
    CX, CZ = (W / 2) * 0.1, (D / 2) * 0.1
    # Few, large shapes (<= 256 per axis), split only along party-wall planes and never
    # horizontally: Teardown judges support per shape, so seams through structure make
    # whole slabs of wall drop off when something near a seam is shot.
    XS_MAIN = [0, ax0 + 2 * SHORT_BAY_W, W]
    XS_ANNEX = [0, A_X0 - 16, A_X1 + 16, W]          # the pool hall stays in one shape
    BANDS = [(0, az0 + 2 * LONG_BAY_W, XS_MAIN), (az0 + 2 * LONG_BAY_W, az0 + 6 * LONG_BAY_W, XS_MAIN),
             (az0 + 6 * LONG_BAY_W, AZ0 - 6, XS_MAIN), (AZ0 - 6, D, XS_ANNEX)]
    YS = [0, H]
    for (z0b, z1b, XS) in BANDS:
        assert 0 < z1b - z0b <= 256, (z0b, z1b)
        assert all(0 < b_ - a_ <= 256 for a_, b_ in zip(XS, XS[1:])), XS
    voxes = []
    total = 0
    for zi, (z0, z1_, XS) in enumerate(BANDS):
        for xi, (x0, x1_) in enumerate(zip(XS, XS[1:])):
            for yi, (y0, y1_) in enumerate(zip(YS, YS[1:])):
                sub = G[x0:x1_, y0:y1_, z0:z1_]
                nz = np.nonzero(sub)
                if len(nz[0]) == 0:
                    continue
                bx_ = (nz[0].min(), nz[0].max() + 1); by_ = (nz[1].min(), nz[1].max() + 1); bz_ = (nz[2].min(), nz[2].max() + 1)
                sub = sub[bx_[0]:bx_[1], by_[0]:by_[1], bz_[0]:bz_[1]]
                gx0, gy0, gz0 = x0 + bx_[0], y0 + by_[0], z0 + bz_[0]
                sx, sy, sz = sub.shape
                name = f"c_{xi}_{yi}_{zi}"
                n = write_vox(os.path.join(VOXDIR, name + ".vox"), sub)
                total += n
                # Teardown vox origin from the grid min corner: (floor(sx/2), 0, sz - floor(sz/2))
                ox = (gx0 + sx // 2) * 0.1 - CX
                oy = gy0 * 0.1
                oz = (gz0 + sz - sz // 2) * 0.1 - CZ
                voxes.append(dict(name=name, gmin=(gx0, gy0, gz0), size=(sx, sy, sz), pos=(ox, oy, oz), lights=[], n=n))
    for pname, arr in PROP_SHAPES.items():
        write_vox(os.path.join(VOXDIR, pname + ".vox"), arr)
    # spawnable prefabs (game spawn menu via spawn.txt, and the map's own N-key spawn menu)
    pdir = os.path.join(OUT, "prefab")
    os.makedirs(pdir, exist_ok=True)
    lines = []
    for pname, label in SPAWNABLE:
        with open(os.path.join(pdir, pname + ".xml"), "w") as f:
            f.write(f'<prefab version="1.6.0">\n\t<group name="{pname}">\n\t\t<body dynamic="true">\n'
                    f'\t\t\t<vox pos="0 0 0" file="MOD/vox/{pname}.vox" object="shape"/>\n\t\t</body>\n\t</group>\n</prefab>\n')
        lines.append(f"prefab/{pname}.xml : Liminal Atrium/{label}")
    with open(os.path.join(OUT, "spawn.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    write_vox(os.path.join(VOXDIR, "elev_btn.vox"), np.full((1, 1, 1), CEIL_LAMP, np.uint8))
    for e in ELEVATORS:
        write_vox(os.path.join(VOXDIR, f"elev_car_{e['shaft']}.vox"), e["arr"])
    door_files = {}
    for d in DOORS:
        key = (d["arr"].shape, d["arr"].tobytes())
        if key not in door_files:
            door_files[key] = f"door_{len(door_files)}"
            write_vox(os.path.join(VOXDIR, door_files[key] + ".vox"), d["arr"])
        d["file"] = door_files[key]

    def owner(gx, gy, gz):
        for v in voxes:
            (a, b, c), (sx, sy, sz) = v["gmin"], v["size"]
            if a <= gx < a + sx and b <= gy < b + sy and c <= gz < c + sz:
                return v
        return None
    # Teardown switches a shape-attached light off when the voxel at its position is gone.
    # So: put each light INSIDE the nearest lamp voxel (then only breaking that lamp kills it);
    # lights with no lamp within reach stay unattached (always on).
    EMIT = np.array([i for i, v in PAL.items() if v[1] == "emit" and i not in (CURT_LIT, CURT_LIT2)], np.uint8)
    loose = []
    snapped = 0
    R = 4
    for (gx, gy, gz, rgb, scale, size, ltags) in LIGHTS:
        ix, iy, iz = int(gx), int(gy), int(gz)
        x0, y0, z0 = max(ix - R, 0), max(iy - R, 0), max(iz - R, 0)
        win = G[x0:ix + R + 1, y0:iy + R + 1, z0:iz + R + 1]
        X, Y, Z = np.nonzero(np.isin(win, EMIT))
        # lights stay unattached (attached lights die on ANY damage to their shape); instead each light
        # remembers its lamp voxel and main.lua switches it off when that lamp is shot / smashed
        if len(X):
            d2 = (X + x0 + 0.5 - gx) ** 2 + (Y + y0 + 0.5 - gy) ** 2 + (Z + z0 + 0.5 - gz) ** 2
            j = int(np.argmin(d2))
            lx, ly, lz = X[j] + x0, Y[j] + y0, Z[j] + z0
            lamp = f"{(lx + 0.5) * 0.1 - CX:.3f},{(ly + 0.5) * 0.1:.3f},{(lz + 0.5) * 0.1 - CZ:.3f}"
            ltags = (ltags + " " if ltags else "") + "lamp=" + lamp
            snapped += 1
        loose.append((gx * 0.1 - CX, gy * 0.1, gz * 0.1 - CZ, rgb, scale, size, ltags))

    def f3(a): return " ".join(f"{t:.3f}".rstrip("0").rstrip(".") if abs(t) > 1e-9 else "0" for t in a)
    def light_xml(p, rgb, scale, size, ind="\t\t\t", ltags=""):
        t_ = f' tags="{ltags}"' if ltags else ""
        return f'{ind}<light{t_} pos="{f3(p)}" type="sphere" color="{f3(rgb)}" scale="{scale:g}" size="{size:g}"/>\n'

    spawn = ((ax0 + ax1) / 2 * 0.1 - CX, G0 * 0.1 + 0.1, (az0 + 18) * 0.1 - CZ)
    half_w, half_d = W / 2 * 0.1, D / 2 * 0.1
    xml = []
    xml.append('<scene version="6" shadowVolume="%d 30 %d">\n' % (int(W * 0.1) + 4, int(D * 0.1) + 4))
    xml.append('\t<environment skybox="cloudy.dds" skyboxtint="0.35 0.3 0.5" skyboxbrightness="0.12" skyboxrot="0" '
               'constant="0.004 0.003 0.006" ambient="0.25" ambientexponent="1.6" fogColor="0.07 0.06 0.1" '
               'fogParams="30 160 0.9 4" sunBrightness="0" sunColorTint="0.6 0.6 1" sunDir="auto" sunSpread="0" '
               'sunLength="32" sunFogScale="1" sunGlare="0" exposure="1 6" brightness="1" nightlight="true" '
               'wetness="0" puddleamount="0" puddlesize="0.5" rain="0"/>\n')
    xml.append('\t<postprocessing saturation="0.92" colorbalance="1.0 0.94 1.1" brightness="1.05" gamma="1" bloom="1.3"/>\n')
    xml.append(f'\t<spawnpoint pos="{f3(spawn)}" rot="0 180 0"/>\n')
    # base-game main.lua: player tools / spawn menu like the official sandbox levels.
    # (our own logic lives in the mod-root main.lua, which the game runs automatically;
    #  it guards itself so it never runs twice even if "main.lua" resolves to it)
    xml.append('\t<boundary>\n')
    for (bx_, bz_) in [(-half_w, -half_d), (half_w, -half_d), (half_w, half_d), (-half_w, half_d)]:
        xml.append(f'\t\t<vertex pos="{bx_:.1f} {bz_:.1f}"/>\n')
    xml.append('\t</boundary>\n')
    xml.append('\t<group name="liminal_atrium" pos="0 0 0">\n')
    for v in voxes:
        if v["lights"]:
            xml.append(f'\t\t<vox name="{v["name"]}" pos="{f3(v["pos"])}" file="MOD/vox/{v["name"]}.vox" object="shape">\n')
            for (lx, ly, lz, rgb, scale, size, ltags) in v["lights"]:
                xml.append(light_xml((lx, ly, lz), rgb, scale, size, ltags=ltags))
            xml.append('\t\t</vox>\n')
        else:
            xml.append(f'\t\t<vox name="{v["name"]}" pos="{f3(v["pos"])}" file="MOD/vox/{v["name"]}.vox" object="shape"/>\n')
    for (wx, wy, wz, rgb, scale, size, ltags) in loose:
        xml.append(light_xml((wx, wy, wz), rgb, scale, size, "\t\t", ltags))
    xml.append('\t</group>\n')
    for (sy_, dep, pts) in POOLS:
        # polygon water anchored at the pool centre; vertices relative to it (like every child node).
        # 'size' is given too, so even a box interpretation stays inside the pool.
        xs_ = [q[0] for q in pts]; zs_ = [q[1] for q in pts]
        pcx, pcz = (min(xs_) + max(xs_)) / 2, (min(zs_) + max(zs_)) / 2
        wx_, wz_ = pcx * 0.1 - CX, pcz * 0.1 - CZ
        xml.append(f'\t<water type="polygon" pos="{wx_:.3f} {sy_ * 0.1:.2f} {wz_:.3f}" size="{(max(xs_) - min(xs_)) * 0.1:.2f} '
                   f'{(max(zs_) - min(zs_)) * 0.1:.2f}" depth="{dep * 0.1:.2f}" wave="0.02" ripple="0.25" motion="0.05" foam="0">\n')
        for (vx, vz) in pts:
            xml.append(f'\t\t<vertex pos="{(vx - pcx) * 0.1:.3f} {(vz - pcz) * 0.1:.3f}"/>\n')
        xml.append('\t</water>\n')
    for (kind, sx_, sy_, sz_) in SOUND_SPOTS:
        xml.append(f'\t<location tags="ambsound kind={kind}" pos="{f3((sx_ * 0.1 - CX, sy_ * 0.1, sz_ * 0.1 - CZ))}"/>\n')
    xml.append('\t<group name="props" pos="0 0 0">\n')
    for i, (pname, gx, gy, gz, roty) in enumerate(PROPS):
        sx, sy, sz = PROP_SHAPES[pname].shape
        # place so the prop's min corner sits at (gx, gy, gz) when unrotated
        ox = (gx + sx // 2) * 0.1 - CX; oy = gy * 0.1 + 0.02; oz = (gz + sz - sz // 2) * 0.1 - CZ
        xml.append(f'\t\t<body name="{pname}_{i}" pos="{f3((ox, oy, oz))}" rot="0 {roty} 0" dynamic="true">\n'
                   f'\t\t\t<vox pos="0 0 0" file="MOD/vox/{pname}.vox" object="shape"/>\n\t\t</body>\n')
    xml.append('\t</group>\n')
    def origin(arr, gmin):
        sx, sy, sz = arr.shape
        gx, gy, gz = gmin
        return ((gx + sx // 2) * 0.1 - CX, gy * 0.1, (gz + sz - sz // 2) * 0.1 - CZ)
    xml.append('\t<group name="elevators" pos="0 0 0">\n')
    for e in ELEVATORS:
        bo = origin(e["arr"], e["gmin"])
        xml.append(f'\t\t<body name="car_{e["shaft"]}" tags="elevcar shaft={e["shaft"]} floor={e["floor"]}" '
                   f'pos="{f3(bo)}" dynamic="true">\n')
        LX, LY, LZ = np.nonzero(e["arr"] == CEIL_LAMP)
        mid = np.array(e["arr"].shape) / 2
        j = int(np.argmin((LX - mid[0]) ** 2 + (LZ - mid[2]) ** 2))
        gx_, gy_, gz_ = e["gmin"]
        lrel = ((gx_ + LX[j] + 0.5) * 0.1 - CX - bo[0], (gy_ + LY[j] + 0.5) * 0.1 - bo[1], (gz_ + LZ[j] + 0.5) * 0.1 - CZ - bo[2])
        xml.append(f'\t\t\t<vox pos="0 0 0" file="MOD/vox/elev_car_{e["shaft"]}.vox" object="shape">\n'
                   f'\t\t\t\t<light pos="{f3(lrel)}" type="sphere" color="1 0.88 0.7" scale="1.6" size="0.25"/>\n'
                   f'\t\t\t</vox>\n')
        for (barr, bmin, f) in e["buttons"]:
            o = origin(barr, bmin)
            rel = (o[0] - bo[0], o[1] - bo[1], o[2] - bo[2])
            xml.append(f'\t\t\t<vox tags="elevbtn floor={f}" pos="{f3(rel)}" file="MOD/vox/elev_btn.vox" object="shape"/>\n')
        xml.append('\t\t</body>\n')
    for (barr, bmin, shaft, k) in CALLS:
        xml.append(f'\t\t<vox tags="elevcall shaft={shaft} floor={k}" pos="{f3(origin(barr, bmin))}" '
                   f'file="MOD/vox/elev_btn.vox" object="shape"/>\n')
    xml.append('\t</group>\n')
    xml.append('\t<group name="doors" pos="0 0 0">\n')
    for i, d in enumerate(DOORS):
        sx, sy, sz = d["arr"].shape
        gx, gy, gz = d["gmin"]
        ox = (gx + sx // 2) * 0.1 - CX; oy = gy * 0.1; oz = (gz + sz - sz // 2) * 0.1 - CZ
        if d["kind"] == "slide":   # elevator landing doors: moved by main.lua
            tags = d["tag"] + f" slide sx={d['slide'][0] * 0.1:.2f} sz={d['slide'][1] * 0.1:.2f}"
            xml.append(f'\t\t<body name="door{i}" tags="{tags}" pos="{f3((ox, oy, oz))}">\n'
                       f'\t\t\t<vox pos="0 0 0" file="MOD/vox/{d["file"]}.vox" object="shape"/>\n\t\t</body>\n')
            continue
        # physical door: dynamic body + two ball joints on the vertical hinge line (= a hinge whose
        # axis does not depend on any joint-axis convention). collide=true lets the frame stop it.
        px, pz = d["pivot"][0] * 0.1 - CX, d["pivot"][1] * 0.1 - CZ
        rel = [(px - ox, 0.1 * 2, pz - oz), (px - ox, sy * 0.1 - 0.2, pz - oz)]
        rot = 0
        bpos = (ox, oy, oz)
        if d["start_open"]:
            rot = d["ang"] * 0.85
            a = np.radians(rot)
            dx, dz = ox - px, oz - pz
            bpos = (px + dx * np.cos(a) + dz * np.sin(a), oy, pz - dx * np.sin(a) + dz * np.cos(a))
        xml.append(f'\t\t<body name="door{i}" tags="hoteldoor" pos="{f3(bpos)}" rot="0 {rot:g} 0" dynamic="true">\n'
                   f'\t\t\t<vox pos="0 0 0" file="MOD/vox/{d["file"]}.vox" object="shape"/>\n')
        for r_ in rel:
            xml.append(f'\t\t\t<joint pos="{f3(r_)}" type="ball" size="0.1" collide="true"/>\n')
        xml.append('\t\t</body>\n')
    xml.append('\t</group>\n')
    xml.append('</scene>\n')
    with open(os.path.join(OUT, "main.xml"), "w") as f:
        f.write("".join(xml))
    with open(os.path.join(OUT, "info.txt"), "w") as f:
        f.write("name = Liminal Atrium v3.7\n"
                "author = Claude\n"
                "description = A deserted hotel at night. 6 floors of fully furnished rooms around a purple-lit atrium, "
                "corridors, stairwells, elevator shafts, lobby, roof and parking lot. Sandbox - break everything.\n"
                "tags = Map\n")
    stats = dict(grid=[W, H, D], chunks=len(voxes), voxels=int(total), lights=len(LIGHTS), props=len(PROPS),
                 doors=len(DOORS), door_files=len(door_files), lights_with_lamp=snapped, lights_free=len(loose), elevators=len(ELEVATORS), calls=len(CALLS),
                 rooms=len(room_log), lit=sum(1 for r in room_log if r[3].startswith("lit")),
                 tv=sum(1 for r in room_log if r[3] == "tv"))
    print(json.dumps(stats))
    return stats

if __name__ == "__main__":
    export()
    if "--save-grid" in sys.argv:
        p = sys.argv[sys.argv.index("--save-grid") + 1]
        Gp = G.copy()   # preview grid: props stamped in at their spawn spots (unrotated)
        for (pname, gx, gy, gz, roty) in PROPS:
            arr = PROP_SHAPES[pname]; sx, sy, sz = arr.shape
            reg = Gp[gx:gx + sx, gy:gy + sy, gz:gz + sz]
            reg[arr > 0] = arr[arr > 0]
        stamps = [(e["arr"], e["gmin"]) for e in ELEVATORS] + [(b_[0], b_[1]) for e in ELEVATORS for b_ in e["buttons"]] \
            + [(c_[0], c_[1]) for c_ in CALLS]
        for arr, (gx, gy, gz) in stamps:
            sx, sy, sz = arr.shape
            Gp[gx:gx + sx, gy:gy + sy, gz:gz + sz][arr > 0] = arr[arr > 0]
        for (sy_, dep, pts) in POOLS:
            xs_ = [p_[0] for p_ in pts]; zs_ = [p_[1] for p_ in pts]
            for x in range(int(min(xs_)), int(max(xs_))):
                for z in range(int(min(zs_)), int(max(zs_))):
                    # point-in-polygon (convex, counter-clockwise or clockwise)
                    sgn = [np.sign((pts[(i + 1) % len(pts)][0] - pts[i][0]) * (z + 0.5 - pts[i][1]) -
                                   (pts[(i + 1) % len(pts)][1] - pts[i][1]) * (x + 0.5 - pts[i][0])) for i in range(len(pts))]
                    if (all(v >= 0 for v in sgn) or all(v <= 0 for v in sgn)) and Gp[x, int(sy_) - 1, z] == 0:
                        Gp[x, int(sy_) - 1, z] = GLASS
        for d in DOORS:
            arr = d["arr"]; gx, gy, gz = d["gmin"]; sx, sy, sz = arr.shape
            Gp[gx:gx + sx, gy:gy + sy, gz:gz + sz][arr > 0] = arr[arr > 0]
        np.save(p, Gp)
        meta = dict(W=W, H=H, D=D, ax0=ax0, ax1=ax1, az0=az0, az1=az1, bx0=bx0, bx1=bx1, bz0=bz0, bz1=bz1,
                    G0=G0, FH=FH, ATR_TOP=ATR_TOP, ROOF_Y=ROOF_Y,
                    pal={i: list(v[0]) for i, v in PAL.items()},
                    emit=[i for i, v in PAL.items() if v[1] == "emit"],
                    glass=[i for i, v in PAL.items() if v[1] == "glass"],
                    lights=[(l[0], l[1], l[2], l[3], l[4]) for l in LIGHTS])  # tags not needed for preview
        with open(p + ".json", "w") as f:
            json.dump(meta, f)
