#!/usr/bin/env python3
"""
Liminal Atrium - Teardown sandbox map generator.

Builds the whole building as one voxel grid (1 voxel = 0.1 m), then cuts it
into <=128^3 chunks, writes them as MagicaVoxel .vox files (Teardown palette
material indices) and writes main.xml with lights, spawn point and boundary.

Global grid axes == Teardown axes: gx -> +X, gy -> +Y (up), gz -> +Z.
North = +Z (the far wall in the reference photo).
"""
import os, struct, random, json, sys
import numpy as np

OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VOXDIR = os.path.join(OUT, "vox")
rng = random.Random(7)

# ----------------------------------------------------------------------------
# Palette  (index -> (rgb, material-finish))
# Teardown material is decided by index range:
#   1-8 glass | 9-24 grass | 25-40 dirt | 41-56 rock | 57-72 wood
#   73-88 concrete | 89-104 brick | 105-120 plaster | 121-136 weak metal
#   137-152 heavy metal | 153-168 plastic | 169-176 hard metal | 177-184 hard masonry
# ----------------------------------------------------------------------------
PAL = {}
def P(i, rgb, fin="diffuse", **kw):
    PAL[i] = (rgb, fin, kw)
    return i

# glass
GLASS      = P(1, (150, 172, 192), "glass")
GLASS_EXT  = P(2, (95, 115, 135), "glass")
GLASS_DOOR = P(3, (170, 190, 200), "glass")
# rock / dirt
BEDROCK    = P(41, (80, 78, 75))
# wood
WOOD_DARK  = P(57, (88, 60, 42))
WOOD_MED   = P(58, (128, 90, 58))
WOOD_DOOR  = P(59, (112, 78, 50))
WOOD_HEAD  = P(60, (66, 48, 38))
WOOD_LIGHT = P(61, (165, 125, 85))
# concrete
SLAB       = P(73, (128, 126, 122))
EXT_WALL   = P(74, (172, 162, 148))
FLOOR_STN  = P(75, (150, 124, 96))
FLOOR_MED  = P(76, (196, 180, 152))
ASPHALT    = P(77, (52, 52, 56))
FLOOR_BRD  = P(78, (112, 92, 72))
PAINT_LINE = P(79, (200, 198, 186))
ROOF       = P(80, (92, 92, 96))
EXT_TRIM   = P(81, (140, 132, 122))
STAIR_CONC = P(82, (150, 148, 142))
# plaster
ATR_WALL   = P(105, (216, 210, 224))
ATR_SEAM   = P(106, (200, 194, 210))
ROOM_WALL  = P(107, (214, 203, 178))
CEIL       = P(108, (226, 224, 219))
COR_WALL   = P(109, (198, 184, 160))
COR_WAINS  = P(110, (140, 112, 88))
TILE       = P(111, (228, 231, 231))
ATR_GRID   = P(112, (186, 182, 196))
ATR_PANEL  = P(113, (224, 222, 230))
STAIR_WALL = P(114, (182, 182, 176))
CORNICE    = P(115, (206, 201, 214))
TILE_DARK  = P(116, (150, 158, 160))
# weak metal
FRAME      = P(121, (36, 36, 42), "metal", rough=0.6, metal=0.4)
STEEL      = P(122, (160, 160, 166), "metal", rough=0.4, metal=0.8)
ELEV_DOOR  = P(123, (176, 176, 182), "metal", rough=0.25, metal=0.9)
BRASS      = P(124, (182, 146, 70), "metal", rough=0.3, metal=0.9)
RADIATOR   = P(125, (204, 204, 198), "metal", rough=0.7, metal=0.2)
MIRROR     = P(126, (205, 214, 220), "metal", rough=0.05, metal=1.0)
HVAC       = P(127, (138, 140, 144), "metal", rough=0.6, metal=0.5)
TV_SCREEN  = P(128, (110, 150, 255), "emit", flux=2, weight=0.6)
CEIL_LAMP  = P(129, (255, 238, 205), "emit", flux=2, weight=0.8)
COVE_LAMP  = P(130, (220, 196, 255), "emit", flux=2, weight=0.7)
ICE_LAMP   = P(131, (120, 200, 255), "emit", flux=2, weight=0.6)
EXIT_SIGN  = P(132, (60, 220, 90), "emit", flux=2, weight=0.7)
STREET_LMP = P(133, (255, 210, 150), "emit", flux=3, weight=1.0)
DARK_METAL = P(134, (70, 70, 76), "metal", rough=0.5, metal=0.6)
CABLE      = P(135, (30, 30, 30), "metal", rough=0.8, metal=0.3)
# heavy metal (unbreakable)
ELEV_RAIL  = P(137, (90, 90, 95), "metal", rough=0.5, metal=0.8)
# plastic
CURT_LIT   = P(153, (238, 192, 112), "emit", flux=1, weight=0.35)
CURT_LIT2  = P(154, (214, 164, 88), "emit", flux=1, weight=0.25)
CURT_DARK  = P(155, (96, 88, 74))
CURT_DARK2 = P(156, (80, 73, 62))
SHEET      = P(157, (226, 226, 220))
BLANKET    = P(158, (150, 128, 104))
PILLOW     = P(159, (236, 236, 230))
ROOM_CARP  = P(160, (96, 86, 76))
COR_CARP   = P(161, (108, 36, 42))
COR_GOLD   = P(162, (168, 128, 62))
RUG        = P(163, (30, 38, 34))
RUG_BRD    = P(164, (46, 56, 48))
TV_BODY    = P(165, (22, 22, 24))
UPHOL      = P(166, (72, 80, 96))
CERAMIC    = P(167, (236, 236, 236))
LAMPSHADE  = P(168, (250, 226, 172), "emit", flux=2, weight=0.6)
# plastic extra (re-use indices inside 153-168 only)

# ----------------------------------------------------------------------------
# Dimensions (voxels)
# ----------------------------------------------------------------------------
M = 40                      # apron around the building
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
H = ATR_TOP + 3 + 4 + 2              # parapet etc.

bx0, bz0 = M, M
bx1, bz1 = M + BX, M + BZ
ax0, az0 = bx0 + T, bz0 + T
ax1, az1 = ax0 + AX, az0 + AZ

G = np.zeros((W, H, D), dtype=np.uint8)
LIGHTS = []   # (gx, gy, gz, rgb, scale, size, kind)

def box(x0, x1, y0, y1, z0, z1, c):
    """fill [x0,x1) x [y0,y1) x [z0,z1) (any order of bounds)."""
    xa, xb = sorted((int(x0), int(x1))); ya, yb = sorted((int(y0), int(y1))); za, zb = sorted((int(z0), int(z1)))
    G[max(xa, 0):max(xb, 0), max(ya, 0):max(yb, 0), max(za, 0):max(zb, 0)] = c

def light(gx, gy, gz, rgb, scale=1.0, size=0.1, kind="sphere"):
    LIGHTS.append((gx, gy, gz, rgb, scale, size, kind))

def fy(k):
    """floor surface y of story k."""
    return G0 + k * FH

# ----------------------------------------------------------------------------
# Local frame helper: build things in (u, v, y) space, mapped to world.
#   u runs along a wall, v runs perpendicular (from atrium outward).
# ----------------------------------------------------------------------------
class Frame:
    def __init__(self, ox, oz, ux, uz, vx, vz):
        self.ox, self.oz, self.ux, self.uz, self.vx, self.vz = ox, oz, ux, uz, vx, vz
    def pt(self, u, v):
        return self.ox + self.ux * u + self.vx * v, self.oz + self.uz * u + self.vz * v
    def box(self, u0, u1, y0, y1, v0, v1, c):
        # u in [u0,u1), v in [v0,v1): convert half-open intervals robustly
        if u1 <= u0 or v1 <= v0 or y1 <= y0:
            return
        xa, za = self.pt(u0, v0)
        xb, zb = self.pt(u1 - 1, v1 - 1)
        box(min(xa, xb), max(xa, xb) + 1, y0, y1, min(za, zb), max(za, zb) + 1, c)
    def light(self, u, y, v, rgb, scale=1.0, size=0.1):
        x, z = self.pt(u, v)
        light(x + 0.5, y, z + 0.5, rgb, scale, size)

# ============================================================================
# 1. Ground
# ============================================================================
box(0, W, 0, 1, 0, D, BEDROCK)
box(0, W, 1, G0, 0, D, ASPHALT)
# parking lines on the apron (south side) and a kerb ring
for i in range(10):
    x = bx0 + 20 + i * 28
    box(x, x + 1, G0 - 1, G0, 2, bz0 - 10, PAINT_LINE)
box(bx0 - 6, bx1 + 6, G0, G0 + 1, bz0 - 6, bz0 - 4, EXT_TRIM)
box(bx0 - 6, bx1 + 6, G0, G0 + 1, bz1 + 4, bz1 + 6, EXT_TRIM)
box(bx0 - 6, bx0 - 4, G0, G0 + 1, bz0 - 6, bz1 + 6, EXT_TRIM)
box(bx1 + 4, bx1 + 6, G0, G0 + 1, bz0 - 6, bz1 + 6, EXT_TRIM)
# building foundation slab
box(bx0, bx1, 1, G0, bz0, bz1, SLAB)

# ============================================================================
# 2. Structure shell: floor slabs, exterior wall, roof
# ============================================================================
for k in range(1, FLOORS + 1):
    y = fy(k)
    box(bx0, bx1, y - SLAB_T, y, bz0, bz1, SLAB)
# cut the atrium void through all upper slabs
box(ax0, ax1, G0 + 1, ATR_TOP, az0, az1, 0)

# exterior walls (full height up to roof + parapet)
PAR = 10
for (x0, x1, z0, z1) in [(bx0, bx1, bz0, bz0 + T_EXT), (bx0, bx1, bz1 - T_EXT, bz1),
                         (bx0, bx0 + T_EXT, bz0, bz1), (bx1 - T_EXT, bx1, bz0, bz1)]:
    box(x0, x1, G0, ROOF_Y + PAR, z0, z1, EXT_WALL)
# horizontal trim bands at every slab on the outside
for k in range(1, FLOORS + 1):
    y = fy(k) - 2
    box(bx0 - 1, bx1 + 1, y, y + 2, bz0 - 1, bz0, EXT_TRIM)
    box(bx0 - 1, bx1 + 1, y, y + 2, bz1, bz1 + 1, EXT_TRIM)
    box(bx0 - 1, bx0, y, y + 2, bz0 - 1, bz1 + 1, EXT_TRIM)
    box(bx1, bx1 + 1, y, y + 2, bz0 - 1, bz1 + 1, EXT_TRIM)
box(bx0 - 1, bx1 + 1, ROOF_Y + PAR, ROOF_Y + PAR + 1, bz0 - 1, bz1 + 1, EXT_TRIM)   # parapet cap
# roof membrane over the room ring
box(bx0 + T_EXT, bx1 - T_EXT, ROOF_Y - 1, ROOF_Y, bz0 + T_EXT, bz1 - T_EXT, ROOF)
box(ax0, ax1, ROOF_Y - SLAB_T, ROOF_Y, az0, az1, 0)

# ============================================================================
# 3. Atrium: facade walls, windows, ceiling, floor
# ============================================================================
# facade walls (4 thick) from ground to the atrium roof
box(ax0 - T_FAC, ax0, G0, ATR_TOP + 3, az0 - T_FAC, az1 + T_FAC, ATR_WALL)   # west
box(ax1, ax1 + T_FAC, G0, ATR_TOP + 3, az0 - T_FAC, az1 + T_FAC, ATR_WALL)   # east
box(ax0 - T_FAC, ax1 + T_FAC, G0, ATR_TOP + 3, az0 - T_FAC, az0, ATR_WALL)   # south
box(ax0 - T_FAC, ax1 + T_FAC, G0, ATR_TOP + 3, az1, az1 + T_FAC, ATR_WALL)   # north
# the facade above the ring roof is the exterior of the atrium "lantern"
# -> give it the exterior finish on the outside face
box(ax0 - T_FAC, ax0 - T_FAC + 1, ROOF_Y, ATR_TOP + 3, az0 - T_FAC, az1 + T_FAC, EXT_WALL)
box(ax1 + T_FAC - 1, ax1 + T_FAC, ROOF_Y, ATR_TOP + 3, az0 - T_FAC, az1 + T_FAC, EXT_WALL)
box(ax0 - T_FAC, ax1 + T_FAC, ROOF_Y, ATR_TOP + 3, az0 - T_FAC, az0 - T_FAC + 1, EXT_WALL)
box(ax0 - T_FAC, ax1 + T_FAC, ROOF_Y, ATR_TOP + 3, az1 + T_FAC - 1, az1 + T_FAC, EXT_WALL)

# faint panel seams on the atrium face (horizontal at mid-storey, vertical at bay lines)
def atrium_face_frames():
    # frames whose (u, v=0) is the atrium-side face voxel layer of each wall,
    # v pointing into the room ring.  Returns (frame, length, bay_width, name)
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
    for b in range(0, L + 1, bw):
        fr.box(max(b - 0, 0), min(b + 1, L), G0, ATR_TOP, 0, 1, ATR_SEAM)

# cornice + cove light strip around the top of the atrium
for fr, L, bw, name in atrium_face_frames():
    fr.box(0, L, ATR_TOP - 6, ATR_TOP - 4, -2, 0, CORNICE)
    fr.box(0, L, ATR_TOP - 4, ATR_TOP - 3, -2, 0, COVE_LAMP)
    fr.box(0, L, ATR_TOP - 3, ATR_TOP, -1, 0, CORNICE)

# atrium ceiling: grid of panels (photo: fine square grid)
box(ax0, ax1, ATR_TOP, ATR_TOP + 3, az0, az1, ATR_PANEL)
for x in range(ax0, ax1, 12):
    box(x, x + 1, ATR_TOP, ATR_TOP + 1, az0, az1, ATR_GRID)
for z in range(az0, az1, 12):
    box(ax0, ax1, ATR_TOP, ATR_TOP + 1, z, z + 1, ATR_GRID)
# atrium roof on top
box(ax0 - T_FAC, ax1 + T_FAC, ATR_TOP + 3, ATR_TOP + 4, az0 - T_FAC, az1 + T_FAC, ROOF)
box(ax0 - T_FAC, ax1 + T_FAC, ATR_TOP + 4, ATR_TOP + 6, az0 - T_FAC, az0 - T_FAC + 1, EXT_TRIM)
box(ax0 - T_FAC, ax1 + T_FAC, ATR_TOP + 4, ATR_TOP + 6, az1 + T_FAC - 1, az1 + T_FAC, EXT_TRIM)
box(ax0 - T_FAC, ax0 - T_FAC + 1, ATR_TOP + 4, ATR_TOP + 6, az0 - T_FAC, az1 + T_FAC, EXT_TRIM)
box(ax1 + T_FAC - 1, ax1 + T_FAC, ATR_TOP + 4, ATR_TOP + 6, az0 - T_FAC, az1 + T_FAC, EXT_TRIM)

# a few recessed downlights in the ceiling grid
for i in range(3):
    for j in range(5):
        cx = ax0 + 30 + i * 50
        cz = az0 + 28 + j * 54
        box(cx - 2, cx + 2, ATR_TOP, ATR_TOP + 1, cz - 2, cz + 2, COVE_LAMP)

# atrium floor (photo: stone floor, 4 dark rugs in a 2x2 layout, round medallion in the middle)
box(ax0, ax1, G0 - 1, G0, az0, az1, FLOOR_STN)
box(ax0, ax1, G0 - 1, G0, az0, az0 + 6, FLOOR_BRD)
box(ax0, ax1, G0 - 1, G0, az1 - 6, az1, FLOOR_BRD)
box(ax0, ax0 + 6, G0 - 1, G0, az0, az1, FLOOR_BRD)
box(ax1 - 6, ax1, G0 - 1, G0, az0, az1, FLOOR_BRD)
cxA, czA = (ax0 + ax1) / 2, (az0 + az1) / 2
path = 22
for sx in (-1, 1):
    for sz in (-1, 1):
        x0 = cxA + sx * path / 2; x1 = cxA + sx * (AX / 2 - 16)
        z0 = czA + sz * path / 2; z1 = czA + sz * (AZ / 2 - 26)
        box(x0, x1, G0 - 1, G0, z0, z1, RUG_BRD)
        xa, xb = sorted((x0, x1)); za, zb = sorted((z0, z1))
        box(xa + 2, xb - 2, G0 - 1, G0, za + 2, zb - 2, RUG)
# central medallion (ellipse)
for x in range(ax0, ax1):
    for z in range(az0, az1):
        e = ((x + 0.5 - cxA) / 30) ** 2 + ((z + 0.5 - czA) / 22) ** 2
        if e <= 1.0:
            G[x, G0 - 1, z] = FLOOR_MED if e < 0.8 else FLOOR_BRD

# (mirrored so it sits on the right of the far wall, as in the photo)
# the long cable hanging from the ceiling near the NE corner (as in the photo)
box(ax0 + 22, ax0 + 21, G0 + 12, ATR_TOP, az1 - 3, az1 - 2, CABLE)
box(ax0 + 14, ax0 + 13, G0 + 12, ATR_TOP, az1 - 3, az1 - 2, CABLE)
# window-cleaning cradle parked at the bottom of the cables
box(ax0 + 25, ax0 + 10, G0 + 8, G0 + 9, az1 - 6, az1 - 1, STEEL)
box(ax0 + 25, ax0 + 10, G0 + 9, G0 + 12, az1 - 6, az1 - 5, STEEL)
box(ax0 + 25, ax0 + 24, G0, G0 + 12, az1 - 6, az1 - 1, STEEL)
box(ax0 + 11, ax0 + 10, G0, G0 + 12, az1 - 6, az1 - 1, STEEL)
# luggage cart near the north wall
lx, lz = ax0 + 40, az1 - 12
box(lx, lx + 12, G0 + 2, G0 + 3, lz, lz + 7, BRASS)
box(lx, lx + 1, G0, G0 + 20, lz, lz + 1, BRASS); box(lx + 11, lx + 12, G0, G0 + 20, lz, lz + 1, BRASS)
box(lx, lx + 1, G0, G0 + 20, lz + 6, lz + 7, BRASS); box(lx + 11, lx + 12, G0, G0 + 20, lz + 6, lz + 7, BRASS)
box(lx, lx + 12, G0 + 20, G0 + 21, lz, lz + 1, BRASS); box(lx, lx + 12, G0 + 20, G0 + 21, lz + 6, lz + 7, BRASS)
box(lx + 1, lx + 6, G0 + 3, G0 + 9, lz + 1, lz + 6, UPHOL)        # suitcase
box(lx + 6, lx + 11, G0 + 3, G0 + 7, lz + 2, lz + 6, TV_BODY)     # suitcase
# a few benches
for (bx, bz) in [(ax0 + 14, czA - 6), (ax1 - 20, czA - 6)]:
    box(bx, bx + 6, G0 + 3, G0 + 5, bz, bz + 12, WOOD_MED)
    box(bx, bx + 1, G0, G0 + 3, bz, bz + 12, DARK_METAL)
    box(bx + 5, bx + 6, G0, G0 + 3, bz, bz + 12, DARK_METAL)

# atrium lights (purple-ish, like the photo)
for i in range(2):
    for j in range(3):
        light(ax0 + 40 + i * 80, ATR_TOP - 8, az0 + 45 + j * 90, (0.78, 0.64, 1.0), 6.0, 0.6)
for fr, L, bw, name in atrium_face_frames():
    for u in range(L // 4, L, L // 2):
        x, z = fr.pt(u, -3)
        light(x + 0.5, ATR_TOP - 4.5, z + 0.5, (0.85, 0.7, 1.0), 3.0, 0.3)

# ============================================================================
# 4. Hotel rooms (ring around atrium) - one window per room, 6 floors
# ============================================================================
STATES = ["lit_closed"] * 22 + ["lit_open"] * 6 + ["dark_closed"] * 34 + ["dark_open"] * 26 + ["tv"] * 12
room_log = []

def room_frames():
    """frames for room bays: origin at the room-side face of the facade wall,
    u along the wall, v from window (0) to corridor partition (ROOM_D)."""
    F = []
    # west wall: rooms at x in [ax0-4-44, ax0-4); u along +z, v along -x
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

def window_in_facade(fr, bw, y):
    """cut the window through the facade wall: facade occupies v in [-T_FAC, 0)."""
    u0 = bw // 2 - WIN_W // 2 + 1
    fr.box(u0, u0 + WIN_W, y + SILL, y + SILL + WIN_H, -T_FAC, 0, 0)
    # dark frame ring (photo: thick black outline) at the 3 outer layers
    fr.box(u0, u0 + WIN_W, y + SILL, y + SILL + 1, -T_FAC, -1, FRAME)
    fr.box(u0, u0 + WIN_W, y + SILL + WIN_H - 1, y + SILL + WIN_H, -T_FAC, -1, FRAME)
    fr.box(u0, u0 + 1, y + SILL, y + SILL + WIN_H, -T_FAC, -1, FRAME)
    fr.box(u0 + WIN_W - 1, u0 + WIN_W, y + SILL, y + SILL + WIN_H, -T_FAC, -1, FRAME)
    # mullion-less pane, 1 voxel thick, set 1 voxel back from the atrium face
    fr.box(u0 + 1, u0 + WIN_W - 1, y + SILL + 1, y + SILL + WIN_H - 1, -T_FAC + 1, -T_FAC + 2, GLASS)
    # interior sill
    fr.box(u0 - 1, u0 + WIN_W + 1, y + SILL - 1, y + SILL, -1, 1, WOOD_LIGHT)
    return u0

def curtains(fr, u0, y, state):
    cu0, cu1 = u0 - 4, u0 + WIN_W + 4
    top, bot = y + SILL + WIN_H + 3, y + SILL - 3
    fr.box(cu0 - 1, cu1 + 1, top, top + 1, 1, 2, STEEL)          # rod
    lit = state.startswith("lit")
    a, b = (CURT_LIT, CURT_LIT2) if lit else (CURT_DARK, CURT_DARK2)
    closed = state.endswith("closed")
    if closed:
        spans = [(cu0, cu1)]
    else:
        spans = [(cu0, cu0 + 6), (cu1 - 6, cu1)]
    for s0, s1 in spans:
        for u in range(s0, s1):
            fold = (u // 2) % 2
            fr.box(u, u + 1, bot, top, 1 + fold, 2 + fold, a if fold == 0 else b)

def furnish_room(fr, bw, k, state):
    y = fy(k)
    U0, U1 = T_PART, bw          # usable u range (partition is u in [0, T_PART))
    # carpet (top layer of the slab)
    fr.box(U0, U1, y - 1, y, 0, ROOM_D, ROOM_CARP)
    # radiator under the window
    fr.box(bw // 2 - 8, bw // 2 + 9, y, y + 6, 0, 2, RADIATOR)
    for u in range(bw // 2 - 8, bw // 2 + 9, 2):
        fr.box(u, u + 1, y + 1, y + 5, 2, 3, RADIATOR)
    # ---- bed: head against the u = U1 partition
    bw_ = 16; bl = 19
    bv0 = 9
    bu1 = U1; bu0 = U1 - bl
    fr.box(bu0, bu1, y, y + 3, bv0, bv0 + bw_, WOOD_DARK)            # frame
    fr.box(bu0, bu1 - 1, y + 3, y + 6, bv0, bv0 + bw_, SHEET)         # mattress
    fr.box(bu0, bu1 - 7, y + 6, y + 7, bv0, bv0 + bw_, BLANKET)       # blanket
    fr.box(bu0, bu0 + 1, y + 3, y + 7, bv0, bv0 + bw_, BLANKET)       # blanket overhang
    fr.box(bu1 - 6, bu1 - 2, y + 6, y + 8, bv0 + 1, bv0 + 7, PILLOW)
    fr.box(bu1 - 6, bu1 - 2, y + 6, y + 8, bv0 + 9, bv0 + 15, PILLOW)
    fr.box(bu1 - 1, bu1, y, y + 14, bv0 - 1, bv0 + bw_ + 1, WOOD_HEAD) # headboard
    # nightstands + lamps
    for nv in (bv0 - 5, bv0 + bw_ + 1):
        fr.box(U1 - 5, U1, y, y + 6, nv, nv + 4, WOOD_MED)
        fr.box(U1 - 3, U1 - 2, y + 6, y + 9, nv + 1, nv + 2, BRASS)
        fr.box(U1 - 4, U1 - 1, y + 9, y + 12, nv, nv + 3, LAMPSHADE if state.startswith("lit") else CURT_DARK)
    if state.startswith("lit"):
        fr.light(U1 - 2.5, y + 10.5, bv0 - 3.5, (1.0, 0.78, 0.45), 1.6, 0.15)
    # ---- desk with TV on the opposite wall (u = U0 side)
    fr.box(U0, U0 + 6, y + 7, y + 8, 13, 30, WOOD_MED)
    fr.box(U0, U0 + 6, y, y + 7, 13, 14, WOOD_MED)
    fr.box(U0, U0 + 6, y, y + 7, 29, 30, WOOD_MED)
    fr.box(U0, U0 + 1, y + 10, y + 19, 15, 28, TV_BODY)
    fr.box(U0 + 1, U0 + 2, y + 11, y + 18, 16, 27, TV_SCREEN if state == "tv" else TV_BODY)
    if state == "tv":
        fr.light(U0 + 3, y + 14, 21.5, (0.45, 0.6, 1.0), 1.0, 0.2)
    # chair
    fr.box(U0 + 7, U0 + 11, y + 4, y + 5, 19, 24, UPHOL)
    fr.box(U0 + 10, U0 + 11, y + 5, y + 11, 19, 24, UPHOL)
    for cu in (U0 + 7, U0 + 10):
        for cv in (19, 23):
            fr.box(cu, cu + 1, y, y + 4, cv, cv + 1, DARK_METAL)
    # armchair by the window
    fr.box(U0 + 2, U0 + 9, y, y + 4, 3, 9, UPHOL)
    fr.box(U0 + 2, U0 + 3, y + 4, y + 10, 3, 9, UPHOL)
    fr.box(U0 + 2, U0 + 9, y + 4, y + 6, 3, 4, UPHOL)
    fr.box(U0 + 2, U0 + 9, y + 4, y + 6, 8, 9, UPHOL)
    # ---- bathroom box in the corridor-side corner (u high side)
    bu0b = U1 - 13
    v0b = ROOM_D - 13
    fr.box(bu0b, bu0b + 1, y, y + FH - SLAB_T, v0b, ROOM_D, ROOM_WALL)      # wall along v
    fr.box(bu0b, U1, y, y + FH - SLAB_T, v0b, v0b + 1, ROOM_WALL)          # wall along u
    fr.box(bu0b, bu0b + 1, y, y + 21, v0b + 2, v0b + 10, 0)                # bathroom door opening
    fr.box(bu0b + 1, U1, y - 1, y, v0b + 1, ROOM_D, TILE)                 # tile floor
    fr.box(bu0b + 1, U1, y, y + 12, ROOM_D - 1, ROOM_D, TILE)             # wainscot tiles
    fr.box(U1 - 1, U1, y, y + 12, v0b + 1, ROOM_D, TILE)
    fr.box(U1 - 4, U1, y, y + 4, v0b + 3, v0b + 7, CERAMIC)                # toilet
    fr.box(U1 - 2, U1, y + 4, y + 9, v0b + 3, v0b + 7, CERAMIC)
    fr.box(bu0b + 1, bu0b + 9, y, y + 6, ROOM_D - 6, ROOM_D - 1, CERAMIC)  # tub
    fr.box(bu0b + 2, bu0b + 8, y + 3, y + 6, ROOM_D - 5, ROOM_D - 2, 0)
    fr.box(bu0b + 3, bu0b + 7, y + 6, y + 8, ROOM_D - 2, ROOM_D - 1, CERAMIC)  # sink-ish ledge
    fr.box(U1 - 1, U1, y + 13, y + 22, v0b + 9, ROOM_D - 2, MIRROR)
    if state.startswith("lit") and rng.random() < 0.5:
        fr.box(bu0b + 5, bu0b + 8, y + 26, y + 27, v0b + 5, v0b + 8, CEIL_LAMP)
    # ---- wardrobe near the entrance (u low side)
    fr.box(U0, U0 + 6, y, y + 22, ROOM_D - 12, ROOM_D - 1, WOOD_DARK)
    fr.box(U0 + 6, U0 + 7, y + 1, y + 21, ROOM_D - 12, ROOM_D - 1, WOOD_MED)
    # ---- entrance door in the corridor partition (v in [ROOM_D, ROOM_D+T_PART))
    du0 = U0 + 8
    fr.box(du0, du0 + 9, y, y + 21, ROOM_D, ROOM_D + T_PART, 0)
    fr.box(du0 - 1, du0 + 10, y + 21, y + 22, ROOM_D, ROOM_D + T_PART + 1, WOOD_DARK)  # header
    fr.box(du0 - 1, du0, y, y + 21, ROOM_D + T_PART, ROOM_D + T_PART + 1, WOOD_DARK)
    fr.box(du0 + 9, du0 + 10, y, y + 21, ROOM_D + T_PART, ROOM_D + T_PART + 1, WOOD_DARK)
    # open door leaf (swung into the room, against the wardrobe side)
    fr.box(du0, du0 + 1, y, y + 21, ROOM_D - 10, ROOM_D - 1, WOOD_DOOR)
    fr.box(du0 + 1, du0 + 2, y + 10, y + 11, ROOM_D - 3, ROOM_D - 2, BRASS)
    # room number plaque + sconce in the corridor
    fr.box(du0 + 11, du0 + 14, y + 15, y + 17, ROOM_D + T_PART, ROOM_D + T_PART + 1, BRASS)
    # ceiling light in lit rooms
    if state.startswith("lit"):
        cu = (U0 + U1) // 2
        fr.box(cu - 2, cu + 2, y + FH - SLAB_T - 1, y + FH - SLAB_T, 18, 22, CEIL_LAMP)
        fr.light(cu, y + FH - SLAB_T - 2, 20, (1.0, 0.82, 0.55), 2.2, 0.3)

def build_rooms():
    for name, b, fr, bw in room_frames():
        for k in range(FLOORS):
            y = fy(k)
            # partition at u in [0, T_PART) from facade to corridor partition
            fr.box(0, T_PART, y - SLAB_T, y + FH - SLAB_T, 0, ROOM_D, ROOM_WALL)
            # corridor partition wall
            fr.box(0, bw, y - SLAB_T if k else G0, y + FH - SLAB_T, ROOM_D, ROOM_D + T_PART, COR_WALL)
            # entrance lobby replaces south bays 1,2 on the ground floor
            if k == 0 and name == "S" and b in (1, 2):
                continue
            u0 = window_in_facade(fr, bw, y)
            state = rng.choice(STATES)
            curtains(fr, u0, y, state)
            furnish_room(fr, bw, k, state)
            room_log.append((name, b, k, state))
    # closing partitions at the end of each wall run (u = bw*bays)
    for name, b, fr, bw in room_frames():
        if b == (LONG_BAYS if name in "WE" else SHORT_BAYS) - 1:
            fr.box(bw, bw + T_PART, G0, ROOF_Y - SLAB_T, 0, ROOM_D, ROOM_WALL)

# ============================================================================
# 6. Corridors (ring between room partition and exterior wall)
# ============================================================================
cor_frames = [
    # (frame: u along corridor, v across from partition outward), length
    ("W", Frame(bx0 + T_EXT + COR_W - 1, bz0 + T_EXT, 0, 1, -1, 0), BZ - 2 * T_EXT),
    ("E", Frame(bx1 - T_EXT - COR_W, bz1 - T_EXT - 1, 0, -1, 1, 0), BZ - 2 * T_EXT),
    ("S", Frame(bx1 - T_EXT - 1, bz0 + T_EXT + COR_W - 1, -1, 0, 0, -1), BX - 2 * T_EXT),
    ("N", Frame(bx0 + T_EXT, bz1 - T_EXT - COR_W, 1, 0, 0, 1), BX - 2 * T_EXT),
]
def build_corridors():
    for name, fr, L in cor_frames:
        for k in range(FLOORS):
            y = fy(k)
            # carpet runner with gold border and repeating diamond motif
            fr.box(0, L, y - 1, y, 0, COR_W, COR_CARP)
            fr.box(0, L, y - 1, y, 2, 3, COR_GOLD)
            fr.box(0, L, y - 1, y, COR_W - 3, COR_W - 2, COR_GOLD)
            for u in range(6, L, 12):
                for d in range(4):
                    fr.box(u + d, u + d + 1, y - 1, y, 9 - d, 9 + d, COR_GOLD)
                    fr.box(u + 7 - d, u + 8 - d, y - 1, y, 9 - d, 9 + d, COR_GOLD)
            # dropped ceiling + lamps
            fr.box(0, L, y + 24, y + 25, 0, COR_W, CEIL)
            for u in range(17, L - 5, 34):
                fr.box(u - 2, u + 2, y + 24, y + 25, 7, 11, CEIL_LAMP)
            for u in range(34, L - 5, 68):
                fr.light(u, y + 22, 9, (1.0, 0.86, 0.62), 2.0, 0.25)
            # wainscot on the exterior side wall + baseboard on partition side
            fr.box(0, L, y, y + 9, COR_W, COR_W + 1, COR_WAINS)
            fr.box(0, L, y, y + 1, -1, 0, COR_WAINS)
            # small exterior windows, one every 2 bays
            for u in range(30, L - 20, 68):
                fr.box(u, u + 8, y + 10, y + 22, COR_W, COR_W + T_EXT, 0)
                fr.box(u, u + 8, y + 10, y + 22, COR_W + 2, COR_W + 3, GLASS_EXT)
                fr.box(u - 1, u + 9, y + 9, y + 10, COR_W, COR_W + T_EXT + 1, EXT_TRIM)
        # strip the wainscot from the ground-floor entrance gap later (handled by carve below)



build_corridors()
build_rooms()

# ============================================================================
# 5. Ground floor lobby (south side, bays 1-2) + main entrance
# ============================================================================
lx0, lx1 = ax0 + SHORT_BAY_W, ax0 + 3 * SHORT_BAY_W
lz0, lz1 = az0 - T_FAC - ROOM_D, az0          # room depth zone
y = G0
box(lx0, lx1, y, y + FH - SLAB_T, lz0, lz1 - T_FAC, 0)
box(lx0, lx1, y - 1, y, lz0, lz1, FLOOR_STN)
box(lx0 + 4, lx1 - 4, y - 1, y, lz0 + 4, lz1 - 6, RUG_BRD)
box(lx0 + 6, lx1 - 6, y - 1, y, lz0 + 6, lz1 - 8, COR_CARP)
# glass double doors to the atrium
cx = (lx0 + lx1) // 2
box(cx - 14, cx + 14, y, y + 22, az0 - T_FAC, az0, FRAME)
box(cx - 13, cx + 13, y, y + 21, az0 - T_FAC, az0, 0)
box(cx - 13, cx + 13, y, y + 21, az0 - 3, az0 - 2, GLASS_DOOR)
box(cx - 1, cx + 1, y, y + 21, az0 - 3, az0 - 2, FRAME)
box(cx - 13, cx + 13, y, y + 1, az0 - 3, az0 - 2, FRAME)
box(cx - 13, cx + 13, y + 20, y + 21, az0 - 3, az0 - 2, FRAME)
box(cx - 3, cx - 2, y + 8, y + 13, az0 - 4, az0 - 3, BRASS)
box(cx + 2, cx + 3, y + 8, y + 13, az0 - 4, az0 - 3, BRASS)
box(cx - 10, cx + 10, y + 23, y + 26, az0 - 1, az0, EXIT_SIGN)
# reception desk
box(lx0 + 8, lx0 + 34, y, y + 11, lz0 + 14, lz0 + 20, WOOD_DARK)
box(lx0 + 8, lx0 + 34, y + 11, y + 12, lz0 + 13, lz0 + 21, WOOD_LIGHT)
box(lx0 + 12, lx0 + 14, y + 12, y + 15, lz0 + 16, lz0 + 18, BRASS)   # bell
# lobby sofas
for sz in (lz0 + 10, lz0 + 28):
    box(lx1 - 30, lx1 - 10, y, y + 5, sz, sz + 7, UPHOL)
    box(lx1 - 30, lx1 - 10, y + 5, y + 11, sz + (0 if sz < lz0 + 20 else 6), sz + (1 if sz < lz0 + 20 else 7), UPHOL)
box(lx1 - 26, lx1 - 14, y, y + 4, lz0 + 19, lz0 + 25, WOOD_MED)
box(lx0 + 2, lx1 - 2, y + 26, y + 27, lz0 + 2, lz1 - 6, CEIL)
for i in range(3):
    xx = lx0 + 14 + i * 26
    box(xx - 2, xx + 2, y + 26, y + 27, lz0 + 20, lz0 + 24, CEIL_LAMP)
    light(xx + 0.5, y + 24, lz0 + 22.5, (1.0, 0.85, 0.65), 2.5, 0.3)
# corridor partition doorway (lobby -> south corridor) and main entrance in the exterior wall
box(cx - 14, cx + 14, y, y + 22, lz0 - T_PART, lz0, 0)
box(cx - 16, cx + 16, y, y + 24, bz0, bz0 + T_EXT, FRAME)
box(cx - 15, cx + 15, y, y + 23, bz0, bz0 + T_EXT, 0)
box(cx - 15, cx + 15, y, y + 23, bz0 + 1, bz0 + 2, GLASS_DOOR)
box(cx - 1, cx + 1, y, y + 23, bz0 + 1, bz0 + 2, FRAME)
box(cx - 15, cx + 15, y, y + 1, bz0 + 1, bz0 + 2, FRAME)
# entrance canopy
box(cx - 30, cx + 30, y + 32, y + 35, bz0 - 30, bz0, EXT_TRIM)
box(cx - 28, cx + 28, y + 31, y + 32, bz0 - 28, bz0 - 2, CEIL)
for sx in (-28, 26):
    box(cx + sx, cx + sx + 2, G0, y + 32, bz0 - 28, bz0 - 26, DARK_METAL)
for i in range(4):
    xx = cx - 21 + i * 14
    box(xx, xx + 2, y + 31, y + 32, bz0 - 16, bz0 - 14, CEIL_LAMP)
light(cx + 0.5, y + 29, bz0 - 15, (1.0, 0.85, 0.65), 4.0, 0.4)
# hotel sign letters block (abstract)
box(cx - 24, cx + 24, y + 36, y + 44, bz0 - 2, bz0, DARK_METAL)
for i in range(8):
    xx = cx - 22 + i * 6
    box(xx, xx + 4, y + 37, y + 43, bz0 - 3, bz0 - 2, STREET_LMP if i % 3 != 1 else COVE_LAMP)

# re-open the main entrance through the wainscot
box(cx - 15, cx + 15, G0, G0 + 23, bz0, bz0 + T_EXT + 2, 0)
box(cx - 15, cx + 15, G0, G0 + 23, bz0 + 1, bz0 + 2, GLASS_DOOR)
box(cx - 1, cx + 1, G0, G0 + 23, bz0 + 1, bz0 + 2, FRAME)

# ============================================================================
# 7. Corner blocks: SW & NE stairwells, NW & SE elevators + ice machine room
# ============================================================================
CB = T_FAC + ROOM_D                    # 48: inner size of a corner block
corner = {
    # origin = inner corner of the block next to the corridor walls; p,q axes point toward the atrium
    "SW": Frame(bx0 + T_EXT + COR_W + T_PART, bz0 + T_EXT + COR_W + T_PART, 1, 0, 0, 1),
    "NE": Frame(bx1 - T_EXT - COR_W - T_PART - 1, bz1 - T_EXT - COR_W - T_PART - 1, -1, 0, 0, -1),
    "NW": Frame(bx0 + T_EXT + COR_W + T_PART, bz1 - T_EXT - COR_W - T_PART - 1, 1, 0, 0, -1),
    "SE": Frame(bx1 - T_EXT - COR_W - T_PART - 1, bz0 + T_EXT + COR_W + T_PART, -1, 0, 0, 1),
}
# corner partition walls (corridor side) are created by the corridor frames' partition? No: build here
for key, fr in corner.items():
    fr.box(-T_PART, CB, G0, ROOF_Y - SLAB_T, -T_PART, 0, COR_WALL)
    fr.box(-T_PART, 0, G0, ROOF_Y - SLAB_T, -T_PART, CB, COR_WALL)
    # the facade corner piece (where two facade walls meet) is already solid; inner walls:
    fr.box(CB - T_FAC, CB, G0, ROOF_Y - SLAB_T, 0, CB, STAIR_WALL)
    fr.box(0, CB, G0, ROOF_Y - SLAB_T, CB - T_FAC, CB, STAIR_WALL)

def stairwell(fr):
    # p = u (perpendicular to the west/east corridor), q = v
    # clear the interior and lay floors
    for k in range(FLOORS + 1):
        y = fy(k)
        if k < FLOORS:
            fr.box(0, CB - T_FAC, y, y + FH - SLAB_T, 0, CB - T_FAC, 0)
        # slab opening: keep landing p in [0,15)
        if k > 0:
            fr.box(15, CB - T_FAC, y - SLAB_T, y, 0, CB - T_FAC, 0)
        fr.box(0, 15, y - 1, y, 0, CB - T_FAC, STAIR_CONC)
        # door from the (u-side) corridor
        if k < FLOORS:
            fr.box(-T_PART, 0, y, y + 21, 26, 36, 0)
            fr.box(-T_PART - 1, -T_PART, y + 22, y + 25, 28, 34, EXIT_SIGN)
            fr.light(4, y + 24, 22, (1.0, 0.95, 0.85), 1.6, 0.2)
            fr.box(2, 6, y + 26, y + 27, 20, 24, CEIL_LAMP)
    for k in range(FLOORS):
        y = fy(k)
        # flight A: q in [2,22), from p=12 rising 2 per 3 voxels up to +16 at p=36
        for s in range(8):
            p0 = 12 + s * 3
            fr.box(p0, p0 + 3, y + s * 2 - 2, y + s * 2 + 2, 2, 22, STAIR_CONC)
        # landing at mid height
        fr.box(36, CB - T_FAC, y + 14, y + 16, 0, CB - T_FAC, STAIR_CONC)
        # flight B: q in [24,44), from landing (+16) down toward p=15 reaching +30
        for s in range(7):
            p1 = 36 - s * 3
            top = y + 16 + (s + 1) * 2
            fr.box(p1 - 3, p1, top - 4, top, 24, 44, STAIR_CONC)
        # railings
        for p in range(12, 37, 4):
            hA = y + int((p - 12) / 3) * 2 + 1
            fr.box(p, p + 1, hA, hA + 9, 22, 23, STEEL)
            hB = y + 30 - int((p - 15) / 3) * 2 if p >= 15 else y + 30
            fr.box(p, p + 1, hB, hB + 9, 23, 24, STEEL)
        fr.box(12, 37, y + 9, y + 10, 22, 23, STEEL)
    # roof penthouse over the stairwell
    y = ROOF_Y
    fr.box(-T_PART, CB, y, y + 28, -T_PART, CB, STAIR_WALL)
    fr.box(0, CB - T_FAC, y, y + 26, 0, CB - T_FAC, 0)
    fr.box(-T_PART, CB, y + 28, y + 30, -T_PART, CB, ROOF)
    fr.box(20, 30, y, y + 21, CB - T_FAC, CB, 0)    # door onto the roof (toward atrium side)
    fr.light(10, y + 24, 10, (1.0, 0.95, 0.85), 1.6, 0.2)

def elevators(fr):
    # two shafts along the corridor wall q in [0,20), [22,42); utility room behind
    for k in range(FLOORS):
        y = fy(k)
        fr.box(0, CB - T_FAC, y, y + FH - SLAB_T, 0, CB - T_FAC, 0)
        fr.box(0, CB - T_FAC, y - 1, y, 0, CB - T_FAC, TILE_DARK)
        # shaft walls (concrete, full height)
    fr.box(0, 22, G0, ROOF_Y + 12, 0, CB - T_FAC, SLAB)
    for q0 in (2, 24):
        fr.box(0, 20, G0, ROOF_Y + 10, q0, q0 + 18, 0)        # hollow shaft through all floors
        fr.box(2, 4, G0, ROOF_Y + 10, q0 + 3, q0 + 4, ELEV_RAIL)
        fr.box(2, 4, G0, ROOF_Y + 10, q0 + 14, q0 + 15, ELEV_RAIL)
    fr.box(-T_PART, 22, ROOF_Y + 10, ROOF_Y + 14, -T_PART, CB - T_FAC, SLAB)   # machine room roof
    # elevator car parked on floor 2 in shaft A, on ground in shaft B
    for q0, kk in ((2, 2), (24, 0)):
        y = fy(kk)
        fr.box(1, 19, y - 2, y, q0 + 1, q0 + 17, DARK_METAL)
        fr.box(1, 19, y + 24, y + 25, q0 + 1, q0 + 17, DARK_METAL)
        fr.box(18, 19, y, y + 24, q0 + 1, q0 + 17, MIRROR)
        fr.box(1, 19, y, y + 24, q0 + 1, q0 + 2, ELEV_DOOR)
        fr.box(1, 19, y, y + 24, q0 + 16, q0 + 17, ELEV_DOOR)
        fr.box(8, 12, y + 23, y + 24, q0 + 7, q0 + 11, CEIL_LAMP)
        fr.box(2, 18, y - 1, y, q0 + 2, q0 + 16, COR_CARP)
    for k in range(FLOORS):
        y = fy(k)
        for q0 in (2, 24):
            # steel doors in the corridor partition (p in [-T_PART, 0))
            fr.box(-T_PART, 0, y, y + 22, q0 + 4, q0 + 14, ELEV_DOOR)
            fr.box(-T_PART - 1, -T_PART, y, y + 23, q0 + 3, q0 + 4, STEEL)
            fr.box(-T_PART - 1, -T_PART, y, y + 23, q0 + 14, q0 + 15, STEEL)
            fr.box(-T_PART - 1, -T_PART, y + 22, y + 23, q0 + 3, q0 + 15, STEEL)
            fr.box(-T_PART - 1, -T_PART, y + 24, y + 26, q0 + 7, q0 + 11, CEIL_LAMP)   # floor indicator
            fr.box(-T_PART - 1, -T_PART, y, y + 22, q0 + 8, q0 + 9 , ELEV_DOOR)
        # call button panel
        fr.box(-T_PART - 1, -T_PART, y + 10, y + 13, 21, 23, BRASS)
        # utility / ice machine room: door on the other corridor wall (q side)
        fr.box(26, 35, y, y + 21, -T_PART, 0, 0)
        fr.box(28, 44, y, y + 18, 34, 42, RADIATOR)                       # ice machine
        fr.box(29, 33, y + 12, y + 15, 33, 34, ICE_LAMP)
        fr.box(36, 43, y, y + 22, 2, 8, STEEL)                            # shelving
        for sy in range(y + 5, y + 22, 6):
            fr.box(36, 43, sy, sy + 1, 2, 8, WOOD_LIGHT)
            fr.box(37, 42, sy + 1, sy + 3, 3, 7, SHEET)                   # folded linen
        fr.box(30, 34, y + 26, y + 27, 18, 22, CEIL_LAMP)
        fr.light(32, y + 24, 20, (0.85, 0.95, 1.0), 1.2, 0.2)
    # roof machine-room box above the shafts
    y = ROOF_Y
    fr.box(-T_PART, 24, y, y + 14, -T_PART, CB - T_FAC + 2, EXT_WALL)

stairwell(corner["SW"]); stairwell(corner["NE"])
elevators(corner["NW"]); elevators(corner["SE"])

# ============================================================================
# 8. Roof details
# ============================================================================
for i in range(5):
    hx = bx0 + 20 + i * 60
    for hz in (bz0 + 14, bz1 - 34):
        if ax0 - 10 < hx < ax1 + 10 and False:
            continue
        box(hx, hx + 22, ROOF_Y, ROOF_Y + 12, hz, hz + 18, HVAC)
        box(hx + 3, hx + 19, ROOF_Y + 12, ROOF_Y + 13, hz + 3, hz + 15, DARK_METAL)
        for gx in range(hx + 2, hx + 21, 3):
            box(gx, gx + 1, ROOF_Y + 2, ROOF_Y + 10, hz - 1, hz, DARK_METAL)
# ducts running to the atrium lantern
box(ax0 - 24, ax0 - T_FAC, ROOF_Y + 2, ROOF_Y + 8, bz0 + 30, bz0 + 36, HVAC)
box(ax1 + T_FAC, ax1 + 24, ROOF_Y + 2, ROOF_Y + 8, bz1 - 36, bz1 - 30, HVAC)

# street lamps on the apron
for (sx, sz) in [(bx0 - 20, bz0 - 20), (bx1 + 18, bz0 - 20), (bx0 - 20, bz1 + 18), (bx1 + 18, bz1 + 18),
                 (bx0 - 20, (bz0 + bz1) // 2), (bx1 + 18, (bz0 + bz1) // 2)]:
    box(sx, sx + 2, G0, G0 + 50, sz, sz + 2, DARK_METAL)
    box(sx - 2, sx + 4, G0 + 50, G0 + 52, sz - 2, sz + 4, DARK_METAL)
    box(sx - 1, sx + 3, G0 + 49, G0 + 50, sz - 1, sz + 3, STREET_LMP)
    light(sx + 1, G0 + 47, sz + 1, (1.0, 0.75, 0.45), 6.0, 0.3)

# ============================================================================
# 9. Export: chunks -> .vox, main.xml
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
    mvx = xs.astype(np.uint8)
    mvy = (sz - 1 - zs).astype(np.uint8)
    mvz = ys.astype(np.uint8)
    xyzi = np.stack([mvx, mvy, mvz, cols.astype(np.uint8)], axis=1).tobytes()
    size_c = chunk(b"SIZE", struct.pack("<iii", sx, sz, sy))
    xyzi_c = chunk(b"XYZI", struct.pack("<i", len(xs)) + xyzi)
    # scene graph: root nTRN(0) -> nGRP(1) -> nTRN(2) -> nSHP(3)
    ntrn0 = chunk(b"nTRN", struct.pack("<i", 0) + vox_dict({}) + struct.pack("<iiii", 1, -1, -1, 1) + vox_dict({}))
    ngrp = chunk(b"nGRP", struct.pack("<i", 1) + vox_dict({}) + struct.pack("<ii", 1, 2))
    ntrn2 = chunk(b"nTRN", struct.pack("<i", 2) + vox_dict({"_name": "shape"}) + struct.pack("<iiii", 3, -1, 0, 1)
                  + vox_dict({"_t": "0 0 0"}))
    nshp = chunk(b"nSHP", struct.pack("<i", 3) + vox_dict({}) + struct.pack("<ii", 1, 0) + vox_dict({}))
    rgba = bytearray()
    for i in range(1, 257):
        if i in PAL:
            r, g, b_ = PAL[i][0]
        else:
            r, g, b_ = 128, 128, 128
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
    CX, CZ = (W / 2) * 0.1, (D / 2) * 0.1          # world origin at the grid centre
    CS = 128
    voxes = []
    total = 0
    for x0 in range(0, W, CS):
        for y0 in range(0, H, CS):
            for z0 in range(0, D, CS):
                sub = G[x0:x0 + CS, y0:y0 + CS, z0:z0 + CS]
                nz = np.nonzero(sub)
                if len(nz[0]) == 0:
                    continue
                # crop to the tight bounding box (so engine 'fit' never matters)
                bx_ = (nz[0].min(), nz[0].max() + 1); by_ = (nz[1].min(), nz[1].max() + 1); bz_ = (nz[2].min(), nz[2].max() + 1)
                sub = sub[bx_[0]:bx_[1], by_[0]:by_[1], bz_[0]:bz_[1]]
                gx0, gy0, gz0 = x0 + bx_[0], y0 + by_[0], z0 + bz_[0]
                sx, sy, sz = sub.shape
                name = f"c_{x0 // CS}_{y0 // CS}_{z0 // CS}"
                n = write_vox(os.path.join(VOXDIR, name + ".vox"), sub)
                total += n
                # Teardown vox origin from min corner: (floor(sx/2), 0, sz - floor(sz/2))
                ox = (gx0 + sx // 2) * 0.1 - CX
                oy = gy0 * 0.1
                oz = (gz0 + sz - sz // 2) * 0.1 - CZ
                voxes.append(dict(name=name, gmin=(gx0, gy0, gz0), size=(sx, sy, sz), pos=(ox, oy, oz), lights=[], n=n))
    # attach every light to the chunk that contains it
    def owner(gx, gy, gz):
        for v in voxes:
            (a, b, c), (sx, sy, sz) = v["gmin"], v["size"]
            if a <= gx < a + sx and b <= gy < b + sy and c <= gz < c + sz:
                return v
        return None
    loose = []
    for (gx, gy, gz, rgb, scale, size, kind) in LIGHTS:
        wx, wy, wz = gx * 0.1 - CX, gy * 0.1, gz * 0.1 - CZ
        v = owner(int(gx), int(gy), int(gz))
        if v is None:
            loose.append((wx, wy, wz, rgb, scale, size))
        else:
            v["lights"].append((wx - v["pos"][0], wy - v["pos"][1], wz - v["pos"][2], rgb, scale, size))

    def f3(a): return " ".join(f"{t:.2f}".rstrip("0").rstrip(".") if abs(t) > 1e-9 else "0" for t in a)
    def light_xml(p, rgb, scale, size, ind="\t\t\t"):
        return f'{ind}<light pos="{f3(p)}" type="sphere" color="{f3(rgb)}" scale="{scale:g}" size="{size:g}"/>\n'

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
    xml.append('\t<boundary>\n')
    for (bx_, bz_) in [(-half_w, -half_d), (half_w, -half_d), (half_w, half_d), (-half_w, half_d)]:
        xml.append(f'\t\t<vertex pos="{bx_:.1f} {bz_:.1f}"/>\n')
    xml.append('\t</boundary>\n')
    xml.append('\t<group name="liminal_atrium" pos="0 0 0">\n')
    for v in voxes:
        if v["lights"]:
            xml.append(f'\t\t<vox name="{v["name"]}" pos="{f3(v["pos"])}" file="MOD/vox/{v["name"]}.vox" object="shape">\n')
            for (lx, ly, lz, rgb, scale, size) in v["lights"]:
                xml.append(light_xml((lx, ly, lz), rgb, scale, size))
            xml.append('\t\t</vox>\n')
        else:
            xml.append(f'\t\t<vox name="{v["name"]}" pos="{f3(v["pos"])}" file="MOD/vox/{v["name"]}.vox" object="shape"/>\n')
    for (wx, wy, wz, rgb, scale, size) in loose:
        xml.append(light_xml((wx, wy, wz), rgb, scale, size, "\t\t"))
    xml.append('\t</group>\n')
    xml.append('</scene>\n')
    with open(os.path.join(OUT, "main.xml"), "w") as f:
        f.write("".join(xml))
    with open(os.path.join(OUT, "info.txt"), "w") as f:
        f.write("name = Liminal Atrium\n"
                "author = Claude\n"
                "description = A deserted hotel atrium at night. 6 floors of rooms around a purple-lit courtyard: "
                "furnished rooms, corridors, stairwells, elevator shafts and a roof. Sandbox - break everything.\n"
                "tags = Map\n")
    stats = dict(grid=[W, H, D], chunks=len(voxes), voxels=int(total), lights=len(LIGHTS),
                 rooms=len(room_log), lit=sum(1 for r in room_log if r[3].startswith("lit")),
                 tv=sum(1 for r in room_log if r[3] == "tv"))
    print(json.dumps(stats))
    return stats

if __name__ == "__main__":
    export()
    if "--save-grid" in sys.argv:
        np.save(sys.argv[sys.argv.index("--save-grid") + 1], G)
        meta = dict(W=W, H=H, D=D, ax0=ax0, ax1=ax1, az0=az0, az1=az1, bx0=bx0, bx1=bx1, bz0=bz0, bz1=bz1,
                    G0=G0, FH=FH, ATR_TOP=ATR_TOP, ROOF_Y=ROOF_Y,
                    pal={i: list(v[0]) for i, v in PAL.items()},
                    emit=[i for i, v in PAL.items() if v[1] == "emit"],
                    glass=[i for i, v in PAL.items() if v[1] == "glass"],
                    lights=[(l[0], l[1], l[2], l[3], l[4]) for l in LIGHTS])
        with open(sys.argv[sys.argv.index("--save-grid") + 1] + ".json", "w") as f:
            json.dump(meta, f)
