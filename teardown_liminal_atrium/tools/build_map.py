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
CEIL_LAMP  = P(4, (255, 238, 205), "emit", flux=2, weight=0.55)   # (v3.48: softer, less glare)
COVE_LAMP  = P(5, (220, 196, 255), "emit", flux=2, weight=0.7)
STREET_LMP = P(6, (255, 210, 150), "emit", flux=3, weight=1.0)
EXIT_SIGN  = P(7, (60, 220, 90), "emit", flux=2, weight=0.7)
TV_SCREEN  = P(8, (84, 116, 196), "emit", flux=2, weight=0.7)
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
# dreamcore pastels (dreamers + memories of the mission)
MEMORY      = P(42, (255, 170, 220), "emit", flux=2, weight=0.8)
DREAM_PINK  = P(43, (246, 188, 218))
DREAM_LILAC = P(44, (206, 190, 242))
DREAM_SKY   = P(45, (176, 214, 248))
DREAM_CLOUD = P(46, (250, 247, 253))
# basement arcade: polished stone (rock = hard) + car park paint
MARBLE_W    = P(47, (234, 231, 226), "metal", rough=0.12, metal=0.05); MARBLE_W2 = P(48, (220, 216, 209), "metal", rough=0.12, metal=0.05)
MARBLE_B    = P(49, (40, 38, 42), "metal", rough=0.12, metal=0.05)
MARBLE_BG   = P(50, (198, 184, 162), "metal", rough=0.12, metal=0.05)
YELLOW_PAINT = P(51, (226, 186, 40))
MARBLE_VEIN = P(52, (176, 172, 172), "metal", rough=0.12, metal=0.05)    # (texture pass only)
MARBLE_B2   = P(53, (58, 54, 62), "metal", rough=0.12, metal=0.05)
MARBLE_BG2  = P(54, (184, 168, 146), "metal", rough=0.12, metal=0.05)
PUDDLE      = P(55, (52, 58, 66), "metal", rough=0.02, metal=0.2)              # standing water: dark mirror
ROSE        = P(56, (212, 70, 112))                                          # glasshouse roses
# per-floor corridor themes (dirt range: soft like carpet / plaster)
CARP_G  = P(26, (52, 86, 62));  CARP_G2  = P(27, (45, 77, 55))
CARP_BL = P(28, (40, 58, 100)); CARP_BL2 = P(29, (35, 51, 89))
CARP_DK = P(30, (50, 46, 50));  CARP_DK2 = P(31, (43, 39, 43))
CARP_PK = P(32, (128, 74, 96)); CARP_PK2 = P(33, (115, 65, 86))
CARP_OR = P(34, (152, 94, 44)); CARP_OR2 = P(35, (137, 83, 39))
WALL_GREEN  = P(36, (146, 176, 134))
WALL_BLUE   = P(37, (132, 156, 196))
WALL_GREY   = P(38, (112, 108, 116))
WALL_MAUVE  = P(39, (192, 150, 170))
WALL_ORANGE = P(40, (214, 166, 112))
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
PARQUET    = P(70, (140, 98, 62), "metal", rough=0.35, metal=0.04); PARQUET2 = P(71, (126, 88, 56), "metal", rough=0.35, metal=0.04)
LOUNGER    = P(72, (234, 230, 222))
# concrete (73-88)
SLAB       = P(73, (128, 126, 122))
FLOOR_STN  = P(74, (150, 124, 96), "metal", rough=0.25, metal=0.04); FLOOR_STN2 = P(75, (142, 117, 90), "metal", rough=0.25, metal=0.04); FLOOR_STN3 = P(76, (158, 132, 103), "metal", rough=0.25, metal=0.04)
FLOOR_MED  = P(77, (196, 180, 152), "metal", rough=0.25, metal=0.04)
FLOOR_BRD  = P(78, (112, 92, 72), "metal", rough=0.25, metal=0.04)
ASPHALT    = P(79, (52, 52, 56)); ASPHALT2 = P(80, (58, 58, 62))
PAINT_LINE = P(81, (200, 198, 186))
ROOF       = P(82, (92, 92, 96)); ROOF2 = P(83, (100, 100, 104))
STAIR_CONC = P(84, (150, 148, 142), "metal", rough=0.45, metal=0.03)
TILE       = P(85, (228, 231, 231), "metal", rough=0.18, metal=0.05)
TILE_DARK  = P(86, (150, 158, 160))
CURB       = P(87, (150, 150, 145))
GROUT      = P(88, (118, 100, 80))
# brick (89-104): exterior
BRICK      = P(89, (128, 72, 58)); BRICK2 = P(90, (116, 64, 52)); BRICK3 = P(91, (138, 82, 66))
EXT_TRIM   = P(93, (176, 166, 150)); EXT_TRIM2 = P(94, (165, 156, 141))
PAVER      = P(95, (120, 116, 110)); PAVER2 = P(96, (108, 104, 99))
LINTEL     = P(97, (186, 176, 160))
GROUT_TILE = P(92, (184, 194, 198))
WHITE_TILE = P(99, (236, 240, 240), "metal", rough=0.18, metal=0.05); WHITE_TILE2 = P(100, (225, 231, 232), "metal", rough=0.18, metal=0.05)
POOL_TILE  = P(101, (122, 198, 224), "metal", rough=0.18, metal=0.05); POOL_TILE2 = P(102, (104, 182, 212), "metal", rough=0.18, metal=0.05)
POOL_LINE  = P(103, (30, 60, 124))
COPING     = P(104, (214, 208, 196), "metal", rough=0.18, metal=0.05)
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
CERAMIC    = P(164, (236, 236, 236), "metal", rough=0.18, metal=0.05)
LAMPSHADE  = P(165, (250, 226, 172), "emit", flux=2, weight=0.6)
TOWEL      = P(166, (240, 240, 236))
ART1       = P(167, (60, 92, 122)); ART2 = P(168, (172, 112, 70))
# hard metal / hard masonry
RED        = P(169, (176, 30, 30), "metal", rough=0.4, metal=0.3)
TIRE       = P(170, (24, 24, 24), "metal", rough=0.9, metal=0.0)
DUMPSTER   = P(171, (40, 82, 52), "metal", rough=0.6, metal=0.4)
POOL_LAMP  = P(172, (150, 232, 255), "emit", flux=2, weight=0.8)
BALL_R     = P(138, (150, 24, 48), "metal", rough=0.08, metal=0.25)     # bowling balls (heavy)
BALL_B     = P(139, (30, 52, 140), "metal", rough=0.08, metal=0.25)
FROST      = P(173, (214, 222, 232), "metal", rough=0.35, metal=0.0)   # smart glass, frosted
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
BASE_H = 36                          # basement B1 floor-to-floor (3.6 m)
BASE2_H = 36                         # basement B2 floor-to-floor (3.6 m, v3.46)
G0 = 4 + BASE2_H + BASE_H            # ground floor surface y
YB = G0 - BASE_H                     # basement B1 floor surface y
YB2 = YB - BASE2_H                   # basement B2 floor surface y
BED_Y = YB - 4                       # bedrock under the site (B2 and its ramp are dug deeper, see section 1)
SEAM = YB                            # world shapes are cut here: B2 + its ceiling below, everything else above (<= 256 tall)
ROOF_Y = G0 + FLOORS * FH            # 184: roof surface of the room ring
ATR_TOP = ROOF_Y + 22                # 206: atrium ceiling underside
H = ATR_TOP + 3 + 4 + 2 + 30         # + rooftop sign (every shape is still <= 256 tall)

bx0, bz0 = M, M
bx1, bz1 = M + BX, M + BZ
ax0, az0 = bx0 + T, bz0 + T
ax1, az1 = ax0 + AX, az0 + AZ
AZ0 = bz1 + 40                        # pool annex (north of the hotel)
AZ1 = AZ0 + 200
D = AZ1 + 30

G = np.zeros((W, H, D), dtype=np.uint8)
LIGHTS = []   # (gx, gy, gz, rgb, scale, size, tags)
LAMPS = []    # filled by export(): lamp shapes cut out of the world
GLOWS = []    # filled by export(): unlit light fittings on a hotel floor (own shapes, on the floor's circuit)
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

LEVELS = [-2, -1] + list(range(FLOORS + 1))  # elevator stops: B2, B1, floors 1-6 and the roof (fy(FLOORS) = ROOF_Y)
def lvl_y(k):
    return YB2 if k == -2 else YB if k == -1 else fy(k)

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
SWITCHGEAR = []    # per-floor electrical switchgear shapes (two per floor: NW + SE corner)
ELEC_ROOMS = []    # (corner frame, floor y): signs are drawn once the sign font exists
CURTAINS = []      # curtain panels (static bodies slid open / shut by main.lua)
KEYCARDS = []      # mission key cards (one per floor)
MANNEQUINS = []    # mission mannequins (static bodies moved by main.lua along a corridor)
MQ_DECOR = []      # decorative dreamer spots (rooms), placed after the rooms
DECOR_MQ = []      # decorative dreamers: static bodies, visible only during the mission
MRNG = random.Random(4242)   # separate RNG: the new features never shift the rest of the map

def mannequin_model():
    """5 wide (a) x 18 tall (b) x 3 deep (c); front is c = 0. A pastel, faceless dreamer."""
    m = np.zeros((5, 18, 3), np.uint8)
    for a in (1, 3):
        m[a, 1:9, 1] = DREAM_SKY                 # legs
        m[a, 0, 0:3] = DREAM_CLOUD               # feet
    m[1:4, 8:10, 1] = DREAM_SKY                  # hips
    m[1:4, 10:15, 0:3] = DREAM_LILAC             # torso
    m[2, 12, 0] = DREAM_PINK                     # little heart on the chest
    m[0:5, 14, 1] = DREAM_LILAC                  # shoulders
    m[0, 8:14, 1] = DREAM_LILAC; m[4, 8:14, 1] = DREAM_LILAC   # arms
    m[2, 15, 1] = DREAM_PINK                     # neck ribbon
    m[1:4, 16:18, 0:3] = DREAM_CLOUD             # head
    m[1, 16, 0] = DREAM_PINK; m[3, 16, 0] = DREAM_PINK          # blush
    return m
MQ_MODEL = mannequin_model()
CALLS = []         # landing call buttons (static shapes)

def add_door(fr, u0, u1, y0, y1, v0, v1, style, hinge=None, open_dir=None, slide=None, start_open=False, tag="hoteldoor",
             stop=WOOD_DARK):
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
    if slide is None:                    # physical swing door: leaf one row shorter than the opening,
        arr = arr[:, :-1, :]             # hung 5 cm up -> 5 cm clearance under and over it
        if stop:
            # door stop: a strip across the top of the opening on the side the door does NOT open to.
            # It hides the clearance gap when the door is shut and stops it swinging the wrong way.
            du, dv = open_dir
            fr.box(u0 - du, u1 - du, y1 - 1, y1 + 1, v0 - dv, v1 - dv, stop)   # 2 rows: also bonds to the header
    d = dict(arr=arr, gmin=(x0, y0, z0), start_open=start_open, tag=tag, yoff=0.05 if slide is None else 0.0)
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
    if b in (9, 10) and a == A - 2:
        return BRASS                                   # handle on the latch edge only
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
box(0, W, BED_Y, BED_Y + 1, 0, D, BEDROCK)
box(0, W, BED_Y + 1, G0 - 3, 0, D, SOIL)       # earth (the basement is dug into it)
# deeper earth for B2 and its ramp only (east margin): bedrock at the grid bottom there
B2_EARTH = (bx0 - 16, bx1 + 16, bz0 - 16, bz1 + 16)
box(B2_EARTH[0], B2_EARTH[1], 0, 1, B2_EARTH[2], B2_EARTH[3], BEDROCK)
box(B2_EARTH[0], B2_EARTH[1], 1, BED_Y + 1, B2_EARTH[2], B2_EARTH[3], SOIL)
box(0, W, G0 - 3, G0, 0, D, ASPHALT)
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

def tree(x, z, h=None, draw=True):
    h = h or rng.randint(42, 58)
    if draw:
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
    if not draw:
        return                                    # (the random draws still happen: the rest of the map stays put)
    canopy = keep_connected(canopy, [(R, R - 1, R)])
    ok = (X >= 0) & (X < W) & (Y >= 0) & (Y < H) & (Z >= 0) & (Z < D) & canopy
    t = hash3(X[ok], Y[ok], Z[ok], 9)
    G[X[ok], Y[ok], Z[ok]] = np.where(t < 0.4, LEAF, np.where(t < 0.75, LEAF3, LEAF2))

for z in range(bz0 + 50, bz1 - 40, 70):
    tree(bx0 - SW // 2 - 2, z); tree(bx1 + SW // 2 + 2, z)
for x in range(bx0 + 50, bx1 - 40, 70):
    tree(x, bz1 + SW // 2 + 2, draw=not (150 <= x <= 215))     # (the pool changing-room wing stands there)
# parking lot (south): bays, wheel stops
for i in range(13):
    x = bx0 - 30 + i * 30
    if abs(x - (bx0 + bx1) // 2) < 30:
        continue
    box(x, x + 1, G0 - 1, G0, 4, bz0 - SW - 4, PAINT_LINE)
    box(x + 8, x + 22, G0, G0 + 1, bz0 - SW - 9, bz0 - SW - 7, CURB)

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
# 2b. Basement B1 shell: solid block under the hotel, hollowed out. Half underground car park
#     (west / south-west, with a ramp to the street), half luxury shopping arcade (east + north).
# ============================================================================
IX0, IX1, IZ0, IZ1 = bx0 + T_EXT, bx1 - T_EXT, bz0 + T_EXT, bz1 - T_EXT   # B1 interior
YC = G0 - SLAB_T                     # B1 ceiling = underside of the ground floor slab
PX1, PZ1 = ax0 + 2 * SHORT_BAY_W, 398  # car park | arcade dividers (x = shape seam, z)
BRNG = random.Random(91)             # own RNG: the basement never shifts the rest of the map
box(bx0, bx1, 1, G0, bz0, bz1, SLAB)
box(IX0, IX1, YB, YC, IZ0, IZ1, 0)
# floors: car park = sealed concrete, arcade = polished marble checkerboard
box(IX0, PX1, YB - 1, YB, IZ0, PZ1, STAIR_CONC)
for x in range(IX0, IX1):
    for z in range(IZ0, IZ1):
        if x < PX1 + 2 and z < PZ1 + 2:
            continue
        G[x, YB - 1, z] = MARBLE_W if ((x // 6) + (z // 6)) % 2 == 0 else MARBLE_W2
# promenade: black border + gold inlay down the middle
PRM0, PRM1 = 290, 330
box(PRM0, PRM0 + 1, YB - 1, YB, IZ0, IZ1, MARBLE_B); box(PRM1 - 1, PRM1, YB - 1, YB, IZ0, IZ1, MARBLE_B)
box(PRM0 + 19, PRM0 + 21, YB - 1, YB, IZ0, IZ1, BRASS)
for z in range(IZ0 + 10, IZ1, 24):
    box(PRM0 + 1, PRM1 - 1, YB - 1, YB, z, z + 1, MARBLE_B)
# divider walls (car park side raw concrete, arcade side plaster)
box(PX1, PX1 + 2, YB, YC, IZ0, PZ1 + 2, SLAB)
box(PX1 - 2, PX1, YB, YC, IZ0, PZ1, SLAB)          # car-park facing on the other side of the x = PX1 shape seam
box(IX0, PX1 + 2, YB, YC, PZ1, PZ1 + 2, SLAB)
# arcade ceiling is painted white, the car park keeps raw concrete
paint(PX1 + 2, IX1, YC, YC + 1, IZ0, IZ1, CEIL)
paint(IX0, PX1 + 2, YC, YC + 1, PZ1 + 2, IZ1, CEIL)
paint(PX1 + 1, PX1 + 2, YB, YC, IZ0, PZ1 + 2, LOBBY_WALL)   # arcade-side face of the x divider
paint(IX0, PX1 + 2, YB, YC, PZ1 + 1, PZ1 + 2, LOBBY_WALL)   # arcade-side face of the z divider
paint(PX1 + 2, IX1, YB, YC, IZ1, IZ1 + 1, LOBBY_WALL)
paint(PX1 + 2, IX1, YB, YC, IZ0 - 1, IZ0, LOBBY_WALL)
paint(IX1, IX1 + 1, YB, YC, IZ0, IZ1, LOBBY_WALL)
paint(IX0 - 1, IX0, YB, YC, PZ1 + 2, IZ1, LOBBY_WALL)

# ---- B2 shell (v3.46/47) under B1: west half a car park right under the B1 car park (a ramp in the B1 car park
#      leads down to it: street -> B1 -> B2 on one route), east half a food street under the arcade
YC2 = YB - SLAB_T                    # B2 ceiling = underside of the B1 floor slab
QX = PX1                             # B2 divider on the x = PX1 shape seam: car park | food street
box(IX0, IX1, YB2, YC2, IZ0, IZ1, 0)
box(IX0, QX, YB2 - 1, YB2, IZ0, IZ1, STAIR_CONC)
box(QX, IX1, YB2 - 1, YB2, IZ0, IZ1, FLOOR_STN)
box(QX - 2, QX + 2, YB2, YC2, IZ0, IZ1, SLAB)
R3_X0, R3_X1 = PX1 - 50, PX1 - 2      # ramp B1 -> B2: along the x divider, in the B1 car park's east bay strip
R3_TOP, R3_BOT = 180, 360            # B1 level at z <= R3_TOP (the wide south end: room to turn), B2 level at
def ramp3_y(z):                      # z >= R3_BOT (cars come out heading north into the open north end of B2)
    if z <= R3_TOP:
        return YB
    if z >= R3_BOT:
        return YB2
    return YB - int(round((z - R3_TOP) * (YB - YB2) / (R3_BOT - R3_TOP)))

# ---- ramp from the street (south-west) down along the west side, then a tunnel into the car park
RX0, RX1 = 6, 54
RZ_TOP, RZ_BOT, RZ_END = 60, 240, 312
TZ0, TZ1 = 260, 310                  # tunnel / car park entry
def ramp_y(z):
    if z < RZ_TOP:
        return G0
    if z >= RZ_BOT:
        return YB
    return G0 - int(round((z - RZ_TOP) * (G0 - YB) / (RZ_BOT - RZ_TOP)))
box(RX0 - 2, RX0, YB - 1, G0 + 3, 58, RZ_END + 2, SLAB)          # retaining walls with a low parapet
box(RX1, RX1 + 2, YB - 1, G0 + 3, 58, RZ_END + 2, SLAB)
box(RX0 - 2, RX1 + 2, YB - 1, G0 + 3, RZ_END, RZ_END + 2, SLAB)
for z in range(56, RZ_END):
    ry = ramp_y(z)
    box(RX0, RX1, ry, G0 + 4, z, z + 1, 0)
    box(RX0, RX1, ry - 1, ry, z, z + 1, STAIR_CONC)
    if ry < G0 and (z // 3) % 2 == 0:
        box(RX0 + 2, RX1 - 2, ry - 1, ry, z, z + 1, ASPHALT2)    # anti-slip grooves
box(RX0 + 23, RX0 + 25, YB - 1, YB, RZ_BOT, RZ_END, PAINT_LINE)   # centre line at the bottom
for (wx0, wx1) in ((RX0 - 2, RX0), (RX1, RX1 + 2)):              # steel guard rail on the parapets
    for z in range(60, RZ_END + 2, 12):
        box(wx0, wx1, G0 + 3, G0 + 10, z, z + 1, STEEL)
    box(wx0, wx1, G0 + 10, G0 + 11, 60, RZ_END + 2, STEEL)
box(RX0 - 2, RX1 + 2, G0 + 10, G0 + 11, RZ_END, RZ_END + 1, STEEL)
# tunnel: lined concrete box under the sidewalk, into the building's west wall
box(RX1, IX0, YB - 1, YB + 33, TZ0 - 2, TZ1 + 2, SLAB)
box(RX1, bx0, YB, YB + 32, TZ0, TZ1, 0)                           # 3.2 m clear: vans fit
box(bx0, IX0, YB, YB + 32, TZ0, TZ1, 0)
box(RX1, IX0, YB - 1, YB, TZ0, TZ1, STAIR_CONC)
for z in range(TZ0 - 2, TZ1 + 2, 10):                             # yellow / black stripes on the face above the mouth
    paint(RX1, RX1 + 1, YB + 32, YB + 35, z, z + 5, YELLOW_PAINT, [SLAB])
    paint(RX1, RX1 + 1, YB + 32, YB + 35, z + 5, z + 10, TIRE, [SLAB])
# "P" sign by the ramp entrance (glowing letter on a blue panel, facing the street)
box(RX1, RX1 + 2, G0 + 3, G0 + 30, 61, 63, STEEL)
box(RX1, RX1 + 14, G0 + 18, G0 + 30, 60, 61, BLANKET_C)                 # (beside the ramp, not over it)
for r_, row in enumerate(["####.", "#...#", "####.", "#....", "#...."]):
    for c_, cc in enumerate(row):
        if cc == "#":
            xx = RX1 + 11 - c_ * 2
            yy = G0 + 27 - r_ * 2
            box(xx - 1, xx + 1, yy - 1, yy + 1, 59, 60, CEIL_LAMP)

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

# v3.47: the atrium as in the reference photo -- the north part is a one-storey podium with a lawn on top
# (2F level, glass balustrade along its edge); in front of it, down at the ground floor, a lounge bar
PODY = fy(1)                                  # lawn surface (= 2F floor level)
ZP = az0 + 120                                # podium front face (z): lounge z az0..ZP, podium ZP..az1
# the long cables + window-cleaning cradle (right side of the far wall, as in the photo) -- now on the lawn
box(ax0 + 21, ax0 + 22, PODY + 12, ATR_TOP, az1 - 3, az1 - 2, CABLE)
box(ax0 + 13, ax0 + 14, PODY + 12, ATR_TOP, az1 - 3, az1 - 2, CABLE)
box(ax0 + 10, ax0 + 25, PODY + 8, PODY + 9, az1 - 6, az1 - 1, STEEL)
box(ax0 + 10, ax0 + 25, PODY + 9, PODY + 12, az1 - 6, az1 - 5, STEEL)
box(ax0 + 10, ax0 + 25, PODY + 12, PODY + 13, az1 - 6, az1 - 1, STEEL)
box(ax0 + 10, ax0 + 11, PODY, PODY + 12, az1 - 6, az1 - 1, STEEL)
box(ax0 + 24, ax0 + 25, PODY, PODY + 12, az1 - 6, az1 - 1, STEEL)
box(ax0 + 12, ax0 + 15, PODY + 9, PODY + 11, az1 - 4, az1 - 2, RED)      # control box

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

for (px, pz) in [(ax0 + 10, az0 + 10), (ax1 - 10, az0 + 10)]:
    potted_plant(px, pz)

# luggage cart (dynamic prop) by the lobby doors
PROPS.append(("luggage_cart", ax1 - 34, G0, az0 + 26, 15))

# ---- the podium: slab on columns over a store room, lawn on top, glass balustrade on its edge
ARNG = random.Random(4747)
box(ax0, ax1, G0, PODY, ZP, az1, SLAB)
box(ax0, ax1, G0, PODY - SLAB_T, ZP + 3, az1, 0)                         # the room under the lawn (bowling)
box(ax0, ax1, G0 - 1, G0, ZP + 3, az1, STAIR_CONC)
for cx_ in (ax0 + 40, ax0 + 80, ax0 + 120):
    for cz_ in (ZP + 50, ZP + 100):
        box(cx_ - 2, cx_ + 2, G0, PODY - SLAB_T, cz_ - 2, cz_ + 2, SLAB)
LZ = np.arange(ZP, az1)
for x in range(ax0, ax1):                                                 # artificial lawn (a little mottled)
    t_ = hash3(np.full(len(LZ), x), np.full(len(LZ), PODY), LZ, 47)
    G[x, PODY - 1, ZP:az1] = np.where(t_ < 0.12, LEAF3, LAWN)
box(ax0 + 16, ax1, PODY, PODY + 1, ZP, ZP + 1, STEEL)                     # balustrade: steel shoe, glass, cap rail
box(ax0 + 16, ax1, PODY + 1, PODY + 10, ZP, ZP + 1, GLASS)
box(ax0 + 16, ax1, PODY + 10, PODY + 11, ZP, ZP + 1, STEEL)
for x in range(ax0 + 22, ax1, 24):                                        # little lamps along its foot (as in the photo)
    box(x, x + 2, PODY, PODY + 1, ZP + 1, ZP + 2, STREET_LMP)
# front face of the podium = the lounge's back wall: dark grey fabric panels with slim joints
paint(ax0, ax1, G0, PODY, ZP, ZP + 1, WALL_GREY)
for x in range(ax0 + 20, ax1, 20):
    paint(x, x + 1, G0, PODY - 2, ZP, ZP + 1, UPHOL)
paint(ax0, ax1, G0, G0 + 1, ZP, ZP + 1, TIRE)                             # shadow-gap skirting
paint(ax0, ax1, PODY - 2, PODY, ZP, ZP + 1, EXT_TRIM)                     # slab edge
# wooden door into the store room (left of centre, as in the photo), steel trim, staff plate
DX0 = ax0 + 20
box(DX0, DX0 + 10, G0, G0 + 22, ZP, ZP + 3, 0)
box(DX0 - 1, DX0, G0, G0 + 23, ZP - 1, ZP, DARK_METAL); box(DX0 + 10, DX0 + 11, G0, G0 + 23, ZP - 1, ZP, DARK_METAL)
box(DX0 - 1, DX0 + 11, G0 + 22, G0 + 23, ZP - 1, ZP, DARK_METAL)
add_door(WORLD, DX0, DX0 + 10, G0, G0 + 22, ZP + 1, ZP + 2, wood_door, hinge=(DX0, ZP + 2), open_dir=(0, 1),
         tag="hoteldoor staff", stop=DARK_METAL)
box(DX0 + 12, DX0 + 16, G0 + 12, G0 + 15, ZP - 1, ZP, BRASS)
# (under the lawn: a bowling alley -- section 8f, after the fonts and helpers it uses)
# ---- stair up to the lawn along the west wall, glass balustrade on its open side
for k_ in range(15):
    z_ = ZP - 45 + 3 * k_
    box(ax0, ax0 + 16, G0, G0 + 2 * (k_ + 1), z_, z_ + 3, FLOOR_BRD)
    box(ax0, ax0 + 16, G0 + 2 * k_ + 1, G0 + 2 * (k_ + 1), z_, z_ + 1, MARBLE_W)     # light nosing
    box(ax0 + 16, ax0 + 17, G0 + 2 * (k_ + 1), G0 + 2 * (k_ + 1) + 10, z_, z_ + 3, GLASS)
    box(ax0 + 16, ax0 + 17, G0 + 2 * (k_ + 1) + 10, G0 + 2 * (k_ + 1) + 11, z_, z_ + 3, STEEL)
    box(ax0 + 16, ax0 + 17, G0, G0 + 2 * (k_ + 1), z_, z_ + 3, WALL_GREY)
# ---- the lounge floor: charcoal carpet with a lattice; polished dark stone around the bar
BAR_X0, BAR_X1, BAR_Z0 = ax1 - 66, ax1 - 4, ZP - 38                      # bar counter (front line z BAR_Z0)
for x in range(ax0, ax1):
    for z in range(az0, ZP):
        if x >= BAR_X0 - 8 and z >= BAR_Z0 - 10:
            c_ = MARBLE_B2 if ((x // 6) + (z // 6)) % 2 else MARBLE_B
        else:
            d1, d2 = (x + z) % 16, (x - z) % 16
            c_ = CARP_BL2 if (d1 == 0 or d2 == 0) else (CARP_DK if ((x // 4) + (z // 4)) % 2 else CARP_B)
        G[x, G0 - 1, z] = c_
# ---- the bar: black gloss counter with a rounded end, gold LED lines, stools; back bar, big neon screen
bar = np.zeros((ax1 - ax0, ZP - az0), bool)
for x in range(BAR_X0, BAR_X1):
    for z in range(BAR_Z0, BAR_Z0 + 8):
        bar[x - ax0, z - az0] = True
for x in range(BAR_X0, BAR_X0 + 8):
    for z in range(BAR_Z0, ZP - 14):
        bar[x - ax0, z - az0] = True
for x in range(BAR_X0, BAR_X0 + 8):                                        # round the outer corner
    for z in range(BAR_Z0, BAR_Z0 + 8):
        if (x + 0.5 - (BAR_X0 + 8)) ** 2 + (z + 0.5 - (BAR_Z0 + 8)) ** 2 > 64:
            bar[x - ax0, z - az0] = False
for (x, z) in zip(*np.nonzero(bar)):
    box(ax0 + x, ax0 + x + 1, G0, G0 + 11, az0 + z, az0 + z + 1, MARBLE_B)
    box(ax0 + x, ax0 + x + 1, G0 + 11, G0 + 12, az0 + z, az0 + z + 1, MARBLE_B2)
edge_ = [(x, z) for (x, z) in zip(*np.nonzero(bar)) if not bar[x, z - 1] or not bar[x - 1, z]]   # the guest side
for (x, z) in edge_:
    gx_, gz_ = ax0 + x, az0 + z
    ox, oz = (gx_, gz_ - 1) if not bar[x, z - 1] else (gx_ - 1, gz_)
    if G[ox, G0, oz] == 0:
        box(ox, ox + 1, G0 + 1, G0 + 2, oz, oz + 1, STREET_LMP)               # LED line at the foot
        box(ox, ox + 1, G0 + 9, G0 + 10, oz, oz + 1, STREET_LMP)              # LED line under the top
        box(ox, ox + 1, G0 + 11, G0 + 12, oz, oz + 1, MARBLE_B2)              # top overhang
for lx_ in (BAR_X0 + 14, BAR_X0 + 34, BAR_X0 + 54):
    light(lx_ + 0.5, G0 + 3, BAR_Z0 - 3.5, (1.0, 0.72, 0.35), 0.9, 0.15)
for sx_ in range(BAR_X0 + 12, BAR_X1 - 2, 8):                              # stools
    box(sx_, sx_ + 1, G0, G0 + 8, BAR_Z0 - 4, BAR_Z0 - 3, CHROME)
    box(sx_ - 1, sx_ + 2, G0, G0 + 1, BAR_Z0 - 5, BAR_Z0 - 2, CHROME)
    box(sx_ - 1, sx_ + 2, G0 + 8, G0 + 9, BAR_Z0 - 5, BAR_Z0 - 2, TV_BODY)
    box(sx_ - 1, sx_ + 2, G0 + 4, G0 + 5, BAR_Z0 - 3, BAR_Z0 - 2, CHROME)
box(BAR_X0 + 2, BAR_X1, G0, G0 + 10, ZP - 6, ZP, MARBLE_B)                   # back bar
box(BAR_X0 + 2, BAR_X1, G0 + 10, G0 + 11, ZP - 6, ZP, STEEL)
for bx_ in range(BAR_X0 + 4, BAR_X1 - 2, 3):                               # bottles + coffee machine
    box(bx_, bx_ + 1, G0 + 11, G0 + 13 + ARNG.randint(0, 2), ZP - 4, ZP - 3, ARNG.choice((GLASS_DOOR, BRASS, CAR_C, DUMPSTER, GLASS)))
box(BAR_X0 + 40, BAR_X0 + 46, G0 + 11, G0 + 16, ZP - 5, ZP - 1, CHROME)
box(BAR_X0 + 6, BAR_X1 - 6, G0 + 14, G0 + 15, ZP - 3, ZP, DARK_METAL)        # shelf
SCR = (BAR_X0 + 6, BAR_X1 - 6, G0 + 16, G0 + 28)
box(SCR[0], SCR[1], SCR[2], SCR[3], ZP - 2, ZP, TV_BODY)
for k_ in range(9):                                                        # cyan light-trail art on the screen
    px_, py_ = ARNG.uniform(SCR[0] + 2, SCR[1] - 2), ARNG.uniform(SCR[2] + 2, SCR[3] - 2)
    ang = ARNG.uniform(0, 6.28)
    for st_ in range(40):
        ang += ARNG.uniform(-0.5, 0.5)
        px_ = min(max(px_ + np.cos(ang) * 0.8, SCR[0] + 1), SCR[1] - 2)
        py_ = min(max(py_ + np.sin(ang) * 0.5, SCR[2] + 1), SCR[3] - 2)
        G[int(px_), int(py_), ZP - 3] = POOL_LAMP
        G[int(px_), int(py_), ZP - 2] = POOL_LAMP
light((SCR[0] + SCR[1]) / 2, (SCR[2] + SCR[3]) / 2, ZP - 6, (0.35, 0.85, 1.0), 1.2, 0.3)
# tall cylinder sconces on the wall (patterned paper shades), on short steel arms
SCONCES = []                    # own lamp shapes (with their light) -> ROOF_SHAPES: one shot sconce goes dark alone
def sconce(cx, cz=ZP - 5, y0=G0 + 12, h=11, r=2.6):
    a_ = np.zeros((7, h, 7), np.uint8)
    for y in range(h):
        for i in range(7):
            for j in range(7):
                d_ = ((i + 0.5 - 3.5) ** 2 + (j + 0.5 - 3.5) ** 2) ** 0.5
                if r - 1.1 < d_ <= r:
                    a_[i, y, j] = CURT_LIT2 if ((i + j + y) % 5 == 0 or y in (0, h - 1)) else LAMPSHADE
    gm_ = (cx - 3, y0, cz - 3)
    zb_ = cz - 3 + int(np.nonzero(a_[3, h - 2, :])[0].max()) + 1    # steel arm from the shade's back to the wall
    box(cx, cx + 1, y0 + h - 2, y0 + h - 1, zb_, ZP, DARK_METAL)
    SCONCES.append((f"sconce{len(SCONCES)}", a_, gm_, [(cx, y0 + h / 2, cz, (1.0, 0.8, 0.5), 1.3, 0.2)]))
for sx_ in (DX0 + 14, DX0 + 30, DX0 + 59):
    sconce(sx_)
# sofas against the wall with patterned cushions, a grey canopy shelf over each, round tables, tub chairs
def sofa(x0, x1):
    box(x0, x1, G0, G0 + 4, ZP - 14, ZP - 6, UPHOL)
    box(x0, x1, G0 + 4, G0 + 5, ZP - 13, ZP - 7, UPHOL2)
    box(x0, x1, G0 + 4, G0 + 11, ZP - 7, ZP - 5, UPHOL)
    for xa in (x0, x1 - 2):
        box(xa, xa + 2, G0 + 4, G0 + 8, ZP - 14, ZP - 6, UPHOL)
    for k_, cx_ in enumerate(range(x0 + 3, x1 - 5, 6)):
        box(cx_, cx_ + 4, G0 + 5, G0 + 9, ZP - 9, ZP - 7, PILLOW if k_ % 2 else RUG_BRD)
    box(x0 - 2, x1 + 2, G0 + 25, G0 + 26, ZP - 9, ZP, HVAC)                  # canopy shelf
def tub_chair(cx, cz):
    for x in range(cx - 3, cx + 4):
        for z in range(cz - 3, cz + 4):
            d_ = ((x + 0.5 - cx - 0.5) ** 2 + (z + 0.5 - cz - 0.5) ** 2) ** 0.5
            if d_ <= 3.2:
                box(x, x + 1, G0 + 1, G0 + 4, z, z + 1, UPHOL)
                if d_ > 2.0 and z <= cz:
                    box(x, x + 1, G0 + 4, G0 + 8, z, z + 1, UPHOL)
    box(cx - 1, cx + 2, G0, G0 + 1, cz - 1, cz + 2, DARK_METAL)
def round_table(cx, cz, r=4):
    for x in range(cx - r, cx + r + 1):
        for z in range(cz - r, cz + r + 1):
            if (x - cx) ** 2 + (z - cz) ** 2 <= r * r:
                box(x, x + 1, G0 + 6, G0 + 7, z, z + 1, CARP_DK)
    box(cx, cx + 1, G0, G0 + 6, cz, cz + 1, DARK_METAL)
    box(cx - 2, cx + 3, G0, G0 + 1, cz - 2, cz + 3, DARK_METAL)
for (x0_, x1_) in ((DX0 + 19, DX0 + 42), (DX0 + 47, DX0 + 71)):
    sofa(x0_, x1_)
    tc_ = (x0_ + x1_) // 2
    if abs(tc_ - (ax0 + 2 * SHORT_BAY_W)) <= 5:                       # (keep it off the x = 236 shape seam)
        tc_ = ax0 + 2 * SHORT_BAY_W + 5
    round_table(tc_, ZP - 24)
    tub_chair((x0_ + x1_) // 2 - 8, ZP - 34); tub_chair((x0_ + x1_) // 2 + 6, ZP - 34)
for (tx_, tz_) in ((ax0 + 60, az0 + 60), (ax0 + 40, az0 + 80)):              # a couple of café tables in the middle
    round_table(tx_, tz_, r=3)
    tub_chair(tx_ - 7, tz_ - 1); tub_chair(tx_ + 6, tz_ - 1)
ATRIUM = dict(pody=PODY, zp=ZP, door=(DX0, DX0 + 10), bar=(BAR_X0, BAR_X1, BAR_Z0), stair=(ax0, ax0 + 16, ZP - 45))

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

ROOM_SWITCHES = []   # per-room light switch shapes: (arr, gmin, room id, lights on, tv on)
ROOM_NSTANDS = {}    # room id -> number of bedside lamps

def curtains(fr, u0, y, state, rid=-1):
    """two curtain panels per window: separate static bodies that main.lua slides open / shut (E)."""
    cu0, cu1 = u0 - 2, u0 + WIN_W + 2
    mid = (cu0 + cu1) // 2
    top, bot = y + SILL + WIN_H + 3, y + SILL - 3
    fr.box(cu0 - 6, cu1 + 6, top, top + 1, 1, 3, BRASS)          # rod (long enough for the open panels)
    fr.box(cu0 - 6, cu0 - 5, top, top + 1, 0, 3, BRASS)          # end brackets to the window wall
    fr.box(cu1 + 5, cu1 + 6, top, top + 1, 0, 3, BRASS)
    if state == "dark_blinds":
        for yy in range(y + SILL + 1, y + SILL + WIN_H - 1, 2):
            fr.box(u0 - 1, u0 + WIN_W + 1, yy, yy + 1, 0, 1, SWITCH)
    lit = state.startswith("lit")
    ca, cb = (CURT_LIT, CURT_LIT2) if lit else (CURT_DARK, CURT_DARK2)
    start_open = not state.endswith("closed")
    cid = len(CURTAINS) // 2
    for (s0, s1, du) in ((cu0, mid, -6), (mid, cu1, 6)):
        def style(a_, b_, c_, A, B, C, s0=s0):
            if c_ == 1:
                return cb                                          # back layer (continuous)
            return ca if ((s0 + a_) // 2) % 2 == 0 else 0          # front folds
        arr, gmin = frame_shape(fr, s0, s1, bot, top, 1, 3, style)
        slide = (fr.ux * du, fr.uz * du)
        CURTAINS.append(dict(arr=arr, gmin=gmin, slide=slide, start_open=start_open, cid=cid, rid=rid, lit=lit))

def wall_art(fr, u_face, y0, v0, w, h, along_v=True, plane=None):
    """picture on a wall plane. u_face: the wall layer (u) to hang on, v0..v0+w along v."""
    fr.box(u_face, u_face + 1, y0, y0 + h, v0, v0 + w, PICFRAME)
    cols = rng.choice([(ART1, ART2, CEIL), (ART2, BLANKET_A, ART1), (LEAF, ART1, CEIL), (BLANKET_B, ART2, BLANKET_A)])
    for yy in range(y0 + 1, y0 + h - 1):
        for vv in range(v0 + 1, v0 + w - 1):
            t = ((yy - y0) * 3 + (vv - v0) * 2 + rng.randint(0, 2)) // max(1, (h + w) // 3)
            fr.box(u_face, u_face + 1, yy, yy + 1, vv, vv + 1, cols[t % 3])

def furnish_room(fr, bw, k, state, twin, blanket, carpet, keycard=False, rid=0, door=True):
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
        fr.box(U1 - 4, U1 - 1, y + 9, y + 12, nv, nv + 3, LAMPSHADE)
        fr.box(U1 - 3, U1 - 2, y + 10, y + 11, nv + 1, nv + 2, 0)            # hollow: the bulb lives here
    fr.box(U1 - 5, U1 - 3, y + 6, y + 7, stands[0][0] + 2, stands[0][0] + 4, TV_BODY)   # phone
    for (nv, nw) in stands:                                                   # every bedside lamp has its own bulb
        fr.light(U1 - 3, y + 10.5, nv + 1, (1.0, 0.78, 0.45), 1.6, 0.1, f"room={rid} rl=lamp")
    ROOM_NSTANDS[rid] = len(stands)
    # art above the bed(s)
    wall_art(fr, U1 - 1 + 1, y + 16, beds[0][0] + (1 if not twin else 4), 14, 7)
    # ---- desk + TV + mirror on the opposite wall (u = U0)
    fr.box(U0, U0 + 6, y + 7, y + 8, 13, 30, WOOD_MED)
    fr.box(U0, U0 + 6, y, y + 7, 13, 14, WOOD_MED)
    fr.box(U0, U0 + 6, y, y + 7, 29, 30, WOOD_MED)
    fr.box(U0, U0 + 5, y + 1, y + 7, 24, 29, FRIDGE)                          # minibar
    fr.box(U0 + 5, U0 + 6, y + 4, y + 5, 25, 28, CHROME)
    fr.box(U0, U0 + 1, y + 10, y + 19, 15, 28, TV_BODY)
    fr.box(U0 + 1, U0 + 2, y + 11, y + 18, 16, 27, TV_SCREEN)
    fr.box(U0, U0 + 3, y + 8, y + 10, 20, 23, TV_BODY)                        # stand (touches the TV)
    fr.light(U0 + 3, y + 14, 21.5, (0.45, 0.6, 1.0), 1.0, 0.2, f"room={rid} rl=tv")
    fr.box(U0 + 2, U0 + 4, y + 8, y + 9, 14, 17, CERAMIC)                     # kettle tray
    if keycard:                                                               # mission memory on the desk
        arr, gmin = frame_shape(fr, U0 + 3, U0 + 6, y + 8, y + 9, 26, 28,
                                lambda a_, b_, c_, A, B, C: DREAM_CLOUD if a_ == 1 else MEMORY)
        KEYCARDS.append(dict(arr=arr, gmin=gmin, floor=k))
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
    add_door(fr, bu0b, bu0b + 1, y, y + 22, v0b + 2, v0b + 10, lambda a, b, c, A, B, C: wood_door(c, b, a, C, B, A),
             hinge=(bu0b, v0b + 2), open_dir=(-1, 0), start_open=rng.random() < 0.6)
    fr.box(bu0b, bu0b + 1, y + 22, y + 23, v0b + 1, v0b + 11, WOOD_DARK)
    fr.box(bu0b + 1, U1, y - 1, y, v0b + 1, ROOM_D, TILE)
    for uu in range(bu0b + 1, U1, 3):                                           # floor tile grout
        fr.box(uu, uu + 1, y - 1, y, v0b + 1, ROOM_D, TILE_DARK)
    fr.box(bu0b + 1, U1, y, y + 12, ROOM_D - 1, ROOM_D, TILE)
    fr.box(U1 - 1, U1, y, y + 12, v0b + 1, ROOM_D, TILE)
    fr.box(bu0b + 1, U1, y + 12, y + 13, ROOM_D - 1, ROOM_D, TILE_DARK)
    fr.box(U1 - 1, U1, y + 12, y + 13, v0b + 1, ROOM_D, TILE_DARK)
    # layout keeps a free standing area (~0.7 x 0.8 m) in front of the door
    # toilet (against the u = U1 wall, near the door)
    fr.box(U1 - 4, U1 - 1, y, y + 4, v0b + 2, v0b + 6, CERAMIC)
    fr.box(U1 - 3, U1 - 2, y + 3, y + 4, v0b + 3, v0b + 5, 0)
    fr.box(U1 - 2, U1, y + 4, y + 10, v0b + 2, v0b + 6, CERAMIC)
    fr.box(U1 - 1, U1, y + 7, y + 8, v0b + 7, v0b + 9, CHROME)                  # paper holder
    fr.box(U1 - 2, U1 - 1, y + 6, y + 8, v0b + 7, v0b + 9, TOWEL)
    # walk-in shower in the far corner: tiled tray, low curb, head on the wall, curtain on a rod
    fr.box(U1 - 6, U1 - 1, y - 1, y, ROOM_D - 7, ROOM_D - 1, TILE_DARK)
    fr.box(U1 - 6, U1 - 1, y, y + 1, ROOM_D - 7, ROOM_D - 6, CERAMIC)            # curb
    fr.box(U1 - 6, U1 - 5, y, y + 1, ROOM_D - 7, ROOM_D - 1, CERAMIC)
    fr.box(U1 - 3, U1 - 2, y + 18, y + 22, ROOM_D - 1, ROOM_D, CHROME)           # shower head (on the wall)
    fr.box(U1 - 3, U1 - 2, y + 22, y + 23, ROOM_D - 2, ROOM_D, CHROME)
    fr.box(U1 - 6, U1 - 1, y + 23, y + 24, ROOM_D - 7, ROOM_D - 6, CHROME)       # curtain rod
    fr.box(U1 - 6, U1 - 5, y + 1, y + 23, ROOM_D - 7, ROOM_D - 6, CHROME)        # corner post (stands on the curb)
    fr.box(U1 - 6, U1 - 4, y + 8, y + 23, ROOM_D - 7, ROOM_D - 6, TOWEL)         # curtain, pulled aside
    # vanity on the back wall next to the shower, mirror above it
    fr.box(bu0b + 1, bu0b + 6, y, y + 9, ROOM_D - 4, ROOM_D - 1, WOOD_DARK)
    fr.box(bu0b + 1, bu0b + 6, y + 9, y + 10, ROOM_D - 5, ROOM_D - 1, CERAMIC)
    fr.box(bu0b + 2, bu0b + 5, y + 9, y + 10, ROOM_D - 4, ROOM_D - 2, 0)        # basin
    fr.box(bu0b + 3, bu0b + 4, y + 10, y + 12, ROOM_D - 2, ROOM_D - 1, CHROME)  # faucet
    fr.box(bu0b + 1, bu0b + 6, y + 13, y + 22, ROOM_D - 1, ROOM_D, MIRROR)
    # towels on a bar on the bathroom's front wall
    fr.box(bu0b + 5, bu0b + 10, y + 15, y + 16, v0b + 1, v0b + 2, CHROME)
    fr.box(bu0b + 6, bu0b + 9, y + 9, y + 15, v0b + 1, v0b + 2, TOWEL)
    fr.box(bu0b + 3, bu0b + 8, y, y + 1, v0b + 5, v0b + 8, BATHMAT)
    fr.box(bu0b + 5, bu0b + 8, y + 26, y + 27, v0b + 5, v0b + 8, CEIL_LAMP)
    fr.light(bu0b + 6, y + 24.5, v0b + 6, (1.0, 0.92, 0.8), 1.0, 0.15, f"room={rid} rl=bath")
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
    if door:
        room_door(fr, du0, y)
    else:
        rng.random()                              # (same random draws as with a door: the rest of the map stays put)
    # light switch beside the entrance, on the bathroom wall (separate shape: E toggles the room's lights)
    sarr, smin = frame_shape(fr, bu0b - 1, bu0b, y + 11, y + 14, ROOM_D - 2, ROOM_D,
                             lambda a_, b_, c_, A, B, C: DARK_METAL if (b_ == 1 and c_ == 0) else SWITCH)
    ROOM_SWITCHES.append((sarr, smin, rid, lit, state == "tv"))
    fr.box(du0 - 3, du0 - 2, y + 15, y + 17, ROOM_D - 1, ROOM_D, SWITCH)         # thermostat
    if door:
        room_door_clutter(fr, du0, y)
    else:
        rng.random()
    room_ceiling(fr, U0, U1, y, rid)

def room_door(fr, du0, y, plate=BRASS):
    fr.box(du0, du0 + 9, y, y + 22, ROOM_D, ROOM_D + T_PART, 0)
    fr.box(du0 - 1, du0 + 10, y + 22, y + 23, ROOM_D, ROOM_D + T_PART + 1, WOOD_DARK)
    fr.box(du0 - 1, du0, y, y + 22, ROOM_D + T_PART, ROOM_D + T_PART + 1, WOOD_DARK)
    fr.box(du0 + 9, du0 + 10, y, y + 22, ROOM_D + T_PART, ROOM_D + T_PART + 1, WOOD_DARK)
    fr.box(du0, du0 + 9, y - 1, y, ROOM_D, ROOM_D + T_PART, WOOD_DARK)          # threshold
    # real door leaf in the room-side layer of the partition, hinged on the wardrobe side, opens inward
    add_door(fr, du0, du0 + 9, y, y + 22, ROOM_D, ROOM_D + 1, wood_door,
             hinge=(du0, ROOM_D), open_dir=(0, -1), start_open=rng.random() < 0.25)
    fr.box(du0 + 11, du0 + 14, y + 15, y + 17, ROOM_D + T_PART, ROOM_D + T_PART + 1, plate)   # number plate

def room_door_clutter(fr, du0, y):
    # corridor-side clutter: room service tray / do-not-disturb sign
    r = rng.random()
    if r < 0.15:
        fr.box(du0 + 1, du0 + 7, y, y + 1, ROOM_D + T_PART, ROOM_D + T_PART + 4, STEEL)
        fr.box(du0 + 2, du0 + 4, y + 1, y + 2, ROOM_D + T_PART + 1, ROOM_D + T_PART + 3, CERAMIC)
        fr.box(du0 + 5, du0 + 6, y + 1, y + 3, ROOM_D + T_PART + 1, ROOM_D + T_PART + 2, GLASS_DOOR)

def room_ceiling(fr, U0, U1, y, rid):
    # ceiling: fixture, smoke detector, AC grille
    cu = (U0 + U1) // 2
    fr.box(cu - 2, cu + 2, y + FH - SLAB_T - 1, y + FH - SLAB_T, 18, 22, CEIL_LAMP)
    fr.box(cu - 3, cu + 3, y + FH - SLAB_T - 1, y + FH - SLAB_T, 17, 18, BRASS)
    fr.box(cu, cu + 1, y + FH - SLAB_T - 1, y + FH - SLAB_T, 30, 31, SWITCH)
    fr.box(U0 + 9, U0 + 17, y + FH - SLAB_T - 1, y + FH - SLAB_T, ROOM_D - 5, ROOM_D - 2, HVAC)
    fr.light(cu, y + FH - SLAB_T - 2, 20, (1.0, 0.82, 0.55), 2.2, 0.3, f"room={rid} rl=ceil")


# ---- 6F suites (v3.50): bays joined into 2-room (bedroom + living) and 3-room (+ dining) suites. Each bay
#      stays a "room" for the light switches; the suite's only door to the corridor is in its living room.
SUITES = {"W": [(0, 1), (2, 3, 4), (6, 7)], "E": [(0, 1), (2, 3, 4), (6, 7)], "S": [(0, 1)], "N": [(0, 1)]}
SUITE_ROLE = {}                                     # (side, bay) -> (suite no, role)
_sn = 0
for side_ in "WESN":
    for grp_ in SUITES[side_]:
        _sn += 1
        for j_, b_ in enumerate(grp_):
            SUITE_ROLE[(side_, b_)] = (_sn, ("bedroom", "living", "dining")[j_], len(grp_))
SUITE_LOG = {}                                      # room id -> (suite no, role, size)

def furnish_suite(fr, bw, k, role, carpet, keycard, rid):
    """the living room or dining room bay of a suite (frame u from the previous bay's side)."""
    y = fy(k)
    U0, U1 = T_PART, bw
    fr.box(U0, U1, y - 1, y, 0, ROOM_D, carpet)
    for (x0_, x1_, v0_, v1_) in ((U0 + 4, U1 - 4, 6, ROOM_D - 8),):              # a big rug
        fr.box(x0_, x1_, y - 1, y, v0_, v1_, RUG_BRD); fr.box(x0_ + 1, x1_ - 1, y - 1, y, v0_ + 1, v1_ - 1, RUG)
    fr.paint(U0 - 1, U0, y, y + 1, 0, ROOM_D, WOOD_DARK, WALLS_ROOM)
    fr.paint(U1, U1 + 1, y, y + 1, 0, ROOM_D, WOOD_DARK, WALLS_ROOM)
    fr.box(bw // 2 - 8, bw // 2 + 9, y + 1, y + 6, 0, 2, RADIATOR)
    fr.box(0, T_PART, y, y + 22, 4, 13, 0)                                          # opening to the previous room
    fr.box(0, T_PART, y + 22, y + 23, 3, 14, WOOD_DARK)
    lamps_ = 0
    if role == "living":
        fr.box(U0, U0 + 5, y, y + 5, 17, 33, WOOD_DARK)                             # media console + TV
        fr.box(U0, U0 + 1, y + 9, y + 19, 18, 32, TV_BODY)
        fr.box(U0 + 1, U0 + 2, y + 10, y + 18, 19, 31, TV_SCREEN)
        fr.box(U0, U0 + 3, y + 5, y + 9, 24, 26, TV_BODY)
        fr.light(U0 + 3, y + 14, 25.5, (0.45, 0.6, 1.0), 1.0, 0.2, f"room={rid} rl=tv")
        so0 = U1 - 7                                                                  # sofa facing the TV
        fr.box(so0, U1, y, y + 4, 15, 36, UPHOL)
        fr.box(U1 - 2, U1, y + 4, y + 10, 15, 36, UPHOL)
        fr.box(so0, U1, y + 4, y + 7, 15, 17, UPHOL); fr.box(so0, U1, y + 4, y + 7, 34, 36, UPHOL)
        for cv in (19, 25, 31):
            fr.box(so0 + 1, so0 + 5, y + 4, y + 5, cv - 2, cv + 2, UPHOL2)
            fr.box(U1 - 3, U1 - 2, y + 5, y + 8, cv - 1, cv + 1, PILLOW)
        fr.box(bw // 2 - 4, bw // 2 + 3, y + 3, y + 4, 20, 30, MARBLE_W)            # coffee table
        fr.box(bw // 2 - 4, bw // 2 + 3, y, y + 3, 24, 26, BRASS)
        fr.box(bw // 2 - 1, bw // 2 + 1, y + 4, y + 6, 24, 26, LEAF2)                 # (flowers)
        fr.box(bw // 2 - 3, bw // 2 + 3, y, y + 4, 5, 10, UPHOL2)                     # armchair by the window
        fr.box(bw // 2 - 3, bw // 2 + 3, y + 4, y + 9, 5, 6, UPHOL2)
        fr.box(U1 - 3, U1 - 2, y, y + 13, 39, 40, BRASS)                              # floor lamp
        fr.box(U1 - 4, U1 - 1, y + 13, y + 16, 38, 41, LAMPSHADE)
        fr.light(U1 - 1, y + 12, 39, (1.0, 0.78, 0.45), 1.4, 0.15, f"room={rid} rl=lamp")
        lamps_ = 1
        fr.box(U0 + 19, U1 - 6, y, y + 9, ROOM_D - 5, ROOM_D, WOOD_DARK)            # bar counter + glasses
        fr.box(U0 + 18, U1 - 6, y + 9, y + 10, ROOM_D - 6, ROOM_D, MARBLE_B)
        for gu in range(U0 + 20, U1 - 7, 2):
            fr.box(gu, gu + 1, y + 10, y + 12, ROOM_D - 2, ROOM_D - 1, GLASS_DOOR)
        du0 = U0 + 8
        room_door(fr, du0, y, plate=COR_GOLD)                                        # the suite's own door
        fr.box(du0 + 11, du0 + 16, y + 13, y + 19, ROOM_D + T_PART, ROOM_D + T_PART + 1, BRASS)  # SUITE plate
        sw_u = du0 + 10
        sarr, smin = frame_shape(fr, sw_u, sw_u + 1, y + 11, y + 14, ROOM_D - 1, ROOM_D,
                                 lambda a_, b_, c_, A, B, C: DARK_METAL if b_ == 1 else SWITCH)
        if keycard:
            arr, gmin = frame_shape(fr, bw // 2 - 2, bw // 2 + 1, y + 4, y + 5, 21, 23,
                                    lambda a_, b_, c_, A, B, C: DREAM_CLOUD if a_ == 1 else MEMORY)
            KEYCARDS.append(dict(arr=arr, gmin=gmin, floor=k))
    else:                                                                             # dining room + study corner
        tu0, tu1 = bw // 2 - 8, bw // 2 + 8
        fr.box(tu0, tu1, y + 7, y + 8, 16, 28, WOOD_DARK)
        for (lu, lv) in ((tu0 + 1, 17), (tu1 - 2, 17), (tu0 + 1, 26), (tu1 - 2, 26)):
            fr.box(lu, lu + 1, y, y + 7, lv, lv + 1, WOOD_DARK)
        for cu_ in (tu0 + 2, bw // 2 - 2, tu1 - 6):
            for (cv0, back) in ((12, 12), (29, 31)):
                fr.box(cu_, cu_ + 4, y + 4, y + 5, cv0, cv0 + 3, UPHOL2)
                fr.box(cu_, cu_ + 4, y + 5, y + 11, back, back + 1, WOOD_DARK)
                for (lu_, lv_) in ((cu_, cv0), (cu_ + 3, cv0), (cu_, cv0 + 2), (cu_ + 3, cv0 + 2)):
                    fr.box(lu_, lu_ + 1, y, y + 4, lv_, lv_ + 1, WOOD_DARK)
        for i_, cu_ in enumerate(range(tu0 + 2, tu1 - 2, 4)):
            fr.box(cu_, cu_ + 2, y + 8, y + 9, 19 + (i_ % 2) * 4, 21 + (i_ % 2) * 4, CERAMIC)      # plates
        fr.box(U1 - 4, U1, y, y + 9, 12, 32, WOOD_MED)                               # sideboard + lamp
        fr.box(U1 - 4, U1, y + 9, y + 10, 12, 32, MARBLE_W)
        fr.box(U1 - 3, U1 - 2, y + 10, y + 13, 28, 29, BRASS)
        fr.box(U1 - 4, U1 - 1, y + 13, y + 16, 27, 30, LAMPSHADE)
        fr.light(U1 - 1, y + 12, 28, (1.0, 0.78, 0.45), 1.2, 0.15, f"room={rid} rl=lamp")
        lamps_ = 1
        fr.box(U0, U0 + 3, y, y + 22, ROOM_D - 14, ROOM_D - 1, WOOD_DARK)            # bookcase + study desk
        for sy in range(y + 4, y + 22, 5):
            fr.box(U0 + 1, U0 + 3, sy, sy + 1, ROOM_D - 13, ROOM_D - 2, WOOD_MED)
            for bv in range(ROOM_D - 13, ROOM_D - 2, 2):
                fr.box(U0 + 2, U0 + 3, sy + 1, sy + 4, bv, bv + 1, rng.choice((BLANKET_B, BLANKET_C, ART2, CARP_OR)))
        fr.box(U1 - 12, U1 - 1, y + 7, y + 8, ROOM_D - 7, ROOM_D - 1, WOOD_DARK)
        fr.box(U1 - 12, U1 - 11, y, y + 7, ROOM_D - 7, ROOM_D - 1, WOOD_DARK)
        sarr, smin = frame_shape(fr, U0, U0 + 1, y + 11, y + 14, 15, 16,
                                 lambda a_, b_, c_, A, B, C: DARK_METAL if b_ == 1 else SWITCH)
        if keycard:
            arr, gmin = frame_shape(fr, tu0 + 1, tu0 + 4, y + 8, y + 9, 17, 19,
                                    lambda a_, b_, c_, A, B, C: DREAM_CLOUD if a_ == 1 else MEMORY)
            KEYCARDS.append(dict(arr=arr, gmin=gmin, floor=k))
    ROOM_NSTANDS[rid] = lamps_
    ROOM_SWITCHES.append((sarr, smin, rid, True, False))
    room_ceiling(fr, U0, U1, y, rid)

KEYCARD_ROOMS = {}
_cands = [(n_, b_, k_) for (n_, b_, f_, bw_) in room_frames() for k_ in range(FLOORS) if not (k_ == 0 and (n_ == "S" and b_ in (1, 2) or n_ == "N"))]
for k_ in range(FLOORS):
    opts = [c for c in _cands if c[2] == k_]
    KEYCARD_ROOMS[MRNG.choice(opts)] = True

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
            if k == 0 and (name == "S" and b in (1, 2) or name == "N"):
                continue                                  # lobby / back of house (staff rooms, built later)
            u0 = window_in_facade(fr, bw, y)
            state = rng.choice(STATES)
            wall = rng.choice([ROOM_WALL, ROOM_WALL, ROOM_WALL_B, ROOM_WALL_C])
            # paint this room's own wall faces with its wallpaper colour
            fr.paint(1, 2, y, y + FH - SLAB_T, 0, ROOM_D, wall, [ROOM_WALL])
            fr.paint(bw, bw + 1, y, y + FH - SLAB_T, 0, ROOM_D, wall, [ROOM_WALL])
            fr.paint(T_PART, bw, y, y + FH - SLAB_T, ROOM_D, ROOM_D + 1, wall, [ROOM_WALL])
            fr.paint(T_PART, bw, y, y + FH - SLAB_T, -1, 0, wall, [ATR_WALL])
            curtains(fr, u0, y, state, rid=len(room_log))
            twin = bw >= 40 and rng.random() < 0.6
            blanket = rng.choice([BLANKET_A, BLANKET_A, BLANKET_B, BLANKET_C])
            carpet = rng.choice([CARP_A, CARP_A, CARP_B])
            ff = fr.mirrored(T_PART, bw) if rng.random() < 0.5 else fr
            suite_ = SUITE_ROLE.get((name, b)) if k == FLOORS - 1 else None
            if suite_ and suite_[1] != "bedroom":
                furnish_suite(fr, bw, k, suite_[1], carpet, (name, b, k) in KEYCARD_ROOMS, len(room_log))
            elif suite_:                                # the suite's bedroom: double bed, bath away from the living room
                fm_ = fr.mirrored(T_PART, bw)
                furnish_room(fm_, bw, k, state, False, blanket, carpet,
                             keycard=(name, b, k) in KEYCARD_ROOMS, rid=len(room_log))
                fm_.box(T_PART, T_PART + 9, y, y + 22, 3, 13, 0)  # (walk-through to the living room's opening)
            else:
                furnish_room(ff, bw, k, state, twin, blanket, carpet, keycard=(name, b, k) in KEYCARD_ROOMS, rid=len(room_log))
            if suite_:
                SUITE_LOG[len(room_log)] = suite_
            room_log.append((name, b, k, state))
            # a few shop-window mannequins standing at open windows, looking out over the atrium
            if name in "WE" and state in ("lit_open", "dark_open", "tv") and MRNG.random() < 0.15:
                MQ_DECOR.append((fr, bw // 2 - 2, y, 4))

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

THEMES = [  # one per floor: carpet, carpet alt, pattern, wallpaper, wallpaper stripe, motif
    dict(c=COR_CARP, c2=COR_CARP2, p=COR_GOLD,   w=COR_WALL,    st=COR_STRIPE,  motif="medallion"),
    dict(c=CARP_OR,  c2=CARP_OR2,  p=COR_GOLD,   w=WALL_ORANGE, st=COR_STRIPE,  motif="zigzag"),
    dict(c=CARP_G,   c2=CARP_G2,   p=COR_GOLD,   w=WALL_GREEN,  st=ROOM_WALL_B, motif="diamond"),
    dict(c=CARP_BL,  c2=CARP_BL2,  p=PAINT_LINE, w=WALL_BLUE,   st=ATR_WALL2,   motif="stripes"),
    dict(c=CARP_PK,  c2=CARP_PK2,  p=COR_GOLD,   w=WALL_MAUVE,  st=ROOM_WALL_C, motif="dots"),
    dict(c=CARP_DK,  c2=CARP_DK2,  p=COR_CARP2,  w=WALL_GREY,   st=STAIR_WALL2, motif="plain"),
]
THEME_WALLS = [t_["w"] for t_ in THEMES] + [t_["st"] for t_ in THEMES]

def corridor_art(fr, u, y, w=8, h=8):
    """framed picture on the exterior wall face of a corridor (v = COR_W layer)."""
    fr.box(u, u + w, y, y + h, COR_W - 1, COR_W, PICFRAME)
    cols = MRNG.choice([(ART1, ART2, CEIL), (LEAF2, ART1, CEIL), (BLANKET_B, ART2, BLANKET_A), (WALL_BLUE, ART1, CEIL)])
    for yy in range(y + 1, y + h - 1):
        for uu in range(u + 1, u + w - 1):
            band = (yy - y) * 2 // max(1, h - 2) + ((uu - u) * 3 // w == 1)
            fr.box(uu, uu + 1, yy, yy + 1, COR_W - 1, COR_W, cols[band % 3])

def corridor_bench(fr, u, y):
    fr.box(u, u + 10, y + 3, y + 4, COR_W - 4, COR_W - 1, WOOD_MED)
    fr.box(u, u + 10, y + 4, y + 8, COR_W - 2, COR_W - 1, WOOD_MED)
    for uu in (u, u + 9):
        fr.box(uu, uu + 1, y, y + 3, COR_W - 4, COR_W - 1, DARK_METAL)

def corridor_plant(fr, u, y):
    fr.box(u + 1, u + 6, y, y + 6, COR_W - 6, COR_W - 1, PLANTER)
    x_, z_ = fr.pt(u + 3, COR_W - 4)
    box(x_, x_ + 1, y + 6, y + 11, z_, z_ + 1, TRUNK)
    leaf_blob(x_, y + 13, z_, 3, 71 + y, LEAF2 if (u // 7) % 2 else LEAF, anchor=(x_, y + 10, z_), squash=0.8, keep=0.3)

def build_corridors():
    for name, fr, L in cor_frames:
        for k in range(FLOORS):
            y = fy(k)
            th = THEMES[k]
            # ---- carpet: themed field + border + motif
            fr.box(0, L, y - 1, y, 0, COR_W, th["c"])
            fr.box(0, L, y - 1, y, 2, 3, th["p"])
            fr.box(0, L, y - 1, y, COR_W - 3, COR_W - 2, th["p"])
            for u in range(6, L, 12):
                if th["motif"] == "medallion":
                    for d in range(4):
                        fr.box(u + d, u + d + 1, y - 1, y, 9 - d, 9 + d, th["p"])
                        fr.box(u + 7 - d, u + 8 - d, y - 1, y, 9 - d, 9 + d, th["p"])
                    fr.box(u + 3, u + 5, y - 1, y, 8, 10, th["c2"])
                elif th["motif"] == "zigzag":
                    for d in range(12):
                        vv = 5 + (d if d < 6 else 11 - d)
                        fr.box(u + d, u + d + 1, y - 1, y, vv, vv + 2, th["p"])
                elif th["motif"] == "diamond":
                    for d in range(5):
                        fr.box(u + d, u + d + 1, y - 1, y, 9 - d, 9 + d + 1, th["c2"])
                        fr.box(u + 9 - d, u + 10 - d, y - 1, y, 9 - d, 9 + d + 1, th["c2"])
                    fr.box(u + 4, u + 6, y - 1, y, 8, 11, th["p"])
                elif th["motif"] == "stripes":
                    fr.box(u, u + 2, y - 1, y, 4, COR_W - 4, th["c2"])
                    fr.box(u + 6, u + 7, y - 1, y, 4, COR_W - 4, th["p"])
                elif th["motif"] == "dots":
                    for vv in (6, 11):
                        fr.box(u + (vv % 4), u + (vv % 4) + 2, y - 1, y, vv, vv + 2, th["p"])
                else:
                    fr.box(u, u + 1, y - 1, y, 3, COR_W - 3, th["c2"])
            # ---- dropped ceiling + crown moulding + lamps + sprinklers
            fr.box(0, L, y + 24, y + 25, 0, COR_W, CEIL)
            for side in (-1, COR_W):
                fr.paint(0, L, y + 23, y + 24, side, side + 1, CEIL, COR_PAINTABLE)
            fr.box(0, L, y + 23, y + 24, 0, 1, CEIL); fr.box(0, L, y + 23, y + 24, COR_W - 1, COR_W, CEIL)
            for u in range(17, L - 5, 34):
                fr.box(u - 2, u + 2, y + 23, y + 24, 7, 11, CEIL_LAMP)
                fr.box(u - 3, u + 3, y + 23, y + 24, 6, 7, BRASS); fr.box(u - 3, u + 3, y + 23, y + 24, 11, 12, BRASS)
            for u in range(0, L, 17):
                fr.box(u, u + 1, y + 23, y + 24, 3, 4, CHROME)
            flick_p = 0.6 if k == 5 else 0.18
            for u in range(51, L - 5, 68):          # aligned with a ceiling lamp
                fr.light(u, y + 21, 9, (1.0, 0.86, 0.62), 2.0, 0.25, "flicker" if rng.random() < flick_p else "")
            # ---- both walls: themed wallpaper with stripes above a wood wainscot with chair rail
            for side in (-1, COR_W):
                fr.paint(0, L, y + 10, y + 23, side, side + 1, th["w"], COR_PAINTABLE)
                for u in range(0, L, 6):
                    fr.paint(u, u + 3, y + 10, y + 23, side, side + 1, th["st"], [th["w"]])
                fr.paint(0, L, y + 1, y + 9, side, side + 1, WAINS, COR_PAINTABLE + THEME_WALLS)
                for u in range(0, L, 12):
                    fr.paint(u, u + 1, y + 1, y + 9, side, side + 1, WAINS2, [WAINS])
                fr.paint(0, L, y + 9, y + 10, side, side + 1, CHAIR_RAIL, COR_PAINTABLE + THEME_WALLS + [WAINS])
                fr.paint(0, L, y, y + 1, side, side + 1, WOOD_DARK, COR_PAINTABLE + THEME_WALLS + [WAINS, WAINS2])
            # ---- exterior-wall occupancy (so features never collide)
            busy = np.zeros(L + 40, bool)
            def mark(a_, b_):
                busy[max(a_, 0):max(b_, 0)] = True
            def free(a_, b_):
                return a_ >= 20 and b_ <= L - 20 and not busy[a_:b_].any()
            def doorway(u_):
                xs_, zs_ = fr.pt(u_, 0)
                return k == 0 and name in ("S", "N") and abs(xs_ - (ax0 + 2 * SHORT_BAY_W)) < 24
            # wall sconces on the exterior side (between the windows)
            for u in range(12, L - 6, 34):
                xa_, za_ = fr.pt(u, 0); xb_, zb_ = fr.pt(u + 1, 0)
                if any(min(xa_, xb_) < sx_ <= max(xa_, xb_) for sx_ in SEAMS_X) or \
                   any(min(za_, zb_) < sz_ <= max(za_, zb_) for sz_ in SEAMS_Z):
                    u += 3                                                         # keep it inside one shape
                if doorway(u):
                    continue                                                       # entrance / pool connector doorway
                fr.box(u, u + 2, y + 14, y + 16, COR_W - 2, COR_W, BRASS)         # bracket under the shade
                fr.box(u, u + 2, y + 16, y + 19, COR_W - 2, COR_W - 1, LAMPSHADE)
                mark(u - 1, u + 3)
            # small exterior windows with stone lintel + sill
            for u in range(30, L - 20, 68):
                fr.box(u, u + 8, y + 10, y + 22, COR_W, COR_W + T_EXT, 0)
                fr.box(u, u + 8, y + 10, y + 22, COR_W + 2, COR_W + 3, GLASS_EXT)
                fr.box(u + 3, u + 5, y + 10, y + 22, COR_W + 2, COR_W + 3, FRAME)
                fr.box(u - 1, u + 9, y + 9, y + 10, COR_W - 1, COR_W + T_EXT + 1, LINTEL)
                fr.box(u - 1, u + 9, y + 22, y + 24, COR_W + 1, COR_W + T_EXT + 1, LINTEL)
                for yy in range(y + 11, y + 22, 2):                                # half-open blind: no bright slab of glass
                    fr.box(u, u + 8, yy, yy + 1, COR_W + 1, COR_W + 2, SHEET)
                mark(u - 2, u + 10)
            # fire extinguisher cabinet near each end
            for u in (24, L - 30):
                fr.box(u, u + 5, y + 8, y + 18, COR_W, COR_W + 1, 0)
                fr.box(u, u + 5, y + 8, y + 18, COR_W + 1, COR_W + 2, RED)
                fr.box(u + 1, u + 4, y + 9, y + 17, COR_W, COR_W + 1, GLASS_DOOR)
                fr.box(u + 2, u + 3, y + 9, y + 15, COR_W + 1, COR_W + 2, RED)
                mark(u - 1, u + 6)
            for u in range(0, L):
                xs_, zs_ = fr.pt(u, COR_W - 4)
                if doorway(u) or any(abs(xs_ - q) <= 6 for q in SEAMS_X) or any(abs(zs_ - q) <= 6 for q in SEAMS_Z):
                    mark(u, u + 1)                                 # doorways + shape seams stay free
            # ---- floor feature (one per floor, on its own side)
            FEATURE_SIDE = {1: "E", 2: "W", 3: "N", 5: "W"}
            def place(w_, target):
                for off in range(0, L):
                    for u_ in (target + off, target - off):
                        if free(u_, u_ + w_):
                            mark(u_ - 1, u_ + w_ + 1)
                            return u_
                return None
            if FEATURE_SIDE.get(k) == name:
                if k == 1:                                     # two vending machines
                    u = place(20, L // 2)
                    if u is not None:
                        for i_, (body, panel) in enumerate(((DARK_METAL, TV_SCREEN), (RED, CEIL_LAMP))):
                            uu = u + i_ * 10
                            fr.box(uu, uu + 9, y, y + 20, COR_W - 6, COR_W, body)
                            fr.box(uu + 1, uu + 6, y + 7, y + 18, COR_W - 7, COR_W - 6, panel)
                            for r_ in range(4):
                                for c_ in range(3):
                                    fr.box(uu + 1 + c_ * 2, uu + 2 + c_ * 2, y + 8 + r_ * 3, y + 10 + r_ * 3, COR_W - 7, COR_W - 6,
                                           (ART1, ART2, BLANKET_B, LEAF2)[(r_ + c_ + i_) % 4])
                            fr.box(uu + 7, uu + 8, y + 9, y + 15, COR_W - 7, COR_W - 6, CHROME)   # coin / buttons
                            fr.box(uu + 1, uu + 8, y + 2, y + 5, COR_W - 7, COR_W - 6, TV_BODY)   # pick-up slot
                        fr.light(u + 10, y + 14, COR_W - 9, (0.6, 0.8, 1.0), 1.2, 0.3)
                elif k == 2:                                   # payphone + bench
                    u = place(6, L // 2)
                    if u is not None:
                        fr.box(u, u + 5, y + 8, y + 18, COR_W - 2, COR_W, DARK_METAL)
                        fr.box(u + 1, u + 4, y + 14, y + 17, COR_W - 3, COR_W - 2, CHROME)    # keypad
                        fr.box(u + 1, u + 2, y + 9, y + 14, COR_W - 3, COR_W - 2, TV_BODY)    # handset
                        fr.box(u + 1, u + 4, y + 18, y + 20, COR_W - 3, COR_W, DARK_METAL)
                elif k == 3:                                   # a door painted on the wall, with an EXIT sign
                    u = place(12, L // 2)
                    if u is not None:
                        fr.box(u, u + 12, y, y + 23, COR_W - 1, COR_W, WOOD_DARK)
                        fr.box(u + 1, u + 11, y, y + 22, COR_W - 1, COR_W, WOOD_DOOR)
                        fr.box(u + 9, u + 10, y + 10, y + 12, COR_W - 2, COR_W - 1, BRASS)
                        fr.box(u + 4, u + 8, y + 24, y + 26, COR_W - 1, COR_W, EXIT_SIGN)
                elif k == 5:                                   # abandoned housekeeping cart + TV with static
                    u = place(10, L // 3)
                    if u is not None:
                        fr.box(u, u + 9, y, y + 12, COR_W - 7, COR_W - 1, STEEL)
                        fr.box(u + 1, u + 8, y + 2, y + 11, COR_W - 6, COR_W - 2, 0)
                        fr.box(u + 1, u + 8, y + 4, y + 5, COR_W - 6, COR_W - 2, STEEL)
                        fr.box(u + 2, u + 7, y + 5, y + 7, COR_W - 5, COR_W - 3, TOWEL)
                        fr.box(u, u + 9, y + 12, y + 13, COR_W - 7, COR_W - 1, STEEL)
                    u = place(8, 2 * L // 3)
                    if u is not None:
                        fr.box(u, u + 8, y, y + 7, COR_W - 6, COR_W - 1, STEEL)           # cart
                        fr.box(u, u + 8, y + 7, y + 14, COR_W - 6, COR_W - 1, TV_BODY)    # old TV
                        fr.box(u + 1, u + 7, y + 8, y + 13, COR_W - 7, COR_W - 6, TV_SCREEN)
                        fr.light(u + 4, y + 10, COR_W - 9, (0.5, 0.6, 1.0), 0.8, 0.2)
            if k == 4:                                         # mirrors at both corners of every side
                for (ma, mb) in ((3, 12), (L - 12, L - 3)):
                    if busy[ma - 1:mb + 1].any():
                        continue
                    mark(ma - 1, mb + 1)
                    fr.box(ma, mb, y + 2, y + 22, COR_W - 1, COR_W, PICFRAME)
                    fr.box(ma + 1, mb - 1, y + 3, y + 21, COR_W - 1, COR_W, MIRROR)
            if k == 5 and name == "S":                         # a lone chair, turned to face the wall
                cu_ = place(5, L // 2 + 30)
                if cu_ is not None:
                    fr.box(cu_, cu_ + 5, y + 4, y + 5, 12, 17, UPHOL2)
                    fr.box(cu_, cu_ + 5, y + 5, y + 11, 12, 13, UPHOL2)
                    for (lu, lv) in ((cu_, 12), (cu_ + 4, 12), (cu_, 16), (cu_ + 4, 16)):
                        fr.box(lu, lu + 1, y, y + 4, lv, lv + 1, WOOD_DARK)
            # ---- pictures, benches and plants along the exterior wall
            n_ = 0
            for target in range(60, L - 30, 68):
                u = place(10, target)
                if u is None:
                    continue
                corridor_art(fr, u + 1, y + 12)
                if n_ % 2 == 0:
                    corridor_bench(fr, u, y)
                else:
                    corridor_plant(fr, u + 2, y)
                n_ += 1

build_rooms()
build_corridors()

def stamp_mannequin(fr, u0, y, v0):
    """decorative dreamer standing at frame (u0.., v0..), facing -v. A separate static body
    (tag "dreamdecor") that main.lua only shows while the mission runs."""
    arr, gmin = frame_shape(fr, u0, u0 + 5, y, y + 18, v0, v0 + 3, lambda a_, b_, c_, A, B, C: MQ_MODEL[a_, b_, c_])
    gx, gy, gz = gmin
    reg = G[gx:gx + arr.shape[0], gy:gy + arr.shape[1], gz:gz + arr.shape[2]]
    if ((reg > 0) & (arr > 0)).any():
        return False
    feet = arr[:, 0, :] > 0
    if not (G[gx:gx + arr.shape[0], gy - 1, gz:gz + arr.shape[2]][feet] > 0).all():
        return False
    DECOR_MQ.append(dict(arr=arr, gmin=gmin))
    return True

MQ_PLACED = sum(stamp_mannequin(fr_, u_, y_, v_) for (fr_, u_, y_, v_) in MQ_DECOR)

# ============================================================================
# 6. Ground floor lobby (south side, bays 1-2) + main entrance
# ============================================================================
lx0, lx1 = ax0 + SHORT_BAY_W, ax0 + 3 * SHORT_BAY_W
lz0, lz1 = az0 - T_FAC - ROOM_D, az0
y = G0
cx = (lx0 + lx1) // 2
# lx1 - T_PART: the party wall to the next room (east) belongs to that room -- keep it
box(lx0, lx1 - T_PART, y, y + FH - SLAB_T, lz0, lz1 - T_FAC, 0)
box(lx0, lx1 - T_PART, y, y + FH - SLAB_T, lz0, lz0 + 1, LOBBY_WALL)
paint(lx1 - T_PART, lx1 - T_PART + 1, y, y + FH - SLAB_T, lz0, lz1 - T_FAC, LOBBY_WALL, [ROOM_WALL, ROOM_WALL_B, ROOM_WALL_C])
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
box(cx - 14, cx + 14, y, y + 23, az0 - T_FAC, az0, FRAME)
box(cx - 13, cx + 13, y, y + 22, az0 - T_FAC, az0, 0)
box(cx - 13, cx + 13, y, y + 3, az0, az0 + 2, 0)          # no skirting across the doorway into the atrium
add_door(WORLD, cx - 13, cx, y, y + 22, az0 - 3, az0 - 2, glass_door, hinge=(cx - 13, az0 - 2), open_dir=(0, 1), stop=FRAME)
add_door(WORLD, cx, cx + 13, y, y + 22, az0 - 3, az0 - 2, lambda a, b, c, A, B, C: glass_door(A - 1 - a, b, c, A, B, C),
         hinge=(cx + 13, az0 - 2), open_dir=(0, 1), stop=FRAME)
box(cx - 4, cx + 4, y + 23, y + 26, az0 - 5, az0 - 4, EXIT_SIGN)
# reception desk with key cubbies behind it
box(lx0 + 8, lx0 + 36, y, y + 11, lz0 + 14, lz0 + 20, WOOD_DARK)
for xx in range(lx0 + 9, lx0 + 36, 4):
    box(xx, xx + 2, y + 2, y + 9, lz0 + 19, lz0 + 20, WOOD_MED)
box(lx0 + 8, lx0 + 36, y + 11, y + 12, lz0 + 13, lz0 + 21, WOOD_LIGHT)
BELL = dict(arr=np.full((2, 2, 2), BRASS, np.uint8), gmin=(lx0 + 12, y + 12, lz0 + 16))   # front-desk bell (mission)
MISSION_START = (lx0 + 24, y, lz0 + 28)
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
# entrance doors swing inward: the sidewalk outside is 10 cm higher than the corridor floor
add_door(WORLD, cx - 15, cx, y, y + 23, bz0 + 1, bz0 + 2, glass_door, hinge=(cx - 15, bz0 + 2), open_dir=(0, 1), stop=FRAME)
add_door(WORLD, cx, cx + 15, y, y + 23, bz0 + 1, bz0 + 2, lambda a, b, c, A, B, C: glass_door(A - 1 - a, b, c, A, B, C),
         hinge=(cx + 15, bz0 + 2), open_dir=(0, 1), stop=FRAME)
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
            fr.box(-T_PART, 0, y, y + 22, 26, 36, 0)
            fr.box(-T_PART - 1, -T_PART, y + 22, y + 25, 28, 34, EXIT_SIGN)
            fr.box(0, 1, y + 22, y + 23, 25, 37, DARK_METAL)          # header above the opening (clear of the swing)
            add_door(fr, -1, 0, y, y + 22, 26, 36, lambda a, b, c, A, B, C: steel_door(C - 1 - c, b, a, C, B, A),
                     hinge=(0, 36), open_dir=(1, 0), stop=DARK_METAL)
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
    HH = ATR_TOP + 3 - ROOF_Y - 2                    # head house: its roof ends level with the atrium wall top
    fr.box(-T_PART, CB, y, y + HH, -T_PART, CB, STAIR_WALL)
    fr.paint(-T_PART, CB, y, y + HH, -T_PART, CB, BRICK, [STAIR_WALL])
    fr.box(0, CB - T_FAC, y, y + HH - 1, 0, CB - T_FAC, 0)
    fr.box(-T_PART - 1, CB - T_FAC, y + HH, y + HH + 1, -T_PART - 1, CB - T_FAC, EXT_TRIM)
    fr.box(-T_PART, CB - T_FAC, y + HH + 1, y + HH + 2, -T_PART, CB - T_FAC, ROOF)
    fr.box(20, 30, y, y + 21, CB - T_FAC, CB, 0)
    fr.box(19, 31, y + 21, y + 23, CB - 1, CB + 1, LINTEL)
    fr.box(23, 27, y + 21, y + 22, CB + 1, CB + 2, CEIL_LAMP)
    fr.light(10, y + HH - 3, 10, (1.0, 0.95, 0.85), 1.6, 0.2)

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

def gear_style(a_, b_, c_, A, B, C):
    if c_ > 0:
        return UPHOL if (b_ in (0, B - 1) or a_ in (0, A - 1)) else SHEET
    if b_ in (0, B - 1) or a_ % 6 == 0 or a_ == A - 1:
        return UPHOL                                                    # cabinet frames
    if b_ == B - 2:
        return WALL_ORANGE                                              # warning band
    if b_ == 17 and a_ % 6 in (2, 4):
        return EXIT_SIGN                                                # status lights
    if 18 <= b_ <= 19 and A // 2 - 1 <= a_ <= A // 2 + 1:
        return TV_SCREEN                                                # meter
    if 5 <= b_ <= 13 and b_ % 2 == 1 and a_ % 6 in (2, 3, 4):
        return CURT_DARK                                                # breaker rows
    if 8 <= b_ <= 12 and A // 2 - 4 <= a_ <= A // 2 - 3:
        return BLANKET_B                                                # main breaker lever
    return SHEET

def elevators(fr, key):
    for k in range(FLOORS):
        y = fy(k)
        fr.box(0, CB - T_FAC, y, y + FH - SLAB_T, 0, CB - T_FAC, 0)
        fr.box(0, CB - T_FAC, y - 1, y, 0, CB - T_FAC, TILE_DARK)
    LIFT_TOP = ROOF_Y + 31                                                       # shafts reach the roof stop
    fr.box(0, 22, G0, ROOF_Y + 12, 0, CB - T_FAC, SLAB)
    fr.box(-T_PART, 22, ROOF_Y, LIFT_TOP + 3, -T_PART, CB - T_FAC, SLAB)         # lift penthouse on the roof
    fr.box(-T_PART, 22, 1, G0, 0, CB - T_FAC, SLAB)                              # shaft core down to B1
    for qi, q0 in enumerate((2, 24)):
        shaft = f"{key}{qi}"
        fr.box(0, 20, 1, LIFT_TOP, q0, q0 + 18, 0)                                # hollow shaft + pit
        # guide rails + brackets on the back wall (behind the car, not touching it)
        for qq in (q0 + 3, q0 + 14):
            fr.box(19, 20, 1, LIFT_TOP, qq, qq + 1, ELEV_RAIL)
            for yy in range(G0, LIFT_TOP, 15):
                fr.box(19, 20, yy, yy + 1, qq - 1, qq + 2, ELEV_RAIL)
        for qq in (q0 + 2, q0 + 15):                                            # pit buffers (outside the car footprint)
            fr.box(19, 20, 1, 3, qq, qq + 1, RED)
        # counterweight hint + hoist sheave at the top
        fr.box(6, 14, LIFT_TOP - 3, LIFT_TOP - 1, q0 + 7, q0 + 11, DARK_METAL)
        fr.box(9, 11, LIFT_TOP - 1, LIFT_TOP, q0 + 8, q0 + 10, ELEV_RAIL)
        start = rng.randrange(FLOORS)
        yb = fy(start) - 2
        arr, gmin = frame_shape(fr, CAR_P0, CAR_P1, yb, yb + CAR_H, q0 + 1, q0 + 17, car_style)
        # floor keypad (a separate shape): E opens the number entry
        def pad_style(a_, b_, c_, A, B, C):
            if b_ >= B - 2:
                return TV_SCREEN                                                    # floor display
            return SWITCH if (b_ % 2 == 0 and c_ % 2 == 0) else DARK_METAL          # keys on a dark plate
        barr, bmin = frame_shape(fr, CAR_P0 + 2, CAR_P0 + 3, yb + 10, yb + 19, q0 + 1 + 13, q0 + 1 + 16, pad_style)
        buttons = [(barr, bmin, None)]
        cxl, czl = cont(fr, (CAR_P0 + CAR_P1) / 2, q0 + 9)
        ELEVATORS.append(dict(arr=arr, gmin=gmin, shaft=shaft, floor=start, buttons=buttons,
                              light=(cxl, yb + CAR_H - 5, czl)))
        for k in LEVELS:
            y = lvl_y(k)
            fr.box(-T_PART, 0, y, y + 22, q0 + 4, q0 + 14, 0)
            # support points inside the wall (left jamb, right of the pocket, above the header):
            # main.lua drops the door when these are blown away
            # support probes: start 6 cm in front of the corridor face of the wall (left jamb, right of the
            # pocket, above the header) and look 20 cm into the wall; no hit = wall gone -> door drops
            sup = []
            for (Q, Y) in ((q0 + 2, y + 11), (q0 + 19, y + 11), (q0 + 13, y + 25)):
                wx_, wz_ = cont(fr, -T_PART - 0.6, Q + 0.5)
                sup.append(f"{wx_ * 0.1 - W * 0.05:.3f},{(Y + 0.5) * 0.1:.3f},{wz_ * 0.1 - D * 0.05:.3f}")
            sdx, sdz = fr.ux, fr.uz
            # the leaf runs one layer in from the corridor face and opens into a pocket behind the face skin
            # (both pockets between the two shafts), so an open door is hidden in the wall, never on it
            sgn = 1 if qi == 0 else -1
            pv0, pv1 = (q0 + 14, q0 + 24) if sgn > 0 else (q0 - 6, q0 + 4)
            fr.box(-T_PART + 1, 0, y, y + 22, pv0, pv1, 0)
            add_door(fr, -T_PART + 1, -T_PART + 2, y, y + 22, q0 + 4, q0 + 14,
                     lambda a, b, c, A, B, C: elev_door(c, b, a, C, B, A), slide=(0, 10 * sgn),
                     tag=f"elevdoor shaft={shaft} floor={k} s1={sup[0]} s2={sup[1]} s3={sup[2]} sdir={sdx},{sdz}")
            # brass portal, lantern and call button panel
            fr.box(-T_PART - 1, -T_PART, y, y + 23, q0 + 3, q0 + 4, BRASS)
            fr.box(-T_PART - 1, -T_PART, y, y + 23, q0 + 14, q0 + 15, BRASS)
            fr.box(-T_PART - 1, -T_PART, y + 22, y + 23, q0 + 3, q0 + 15, BRASS)
            fr.box(-T_PART - 1, -T_PART, y + 23, y + 26, q0 + 4, q0 + 13, DARK_METAL)
            for f in LEVELS:                                                     # floor dial dots (B2..R)
                fr.box(-T_PART - 2, -T_PART - 1, y + 24, y + 25, q0 + 6 + f, q0 + 7 + f, CEIL_LAMP if f == k else BRASS)
            cp0 = q0 + 16 if qi == 0 else q0 - 1                                  # call panel: clear of the jamb
            fr.box(-T_PART - 1, -T_PART, y + 9, y + 15, cp0, cp0 + 3, BRASS)
            barr, bmin = frame_shape(fr, -T_PART - 2, -T_PART - 1, y + 11, y + 13, cp0 + 1, cp0 + 2,
                                     lambda *a_: CEIL_LAMP)
            CALLS.append((barr, bmin, shaft, k))
    # lift penthouse on the roof (the shafts run up to the roof stop): brick outside, trimmed cap
    fr.paint(-T_PART, 22, ROOF_Y, LIFT_TOP + 3, -T_PART, CB - T_FAC, BRICK, [SLAB])
    fr.box(-T_PART - 1, 23, LIFT_TOP + 2, LIFT_TOP + 3, -T_PART - 1, CB - T_FAC + 1, EXT_TRIM)
    for k in range(FLOORS):
        y = fy(k)
        # electrical room of this floor: switchgear (separate shape: E switches the floor's power,
        # destroying it blacks the floor out for good), transformer, cable tray, safety markings
        fr.box(26, 35, y, y + 21, -T_PART, 0, 0)
        add_door(fr, 26, 35, y, y + 21, -1, 0, lambda a, b, c, A, B, C: steel_door(A - 1 - a, b, c, A, B, C),
                 hinge=(35, 0), open_dir=(0, 1), stop=DARK_METAL)
        fr.paint(22, 44, y - 1, y, 0, 44, STAIR_CONC)
        fr.box(24, 44, y - 1, y, 33, 34, YELLOW_PAINT)                          # keep-clear line
        garr, gmin = frame_shape(fr, 24, 43, y, y + 22, 37, 43, gear_style)
        SWITCHGEAR.append(dict(arr=garr, gmin=gmin, floor=k, corner=key))
        fr.box(23, 28, y, y + 14, 8, 24, HVAC)                                  # transformer
        for vv in range(9, 24, 3):
            fr.box(28, 29, y + 2, y + 13, vv, vv + 1, DARK_METAL)               # cooling fins
        fr.box(24, 25, y + 14, y + 27, 14, 16, DARK_METAL)                      # its cable up to the tray
        fr.box(24, 43, y + 25, y + 26, 30, 36, STEEL)                           # cable tray (hangs from the ceiling)
        fr.box(25, 42, y + 24, y + 25, 31, 35, TIRE)
        for uu in (24, 42):
            fr.box(uu, uu + 1, y + 25, y + 27, 30, 36, STEEL)
        fr.box(24, 25, y + 22, y + 25, 35, 37, TIRE)                            # cables down from the tray to the switchgear
        fr.box(30, 34, y + 26, y + 27, 18, 22, CEIL_LAMP)
        ELEC_ROOMS.append((fr, y))
        fr.light(32, y + 24, 20, (0.85, 0.95, 1.0), 1.2, 0.2)
    # (the old machine room on the roof is now the lift penthouse with the roof landing, see above)

stairwell(corner["SW"]); stairwell(corner["NE"])
elevators(corner["NW"], "NW"); elevators(corner["SE"], "SE")

# ============================================================================
# 8. Roof: HVAC, ducts, vents, rooftop sign
# ============================================================================
CORNER_RECTS = [corner[k_]._rect(-T_PART - 1, CB + 1, -T_PART - 1, CB + 1) for k_ in corner]   # penthouses / lift rooms
def roof_clear(x0, x1, z0, z1, m=4):
    return not any(x0 < b + m and x1 > a - m and z0 < d + m and z1 > c - m for (a, b, c, d) in CORNER_RECTS)
HVAC_SPOTS = [(bx0 + 20 + i * 60, hz) for i in range(5) for hz in (bz0 + 14, bz1 - 34)]
HVAC_SPOTS = [(hx, hz) for (hx, hz) in HVAC_SPOTS if roof_clear(hx - 1, hx + 23, hz - 1, hz + 19)]
# the east roof carries the penthouse suite and its terrace (section 10e): keep roof plant off it
PH_X0, PH_X1, PH_Z0, PH_Z1 = ax1 + T_FAC + 10, bx1 - T_EXT, 228, 404     # suite (outer walls; 1 m walkway west)
PT_Z0 = 168                                                                    # terrace from here to PH_Z0
CORNER_RECTS.append((PH_X0 - 2, PH_X1 + 2, PT_Z0 - 2, PH_Z1 + 2))
for (hx, hz) in HVAC_SPOTS:
    box(hx, hx + 22, ROOF_Y, ROOF_Y + 12, hz, hz + 18, HVAC)
    box(hx - 1, hx + 23, ROOF_Y, ROOF_Y + 2, hz - 1, hz + 19, DARK_METAL)
    box(hx + 3, hx + 19, ROOF_Y + 12, ROOF_Y + 13, hz + 3, hz + 15, DARK_METAL)
    for gx in range(hx + 2, hx + 21, 3):
        box(gx, gx + 1, ROOF_Y + 2, ROOF_Y + 10, hz - 1, hz, DARK_METAL)
    # fan on top
    cxf, czf = hx + 11, hz + 9
    for a in range(-5, 6):
        box(cxf + a, cxf + a + 1, ROOF_Y + 13, ROOF_Y + 14, czf - 5 + abs(a) // 2, czf + 5 - abs(a) // 2, CABLE)
for (dx0_, dx1_, dz0_, dz1_) in ((ax0 - 24, ax0 - T_FAC, bz0 + 30, bz0 + 36), (ax1 + T_FAC, ax1 + 24, bz1 - 36, bz1 - 30)):
    if roof_clear(dx0_, dx1_, dz0_, dz1_, 1):
        box(dx0_, dx1_, ROOF_Y + 2, ROOF_Y + 8, dz0_, dz1_, HVAC)
for (vx, vz) in [(bx0 + 30, bz0 + 70), (bx1 - 30, bz0 + 120), (bx0 + 30, bz1 - 120), (bx1 - 30, bz1 - 80)]:
    if not roof_clear(vx - 1, vx + 5, vz - 1, vz + 5, 2):
        continue
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
sz_ = bz0 + T_EXT - 2                  # letters stand on the parapet, the panel against its inner face (no gap behind)
box(sx0 - 4, sx0 + len(word) * 12, ROOF_Y, ROOF_Y + 28, sz_ + 2, sz_ + 3, DARK_METAL)   # backing panel holds the letters
for i in range(sx0 - 2, sx0 + len(word) * 12, 10):
    box(i, i + 1, ROOF_Y, ROOF_Y + 28, sz_ + 3, sz_ + 4, DARK_METAL)
# every letter is its own lamp shape (bulbs on a dark plate) with its own light: a shot letter goes dark alone
SIGN_LETTERS = []        # (name, arr, gmin, lights) -> ROOF_SHAPES (section 10c)
for li, ch in enumerate(word):
    lx0 = sx0 + (len(word) - 1 - li) * 12                      # mirrored: read from the south
    la = np.zeros((10, 14, 2), np.uint8)
    la[:, :, 1] = DARK_METAL
    for r_, row in enumerate(FONT[ch]):
        for c_, cc in enumerate(row):
            if cc == "#":
                xx = (4 - c_) * 2; yy = (6 - r_) * 2
                la[xx:xx + 2, yy:yy + 2, :] = STREET_LMP
    SIGN_LETTERS.append((f"hotel_letter_{ch}{li}", la, (lx0, ROOF_Y + 13, sz_),
                         [(lx0 + 4.5, ROOF_Y + 20, sz_ - 3, (1.0, 0.75, 0.45), 1.8, 0.3)]))

# street lamps
for (sx, sz) in [(bx0 - 14, bz0 - 14), (bx1 + 12, bz0 - 14), (bx0 - 14, bz1 + 12), (bx1 + 12, bz1 + 12),
                 (bx0 - 14, (bz0 + bz1) // 2), (bx1 + 12, (bz0 + bz1) // 2)]:
    box(sx - 1, sx + 3, G0, G0 + 3, sz - 1, sz + 3, DARK_METAL)
    box(sx - 1, sx + 3, G0 + 49, G0 + 50, sz - 1, sz + 3, STREET_LMP)
    box(sx, sx + 2, G0, G0 + 50, sz, sz + 2, DARK_METAL)
    box(sx - 2, sx + 4, G0 + 50, G0 + 52, sz - 2, sz + 4, DARK_METAL)
    light(sx + 1, G0 + 48.5, sz - 0.5, (1.0, 0.75, 0.45), 6.0, 0.3)
# dumpster + fire hydrant by the north-east
box(bx1 + 8, bx1 + 22, G0 + 1, G0 + 12, bz1 - 40, bz1 - 22, DUMPSTER)
box(bx1 + 7, bx1 + 23, G0 + 12, G0 + 13, bz1 - 41, bz1 - 21, DARK_METAL)
box(bx1 + 9, bx1 + 11, G0, G0 + 1, bz1 - 39, bz1 - 37, TIRE); box(bx1 + 19, bx1 + 21, G0, G0 + 1, bz1 - 25, bz1 - 23, TIRE)
box(bx0 - 8, bx0 - 5, G0 + 1, G0 + 8, bz0 + 20, bz0 + 23, RED)
box(bx0 - 9, bx0 - 4, G0 + 5, G0 + 6, bz0 + 21, bz0 + 22, RED)
# parked cars (dynamic props)
CAR_Z = bz0 - SW - 9 - 44
# parked cars: base-game drivable vehicles spawned by main.lua (builtin asset pack); kind, fallback prop,
# footprint min corner (x, y, z) of a 2.0 x 4.4 m bay, yaw. Vehicles face -Z.
CAR_SPOTS = []
CAR_SPOTS.append(("salooncar", "car_a", bx0 + 5, G0, CAR_Z, 0))
CAR_SPOTS.append(("stationwagon", "car_b", bx0 + 65, G0, CAR_Z, 0))
CAR_SPOTS.append(("suv1", "car_c", bx1 - 55, G0, CAR_Z, 0))
CAR_SPOTS.append(("castanet-500l-gt", "car_b", bx1 + 5, G0, CAR_Z, 0))

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
box(cxN - CW, cxN + CW, BED_Y + 1, G0, bz1, AZ0, SLAB)
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
box(A_X0, A_X1, BED_Y + 1, DY, AZ0, AZ1, SLAB)                                  # podium / basin structure
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
# changing rooms (v3.49): a small wing outside the hall's south wall, between the hotel and the annex
CH_X0, CH_X1, CH_Z0 = cxN - 76, cxN - 34, AZ0 - 36
box(CH_X0, CH_X1, BED_Y + 1, DY, CH_Z0, AZ0, SLAB)
box(CH_X0, CH_X1, DY, DY + 30, CH_Z0, AZ0, EXT_WALL)
box(CH_X0 - 1, CH_X1 + 1, DY + 30, DY + 32, CH_Z0 - 1, AZ0, EXT_TRIM)
CHANGING = []
for i, dxs in enumerate((-70, -50)):
    dx_ = cxN + dxs
    a, b = (CH_X0 + 2, cxN - 56) if i == 0 else (cxN - 54, CH_X1 - 2)
    col = ART1 if i == 0 else BLANKET_B
    box(a, b, DY, DY + 28, CH_Z0 + 2, AZ0, 0)
    for x in range(a, b):
        for z in range(CH_Z0 + 2, AZ0):
            G[x, DY - 1, z] = POOL_TILE if ((x // 4) + (z // 4)) % 2 else WHITE_TILE
    paint(a - 1, b + 1, DY, DY + 28, CH_Z0 + 1, AZ0, WHITE_TILE, [EXT_WALL])
    paint(a - 1, b + 1, DY + 12, DY + 13, CH_Z0 + 1, AZ0, col, [WHITE_TILE])
    for lz in range(CH_Z0 + 8, AZ0 - 4, 5):                                         # lockers along the outer wall
        bx_ = a if i == 0 else b - 4
        box(bx_, bx_ + 4, DY, DY + 22, lz, lz + 4, col)
        box(bx_ + (3 if i == 0 else 0), bx_ + (4 if i == 0 else 1), DY + 18, DY + 20, lz + 1, lz + 3, DARK_METAL)
        box(bx_ + (3 if i == 0 else 0), bx_ + (4 if i == 0 else 1), DY + 10, DY + 11, lz + 3, lz + 4, CHROME)
    mx_ = (a + b) // 2                                                                # bench
    box(mx_ - 2, mx_ + 2, DY + 4, DY + 5, CH_Z0 + 12, AZ0 - 8, WOOD_MED)
    for bz_ in (CH_Z0 + 13, AZ0 - 10):
        box(mx_ - 1, mx_ + 1, DY, DY + 4, bz_, bz_ + 1, CHROME)
    sx_ = b - 7 if i == 0 else a                                                      # shower in the far corner
    box(sx_, sx_ + 7, DY - 1, DY, CH_Z0 + 2, CH_Z0 + 9, TILE_DARK)
    box(sx_ + 3, sx_ + 4, DY + 22, DY + 28, CH_Z0 + 2, CH_Z0 + 3, CHROME)
    box(sx_ + 2, sx_ + 5, DY + 22, DY + 23, CH_Z0 + 2, CH_Z0 + 5, CHROME)
    box(sx_, sx_ + 7, DY, DY + 22, CH_Z0 + 9, CH_Z0 + 10, GLASS)
    box(mx_ - 1, mx_ + 2, DY + 27, DY + 28, (CH_Z0 + AZ0) // 2 - 1, (CH_Z0 + AZ0) // 2 + 2, CEIL_LAMP)
    light(mx_ + 0.5, DY + 25.5, (CH_Z0 + AZ0) // 2 + 0.5, (0.95, 0.98, 1.0), 1.2, 0.2)
    # the door from the hall (was painted on the wall)
    box(dx_ - 1, dx_ + 11, DY, DY + 23, iz0 - 1, iz0, FRAME)
    box(dx_, dx_ + 10, DY, DY + 22, AZ0, iz0, 0)
    add_door(WORLD, dx_, dx_ + 10, DY, DY + 22, iz0 - 1, iz0, wood_door, hinge=(dx_, iz0 - 1), open_dir=(0, -1),
             tag="hoteldoor changing", stop=FRAME)
    box(dx_ + 3, dx_ + 7, DY + 25, DY + 29, iz0 - 1, iz0, col)                        # pictogram plate
    CHANGING.append(((a + b) // 2, (CH_Z0 + AZ0) // 2))
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
# poolside radio: plays the song (snd/radio_song.ogg) until it is shot / smashed
box(cxN + 2, cxN + 16, DY, DY + 6, pz1 + 14, pz1 + 20, LOUNGER)               # side table
box(cxN + 3, cxN + 15, DY, DY + 5, pz1 + 15, pz1 + 19, 0)
box(cxN + 2, cxN + 3, DY, DY + 5, pz1 + 14, pz1 + 15, LOUNGER); box(cxN + 15, cxN + 16, DY, DY + 5, pz1 + 14, pz1 + 15, LOUNGER)
box(cxN + 2, cxN + 3, DY, DY + 5, pz1 + 19, pz1 + 20, LOUNGER); box(cxN + 15, cxN + 16, DY, DY + 5, pz1 + 19, pz1 + 20, LOUNGER)
def make_radio():
    a = np.zeros((10, 7, 4), np.uint8)
    a[:, 0:5, :] = TV_BODY
    for cxs in (2, 7):                                   # two speakers on the front (z = 0, facing the pool)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if abs(dx) + abs(dy) < 2:
                    a[cxs + dx, 2 + dy, 0] = CHROME
    a[4:6, 2:4, 0] = GLASS_DOOR                          # cassette window
    a[4, 4, 0] = TV_SCREEN                               # power LED
    a[1, 5, 1:3] = CHROME; a[8, 5, 1:3] = CHROME         # carry handle
    a[1:9, 6, 1:3] = CHROME
    return a
RADIO = dict(arr=make_radio(), gmin=(cxN + 4, DY + 6, pz1 + 15))

# floating toys (dynamic: plastic floats in Teardown water)
PROPS.append(("beach_ball", cxN - 30, DY - 6, pz0 + 30, 0))
PROPS.append(("beach_ball", cxN + 34, DY - 6, pz0 + 52, 0))
PROPS.append(("swim_ring", cxN - 6, DY - 4, pz0 + 18, 0))
PROPS.append(("swim_ring", cxN + 14, DY - 4, pz0 + 44, 30))
PROPS.append(("kickboard", cxN - 44, DY - 3, pz0 + 46, 20))
PROPS.append(("kickboard", cxN + 46, DY - 3, pz0 + 20, -15))
SOUND_SPOTS = [("pool", cxN, DY, (pz0 + pz1) // 2), ("spa", scx, DY, scz)]

# ---- mission mannequins: two per floor, each patrolling (silently) one straight corridor side
def _swing_cells():
    occ = set()
    for d in DOORS:
        if d["kind"] != "swing":
            continue
        px, pz = d["pivot"]; X, Y, Z = np.nonzero(d["arr"]); gx, gy, gz = d["gmin"]
        for frac in np.linspace(0, 0.85, 8):
            a_ = np.radians(d["ang"] * frac)
            cx_, cz_ = X + gx + 0.5 - px, Z + gz + 0.5 - pz
            rx = cx_ * np.cos(a_) + cz_ * np.sin(a_); rz = -cx_ * np.sin(a_) + cz_ * np.cos(a_)
            occ |= set(zip(np.floor(px + rx).astype(int).tolist(), np.floor(pz + rz).astype(int).tolist()))
    return occ
SWING = _swing_cells()

def clear_run(fr_, L_, y_):
    """longest stretch of the corridor centre line (u) where a turning mannequin touches nothing."""
    ok = []
    for u in range(22, L_ - 21):
        px_, pz_ = cont(fr_, u, 8.5)
        x0, z0 = int(np.floor(px_ - 2.5)), int(np.floor(pz_ - 2.5))
        free_ = not (G[x0:x0 + 5, y_:y_ + 18, z0:z0 + 5] > 0).any() and \
            not any((x, z) in SWING for x in range(x0, x0 + 5) for z in range(z0, z0 + 5))
        ok.append(free_)
    best, cur, start = (0, 0), 0, 0
    for i, f_ in enumerate(ok + [False]):
        if f_:
            if cur == 0:
                start = i
            cur += 1
        else:
            if cur > best[1] - best[0]:
                best = (start, start + cur)
            cur = 0
    return 22 + best[0], 22 + best[1] - 1

for k_ in range(FLOORS):
    sides = MRNG.sample([c_ for c_ in cor_frames], 2)
    for (name_, fr_, L_) in sides:
        ua, ub = clear_run(fr_, L_, fy(k_))
        assert ub - ua >= 80, (name_, k_, ua, ub)
        pa = cont(fr_, ua, 8.5); pb = cont(fr_, ub, 8.5)
        t_ = MRNG.uniform(0.25, 0.75)
        u_ = int(ua + (ub - ua) * t_)
        arr, gmin = frame_shape(fr_, u_ - 2, u_ + 3, fy(k_), fy(k_) + 18, 7, 10, lambda a__, b__, c__, A, B, C: MQ_MODEL[a__, b__, c__])
        MANNEQUINS.append(dict(arr=arr, gmin=gmin, seg=(pa, pb), floor=k_, front=(-fr_.vx, -fr_.vz)))
# a few more decorative ones: lobby corner, poolside
MQ_PLACED += stamp_mannequin(WORLD, lx0 + 4, G0, lz0 + 24)
MQ_PLACED += stamp_mannequin(WORLD, px1 + 22, DY, pz0 + 8)
print("decor mannequins", MQ_PLACED, "of", len(MQ_DECOR) + 2, file=sys.stderr)

# ============================================================================
# 8c. Basement B1 fit-out: luxury arcade (boutiques, restaurant, café, fountain), car park,
#     automatic sliding doors between them. Elevators (NW + SE) open into the arcade.
# ============================================================================
BFONT = {
    "A": [".#.", "#.#", "###", "#.#", "#.#"], "B": ["##.", "#.#", "##.", "#.#", "##."],
    "C": [".##", "#..", "#..", "#..", ".##"], "E": ["###", "#..", "##.", "#..", "###"],
    "F": ["###", "#..", "##.", "#..", "#.."], "I": ["###", ".#.", ".#.", ".#.", "###"],
    "L": ["#..", "#..", "#..", "#..", "###"], "M": ["#...#", "##.##", "#.#.#", "#...#", "#...#"],
    "N": ["#..#", "##.#", "#.##", "#..#", "#..#"], "O": [".#.", "#.#", "#.#", "#.#", ".#."],
    "P": ["##.", "#.#", "##.", "#..", "#.."], "R": ["##.", "#.#", "##.", "#.#", "#.#"],
    "S": [".##", "#..", ".#.", "..#", "##."], "T": ["###", ".#.", ".#.", ".#.", ".#."],
    "U": ["#.#", "#.#", "#.#", "#.#", "###"], "V": ["#.#", "#.#", "#.#", "#.#", ".#."],
    "X": ["#.#", "#.#", ".#.", "#.#", "#.#"], "1": [".#.", "##.", ".#.", ".#.", "###"],
    "K": ["#.#", "##.", "#..", "##.", "#.#"], "H": ["#.#", "#.#", "###", "#.#", "#.#"],
    "D": ["##.", "#.#", "#.#", "#.#", "##."], "Y": ["#.#", "#.#", ".#.", ".#.", ".#."],
    " ": ["..", "..", "..", "..", ".."],
}

SIGN_CELLS = []   # (letter voxel, the cell right in front of it): checked by qa_full.py

def ftext(fr, s, u_mid, y_top, v, col):
    """5-row letters drawn in a frame plane at layer v; u runs to the viewer's right."""
    widths = [len(BFONT[ch][0]) for ch in s]
    u = u_mid - (sum(widths) + len(s) - 1) // 2
    for ch, w_ in zip(s, widths):
        for r_, row in enumerate(BFONT[ch]):
            for c_, cc in enumerate(row):
                if cc == "#":
                    fr.box(u + c_, u + c_ + 1, y_top - r_ - 1, y_top - r_, v, v + 1, col)
                    x_, z_ = fr.pt(u + c_, v); fx_, fz_ = fr.pt(u + c_, v - 1)
                    SIGN_CELLS.append(((x_, y_top - r_ - 1, z_), (fx_, y_top - r_ - 1, fz_), s))
        u += w_ + 1

def ceiling_panel(fr, u, v, rgb, scale=1.8, half=4):
    fr.box(u - half, u + half, YC - 1, YC, v - half, v + half, BRASS)
    fr.box(u - half + 1, u + half - 1, YC - 1, YC, v - half + 1, v + half - 1, CEIL_LAMP)
    fr.light(u, YC - 3, v, rgb, scale, 0.3)

def chandelier(x, z, rgb=(1.0, 0.86, 0.66), scale=2.4):
    box(x, x + 1, YC - 4, YC, z, z + 1, BRASS)                         # chain
    box(x - 4, x + 5, YC - 5, YC - 4, z - 4, z + 5, BRASS)              # ring
    box(x - 3, x + 4, YC - 5, YC - 4, z - 3, z + 4, 0)
    box(x, x + 1, YC - 5, YC - 4, z - 4, z + 5, BRASS); box(x - 4, x + 5, YC - 5, YC - 4, z, z + 1, BRASS)
    for (dx, dz) in ((-4, -4), (4, -4), (-4, 4), (4, 4), (0, -4), (0, 4), (-4, 0), (4, 0)):
        box(x + dx, x + dx + 1, YC - 7, YC - 5, z + dz, z + dz + 1, CEIL_LAMP)   # crystal drops
    box(x - 1, x + 2, YC - 8, YC - 5, z - 1, z + 2, CEIL_LAMP)          # centre crystal
    light(x + 0.5, YC - 10, z + 0.5, rgb, scale, 0.35)

def pendant(x, z, rgb=(1.0, 0.85, 0.62), scale=1.6):
    box(x, x + 1, YC - 5, YC, z, z + 1, BRASS)
    box(x - 2, x + 3, YC - 6, YC - 5, z - 2, z + 3, BRASS)
    box(x - 1, x + 2, YC - 7, YC - 6, z - 1, z + 2, LAMPSHADE)
    light(x + 0.5, YC - 9, z + 0.5, rgb, scale, 0.25)

def bench(fr, u0, u1, v0):
    fr.box(u0, u1, YB + 3, YB + 4, v0, v0 + 4, WOOD_MED)
    for u in (u0, u1 - 1):
        fr.box(u, u + 1, YB, YB + 3, v0, v0 + 4, BRASS)

def planter(x, z, seed):
    box(x - 3, x + 4, YB, YB + 6, z - 3, z + 4, MARBLE_W)
    box(x - 2, x + 3, YB + 5, YB + 6, z - 2, z + 3, SOIL)
    box(x, x + 1, YB + 6, YB + 16, z, z + 1, TRUNK)
    leaf_blob(x, YB + 19, z, 4, seed, LEAF2, anchor=(x, YB + 15, z), squash=1.0, keep=0.25)

def chair(fr, u, v, face, col=UPHOL):
    """dining chair, 4x4 footprint at (u, v); face = (du, dv) direction the sitter looks."""
    for (a_, b_) in ((0, 0), (3, 0), (0, 3), (3, 3)):
        fr.box(u + a_, u + a_ + 1, YB, YB + 4, v + b_, v + b_ + 1, WOOD_DARK)
    fr.box(u, u + 4, YB + 4, YB + 5, v, v + 4, col)
    du, dv = face
    if du:
        ub = u + (0 if du > 0 else 3)
        fr.box(ub, ub + 1, YB + 5, YB + 10, v, v + 4, WOOD_DARK)
    else:
        vb = v + (0 if dv > 0 else 3)
        fr.box(u, u + 4, YB + 5, YB + 10, vb, vb + 1, WOOD_DARK)

def round_table(fr, u, v, top=SHEET, r=3, h=7, cloth=True):
    fr.box(u - 1, u + 1, YB, YB + h, v - 1, v + 1, WOOD_DARK)
    fr.box(u - 2, u + 2, YB, YB + 1, v - 2, v + 2, WOOD_DARK)
    for a_ in range(-r, r):
        for b_ in range(-r, r):
            if (a_ + 0.5) ** 2 + (b_ + 0.5) ** 2 <= r * r:
                fr.box(u + a_, u + a_ + 1, YB + h, YB + h + 1, v + b_, v + b_ + 1, top)
                if cloth and abs(a_ + 0.5) + 0.8 > r - 0.5 or cloth and abs(b_ + 0.5) + 0.8 > r - 0.5:
                    fr.box(u + a_, u + a_ + 1, YB + h - 3, YB + h, v + b_, v + b_ + 1, top)

GEMS = [MEMORY, COVE_LAMP, EXIT_SIGN, POOL_LAMP, STREET_LMP, CEIL_LAMP]
SOFT = [BLANKET_B, UPHOL2, TV_BODY, DREAM_PINK, DREAM_SKY, BLANKET_C, DREAM_LILAC, WOOD_LIGHT, CURT_DARK, TOWEL]

def glass_counter(fr, u0, u1, v0, v1, kind="gems"):
    fr.box(u0, u1, YB, YB + 8, v0, v1, WOOD_DARK)
    fr.box(u0, u1, YB + 7, YB + 8, v0, v1, BRASS)
    fr.box(u0, u1, YB + 8, YB + 9, v0, v1, BLANKET_B if kind == "gems" else TV_BODY)
    fr.box(u0, u1, YB + 9, YB + 13, v0, v1, GLASS_DOOR)
    fr.box(u0 + 1, u1 - 1, YB + 9, YB + 12, v0 + 1, v1 - 1, 0)
    i = 0
    for u in range(u0 + 2, u1 - 2, 3):
        for v in range(v0 + 2, v1 - 2, 3):
            if kind == "gems":
                fr.box(u, u + 1, YB + 9, YB + 10, v, v + 1, GEMS[i % len(GEMS)] if i % 3 else BRASS)
            else:
                fr.box(u, u + 2, YB + 9, YB + 10, v, v + 2, BRASS)
                fr.box(u, u + 1, YB + 9, YB + 10, v, v + 1, CERAMIC)
            i += 1

def painting(fr, u0, y0, v, w, h):
    fr.box(u0, u0 + w, y0, y0 + h, v, v + 1, PICFRAME)
    cols = BRNG.choice([(DREAM_PINK, DREAM_SKY, DREAM_CLOUD), (WALL_BLUE, DREAM_LILAC, CEIL), (WALL_ORANGE, DREAM_PINK, ART2),
                        (LEAF2, DREAM_SKY, CEIL), (ART1, DREAM_CLOUD, WALL_MAUVE)])
    for yy in range(y0 + 1, y0 + h - 1):
        for uu in range(u0 + 1, u0 + w - 1):
            t_ = ((yy - y0) * 2 + (uu - u0) + BRNG.randint(0, 1)) * 3 // (w + h)
            fr.box(uu, uu + 1, yy, yy + 1, v, v + 1, cols[t_ % 3])

SHOP_STYLE = {   # wall, floor, light colour
    "jewelry": (TV_BODY, MARBLE_B, (1.0, 0.9, 0.75)), "bags": (ROOM_WALL_C, WOOD_LIGHT, (1.0, 0.85, 0.7)),
    "watches": (WOOD_DARK, MARBLE_W, (1.0, 0.88, 0.7)), "perfume": (LOBBY_WALL, MARBLE_BG, (1.0, 0.82, 0.9)),
    "fashion": (ATR_WALL, PARQUET, (0.95, 0.9, 1.0)), "shoes": (ROOM_WALL_B, MARBLE_BG, (1.0, 0.9, 0.8)),
    "florist": (WALL_GREEN, TILE, (0.95, 1.0, 0.9)), "gallery": (CEIL, MARBLE_W, (1.0, 0.97, 0.92)),
    "cafe": (WOOD_MED, PARQUET, (1.0, 0.8, 0.55)), "restaurant": (ROOM_WALL_C, PARQUET, (1.0, 0.78, 0.5)),
    "tech": (CEIL, FLOOR_MED, (0.97, 0.98, 1.0)),
}
SHOPS = []

def shop(x0, x1, z0, z1, side, kind, name, sign=STREET_LMP):
    if side == "E":
        fr = Frame(x1 - 1, z1 - 1, 0, -1, -1, 0); Wd, Dp = z1 - z0, x1 - x0
    elif side == "W":
        fr = Frame(x0, z0, 0, 1, 1, 0); Wd, Dp = z1 - z0, x1 - x0
    else:
        fr = Frame(x1 - 1, z0, -1, 0, 0, 1); Wd, Dp = x1 - x0, z1 - z0
    wall, floor, rgb = SHOP_STYLE[kind]
    SHOPS.append((name, kind, (x0 + x1) // 2, (z0 + z1) // 2))
    fr.box(0, 2, YB, YC, 0, Dp, wall); fr.box(Wd - 2, Wd, YB, YC, 0, Dp, wall); fr.box(0, Wd, YB, YC, Dp - 2, Dp, wall)
    fr.box(2, Wd - 2, YB - 1, YB, 0, Dp - 2, floor)
    fr.box(2, Wd - 2, YB, YB + 1, 2, 3, WOOD_DARK); fr.box(2, Wd - 2, YB, YB + 1, Dp - 3, Dp - 2, WOOD_DARK)  # skirting
    # storefront: glass between brass mullions, marble pilasters, black fascia with the name lit up
    fr.box(0, Wd, YB, YC, 0, 1, TV_BODY)
    fr.box(2, Wd - 2, YB, YB + 24, 0, 1, GLASS_DOOR)
    fr.box(2, Wd - 2, YB, YB + 1, 0, 1, BRASS); fr.box(2, Wd - 2, YB + 24, YB + 25, 0, 1, BRASS)
    for u in range(2, Wd - 2, 10):
        fr.box(u, u + 1, YB, YB + 24, 0, 1, BRASS)
    fr.box(0, 2, YB, YC, -1, 1, MARBLE_W); fr.box(Wd - 2, Wd, YB, YC, -1, 1, MARBLE_W)
    d0, d1 = Wd // 2 - 9, Wd // 2 + 9
    fr.box(d0, d1, YB, YB + 24, 0, 1, 0)
    fr.box(d0 - 1, d0, YB, YB + 25, 0, 1, BRASS); fr.box(d1, d1 + 1, YB, YB + 25, 0, 1, BRASS)
    fr.box(d0, d1, YB - 1, YB, 0, 1, MARBLE_B)                                  # threshold
    ftext(fr, name, Wd // 2, YC - 1, -1, sign)
    ceiling_panel(fr, Wd // 2, Dp // 2, rgb)
    cu, cv = Wd // 2, Dp // 2
    if kind == "jewelry":
        glass_counter(fr, 8, Wd - 8, Dp - 14, Dp - 8)
        glass_counter(fr, 4, 10, 12, Dp - 18); glass_counter(fr, Wd - 10, Wd - 4, 12, Dp - 18)
        for yy in (YB + 12, YB + 20):
            fr.box(4, Wd - 4, yy, yy + 1, Dp - 3, Dp - 2, BRASS)
    elif kind == "bags":
        for k_, sy in enumerate((YB + 8, YB + 17)):
            fr.box(4, Wd - 4, sy, sy + 1, Dp - 6, Dp - 2, WOOD_LIGHT)
            fr.box(4, Wd - 4, sy - 1, sy, Dp - 3, Dp - 2, STREET_LMP)              # under-shelf light strip
            for i, u in enumerate(range(6, Wd - 8, 7)):
                c_ = SOFT[(i + k_ * 3) % len(SOFT)]
                fr.box(u, u + 4, sy + 1, sy + 5, Dp - 5, Dp - 3, c_)
                fr.box(u + 1, u + 3, sy + 5, sy + 6, Dp - 4, Dp - 3, BRASS)          # handle
        fr.box(cu - 6, cu + 6, YB, YB + 7, cv - 3, cv + 3, WOOD_DARK)
        for i, u in enumerate((cu - 4, cu + 1)):
            fr.box(u, u + 4, YB + 7, YB + 11, cv - 1, cv + 1, SOFT[i + 3])
            fr.box(u + 1, u + 3, YB + 11, YB + 12, cv - 1, cv, BRASS)
        fr.box(4, 9, YB, YB + 4, cv - 3, cv + 3, BLANKET_B)                        # velvet ottoman
    elif kind == "watches":
        for sy in (YB + 9, YB + 15, YB + 21):
            for u in range(5, Wd - 6, 5):
                fr.box(u, u + 3, sy, sy + 3, Dp - 3, Dp - 2, BRASS)
                fr.box(u + 1, u + 2, sy + 1, sy + 2, Dp - 3, Dp - 2, CERAMIC)
                fr.box(u + 1, u + 2, sy - 1, sy, Dp - 3, Dp - 2, TV_BODY)
                fr.box(u + 1, u + 2, sy + 3, sy + 4, Dp - 3, Dp - 2, TV_BODY)
        glass_counter(fr, cu - 10, cu + 10, cv - 3, cv + 3, kind="watch")
    elif kind == "perfume":
        fr.box(4, Wd - 4, YB + 4, YB + 24, Dp - 3, Dp - 2, MIRROR)
        for sy in (YB + 8, YB + 14, YB + 20):
            fr.box(4, Wd - 4, sy, sy + 1, Dp - 6, Dp - 3, BRASS)
            for i, u in enumerate(range(5, Wd - 5, 3)):
                fr.box(u, u + 1, sy + 1, sy + 3, Dp - 5, Dp - 4, (GLASS_DOOR, MEMORY, POOL_LAMP, COVE_LAMP)[(i + sy) % 4])
                fr.box(u, u + 1, sy + 3, sy + 4, Dp - 5, Dp - 4, BRASS)
        fr.box(cu - 5, cu + 5, YB, YB + 8, cv - 5, cv + 5, MARBLE_W)
        for i, (a_, b_) in enumerate(((-3, -3), (1, -2), (-2, 1), (2, 2))):
            fr.box(cu + a_, cu + a_ + 2, YB + 8, YB + 12, cv + b_, cv + b_ + 2, (MEMORY, COVE_LAMP, GLASS_DOOR, POOL_LAMP)[i])
            fr.box(cu + a_, cu + a_ + 1, YB + 12, YB + 13, cv + b_, cv + b_ + 1, BRASS)
    elif kind == "fashion":
        for (rv, n0) in ((Dp - 7, 0), (cv, 4)):
            u0, u1 = 6, Wd - 6
            fr.box(u0, u0 + 1, YB, YB + 18, rv, rv + 1, STEEL); fr.box(u1 - 1, u1, YB, YB + 18, rv, rv + 1, STEEL)
            fr.box(u0, u1, YB + 17, YB + 18, rv, rv + 1, CHROME)
            for i, u in enumerate(range(u0 + 2, u1 - 2, 2)):
                fr.box(u, u + 1, YB + 6 + (i % 3), YB + 17, rv - 2, rv + 3, SOFT[(i // 2 + n0) % len(SOFT)])
        fr.box(2, 3, YB, YB + 22, 8, 16, BRASS); fr.box(2, 3, YB + 1, YB + 21, 9, 15, MIRROR)
    elif kind == "shoes":
        for sy in (YB + 6, YB + 12, YB + 18):
            fr.box(3, Wd - 3, sy, sy + 1, Dp - 6, Dp - 2, WOOD_LIGHT)
            for i, u in enumerate(range(5, Wd - 6, 6)):
                c_ = SOFT[(i + sy) % len(SOFT)]
                for du in (0, 2):
                    fr.box(u + du, u + du + 1, sy + 1, sy + 2, Dp - 5, Dp - 2, c_)
                    fr.box(u + du, u + du + 1, sy + 2, sy + 4, Dp - 3, Dp - 2, c_)
        fr.box(cu - 7, cu + 7, YB, YB + 5, cv - 2, cv + 2, UPHOL)
    elif kind == "florist":
        for i, u in enumerate(range(5, Wd - 8, 8)):
            for tier, (tv, th) in enumerate(((Dp - 8, 0), (Dp - 5, 4))):
                fr.box(u, u + 5, YB, YB + th + 4, tv, tv + 3, WOOD_MED)
                fr.box(u + 1, u + 4, YB + th + 4, YB + th + 7, tv, tv + 3, STEEL)
                for j, (a_, b_) in enumerate(((1, 0), (3, 1), (2, 2))):
                    hgt = 4 + (i + j + tier) % 4
                    fr.box(u + a_, u + a_ + 1, YB + th + 7, YB + th + 7 + hgt, tv + b_, tv + b_ + 1, LEAF)
                    hc = (DREAM_PINK, BLANKET_B, WALL_ORANGE, DREAM_LILAC, CEIL, DREAM_SKY)[(i * 3 + j + tier) % 6]
                    fr.box(u + a_, u + a_ + 1, YB + th + 7 + hgt, YB + th + 9 + hgt, tv + b_, tv + b_ + 1, hc)
        fr.box(cu - 6, cu + 6, YB, YB + 8, cv - 3, cv + 3, WOOD_MED)
        for j in range(5):
            fr.box(cu - 5 + j * 2, cu - 4 + j * 2, YB + 8, YB + 12, cv - 1, cv, LEAF)
            fr.box(cu - 5 + j * 2, cu - 4 + j * 2, YB + 12, YB + 14, cv - 1, cv, (DREAM_PINK, WALL_ORANGE, CEIL, BLANKET_B, DREAM_LILAC)[j])
    elif kind == "gallery":
        for u in range(5, Wd - 18, 20):
            painting(fr, u, YB + 8, Dp - 3, 14, 12)
        fr.box(cu - 6, cu + 6, YB + 3, YB + 4, cv - 2, cv + 2, WOOD_LIGHT)
        for u in (cu - 6, cu + 5):
            fr.box(u, u + 1, YB, YB + 3, cv - 2, cv + 2, BRASS)
    elif kind == "cafe":
        fr.box(4, Wd - 14, YB, YB + 10, Dp - 10, Dp - 6, WOOD_DARK)
        fr.box(4, Wd - 14, YB + 10, YB + 11, Dp - 10, Dp - 6, MARBLE_W)
        fr.box(6, 11, YB + 11, YB + 16, Dp - 9, Dp - 6, CHROME)                     # espresso machine
        fr.box(7, 10, YB + 12, YB + 13, Dp - 10, Dp - 9, BRASS)
        fr.box(14, 26, YB + 11, YB + 16, Dp - 10, Dp - 6, GLASS_DOOR)               # pastry case
        fr.box(15, 25, YB + 11, YB + 15, Dp - 9, Dp - 7, 0)
        for i, u in enumerate(range(15, 25, 2)):
            fr.box(u, u + 1, YB + 11, YB + 12, Dp - 8, Dp - 7, (DREAM_PINK, WALL_ORANGE, CEIL, ART2, DREAM_LILAC)[i % 5])
        fr.box(4, Wd - 4, YB + 18, YB + 19, Dp - 4, Dp - 2, WOOD_LIGHT)
        for u in range(6, Wd - 6, 3):
            fr.box(u, u + 1, YB + 19, YB + 21, Dp - 3, Dp - 2, CERAMIC)
        fr.box(Wd - 12, Wd - 4, YB + 12, YB + 20, Dp - 3, Dp - 2, TV_BODY)          # menu board
        for (tu, tv) in ((10, 12), (Wd // 2 + 6, 12), (Wd // 2 + 6, Dp // 2 + 2)):
            round_table(fr, tu, tv, MARBLE_W, r=3, h=8, cloth=False)
            chair(fr, tu - 9, tv - 2, (1, 0), BLANKET_B); chair(fr, tu + 5, tv - 2, (-1, 0), BLANKET_B)
    elif kind == "tech":
        # a minimal tech store: steel instead of brass on the front, white walls, light-oak tables with
        # laptops / phones / tablets, a service bar, a video wall at the back, two trees, a light ceiling
        fr.paint(0, Wd, YB, YC, -1, 1, STEEL, [BRASS]); fr.paint(0, Wd, YB, YC, -1, 1, CEIL, [MARBLE_W])
        fr.paint(2, Wd - 2, YB - 1, YB, 0, Dp - 2, FLOOR_MED)
        TRNG = random.Random(4950)
        def device_table(u0, u1, v0):
            fr.box(u0, u1, YB + 7, YB + 8, v0, v0 + 7, WOOD_LIGHT)
            for lu in (u0 + 1, u1 - 2):
                for lv in (v0 + 1, v0 + 5):
                    fr.box(lu, lu + 1, YB, YB + 7, lv, lv + 1, CEIL)
            for k_, u in enumerate(range(u0 + 2, u1 - 4, 6)):
                if k_ % 3 == 0:                                                        # open laptop
                    fr.box(u, u + 4, YB + 8, YB + 9, v0 + 2, v0 + 5, CHROME)
                    fr.box(u, u + 4, YB + 9, YB + 12, v0 + 5, v0 + 6, CHROME)
                    fr.box(u, u + 4, YB + 9, YB + 12, v0 + 4, v0 + 5, TV_SCREEN)
                elif k_ % 3 == 1:                                                      # tablets
                    fr.box(u, u + 3, YB + 8, YB + 9, v0 + 2, v0 + 4, CHROME)
                    fr.box(u + 1, u + 2, YB + 8, YB + 9, v0 + 2, v0 + 4, TV_SCREEN)
                else:                                                                  # phones on stands
                    for pu in (u, u + 2):
                        fr.box(pu, pu + 1, YB + 8, YB + 11, v0 + 3, v0 + 4, TV_BODY)
                        fr.box(pu, pu + 1, YB + 9, YB + 11, v0 + 2, v0 + 3, TV_SCREEN)
        d0, d1 = Wd // 2 - 9, Wd // 2 + 9
        device_table(8, d0 - 4, 10); device_table(d1 + 4, Wd - 8, 10)
        device_table(20, Wd // 2 - 4, 24); device_table(Wd // 2 + 4, Wd - 20, 24)
        # service bar with stools, the video wall behind it (soft gradient light), accessory walls on the sides
        fr.box(28, Wd - 28, YB, YB + 10, Dp - 13, Dp - 10, CEIL)
        fr.box(27, Wd - 27, YB + 10, YB + 11, Dp - 14, Dp - 9, WOOD_LIGHT)
        for su in range(30, Wd - 30, 6):
            fr.box(su, su + 1, YB, YB + 8, Dp - 17, Dp - 16, CHROME)
            fr.box(su - 1, su + 2, YB + 8, YB + 9, Dp - 18, Dp - 15, WOOD_LIGHT)
        fr.box(24, Wd - 24, YB + 12, YB + 30, Dp - 3, Dp - 2, TV_BODY)
        for yy in range(YB + 13, YB + 29):
            col_ = (POOL_LAMP, TV_SCREEN, COVE_LAMP, MEMORY)[min(3, (yy - YB - 13) // 4)]
            fr.box(25, Wd - 25, yy, yy + 1, Dp - 4, Dp - 3, col_)
        for (au0, au1) in ((3, 20), (Wd - 20, Wd - 3)):
            for sy in (YB + 10, YB + 16, YB + 22):
                fr.box(au0, au1, sy, sy + 1, Dp - 5, Dp - 2, CEIL)
                for u in range(au0 + 1, au1 - 2, 3):
                    fr.box(u, u + 2, sy + 1, sy + 3, Dp - 4, Dp - 3, TRNG.choice((CEIL, TV_BODY, ART1, ROSE, WALL_GREEN, YELLOW_PAINT)))
        for tu in (5, Wd - 6):                                                         # two trees in white planters
            fr.box(tu - 3, tu + 4, YB, YB + 6, Dp - 14, Dp - 7, CEIL)
            fr.box(tu - 2, tu + 3, YB + 5, YB + 6, Dp - 13, Dp - 8, SOIL)
            tx_, tz_ = fr.pt(tu, Dp - 11)
            box(tx_, tx_ + 1, YB + 6, YB + 18, tz_, tz_ + 1, TRUNK)
            leaf_blob(tx_, YB + 23, tz_, 6, 90 + tu, LEAF2, anchor=(tx_, YB + 17, tz_), squash=1.0, keep=0.3)
        for (pu, pv) in ((Wd // 4, Dp // 3), (3 * Wd // 4, Dp // 3), (Wd // 4, 2 * Dp // 3), (3 * Wd // 4, 2 * Dp // 3)):
            fr.box(pu - 6, pu + 6, YC - 1, YC, pv - 4, pv + 4, CEIL_LAMP)              # light-box ceiling panels
    return fr, Wd, Dp

# ---- west row (fronts face east onto the promenade)
shop(PX1 + 2, PRM0, IZ0, 160, "E", "jewelry", "ORO")
shop(PX1 + 2, PRM0, 160, 232, "E", "bags", "VELOUR")
shop(PX1 + 2, PRM0, 232, 332, "E", "tech", "NOVA", sign=CEIL_LAMP)     # (v3.49: a tech store, the old door alcove merged in)
shop(PX1 + 2, PRM0, 332, PZ1, "E", "perfume", "AURELIA")
shop(PX1 + 2, PRM0, 428, IZ1, "E", "cafe", "CAFE")
# ---- east row (fronts face west)
shop(PRM1, IX1, 176, 246, "W", "fashion", "MAISON")
shop(PRM1, IX1, 246, 316, "W", "shoes", "SOLE")
shop(PRM1, IX1, 316, 386, "W", "gallery", "LUNE")
shop(PRM1, IX1, 386, 426, "W", "florist", "FLEUR")

# ---- restaurant LUMIERE (north arcade, front faces south onto the arcade corridor)
rfr, RW, RD = shop(132, PX1 + 2, 428, IZ1, "S", "restaurant", "LUMIERE", sign=CEIL_LAMP)
# ---- public restrooms (v3.49): a men's and a women's room side by side, doors on the z1 face
RESTROOMS = []                                    # (level name, x0, x1, z0, z1, y)
def pictogram(x0, y0, z, col, women):
    """a 5 x 7 sign plate on the z face: a white figure on blue / red."""
    box(x0, x0 + 5, y0, y0 + 7, z, z + 1, col)
    box(x0 + 2, x0 + 3, y0 + 5, y0 + 6, z, z + 1, SHEET)                              # head
    if women:
        box(x0 + 1, x0 + 4, y0 + 2, y0 + 4, z, z + 1, SHEET); box(x0 + 2, x0 + 3, y0 + 4, y0 + 5, z, z + 1, SHEET)
        box(x0 + 1, x0 + 2, y0 + 1, y0 + 2, z, z + 1, SHEET); box(x0 + 3, x0 + 4, y0 + 1, y0 + 2, z, z + 1, SHEET)
    else:
        box(x0 + 1, x0 + 4, y0 + 3, y0 + 5, z, z + 1, SHEET)
        box(x0 + 1, x0 + 2, y0 + 1, y0 + 3, z, z + 1, SHEET); box(x0 + 3, x0 + 4, y0 + 1, y0 + 3, z, z + 1, SHEET)
def restrooms(x0, x1, z0, z1, y, top, name):
    box(x0, x1, y, top, z0, z1, WHITE_TILE)
    mid = (x0 + x1) // 2
    for (a, b, col, women) in ((x0 + 2, mid - 1, BLANKET_C, False), (mid + 1, x1 - 2, BLANKET_B, True)):
        box(a, b, y, top, z0, z1 - 2, 0)
        for x in range(a, b):
            for z in range(z0, z1 - 2):
                G[x, y - 1, z] = TILE_DARK if ((x // 3) + (z // 3)) % 2 else WHITE_TILE
        paint(a - 1, b + 1, y, y + 10, z0 - 1, z1 - 1, col, [WHITE_TILE])                 # coloured dado
        paint(a - 1, b + 1, y + 10, y + 11, z0 - 1, z1 - 1, SHEET, [col])
        dx = (a + b) // 2 - 4
        box(dx, dx + 9, y, y + 22, z1 - 2, z1, 0)
        box(dx - 1, dx + 10, y + 22, y + 23, z1 - 1, z1, STEEL)
        add_door(WORLD, dx, dx + 9, y, y + 22, z1 - 2, z1 - 1, wood_door, hinge=(dx, z1 - 2), open_dir=(0, -1),
                 tag="hoteldoor wc", stop=STEEL)
        pictogram(dx + 2, y + 24, z1, col, women)
        # WC (with its tank) in the back corner, a basin with a mirror and a dryer on the side wall
        box(a + 1, a + 6, y, y + 4, z0 + 1, z0 + 7, CERAMIC); box(a + 2, a + 5, y + 3, y + 4, z0 + 2, z0 + 6, 0)
        box(a + 1, a + 6, y + 4, y + 10, z0, z0 + 2, CERAMIC); box(a + 3, a + 4, y + 10, y + 11, z0, z0 + 1, CHROME)
        box(a + 8, a + 9, y, y + 20, z0, z0 + 9, WHITE_TILE)                             # cubicle screen
        box(b - 4, b, y + 8, y + 10, z0 + 10, z0 + 16, CERAMIC); box(b - 3, b - 1, y + 9, y + 10, z0 + 11, z0 + 15, 0)
        box(b - 1, b, y + 10, y + 12, z0 + 12, z0 + 14, CHROME)
        box(b - 1, b, y + 12, y + 21, z0 + 10, z0 + 16, MIRROR)
        box(b - 2, b, y + 13, y + 16, z0 + 18, z0 + 21, CHROME)                         # hand dryer
        if not women:
            box(a, a + 2, y + 5, y + 11, z0 + 13, z0 + 16, CERAMIC)                     # urinal
        cx_, cz_ = (a + b) // 2, (z0 + z1) // 2
        box(cx_ - 1, cx_ + 2, top - 1, top, cz_ - 1, cz_ + 2, CEIL_LAMP)
        light(cx_ + 0.5, top - 2.5, cz_ + 0.5, (0.95, 0.97, 1.0), 1.2, 0.2)
    RESTROOMS.append((name, x0, x1, z0, z1, y))
WC_BOX = (PRM0 + 6, PRM0 + 46, IZ0, IZ0 + 30)               # south end of the B1 promenade (and below it in B2)
restrooms(WC_BOX[0], WC_BOX[1], WC_BOX[2], WC_BOX[3], YB, YC, "B1")

rfr.box(2, RW - 2, YB, YB + 10, RD - 3, RD - 2, WAINS)
rfr.box(2, RW - 2, YB + 10, YB + 11, RD - 3, RD - 2, CHAIR_RAIL)
rfr.box(8, RW - 30, YB, YB + 11, RD - 16, RD - 11, WOOD_DARK)                     # bar
rfr.box(8, RW - 30, YB + 11, YB + 12, RD - 17, RD - 11, MARBLE_B)
for u in range(10, RW - 32, 6):                                                    # bar stools
    rfr.box(u, u + 1, YB, YB + 7, RD - 20, RD - 19, BRASS)
    rfr.box(u - 1, u + 2, YB + 7, YB + 8, RD - 21, RD - 18, BLANKET_B)
rfr.box(8, RW - 30, YB + 14, YB + 26, RD - 3, RD - 2, MIRROR)
for sy in (YB + 14, YB + 20):
    rfr.box(8, RW - 30, sy, sy + 1, RD - 6, RD - 3, WOOD_DARK)
    for i, u in enumerate(range(9, RW - 31, 2)):
        rfr.box(u, u + 1, sy + 1, sy + 4, RD - 5, RD - 4, (GLASS_EXT, LEAF3, GLASS_EXT, COR_CARP)[i % 4])
for (tu, tv) in ((18, 14), (40, 14), (62, 14), (84, 14), (29, 30), (51, 30), (73, 30)):
    if tv + 6 > RD - 22 or tu + 9 > RW - 2:
        continue
    round_table(rfr, tu, tv, SHEET, r=4, h=7)
    rfr.box(tu, tu + 1, YB + 8, YB + 10, tv, tv + 1, STREET_LMP)                   # candle
    chair(rfr, tu - 10, tv - 2, (1, 0)); chair(rfr, tu + 6, tv - 2, (-1, 0))
for (cu_, cv_) in ((RW // 3, RD // 2 - 6), (2 * RW // 3, RD // 2 - 6)):
    cx_, cz_ = rfr.pt(cu_, cv_)
    chandelier(cx_, cz_, (1.0, 0.76, 0.45), 2.0)

# ---- promenade: chandeliers, gold ceiling trim, fountain, benches, planters
for z in range(IZ0 + 2, IZ1 - 2, 24):
    box(PRM0, PRM1, YC - 1, YC, z, z + 1, BRASS)
box(PRM0, PRM0 + 1, YC - 1, YC, IZ0, IZ1, BRASS); box(PRM1 - 1, PRM1, YC - 1, YC, IZ0, IZ1, BRASS)
for z in (IZ0 + 50, IZ0 + 120, 244, 330, 400, 466):          # (clear of the shape seams at z 224 / 360)
    chandelier((PRM0 + PRM1) // 2, z)
FX0, FX1, FZ0, FZ1 = PRM0 + 8, PRM1 - 8, 270, 302
box(FX0, FX1, YB, YB + 5, FZ0, FZ1, MARBLE_W)
box(FX0 + 2, FX1 - 2, YB, YB + 5, FZ0 + 2, FZ1 - 2, 0)
paint(FX0 + 2, FX1 - 2, YB - 1, YB, FZ0 + 2, FZ1 - 2, POOL_TILE)
fcx, fcz = (FX0 + FX1) // 2, (FZ0 + FZ1) // 2
box(fcx - 1, fcx + 1, YB, YB + 11, fcz - 1, fcz + 1, MARBLE_W)
box(fcx - 3, fcx + 3, YB + 11, YB + 12, fcz - 3, fcz + 3, BRASS)
box(fcx - 2, fcx + 2, YB + 12, YB + 13, fcz - 2, fcz + 2, BRASS)
box(fcx - 1, fcx + 1, YB + 13, YB + 15, fcz - 1, fcz + 1, MARBLE_W)
POOLS.append((YB + 4.5, 4.5, [(FX0 + 2, FZ0 + 2), (FX1 - 2, FZ0 + 2), (FX1 - 2, FZ1 - 2), (FX0 + 2, FZ1 - 2)],
              dict(wave=0.06, ripple=0.9, motion=0.5, foam=0.6)))
for (sx_, sz_) in ((fcx - 3, fcz - 3), (fcx + 2, fcz - 3), (fcx - 3, fcz + 2), (fcx + 2, fcz + 2), (fcx - 3, fcz), (fcx + 2, fcz - 1)):
    box(sx_, sx_ + 1, YB, YB + 11, sz_, sz_ + 1, GLASS)                         # water falling from the bowl
pfr_w = Frame(PRM0, IZ0, 0, 1, 1, 0)       # u along +z, v into the promenade from its west edge
pfr_e = Frame(PRM1 - 1, IZ0, 0, 1, -1, 0)  # from its east edge
for z in (140, 380, 476):
    bench(pfr_w, z - IZ0, z - IZ0 + 12, 2)
    if z < 420:
        bench(pfr_e, z - IZ0, z - IZ0 + 12, 2)
planter(PRM0 + 6, 318, 301); planter(PRM1 - 7, 318, 302)
planter(PRM0 + 6, 438, 303); planter(PRM1 - 7, 254, 305)
# SE elevator hall, NW elevator lobby, arcade corridor
pendant(335, 130); pendant(374, 165); planter(374, 98, 306)
pendant(96, 452); pendant(96, 485); planter(118, 488, 307)
for x in (110, 150, 210, 262):
    pendant(x, 414)
bench(Frame(IX0, PZ1 + 2, 1, 0, 0, 1), 26, 38, 1)
# north-east corner: the stairwell comes down here; small seating by its door
box(366, 382, YB, YB + 4, 486, 491, UPHOL); box(366, 382, YB + 4, YB + 10, 489, 491, UPHOL)
box(366, 368, YB + 4, YB + 7, 486, 491, UPHOL); box(380, 382, YB + 4, YB + 7, 486, 491, UPHOL)
pendant(374, 470)

# ---- automatic sliding glass doors between the car park and the arcade
def autodoor_style(a, b, c, A, B, C):
    if b in (0, 1, B - 1) or (A > 1 and a in (0, A - 1)) or (C > 1 and c in (0, C - 1)):
        return FRAME
    return GLASS_DOOR
AUTODOORS = []
def auto_door(grp, along_x, wall0, a0, a1, y=None):
    YB = y if y is not None else globals()["YB"]
    """double sliding door in a 2-thick wall at wall0..wall0+2; leaves run in the arcade-side layer
    and slide into pockets of that layer (main.lua opens them when someone walks up)."""
    mid = (a0 + a1) // 2
    lay = wall0 + 1
    if along_x:      # wall runs along x (normal z)
        box(a0, a1, YB, YB + 24, wall0, wall0 + 2, 0)
        box(a0 - (mid - a0), a0, YB, YB + 24, lay, lay + 1, 0)
        box(a1, a1 + (a1 - mid), YB, YB + 24, lay, lay + 1, 0)
        add_door(WORLD, a0, mid, YB, YB + 24, lay, lay + 1, autodoor_style, slide=(-(mid - a0), 0), tag=f"autodoor grp={grp}")
        add_door(WORLD, mid, a1, YB, YB + 24, lay, lay + 1, autodoor_style, slide=(a1 - mid, 0), tag=f"autodoor grp={grp}")
        box(mid - 2, mid + 2, YB + 26, YB + 27, wall0 - 1, wall0, DARK_METAL)     # sensors
        box(mid - 2, mid + 2, YB + 26, YB + 27, wall0 + 2, wall0 + 3, DARK_METAL)
    else:            # wall runs along z (normal x)
        box(wall0, wall0 + 2, YB, YB + 24, a0, a1, 0)
        box(lay, lay + 1, YB, YB + 24, a0 - (mid - a0), a0, 0)
        box(lay, lay + 1, YB, YB + 24, a1, a1 + (a1 - mid), 0)
        add_door(WORLD, lay, lay + 1, YB, YB + 24, a0, mid, autodoor_style, slide=(0, -(mid - a0)), tag=f"autodoor grp={grp}")
        add_door(WORLD, lay, lay + 1, YB, YB + 24, mid, a1, autodoor_style, slide=(0, a1 - mid), tag=f"autodoor grp={grp}")
        box(wall0 + 2, wall0 + 3, YB + 26, YB + 27, mid - 2, mid + 2, DARK_METAL)
    AUTODOORS.append((grp, along_x, wall0, a0, a1))
# (v3.47: the door in the x divider is gone -- the ramp down to B2 runs along that wall; the arcade keeps door 2)
auto_door(2, True, PZ1, 176, 192)
# "MALL" above the door on the car-park side
ftext(Frame(192 - 1, PZ1, -1, 0, 0, 1), "MALL", 8, YC - 1, -1, CEIL_LAMP)

# ---- car park: bays, aisle line, columns, tube lights, pipes, signs, parked cars
# 90-degree bays 2.5 m wide x 5 m deep along both long walls; columns stand in a strip on the aisle side of the
# bay ends (never inside a bay or on a bay line); no bays by the stair core, the ramp tunnel or the mall door.
AISLE0, AISLE1 = IX0 + 50, PX1 - 2 - 50
BAY_W = 25
WEST_BAYS = [166 + i * BAY_W for i in range(3)] + [322 + i * BAY_W for i in range(3)]     # bay start z
EAST_BAYS = [365]                                         # (the south end is the turn into the ramp down to B2)
STAIR_RECTS = []
for key_ in ("SW", "NE"):
    xa_, xb_, za_, zb_ = corner[key_]._rect(-T_PART, CB, -T_PART, CB)
    STAIR_RECTS.append((xa_ - 1, xb_ + 1, za_ - 1, zb_ + 1))
def in_stair(x, z, m=4):
    return any(a - m <= x < b + m and c - m <= z < d + m for (a, b, c, d) in STAIR_RECTS)
for (bays_, xa_, xb_) in ((WEST_BAYS, IX0, AISLE0), (EAST_BAYS, AISLE1, PX1 - 2)):
    for z0_ in bays_:
        for zl_ in (z0_, z0_ + BAY_W - 1):
            box(xa_, xb_, YB - 1, YB, zl_, zl_ + 1, PAINT_LINE)
# no-parking hatching: walkway to the stair door, the mall door, the dumpster corner
for (xa_, xb_, za_, zb_) in ((IX0, 105, IZ0, 166), (AISLE1, PX1 - 2, 383, PZ1)):
    for x in range(xa_, xb_):
        for z in range(za_, zb_):
            if G[x, YB - 1, z] == STAIR_CONC and not (G[x, YB, z]) and (x + z) % 7 == 0:
                G[x, YB - 1, z] = YELLOW_PAINT
for z in range(IZ0, PZ1, 12):
    box((AISLE0 + AISLE1) // 2 - 1, (AISLE0 + AISLE1) // 2 + 1, YB - 1, YB, z, z + 6, YELLOW_PAINT)
for z in range(IZ0, PZ1):
    if not in_stair(AISLE0, z, 0):
        box(AISLE0, AISLE0 + 1, YB - 1, YB, z, z + 1, YELLOW_PAINT)
box(AISLE1 - 1, AISLE1, YB - 1, YB, IZ0, PZ1, YELLOW_PAINT)
COLS = []                            # (v3.48: no columns on the aisle edges -- cars need the room)
BEAM_Z = [138, 191, 213, 308, 347, 358]
for (cxc, czc) in COLS:
    box(cxc - 3, cxc + 3, YB, YC, czc - 3, czc + 3, SLAB)
    for yy in range(YB, YB + 8, 2):
        paint(cxc - 3, cxc + 3, yy, yy + 1, czc - 3, czc + 3, YELLOW_PAINT)
        paint(cxc - 3, cxc + 3, yy + 1, yy + 2, czc - 3, czc + 3, TIRE)
    face = Frame(cxc + 2, czc + 2, 0, -1, -1, 0) if cxc < (AISLE0 + AISLE1) // 2 else Frame(cxc - 3, czc - 3, 0, 1, 1, 0)
    ftext(face, "B1", 2, YB + 20, -1, YELLOW_PAINT)
TUBE_N = [0]
def tube(x, z):
    """twin fluorescent batten; every 4th one flickers (buzz), one is dead."""
    n_ = TUBE_N[0]; TUBE_N[0] += 1
    box(x - 1, x + 2, YC - 1, YC, z, z + 10, STEEL)                   # surface-mounted: 3.2 m clear under it
    dead = n_ == 5
    box(x - 1, x, YC - 2, YC - 1, z, z + 10, CEIL if dead else CEIL_LAMP)
    box(x + 1, x + 2, YC - 2, YC - 1, z, z + 10, CEIL if dead else CEIL_LAMP)
    if not dead:
        light(x + 0.5, YC - 4, z + 5, (0.86, 0.95, 1.0), 1.9, 0.3, "flicker" if n_ % 4 == 1 else "")
for z in (100, 170, 240, 320, 375):
    tube((AISLE0 + AISLE1) // 2, z)
for z in (130, 210, 350):
    for tx in (IX0 + 23, PX1 - 23):
        if not in_stair(tx, z + 5, 8):
            tube(tx, z)
box(IX0 + 10, IX0 + 12, YC - 2, YC, IZ0, PZ1, STEEL); box(PX1 - 12, PX1 - 10, YC - 2, YC, IZ0, PZ1, STEEL)
ftext(Frame(IX0 - 1, TZ1 - 1, 0, -1, -1, 0), "EXIT", -12, YC - 2, -1, EXIT_SIGN)       # on the wall beside the tunnel mouth
for (kind_, pn, side_, z0_) in (("salooncar", "car_a", "W", 166), ("stationwagon", "car_c", "W", 216),
                                ("suv1", "car_b", "W", 372)):
    cxp_ = IX0 + 28 if side_ == "W" else PX1 - 2 - 28          # rear 0.2 m off the wall (5.2 m car)
    czp_ = z0_ + BAY_W / 2
    CAR_SPOTS.append((kind_, pn, cxp_ - 10, YB, czp_ - 22, -90 if side_ == "W" else 90))
# ---- car park detail pass: standing water, ceiling services, paint, signage, clutter
for ch_, rows_ in {"0": ["###", "#.#", "#.#", "#.#", "###"], "2": ["##.", "..#", ".#.", "#..", "###"],
                   "3": ["##.", "..#", ".#.", "..#", "##."], "4": ["#.#", "#.#", "###", "..#", "..#"],
                   "5": ["###", "#..", "##.", "..#", "##."], "6": [".##", "#..", "###", "#.#", "###"],
                   "7": ["###", "..#", ".#.", ".#.", ".#."], "8": ["###", "#.#", "###", "#.#", "###"],
                   "9": ["###", "#.#", "###", "..#", "##."]}.items():
    BFONT[ch_] = rows_
def garage_ok(x0, x1, z0, z1, m=3):
    """inside the car park, clear of the stair core, the tunnel mouth and the shape seams."""
    if x0 < IX0 or x1 > PX1 - 2 or z0 < IZ0 or z1 > PZ1:
        return False
    for (a, b, c, d) in STAIR_RECTS:
        if x0 < b + m and x1 > a - m and z0 < d + m and z1 > c - m:
            return False
    return True
# wall paint: grey dado band with a yellow stripe, on every car-park wall face
for (xa, xb, za, zb) in ((IX0 - 1, IX0, IZ0, PZ1), (IX0, PX1 - 2, IZ0 - 1, IZ0), (PX1 - 2, PX1 - 1, IZ0, PZ1), (IX0, PX1 - 2, PZ1, PZ1 + 1)):
    paint(xa, xb, YB, YB + 10, za, zb, WALL_GREY, [SLAB])
    paint(xa, xb, YB + 10, YB + 11, za, zb, YELLOW_PAINT, [SLAB])
# downstand beams across the ceiling (in line with the columns), sprinkler main, cable tray, supply duct
for bz in BEAM_Z:      # (all clear of the EXIT sign over the tunnel mouth)
    xs_ = [x for x in range(IX0, PX1 - 2) if garage_ok(x, x + 1, bz - 2, bz + 2, 1)]
    for x in xs_:
        box(x, x + 1, YC - 2, YC, bz - 2, bz + 2, SLAB)
box(146, 147, YC - 1, YC, IZ0, PZ1, RED)
for z in range(IZ0 + 6, PZ1, 20):
    if garage_ok(145, 148, z, z + 1, 0):
        box(146, 147, YC - 2, YC - 1, z, z + 1, CHROME)                   # sprinkler heads
for z in range(IZ0, PZ1):
    if garage_ok(218, 224, z, z + 1, 0) and not (z % 40 < 2):
        box(218, 224, YC - 1, YC, z, z + 1, STEEL)
        box(219, 223, YC - 2, YC - 1, z, z + 1, TIRE if z % 3 else CABLE)   # cables in the tray
DZ1 = 392
box(175, 182, YC - 2, YC, IZ0, DZ1, HVAC)
for z in range(IZ0 + 14, DZ1 - 6, 30):
    box(176, 181, YC - 2, YC - 1, z, z + 6, DARK_METAL)                   # supply grilles (flush with the duct)
    for gz in range(z, z + 6, 2):
        box(177, 180, YC - 2, YC - 1, gz, gz + 1, HVAC)
# bay numbers on the walls, wheel stops, oil stains
for (lbl_, bays_, west_) in (("A", WEST_BAYS, True), ("B", EAST_BAYS, False)):
    for i, z in enumerate(bays_):
        zc = z + BAY_W // 2
        if west_:
            ftext(Frame(IX0 - 1, zc + 6, 0, -1, -1, 0), lbl_ + str(i + 1), 6, YB + 22, -1, YELLOW_PAINT)
            box(IX0 + 7, IX0 + 9, YB, YB + 1, zc - 5, zc + 5, CURB)
            sx_ = IX0 + 24
        else:
            ftext(Frame(PX1 - 2, zc - 6, 0, 1, 1, 0), lbl_ + str(i + 1), 6, YB + 22, -1, YELLOW_PAINT)
            box(PX1 - 11, PX1 - 9, YB, YB + 1, zc - 5, zc + 5, CURB)
            sx_ = PX1 - 26
        if BRNG.random() < 0.7:
            for dx in range(-5, 6):
                for dz in range(-4, 5):
                    if (dx / 5.5) ** 2 + (dz / 4.5) ** 2 < 1 and BRNG.random() < 0.85:
                        if G[sx_ + dx, YB - 1, zc + dz] == STAIR_CONC:
                            G[sx_ + dx, YB - 1, zc + dz] = ASPHALT
# tyre marks along the aisle, direction arrows, zebra crossing to the arcade door, speed bump at the tunnel
for lane in (150, 174):
    for z in range(IZ0 + 4, PZ1 - 4):
        if BRNG.random() < 0.55 and G[lane, YB - 1, z] == STAIR_CONC:
            G[lane, YB - 1, z] = ASPHALT2
for (ax_, az_, dz_) in ((AISLE0 + 9, 228, -1), (AISLE0 + 9, 330, -1), (AISLE1 - 11, 186, 1), (AISLE1 - 11, 326, 1)):
    for k_ in range(9):
        box(ax_, ax_ + 2, YB - 1, YB, az_ + dz_ * k_, az_ + dz_ * k_ + 1, PAINT_LINE)       # shaft
    for k_ in range(4):
        hz = az_ + dz_ * (9 + k_)
        box(ax_ - 3 + k_, ax_ + 5 - k_, YB - 1, YB, hz, hz + 1, PAINT_LINE)                 # head
for z in range(TZ0 + 2, TZ1 - 2):
    box(IX0 + 3, IX0 + 6, YB, YB + 1, z, z + 1, YELLOW_PAINT if (z // 4) % 2 else TIRE)
# ticket machine by the entry, fire hose cabinet, electrical panel, bin, cones, CCTV
box(IX0 + 2, IX0 + 7, YB, YB + 14, TZ1 + 6, TZ1 + 10, DARK_METAL)
box(IX0 + 7, IX0 + 8, YB + 9, YB + 12, TZ1 + 7, TZ1 + 9, TV_SCREEN)
box(IX0 + 7, IX0 + 8, YB + 6, YB + 7, TZ1 + 7, TZ1 + 9, YELLOW_PAINT)
box(IX0, IX0 + 2, YB + 3, YB + 15, 200, 208, RED)                  # (below the bay number)
box(IX0 + 2, IX0 + 3, YB + 4, YB + 14, 201, 207, GLASS_DOOR)
box(IX0 + 1, IX0 + 2, YB + 6, YB + 12, 202, 206, CEIL)
box(IX0 + 30, IX0 + 40, YB + 6, YB + 22, IZ0, IZ0 + 2, DARK_METAL)
box(IX0 + 33, IX0 + 37, YB + 16, YB + 19, IZ0 + 2, IZ0 + 3, YELLOW_PAINT)
box(IX0 + 3, IX0 + 7, YB, YB + 9, IZ0 + 2, IZ0 + 6, DUMPSTER)       # (the north-east corner is the turn into the ramp)
for (cx_, cz_) in ((95, 128), (95, 140), (99, 152)):             # cones parked on the stair walkway, off the aisle
    box(cx_ - 2, cx_ + 3, YB, YB + 1, cz_ - 2, cz_ + 3, TIRE)
    box(cx_ - 1, cx_ + 2, YB + 1, YB + 5, cz_ - 1, cz_ + 2, WALL_ORANGE)
    box(cx_ - 1, cx_ + 2, YB + 3, YB + 4, cz_ - 1, cz_ + 2, CEIL)
    box(cx_, cx_ + 1, YB + 5, YB + 7, cz_, cz_ + 1, WALL_ORANGE)
for (ccx, ccz) in ((IX0 + 2, IZ0 + 2), (PX1 - 6, IZ0 + 2), (IX0 + 2, PZ1 - 4), (PX1 - 6, PZ1 - 4)):
    if garage_ok(ccx, ccx + 3, ccz, ccz + 2, 0):
        box(ccx, ccx + 3, YC - 3, YC, ccz, ccz + 2, DARK_METAL)
        box(ccx + 1, ccx + 2, YC - 3, YC - 2, ccz + 1, ccz + 2, TV_BODY)
# standing water: shallow dips in the floor with real water, a wet halo, a stain on the ceiling above
def convex_hull(pts):
    pts = sorted(set(pts))
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for p_ in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p_) <= 0:
            lo.pop()
        lo.append(p_)
    for p_ in reversed(pts):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p_) <= 0:
            hi.pop()
        hi.append(p_)
    return lo[:-1] + hi[:-1]
def inside(poly, x, z):
    sg = [(poly[(i + 1) % len(poly)][0] - poly[i][0]) * (z - poly[i][1]) - (poly[(i + 1) % len(poly)][1] - poly[i][1]) * (x - poly[i][0])
          for i in range(len(poly))]
    return all(v >= 0 for v in sg) or all(v <= 0 for v in sg)
PUDDLES = []
for (pcx, pcz, rx, rz) in ((161, 198, 11, 8), (167, 338, 9, 8), (108, 296, 11, 7), (100, 243, 8, 7),
                          (205, 118, 9, 7), (150, 380, 10, 7), (100, 346, 6, 6), (172, 128, 13, 9)):
    pts = []
    for a_ in range(0, 360, 30):
        f_ = BRNG.uniform(0.7, 1.0)
        pts.append((round(pcx + rx * f_ * np.cos(np.radians(a_)), 1), round(pcz + rz * f_ * np.sin(np.radians(a_)), 1)))
    poly = convex_hull(pts)
    cells = [(x, z) for x in range(pcx - rx - 1, pcx + rx + 2) for z in range(pcz - rz - 1, pcz + rz + 2) if inside(poly, x + 0.5, z + 0.5)]
    if not all(garage_ok(x, x + 1, z, z + 1, 1) and G[x, YB - 1, z] != 0 and not (G[x, YB:YB + 2, z] > 0).any() for (x, z) in cells):
        continue
    for (x, z) in cells:
        G[x, YB - 1, z] = PUDDLE                                           # glossy standing water, flush with the floor
    for x in range(pcx - rx - 4, pcx + rx + 5):                            # wet, darker concrete around it
        for z in range(pcz - rz - 4, pcz + rz + 5):
            d_ = min(((x + 0.5 - c[0]) ** 2 + (z + 0.5 - c[1]) ** 2) for c in cells) ** 0.5
            if 0 < d_ < 3.5 and G[x, YB - 1, z] in (STAIR_CONC, PAINT_LINE, ASPHALT2) and BRNG.random() < 1.2 - d_ / 3.5:
                G[x, YB - 1, z] = ROOF
            if d_ < 2.5 and G[x, YC, z] == SLAB and BRNG.random() < 0.8:
                G[x, YC, z] = ROOF2                                        # damp patch on the ceiling
    PUDDLES.append((poly, cells))
# a slow leak above the puddle by the west wall: rusty drip line on the pipe
box(IX0 + 10, IX0 + 12, YC - 3, YC - 2, 344, 348, DUMPSTER)
SOUND_SPOTS.extend([("garage", 162, YB + 15, 150), ("garage", 162, YB + 15, 300), ("garage", 110, YB + 15, 296)])

# ============================================================================
# 8d. Back of house (v3.40): the four north rooms of the ground floor are staff space -- a kitchen (two
#     bays), a laundry and a boiler room, joined by a staff passage along their corridor side
# ============================================================================
BOH = []                                   # (name, x0, x1, z0, z1) interiors, for QA / blueprints
y = G0
bz_a, bz_c = az1 + T_FAC, az1 + T_FAC + ROOM_D            # interior z (atrium side .. corridor partition)
bxs = [ax0 + b * SHORT_BAY_W for b in range(SHORT_BAYS + 1)]
KX0, KX1 = bxs[0] + T_PART, bxs[2]                         # kitchen: bays 0 + 1
LX0, LX1 = bxs[2] + T_PART, bxs[3]                         # laundry: bay 2
BX0_, BX1_ = bxs[3] + T_PART, bxs[4]                       # boiler room: bay 3
WALK0 = bz_c - 12                                          # staff passage strip (z WALK0 .. bz_c) kept clear
box(bxs[1], bxs[1] + T_PART, y, y + FH - SLAB_T, bz_a, bz_c, 0)        # kitchen: one long room
for xw in (bxs[2], bxs[3]):                                             # passage doorways in the party walls
    box(xw, xw + T_PART, y, y + 22, bz_c - 11, bz_c - 2, 0)
    box(xw - 1, xw + T_PART + 1, y + 22, y + 23, bz_c - 12, bz_c - 1, STEEL)
    for zz in (bz_c - 12, bz_c - 2):
        box(xw - 1, xw + T_PART + 1, y, y + 22, zz, zz + 1, STEEL)
# floors, wall tiles
for x in range(KX0, KX1):
    for z in range(bz_a, bz_c):
        G[x, y - 1, z] = WHITE_TILE if ((x // 3) + (z // 3)) % 2 else TILE_DARK            # kitchen quarry tiles
paint(KX0, KX1, y, y + 12, bz_a, bz_a + 1, WHITE_TILE)
paint(LX0, BX1_, y - 1, y, bz_a, bz_c, STAIR_CONC)
paint(LX0, LX1, y, y + 12, bz_a, bz_a + 1, WHITE_TILE2)
paint(KX0, BX1_, y - 1, y, WALK0, bz_c, PAINT_LINE, [STAIR_CONC])
box(KX0, BX1_, y - 1, y, WALK0, WALK0 + 1, YELLOW_PAINT)                 # passage edge line
def boh_lamp(x0_, x1_, zc_, rgb=(0.92, 0.97, 1.0), sc=2.0):
    box(x0_, x1_, y + FH - SLAB_T - 1, y + FH - SLAB_T, zc_ - 1, zc_ + 1, STEEL)
    box(x0_ + 1, x1_ - 1, y + FH - SLAB_T - 2, y + FH - SLAB_T - 1, zc_ - 1, zc_ + 1, CEIL_LAMP)
    light((x0_ + x1_) / 2, y + FH - SLAB_T - 3.5, zc_, rgb, sc, 0.3)
# ---- kitchen
box(KX0 + 1, KX1 - 1, y, y + 8, bz_a, bz_a + 6, FRIDGE)                  # counter run under the atrium wall
box(KX0 + 1, KX1 - 1, y + 8, y + 9, bz_a, bz_a + 7, STEEL)
for x in range(KX0 + 4, KX1 - 4, 6):
    box(x, x + 1, y + 1, y + 7, bz_a + 6, bz_a + 7, CHROME)               # cupboard handles
rg0 = KX0 + 22
box(rg0, rg0 + 20, y + 8, y + 9, bz_a, bz_a + 7, DARK_METAL)               # range top + burners
for bx_ in (rg0 + 3, rg0 + 9, rg0 + 15):
    for bz__ in (bz_a + 1, bz_a + 4):
        box(bx_, bx_ + 3, y + 9, y + 10, bz__, bz__ + 2, TIRE)
box(rg0 + 1, rg0 + 19, y + 1, y + 7, bz_a + 6, bz_a + 7, CHROME)           # oven doors
box(rg0 - 1, rg0 + 21, y + 21, y + 25, bz_a, bz_a + 9, STEEL)              # extractor hood
box(rg0 + 2, rg0 + 18, y + FH - SLAB_T - 2, y + FH - SLAB_T, bz_a + 2, bz_a + 6, STEEL)    # duct
box(rg0 + 2, rg0 + 18, y + 20, y + 21, bz_a + 6, bz_a + 8, CEIL_LAMP)     # hood light
light(rg0 + 10, y + 18, bz_a + 7, (1.0, 0.9, 0.75), 1.4, 0.2)
box(rg0 + 4, rg0 + 7, y + 10, y + 13, bz_a + 2, bz_a + 5, DARK_METAL)     # stock pot
box(rg0 + 12, rg0 + 17, y + 10, y + 11, bz_a + 1, bz_a + 5, DARK_METAL)   # pan
box(rg0 + 17, rg0 + 21, y + 10, y + 11, bz_a + 2, bz_a + 3, WOOD_DARK)    # pan handle
for fx in (KX1 - 24, KX1 - 13):                                           # two tall reach-in fridges
    box(fx, fx + 10, y, y + 22, bz_a + 8, bz_a + 15, FRIDGE)
    box(fx + 4, fx + 5, y + 2, y + 21, bz_a + 15, bz_a + 16, DARK_METAL)
    box(fx + 1, fx + 9, y + 18, y + 20, bz_a + 15, bz_a + 16, TV_SCREEN if fx == KX1 - 24 else CEIL_LAMP)
box(KX0 + 26, KX0 + 52, y, y + 8, bz_a + 16, bz_a + 25, CHROME)           # prep island (shelf frame)
box(KX0 + 27, KX0 + 51, y + 1, y + 7, bz_a + 17, bz_a + 24, 0)
box(KX0 + 27, KX0 + 51, y + 3, y + 4, bz_a + 17, bz_a + 24, STEEL)
box(KX0 + 25, KX0 + 53, y + 8, y + 9, bz_a + 15, bz_a + 26, STEEL)
box(KX0 + 30, KX0 + 36, y + 9, y + 10, bz_a + 18, bz_a + 23, WOOD_LIGHT)  # chopping board
for (px_, pc_) in ((KX0 + 40, CERAMIC), (KX0 + 44, CERAMIC), (KX0 + 47, BRASS)):
    box(px_, px_ + 3, y + 9, y + 11, bz_a + 19, bz_a + 22, pc_)
rail_y = y + FH - SLAB_T - 6                                              # pot rail over the island
for rx_ in (KX0 + 28, KX0 + 50):
    box(rx_, rx_ + 1, rail_y, y + FH - SLAB_T, bz_a + 20, bz_a + 21, DARK_METAL)
box(KX0 + 28, KX0 + 51, rail_y, rail_y + 1, bz_a + 20, bz_a + 21, DARK_METAL)
for i, hx_ in enumerate(range(KX0 + 31, KX0 + 49, 4)):
    box(hx_ + 1, hx_ + 2, rail_y - 2, rail_y, bz_a + 20, bz_a + 21, DARK_METAL)
    box(hx_, hx_ + 3, rail_y - 4, rail_y - 2, bz_a + 19, bz_a + 22, BRASS if i % 2 else DARK_METAL)
box(KX0, KX0 + 5, y, y + 22, bz_a + 9, bz_a + 28, CHROME)                 # dry-store shelving
for sy in range(y + 4, y + 22, 5):
    box(KX0, KX0 + 5, sy, sy + 1, bz_a + 9, bz_a + 28, STEEL)
    for zz in range(bz_a + 10, bz_a + 27, 4):
        box(KX0 + 1, KX0 + 4, sy + 1, sy + 3, zz, zz + 3, (CARP_OR, CERAMIC, WALL_ORANGE, SHEET)[(zz + sy) % 4])
for lx_ in (KX0 + 10, KX0 + 38, KX0 + 62):
    boh_lamp(lx_, lx_ + 10, bz_a + 30)
# ---- laundry
for i in range(4):                                                         # four front-loading washers
    wx = LX0 + 1 + i * 9
    box(wx, wx + 8, y, y + 9, bz_a, bz_a + 8, FRIDGE)
    box(wx + 2, wx + 6, y + 2, y + 7, bz_a + 8, bz_a + 9, CHROME)
    box(wx + 3, wx + 5, y + 3, y + 6, bz_a + 8, bz_a + 9, GLASS)
    box(wx + 1, wx + 7, y + 8, y + 9, bz_a + 7, bz_a + 8, DARK_METAL)      # control strip
    if i < 2:                                                               # two dryers stacked on top
        box(wx, wx + 8, y + 9, y + 18, bz_a, bz_a + 8, FRIDGE)
        box(wx + 2, wx + 6, y + 11, y + 16, bz_a + 8, bz_a + 9, CHROME)
        box(wx + 3, wx + 5, y + 12, y + 15, bz_a + 8, bz_a + 9, TV_BODY)
    else:
        box(wx + 1, wx + 4, y + 9, y + 12, bz_a + 2, bz_a + 6, (WALL_BLUE, CARP_OR)[i % 2])     # detergent
box(LX0 + 8, LX1 - 8, y, y + 8, bz_a + 16, bz_a + 24, WOOD_LIGHT)          # folding table
box(LX0 + 9, LX1 - 9, y + 1, y + 7, bz_a + 17, bz_a + 23, 0)
box(LX0 + 9, LX0 + 10, y, y + 8, bz_a + 17, bz_a + 18, WOOD_DARK); box(LX1 - 10, LX1 - 9, y, y + 8, bz_a + 17, bz_a + 18, WOOD_DARK)
box(LX0 + 9, LX0 + 10, y, y + 8, bz_a + 22, bz_a + 23, WOOD_DARK); box(LX1 - 10, LX1 - 9, y, y + 8, bz_a + 22, bz_a + 23, WOOD_DARK)
for j, tx in enumerate(range(LX0 + 10, LX1 - 12, 6)):                      # towel stacks
    box(tx, tx + 5, y + 8, y + 10 + j % 3, bz_a + 18, bz_a + 22, (TOWEL, SHEET, DREAM_PINK)[j % 3])
for (cx_, cz_) in ((LX1 - 10, bz_a + 12),):                                 # linen cart, piled
    box(cx_ - 4, cx_ + 4, y + 1, y + 2, cz_ - 3, cz_ + 3, CHROME)
    for (ex_, ez_) in ((cx_ - 4, cz_ - 3), (cx_ + 3, cz_ - 3), (cx_ - 4, cz_ + 2), (cx_ + 3, cz_ + 2)):
        box(ex_, ex_ + 1, y, y + 9, ez_, ez_ + 1, CHROME)
    box(cx_ - 3, cx_ + 3, y + 2, y + 9, cz_ - 2, cz_ + 2, SHEET)
    box(cx_ - 2, cx_ + 2, y + 9, y + 10, cz_ - 1, cz_ + 1, PILLOW)
box(LX0 + 2, LX0 + 4, y - 1, y, bz_a + 12, bz_a + 14, DARK_METAL)          # floor drain
boh_lamp(LX0 + 14, LX0 + 24, bz_a + 14)
# ---- boiler room
box(BX0_, BX1_, y - 1, y, bz_a + 2, WALK0 - 2, STAIR_CONC)
for (ocx, ocz) in ((BX0_ + 10, bz_a + 13), (BX0_ + 28, bz_a + 13)):        # two boilers
    for x in range(ocx - 8, ocx + 9):
        for z in range(ocz - 8, ocz + 9):
            d_ = np.hypot(x + 0.5 - ocx, z + 0.5 - ocz)
            if d_ < 6.5:
                box(x, x + 1, y, y + 3, z, z + 1, DARK_METAL)                # plinth
                box(x, x + 1, y + 3, y + 20, z, z + 1, RED)
                for by_ in (y + 7, y + 14):
                    box(x, x + 1, by_, by_ + 1, z, z + 1, STEEL)             # bands
                if d_ < 4.5:
                    box(x, x + 1, y + 20, y + 21, z, z + 1, RED)
            elif 6.5 <= d_ < 8.0 and G[x, y - 1, z] in (STAIR_CONC, PAINT_LINE):
                G[x, y - 1, z] = YELLOW_PAINT if ((x + z) // 2) % 2 else TIRE   # hazard ring
    box(ocx - 1, ocx + 2, y + 21, y + FH - SLAB_T, ocz - 1, ocz + 2, DARK_METAL)       # flue to the ceiling
    box(ocx - 2, ocx + 3, y + 8, y + 12, ocz + 6, ocz + 7, CEIL)                        # gauge panel
    box(ocx - 1, ocx, y + 10, y + 11, ocz + 7, ocz + 8, RED)                            # needle
    box(ocx - 3, ocx + 4, y + 4, y + 7, ocz + 6, ocz + 8, DARK_METAL)                   # burner box
    box(ocx - 1, ocx + 2, y + 5, y + 6, ocz + 8, ocz + 9, EXIT_SIGN)                    # pilot light
for (pz_, pc) in ((bz_a + 2, STEEL), (bz_a + 5, RED), (bz_a + 25, YELLOW_PAINT)):        # pipes under the ceiling
    box(BX0_, BX1_, y + FH - SLAB_T - 3, y + FH - SLAB_T - 1, pz_, pz_ + 2, pc)
    for hx_ in range(BX0_ + 4, BX1_, 10):
        box(hx_, hx_ + 1, y + FH - SLAB_T - 1, y + FH - SLAB_T, pz_, pz_ + 2, DARK_METAL)   # hangers
for (vx_, vz_) in ((BX0_ + 19, bz_a + 25),):                                # riser + valve wheel
    box(vx_, vx_ + 2, y, y + FH - SLAB_T - 3, vz_, vz_ + 2, YELLOW_PAINT)
    for wx_ in range(vx_ - 4, vx_ + 6):                                      # wheel rim (a solid ring)
        for wy_ in range(y + 8, y + 17):
            if 2.6 <= np.hypot(wx_ + 0.5 - (vx_ + 1), wy_ + 0.5 - (y + 12.5)) < 3.7:
                box(wx_, wx_ + 1, wy_, wy_ + 1, vz_ - 1, vz_, RED)
    box(vx_, vx_ + 2, y + 12, y + 13, vz_ - 1, vz_, RED)
    box(vx_ - 2, vx_ + 4, y + 12, y + 13, vz_ - 1, vz_, RED)
box(BX0_ + 16, BX0_ + 22, y + FH - SLAB_T - 2, y + FH - SLAB_T, bz_a + 16, bz_a + 18, DARK_METAL)   # caged bulb
box(BX0_ + 18, BX0_ + 20, y + FH - SLAB_T - 4, y + FH - SLAB_T - 2, bz_a + 16, bz_a + 18, STREET_LMP)
light(BX0_ + 19, y + FH - SLAB_T - 5.5, bz_a + 17, (1.0, 0.72, 0.45), 1.8, 0.2)
# ---- corridor doors (steel, opening into the room), name boards above them
for (nm_, dx0) in (("KITCHEN", KX0 + 8), ("LAUNDRY", LX0 + 2), ("BOILER", BX0_ + 2)):   # name board right of each door
    fr_ = Frame(dx0, bz_a, 1, 0, 0, 1)                                     # u along +x from the door's left edge
    fr_.box(0, 9, y, y + 22, ROOM_D, ROOM_D + T_PART, 0)                          # 2.2 m, like the guest doors
    fr_.box(-1, 10, y + 22, y + 23, ROOM_D, ROOM_D + T_PART + 1, STEEL)
    fr_.box(-1, 0, y, y + 22, ROOM_D + T_PART, ROOM_D + T_PART + 1, STEEL)
    fr_.box(9, 10, y, y + 22, ROOM_D + T_PART, ROOM_D + T_PART + 1, STEEL)
    def staff_door(a, b, c, A, B, C):
        if b in (10, 11) and a == 1:
            return STEEL                                                     # handle (latch side)
        if 15 <= b <= 16:
            return YELLOW_PAINT if a % 2 else TIRE                           # hazard band
        if b in (18, 19) and 2 <= a <= 6:
            return RED                                                       # STAFF ONLY plate
        return DARK_METAL if a in (0, A - 1) or b in (0, B - 1) else HVAC
    add_door(fr_, 0, 9, y, y + 22, ROOM_D, ROOM_D + 1, staff_door, hinge=(9, ROOM_D), open_dir=(0, -1),
             tag="hoteldoor staff", stop=STEEL)
    w_ = 4 * len(nm_) - 1
    box(dx0 + 11, dx0 + 13 + w_, y + 10, y + 18, bz_c + T_PART, bz_c + T_PART + 1, DARK_METAL)   # plate
    ftext(Frame(0, bz_c + T_PART, 1, 0, 0, -1), nm_, dx0 + 12 + w_ // 2, y + 17, -1, SWITCH)   # eye level, beside the door
BOH += [("kitchen", KX0, KX1, bz_a, bz_c), ("laundry", LX0, LX1, bz_a, bz_c), ("boiler", BX0_, BX1_, bz_a, bz_c)]
SOUND_SPOTS.extend([("laundry", (LX0 + LX1) / 2, y + 8, bz_a + 10), ("boiler", (BX0_ + BX1_) / 2, y + 10, bz_a + 13)])

BOLT = ["..###", ".###.", "#####", "..##.", ".##..", "##..."]
for (fr_, y_) in ELEC_ROOMS:
    fr_.box(36, 43, y_ + 12, y_ + 20, -T_PART - 1, -T_PART, YELLOW_PAINT)        # yellow plate on the corridor side
    for r_, row in enumerate(BOLT):
        for c_, cc in enumerate(row):
            if cc == "#":
                fr_.box(37 + c_, 38 + c_, y_ + 18 - r_, y_ + 19 - r_, -T_PART - 2, -T_PART - 1, TV_BODY)
    ftext(fr_, "ELEC", 33, y_ + 27, CB - T_FAC - 1, YELLOW_PAINT)                 # inside, above the switchgear
    for uu in range(26, 35, 2):                                                    # hazard stripes on the threshold
        fr_.box(uu, uu + 1, y_ - 1, y_, -T_PART, 0, YELLOW_PAINT)

# ---- both stairwells continue down to B1 (SW -> car park, NE -> arcade)
B_GLYPH = ["##.", "#.#", "##.", "#.#", "##."]
def basement_stairs(fr, YB, digit):
    YC, G0 = YB + BASE_H - SLAB_T, YB + BASE_H          # (this storey's floor, ceiling, the floor above)
    W4 = CB - T_FAC
    fr.box(-T_PART, CB, 1, YC, -T_PART, CB, STAIR_WALL)                 # core walls under the ground slab
    fr.box(0, W4, YB, YC, 0, W4, 0)
    fr.box(15, W4, YC, G0, 0, W4, 0)                                     # stair opening through the ground slab
    fr.box(0, W4, YB - 1, YB, 0, W4, STAIR_CONC)
    fr.box(0, 15, YB - 1, YB, 0, 1, RED)
    fr.paint(-1, 0, YB, YB + 10, 0, W4, STAIR_WALL2, [STAIR_WALL]); fr.paint(W4, W4 + 1, YB, YB + 10, 0, W4, STAIR_WALL2, [STAIR_WALL])
    fr.paint(0, W4, YB, YB + 10, -1, 0, STAIR_WALL2, [STAIR_WALL]); fr.paint(0, W4, YB, YB + 10, W4, W4 + 1, STAIR_WALL2, [STAIR_WALL])
    # flight A (8 steps up to the half landing), half landing, flight B (10 steps up to the ground floor)
    for s_ in range(8):
        p0 = 12 + s_ * 3
        fr.box(p0, p0 + 3, YB + s_ * 2 - 2, YB + s_ * 2 + 2, 2, 22, STAIR_CONC)
        fr.box(p0, p0 + 1, YB + s_ * 2 + 1, YB + s_ * 2 + 2, 2, 22, DARK_METAL)
    fr.box(36, W4, YB + 14, YB + 16, 0, W4, STAIR_CONC)
    def topB(u):
        if u >= 33:
            return YB + 18
        return YB + 16 + 2 * (1 + (32 - u) // 2 + 1)
    for u in range(15, 36):
        t_ = topB(u)
        fr.box(u, u + 1, t_ - 4, t_, 24, 44, STAIR_CONC)
        if u in (15, 17, 19, 21, 23, 25, 27, 29, 31, 33):
            fr.box(u, u + 1, t_ - 1, t_, 24, 44, DARK_METAL)
    # balustrades on the stairwell side of both flights
    for u in range(12, 36):
        tA = YB + (int((u - 12) / 3) + 1) * 2
        fr.box(u, u + 1, tA + 8, tA + 11, 21, 22, STEEL)
        if u % 4 == 0:
            fr.box(u, u + 1, tA, tA + 8, 21, 22, STEEL)
        if u >= 15:
            tB = topB(u)
            fr.box(u, u + 1, tB + 8, tB + 11, 24, 25, STEEL)
            if u % 4 == 0:
                fr.box(u, u + 1, tB, tB + 8, 24, 25, STEEL)
    # door to the basement, sign, light, painted "B1"
    fr.box(-T_PART, 0, YB, YB + 22, 26, 36, 0)
    fr.box(-T_PART - 1, -T_PART, YB + 22, YB + 25, 28, 34, EXIT_SIGN)
    fr.box(0, 1, YB + 22, YB + 23, 25, 37, DARK_METAL)
    add_door(fr, -1, 0, YB, YB + 22, 26, 36, lambda a, b, c, A, B, C: steel_door(C - 1 - c, b, a, C, B, A),
             hinge=(0, 36), open_dir=(1, 0), stop=DARK_METAL)
    fr.light(4, YB + 30, 22, (1.0, 0.95, 0.85), 1.6, 0.2)
    fr.box(2, 6, YC - 1, YC, 20, 24, CEIL_LAMP)
    for gi, glyph in enumerate((B_GLYPH, DIGITS[digit])):
        for r_, row in enumerate(glyph):
            for c_, ch in enumerate(row):
                if ch == "#":
                    fr.box(W4, W4 + 1, YB + 20 - r_ * 2, YB + 22 - r_ * 2, 4 + gi * 8 + c_ * 2, 6 + gi * 8 + c_ * 2, RED)
basement_stairs(corner["SW"], YB, "1"); basement_stairs(corner["NE"], YB, "1")
# (v3.46) and on down to B2: SW -> the food street, NE -> the B2 car park
basement_stairs(corner["SW"], YB2, "2"); basement_stairs(corner["NE"], YB2, "2")
def paint_shell(x0, x1, z0, z1, y0, y1, col, only):
    paint(x0, x1, y0, y1, z0, z0 + 1, col, only); paint(x0, x1, y0, y1, z1 - 1, z1, col, only)
    paint(x0, x0 + 1, y0, y1, z0, z1, col, only); paint(x1 - 1, x1, y0, y1, z0, z1, col, only)
# the elevator cores and the NE stair core stand inside the arcade: plaster them like the arcade walls
for key_ in ("NW", "SE"):
    xa_, xb_, za_, zb_ = corner[key_]._rect(-T_PART, 22, 0, CB - T_FAC)
    paint_shell(xa_, xb_, za_, zb_, YB, YC, LOBBY_WALL, [SLAB])
    paint_shell(xa_, xb_, za_, zb_, YB, YB + 1, WOOD_DARK, [LOBBY_WALL])             # skirting
xa_, xb_, za_, zb_ = corner["NE"]._rect(-T_PART, CB, -T_PART, CB)
paint_shell(xa_, xb_, za_, zb_, YB, YC, LOBBY_WALL, [STAIR_WALL, STAIR_WALL2])
paint_shell(xa_, xb_, za_, zb_, YB, YB + 1, WOOD_DARK, [LOBBY_WALL])

# ============================================================================
# 8e. Basement B2 (v3.46/47): east half a food street (12 stalls, long tables, lanterns, neon gates) under
#     the arcade, west half a car park under the B1 car park, reached by a ramp down from B1. Both lifts and
#     both stairs come down.
# ============================================================================
B2RNG = random.Random(4646)                                   # own RNG: B2 never shifts the rest of the map
BFONT.update({"G": [".##", "#..", "#.#", "#.#", ".##"], "J": ["..#", "..#", "..#", "#.#", ".#."],
              "Q": [".#.", "#.#", "#.#", "##.", ".##"], "Z": ["###", "..#", ".#.", "#..", "###"],
              "W": ["#...#", "#...#", "#.#.#", "##.##", "#...#"], "2": ["##.", "..#", ".#.", "#..", "###"]})
def big_text(fr, s, u_mid, y_top, v, col, k=3):
    """BFONT letters scaled k x k (u to the viewer's right, front = layer v - 1)."""
    widths = [len(BFONT[ch][0]) for ch in s]
    u = u_mid - ((sum(widths) + len(s) - 1) * k) // 2
    for ch, w_ in zip(s, widths):
        for r_, row in enumerate(BFONT[ch]):
            for c_, cc in enumerate(row):
                if cc == "#":
                    fr.box(u + c_ * k, u + c_ * k + k, y_top - (r_ + 1) * k, y_top - r_ * k, v, v + 1, col)
        u += (w_ + 1) * k
FS_X0, FS_X1 = QX + 2, IX1                                    # food street (x 238..384)
CP_X0, CP_X1 = IX0, QX - 2                                    # B2 car park (x 88..234)
Y2 = YB2
SWr = corner["SW"]._rect(-T_PART, CB, -T_PART, CB)           # cores standing in B2
NWr = corner["NW"]._rect(-T_PART, 22, 0, CB - T_FAC)
SEr = corner["SE"]._rect(-T_PART, 22, 0, CB - T_FAC)
NEr = corner["NE"]._rect(-T_PART, CB, -T_PART, CB)
ST_Z0, ST_N, ST_L = 172, 6, 40                                # stall rows: z 172..412, 6 stalls of 4 m a side
ST_Z1 = ST_Z0 + ST_N * ST_L
WALK_W, WALK_E = (FS_X0 + 32, FS_X0 + 52), (FS_X1 - 52, FS_X1 - 32)   # walkways in front of the stalls
TAB_X = ((FS_X0 + FS_X1) // 2 - 5, (FS_X0 + FS_X1) // 2 + 5)  # long tables down the middle
TC = (FS_X0 + FS_X1) // 2                                      # (x 311: the street's centre line)

Xt_, Zt_ = np.meshgrid(np.arange(FS_X0, FS_X1), np.arange(IZ0, IZ1), indexing="ij")
TERRAZZO = hash3(Xt_, np.full_like(Xt_, Y2), Zt_, 31)
# ---- floors: stone tiles on the walkways, oak parquet under the tables, terrazzo courts with brass inlay
for x in range(FS_X0, FS_X1):
    for z in range(IZ0, IZ1):
        if TAB_X[0] - 8 <= x < TAB_X[1] + 8 and ST_Z0 <= z < ST_Z1:
            c_ = PARQUET if ((x // 2) + (z // 6)) % 2 else PARQUET2
        elif ST_Z0 <= z < ST_Z1 and (x < WALK_W[0] or x >= WALK_E[1]):
            c_ = WHITE_TILE if ((x // 3) + (z // 3)) % 2 else TILE_DARK          # stall kitchens
        elif ST_Z0 <= z < ST_Z1:
            c_ = BASE_STONE if ((x // 8) + (z // 8)) % 2 else BASE_STONE2
        else:
            c_ = FLOOR_MED if TERRAZZO[x - FS_X0, z - IZ0] > 0.12 else MARBLE_B
        G[x, Y2 - 1, z] = c_
for z in (ST_Z0 - 2, ST_Z1 + 1):
    box(FS_X0, FS_X1, Y2 - 1, Y2, z, z + 1, BRASS)
for x in (WALK_W[0], WALK_E[1] - 1):
    box(x, x + 1, Y2 - 1, Y2, ST_Z0, ST_Z1, BRASS)
# ceiling painted black, exposed brick on the outer walls of the courts
paint(FS_X0, FS_X1, YC2, YC2 + 1, IZ0, IZ1, CABLE)
for (xa, xb, za, zb) in ((FS_X0 - 1, FS_X0, IZ0, IZ1), (FS_X1, FS_X1 + 1, IZ0, IZ1), (FS_X0, FS_X1, IZ0 - 1, IZ0), (FS_X0, FS_X1, IZ1, IZ1 + 1)):
    for y in range(Y2, YC2):
        for x in range(xa, xb):
            for z in range(za, zb):
                if G[x, y, z] in (SLAB, STAIR_CONC, FLOOR_STN):
                    G[x, y, z] = BRICK if ((y // 2) + ((x + z) // 4 + (y // 2) % 2) // 1) % 7 else BRICK2
# exposed duct + cable tray along the hall, hung from the ceiling
box(TC - 3, TC + 3, YC2 - 4, YC2, ST_Z0 - 4, ST_Z1 + 4, STEEL)
for z in range(ST_Z0, ST_Z1, 16):
    box(TC - 4, TC + 4, YC2 - 4, YC2 - 3, z, z + 1, DARK_METAL)               # duct bands
for z in range(ST_Z0 + 8, ST_Z1, 32):
    box(TC - 2, TC + 2, YC2 - 5, YC2 - 4, z, z + 3, DARK_METAL)               # diffusers
box(TC - 17, TC - 13, YC2 - 1, YC2, ST_Z0 - 4, ST_Z1 + 4, DARK_METAL)
box(TC + 13, TC + 17, YC2 - 1, YC2, ST_Z0 - 4, ST_Z1 + 4, DARK_METAL)

# ---- the stalls
STALLS = []
def stall(fr, name, col, neon, seed):
    r_ = random.Random(seed)
    Y = Y2
    for (u0, u1) in ((0, 1), (39, 40)):                                     # tiled partitions, colour band below
        fr.box(u0, u1, Y, Y + 26, 0, 32, WHITE_TILE)
        fr.paint(u0, u1, Y, Y + 10, 0, 32, col)
        fr.box(u0, u1, Y + 26, YC2, 0, 2, TIRE)                             # (up to the ceiling at the front)
    fr.paint(1, 39, Y, Y + 22, 32, 33, WHITE_TILE)                          # tiled back wall
    fr.paint(1, 39, Y + 22, YC2, 32, 33, col)
    # counter: slatted front in the stall colour, marble top, glass display case with food, till
    fr.box(3, 37, Y, Y + 10, 0, 6, col)
    for u in range(4, 37, 3):
        fr.box(u, u + 1, Y + 1, Y + 9, 0, 1, WOOD_DARK)
    fr.box(3, 37, Y, Y + 1, -1, 6, TIRE)                                    # kick plinth
    fr.box(2, 38, Y + 10, Y + 11, -1, 7, MARBLE_W)
    fr.box(5, 19, Y + 11, Y + 15, 1, 2, GLASS)
    fr.box(5, 19, Y + 15, Y + 16, 1, 5, GLASS)
    for u in range(6, 18, 2):
        fr.box(u, u + 2, Y + 11, Y + 12 + r_.randint(0, 1), 2, 4, r_.choice((ROSE, YELLOW_PAINT, WALL_ORANGE, LEAF, SHEET, CARP_OR, BLANKET_B)))
    fr.box(27, 31, Y + 11, Y + 12, 2, 5, TV_BODY)
    fr.box(28, 30, Y + 12, Y + 15, 4, 5, TV_BODY)
    fr.box(28, 30, Y + 13, Y + 15, 3, 4, TV_SCREEN)                          # till screen
    # kitchen: steel back counter, two burners with woks, stock pot, extractor hood, menu board
    fr.box(3, 37, Y, Y + 9, 25, 31, HVAC)
    fr.box(3, 37, Y + 9, Y + 10, 25, 31, STEEL)
    for bu in (8, 15):
        fr.box(bu, bu + 4, Y + 10, Y + 11, 26, 30, DARK_METAL)
        fr.box(bu + 1, bu + 3, Y + 10, Y + 11, 27, 29, STREET_LMP)             # flame ring
        fr.box(bu, bu + 4, Y + 11, Y + 12, 26, 30, TV_BODY)                    # wok
    fr.box(22, 27, Y + 10, Y + 16, 26, 30, CHROME)
    fr.box(23, 26, Y + 15, Y + 16, 27, 29, 0)                               # (open pot)
    fr.box(29, 35, Y + 10, Y + 12, 26, 30, WOOD_LIGHT)                       # chopping board
    fr.box(3, 37, Y + 22, Y + 23, 22, 32, STEEL)                            # hood
    fr.box(3, 37, Y + 23, Y + 26, 26, 32, STEEL)
    fr.box(4, 36, Y + 12, Y + 21, 31, 32, TV_BODY)                          # menu board
    for ry in range(Y + 14, Y + 20, 2):
        fr.box(6, 6 + r_.randint(8, 16), ry, ry + 1, 30, 31, SHEET)
        fr.box(30, 34, ry, ry + 1, 30, 31, YELLOW_PAINT)
    # sign board with the neon name, striped awning, lamp under it
    fr.box(1, 39, Y + 22, Y + 31, 0, 2, TIRE)
    ftext(fr, name, 20, Y + 30, -1, neon)
    for u in (1, 2, 37, 38):
        fr.box(u, u + 1, Y + 23, Y + 30, -1, 0, neon)                           # neon side bars
    for dv in range(7):
        yy = Y + 21 - dv // 3
        for u in range(1, 39):
            fr.box(u, u + 1, yy, yy + 2, -1 - dv, -dv, col if (u // 4) % 2 else SHEET)
    for lu in (8, 20, 32):
        fr.box(lu, lu + 1, Y + 19, Y + 20, -4, -3, CABLE)
        fr.box(lu - 1, lu + 2, Y + 17, Y + 19, -5, -2, LAMPSHADE)
    fr.light(20, Y + 15.5, -4, (1.0, 0.8, 0.55), 1.5, 0.3)
    # stools at the counter
    for su in (8, 16, 24, 32):
        fr.box(su, su + 1, Y, Y + 6, -3, -2, CHROME)
        fr.box(su - 1, su + 2, Y, Y + 1, -4, -1, CHROME)
        fr.box(su - 1, su + 2, Y + 6, Y + 7, -4, -1, col)
    STALLS.append((name, fr.pt(20, -3)))
W_STALLS = [("RAMEN", RED, MEMORY), ("TACOS", YELLOW_PAINT, STREET_LMP), ("DIMSUM", DUMPSTER, EXIT_SIGN),
            ("BBQ", CAR_C, STREET_LMP), ("PHO", POOL_TILE, POOL_LAMP), ("CURRY", WALL_ORANGE, LAMPSHADE)]
E_STALLS = [("SUSHI", BLANKET_C, POOL_LAMP), ("WAFFLE", WALL_MAUVE, MEMORY), ("BOBA", ART1, COVE_LAMP),
            ("PIZZA", RED, STREET_LMP), ("KEBAB", WALL_GREEN, EXIT_SIGN), ("TTEOK", ROSE, MEMORY)]
for i, (nm, col, neon) in enumerate(W_STALLS):                 # west row: counter front at x 119, facing east
    z0 = ST_Z0 + i * ST_L
    stall(Frame(WALK_W[0] - 1, z0 + ST_L - 1, 0, -1, -1, 0), nm, col, neon, 100 + i)
for i, (nm, col, neon) in enumerate(E_STALLS):                 # east row: counter front at x 202, facing west
    z0 = ST_Z0 + i * ST_L
    stall(Frame(WALK_E[1], z0, 0, 1, 1, 0), nm, col, neon, 200 + i)

# ---- long tables with benches down the middle, planters between them, lanterns over both walkways
TABLES = [(182, 222), (238, 278), (306, 346), (362, 402)]
for (tz0, tz1) in TABLES:
    box(TAB_X[0], TAB_X[1], Y2 + 7, Y2 + 8, tz0, tz1, WOOD_MED)
    box(TAB_X[0], TAB_X[1], Y2 + 6, Y2 + 7, tz0 + 1, tz1 - 1, WOOD_DARK)
    for lz in (tz0 + 2, (tz0 + tz1) // 2, tz1 - 3):
        box(TAB_X[0] + 2, TAB_X[1] - 2, Y2, Y2 + 6, lz, lz + 1, DARK_METAL)        # trestle legs
    for (bx_a, bx_b) in ((TAB_X[0] - 5, TAB_X[0] - 2), (TAB_X[1] + 2, TAB_X[1] + 5)):
        box(bx_a, bx_b, Y2 + 4, Y2 + 5, tz0 + 1, tz1 - 1, WOOD_MED2)
        for lz in (tz0 + 3, tz1 - 4):
            box(bx_a + 1, bx_b - 1, Y2, Y2 + 4, lz, lz + 1, DARK_METAL)
    for k_ in range(3):                                                         # bowls + cups on the table
        bz_ = B2RNG.randint(tz0 + 3, tz1 - 4)
        box(TAB_X[0] + 2 + 4 * (k_ % 2), TAB_X[0] + 4 + 4 * (k_ % 2), Y2 + 8, Y2 + 9, bz_, bz_ + 2, B2RNG.choice((CERAMIC, RED, WALL_ORANGE)))
    for py_ in (Y2 + 20,):                                                      # pendant over each table
        box(TC - 1, TC + 1, py_ + 2, YC2 - 4, (tz0 + tz1) // 2, (tz0 + tz1) // 2 + 1, CABLE)
        box(TC - 3, TC + 3, py_, py_ + 2, (tz0 + tz1) // 2 - 2, (tz0 + tz1) // 2 + 3, BRASS)
        box(TC - 2, TC + 2, py_ - 1, py_, (tz0 + tz1) // 2 - 1, (tz0 + tz1) // 2 + 2, LAMPSHADE)
        light(TC, py_ - 2.5, (tz0 + tz1) / 2 + 0.5, (1.0, 0.78, 0.5), 1.6, 0.3)
def planter(cx, cz, r=3, h=6):
    box(cx - r, cx + r, Y2, Y2 + h, cz - r, cz + r, WOOD_DARK)
    box(cx - r + 1, cx + r - 1, Y2 + h - 1, Y2 + h, cz - r + 1, cz + r - 1, SOIL)
    box(cx, cx + 1, Y2 + h, Y2 + h + 8, cz, cz + 1, TRUNK)
    Xo, Yo, Zo = np.meshgrid(np.arange(cx - 5, cx + 6), np.arange(Y2 + h + 4, Y2 + h + 14), np.arange(cz - 5, cz + 6), indexing="ij")
    mo = (((Xo - cx) ** 2 + ((Yo - Y2 - h - 9) * 1.2) ** 2 + (Zo - cz) ** 2) <= 22) & (hash3(Xo, Yo, Zo, cx + cz) > 0.3)
    mo[5, :5, 5] = True
    mo = keep_connected(mo, [(5, 0, 5)]) & (G[Xo, Yo, Zo] == 0)
    G[Xo[mo], Yo[mo], Zo[mo]] = np.where((Xo[mo] + Yo[mo] + Zo[mo]) % 3 > 0, LEAF2, LEAF3)
for (tz0, tz1) in zip([t[1] for t in TABLES[:-1]], [t[0] for t in TABLES[1:]]):
    planter(TC, (tz0 + tz1) // 2)
LANTERNS = []
for lx in ((WALK_W[0] + WALK_W[1]) // 2, (WALK_E[0] + WALK_E[1]) // 2):
    for i, lz in enumerate(range(ST_Z0 + 10, ST_Z1, 20)):
        drop = 6 + (i % 2) * 2
        box(lx, lx + 1, YC2 - drop, YC2, lz, lz + 1, CABLE)
        box(lx - 1, lx + 2, YC2 - drop - 5, YC2 - drop, lz - 1, lz + 2, LAMPSHADE)
        box(lx - 1, lx + 2, YC2 - drop - 1, YC2 - drop, lz - 1, lz + 2, RED)
        box(lx - 1, lx + 2, YC2 - drop - 5, YC2 - drop - 4, lz - 1, lz + 2, RED)
        box(lx, lx + 1, YC2 - drop - 6, YC2 - drop, lz, lz + 1, BRASS)          # spine + tassel (holds the caps when the lit
                                                                                # paper is its own lamp shape)
        LANTERNS.append((lx, lz))
        if i % 2 == 0:
            light(lx + 0.5, YC2 - drop - 7.5, lz + 0.5, (1.0, 0.62, 0.42), 1.3, 0.2)

# ---- neon gates at both ends of the street: two posts, a beam, FOOD (pink) STREET (cyan)
def gate(z_beam, south):
    for (px0, px1) in ((WALK_W[0], WALK_W[0] + 3), (WALK_E[1] - 3, WALK_E[1])):
        box(px0, px1, Y2, YC2, z_beam, z_beam + 3, TIRE)
        box(px0, px1, Y2, Y2 + 2, z_beam - 1, z_beam + 4, BRASS)
    box(WALK_W[0], WALK_E[1], Y2 + 25, Y2 + 32, z_beam, z_beam + 3, TIRE)
    cx = (WALK_W[0] + WALK_E[1]) // 2
    if south:                                     # read from the south: the viewer's right is -x
        fr_ = Frame(0, z_beam - 1, -1, 0, 0, 1)
        ftext(fr_, "FOOD", -(cx + 14), Y2 + 31, 0, MEMORY); ftext(fr_, "STREET", -(cx - 9), Y2 + 31, 0, POOL_LAMP)
    else:
        fr_ = Frame(0, z_beam + 3, 1, 0, 0, -1)
        ftext(fr_, "FOOD", cx - 14, Y2 + 31, 0, MEMORY); ftext(fr_, "STREET", cx + 9, Y2 + 31, 0, POOL_LAMP)
    box(WALK_W[0] + 3, WALK_E[1] - 3, Y2 + 24, Y2 + 25, z_beam + 1, z_beam + 2, COVE_LAMP)   # glow strip under the beam
    light(cx + 0.5, Y2 + 22, z_beam + (-3 if south else 6), (0.95, 0.55, 0.9), 1.4, 0.3)
gate(ST_Z0 - 8, True)
gate(ST_Z1 + 4, False)

# ---- courts: café tables at both ends, big neon EAT on the south wall, planters
def cafe_table(cx, cz, col):
    box(cx - 3, cx + 3, Y2 + 7, Y2 + 8, cz - 3, cz + 3, MARBLE_W)
    box(cx - 2, cx + 3 - 1, Y2 + 7, Y2 + 8, cz - 4, cz - 3, MARBLE_W); box(cx - 2, cx + 2, Y2 + 7, Y2 + 8, cz + 3, cz + 4, MARBLE_W)
    box(cx, cx + 1, Y2, Y2 + 7, cz, cz + 1, BRASS)
    box(cx - 2, cx + 3, Y2, Y2 + 1, cz - 2, cz + 3, BRASS)
    for (dx, dz) in ((-6, 0), (6, 0), (0, -6), (0, 6)):
        x_, z_ = cx + dx, cz + dz
        box(x_ - 1, x_ + 2, Y2 + 4, Y2 + 5, z_ - 1, z_ + 2, col)                  # seat
        box(x_, x_ + 1, Y2, Y2 + 4, z_, z_ + 1, DARK_METAL)
        bx_ = x_ + (2 if dx > 0 else -2 if dx < 0 else 0); bz_ = z_ + (2 if dz > 0 else -2 if dz < 0 else 0)
        if dx:
            box(bx_, bx_ + 1, Y2 + 5, Y2 + 10, z_ - 1, z_ + 2, DARK_METAL)
            box(min(bx_, x_), max(bx_, x_) + 1, Y2 + 4, Y2 + 5, z_, z_ + 1, DARK_METAL)
        else:
            box(x_ - 1, x_ + 2, Y2 + 5, Y2 + 10, bz_, bz_ + 1, DARK_METAL)
            box(x_, x_ + 1, Y2 + 4, Y2 + 5, min(bz_, z_), max(bz_, z_) + 1, DARK_METAL)
S_COURT = (FS_X0, SEr[0] - 4, IZ0, ST_Z0 - 10)                # x 238..338, z 88..162 (the SE lift lobby east of it)
N_COURT = (FS_X0, NEr[0] - 4, ST_Z1 + 10, IZ1)                # x 238..312, z 422..496 (the NE stair lobby east of it)
restrooms(WC_BOX[0], WC_BOX[1], WC_BOX[2], WC_BOX[3], Y2, YC2, "B2")
for (cx_, cz_, c_) in ((FS_X0 + 18, 108, UPHOL2), (FS_X0 + 44, 108, BLANKET_B), (FS_X0 + 18, 140, BLANKET_B),
                       (FS_X0 + 44, 140, UPHOL2), (FS_X0 + 72, 146, UPHOL2),
                       (FS_X0 + 26, 444, BLANKET_C), (FS_X0 + 56, 444, UPHOL2), (FS_X0 + 56, 474, BLANKET_C)):
    cafe_table(cx_, cz_, c_)
for (px_, pz_) in ((FS_X0 + 6, IZ0 + 6), (FS_X0 + 6, ST_Z0 - 16), (FS_X0 + 6, ST_Z1 + 14), (N_COURT[1] - 4, IZ1 - 6)):
    planter(px_, pz_, r=3, h=6)
for (lx_, lz_) in ((FS_X0 + 37, 124), (FS_X0 + 41, 459)):
    box(lx_ - 3, lx_ + 4, YC2 - 1, YC2, lz_ - 3, lz_ + 4, BRASS)
    box(lx_ - 2, lx_ + 3, YC2 - 2, YC2 - 1, lz_ - 2, lz_ + 3, CEIL_LAMP)
    light(lx_ + 0.5, YC2 - 4, lz_ + 0.5, (1.0, 0.85, 0.65), 2.4, 0.4)
eat_fr = Frame(0, IZ0, 1, 0, 0, -1)                           # on the south wall, read from the north
box(FS_X0 + 10, FS_X0 + 54, Y2 + 12, Y2 + 31, IZ0, IZ0 + 1, TIRE)
big_text(eat_fr, "EAT", FS_X0 + 33, Y2 + 29, -1, MEMORY, k=3)
light(FS_X0 + 32, Y2 + 20, IZ0 + 6, (1.0, 0.5, 0.8), 1.2, 0.3)
box(N_COURT[0] + 18, N_COURT[1] - 12, Y2 + 12, Y2 + 31, IZ1 - 1, IZ1, TIRE)  # north wall: a big neon B2
nfr = Frame(0, IZ1 - 1, -1, 0, 0, 1)
big_text(nfr, "B2", -((N_COURT[0] + N_COURT[1]) // 2 + 3), Y2 + 29, -1, POOL_LAMP, k=3)
# door to the car park (automatic sliding, like the arcade's), at the north end
B2_DOOR = (470, 486)
auto_door(3, False, QX, B2_DOOR[0], B2_DOOR[1], y=Y2)
box(QX - 2, QX, Y2, Y2 + 24, B2_DOOR[0], B2_DOOR[1], 0)            # through the car-park facing too
fs_sign = Frame(FS_X0 - 1, 0, 0, -1, -1, 0)                  # read from the food street (looking -x): right is -z
ftext(fs_sign, "PARKING", -((B2_DOOR[0] + B2_DOOR[1]) // 2), Y2 + 31, -1, CEIL_LAMP)

# ---- B2 car park (under the B1 car park): ramp from B1, bays, aisle, columns, lights, signage, cars
CP_AISLE = (AISLE0, AISLE1)                                  # the same aisle line as B1 above (x 138..184)
# the ramp: B1's east bay strip slopes down along the divider from the wide south end of the B1 car park
# (room to turn in) to the open north end of B2 (cars come out heading north); solid under its deck
for z in range(R3_TOP, R3_BOT):
    ry = ramp3_y(z)
    box(R3_X0, R3_X1, ry, YC - 2, z, z + 1, 0)                 # (B1's ceiling fittings stay)
    box(R3_X0 - 2, R3_X1, Y2 - 1, ry - 1, z, z + 1, SLAB)
    box(R3_X0, R3_X1, ry - 1, ry, z, z + 1, ASPHALT2 if (z // 3) % 2 == 0 else STAIR_CONC)
    box(R3_X0 - 2, R3_X0, ry - 1, ry + 2, z, z + 1, CURB)
box(R3_X0 + 23, R3_X0 + 25, YB - 1, YB, R3_TOP - 30, R3_TOP, PAINT_LINE)
# B1 side: a 1.1 m parapet with a steel rail along the aisle and across the north end of the drop
box(R3_X0 - 2, R3_X0, YB, YB + 10, R3_TOP, R3_BOT + 2, SLAB)
box(R3_X0 - 2, R3_X1, YB, YB + 10, R3_BOT, R3_BOT + 2, SLAB)
box(R3_X0 - 2, R3_X0, YB + 10, YB + 11, R3_TOP, R3_BOT + 2, STEEL)
box(R3_X0 - 2, R3_X1, YB + 10, YB + 11, R3_BOT, R3_BOT + 2, STEEL)
for z in range(R3_TOP, R3_BOT, 6):
    paint(R3_X0 - 2, R3_X0, YB, YB + 10, z, z + 3, YELLOW_PAINT, [SLAB])
# "TO B2" on the divider at the top of the ramp (read from the B1 turn), "B1" painted big at the bottom wall
box(PX1 - 3, PX1 - 2, YB + 20, YB + 29, R3_TOP - 34, R3_TOP - 6, TIRE)
ftext(Frame(PX1 - 3, 0, 0, 1, 1, 0), "TO B2", R3_TOP - 20, YB + 27, -1, POOL_LAMP)
# B2 floor: bays, aisle, walkway from the food-street door to the NW lift lobby
W2_BAYS = [166 + i * 25 for i in range(10)]                  # against the west wall (x 88..138), between the cores
E2_BAYS = [IZ0 + 4 + i * 25 for i in range(3)]              # against the divider, south of the ramp (x 186..234)
for (bays_, xa_, xb_) in ((W2_BAYS, CP_X0, CP_AISLE[0]), (E2_BAYS, CP_AISLE[1] + 2, CP_X1)):
    for z0_ in bays_:
        for zl_ in (z0_, z0_ + 24):
            box(xa_, xb_, Y2 - 1, Y2, zl_, zl_ + 1, PAINT_LINE)
for z in range(IZ0, IZ1 - 30, 12):
    box(sum(CP_AISLE) // 2 - 1, sum(CP_AISLE) // 2 + 1, Y2 - 1, Y2, z, z + 6, YELLOW_PAINT)
box(CP_AISLE[0], CP_AISLE[0] + 1, Y2 - 1, Y2, W2_BAYS[0], W2_BAYS[-1] + 25, YELLOW_PAINT)
box(CP_AISLE[1] - 1, CP_AISLE[1], Y2 - 1, Y2, E2_BAYS[0], E2_BAYS[-1] + 25, YELLOW_PAINT)
for x in range(NWr[1], QX - 2):                              # green walkway (zebra) to the lift lobby
    for z in range(B2_DOOR[0], B2_DOOR[1]):
        G[x, Y2 - 1, z] = DUMPSTER if (x // 3) % 2 else PAINT_LINE
for x in range(CP_X0, 105):                                   # (walk to the stair door: no parking)
    for z in range(IZ0, 166):
        if G[x, Y2 - 1, z] == STAIR_CONC and G[x, Y2, z] == 0 and (x + z) % 7 == 0:
            G[x, Y2 - 1, z] = YELLOW_PAINT
for (xa_, xb_, za_, zb_) in ((CP_AISLE[0] + 4, R3_X1 - 4, R3_BOT + 8, B2_DOOR[0] - 6),):   # turning box at the ramp's foot
    box(xa_, xb_, Y2 - 1, Y2, za_, za_ + 1, YELLOW_PAINT); box(xa_, xb_, Y2 - 1, Y2, zb_ - 1, zb_, YELLOW_PAINT)
    box(xa_, xa_ + 1, Y2 - 1, Y2, za_, zb_, YELLOW_PAINT); box(xb_ - 1, xb_, Y2 - 1, Y2, za_, zb_, YELLOW_PAINT)
for (ax_, az_, dz_) in ((sum(CP_AISLE) // 2 - 1, 300, -1), (sum(CP_AISLE) // 2 - 1, 200, -1), (R3_X0 + 22, R3_BOT + 14, 1)):
    for k_ in range(9):
        box(ax_, ax_ + 2, Y2 - 1, Y2, az_ + dz_ * k_, az_ + dz_ * k_ + 1, PAINT_LINE)
    for k_ in range(4):
        hz = az_ + dz_ * (9 + k_)
        box(ax_ - 3 + k_, ax_ + 5 - k_, Y2 - 1, Y2, hz, hz + 1, PAINT_LINE)
COLS2 = []                                                    # (no columns: room to drive)
big_text(Frame(0, IZ1, -1, 0, 0, 1), "B2", -((CP_AISLE[0] + R3_X1) // 2), Y2 + 30, -1, YELLOW_PAINT, k=4)
for (cxc, czc) in COLS2:
    box(cxc - 3, cxc + 3, Y2, YC2, czc - 3, czc + 3, SLAB)
    for yy in range(Y2, Y2 + 8, 2):
        paint(cxc - 3, cxc + 3, yy, yy + 1, czc - 3, czc + 3, YELLOW_PAINT)
        paint(cxc - 3, cxc + 3, yy + 1, yy + 2, czc - 3, czc + 3, TIRE)
    face = Frame(cxc + 2, czc + 2, 0, -1, -1, 0) if cxc < sum(CP_AISLE) // 2 else Frame(cxc - 3, czc - 3, 0, 1, 1, 0)
    ftext(face, "B2", 2, Y2 + 20, -1, YELLOW_PAINT)
for (xa, xb, za, zb) in ((CP_X0 - 1, CP_X0, IZ0, IZ1), (CP_X0, CP_X1, IZ0 - 1, IZ0), (CP_X1, CP_X1 + 1, IZ0, IZ1), (CP_X0, CP_X1, IZ1, IZ1 + 1)):
    paint(xa, xb, Y2, Y2 + 10, za, zb, WALL_GREY, [SLAB])
    paint(xa, xb, Y2 + 10, Y2 + 11, za, zb, POOL_TILE, [SLAB])                 # B2 colour code: teal
paint(R3_X0 - 2, R3_X0 - 1, Y2, YB, R3_BOT, R3_TOP, WALL_GREY, [SLAB])          # the ramp's side wall
def tube2(x, z, flicker=False):
    box(x - 1, x + 2, YC2 - 1, YC2, z, z + 10, STEEL)
    box(x - 1, x, YC2 - 2, YC2 - 1, z, z + 10, CEIL_LAMP)
    box(x + 1, x + 2, YC2 - 2, YC2 - 1, z, z + 10, CEIL_LAMP)
    light(x + 0.5, YC2 - 4, z + 5, (0.86, 0.95, 1.0), 1.9, 0.3, "flicker" if flicker else "")
for i, z in enumerate((100, 175, 250, 325, 400)):
    tube2(sum(CP_AISLE) // 2, z, flicker=(i == 3))
for z in (200, 330):
    tube2(CP_X0 + 25, z)
for z in (100, 420):
    tube2(R3_X0 + 25, z)
box(CP_X0 + 30, CP_X0 + 33, YC2 - 2, YC2, 160, IZ1 - 70, STEEL)                 # sprinkler main
for (lbl_, bays_, west_) in (("C", W2_BAYS, True), ("D", E2_BAYS, False)):
    for i, z in enumerate(bays_):
        zc = z + 12
        if west_:
            ftext(Frame(CP_X0 - 1, zc + 6, 0, -1, -1, 0), lbl_ + str(i + 1), 6, Y2 + 22, -1, YELLOW_PAINT)
            box(CP_X0 + 7, CP_X0 + 9, Y2, Y2 + 1, zc - 5, zc + 5, CURB)
        else:
            ftext(Frame(CP_X1, zc - 6, 0, 1, 1, 0), lbl_ + str(i + 1), 6, Y2 + 22, -1, YELLOW_PAINT)
            box(CP_X1 - 9, CP_X1 - 7, Y2, Y2 + 1, zc - 5, zc + 5, CURB)
for (kind_, pn, side_, z0_) in (("salooncar", "car_a", "W", W2_BAYS[1]), ("suv1", "car_b", "W", W2_BAYS[7]),
                                ("castanet-500l-gt", "car_b", "W", W2_BAYS[4]), ("stationwagon", "car_c", "E", E2_BAYS[2])):
    cxp_ = CP_X0 + 28 if side_ == "W" else CP_X1 - 28
    CAR_SPOTS.append((kind_, pn, cxp_ - 10, Y2, z0_ + 12.5 - 22, -90 if side_ == "W" else 90))
# FOOD STREET over the door on the car-park side (neon on a dark board)
box(CP_X1 - 1, CP_X1, Y2 + 25, Y2 + 33, B2_DOOR[0] - 18, B2_DOOR[1] + 10, TIRE)
cp_sign = Frame(CP_X1 - 1, 0, 0, 1, 1, 0)                     # read from the car park (looking +x): right is +z
zc_ = (B2_DOOR[0] + B2_DOOR[1]) // 2 - 4
ftext(cp_sign, "FOOD", zc_ - 13, Y2 + 31, -1, MEMORY)
ftext(cp_sign, "STREET", zc_ + 9, Y2 + 31, -1, POOL_LAMP)
SOUND_SPOTS.extend([("mall", TC, Y2 + 15, z_) for z_ in (200, 300, 400)] + [("mall", FS_X0 + 37, Y2 + 15, 124), ("mall", FS_X0 + 41, Y2 + 15, 459)])
SOUND_SPOTS.extend([("garage", sum(CP_AISLE) // 2, Y2 + 15, z_) for z_ in (150, 300, 450)])
B2 = dict(food=(FS_X0, FS_X1), park=(CP_X0, CP_X1), stalls=STALLS, tables=TABLES, door=B2_DOOR, cols=COLS2,
          w_bays=W2_BAYS, e_bays=E2_BAYS, aisle=CP_AISLE, lanterns=LANTERNS, ramp=(R3_X0, R3_X1, R3_TOP, R3_BOT))

# ============================================================================
# 8f. Bowling alley (v3.49) in the room under the atrium lawn: 4 lanes with gutters, pin decks behind a
#     masking wall, scoreboards, ball racks with a reset button per lane, a snack bar and a lounge.
#     main.lua spawns the pins and balls ("bowlinglane" locations) and resets a lane on E.
# ============================================================================
BW_Z0, BW_Z1 = ZP + 3, az1                      # room interior (z), x ax0..ax1, y G0..BW_TOP
BW_TOP = PODY - SLAB_T
FOUL_Z, DECK_Z, PIT_Z, END_Z = ZP + 24, az1 - 20, az1 - 6, az1 - 1
LANE_X = [ax0 + 46, ax0 + 64, ax0 + 86, ax0 + 104]   # lane beds (12 wide): two lanes each side of the x = 236 columns
BOWL_LANES = []                                   # (lane, head pin (x, z), rack ball spots [(x, z), ...])
BOWL_BUTTONS = []                                 # (name, arr, gmin, tags) -> TAGGED_SHAPES
BRNG2 = random.Random(4949)
paint(ax0, ax1, BW_TOP, BW_TOP + 1, BW_Z0, BW_Z1, CABLE)                         # black ceiling
for (xa, xb, za, zb) in ((ax0 - 1, ax0, BW_Z0, BW_Z1), (ax1, ax1 + 1, BW_Z0, BW_Z1), (ax0, ax1, BW_Z1, BW_Z1 + 1), (ax0, ax1, BW_Z0 - 1, BW_Z0)):
    paint(xa, xb, G0, BW_TOP, za, zb, BLANKET_C)                                 # deep blue walls
    paint(xa, xb, G0 + 9, G0 + 10, za, zb, POOL_LAMP)                            # a neon line all round
# carpet: midnight blue with neon confetti
for x in range(ax0, ax1):
    for z in range(BW_Z0, BW_Z1):
        h_ = (x * 7 + z * 13 + (x * z) % 11) % 23
        G[x, G0 - 1, z] = (MEMORY if h_ == 0 else POOL_LAMP if h_ == 1 else YELLOW_PAINT if h_ == 2 else CARP_BL2 if (x + z) % 2 else CARP_BL)
for i_, lx in enumerate(LANE_X):
    for x in range(lx, lx + 12):                                                  # maple boards
        G[x, G0 - 1, FOUL_Z:DECK_Z] = WOOD_LIGHT if (x - lx) % 3 else PARQUET
    G[lx:lx + 12, G0 - 1, DECK_Z:PIT_Z] = MARBLE_W                                # pin deck
    box(lx, lx + 12, G0 - 1, G0, FOUL_Z, FOUL_Z + 1, TV_BODY)                     # foul line
    for k_ in range(-2, 3):                                                       # aiming arrows
        G[lx + 6 + 2 * k_, G0 - 1, FOUL_Z + 34 + abs(k_) * 3] = TV_BODY
        G[lx + 6 + 2 * k_, G0 - 1, FOUL_Z + 12] = TV_BODY
    for gx in (lx - 2, lx + 12):                                                  # gutters
        box(gx, gx + 2, G0 - 1, G0, FOUL_Z, PIT_Z, 0)
        box(gx, gx + 2, G0 - 2, G0 - 1, FOUL_Z, PIT_Z, STEEL)
    box(lx - 2, lx + 14, G0 - 1, G0, PIT_Z, END_Z, 0)                               # pit + its curtain
    box(lx - 2, lx + 14, G0 - 2, G0 - 1, PIT_Z, END_Z, TV_BODY)
    box(lx - 2, lx + 14, G0, G0 + 12, END_Z, END_Z + 1, TIRE)
    # pin-deck lamp under the masking wall, scoreboard over the approach
    box(lx, lx + 12, G0 + 13, G0 + 14, PIT_Z - 3, PIT_Z - 2, CEIL_LAMP)
    light(lx + 6, G0 + 11, PIT_Z - 4.5, (1.0, 0.95, 0.88), 1.6, 0.3)
    box(lx - 2, lx + 14, BW_TOP - 7, BW_TOP, FOUL_Z - 4, FOUL_Z - 3, TV_BODY)
    box(lx - 1, lx + 13, BW_TOP - 6, BW_TOP - 1, FOUL_Z - 5, FOUL_Z - 4, TV_SCREEN)
    ftext(Frame(0, FOUL_Z - 5, -1, 0, 0, 1), f"L{i_ + 1}", -(lx + 6), BW_TOP - 1, -1, CEIL_LAMP)
    pins_ = [(lx + 6 + (k_ - r_ / 2) * 3, DECK_Z + 3 + r_ * 3) for r_ in range(4) for k_ in range(r_ + 1)]
    for (px_, pz_) in pins_:
        G[int(px_), G0 - 1, int(pz_)] = TV_BODY                                    # pin spots
    BOWL_LANES.append((i_ + 1, (lx + 6, DECK_Z + 3), None))
# lane cappings with neon tops (between lanes and at both ends); the masking wall over the pin decks
for (c0, c1) in ((LANE_X[0] - 4, LANE_X[0] - 2), (LANE_X[1] - 4, LANE_X[1] - 2), (LANE_X[1] + 14, LANE_X[2] - 2),
                 (LANE_X[3] - 4, LANE_X[3] - 2), (LANE_X[3] + 14, LANE_X[3] + 16)):
    box(c0, c1, G0 - 1, G0 + 2, FOUL_Z, PIT_Z, TV_BODY)
    box(c0, c1, G0 + 2, G0 + 3, FOUL_Z, PIT_Z, COVE_LAMP)
box(LANE_X[0] - 4, LANE_X[3] + 16, G0 + 14, BW_TOP, PIT_Z - 3, PIT_Z, TV_BODY)
for i_, lx in enumerate(LANE_X):                                                   # neon lane numbers on the masking
    ftext(Frame(0, PIT_Z - 4, -1, 0, 0, 1), str(i_ + 1), -(lx + 6), G0 + 24, 0, (MEMORY, POOL_LAMP, EXIT_SIGN, STREET_LMP)[i_])
mfr = Frame(0, PIT_Z - 4, -1, 0, 0, 1)
ftext(mfr, "STRIKE", -((LANE_X[1] + LANE_X[2]) // 2 + 6), BW_TOP - 2, 0, COVE_LAMP)
# ball racks between the two lanes of each pair, with a red reset button for each lane
for p_ in range(2):
    la, lb = LANE_X[2 * p_], LANE_X[2 * p_ + 1]
    rx0, rx1 = la + 10, lb + 2                                                    # (straddles the capping)
    rz0, rz1 = FOUL_Z - 18, FOUL_Z - 4
    box(rx0, rx1, G0, G0 + 5, rz0, rz1, DARK_METAL)
    box(rx0, rx1, G0 + 5, G0 + 6, rz0, rz1, CHROME)
    box(rx0 + 1, rx1 - 1, G0 + 5, G0 + 6, rz0 + 1, rz1 - 1, TV_BODY)             # tray (the balls sit in it)
    for j_, (bx_, lane_) in enumerate(((rx0, 2 * p_), (rx1 - 5, 2 * p_ + 1))):
        spots_ = [(bx_ + 2.5, rz0 + 3.5), (bx_ + 2.5, rz0 + 9.5)]
        n_, hd_, _ = BOWL_LANES[lane_]
        BOWL_LANES[lane_] = (n_, hd_, spots_)
        ba_ = np.zeros((2, 2, 1), np.uint8); ba_[:, :, :] = RED
        BOWL_BUTTONS.append((f"bowl_reset{lane_ + 1}", ba_, (bx_ + 1, G0 + 2, rz0 - 1), f"bowlreset lane={lane_ + 1}"))
        box(bx_ + 1, bx_ + 3, G0 + 1, G0 + 2, rz0 - 1, rz0, YELLOW_PAINT)       # (a yellow sill under the button)
# lounge on the west side: neon BOWL sign, curved bench seats, tables; snack bar on the east side
box(ax0, ax0 + 1, G0 + 12, G0 + 25, BW_Z0 + 30, BW_Z0 + 72, TV_BODY)
ftext(Frame(ax0 + 1, 0, 0, -1, -1, 0), "BOWL", -(BW_Z0 + 51), G0 + 22, 0, MEMORY)
for (sz0, sz1) in ((BW_Z0 + 24, BW_Z0 + 48), (BW_Z0 + 64, BW_Z0 + 88), (BW_Z0 + 104, BW_Z0 + 128)):
    box(ax0, ax0 + 6, G0, G0 + 4, sz0, sz1, BLANKET_B)                             # bench seats along the west wall
    box(ax0, ax0 + 2, G0 + 4, G0 + 10, sz0, sz1, BLANKET_B)
    box(ax0 + 12, ax0 + 20, G0 + 6, G0 + 7, (sz0 + sz1) // 2 - 5, (sz0 + sz1) // 2 + 5, MARBLE_B)   # table
    box(ax0 + 15, ax0 + 17, G0, G0 + 6, (sz0 + sz1) // 2 - 1, (sz0 + sz1) // 2 + 1, CHROME)
box(ax0 + 14, ax0 + 19, BW_TOP - 1, BW_TOP, BW_Z0 + 74, BW_Z0 + 79, CEIL_LAMP)          # lounge downlight
light(ax0 + 16.5, BW_TOP - 3.5, BW_Z0 + 76.5, (1.0, 0.7, 0.9), 1.4, 0.3)
EB0 = LANE_X[3] + 22                                                                # snack bar along the east wall
box(EB0, EB0 + 6, G0, G0 + 11, BW_Z0 + 20, BW_Z0 + 80, TV_BODY)
box(EB0 - 1, EB0 + 6, G0 + 11, G0 + 12, BW_Z0 + 19, BW_Z0 + 81, MARBLE_W)
box(EB0 - 1, EB0, G0 + 1, G0 + 2, BW_Z0 + 20, BW_Z0 + 80, POOL_LAMP)              # neon kick strip
for sz_ in range(BW_Z0 + 24, BW_Z0 + 78, 8):
    if min(abs(sz_ - (ZP + 50)), abs(sz_ - (ZP + 100))) < 5:
        continue                                                                    # (a column stands there)
    box(EB0 - 5, EB0 - 4, G0, G0 + 8, sz_, sz_ + 1, CHROME)
    box(EB0 - 6, EB0 - 3, G0 + 8, G0 + 9, sz_ - 1, sz_ + 2, BLANKET_B)
box(ax1 - 4, ax1, G0, G0 + 20, BW_Z0 + 22, BW_Z0 + 78, DARK_METAL)                  # back fridge wall
for sz_ in range(BW_Z0 + 24, BW_Z0 + 76, 6):
    box(ax1 - 5, ax1 - 4, G0 + 6, G0 + 18, sz_, sz_ + 4, GLASS_DOOR)
    box(ax1 - 4, ax1 - 3, G0 + 8, G0 + 16, sz_ + 1, sz_ + 3, BRNG2.choice((RED, YELLOW_PAINT, LEAF, POOL_TILE)))
box(ax1 - 4, ax1 - 3, G0 + 19, G0 + 20, BW_Z0 + 22, BW_Z0 + 78, EXIT_SIGN)          # fridge light strip
light(EB0 - 2, BW_TOP - 4, BW_Z0 + 50, (0.85, 0.95, 1.0), 1.3, 0.3)
box(EB0 - 3, EB0 + 2, BW_TOP - 1, BW_TOP, BW_Z0 + 48, BW_Z0 + 53, CEIL_LAMP)
# neon sign over the door from the lounge (lounge side)
ftext(Frame(0, ZP - 1, -1, 0, 0, 1), "BOWL", -(DX0 + 5), G0 + 30, 0, MEMORY)
BOWL = dict(lanes=BOWL_LANES, x=LANE_X, foul=FOUL_Z, deck=DECK_Z, pit=PIT_Z, room=(ax0, ax1, BW_Z0, BW_Z1))

# ============================================================================
# 8g. Banquet hall "AURORA" (v3.50) on the lawn east of the pool annex, joined to the hotel's north-east
#     corridor by a glass link: foyer, 12 round tables, dance floor, stage with curtain and spots,
#     three crystal chandeliers; light switches for the hall and the stage.
# ============================================================================
HX0, HX1, HZ0, HZ1 = A_X1, W - 4, AZ0 + 4, D - 6              # outer walls (the west wall backs onto the annex)
HT = G0 + 50                                                  # roof top; ceiling underside G0 + 46
LKX0, LKX1 = bx1 - 22, bx1 + 6                                # glass link (outer x)
box(HX0, HX1, BED_Y + 1, G0, HZ0, HZ1, SLAB)
box(HX0, HX1, G0, HT, HZ0, HZ1, EXT_WALL)
box(HX0 + 4, HX1 - 4, G0, G0 + 46, HZ0 + 4, HZ1 - 4, 0)
box(HX0 - 1, HX1 + 1, HT - 2, HT, HZ0 - 1, HZ1 + 1, EXT_TRIM)
box(HX0, HX1, G0, G0 + 10, HZ0, HZ0 + 1, BASE_STONE)                              # plinth on the street side
hx0, hx1, hz0, hz1 = HX0 + 4, HX1 - 4, HZ0 + 4, HZ1 - 4       # interior
paint(hx0 - 1, hx1 + 1, G0, G0 + 46, hz0 - 1, hz1 + 1, LOBBY_WALL, [EXT_WALL])
paint(hx0 - 1, hx1 + 1, G0, G0 + 12, hz0 - 1, hz1 + 1, WAINS, [LOBBY_WALL])
paint(hx0 - 1, hx1 + 1, G0 + 12, G0 + 13, hz0 - 1, hz1 + 1, CHAIR_RAIL, [WAINS])
paint(hx0, hx1, G0 + 46, G0 + 47, hz0, hz1, CEIL)
for z in range(hz0, hz1, 20):                                                     # coffered ceiling beams
    box(hx0, hx1, G0 + 44, G0 + 46, z, z + 2, CORNICE)
for x in range(hx0, hx1, 20):
    box(x, x + 2, G0 + 44, G0 + 46, hz0, hz1, CORNICE)
# floor: red ballroom carpet with gold medallions, parquet dance floor, stage at the north end
for x in range(hx0, hx1):
    for z in range(hz0, hz1):
        m_ = ((x - hx0) % 12, (z - hz0) % 12)
        G[x, G0 - 1, z] = COR_GOLD if (abs(m_[0] - 6) + abs(m_[1] - 6) == 3) else (COR_CARP if (x + z) % 5 else COR_CARP2)
STG_Z = hz1 - 30
DF = (hx0 + 24, hx1 - 24, STG_Z - 30, STG_Z)
for x in range(DF[0], DF[1]):
    for z in range(DF[2], DF[3]):
        G[x, G0 - 1, z] = PARQUET if ((x // 4) + (z // 4)) % 2 else PARQUET2
box(hx0 + 10, hx1 - 10, G0, G0 + 6, STG_Z, hz1, WOOD_DARK)                       # stage
box(hx0 + 10, hx1 - 10, G0 + 5, G0 + 6, STG_Z, hz1, PARQUET)
for k_ in range(3):                                                                # steps up in the middle
    box((hx0 + hx1) // 2 - 8, (hx0 + hx1) // 2 + 8, G0, G0 + 2 * (k_ + 1), STG_Z - 9 + 3 * k_, STG_Z - 6 + 3 * k_, WOOD_DARK)
for x in range(hx0 + 10, hx1 - 10):                                                # red velvet curtain in folds
    box(x, x + 1, G0 + 6, G0 + 42, hz1 - 2 - (x % 3 == 0), hz1, BLANKET_B if x % 3 else CAR_C)
box(hx0 + 10, hx1 - 10, G0 + 38, G0 + 46, hz1 - 5, hz1, COR_GOLD)                   # pelmet (carries the name)
ftext(Frame(0, hz1 - 6, -1, 0, 0, 1), "AURORA", -((hx0 + hx1) // 2), G0 + 44, 0, BRASS)
box((hx0 + hx1) // 2 - 3, (hx0 + hx1) // 2 + 3, G0 + 6, G0 + 18, STG_Z + 8, STG_Z + 12, WOOD_DARK)   # lectern
box((hx0 + hx1) // 2 - 4, (hx0 + hx1) // 2 + 4, G0 + 18, G0 + 19, STG_Z + 7, STG_Z + 13, WOOD_MED)
box((hx0 + hx1) // 2, (hx0 + hx1) // 2 + 1, G0 + 19, G0 + 23, STG_Z + 9, STG_Z + 10, CHROME)          # microphone
box((hx0 + hx1) // 2 - 32, (hx0 + hx1) // 2 + 33, G0 + 40, G0 + 41, STG_Z + 2, STG_Z + 4, DARK_METAL)   # lighting truss
for sx_ in ((hx0 + hx1) // 2 - 30, (hx0 + hx1) // 2, (hx0 + hx1) // 2 + 30):
    box(sx_, sx_ + 1, G0 + 41, G0 + 46, STG_Z + 2, STG_Z + 3, DARK_METAL)
    box(sx_ - 1, sx_ + 2, G0 + 37, G0 + 40, STG_Z + 2, STG_Z + 4, DARK_METAL)
    box(sx_ - 1, sx_ + 2, G0 + 37, G0 + 38, STG_Z + 4, STG_Z + 5, CEIL_LAMP)
    light(sx_ + 0.5, G0 + 35.5, STG_Z + 5.5, (1.0, 0.92, 0.8), 1.6, 0.2, "room=stage rl=ceil")
# round banquet tables (white cloth, flowers, a candle) with eight gold chairs each
def banquet_table(cx, cz, r=6):
    for x in range(cx - r, cx + r + 1):
        for z in range(cz - r, cz + r + 1):
            d_ = ((x - cx) ** 2 + (z - cz) ** 2) ** 0.5
            if d_ <= r:
                box(x, x + 1, G0 + 7, G0 + 8, z, z + 1, SHEET)
                if d_ > r - 1:
                    box(x, x + 1, G0 + 4, G0 + 7, z, z + 1, SHEET)                    # cloth drop
    box(cx, cx + 1, G0, G0 + 7, cz, cz + 1, DARK_METAL)
    box(cx - 1, cx + 2, G0 + 8, G0 + 10, cz - 1, cz + 2, LEAF2)
    box(cx, cx + 1, G0 + 10, G0 + 11, cz, cz + 1, ROSE)
    for a_ in range(0, 360, 45):
        sx_ = cx + int(round(9 * np.cos(np.radians(a_)))); sz_ = cz + int(round(9 * np.sin(np.radians(a_))))
        box(sx_ - 1, sx_ + 1, G0 + 4, G0 + 5, sz_ - 1, sz_ + 1, UPHOL2)
        for (lx_, lz_) in ((sx_ - 1, sz_ - 1), (sx_, sz_)):
            box(lx_, lx_ + 1, G0, G0 + 4, lz_, lz_ + 1, BRASS)
        bx_ = sx_ + int(round(np.cos(np.radians(a_)))); bz_ = sz_ + int(round(np.sin(np.radians(a_))))
        c_, s_ = np.cos(np.radians(a_)), np.sin(np.radians(a_))
        if abs(c_) >= abs(s_):
            bx_ = sx_ + 1 if c_ > 0 else sx_ - 2
            box(bx_, bx_ + 1, G0 + 4, G0 + 11, sz_ - 1, sz_ + 1, BRASS)
        else:
            bz_ = sz_ + 1 if s_ > 0 else sz_ - 2
            box(sx_ - 1, sx_ + 1, G0 + 4, G0 + 11, bz_, bz_ + 1, BRASS)
BQ_TABLES = [(x_, z_) for z_ in range(hz0 + 40, STG_Z - 40, 30) for x_ in (hx0 + 20, (hx0 + hx1) // 2, hx1 - 20)]
for (tx_, tz_) in BQ_TABLES:
    banquet_table(tx_, tz_)
# crystal chandeliers on the hall's circuit, a long buffet in the foyer, a coat rack, the hall light switches
for cz_ in (hz0 + 60, (hz0 + STG_Z) // 2 + 10, STG_Z - 20):
    cx_ = (hx0 + hx1) // 2
    box(cx_, cx_ + 1, G0 + 38, G0 + 46, cz_, cz_ + 1, BRASS)
    box(cx_ - 6, cx_ + 7, G0 + 37, G0 + 38, cz_ - 6, cz_ + 7, BRASS)
    box(cx_ - 5, cx_ + 6, G0 + 37, G0 + 38, cz_ - 5, cz_ + 6, 0)
    box(cx_, cx_ + 1, G0 + 37, G0 + 38, cz_ - 6, cz_ + 7, BRASS); box(cx_ - 6, cx_ + 7, G0 + 37, G0 + 38, cz_, cz_ + 1, BRASS)
    for (dx_, dz_) in ((-6, -6), (6, -6), (-6, 6), (6, 6), (0, -6), (0, 6), (-6, 0), (6, 0)):
        box(cx_ + dx_, cx_ + dx_ + 1, G0 + 34, G0 + 37, cz_ + dz_, cz_ + dz_ + 1, CEIL_LAMP)
    box(cx_ - 1, cx_ + 2, G0 + 33, G0 + 37, cz_ - 1, cz_ + 2, CEIL_LAMP)
    light(cx_ + 0.5, G0 + 31.5, cz_ + 0.5, (1.0, 0.88, 0.68), 2.6, 0.4, "room=banquet rl=ceil")
box(hx0 + 4, hx0 + 40, G0, G0 + 8, hz0 + 6, hz0 + 12, WOOD_DARK)                 # buffet / registration
box(hx0 + 3, hx0 + 41, G0 + 8, G0 + 9, hz0 + 5, hz0 + 13, SHEET)
for bu_ in range(hx0 + 6, hx0 + 38, 6):
    box(bu_, bu_ + 4, G0 + 9, G0 + 11, hz0 + 7, hz0 + 11, CHROME)                    # chafing dishes
box(hx1 - 8, hx1 - 7, G0, G0 + 20, hz0 + 8, hz0 + 9, BRASS)                         # coat rack
box(hx1 - 11, hx1 - 4, G0 + 19, G0 + 20, hz0 + 8, hz0 + 9, BRASS)
# tall windows on the east wall with velvet drapes
for wz_ in range(hz0 + 20, STG_Z - 10, 30):
    box(hx1, HX1, G0 + 8, G0 + 38, wz_, wz_ + 10, 0)
    box(hx1 + 2, hx1 + 3, G0 + 8, G0 + 38, wz_, wz_ + 10, GLASS_EXT)
    box(hx1 + 2, hx1 + 3, G0 + 8, G0 + 38, wz_ + 5, wz_ + 6, FRAME)
    box(hx1 - 1, hx1, G0 + 6, G0 + 42, wz_ - 3, wz_, BLANKET_B); box(hx1 - 1, hx1, G0 + 6, G0 + 42, wz_ + 10, wz_ + 13, BLANKET_B)
# the glass link from the hotel's north-east corridor; the door into the hall
box(LKX0 - 2, LKX1 + 2, G0, G0 + 40, bz1, HZ0, 0)
box(LKX0, LKX1, BED_Y + 1, G0, bz1, HZ0, SLAB)
for x in range(LKX0 + 2, LKX1 - 2):
    for z in range(bz1, HZ0):
        G[x, G0 - 1, z] = MARBLE_W if ((x // 4) + (z // 4)) % 2 else MARBLE_B
for xw in (LKX0, LKX1 - 2):
    box(xw, xw + 2, G0, G0 + 28, bz1, HZ0, FRAME)
    box(xw, xw + 2, G0 + 1, G0 + 27, bz1 + 1, HZ0 - 1, 0)
    box(xw + (1 if xw == LKX0 else 0), xw + (2 if xw == LKX0 else 1), G0 + 1, G0 + 27, bz1 + 1, HZ0 - 1, GLASS_EXT)
    for z in range(bz1, HZ0, 8):
        box(xw, xw + 2, G0, G0 + 28, z, z + 1, FRAME)
box(LKX0, LKX1, G0 + 28, G0 + 31, bz1, HZ0, SLAB)
box(LKX0 - 1, LKX1 + 1, G0 + 30, G0 + 31, bz1, HZ0, EXT_TRIM)
LD = ((LKX0 + LKX1) // 2 - 6, (LKX0 + LKX1) // 2 + 6)                             # door gaps (hotel side, hall side)
box(LD[0], LD[1], G0, G0 + 22, bz1 - T_EXT - 1, bz1 + 3, 0)
box(LD[0] - 1, LD[1] + 1, G0 + 22, G0 + 24, bz1 - T_EXT - 1, bz1, LINTEL)
box(LD[0], LD[1], G0, G0 + 24, HZ0, hz0, 0)
box(LD[0] - 1, LD[1] + 1, G0 + 24, G0 + 26, HZ0, hz0, BRASS)
box((LKX0 + LKX1) // 2 - 1, (LKX0 + LKX1) // 2 + 2, G0 + 27, G0 + 28, (bz1 + HZ0) // 2 - 1, (bz1 + HZ0) // 2 + 2, CEIL_LAMP)
light((LKX0 + LKX1) / 2 + 0.5, G0 + 25.5, (bz1 + HZ0) / 2 + 0.5, (1.0, 0.9, 0.75), 1.4, 0.3)
BANQUET_SWITCHES = []
for (nm_, rm_, sx_) in (("banquet_switch", "banquet", LD[1] + 2), ("stage_switch", "stage", LD[1] + 6)):
    a_ = np.full((2, 3, 1), SWITCH, np.uint8); a_[:, 1, 0] = DARK_METAL if rm_ == "banquet" else RED
    BANQUET_SWITCHES.append((nm_, a_, (sx_, G0 + 11, hz0), f"roomswitch room={rm_} on=1 tv=0"))
BANQUET = dict(x=(hx0, hx1), z=(hz0, hz1), stage=STG_Z, tables=BQ_TABLES, link=(LKX0, LKX1), door=LD)

# music for the arcade (the player's song, looped from the nearest speaker)
for (sx_, sz_) in ((310, 140), (310, 260), (310, 380), (310, 470), (185, 462), (180, 414), (372, 130)):
    SOUND_SPOTS.append(("mall", sx_, YB + 15, sz_))

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
for (c1_, c2_, sd_) in ((CARP_OR, CARP_OR2, 81), (CARP_G, CARP_G2, 82), (CARP_BL, CARP_BL2, 83), (CARP_PK, CARP_PK2, 84), (CARP_DK, CARP_DK2, 85)):
    vary(c1_, [c1_, c2_], seed=sd_, weights=[4, 1])
vary(RUG, [RUG, RUG2], seed=9, weights=[3, 1])
vary(WOOD_DARK, [WOOD_DARK, WOOD_DARK2], cell=(1, 3, 1), seed=10, weights=[2, 1])
vary(WOOD_MED, [WOOD_MED, WOOD_MED2], cell=(1, 3, 1), seed=11, weights=[2, 1])
vary(ROOF, [ROOF, ROOF2], cell=(8, 1, 8), seed=12)
vary(EXT_TRIM, [EXT_TRIM, EXT_TRIM2], cell=(4, 2, 4), seed=13, weights=[3, 1])
vary(BASE_STONE, [BASE_STONE, BASE_STONE2], cell=(6, 3, 6), seed=14)

def face_axes(mask):
    """for each True voxel: which axis has open air next to it (0 = x, 1 = y, 2 = z, -1 = buried)."""
    X, Y, Z = np.nonzero(mask)
    ax = np.full(len(X), -1, np.int8)
    for a_, (dx, dy, dz) in ((1, (0, 1, 0)), (1, (0, -1, 0)), (0, (1, 0, 0)), (0, (-1, 0, 0)), (2, (0, 0, 1)), (2, (0, 0, -1))):
        nx, ny, nz = (X + dx).clip(0, W - 1), (Y + dy).clip(0, H - 1), (Z + dz).clip(0, D - 1)
        open_ = (G[nx, ny, nz] == 0) & (ax < 0)
        ax[open_] = a_
    return X, Y, Z, ax

def grout(base, line, step):
    """square tiles with grout lines in the plane of each visible face."""
    X, Y, Z, ax = face_axes(G == base)
    on = ((ax == 1) & ((X % step == 0) | (Z % step == 0))) | ((ax == 0) & ((Y % step == 0) | (Z % step == 0))) | \
         ((ax == 2) & ((X % step == 0) | (Y % step == 0)))
    G[X[on], Y[on], Z[on]] = line

def speckle(base, specks, seed):
    """per-voxel noise: specks = [(colour, fraction), ...]."""
    X, Y, Z = np.nonzero(G == base)
    t = hash3(X, Y, Z, seed)
    acc = 0.0
    for col, frac in specks:
        m = (t >= acc) & (t < acc + frac)
        G[X[m], Y[m], Z[m]] = col
        acc += frac

def blotch(base, col, cell, frac, seed, mix=0.35):
    """soft patches (stains, weathering): cell-level choice broken up by per-voxel noise."""
    X, Y, Z = np.nonzero(G == base)
    t = (1 - mix) * hash3(X // cell, Y // cell, Z // cell, seed) + mix * hash3(X, Y, Z, seed + 7)
    m = t < frac
    G[X[m], Y[m], Z[m]] = col

def wallpaper(base, motif, step):
    """thin diamond trellis in a slightly different tone on wall faces."""
    X, Y, Z, ax = face_axes(G == base)
    h = np.where(ax == 0, Z, X)
    m = (ax != 1) & (ax >= 0) & ((((h + Y) % step) == 0) | (((h - Y) % step) == 0))
    G[X[m], Y[m], Z[m]] = motif

def marble_veins(bases, vein, n, seed):
    """meandering veins across polished stone floors (random walks over the floor surface)."""
    rr = random.Random(seed)
    X, Y, Z = np.nonzero(np.isin(G, bases))
    top = G[X, (Y + 1).clip(0, H - 1), Z] == 0
    X, Y, Z = X[top], Y[top], Z[top]
    if not len(X):
        return
    for _ in range(n):
        i = rr.randrange(len(X))
        x, y, z = int(X[i]), int(Y[i]), int(Z[i])
        ang = rr.uniform(0, 6.283)
        for _s in range(rr.randint(10, 40)):
            if G[x, y, z] in bases:
                G[x, y, z] = vein
            ang += rr.uniform(-0.6, 0.6)
            x += int(round(np.cos(ang))); z += int(round(np.sin(ang)))
            if not (0 <= x < W and 0 <= z < D):
                break

# diamond-trellis wallpaper in the rooms (thin lines, no per-voxel noise on walls / ceilings / concrete)
wallpaper(ROOM_WALL, COR_WALL, 12)
wallpaper(ROOM_WALL_B, STAIR_WALL, 12)
wallpaper(ROOM_WALL_C, ATR_SEAM, 12)
# brick facade: a few darker burnt bricks
blotch(BRICK2, BRICK3, 1, 0.12, 211, mix=0.0)
# lawn: mixed grass tones
speckle(LAWN, [(LEAF3, 0.10), (LAWN2, 0.15)], 216)
# floors: bathroom tiles with grout, veins in the white marble
grout(TILE, TILE_DARK, 5)
marble_veins([MARBLE_W, MARBLE_W2], MARBLE_VEIN, 260, 220)

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

def make_pin():
    a = np.zeros((2, 5, 2), np.uint8)
    a[:, :, :] = CERAMIC
    a[:, 3, :] = RED                                  # the red neck stripe
    return a

def make_bball(col):
    r = 2
    a = np.zeros((5, 5, 5), np.uint8)
    for x in range(5):
        for y in range(5):
            for z in range(5):
                if (x - r) ** 2 + (y - r) ** 2 + (z - r) ** 2 <= r * r + 1.5:
                    a[x, y, z] = col
    a[2, 4, 1] = TV_BODY; a[1, 4, 2] = TV_BODY; a[3, 4, 2] = TV_BODY        # finger holes
    return a

PROP_SHAPES = {"car_a": make_car(CAR_A), "car_b": make_car(CAR_B), "car_c": make_car(CAR_C), "luggage_cart": make_cart(),
               "beach_ball": make_ball(), "swim_ring": make_ring(), "kickboard": make_kickboard(),
               "crate": make_crate(), "barrel": make_barrel(), "sofa": make_sofa(), "crt_tv": make_crt(),
               "bowling_pin": make_pin(), "bowling_ball": make_bball(BALL_R), "bowling_ball2": make_bball(BALL_B)}
PROP_TAGS = {"bowling_pin": "bowlpin", "bowling_ball": "bowlball", "bowling_ball2": "bowlball"}
PROP_DENSITY = {"bowling_ball": 0.3, "bowling_ball2": 0.3}       # (heavy-metal look, a 6-7 kg ball to throw)
SPAWNABLE = [("car_a", "Car (blue)"), ("car_b", "Car (silver)"), ("car_c", "Car (red)"), ("luggage_cart", "Luggage cart"),
             ("beach_ball", "Beach ball"), ("swim_ring", "Swim ring"), ("kickboard", "Kickboard"),
             ("crate", "Wooden crate"), ("barrel", "Red barrel"), ("sofa", "Lobby sofa"), ("crt_tv", "Old TV"),
             ("bowling_pin", "Bowling pin"), ("bowling_ball", "Bowling ball (red)"), ("bowling_ball2", "Bowling ball (blue)")]

# ============================================================================
# 10b. Street south of the parking lot (beyond the original grid edge z = 0):
#      its own voxel grid ROAD (local z 0..RD, grid z = local z - RD), exported as separate shapes.
# ============================================================================
RD = 150
RH = G0 + 64
ROAD = np.zeros((W, RH, RD), np.uint8)
ROAD_LAMPS = []          # (arr, gmin_grid, light (gx, gy, gz_grid))
ROAD_CARS = []           # (kind, fallback, centre x, ground y, centre z_grid, yaw)
RRNG = random.Random(613)
def rb(x0, x1, y0, y1, z0, z1, c):
    xa, xb = sorted((int(x0), int(x1))); ya, yb = sorted((int(y0), int(y1))); za, zb = sorted((int(z0), int(z1)))
    ROAD[max(xa, 0):min(xb, W), max(ya, 0):min(yb, RH), max(za, 0):min(zb, RD)] = c
# ground: same layers as the site (bedrock, earth, asphalt on top -> surface at G0)
rb(0, W, BED_Y, BED_Y + 1, 0, RD, BEDROCK); rb(0, W, BED_Y + 1, G0 - 3, 0, RD, SOIL); rb(0, W, G0 - 3, G0, 0, RD, ASPHALT)
XR = np.arange(W)[:, None]; ZR = np.arange(RD)[None, :]
tex = hash3(np.broadcast_to(XR, (W, RD)), np.zeros((W, RD), int), np.broadcast_to(ZR, (W, RD)), 77)
ROAD[:, G0 - 1, :] = np.where(tex < 0.25, ASPHALT2, ASPHALT)
NS0, NS1 = 128, RD          # north sidewalk (along the parking lot)
NC0 = 126                   # north curb
RZ0, RZ1 = 54, 126          # carriageway (2 x 3.6 m)
SC0 = 52                    # south curb
SS0, SS1 = 26, 52           # south sidewalk
DRIVEWAYS = [(70, 170), (300, 400), (4, 58)]          # (the last: the car-park ramp)
def on_drive(x):
    return any(a <= x < b for (a, b) in DRIVEWAYS)
for x in range(W):
    if on_drive(x):
        continue
    rb(x, x + 1, G0, G0 + 1, NS0, NS1, PAVER if (x // 6) % 2 == 0 else PAVER2)
    rb(x, x + 1, G0 - 1, G0 + 1, NC0, NS0, CURB)
for (a, b) in DRIVEWAYS:                     # flush driveway with dropped curbs at its sides
    rb(a - 2, a, G0 - 1, G0 + 1, NC0, NS1, CURB); rb(b, b + 2, G0 - 1, G0 + 1, NC0, NS1, CURB)
for x in range(W):
    rb(x, x + 1, G0, G0 + 1, SS0, SS1, PAVER if ((x // 6) + 1) % 2 == 0 else PAVER2)
rb(0, W, G0 - 1, G0 + 1, SC0, RZ0, CURB)
# markings: edge lines, double yellow centre line, zebra crossing in front of the hotel entrance
rb(0, W, G0 - 1, G0, RZ0 + 3, RZ0 + 4, PAINT_LINE); rb(0, W, G0 - 1, G0, RZ1 - 4, RZ1 - 3, PAINT_LINE)
MID = (RZ0 + RZ1) // 2
rb(0, W, G0 - 1, G0, MID - 2, MID - 1, YELLOW_PAINT); rb(0, W, G0 - 1, G0, MID + 1, MID + 2, YELLOW_PAINT)
ENT = (bx0 + bx1) // 2
for x in range(ENT - 24, ENT + 24, 5):
    rb(x, x + 3, G0 - 1, G0, RZ0 + 2, RZ1 - 2, PAINT_LINE)
for x in range(ENT - 26, ENT + 26):                      # dropped curbs at the crossing
    rb(x, x + 1, G0 - 1, G0, NC0, NS0, CURB); rb(x, x + 1, G0 - 1, G0, SC0, RZ0, CURB)
    rb(x, x + 1, G0, G0 + 1, NC0, NS0, 0); rb(x, x + 1, G0, G0 + 1, SC0, RZ0, 0)
# manholes, storm drains
for (mx, mz) in ((150, MID + 10), (330, MID - 12), (40, MID - 10)):
    for dx in range(-3, 4):
        for dz in range(-3, 4):
            if dx * dx + dz * dz <= 10:
                rb(mx + dx, mx + dx + 1, G0 - 1, G0, mz + dz, mz + dz + 1, DARK_METAL if (dx + dz) % 2 else TIRE)
for x in range(30, W - 30, 80):
    for z0_ in (RZ0, RZ1 - 2):
        rb(x, x + 6, G0 - 1, G0, z0_, z0_ + 2, TIRE)
        for gx in range(x, x + 6, 2):
            rb(gx, gx + 1, G0 - 1, G0, z0_, z0_ + 2, DARK_METAL)
# street lamps on the south sidewalk (heads are separate lamp shapes), trees in pits between them
for x in range(40, W - 20, 90):
    rb(x - 1, x + 3, G0 + 1, G0 + 3, SS1 - 6, SS1 - 2, DARK_METAL)
    rb(x, x + 2, G0 + 1, G0 + 50, SS1 - 5, SS1 - 3, DARK_METAL)
    rb(x, x + 2, G0 + 48, G0 + 50, SS1 - 3, SS1 + 6, DARK_METAL)              # arm over the road
    head = np.full((4, 2, 4), STREET_LMP, np.uint8)
    ROAD_LAMPS.append((head, (x - 1, G0 + 46, SS1 + 3 - RD), (x + 1, G0 + 45, SS1 + 5 - RD)))
for x in range(85, W - 20, 90):
    rb(x - 5, x + 6, G0 - 1, G0 + 1, SS0 + 6, SS0 + 17, CURB)
    rb(x - 4, x + 5, G0, G0 + 1, SS0 + 7, SS0 + 16, SOIL)
    rb(x, x + 2, G0 + 1, G0 + 40, SS0 + 11, SS0 + 13, TRUNK)
    R_ = 12
    X3, Y3, Z3 = np.meshgrid(np.arange(-R_, R_ + 1), np.arange(-R_, R_ + 1), np.arange(-R_, R_ + 1), indexing="ij")
    can = np.zeros(X3.shape, bool)
    for _ in range(7):
        ox, oy, oz = RRNG.randint(-5, 5), RRNG.randint(-3, 4), RRNG.randint(-5, 5); rr = RRNG.randint(5, 7)
        can |= (X3 - ox) ** 2 + ((Y3 - oy) ** 2) * 1.3 + (Z3 - oz) ** 2 <= rr * rr
    can &= hash3(X3 + x, Y3, Z3, 9) > 0.2
    can[R_, :R_ + 1, R_] = True
    can = keep_connected(can, [(R_, 0, R_)])
    cy, cz = G0 + 40 + 6, SS0 + 12
    for (i, j, k) in zip(*np.nonzero(can)):
        gx, gy, gz = x + i - R_, cy + j - R_, cz + k - R_
        if 0 <= gx < W and gy < RH and 0 <= gz < RD and ROAD[gx, gy, gz] == 0:
            ROAD[gx, gy, gz] = LEAF if hash3(np.array([gx]), np.array([gy]), np.array([gz]), 3)[0] < 0.5 else LEAF2
    rb(x, x + 2, G0 + 30, cy, SS0 + 11, SS0 + 13, TRUNK)                          # trunk up into the crown
# bus stop: shelter, bench, timetable, sign
BS = 300
rb(BS, BS + 40, G0 + 1, G0 + 26, SS0 + 2, SS0 + 3, GLASS_EXT)                     # back glass
for px in (BS, BS + 39):
    rb(px, px + 1, G0 + 1, G0 + 26, SS0 + 2, SS0 + 14, STEEL)
rb(BS - 1, BS + 41, G0 + 26, G0 + 27, SS0 + 1, SS0 + 16, STEEL)                    # roof
rb(BS + 4, BS + 36, G0 + 5, G0 + 6, SS0 + 4, SS0 + 8, WOOD_MED)                    # bench
for px in (BS + 5, BS + 34):
    rb(px, px + 1, G0 + 1, G0 + 5, SS0 + 4, SS0 + 8, STEEL)
rb(BS + 36, BS + 38, G0 + 8, G0 + 20, SS0 + 3, SS0 + 4, CEIL)                      # timetable
rb(BS + 44, BS + 46, G0 + 1, G0 + 34, SS1 - 5, SS1 - 3, STEEL)                     # sign post
rb(BS + 35, BS + 50, G0 + 26, G0 + 34, SS1 - 3, SS1 - 2, BLANKET_C)
for ci, ch in enumerate("BUS"):                                                     # white letters facing the road (+z)
    for r_, row in enumerate(BFONT[ch]):
        for c_, cc in enumerate(row):
            if cc == "#":
                rb(BS + 47 - ci * 4 - c_, BS + 48 - ci * 4 - c_, G0 + 32 - r_, G0 + 33 - r_, SS1 - 2, SS1 - 1, CEIL)
# south edge: low brick wall with an iron fence, hedge in front, lawn behind
rb(0, W, G0, G0 + 1, 0, SS0, LAWN)
rb(0, W, G0, G0 + 8, 14, 18, BRICK); rb(0, W, G0 + 8, G0 + 9, 13, 19, LINTEL)
for x in range(0, W, 8):
    rb(x, x + 1, G0 + 9, G0 + 20, 15, 17, DARK_METAL)
rb(0, W, G0 + 18, G0 + 19, 15, 17, DARK_METAL)
for x in range(W):
    h_ = 6 + int(3 * hash3(np.array([x // 3]), np.array([0]), np.array([0]), 21)[0])
    rb(x, x + 1, G0 + 1, G0 + 1 + h_, 19, SS0, LEAF3 if (x // 5) % 3 else LEAF)
# both road ends are closed: striped barricades + cones (the map ends there)
for x0_ in (3, W - 9):
    for z in range(RZ0 + 4, RZ1 - 4, 14):
        rb(x0_, x0_ + 1, G0, G0 + 9, z, z + 1, WOOD_DARK); rb(x0_, x0_ + 1, G0, G0 + 9, z + 10, z + 11, WOOD_DARK)
        for k in range(10):
            rb(x0_ + 1, x0_ + 2, G0 + 6, G0 + 9, z + k, z + k + 1, RED if (k // 2) % 2 else CEIL)
    for z in range(RZ0 + 6, RZ1 - 6, 10):
        cx_ = x0_ + (5 if x0_ < 10 else -4)
        rb(cx_ - 2, cx_ + 3, G0, G0 + 1, z - 2, z + 3, TIRE)
        rb(cx_ - 1, cx_ + 2, G0 + 1, G0 + 6, z - 1, z + 2, WALL_ORANGE)
        rb(cx_ - 1, cx_ + 2, G0 + 3, G0 + 4, z - 1, z + 2, CEIL)
# a van parked at the south kerb (base-game vehicle, along the road)
ROAD_CARS.append(("van", "car_a", 410, G0, SC0 + 14 - RD, 90))

# ============================================================================
# 10c. Upper roof: stairs from the room-ring roof, helipad, flyable helicopter
# ============================================================================
RT = ATR_TOP + 4                  # walking surface of the upper (atrium) roof
STX0, STX1 = 250, 262             # stairs: up the south side, ending at the upper roof's edge
STZ_TOP = az0 - 5                 # last tread (the upper roof starts 4 voxels south of az0)
box(STX0 - 1, STX1 + 1, ROOF_Y, RT + 9, STZ_TOP - 40, STZ_TOP + 1, 0)         # clear (a wall vent sat here)
for s_ in range(13):
    z0_ = STZ_TOP - 38 + s_ * 3
    box(STX0, STX1, ROOF_Y, ROOF_Y + 2 * (s_ + 1), z0_, z0_ + 3, STEEL)
    box(STX0, STX1, ROOF_Y + 2 * s_ + 1, ROOF_Y + 2 * (s_ + 1), z0_, z0_ + 1, YELLOW_PAINT)   # step nosing
for xr in (STX0 - 1, STX1):
    for s_ in range(0, 13, 2):
        z0_ = STZ_TOP - 38 + s_ * 3
        box(xr, xr + 1, ROOF_Y, ROOF_Y + 2 * (s_ + 1) + 9, z0_, z0_ + 1, STEEL)
    for s_ in range(13):
        z0_ = STZ_TOP - 38 + s_ * 3
        box(xr, xr + 1, ROOF_Y + 2 * (s_ + 1) + 7, ROOF_Y + 2 * (s_ + 1) + 9, z0_, z0_ + 3, STEEL)
# helipad on the upper roof: dark pad, yellow ring, white H, green edge lights
HCX, HCZ = (ax0 + ax1) // 2, (az0 + az1) // 2
for x in range(HCX - 72, HCX + 73):
    for z in range(HCZ - 72, HCZ + 73):
        d_ = ((x - HCX) ** 2 + (z - HCZ) ** 2) ** 0.5
        if d_ <= 70 and G[x, RT - 1, z]:
            G[x, RT - 1, z] = YELLOW_PAINT if 56 <= d_ <= 60 else (PAINT_LINE if 66 <= d_ <= 68 else ASPHALT)
box(HCX - 16, HCX - 10, RT - 1, RT, HCZ - 22, HCZ + 22, PAINT_LINE)
box(HCX + 10, HCX + 16, RT - 1, RT, HCZ - 22, HCZ + 22, PAINT_LINE)
box(HCX - 10, HCX + 10, RT - 1, RT, HCZ - 3, HCZ + 3, PAINT_LINE)
for a_ in range(0, 360, 30):
    ex = int(round(HCX + 70 * np.cos(np.radians(a_)))); ez = int(round(HCZ + 70 * np.sin(np.radians(a_))))
    box(ex, ex + 2, RT, RT + 1, ez, ez + 2, EXIT_SIGN)
    if a_ % 90 == 0:                                                # every third marker carries a light
        light(ex + 1, RT + 2, ez + 1, (0.3, 1.0, 0.45), 1.2, 0.1)
# perimeter railing round the upper roof (gap where the stairs arrive), windsock, floodlights
for (xa_, xb_, za_, zb_) in ((ax0, ax1, az0 - 4, az0 - 3), (ax0, ax1, az1 + 3, az1 + 4), (ax0 - 4, ax0 - 3, az0 - 4, az1 + 4), (ax1 + 3, ax1 + 4, az0 - 4, az1 + 4)):
    for x in range(xa_, xb_):
        for z in range(za_, zb_):
            if STX0 - 1 <= x < STX1 + 1 and z == az0 - 4:
                continue
            if G[x, RT - 1, z] == 0:
                continue
            if (x + z) % 10 == 0:
                box(x, x + 1, RT, RT + 9, z, z + 1, STEEL)
            box(x, x + 1, RT + 8, RT + 9, z, z + 1, STEEL)
box(STX0 - 1, STX0, RT, RT + 9, az0 - 4, az0 - 3, STEEL); box(STX1, STX1 + 1, RT, RT + 9, az0 - 4, az0 - 3, STEEL)
# tall roof fixtures are their own static shapes (the world shapes stop at 256 voxels high)
ROOF_SHAPES = list(SIGN_LETTERS) + list(SCONCES)      # (name, arr, gmin, [(gx, gy, gz, rgb, scale, size)])
ws = np.zeros((16, 26, 7), np.uint8)
ws[15, 0:26, 3] = STEEL                                           # pole (x = 15)
for k in range(12):
    rr_ = 3 - k // 4
    for dy in range(-rr_, rr_ + 1):
        for dz in range(-rr_, rr_ + 1):
            if dy * dy + dz * dz <= rr_ * rr_ + 1:
                ws[14 - k, 22 + dy, 3 + dz] = WALL_ORANGE if (k // 3) % 2 == 0 else CEIL
ROOF_SHAPES.append(("windsock", ws, (ax1 - 8 - 15, RT, az0 + 6 - 3), []))
# four floodlights, one per corner; pole and lamp head are separate shapes (a shot pole leaves the lamp lit)
for (fx_, fz_) in ((ax0 + 4, az0 + 4), (ax1 - 10, az1 - 10), (ax0 + 4, az1 - 10), (ax1 - 10, az0 + 10)):
    po_ = np.zeros((2, 15, 2), np.uint8); po_[:, :, :] = STEEL
    ROOF_SHAPES.append((f"floodpole{len(ROOF_SHAPES)}", po_, (fx_, RT, fz_), []))
    hd_ = np.zeros((6, 2, 6), np.uint8); hd_[:, :, :] = CEIL_LAMP
    ROOF_SHAPES.append((f"floodlight{len(ROOF_SHAPES)}", hd_, (fx_, RT + 15, fz_), [(fx_ + 4, RT + 13, fz_ + 4, (1.0, 0.95, 0.85), 2.4, 0.3)]))

# ============================================================================
# 10d. Rooftop glasshouse "FLORA" on the west roof (in front of the SW stair penthouse door):
#      a Victorian conservatory -- stone plinth, white-framed glass walls with arched heads, a glass
#      barrel vault with a lantern cupola (its own shape above the walls, the world stops at 256),
#      encaustic-tiled path, round plaza with a lily pond, palms, flower beds, a wisteria curtain,
#      hanging baskets, lamp posts and benches.
# ============================================================================
GRNG = random.Random(123)
GX0, GX1, GZ0, GZ1 = bx0 + 8, ax0 - 14, 196, 396       # 5.0 x 20 m footprint (1 m walkway to the atrium wall)
GXC = (GX0 + GX1) // 2
GEAVE = ROOF_Y + 32                                       # glass walls up to here, the vault shape above
PCZ = (GZ0 + GZ1) // 2                                    # round plaza / pond centre
PW0, PW1 = GXC - 10, GXC + 10                             # central path (2 m)
PR = 22                                                   # plaza radius
POND_R = 7.5                                              # pond water radius
SEAMS_Z = (az0 + 2 * LONG_BAY_W, az0 + 6 * LONG_BAY_W)    # world shape seams: keep plants clear of them
box(GX0 - 2, GX1 + 2, ROOF_Y, GEAVE, GZ0 - 2, GZ1 + 2, 0)    # (a roof vent stood here)
def g_rad(x, z):
    return float(np.hypot(x + 0.5 - GXC, z + 0.5 - PCZ))
def g_band(x, z):
    return x < GX0 + 3 or x >= GX1 - 3 or z < GZ0 + 3 or z >= GZ1 - 3
FOYER1, TERR0 = GZ0 + 16, GZ1 - 16                        # tiled entrance foyer / north terrace
def g_paved(x, z):
    return PW0 <= x < PW1 or g_rad(x, z) < PR or z < FOYER1 or z >= TERR0
# ---- floor: encaustic tiles on the path, foyer and terrace, a rosette on the plaza
for x in range(GX0 + 3, GX1 - 3):
    for z in range(GZ0 + 3, GZ1 - 3):
        if not g_paved(x, z):
            continue
        r_ = g_rad(x, z)
        if r_ < PR:
            ang = (np.degrees(np.arctan2(z + 0.5 - PCZ, x + 0.5 - GXC)) + 360) % 45
            c = MARBLE_B if r_ >= PR - 1.5 else (CARP_OR if (ang < 4 or ang > 41) and r_ > POND_R + 3 else
                                            (MARBLE_W if int(r_) % 3 == 0 else MARBLE_BG))
        else:
            dz_ = abs(((z - GZ0) % 12) - 6); dx_ = abs(((x - GXC) % 12) - 6) if not (PW0 <= x < PW1) else abs(x + 0.5 - GXC)
            d_ = dx_ + dz_
            edge = (PW0 <= x < PW1) and (x in (PW0, PW1 - 1)) and FOYER1 <= z < TERR0
            c = MARBLE_B if edge else (CARP_OR if d_ <= 2.5 else (MARBLE_B2 if d_ <= 3.5 else MARBLE_BG))
        G[x, ROOF_Y - 1, z] = c
# ---- planting beds: stone kerb, dark soil
BEDS = np.zeros((W, D), bool)
for x in range(GX0 + 3, GX1 - 3):
    for z in range(GZ0 + 3, GZ1 - 3):
        BEDS[x, z] = not g_paved(x, z)
for x in range(GX0 + 3, GX1 - 3):
    for z in range(GZ0 + 3, GZ1 - 3):
        if BEDS[x, z]:
            edge = not (BEDS[x - 1, z] and BEDS[x + 1, z] and BEDS[x, z - 1] and BEDS[x, z + 1])
            if edge:
                box(x, x + 1, ROOF_Y, ROOF_Y + 3, z, z + 1, BASE_STONE if (x // 3 + z // 3) % 2 else BASE_STONE2)
            else:
                box(x, x + 1, ROOF_Y, ROOF_Y + 2, z, z + 1, SOIL)
SOIL_Y = ROOF_Y + 2                                       # plants grow from here
# ---- plinth, glass walls, mullions, transom, arched heads, eave beam
for x in range(GX0, GX1):
    for z in range(GZ0, GZ1):
        if not g_band(x, z):
            continue
        for y in range(ROOF_Y, ROOF_Y + 6):
            G[x, y, z] = BASE_STONE if ((x + z) // 4 + (y - ROOF_Y) // 2) % 2 else BASE_STONE2
        G[x, ROOF_Y + 6, z] = EXT_TRIM
for (x0_, x1_, z0_, z1_, along_x) in ((GX0, GX1, GZ0 + 1, GZ0 + 2, True), (GX0, GX1, GZ1 - 2, GZ1 - 1, True),
                                      (GX0 + 1, GX0 + 2, GZ0, GZ1, False), (GX1 - 2, GX1 - 1, GZ0, GZ1, False)):
    box(x0_, x1_, ROOF_Y + 7, GEAVE - 3, z0_, z1_, GLASS)
for (x0_, x1_, z0_, z1_, along_x, lo_, hi_) in ((GX0, GX1, GZ0, GZ0 + 3, True, GX0, GX1), (GX0, GX1, GZ1 - 3, GZ1, True, GX0, GX1),
                                                (GX0, GX0 + 3, GZ0, GZ1, False, GZ0, GZ1), (GX1 - 3, GX1, GZ0, GZ1, False, GZ0, GZ1)):
    for p in range(lo_, hi_):
        o_ = p - lo_
        if o_ % 8 == 0 or p == hi_ - 1:                                   # mullions
            if along_x:
                box(p, p + 1, ROOF_Y + 7, GEAVE, z0_, z1_, SWITCH)
            else:
                box(x0_, x1_, ROOF_Y + 7, GEAVE, p, p + 1, SWITCH)
        else:                                                            # round arched head in each upper pane
            yy = ROOF_Y + 25 + int(round(3 * np.sqrt(max(0.0, 1 - ((o_ % 8 - 4) / 3.6) ** 2))))
            if along_x:
                G[p, yy, (z0_ + z1_) // 2] = SWITCH
            else:
                G[(x0_ + x1_) // 2, yy, p] = SWITCH
    if along_x:
        box(x0_, x1_, ROOF_Y + 18, ROOF_Y + 19, z0_, z1_, SWITCH); box(x0_, x1_, GEAVE - 3, GEAVE, z0_, z1_, SWITCH)
    else:
        box(x0_, x1_, ROOF_Y + 18, ROOF_Y + 19, z0_, z1_, SWITCH); box(x0_, x1_, GEAVE - 3, GEAVE, z0_, z1_, SWITCH)
# ---- arched entrance (south, facing the stair penthouse door) with a white frame and a brass "FLORA"
for x in range(GXC - 9, GXC + 9):
    for y in range(ROOF_Y, ROOF_Y + 26):
        dx_ = x + 0.5 - GXC
        if abs(dx_) < 7 and (y < ROOF_Y + 18 or (y - ROOF_Y - 18) ** 2 + dx_ * dx_ < 49):
            box(x, x + 1, y, y + 1, GZ0, GZ0 + 3, 0)
        elif abs(dx_) < 8.2 and (y < ROOF_Y + 18 or (y - ROOF_Y - 18) ** 2 + dx_ * dx_ < 67):
            box(x, x + 1, y, y + 1, GZ0, GZ0 + 3, SWITCH)
box(GXC - 7, GXC + 7, ROOF_Y - 1, ROOF_Y, GZ0, GZ0 + 3, MARBLE_W)                 # threshold
for x in range(GXC - 9, GXC + 9):                                                  # north door (same arch)
    for y in range(ROOF_Y, ROOF_Y + 26):
        dx_ = x + 0.5 - GXC
        if abs(dx_) < 7 and (y < ROOF_Y + 18 or (y - ROOF_Y - 18) ** 2 + dx_ * dx_ < 49):
            box(x, x + 1, y, y + 1, GZ1 - 3, GZ1, 0)
        elif abs(dx_) < 8.2 and (y < ROOF_Y + 18 or (y - ROOF_Y - 18) ** 2 + dx_ * dx_ < 67):
            box(x, x + 1, y, y + 1, GZ1 - 3, GZ1, SWITCH)
box(GXC - 7, GXC + 7, ROOF_Y - 1, ROOF_Y, GZ1 - 3, GZ1, MARBLE_W)
box(GXC - 12, GXC + 12, GEAVE - 9, GEAVE - 3, GZ0, GZ0 + 1, SWITCH)               # name board
ftext(Frame(GXC, GZ0, -1, 0, 0, 1), "FLORA", 0, GEAVE - 3, -1, BRASS)
light(GXC + 0.5, GEAVE + 1, GZ0 - 7, (1.0, 0.85, 0.62), 1.2, 0.2)
# ---- plants
def g_free(x, z, r):
    return all(abs(z - s_) > r + 2 for s_ in SEAMS_Z)
def plant_blob(cx_, cy_, cz_, r, seed, cols, squash=1.3, keep=0.3, flowers=None, fp=0.45):
    """leaf ball rooted in the soil below it; writes only into air; flowers on its sunny side."""
    xs = np.arange(cx_ - r - 1, cx_ + r + 2); ys = np.arange(SOIL_Y - 1, cy_ + r + 2); zs = np.arange(cz_ - r - 1, cz_ + r + 2)
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    m = (((X - cx_) ** 2 + ((Y - cy_) * squash) ** 2 + (Z - cz_) ** 2) <= r * r) & (hash3(X, Y, Z, seed) > keep)
    m |= (X == cx_) & (Z == cz_) & (Y < cy_)                                   # stem down to the soil
    m &= (G[X, Y, Z] == 0) | ((X == cx_) & (Z == cz_) & (Y == SOIL_Y - 1))
    m &= BEDS[X, Z]                                                            # never over the path
    m = keep_connected(m, [(cx_ - xs[0], 0, cz_ - zs[0])])
    t = hash3(X, Y, Z, seed + 1)
    col = np.where(t < 0.4, cols[0], np.where(t < 0.75, cols[1], cols[2]))
    if flowers:
        above_free = np.ones_like(m); above_free[:, :-1, :] = ~m[:, 1:, :]
        fl = m & above_free & (hash3(X, Y, Z, seed + 2) < fp) & (Y >= SOIL_Y + 1)
        fc = np.array(flowers)[(hash3(X, Y, Z, seed + 3) * len(flowers)).astype(int).clip(0, len(flowers) - 1)]
        col = np.where(fl, fc, col)
    G[X[m], Y[m], Z[m]] = col[m]
def line3(p, q):
    """6-connected voxel path from p to q."""
    out = [tuple(p)]; c = list(p)
    for k in range(3):
        while c[k] != q[k]:
            c[k] += 1 if q[k] > c[k] else -1
            out.append(tuple(c))
    return out
def palm(px, pz, h, seed):
    rr = random.Random(seed)
    lean = rr.choice((-1, 1))
    tx, tz = px, pz
    cells = {}
    for y in range(SOIL_Y - 1, SOIL_Y + h):
        if (y - SOIL_Y) % 9 == 8:
            tx += lean
        for (dx, dz) in ((0, 0), (1, 0), (0, 1), (1, 1)):
            cells[(tx + dx, y, tz + dz)] = TRUNK if (y // 2) % 2 else WOOD_DARK
    top = SOIL_Y + h
    for (dx, dz) in ((0, 0), (1, 0), (0, 1), (1, 1)):
        for y in (top, top + 1):
            cells[(tx + dx, y, tz + dz)] = LEAF3
    for f_ in range(9):
        a_ = np.radians(f_ * 40 + rr.uniform(-12, 12))
        L_ = rr.randint(11, 15)
        prev = (tx, top + 1, tz)
        for t_ in range(1, L_ + 1):
            sx_ = int(round(tx + 0.5 + np.cos(a_) * t_)); sz_ = int(round(tz + 0.5 + np.sin(a_) * t_))
            sy_ = int(round(top + 1 + 0.55 * t_ - 0.075 * t_ * t_))
            cur = (sx_, sy_, sz_)
            for c_ in line3(prev, cur):
                cells[c_] = LEAF2
            prev = cur
            w_ = int(round(2.6 * np.sin(np.pi * t_ / (L_ + 1))))
            for side in (-1, 1):
                for k_ in range(1, w_ + 1):
                    lx_ = int(round(sx_ - np.sin(a_) * side * k_)); lz_ = int(round(sz_ + np.cos(a_) * side * k_))
                    for c_ in line3(cur, (lx_, sy_ - (k_ + 1) // 2, lz_)):
                        cells.setdefault(c_, LEAF if (t_ + k_) % 3 else LEAF3)
    keys = list(cells)
    mn = np.min(keys, 0); mx = np.max(keys, 0) + 1
    m = np.zeros(tuple(mx - mn), bool); cm = np.zeros(tuple(mx - mn), np.uint8)
    for c_, v_ in cells.items():
        x, y, z = c_
        if GX0 + 4 <= x < GX1 - 4 and GZ0 + 4 <= z < GZ1 - 4 and y < GEAVE - 4 and (G[x, y, z] == 0 or y < SOIL_Y) \
                and all((z < s_) == (pz < s_) for s_ in SEAMS_Z) and (BEDS[x, z] or y >= ROOF_Y + 22):
            m[x - mn[0], y - mn[1], z - mn[2]] = True; cm[x - mn[0], y - mn[1], z - mn[2]] = v_
    m = keep_connected(m, [(px - mn[0], SOIL_Y - 1 - mn[1], pz - mn[2])])
    X, Y, Z = np.nonzero(m)
    G[X + mn[0], Y + mn[1], Z + mn[2]] = cm[X, Y, Z]
PALMS = [(GXC - 20, PCZ - 18), (GXC + 19, PCZ - 18), (GXC - 20, PCZ + 17), (GXC + 19, PCZ + 17)]
for i, (px_, pz_) in enumerate(PALMS):
    palm(px_, pz_, GRNG.randint(17, 20), 300 + i)
    for (ux_, uz_) in ((px_ + 3, pz_ + 1),):                                        # lilac uplight at its foot
        if BEDS[ux_, uz_]:
            G[ux_, SOIL_Y, uz_] = COVE_LAMP
            light(ux_ + 0.5, SOIL_Y + 2, uz_ + 0.5, (0.78, 0.6, 1.0), 1.3, 0.15)
HYDRANGEA = [(WALL_BLUE, DREAM_LILAC), (DREAM_PINK, WALL_MAUVE), (DREAM_LILAC, DREAM_CLOUD)]
ROSES = [(ROSE, DREAM_PINK), (DREAM_CLOUD, DREAM_PINK), (ROSE, ROSE)]
placed = [(px_, pz_, 7) for (px_, pz_) in PALMS] + [(px_ + 3, pz_ + 1, 3) for (px_, pz_) in PALMS]
def g_try(x, z, r):
    if not (BEDS[x - r:x + r + 1, z - r:z + r + 1].all() and g_free(x, z, r)):
        return False
    return all((x - a) ** 2 + (z - b) ** 2 > (r + c) ** 2 for (a, b, c) in placed)
for n_ in range(1400):
    x = GRNG.randint(GX0 + 4, GX1 - 5); z = GRNG.randint(GZ0 + 4, GZ1 - 5)
    near_wall = x < GX0 + 12 or x >= GX1 - 12
    if near_wall:
        r = GRNG.randint(3, 4)
        if g_try(x, z, r - 1):
            cols = GRNG.choice(HYDRANGEA)
            plant_blob(x, SOIL_Y + r + GRNG.randint(1, 3), z, r, 400 + n_, (LEAF, LEAF3, LEAF2), squash=1.1, keep=0.22, flowers=list(cols), fp=0.55)
            placed.append((x, z, r))
    else:
        r = GRNG.randint(2, 3)
        if g_try(x, z, r - 1):
            kind = GRNG.random()
            if kind < 0.45:
                plant_blob(x, SOIL_Y + r, z, r, 400 + n_, (LEAF2, LEAF, LEAF3), squash=1.2, keep=0.25, flowers=list(GRNG.choice(ROSES)), fp=0.4)
            elif kind < 0.75:                                                      # fern: low and wide
                plant_blob(x, SOIL_Y + 1, z, r + 1, 400 + n_, (LEAF, LEAF2, LAWN), squash=2.2, keep=0.3)
            else:                                                                  # lavender tuft
                for dx in range(-r + 1, r):
                    for dz in range(-r + 1, r):
                        if dx * dx + dz * dz <= (r - 1) ** 2 + 1 and G[x + dx, SOIL_Y, z + dz] == 0:
                            hgt = 3 + int(hash3(np.array([x + dx]), np.array([0]), np.array([z + dz]), 7)[0] * 4)
                            box(x + dx, x + dx + 1, SOIL_Y - 1, SOIL_Y + hgt - 2, z + dz, z + dz + 1, LEAF3)
                            box(x + dx, x + dx + 1, SOIL_Y + hgt - 2, SOIL_Y + hgt, z + dz, z + dz + 1, DREAM_LILAC)
            placed.append((x, z, r))
# ---- wisteria curtain hanging from the eave beams of the long walls, vines on some mullions
for (xw, dirx) in ((GX0 + 3, 1), (GX1 - 4, -1)):
    for z in range(GZ0 + 4, GZ1 - 4):
        if any(abs(z - s_) < 3 for s_ in SEAMS_Z) or GRNG.random() < 0.25:
            continue
        L_ = GRNG.randint(4, 13)
        for k in range(L_):
            y = GEAVE - 3 - k
            c = LEAF2 if k < 2 else (DREAM_LILAC if k < L_ - 2 else (WALL_MAUVE if k == L_ - 2 else DREAM_CLOUD))
            if G[xw, y, z] == 0:
                G[xw, y, z] = c
            else:
                break
            if k >= 2 and k < L_ - 3 and GRNG.random() < 0.45 and G[xw + dirx, y, z] == 0:
                G[xw + dirx, y, z] = DREAM_LILAC if GRNG.random() < 0.7 else DREAM_PINK
    for z in range(GZ0 + 8, GZ1 - 8, 24):                                          # ivy up a mullion
        if any(abs(z - s_) < 3 for s_ in SEAMS_Z):
            continue
        for y in range(ROOF_Y + 7, GEAVE - 6):
            if GRNG.random() < 0.8 and G[xw, y, z] == 0:
                G[xw, y, z] = LEAF if y % 3 else LEAF3
# ---- hanging baskets on white brackets from the eave
for (xw, dirx) in ((GX0 + 3, 1), (GX1 - 4, -1)):
    for z in range(GZ0 + 20, GZ1 - 16, 26):
        if abs(z - PCZ) < 40 or any(abs(z - s_) < 6 for s_ in SEAMS_Z):
            continue
        bx_ = xw + dirx * 5
        for x in range(min(xw, bx_), max(xw, bx_) + 1):
            G[x, GEAVE - 3, z] = SWITCH
        box(bx_, bx_ + 1, GEAVE - 9, GEAVE - 3, z, z + 1, DARK_METAL)               # chain
        yb = GEAVE - 11
        for dx in range(-2, 3):
            for dz in range(-2, 3):
                d2 = dx * dx + dz * dz
                if d2 <= 5:
                    G[bx_ + dx, yb, z + dz] = PLANTER
                    if d2 >= 3:
                        G[bx_ + dx, yb + 1, z + dz] = PLANTER
                    else:
                        G[bx_ + dx, yb + 1, z + dz] = LEAF2
                    if d2 <= 2:
                        G[bx_ + dx, yb + 2, z + dz] = LEAF if d2 else ROSE
                if d2 in (4, 5) and GRNG.random() < 0.6:                           # trailing strands
                    for k in range(1, GRNG.randint(2, 5)):
                        G[bx_ + dx, yb - k, z + dz] = LEAF3 if k % 2 else GRNG.choice((DREAM_PINK, DREAM_LILAC, LEAF))
# ---- lily pond on the plaza: stone rim, marble cap, dark basin, lilies, a flower urn on a column, underwater lights
for x in range(GXC - 14, GXC + 14):
    for z in range(PCZ - 14, PCZ + 14):
        r_ = g_rad(x, z)
        if r_ < POND_R:
            G[x, ROOF_Y - 1, z] = MARBLE_B2
        elif r_ < POND_R + 2:
            box(x, x + 1, ROOF_Y, ROOF_Y + 5, z, z + 1, BASE_STONE if (x + z) % 3 else BASE_STONE2)
        if POND_R <= r_ < POND_R + 2.6:
            G[x, ROOF_Y + 5, z] = MARBLE_W
POOLS.append((ROOF_Y + 4.5, 4.5, [(GXC + (POND_R - 0.3) * np.cos(np.radians(a)), PCZ + (POND_R - 0.3) * np.sin(np.radians(a))) for a in range(0, 360, 30)],
              dict(wave=0.01, ripple=0.3, motion=0.04, foam=0)))
box(GXC - 1, GXC + 1, ROOF_Y, ROOF_Y + 9, PCZ - 1, PCZ + 1, MARBLE_W)              # column
for x in range(GXC - 4, GXC + 4):
    for z in range(PCZ - 4, PCZ + 4):
        d_ = g_rad(x, z)
        if d_ < 2.2:
            box(x, x + 1, ROOF_Y + 9, ROOF_Y + 10, z, z + 1, MARBLE_W)
        if d_ < 3.6:
            box(x, x + 1, ROOF_Y + 10, ROOF_Y + 11, z, z + 1, MARBLE_W)
            G[x, ROOF_Y + 11, z] = MARBLE_W if d_ >= 2.6 else SOIL
            if d_ >= 2.6 and GRNG.random() < 0.6:
                for k in range(1, GRNG.randint(2, 6)):
                    if G[x, ROOF_Y + 11 - k, z] == 0:
                        G[x, ROOF_Y + 11 - k, z] = LEAF if k % 2 else DREAM_PINK
for x in range(GXC - 3, GXC + 3):                                                  # (rooted in the urn's soil)
    for z in range(PCZ - 3, PCZ + 3):
        for y in range(ROOF_Y + 12, ROOF_Y + 16):
            d2 = (x + 0.5 - GXC) ** 2 + (z + 0.5 - PCZ) ** 2 + ((y - ROOF_Y - 12) * 1.2) ** 2
            if d2 < 7.5 and G[x, y, z] == 0:
                G[x, y, z] = GRNG.choice((LEAF2, LEAF, ROSE, DREAM_PINK, DREAM_CLOUD)) if y > ROOF_Y + 12 else LEAF3
for i in range(6):                                                                 # lily pads (stem from the basin floor)
    a_ = np.radians(i * 60 + GRNG.uniform(-15, 15)); rr_ = GRNG.uniform(3.8, POND_R - 1.6)
    lx_ = int(GXC + rr_ * np.cos(a_)); lz_ = int(PCZ + rr_ * np.sin(a_))
    box(lx_, lx_ + 1, ROOF_Y, ROOF_Y + 4, lz_, lz_ + 1, LEAF3)
    for dx in range(-1, 2):
        for dz in range(-1, 2):
            if abs(dx) + abs(dz) < 2 or GRNG.random() < 0.6:
                G[lx_ + dx, ROOF_Y + 4, lz_ + dz] = LEAF2
    if i % 3 == 0:
        G[lx_, ROOF_Y + 5, lz_] = DREAM_PINK; G[lx_, ROOF_Y + 6, lz_] = DREAM_CLOUD
for a_ in (30, 210):                                                           # (between the lily pads)
    lx_ = int(round(GXC + (POND_R - 0.8) * np.cos(np.radians(a_)))); lz_ = int(round(PCZ + (POND_R - 0.8) * np.sin(np.radians(a_))))
    G[lx_, ROOF_Y, lz_] = POOL_LAMP
    light(lx_ + 0.5 - np.cos(np.radians(a_)) * 1.5, ROOF_Y + 1.5, lz_ + 0.5 - np.sin(np.radians(a_)) * 1.5, (0.65, 0.85, 1.0), 0.9, 0.1)
# ---- benches facing the pond, and on the north terrace
def g_bench(x0_, z0_, along_z, face):
    """1.2 m garden bench: wooden slats on black iron ends; face = direction the sitter looks (+1/-1)."""
    if along_z:
        for z in (z0_, z0_ + 11):
            box(x0_, x0_ + 4, ROOF_Y, ROOF_Y + 4, z, z + 1, DARK_METAL)
        box(x0_, x0_ + 4, ROOF_Y + 4, ROOF_Y + 5, z0_, z0_ + 12, WOOD_MED)
        bxk = x0_ if face > 0 else x0_ + 3                                         # back away from the view
        box(bxk, bxk + 1, ROOF_Y + 5, ROOF_Y + 10, z0_, z0_ + 12, WOOD_MED)
        box(bxk, bxk + 1, ROOF_Y + 6, ROOF_Y + 7, z0_ + 1, z0_ + 11, WOOD_DARK)
    else:
        for x in (x0_, x0_ + 11):
            box(x, x + 1, ROOF_Y, ROOF_Y + 4, z0_, z0_ + 4, DARK_METAL)
        box(x0_, x0_ + 12, ROOF_Y + 4, ROOF_Y + 5, z0_, z0_ + 4, WOOD_MED)
        bzk = z0_ if face > 0 else z0_ + 3
        box(x0_, x0_ + 12, ROOF_Y + 5, ROOF_Y + 10, bzk, bzk + 1, WOOD_MED)
        box(x0_ + 1, x0_ + 11, ROOF_Y + 6, ROOF_Y + 7, bzk, bzk + 1, WOOD_DARK)
g_bench(GXC - 22, GZ1 - 10, False, -1)
g_bench(GXC + 10, GZ1 - 10, False, -1)
# entrance foyer: two terracotta urns with clipped bay balls
for ux_ in (GXC - 17, GXC + 16):
    uz_ = GZ0 + 9
    for x in range(ux_ - 4, ux_ + 5):
        for z in range(uz_ - 4, uz_ + 5):
            d_ = np.hypot(x - ux_, z - uz_)
            for y in range(ROOF_Y, ROOF_Y + 8):
                rr_ = 2.2 + (y - ROOF_Y) * 0.22 + (0.6 if y == ROOF_Y + 7 else 0)
                if d_ <= rr_:
                    G[x, y, z] = (CARP_OR2 if y in (ROOF_Y + 2, ROOF_Y + 7) else CARP_OR) if d_ > rr_ - 1.1 or y < ROOF_Y + 2 else SOIL
    box(ux_, ux_ + 1, ROOF_Y + 8, ROOF_Y + 12, uz_, uz_ + 1, TRUNK)
    for x in range(ux_ - 4, ux_ + 5):
        for z in range(uz_ - 4, uz_ + 5):
            for y in range(ROOF_Y + 11, ROOF_Y + 20):
                if (x - ux_) ** 2 + (z - uz_) ** 2 + (y - ROOF_Y - 15) ** 2 <= 14 and G[x, y, z] == 0:
                    G[x, y, z] = LEAF if hash3(np.array([x]), np.array([y]), np.array([z]), 21)[0] < 0.6 else LEAF3
# ---- Victorian lamp posts along the path (crook arm, lantern hanging over the path)
for pz_ in (GZ0 + 32, GZ0 + 60, GZ1 - 58, GZ1 - 28):             # (clear of the shape seam at z 224)
    for (px_, d_) in ((PW0 - 1, 1), (PW1, -1)):
        box(px_ - 1, px_ + 2, ROOF_Y, ROOF_Y + 4, pz_ - 1, pz_ + 2, DARK_METAL)
        box(px_, px_ + 1, ROOF_Y + 4, ROOF_Y + 23, pz_, pz_ + 1, DARK_METAL)
        for k in range(0, 4):
            G[px_ + d_ * k, ROOF_Y + 23, pz_] = DARK_METAL
        G[px_ + d_ * 3, ROOF_Y + 22, pz_] = DARK_METAL
        lx_ = px_ + d_ * 3
        box(lx_ - 1, lx_ + 2, ROOF_Y + 21, ROOF_Y + 22, pz_ - 1, pz_ + 2, DARK_METAL)          # lantern hood
        G[lx_, ROOF_Y + 22, pz_] = DARK_METAL
        box(lx_, lx_ + 1, ROOF_Y + 18, ROOF_Y + 21, pz_, pz_ + 1, LAMPSHADE)                 # glowing core
        for (ex_, ez_) in ((lx_ - 1, pz_ - 1), (lx_ + 1, pz_ - 1), (lx_ - 1, pz_ + 1), (lx_ + 1, pz_ + 1)):
            box(ex_, ex_ + 1, ROOF_Y + 19, ROOF_Y + 21, ez_, ez_ + 1, DARK_METAL)              # corner bars
        for (ex_, ez_) in ((lx_ - 1, pz_), (lx_ + 1, pz_), (lx_, pz_ - 1), (lx_, pz_ + 1)):
            box(ex_, ex_ + 1, ROOF_Y + 19, ROOF_Y + 21, ez_, ez_ + 1, GLASS)                   # glass panes
        light(lx_ + 0.5, ROOF_Y + 17.2, pz_ + 0.5, (1.0, 0.8, 0.55), 1.8, 0.15)
# ---- the glass vault (own static shape on the eave beams): white ribs every 8, purlins, cresting,
#      fairy lights under the ribs, glass gables with a sunburst, an octagonal lantern cupola
NXV, NZV = GX1 - GX0, GZ1 - GZ0
VA = np.zeros((NXV, 29, NZV), np.uint8)
a_v, b_v = NXV / 2, 19.0
hv = [b_v * np.sqrt(max(0.0, 1 - ((i + 0.5 - a_v) / a_v) ** 2)) for i in range(NXV)]
tv = [int(h) for h in hv]
lov = [0 if i in (0, NXV - 1) else min(tv[i - 1], tv[i], tv[i + 1]) for i in range(NXV)]
for i in range(NXV):
    VA[i, lov[i]:tv[i] + 1, :] = GLASS
    if i % 7 == 0 and 0 < i < NXV - 1:
        VA[i, tv[i], :] = SWITCH                                                   # purlins
for zr in list(range(0, NZV, 8)) + [NZV - 1]:
    for i in range(NXV):
        VA[i, max(lov[i] - 1, 0):tv[i] + 1, zr] = SWITCH
        if 0 < zr < NZV - 1 and i % 3 == 1 and lov[i] - 2 >= 3:
            VA[i, lov[i] - 2, zr] = LAMPSHADE                                      # fairy lights
for zg in (0, NZV - 1):                                                            # gables + sunburst
    for i in range(NXV):
        VA[i, 0:tv[i] + 1, zg] = np.where(VA[i, 0:tv[i] + 1, zg] == SWITCH, SWITCH, GLASS)
    for ang in range(20, 180, 20):
        for rr_ in np.arange(0, 22, 0.5):
            i = int(a_v + np.cos(np.radians(ang)) * rr_); yy = int(np.sin(np.radians(ang)) * rr_)
            if 0 <= i < NXV and yy <= tv[i]:
                VA[i, yy, zg] = SWITCH
    for ang in np.arange(0, 180, 3):
        i = int(a_v + np.cos(np.radians(ang)) * 7); yy = int(np.sin(np.radians(ang)) * 7)
        VA[i, yy, zg] = SWITCH
    VA[:, 0, zg] = SWITCH
ic = NXV // 2
for z in range(NZV):                                                               # ridge cresting + finials
    VA[ic - 1:ic + 1, tv[ic] + 1, z] = SWITCH
    if z % 16 == 8 and abs(z - NZV // 2) > 10:
        VA[ic - 1:ic + 1, tv[ic] + 2, z] = SWITCH; VA[ic - 1:ic + 1, tv[ic] + 3, z] = BRASS
cz_c = NZV // 2; yc0 = tv[ic] + 1                                                  # octagonal lantern cupola
for i in range(NXV):
    for z in range(NZV):
        ddx, ddz = i + 0.5 - ic, z + 0.5 - cz_c
        dx_, dz_ = abs(ddx), abs(ddz)
        ang = np.degrees(np.arctan2(ddz, ddx)) % 45
        rib = ang < 7 or ang > 38
        if dx_ <= 6.5 and dz_ <= 6.5 and dx_ + dz_ <= 9.5:
            VA[i, yc0, z] = SWITCH
            VA[i, yc0 + 5, z] = SWITCH
            if not (dx_ <= 5.5 and dz_ <= 5.5 and dx_ + dz_ <= 8.5):
                VA[i, yc0 + 1:yc0 + 5, z] = SWITCH if rib else GLASS
        r2 = ddx * ddx + ddz * ddz
        if r2 <= 25:
            VA[i, yc0 + 6, z] = SWITCH if rib else GLASS
        if r2 <= 10:
            VA[i, yc0 + 7, z] = SWITCH if rib else GLASS
VA[ic - 1:ic + 1, yc0 + 8, cz_c - 1:cz_c + 1] = BRASS
ROOF_SHAPES.append(("glasshouse_vault", VA, (GX0, GEAVE, GZ0),
                    [(GXC, GEAVE + 13, z, (1.0, 0.84, 0.62), 1.3, 0.2) for z in (GZ0 + 40, PCZ, GZ1 - 40)]))
GLASSHOUSE = dict(x0=GX0, x1=GX1, z0=GZ0, z1=GZ1, eave=GEAVE, plaza=(GXC, PCZ), palms=PALMS)

# ============================================================================
# 10e. Penthouse suite (v3.40) on the east roof, in front of the NE stair penthouse door: foyer + bar,
#      living room with a fireplace, dining, bedroom, bathroom; a deck terrace with a jacuzzi to the south.
#      Glass east wall over the street. (World voxels: the suite stops below the 256 world height.)
# ============================================================================
PRNG = random.Random(4040)
PY = ROOF_Y; PCEIL = PY + 28                                 # 2.8 m rooms, roof slab above
box(PH_X0 - 1, PH_X1, PY, PY + 34, PT_Z0 - 1, PH_Z1 + 1, 0)
ix0p, ix1p, iz0p, iz1p = PH_X0 + 2, PH_X1 - 2, PH_Z0 + 2, PH_Z1 - 2      # interior
Z_BATH, Z_BED, Z_DIN, Z_LIV = iz0p + 34, iz0p + 72, iz0p + 102, iz0p + 150   # partitions (south -> north)
# floors: oak parquet, marble in the bathroom
for x in range(ix0p, ix1p):
    for z in range(iz0p, iz1p):
        if z < Z_BATH:
            G[x, PY - 1, z] = MARBLE_W if ((x // 5) + (z // 5)) % 2 else MARBLE_W2
        else:
            G[x, PY - 1, z] = PARQUET if ((x // 2) + (z // 8)) % 2 else PARQUET2
# shell: solid west wall (atrium side), glass east wall with bronze mullions, glass south wall to the terrace
box(PH_X0, PH_X0 + 2, PY, PCEIL, PH_Z0, PH_Z1, LOBBY_WALL)
box(PH_X0, PH_X1, PY, PCEIL, PH_Z1 - 2, PH_Z1, LOBBY_WALL)
box(PH_X1 - 2, PH_X1, PY, PY + 1, PH_Z0, PH_Z1, PICFRAME)
box(PH_X1 - 2, PH_X1, PCEIL - 1, PCEIL, PH_Z0, PH_Z1, PICFRAME)
box(PH_X1 - 1, PH_X1, PY + 1, PCEIL - 1, PH_Z0, PH_Z1, GLASS_EXT)
for z in range(PH_Z0, PH_Z1, 14):
    box(PH_X1 - 2, PH_X1, PY, PCEIL, z, z + 1, PICFRAME)
box(PH_X0, PH_X1, PY, PCEIL, PH_Z0, PH_Z0 + 2, PICFRAME)
box(PH_X0 + 2, PH_X1 - 2, PY + 1, PCEIL - 1, PH_Z0 + 1, PH_Z0 + 2, GLASS_EXT)
for x in range(PH_X0 + 12, PH_X1 - 2, 14):
    box(x, x + 1, PY, PCEIL, PH_Z0, PH_Z0 + 2, PICFRAME)
DOORS_SOUTH = (PH_X0 + 18, PH_X0 + 36)                       # open slider to the terrace
box(DOORS_SOUTH[0], DOORS_SOUTH[1], PY, PY + 23, PH_Z0, PH_Z0 + 2, 0)
box(DOORS_SOUTH[0] - 1, DOORS_SOUTH[1] + 1, PY + 23, PY + 24, PH_Z0, PH_Z0 + 2, PICFRAME)
for xs_ in (DOORS_SOUTH[0] - 1, DOORS_SOUTH[1]):
    box(xs_, xs_ + 1, PY, PY + 23, PH_Z0, PH_Z0 + 2, PICFRAME)
# roof slab + cornice
box(PH_X0 - 1, PH_X1 + 1, PCEIL, PCEIL + 3, PH_Z0 - 1, PH_Z1 + 1, SLAB)
box(PH_X0 - 2, PH_X1 + 2, PCEIL + 2, PCEIL + 3, PH_Z0 - 2, PH_Z1 + 2, EXT_TRIM)
paint(ix0p, ix1p, PCEIL, PCEIL + 1, iz0p, iz1p, CEIL)
paint(PH_X0 + 1, PH_X0 + 2, PY, PCEIL, iz0p, iz1p, ROOM_WALL_C, [LOBBY_WALL])   # west wall, inside
# entrance (north wall), with a brass "PH" plate
ENT_X = PH_X0 + 14
box(ENT_X, ENT_X + 10, PY, PY + 23, PH_Z1 - 2, PH_Z1, 0)
box(ENT_X - 1, ENT_X + 11, PY + 23, PY + 24, PH_Z1 - 2, PH_Z1 + 1, BRASS)
for xe_ in (ENT_X - 1, ENT_X + 10):
    box(xe_, xe_ + 1, PY, PY + 23, PH_Z1, PH_Z1 + 1, BRASS)
add_door(Frame(ENT_X, PH_Z1 - 2, 1, 0, 0, 1), 0, 10, PY, PY + 23, 1, 2, lambda a, b, c, A, B, C: wood_door(A - 1 - a, b, c, A, B, C),
         hinge=(10, 1), open_dir=(0, -1), tag="hoteldoor penthouse", stop=BRASS)
box(ENT_X - 14, ENT_X + 25, PY + 23, PY + 28, PH_Z1, PH_Z1 + 1, DARK_METAL)  # board behind the letters
ftext(Frame(0, PH_Z1, 1, 0, 0, -1), "PENTHOUSE", ENT_X + 5, PY + 28, -1, BRASS)
# partitions with open doorways
for (zp, dx0p, dx1p) in ((Z_BATH, ix0p + 8, ix0p + 18), (Z_BED, ix0p + 8, ix0p + 18)):
    box(ix0p, PH_X1 - 1, PY, PCEIL, zp, zp + 2, ROOM_WALL)
    box(dx0p, dx1p, PY, PY + 23, zp, zp + 2, 0)
# lights: warm recessed downlights
def ph_light(x, z, rgb=(1.0, 0.82, 0.6), sc=1.6):
    box(x - 1, x + 2, PCEIL - 1, PCEIL, z - 1, z + 2, CEIL_LAMP)
    light(x + 0.5, PCEIL - 2.5, z + 0.5, rgb, sc, 0.25)
for (lx_, lz_) in ((ix0p + 26, Z_LIV + 14), (ix0p + 12, Z_LIV - 14), (ix0p + 38, Z_LIV - 14), (ix0p + 25, Z_DIN - 15),
                   (ix0p + 25, Z_BED - 16), (ix0p + 12, (Z_BATH + Z_BED) // 2 - 4), (ix0p + 30, iz0p + 16)):
    ph_light(lx_, lz_)
# ---- foyer + bar (north)
bx_b = ix1p - 8
box(bx_b, bx_b + 6, PY, PY + 10, Z_LIV + 6, iz1p - 6, WOOD_DARK)               # bar counter
box(bx_b - 1, bx_b + 6, PY + 10, PY + 11, Z_LIV + 5, iz1p - 5, MARBLE_B)
box(bx_b, bx_b + 1, PY + 1, PY + 9, Z_LIV + 6, iz1p - 6, BRASS)                # brass kick plate (bar front)
for zs in range(Z_LIV + 9, iz1p - 8, 7):                                         # bar stools
    box(bx_b - 6, bx_b - 5, PY, PY + 7, zs, zs + 1, BRASS)
    box(bx_b - 8, bx_b - 3, PY + 7, PY + 8, zs - 2, zs + 3, UPHOL)
box(ix1p - 1, ix1p + 1, PY, PY + 24, Z_LIV + 7, iz1p - 7, WOOD_DARK)             # back-bar panel (the glass is smart glass)
for sy_ in (PY + 14, PY + 19):                                                   # back-bar shelves on the panel
    box(ix1p - 2, ix1p - 1, sy_, sy_ + 1, Z_LIV + 8, iz1p - 8, PICFRAME)
    for zb in range(Z_LIV + 9, iz1p - 9, 2):
        box(ix1p - 2, ix1p - 1, sy_ + 1, sy_ + 3 + (zb % 3 == 0), zb, zb + 1, PRNG.choice((GLASS_DOOR, BRASS, CAR_C, DUMPSTER)))
box(ix1p - 2, ix1p - 1, PY + 13, PY + 14, Z_LIV + 8, iz1p - 8, COVE_LAMP)        # back-bar glow strip
light(ix1p - 4, PY + 13, (Z_LIV + iz1p) / 2, (0.85, 0.65, 1.0), 1.2, 0.2)
# ---- living room: fireplace on the west wall, velvet L sofa, marble table, rug
fz = (Z_DIN + Z_LIV) // 2 + 10
box(ix0p, ix0p + 4, PY, PY + 22, fz - 9, fz + 9, MARBLE_BG)                      # chimney breast
box(ix0p, ix0p + 4, PY + 2, PY + 9, fz - 5, fz + 5, 0)
box(ix0p, ix0p + 1, PY + 2, PY + 9, fz - 5, fz + 5, TIRE)                        # firebox
box(ix0p + 1, ix0p + 3, PY + 2, PY + 3, fz - 4, fz + 4, DARK_METAL)              # grate
for k_ in range(6):
    box(ix0p + 1, ix0p + 3, PY + 3 + k_ // 2, PY + 4 + k_ // 2, fz - 3 + k_ % 3, fz - 2 + k_ % 3 + 3 - k_ // 2, STREET_LMP)
light(ix0p + 5, PY + 5, fz, (1.0, 0.55, 0.25), 1.6, 0.2)
box(ix0p + 4, ix0p + 6, PY + 10, PY + 11, fz - 10, fz + 10, MARBLE_W)            # mantel
box(ix0p + 4, ix0p + 5, PY + 13, PY + 21, fz - 7, fz + 7, TV_BODY)               # TV over the mantel
box(ix0p + 5, ix0p + 6, PY + 14, PY + 20, fz - 6, fz + 6, TV_SCREEN)
light(ix0p + 7.5, PY + 17, fz + 0.5, (0.45, 0.6, 1.0), 1.0, 0.2, "room=ph rl=tv")   # E on the screen: TV on / off
for x in range(ix0p + 10, ix0p + 40):                                            # rug
    for z in range(fz - 14, fz + 14):
        G[x, PY - 1, z] = RUG_BRD if x in (ix0p + 10, ix0p + 39) or z in (fz - 14, fz + 13) else (RUG if (x + z) % 4 else RUG2)
SOFA = WALL_MAUVE
box(ix0p + 30, ix0p + 38, PY, PY + 5, fz - 13, fz + 13, SOFA)                    # long side, facing the fire
box(ix0p + 35, ix0p + 38, PY + 5, PY + 10, fz - 13, fz + 13, SOFA)
box(ix0p + 14, ix0p + 38, PY, PY + 5, fz + 10, fz + 14, SOFA)                    # return
box(ix0p + 14, ix0p + 38, PY + 5, PY + 10, fz + 12, fz + 14, SOFA)
for (cx_, cz_) in ((ix0p + 33, fz - 8), (ix0p + 33, fz + 3), (ix0p + 20, fz + 11)):
    box(cx_ - 1, cx_ + 2, PY + 5, PY + 7, cz_, cz_ + 3, PILLOW)
box(ix0p + 16, ix0p + 26, PY, PY + 4, fz - 6, fz + 4, MARBLE_B)                 # coffee table
box(ix0p + 18, ix0p + 21, PY + 4, PY + 5, fz - 3, fz, BRASS)                     # (a brass bowl)
# ---- dining: table for six, pendant lamp
dz = (Z_BED + Z_DIN) // 2 + 6
box(ix0p + 14, ix0p + 36, PY + 7, PY + 8, dz - 5, dz + 5, WOOD_DARK)
for (tx_, tz_) in ((ix0p + 15, dz - 4), (ix0p + 34, dz - 4), (ix0p + 15, dz + 3), (ix0p + 34, dz + 3)):
    box(tx_, tx_ + 1, PY, PY + 7, tz_, tz_ + 1, WOOD_DARK)
for cx_ in (ix0p + 17, ix0p + 24, ix0p + 31):
    for (cz0, back) in ((dz - 9, dz - 9), (dz + 6, dz + 8)):
        box(cx_, cx_ + 4, PY + 4, PY + 5, cz0, cz0 + 3, UPHOL2)
        box(cx_, cx_ + 4, PY + 5, PY + 11, back, back + 1, WOOD_DARK)
        for (lx_, lz_) in ((cx_, cz0), (cx_ + 3, cz0), (cx_, cz0 + 2), (cx_ + 3, cz0 + 2)):
            box(lx_, lx_ + 1, PY, PY + 4, lz_, lz_ + 1, WOOD_DARK)
box(ix0p + 25, ix0p + 26, PCEIL - 7, PCEIL, dz, dz + 1, BRASS)                    # pendant
box(ix0p + 22, ix0p + 29, PCEIL - 9, PCEIL - 7, dz - 3, dz + 4, BRASS)
box(ix0p + 23, ix0p + 28, PCEIL - 10, PCEIL - 9, dz - 2, dz + 3, LAMPSHADE)
light(ix0p + 25.5, PCEIL - 11.5, dz + 0.5, (1.0, 0.8, 0.55), 1.4, 0.2)
# ---- bedroom: king bed against the partition, nightstands with lamps, wardrobe on the west wall
bz0_b = Z_BED - 2
BX_ = ix0p + 20
box(BX_, BX_ + 24, PY, PY + 4, bz0_b - 26, bz0_b, WOOD_DARK)                       # bed base
box(BX_ + 1, BX_ + 23, PY + 4, PY + 7, bz0_b - 25, bz0_b - 1, SHEET)               # mattress
box(BX_ + 1, BX_ + 23, PY + 7, PY + 8, bz0_b - 25, bz0_b - 10, BLANKET_C)          # duvet
box(BX_ + 1, BX_ + 23, PY + 6, PY + 7, bz0_b - 26, bz0_b - 25, BLANKET_C)
for px_ in (BX_ + 3, BX_ + 14):
    box(px_, px_ + 8, PY + 7, PY + 9, bz0_b - 7, bz0_b - 2, PILLOW)
box(BX_ - 1, BX_ + 25, PY, PY + 16, bz0_b - 1, bz0_b, UPHOL)                       # tall headboard
for nx_ in (BX_ - 7, BX_ + 26):                                                   # nightstands + lamps
    box(nx_, nx_ + 5, PY, PY + 6, bz0_b - 6, bz0_b - 1, WOOD_DARK)
    box(nx_ + 2, nx_ + 3, PY + 6, PY + 9, bz0_b - 4, bz0_b - 3, BRASS)
    box(nx_ + 1, nx_ + 4, PY + 9, PY + 12, bz0_b - 5, bz0_b - 2, LAMPSHADE)
    light(nx_ + 2.5, PY + 13.5, bz0_b - 3.5, (1.0, 0.8, 0.55), 0.9, 0.15)
box(ix0p, ix0p + 6, PY, PY + 24, Z_BATH + 4, Z_BATH + 24, WOOD_MED)              # wardrobe
box(ix0p + 6, ix0p + 7, PY + 1, PY + 23, Z_BATH + 14, Z_BATH + 15, WOOD_DARK)
box(ix0p + 6, ix0p + 7, PY + 11, PY + 13, Z_BATH + 12, Z_BATH + 13, BRASS)
# ---- bathroom: freestanding tub by the glass, double vanity with a mirror, glass shower
tcx, tcz = ix1p - 16, iz0p + 14
for x in range(tcx - 10, tcx + 10):
    for z in range(tcz - 6, tcz + 6):
        e_ = ((x + 0.5 - tcx) / 9.5) ** 2 + ((z + 0.5 - tcz) / 5.5) ** 2
        if e_ <= 1:
            box(x, x + 1, PY, PY + 6, z, z + 1, CERAMIC)
            if e_ <= 0.62:
                box(x, x + 1, PY + 2, PY + 6, z, z + 1, 0)
box(tcx - 1, tcx + 1, PY, PY + 9, tcz + 6, tcz + 7, CHROME)                        # floor-standing tap
box(tcx - 1, tcx + 1, PY + 8, PY + 9, tcz + 3, tcz + 7, CHROME)
box(ix0p, ix0p + 7, PY, PY + 8, iz0p + 4, iz0p + 26, MARBLE_W)                     # vanity on the west wall
for sz_ in (iz0p + 8, iz0p + 18):
    box(ix0p + 2, ix0p + 5, PY + 7, PY + 8, sz_, sz_ + 4, CERAMIC)
    box(ix0p, ix0p + 1, PY + 9, PY + 11, sz_ + 1, sz_ + 3, CHROME)
box(ix0p, ix0p + 1, PY + 11, PY + 22, iz0p + 4, iz0p + 26, MIRROR)
box(ix0p, ix0p + 1, PY + 22, PY + 23, iz0p + 4, iz0p + 26, COVE_LAMP)
box(ix0p + 22, ix0p + 23, PY, PY + 22, iz0p, iz0p + 14, GLASS)                     # shower screen
box(ix0p + 12, ix0p + 22, PY, PY + 1, iz0p, iz0p + 14, MARBLE_B)
box(ix0p + 18, ix0p + 20, PCEIL - 2, PCEIL, iz0p + 6, iz0p + 8, CHROME)            # rain head
# ---- terrace: oak deck, glass balustrade, jacuzzi with underwater lights, loungers, string lights
for x in range(PH_X0, PH_X1):
    for z in range(PT_Z0, PH_Z0):
        G[x, PY - 1, z] = WOOD_MED if (x // 2) % 2 else WOOD_MED2
# east side (the street view): low glass balustrade; west side (the roof walkway): 2.4 m glass wall
box(PH_X1 - 1, PH_X1, PY, PY + 1, PT_Z0, PH_Z0, PICFRAME)
box(PH_X1 - 1, PH_X1, PY + 1, PY + 10, PT_Z0, PH_Z0, GLASS)
box(PH_X1 - 1, PH_X1, PY + 10, PY + 11, PT_Z0, PH_Z0, PICFRAME)
for z in range(PT_Z0, PH_Z0, 10):
    box(PH_X1 - 1, PH_X1, PY, PY + 11, z, z + 1, PICFRAME)
box(PH_X0, PH_X0 + 1, PY, PY + 1, PT_Z0, PH_Z0, PICFRAME)
box(PH_X0, PH_X0 + 1, PY + 1, PY + 24, PT_Z0, PH_Z0, GLASS)
box(PH_X0, PH_X0 + 1, PY + 24, PY + 25, PT_Z0, PH_Z0, PICFRAME)
for z in range(PT_Z0, PH_Z0, 12):
    box(PH_X0, PH_X0 + 1, PY, PY + 25, z, z + 1, PICFRAME)
# south side (facing the roof lift landing): a 2.4 m glass screen with a wooden door
box(PH_X0, PH_X1, PY, PY + 1, PT_Z0, PT_Z0 + 1, PICFRAME)
box(PH_X0, PH_X1, PY + 1, PY + 24, PT_Z0, PT_Z0 + 1, GLASS)
box(PH_X0, PH_X1, PY + 24, PY + 25, PT_Z0, PT_Z0 + 1, PICFRAME)
for x in list(range(PH_X0, PH_X1, 12)) + [PH_X1 - 1]:
    box(x, x + 1, PY, PY + 25, PT_Z0, PT_Z0 + 1, PICFRAME)
GATE_X = (PH_X1 - 21, PH_X1 - 11)                                                  # door to the SE lift (roof stop)
box(GATE_X[0] - 1, GATE_X[1] + 1, PY, PY + 23, PT_Z0, PT_Z0 + 1, WOOD_DARK)
box(GATE_X[0], GATE_X[1], PY, PY + 22, PT_Z0, PT_Z0 + 1, 0)
add_door(Frame(GATE_X[0], PT_Z0, 1, 0, 0, 1), 0, 10, PY, PY + 22, 0, 1, lambda a, b, c, A, B, C: wood_door(A - 1 - a, b, c, A, B, C),
         hinge=(10, 0), open_dir=(0, -1), tag="hoteldoor penthouse", stop=WOOD_DARK)
JX, JZ, JR = PH_X0 + 36, PT_Z0 + 24, 11.5                                          # jacuzzi
for x in range(int(JX - JR - 2), int(JX + JR + 3)):
    for z in range(int(JZ - JR - 2), int(JZ + JR + 3)):
        d_ = np.hypot(x + 0.5 - JX, z + 0.5 - JZ)
        if d_ < JR - 2:
            G[x, PY - 1, z] = POOL_TILE if (x + z) % 3 else POOL_TILE2
            box(x, x + 1, PY, PY + 1, z, z + 1, POOL_TILE2 if d_ < JR - 4 else WHITE_TILE)   # seat ring
        elif d_ < JR:
            box(x, x + 1, PY, PY + 6, z, z + 1, MARBLE_W2)
        if JR - 2 <= d_ < JR + 0.8:
            G[x, PY + 6, z] = MARBLE_W
for a_ in (30, 150, 270):
    lx_ = int(round(JX + (JR - 3.4) * np.cos(np.radians(a_)))); lz_ = int(round(JZ + (JR - 3.4) * np.sin(np.radians(a_))))
    G[lx_, PY + 1, lz_] = POOL_LAMP
    light(lx_ + 0.5 - 1.2 * np.cos(np.radians(a_)), PY + 2.5, lz_ + 0.5 - 1.2 * np.sin(np.radians(a_)), (0.55, 0.85, 1.0), 0.9, 0.1)
POOLS.append((PY + 5.0, 4.0, [(JX + (JR - 3.2) * np.cos(np.radians(a)), JZ + (JR - 3.2) * np.sin(np.radians(a))) for a in range(0, 360, 30)],
              dict(wave=0.04, ripple=0.5, motion=0.3, foam=0.4)))
for (lx_, lz_) in ((PH_X0 + 4, PT_Z0 + 8), (PH_X0 + 4, PT_Z0 + 32)):              # loungers (along x)
    box(lx_, lx_ + 18, PY + 3, PY + 4, lz_, lz_ + 7, LOUNGER)
    for i in range(6):
        box(lx_ + i, lx_ + i + 2, PY + 4 + i, PY + 5 + i, lz_, lz_ + 7, LOUNGER)
    for (fx_, fz_) in ((lx_ + 1, lz_), (lx_ + 1, lz_ + 6), (lx_ + 16, lz_), (lx_ + 16, lz_ + 6)):
        box(fx_, fx_ + 1, PY, PY + 3, fz_, fz_ + 1, CHROME)
    box(lx_ + 6, lx_ + 14, PY + 4, PY + 5, lz_ + 1, lz_ + 6, TOWEL)
STR_Z = (PT_Z0 + 2, PH_Z0 - 4)                                                    # festoon lights between two posts
for zz in STR_Z:
    for xp_ in (PH_X0 + 2, PH_X1 - 3):
        box(xp_, xp_ + 1, PY, PY + 24, zz, zz + 1, DARK_METAL)
    box(PH_X0 + 2, PH_X1 - 2, PY + 24, PY + 25, zz, zz + 1, DARK_METAL)
    for x in range(PH_X0 + 5, PH_X1 - 4, 4):
        G[x, PY + 23, zz] = LAMPSHADE
light((PH_X0 + PH_X1) / 2, PY + 20, (PT_Z0 + PH_Z0) / 2, (1.0, 0.8, 0.55), 2.2, 0.4)
for (ppx, ppz) in ((PH_X1 - 8, PT_Z0 + 6), (PH_X1 - 8, PH_Z0 - 12)):              # potted olive trees
    for x in range(ppx - 3, ppx + 4):
        for z in range(ppz - 3, ppz + 4):
            if (x - ppx) ** 2 + (z - ppz) ** 2 <= 10:
                box(x, x + 1, PY, PY + 7, z, z + 1, CARP_OR if (x - ppx) ** 2 + (z - ppz) ** 2 > 4 else SOIL)
    box(ppx, ppx + 1, PY + 7, PY + 17, ppz, ppz + 1, TRUNK)
    Xo, Yo, Zo = np.meshgrid(np.arange(ppx - 4, ppx + 5), np.arange(PY + 13, PY + 20), np.arange(ppz - 4, ppz + 5), indexing="ij")
    mo = (((Xo - ppx) ** 2 + ((Yo - PY - 16) * 1.3) ** 2 + (Zo - ppz) ** 2) <= 16) & (hash3(Xo, Yo, Zo, 44) > 0.3)
    mo[4, :5, 4] = True                                                          # (the trunk top is the anchor)
    mo = keep_connected(mo, [(4, 0, 4)]) & (G[Xo, Yo, Zo] == 0)
    G[Xo[mo], Yo[mo], Zo[mo]] = np.where((Xo[mo] + Yo[mo] + Zo[mo]) % 3 > 0, LEAF2, LEAF3)
# ---- switches inside the entrance: lights (a room switch, room "ph") and privacy glass
TAGGED_SHAPES = list(BOWL_BUTTONS) + list(BANQUET_SWITCHES)                                     # (name, arr, gmin, tags): own static shapes
PH_SW = (ENT_X + 13, PY + 11, PH_Z1 - 3)                                 # on the north wall, right of the door (inside)
sw_ = np.full((2, 3, 1), SWITCH, np.uint8); sw_[:, 1, 0] = DARK_METAL
TAGGED_SHAPES.append(("ph_switch_lights", sw_, PH_SW, "roomswitch room=ph on=1 tv=0"))
pv_ = np.full((2, 3, 1), BRASS, np.uint8); pv_[:, 1, 0] = FROST
TAGGED_SHAPES.append(("ph_switch_privacy", pv_, (PH_SW[0] + 4, PH_SW[1], PH_SW[2]), "phprivacy"))
# ---- smart glass: every pane of the suite and the terrace is a pair of static bodies, clear and frosted;
#      main.lua shows one of each pair (privacy switch, and frosted when the roof power is off)
SMART_GLASS = []                                                       # dict(arr, gmin, frost, pane)
PH_GLASS_ZONES = [(PH_X1 - 1, PH_X1, PY + 1, PCEIL - 1, PH_Z0, PH_Z1),             # east wall
                  (PH_X0 + 2, PH_X1 - 2, PY + 1, PCEIL - 1, PH_Z0 + 1, PH_Z0 + 2),   # south wall
                  (ix0p + 22, ix0p + 23, PY, PY + 22, iz0p, iz0p + 14),              # shower screen
                  (PH_X0, PH_X0 + 1, PY + 1, PY + 24, PT_Z0, PH_Z0),                 # terrace west
                  (PH_X0, PH_X1, PY + 1, PY + 24, PT_Z0, PT_Z0 + 1),                 # terrace south
                  (PH_X1 - 1, PH_X1, PY + 1, PY + 10, PT_Z0, PH_Z0)]                 # terrace east (low)
from scipy import ndimage as _ndi_sg
for (x0_, x1_, y0_, y1_, z0_, z1_) in PH_GLASS_ZONES:
    reg_ = G[x0_:x1_, y0_:y1_, z0_:z1_]
    lab_, n_ = _ndi_sg.label(np.isin(reg_, [GLASS, GLASS_EXT]))
    for i_, sl_ in enumerate(_ndi_sg.find_objects(lab_)):
        m_ = lab_[sl_] == i_ + 1
        clear_ = np.where(m_, reg_[sl_], 0).astype(np.uint8)
        gm_ = (x0_ + sl_[0].start, y0_ + sl_[1].start, z0_ + sl_[2].start)
        pane_ = len(SMART_GLASS) // 2
        SMART_GLASS.append(dict(arr=clear_, gmin=gm_, frost=False, pane=pane_))
        SMART_GLASS.append(dict(arr=np.where(m_, FROST, 0).astype(np.uint8), gmin=gm_, frost=True, pane=pane_))
        reg_[sl_][m_] = 0
PH_INTERIOR = (ix0p, ix1p, PY, PCEIL, iz0p, iz1p)
PENTHOUSE = dict(x0=PH_X0, x1=PH_X1, z0=PH_Z0, z1=PH_Z1, terrace_z0=PT_Z0, entrance_x=ENT_X, ceil=PCEIL,
                 rooms=dict(bar=(bx_b - 10, (Z_LIV + iz1p) // 2), living=(ix0p + 22, fz), dining=(ix0p + 25, dz - 14),
                            bedroom=(ix0p + 26, bz0_b - 32), bath=(ix0p + 12, iz0p + 30), terrace=(PH_X0 + 12, PT_Z0 + 20)))

# ============================================================================
# 10f. Roof electrical room (v3.45): one switchgear for the roof (glasshouse + penthouse + terrace),
#      against the west parapet north of the glasshouse; steel door to the plaza.
# ============================================================================
RE_X0, RE_X1, RE_Z0, RE_Z1 = bx0 + T_EXT, bx0 + T_EXT + 20, GZ1, GZ1 + 20
box(RE_X0, RE_X1, ROOF_Y, ROOF_Y + 24, RE_Z0, RE_Z1, BRICK)
box(RE_X0 + 2, RE_X1 - 2, ROOF_Y, ROOF_Y + 24, RE_Z0 + 2, RE_Z1 - 2, 0)
box(RE_X0 - 1, RE_X1 + 1, ROOF_Y + 24, ROOF_Y + 26, RE_Z0, RE_Z1 + 1, SLAB)
box(RE_X0, RE_X1 + 1, ROOF_Y + 25, ROOF_Y + 26, RE_Z0, RE_Z1 + 1, EXT_TRIM)
paint(RE_X0 + 2, RE_X1 - 2, ROOF_Y - 1, ROOF_Y, RE_Z0 + 2, RE_Z1 - 2, STAIR_CONC)
RE_DZ = RE_Z0 + 3                                                       # door in the east wall, opens out
box(RE_X1 - 2, RE_X1, ROOF_Y, ROOF_Y + 21, RE_DZ, RE_DZ + 9, 0)
add_door(Frame(RE_X1 - 1, RE_DZ, 0, 1, 1, 0), 0, 9, ROOF_Y, ROOF_Y + 21, 0, 1,
         steel_door, hinge=(0, 1), open_dir=(0, 1), stop=DARK_METAL)
ftext(Frame(RE_X1, 0, 0, -1, -1, 0), "ELEC", -(RE_DZ + 4), ROOF_Y + 27, 0, YELLOW_PAINT)
for zz in range(RE_DZ, RE_DZ + 9, 2):                                   # hazard stripes on the threshold
    box(RE_X1 - 2, RE_X1, ROOF_Y - 1, ROOF_Y, zz, zz + 1, YELLOW_PAINT)
re_fr = Frame(0, 0, 1, 0, 0, 1)
garr, gmin = frame_shape(re_fr, RE_X0 + 2, RE_X0 + 16, ROOF_Y, ROOF_Y + 22, RE_Z1 - 7, RE_Z1 - 2, gear_style)
SWITCHGEAR.append(dict(arr=garr, gmin=gmin, floor=FLOORS, corner="roof"))
box(RE_X0 + 2, RE_X0 + 6, ROOF_Y, ROOF_Y + 12, RE_Z0 + 2, RE_Z0 + 10, HVAC)      # transformer
for zz in range(RE_Z0 + 3, RE_Z0 + 10, 3):
    box(RE_X0 + 6, RE_X0 + 7, ROOF_Y + 2, ROOF_Y + 11, zz, zz + 1, DARK_METAL)
box(RE_X0 + 8, RE_X0 + 11, ROOF_Y + 23, ROOF_Y + 24, RE_Z0 + 8, RE_Z0 + 11, CEIL_LAMP)
light(RE_X0 + 9.5, ROOF_Y + 21.5, RE_Z0 + 9.5, (1.0, 0.95, 0.85), 1.2, 0.2)
ROOF_POWER_ZONES = [(GX0 - 3, GX1 + 3, GZ0 - 3, GZ1 + 1), (PH_X0 - 2, PH_X1 + 2, PT_Z0 - 2, PH_Z1 + 2), (RE_X0, RE_X1, RE_Z0, RE_Z1)]
# the 40 cm gap between the glasshouse and the west parapet read as a passage: a hedge planter fills it
box(bx0 + T_EXT, GX0, ROOF_Y, ROOF_Y + 5, GZ0 - 2, GZ1, BRICK)
box(bx0 + T_EXT, GX0, ROOF_Y + 4, ROOF_Y + 5, GZ0 - 1, GZ1 - 1, SOIL)
Xh, Zh = np.meshgrid(np.arange(bx0 + T_EXT, GX0), np.arange(GZ0 - 1, GZ1 - 1), indexing="ij")
Hh = 3 + (hash3(Xh, np.full_like(Xh, ROOF_Y), Zh, 91) * 3).astype(int)
for (x, z, h_) in zip(Xh.ravel(), Zh.ravel(), Hh.ravel()):
    box(x, x + 1, ROOF_Y + 5, ROOF_Y + 5 + h_, z, z + 1, LEAF2 if (x + z) % 3 else LEAF3)

# ---- the helicopter (my own design): body, main rotor, tail rotor (shapes of one vehicle body)
def helicopter_model():
    X_, Y_, Z_ = 24, 40, 120
    m = np.zeros((X_, Y_, Z_), np.uint8)
    A, B, C = np.meshgrid(np.arange(X_), np.arange(Y_), np.arange(Z_), indexing="ij")
    ac = (X_ - 1) / 2
    # cabin: rounded nose, elliptic section, hollow with a floor
    s = np.clip(np.sqrt((C + 1) / 14.0), 0, 1) * np.where(C > 40, 1 - (C - 40) / 20 * 0.45, 1)
    yb = 6 + (1 - s) * 7; yt = 28 - (1 - s) * 9
    ym, hh, hw = (yb + yt) / 2, (yt - yb) / 2, 11 * s
    outer = (C < 52) & (((A - ac) / np.maximum(hw, 0.1)) ** 2 + ((B - ym) / np.maximum(hh, 0.1)) ** 2 <= 1)
    inner = (C < 50) & (C > 3) & (((A - ac) / np.maximum(hw - 1.6, 0.1)) ** 2 + ((B - ym) / np.maximum(hh - 1.6, 0.1)) ** 2 <= 1)
    shell = outer & ~inner
    m[shell & (B < ym)] = BLANKET_C
    m[shell & (B >= ym)] = SHEET
    m[shell & (np.abs(B - np.round(ym)) < 0.6)] = ART2
    m[shell & (B > ym + 1) & (C >= 2) & (C <= 34)] = GLASS                                   # canopy + side windows
    m[shell & (B > ym + 1) & ((C == 18) | (C == 19))] = SHEET                                  # door pillar
    m[inner & (B <= np.floor(yb) + 2)] = CURT_DARK                                              # cabin floor
    for (sa, sc) in ((5, 14), (5, 24), (14, 14), (14, 24)):                                   # two pairs of seats
        m[sa:sa + 5, 9:13, sc:sc + 5] = UPHOL; m[sa:sa + 5, 13:19, sc + 4:sc + 5] = UPHOL
    m[6:18, 16:18, 6:9] = CURT_DARK                                                             # instrument panel
    m[8:10, 18:19, 7:8] = TV_SCREEN; m[14:16, 18:19, 7:8] = TV_SCREEN
    # tail boom, fin, stabiliser
    for c in range(48, 114):
        hs = 4 - (c - 48) / 66 * 2.2; yc = 20 + (c - 48) / 66 * 6
        sel = (np.abs(A[:, :, c] - ac) <= hs) & (np.abs(B[:, :, c] - yc) <= hs)
        if c < 110:                                                       # hollow boom: a light tail
            sel &= ~((np.abs(A[:, :, c] - ac) <= hs - 1) & (np.abs(B[:, :, c] - yc) <= hs - 1))
        m[:, :, c][sel] = BLANKET_C
        m[:, :, c][sel & (B[:, :, c] >= yc + hs - 1)] = SHEET
    for c in range(102, 119):
        top = int(24 + (c - 102) * 0.95)
        m[11:13, 22:min(top, Y_ - 1), c] = BLANKET_C
        m[11:13, max(top - 3, 22):min(top, Y_ - 1), c] = ART2
    m[2:22, 24:25, 98:105] = SHEET
    # engine cowling, exhaust, mast
    m[7:17, 26:32, 18:44] = TOWEL
    m[8:16, 30:32, 22:40] = SHEET
    m[10:14, 27:30, 44:47] = DARK_METAL
    m[10:14, 32:38, 25:29] = DARK_METAL
    m[10:14, 29:33, 108:116] = DARK_METAL                                                     # tail rotor gearbox (centred y 31, z 112)
    # skids + struts
    m[7:17, 7:9, 6:20] = ELEV_RAIL                                     # ballast under the cockpit floor (heavy metal)
    for sa in (2, 20):
        m[sa:sa + 2, 0:2, 4:66] = DARK_METAL                                    # skids reach well behind the mast
        m[sa:sa + 2, 2:3, 64:67] = DARK_METAL
        m[sa:sa + 2, 2:3, 2:5] = DARK_METAL
        for sc in (14, 46):
            m[sa:sa + 2, 2:10, sc:sc + 2] = DARK_METAL
            m[min(sa, 6):max(sa + 2, 18), 8:10, sc:sc + 2] = DARK_METAL
    # nav lights, landing light
    m[0, 18:20, 26:28] = BLANKET_B; m[X_ - 1, 18:20, 26:28] = EXIT_SIGN
    m[10:14, 5:7, 6:9] = CEIL_LAMP
    m = np.where(keep_connected(m > 0, [(12, 7, 30)]), m, 0).astype(np.uint8)
    return m

def rotor_model(R_=50):
    """main rotor = its own body: blades (y 8), hub, and a shaft (y 0..5) that sits inside the mast,
    held there by two ball joints on the shaft axis (= a hinge about the vertical)."""
    # even size: blades, hub and shaft are all centred on the same line (grid x = z = R_), which is
    # exactly the joint axis and the mast centre -> the rotor spins in place, it does not orbit
    r = np.zeros((2 * R_, 9, 2 * R_), np.uint8)
    r[:, 8, R_ - 1:R_ + 1] = UPHOL; r[R_ - 1:R_ + 1, 8, :] = UPHOL                   # plastic blades
    r[:3, 8, R_ - 1:R_ + 1] = ART2; r[-3:, 8, R_ - 1:R_ + 1] = ART2
    r[R_ - 1:R_ + 1, 8, :3] = ART2; r[R_ - 1:R_ + 1, 8, -3:] = ART2
    r[R_ - 3:R_ + 3, 6:8, R_ - 3:R_ + 3] = DARK_METAL                                # hub (small at blade height:
    r[R_ - 2:R_ + 2, 8, R_ - 2:R_ + 2] = DARK_METAL                                  #  the blades stay breakable)
    r[R_ - 1:R_ + 1, 0:6, R_ - 1:R_ + 1] = CHROME
    return r

def tail_rotor_model(R_=10):
    """tail rotor body: shaft along x (x 0..4, inside the gearbox) and the blades at x = 4."""
    t = np.zeros((5, 2 * R_, 2 * R_), np.uint8)                       # (even size: centred on its axis)
    t[4, R_ - 1:R_ + 1, :] = UPHOL; t[4, :, R_ - 1:R_ + 1] = UPHOL
    t[3:5, R_ - 2:R_ + 2, R_ - 2:R_ + 2] = DARK_METAL
    t[0:4, R_ - 1:R_ + 1, R_ - 1:R_ + 1] = CHROME
    return t

HELI_BODY = helicopter_model()
HELI_ROTOR = rotor_model()
HELI_TAIL = tail_rotor_model()
hx0, hz0 = HCX - 12, HCZ - 60                      # body grid min corner: centred on the pad; the nose (c = 0) faces -z
HELI = dict(gmin=(hx0, RT, hz0),
            rotor_gmin=(hx0 + 12 - 50, RT + 30, hz0 + 27 - 50),       # shaft in the mast, blades 0.8 m higher
            tail_gmin=(hx0 + 10, RT + 31 - 10, hz0 + 112 - 10),       # shaft in the gearbox, blades right of the fin
            seat=(7, 12, 16), light=(12, 4, 7))

def power_floor(gx, gy, gz):
    if gy >= ROOF_Y - 1:
        for (x0_, x1_, z0_, z1_) in ROOF_POWER_ZONES:
            if x0_ <= gx < x1_ and z0_ <= gz < z1_:
                return FLOORS                         # the roof circuit (glasshouse, penthouse, roof electrical room)
        return None
    if not (bx0 <= gx < bx1 and bz0 <= gz < bz1) or (ax0 <= gx < ax1 and az0 <= gz < az1):
        return None                                   # outside the hotel ring, or in the atrium (own supply)
    for k in range(FLOORS):
        if fy(k) - SLAB_T <= gy < fy(k) + FH - SLAB_T:
            return k
    return None
_lt = []
for (gx, gy, gz, rgb, scale, size, tags) in LIGHTS:
    k = power_floor(gx, gy, gz)
    if k == FLOORS and "room=" not in tags and PH_INTERIOR[0] <= gx < PH_INTERIOR[1] and PH_INTERIOR[2] <= gy < PH_INTERIOR[3] \
            and PH_INTERIOR[4] <= gz < PH_INTERIOR[5]:
        tags = (tags + " room=ph rl=ceil").strip()     # the suite's lights hang on its switch by the entrance
    _lt.append((gx, gy, gz, rgb, scale, size, (tags + f" pw={k}").strip() if k is not None else tags))
LIGHTS[:] = _lt

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
    # ---- lamps become their own small shapes, each carrying its light(s) --------------------------
    # Teardown turns a shape's lights off when that shape is damaged. With every lamp a separate shape,
    # shooting a lamp kills exactly its light, and damage anywhere else never touches it.
    EMIT = np.array([i for i, v in PAL.items() if v[1] == "emit" and i not in (CURT_LIT, CURT_LIT2)], np.uint8)
    claimed = np.zeros(G.shape, np.int32)          # lamp id + 1
    lamps = []                                     # dict(vox=set, lights=[...])
    loose = []
    R, B = 4, 7
    for (gx, gy, gz, rgb, scale, size, ltags) in LIGHTS:
        ix, iy, iz = int(gx), int(gy), int(gz)
        x0, y0, z0 = max(ix - R, 0), max(iy - R, 0), max(iz - R, 0)
        win = G[x0:ix + R + 1, y0:iy + R + 1, z0:iz + R + 1]
        X, Y, Z = np.nonzero(np.isin(win, EMIT) | (claimed[x0:ix + R + 1, y0:iy + R + 1, z0:iz + R + 1] > 0))
        if not len(X):
            loose.append((gx * 0.1 - CX, gy * 0.1, gz * 0.1 - CZ, rgb, scale, size, ltags))
            continue
        d2 = (X + x0 + 0.5 - gx) ** 2 + (Y + y0 + 0.5 - gy) ** 2 + (Z + z0 + 0.5 - gz) ** 2
        j = int(np.argmin(d2))
        lv = (X[j] + x0, Y[j] + y0, Z[j] + z0)
        if claimed[lv]:
            lamps[claimed[lv] - 1]["lights"].append((gx, gy, gz, rgb, scale, size, ltags))
            continue
        # flood the lamp's emissive voxels (bounded box around the lamp, unclaimed only)
        lid = len(lamps)
        comp, stack = [], [lv]
        claimed[lv] = lid + 1
        while stack:
            c = stack.pop()
            comp.append(c)
            for d in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)):
                n_ = (c[0] + d[0], c[1] + d[1], c[2] + d[2])
                if all(abs(n_[k] - lv[k]) <= B for k in range(3)) and 0 <= n_[0] < W and 0 <= n_[1] < H and 0 <= n_[2] < D \
                        and not claimed[n_] and G[n_] in EMIT:
                    claimed[n_] = lid + 1
                    stack.append(n_)
        lamps.append(dict(vox=comp, lights=[(gx, gy, gz, rgb, scale, size, ltags)]))
    lamp_files = {}
    for L in lamps:
        V = np.array(L["vox"])
        mn = V.min(0); mx = V.max(0) + 1
        arr = np.zeros(tuple(mx - mn), np.uint8)
        arr[V[:, 0] - mn[0], V[:, 1] - mn[1], V[:, 2] - mn[2]] = G[V[:, 0], V[:, 1], V[:, 2]]
        G[V[:, 0], V[:, 1], V[:, 2]] = 0                       # removed from the world chunks
        key = (arr.shape, arr.tobytes())
        if key not in lamp_files:
            lamp_files[key] = f"lamp_{len(lamp_files)}"
            write_vox(os.path.join(VOXDIR, lamp_files[key] + ".vox"), arr)
        L["file"] = lamp_files[key]
        sx, sy, sz = arr.shape
        L["pos"] = ((mn[0] + sx // 2) * 0.1 - CX, mn[1] * 0.1, (mn[2] + sz - sz // 2) * 0.1 - CZ)
        L["arr"] = arr; L["gmin"] = tuple(int(v) for v in mn)
    LAMPS[:] = lamps
    # ---- light fittings with no light of their own (decor wall sconces, the unlit half of the ceiling
    #      lamps) on a hotel floor become small shapes on that floor's circuit, so a blackout darkens them too
    from scipy import ndimage as _ndi
    GLOW_IDX = np.array([CEIL_LAMP, COVE_LAMP, LAMPSHADE], np.uint8)
    gx0_, gx1_, gy0_, gy1_, gz0_, gz1_ = bx0, bx1, G0 - SLAB_T, min(H, 256), bz0, bz1
    glab_, gn_ = _ndi.label(np.isin(G[gx0_:gx1_, gy0_:gy1_, gz0_:gz1_], GLOW_IDX))
    GLOWS.clear()
    for i_, sl_ in enumerate(_ndi.find_objects(glab_)):
        V = np.argwhere(glab_[sl_] == i_ + 1) + [sl_[0].start + gx0_, sl_[1].start + gy0_, sl_[2].start + gz0_]
        c_ = V.mean(0)
        k_ = power_floor(int(c_[0]), int(c_[1]), int(c_[2]))
        if k_ is None or len(V) < 2:                  # (single dots: the elevator floor dials, own supply)
            continue
        mn = V.min(0); mx = V.max(0) + 1
        arr = np.zeros(tuple(mx - mn), np.uint8)
        arr[V[:, 0] - mn[0], V[:, 1] - mn[1], V[:, 2] - mn[2]] = G[V[:, 0], V[:, 1], V[:, 2]]
        G[V[:, 0], V[:, 1], V[:, 2]] = 0
        key = (arr.shape, arr.tobytes())
        if key not in lamp_files:
            lamp_files[key] = f"lamp_{len(lamp_files)}"
            write_vox(os.path.join(VOXDIR, lamp_files[key] + ".vox"), arr)
        sx, sy, sz = arr.shape
        in_ph = all(PH_INTERIOR[2 * a] <= c_[a] < PH_INTERIOR[2 * a + 1] for a in range(3))
        GLOWS.append(dict(file=lamp_files[key], floor=k_, arr=arr, gmin=tuple(int(v) for v in mn), room="ph" if in_ph else None,
                          pos=((mn[0] + sx // 2) * 0.1 - CX, mn[1] * 0.1, (mn[2] + sz - sz // 2) * 0.1 - CZ)))
    # Few, large shapes (<= 256 per axis), split only along party-wall planes and never
    # horizontally: Teardown judges support per shape, so seams through structure make
    # whole slabs of wall drop off when something near a seam is shot.
    XS_MAIN = [0, ax0 + 2 * SHORT_BAY_W, W]
    XS_ANNEX = [0, A_X0 - 16, A_X1 + 16, W]          # the pool hall stays in one shape
    BANDS = [(0, az0 + 2 * LONG_BAY_W, XS_MAIN), (az0 + 2 * LONG_BAY_W, az0 + 6 * LONG_BAY_W, XS_MAIN),
             (az0 + 6 * LONG_BAY_W, AZ0 - 6, XS_MAIN), (AZ0 - 6, D, XS_ANNEX)]
    YS = [0, SEAM, H]                                  # B2 band | the rest
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
    road_voxes = []
    for xi, (x0, x1_) in enumerate(zip(XS_MAIN, XS_MAIN[1:])):
        sub = ROAD[x0:x1_]
        nz = np.nonzero(sub)
        if len(nz[0]) == 0:
            continue
        bx_ = (nz[0].min(), nz[0].max() + 1); by_ = (nz[1].min(), nz[1].max() + 1); bz_ = (nz[2].min(), nz[2].max() + 1)
        sub = sub[bx_[0]:bx_[1], by_[0]:by_[1], bz_[0]:bz_[1]]
        gx0, gy0, gz0 = x0 + bx_[0], by_[0], bz_[0] - RD                 # grid z is negative south of the map
        sx, sy, sz = sub.shape
        name = f"road_{xi}"
        total += write_vox(os.path.join(VOXDIR, name + ".vox"), sub)
        road_voxes.append((name, ((gx0 + sx // 2) * 0.1 - CX, gy0 * 0.1, (gz0 + sz - sz // 2) * 0.1 - CZ)))
    write_vox(os.path.join(VOXDIR, "road_lamp.vox"), ROAD_LAMPS[0][0])
    for pname, arr in PROP_SHAPES.items():
        write_vox(os.path.join(VOXDIR, pname + ".vox"), arr)
    # spawnable prefabs (game spawn menu via spawn.txt, and the map's own N-key spawn menu)
    pdir = os.path.join(OUT, "prefab")
    os.makedirs(pdir, exist_ok=True)
    lines = []
    for pname, label in SPAWNABLE:
        with open(os.path.join(pdir, pname + ".xml"), "w") as f:
            tg_ = f' tags="{PROP_TAGS[pname]}"' if pname in PROP_TAGS else ""
            f.write(f'<prefab version="1.6.0">\n\t<group name="{pname}">\n\t\t<body dynamic="true"{tg_}>\n'
                    f'\t\t\t<vox pos="0 0 0" file="MOD/vox/{pname}.vox" object="shape"'
                    + (f' density="{PROP_DENSITY[pname]}"' if pname in PROP_DENSITY else '') + '/>\n\t\t</body>\n\t</group>\n</prefab>\n')
        if not pname.startswith("car_"):
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
    def f3(a): return " ".join(f"{t:.3f}".rstrip("0").rstrip(".") if abs(t) > 1e-9 else "0" for t in a)
    def light_xml(p, rgb, scale, size, ind="\t\t\t", ltags=""):
        t_ = f' tags="{ltags}"' if ltags else ""
        return f'{ind}<light{t_} pos="{f3(p)}" type="sphere" color="{f3(rgb)}" scale="{scale:g}" size="{size:g}"/>\n'

    spawn = ((ax0 + ax1) / 2 * 0.1 - CX, G0 * 0.1 + 0.1, (az0 + 18) * 0.1 - CZ)
    half_w, half_d = W / 2 * 0.1, D / 2 * 0.1
    south = -half_d - RD * 0.1                                             # the street extends the map south
    xml = []
    # scene format version as the current game writes it: "6" was read as a pre-spawn-menu legacy level
    xml.append('<scene version="2.0.0" shadowVolume="%d %d %d">\n' % (int(W * 0.1) + 4, int(H * 0.1) * 2 + 6, int(D * 0.1) + 4))
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
    for (bx_, bz_) in [(-half_w, south), (half_w, south), (half_w, half_d), (-half_w, half_d)]:
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
    ra = RADIO["arr"]; rsx, rsy, rsz = ra.shape; rgx, rgy, rgz = RADIO["gmin"]
    write_vox(os.path.join(VOXDIR, "radio.vox"), ra)
    rpos = ((rgx + rsx // 2) * 0.1 - CX, rgy * 0.1, (rgz + rsz - rsz // 2) * 0.1 - CZ)
    xml.append(f'\t<vox name="poolradio" tags="radio" pos="{f3(rpos)}" file="MOD/vox/radio.vox" object="shape"/>\n')
    def body_origin(arr, gmin):
        sx, sy, sz = arr.shape
        gx, gy, gz = gmin
        return ((gx + sx // 2) * 0.1 - CX, gy * 0.1, (gz + sz - sz // 2) * 0.1 - CZ)
    shape_files = {}
    def shape_file(prefix, arr):
        key = (prefix, arr.shape, arr.tobytes())
        if key not in shape_files:
            shape_files[key] = f"{prefix}_{sum(1 for k_ in shape_files if k_[0] == prefix)}"
            write_vox(os.path.join(VOXDIR, shape_files[key] + ".vox"), arr)
        return shape_files[key]
    xml.append('\t<group name="curtains" pos="0 0 0">\n')
    for i, c in enumerate(CURTAINS):
        o = body_origin(c["arr"], c["gmin"])
        tg = f"curtain cid={c['cid']} sx={c['slide'][0] * 0.1:.2f} sz={c['slide'][1] * 0.1:.2f}" + (" startopen" if c["start_open"] else "") \
             + (f" room={c['rid']}" if c["lit"] else "")
        xml.append(f'\t\t<body name="curtain{i}" tags="{tg}" pos="{f3(o)}"><vox pos="0 0 0" file="MOD/vox/{shape_file("curtain", c["arr"])}.vox" object="shape"/></body>\n')
    xml.append('\t</group>\n')
    xml.append('\t<group name="smartglass" pos="0 0 0">\n')
    for i, sg in enumerate(SMART_GLASS):
        o = body_origin(sg["arr"], sg["gmin"])
        xml.append(f'\t\t<body name="smartglass{i}" tags="smartglass pane={sg["pane"]}' + (' frost' if sg["frost"] else '') +
                   f'" pos="{f3(o)}"><vox pos="0 0 0" file="MOD/vox/{shape_file("smartglass", sg["arr"])}.vox" object="shape"/></body>\n')
    xml.append('\t</group>\n')
    xml.append('\t<group name="electrical" pos="0 0 0">\n')
    for g in SWITCHGEAR:
        xml.append(f'\t\t<vox tags="switchgear floor={g["floor"]} corner={g["corner"]}" pos="{f3(body_origin(g["arr"], g["gmin"]))}" '
                   f'file="MOD/vox/{shape_file("switchgear", g["arr"])}.vox" object="shape"/>\n')
    xml.append('\t</group>\n')
    xml.append('\t<group name="roomswitches" pos="0 0 0">\n')
    for (sarr, smin, rid, on, tv) in ROOM_SWITCHES:
        xml.append(f'\t\t<vox tags="roomswitch room={rid} on={int(on)} tv={int(tv)}" pos="{f3(body_origin(sarr, smin))}" '
                   f'file="MOD/vox/{shape_file("switch", sarr)}.vox" object="shape"/>\n')
    xml.append('\t</group>\n')
    xml.append('\t<group name="mission" pos="0 0 0">\n')
    bo = body_origin(BELL["arr"], BELL["gmin"])
    xml.append(f'\t\t<body name="deskbell" tags="deskbell" pos="{f3(bo)}"><vox pos="0 0 0" file="MOD/vox/{shape_file("bell", BELL["arr"])}.vox" object="shape"/></body>\n')
    mx, my, mz = MISSION_START
    xml.append(f'\t\t<location tags="missionstart" pos="{f3((mx * 0.1 - CX, my * 0.1, mz * 0.1 - CZ))}"/>\n')
    for i, kc in enumerate(KEYCARDS):
        o = body_origin(kc["arr"], kc["gmin"])
        xml.append(f'\t\t<body name="keycard{i}" tags="keycard floor={kc["floor"] + 1}" pos="{f3(o)}">'
                   f'<vox pos="0 0 0" file="MOD/vox/{shape_file("keycard", kc["arr"])}.vox" object="shape">'
                   f'<light pos="0 0.15 -0.05" type="sphere" color="1 0.62 0.9" scale="0.8" size="0.05"/></vox></body>\n')
    for i, m in enumerate(DECOR_MQ):
        o = body_origin(m["arr"], m["gmin"])
        xml.append(f'\t\t<body name="dreamdecor{i}" tags="dreamdecor" pos="{f3(o)}">'
                   f'<vox pos="0 0 0" file="MOD/vox/{shape_file("mannequin", m["arr"])}.vox" object="shape"/></body>\n')
    for i, m in enumerate(MANNEQUINS):
        o = body_origin(m["arr"], m["gmin"])
        (ax_, az_), (bx_, bz_) = m["seg"]
        seg = f"{ax_ * 0.1 - CX:.2f},{az_ * 0.1 - CZ:.2f},{bx_ * 0.1 - CX:.2f},{bz_ * 0.1 - CZ:.2f}"
        xml.append(f'\t\t<body name="mannequin{i}" tags="mannequin seg={seg} fx={m["front"][0]} fz={m["front"][1]}" pos="{f3(o)}">'
                   f'<vox pos="0 0 0" file="MOD/vox/{shape_file("mannequin", m["arr"])}.vox" object="shape">'
                   f'<light pos="0 2.0 0" type="sphere" color="1 0.78 0.95" scale="0.5" size="0.3"/></vox></body>\n')
    xml.append('\t</group>\n')
    xml.append('\t<group name="lamps" pos="0 0 0">\n')
    for i, L in enumerate(lamps):
        px_, py_, pz_ = L["pos"]
        xml.append(f'\t\t<vox name="lamp{i}" pos="{f3(L["pos"])}" file="MOD/vox/{L["file"]}.vox" object="shape">\n')
        for (gx, gy, gz, rgb, scale, size, ltags) in L["lights"]:
            rel = (gx * 0.1 - CX - px_, gy * 0.1 - py_, gz * 0.1 - CZ - pz_)
            xml.append(light_xml(rel, rgb, scale, size, ltags=ltags))
        xml.append('\t\t</vox>\n')
    for i, L in enumerate(GLOWS):
        xml.append(f'\t\t<vox name="glow{i}" tags="glow pw={L["floor"]}{' room=' + L['room'] if L.get('room') else ''}" pos="{f3(L["pos"])}" file="MOD/vox/{L["file"]}.vox" object="shape"/>\n')
    xml.append('\t</group>\n')
    for pool_ in POOLS:
        sy_, dep, pts = pool_[:3]
        wa = dict(wave=0.02, ripple=0.25, motion=0.05, foam=0); wa.update(pool_[3] if len(pool_) > 3 else {})
        # polygon water anchored at the pool centre; vertices relative to it (like every child node).
        # 'size' is given too, so even a box interpretation stays inside the pool.
        xs_ = [q[0] for q in pts]; zs_ = [q[1] for q in pts]
        pcx, pcz = (min(xs_) + max(xs_)) / 2, (min(zs_) + max(zs_)) / 2
        wx_, wz_ = pcx * 0.1 - CX, pcz * 0.1 - CZ
        xml.append(f'\t<water type="polygon" pos="{wx_:.3f} {sy_ * 0.1:.2f} {wz_:.3f}" size="{(max(xs_) - min(xs_)) * 0.1:.2f} '
                   f'{(max(zs_) - min(zs_)) * 0.1:.2f}" depth="{dep * 0.1:.2f}" wave="{wa["wave"]:g}" ripple="{wa["ripple"]:g}" '
                   f'motion="{wa["motion"]:g}" foam="{wa["foam"]:g}">\n')
        for (vx, vz) in pts:
            xml.append(f'\t\t<vertex pos="{(vx - pcx) * 0.1:.3f} {(vz - pcz) * 0.1:.3f}"/>\n')
        xml.append('\t</water>\n')
    for nm_, arr_ in (("heli_body", HELI_BODY), ("heli_rotor", HELI_ROTOR), ("heli_tail", HELI_TAIL)):
        write_vox(os.path.join(VOXDIR, nm_ + ".vox"), arr_)
    def org(arr_, gm):
        sx, sy, sz = arr_.shape
        return ((gm[0] + sx // 2) * 0.1 - CX, gm[1] * 0.1, (gm[2] + sz - sz // 2) * 0.1 - CZ)
    hb = org(HELI_BODY, HELI["gmin"])
    rel = lambda o: (o[0] - hb[0], o[1] - hb[1], o[2] - hb[2])
    bsx, bsy, bsz = HELI_BODY.shape
    def in_body(a, b, c):        # body-array cell -> position relative to the body vox origin
        return ((a + 0.5 - bsx // 2) * 0.1, b * 0.1, (c + 0.5 - (bsz - bsz // 2)) * 0.1)
    xml.append(f'\t<vehicle name="helicopter" tags="helicopter" pos="0 0 0" driven="false" topspeed="0" acceleration="0" strength="1">\n'
               f'\t\t<body tags="helibody" pos="{f3(hb)}" dynamic="true">\n'
               f'\t\t\t<vox pos="0 0 0" file="MOD/vox/heli_body.vox" object="shape" density="0.4">\n'
               f'\t\t\t\t<location tags="player" pos="{f3(in_body(*HELI["seat"]))}" rot="0 0 0"/>\n'
               f'\t\t\t\t<location tags="vital" pos="{f3(in_body(12, 28, 30))}"/>\n'
               f'\t\t\t\t<light pos="{f3(in_body(*HELI["light"]))}" rot="-60 0 0" type="cone" color="1 .95 .85" scale="12" angle="60" penumbra="25" size="0.1"/>\n'
               f'\t\t\t\t<light pos="{f3(in_body(-1, 19, 27))}" type="sphere" color="1 0.1 0.1" scale="0.8" size="0.05"/>\n'
               f'\t\t\t\t<light pos="{f3(in_body(24, 19, 27))}" type="sphere" color="0.1 1 0.2" scale="0.8" size="0.05"/>\n'
               f'\t\t\t</vox>\n'
               f'\t\t</body>\n\t</vehicle>\n')
    # rotors: separate light bodies, each on two ball joints along its axis (a hinge without any axis convention)
    def joint_rel(arr_, a, b, c):
        sx, sy, sz = arr_.shape
        return ((a - sx // 2) * 0.1, b * 0.1, (c - (sz - sz // 2)) * 0.1)
    ro_ = org(HELI_ROTOR, HELI["rotor_gmin"])
    xml.append(f'\t<body name="helirotor" tags="helirotor" pos="{f3(ro_)}" dynamic="true">\n'
               f'\t\t<vox pos="0 0 0" file="MOD/vox/heli_rotor.vox" object="shape" density="0.25">\n'
               f'\t\t\t<joint pos="{f3(joint_rel(HELI_ROTOR, 50, 2.5, 50))}" type="ball" size="0.1"/>\n'
               f'\t\t\t<joint pos="{f3(joint_rel(HELI_ROTOR, 50, 5.5, 50))}" type="ball" size="0.1"/>\n'
               f'\t\t</vox>\n\t</body>\n')
    to_ = org(HELI_TAIL, HELI["tail_gmin"])
    xml.append(f'\t<body name="helitail" tags="helitail" pos="{f3(to_)}" dynamic="true">\n'
               f'\t\t<vox pos="0 0 0" file="MOD/vox/heli_tail.vox" object="shape" density="0.25">\n'
               f'\t\t\t<joint pos="{f3(joint_rel(HELI_TAIL, 0.5, 10, 10))}" type="ball" size="0.1"/>\n'
               f'\t\t\t<joint pos="{f3(joint_rel(HELI_TAIL, 3.5, 10, 10))}" type="ball" size="0.1"/>\n'
               f'\t\t</vox>\n\t</body>\n')
    for (nm_, arr_, gm_, tg_) in TAGGED_SHAPES:
        write_vox(os.path.join(VOXDIR, nm_ + ".vox"), arr_)
        xml.append(f'\t<vox name="{nm_}" tags="{tg_}" pos="{f3(org(arr_, gm_))}" file="MOD/vox/{nm_}.vox" object="shape"/>\n')
    xml.append('\t<group name="rooftop" pos="0 0 0">\n')
    for (nm_, arr_, gm_, lts_) in ROOF_SHAPES:
        write_vox(os.path.join(VOXDIR, nm_ + ".vox"), arr_)
        o_ = org(arr_, gm_)
        xml.append(f'\t\t<vox name="{nm_}" pos="{f3(o_)}" file="MOD/vox/{nm_}.vox" object="shape"' + ('>\n' if lts_ else '/>\n'))
        for (lx_, ly_, lz_, rgb_, sc_, sz_) in lts_:
            k_ = power_floor(int(lx_), int(ly_), int(lz_))
            xml.append(light_xml(((lx_ + 0.5) * 0.1 - CX - o_[0], ly_ * 0.1 - o_[1], (lz_ + 0.5) * 0.1 - CZ - o_[2]), rgb_, sc_, sz_,
                                 ltags=f"pw={k_}" if k_ is not None else ""))
        if lts_:
            xml.append('\t\t</vox>\n')
    xml.append('\t</group>\n')
    xml.append('\t<group name="street" pos="0 0 0">\n')
    for (name_, pos_) in road_voxes:
        xml.append(f'\t\t<vox name="{name_}" pos="{f3(pos_)}" file="MOD/vox/{name_}.vox" object="shape"/>\n')
    for i, (arr_, (lx_, ly_, lz_), (qx, qy, qz)) in enumerate(ROAD_LAMPS):
        sx, sy, sz = arr_.shape
        lp = ((lx_ + sx // 2) * 0.1 - CX, ly_ * 0.1, (lz_ + sz - sz // 2) * 0.1 - CZ)
        rel = ((qx + 0.5) * 0.1 - CX - lp[0], qy * 0.1 - lp[1], (qz + 0.5) * 0.1 - CZ - lp[2])
        xml.append(f'\t\t<vox name="streetlamp{i}" pos="{f3(lp)}" file="MOD/vox/road_lamp.vox" object="shape">\n')
        xml.append(light_xml(rel, (1.0, 0.75, 0.45), 6.0, 0.3))
        xml.append('\t\t</vox>\n')
    for (kind_, fb_, cx_, cy_, cz_, ry_) in ROAD_CARS:
        xml.append(f'\t\t<location tags="carspawn kind={kind_} fallback={fb_}" pos="{cx_ * 0.1 - CX:.2f} {cy_ * 0.1 + 0.05:.2f} {cz_ * 0.1 - CZ:.2f}" rot="0 {ry_} 0"/>\n')
    xml.append('\t</group>\n')
    for (kind_, fb_, gx_, gy_, gz_, ry_) in CAR_SPOTS:
        cxp, czp = (gx_ + 10) * 0.1 - CX, (gz_ + 22) * 0.1 - CZ                   # bay centre on the ground
        xml.append(f'\t<location tags="carspawn kind={kind_} fallback={fb_}" pos="{cxp:.2f} {gy_ * 0.1 + 0.05:.2f} {czp:.2f}" rot="0 {ry_} 0"/>\n')
    # where the pool sounds may be heard: the pool hall, and (quieter) the glass connector to it
    def zone(tag, gx0, gx1, gy0, gy1, gz0, gz1):
        xml.append(f'\t<location tags="soundzone kind={tag} x0={gx0 * 0.1 - CX:.2f} x1={gx1 * 0.1 - CX:.2f} y0={gy0 * 0.1:.2f} '
                   f'y1={gy1 * 0.1:.2f} z0={gz0 * 0.1 - CZ:.2f} z1={gz1 * 0.1 - CZ:.2f}" pos="{f3(((gx0 + gx1) * 0.05 - CX, gy0 * 0.1, (gz0 + gz1) * 0.05 - CZ))}"/>\n')
    zone("hall", ix0, ix1, DY - 20, DY + HALL_H + 2, iz0, iz1)
    zone("connector", cxN - CW, cxN + CW, G0 - 2, DY + 30, bz1 - 20, AZ0 + 4)
    # the hotel's public-address announcement (main.lua plays it now and then, softly, anywhere inside)
    xml.append(f'\t<location tags="pazone x0={bx0 * 0.1 - CX:.2f} x1={bx1 * 0.1 - CX:.2f} y0={(YB2 - 2) * 0.1:.2f} y1={(ROOF_Y + 2) * 0.1:.2f} '
               f'z0={bz0 * 0.1 - CZ:.2f} z1={bz1 * 0.1 - CZ:.2f}" pos="{f3(((bx0 + bx1) * 0.05 - CX, G0 * 0.1, (bz0 + bz1) * 0.05 - CZ))}"/>\n')
    for (ln_, (hx_, hz_), spots_) in BOWL_LANES:                       # bowling: head pin + the lane's two ball spots
        sp_ = " ".join(f"b{j}={(bx_) * 0.1 - CX:.2f},{(G0 + 6) * 0.1 + 0.02:.2f},{bz_ * 0.1 - CZ:.2f}" for j, (bx_, bz_) in enumerate(spots_))
        xml.append(f'\t<location tags="bowlinglane lane={ln_} {sp_}" pos="{f3(((hx_) * 0.1 - CX, G0 * 0.1 + 0.01, hz_ * 0.1 - CZ))}"/>\n')
    xml.append(f'\t<location tags="respawn" pos="{f3(spawn)}" rot="0 180 0"/>\n')
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
            write_vox(os.path.join(VOXDIR, "elev_pad.vox"), barr)
            xml.append(f'\t\t\t<vox tags="elevpad" pos="{f3(rel)}" file="MOD/vox/elev_pad.vox" object="shape"/>\n')
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
        oy += d["yoff"]
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
        f.write("name = Liminal Atrium v3.50\n"
                "author = Claude\n"
                "description = A deserted hotel at night. 6 floors of fully furnished rooms around a purple-lit atrium, "
                "themed corridors, stairwells, elevators, lobby, indoor pool, roof and parking lot, and a basement with an underground "
                "car park and a luxury shopping arcade. Sandbox - break everything. "
                "Dreamcore mission SWEET DREAMS: ring the front-desk bell, follow the pastel dreamers to six lost memories and wake up.\n"
                "tags = Map\n")
    stats = dict(grid=[W, H, D], chunks=len(voxes), voxels=int(total), lights=len(LIGHTS), props=len(PROPS),
                 doors=len(DOORS), door_files=len(door_files), curtains=len(CURTAINS), switches=len(ROOM_SWITCHES), keycards=len(KEYCARDS),
                 mannequins=len(MANNEQUINS), decor_dreamers=len(DECOR_MQ), lamp_shapes=len(lamps), glow_shapes=len(GLOWS), lamp_files=len(lamp_files), lights_free=len(loose), elevators=len(ELEVATORS), calls=len(CALLS),
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
        stamps = [(c_["arr"], c_["gmin"]) for c_ in CURTAINS] + [(w_[0], w_[1]) for w_ in ROOM_SWITCHES] + [(g_["arr"], g_["gmin"]) for g_ in SWITCHGEAR] + [(k_["arr"], k_["gmin"]) for k_ in KEYCARDS] + \
                 [(m_["arr"], m_["gmin"]) for m_ in MANNEQUINS + DECOR_MQ] + [(BELL["arr"], BELL["gmin"])] + [(RADIO["arr"], RADIO["gmin"])] + [(L_["arr"], L_["gmin"]) for L_ in LAMPS] + [(L_["arr"], L_["gmin"]) for L_ in GLOWS] + [(e["arr"], e["gmin"]) for e in ELEVATORS] + [(b_[0], b_[1]) for e in ELEVATORS for b_ in e["buttons"]] \
            + [(c_[0], c_[1]) for c_ in CALLS] + [(t_[1], t_[2]) for t_ in TAGGED_SHAPES] + [(g_["arr"], g_["gmin"]) for g_ in SMART_GLASS if not g_["frost"]]
        for arr, (gx, gy, gz) in stamps:
            sx, sy, sz = arr.shape
            Gp[gx:gx + sx, gy:gy + sy, gz:gz + sz][arr > 0] = arr[arr > 0]
        for (sy_, dep, pts) in [p_[:3] for p_ in POOLS]:
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
