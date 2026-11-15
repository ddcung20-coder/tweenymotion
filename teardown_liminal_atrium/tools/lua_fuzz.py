"""Data-driven fuzz of main.lua: the whole main.xml scene (bodies, shapes, lights, locations, tags) in a mock
Teardown API; the player wanders between tagged things, presses E on whatever is in reach, shapes get shot,
bodies get deleted. Any Lua runtime error is reported with a traceback."""
import sys, math, random, re, collections
import xml.etree.ElementTree as ET
import lupa.lua51 as lupa

import os
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 1
FRAMES = int(sys.argv[2]) if len(sys.argv) > 2 else 6000
rnd = random.Random(SEED)

tree = ET.parse(f"{ROOT}/main.xml").getroot()
def vec(s, d=(0, 0, 0)):
    return [float(v) for v in s.split()] if s else list(d)
def parse_tags(s):
    out = {}
    for t in (s or "").split():
        k, _, v = t.partition("=")
        out[k] = v
    return out

ent = {}           # handle -> dict(kind, tags, pos, body, light_shape, rot)
nh = [10]
def new(kind, **kw):
    nh[0] += 1
    ent[nh[0]] = dict(kind=kind, **kw)
    return nh[0]
WORLD_BODY = new("body", tags={}, pos=[0, 0, 0], rot=[0, 0, 0], dynamic=False)
def walk(el, base, body, shape):
    for c in el:
        p = (vec(c.get("pos")) + [0, 0, 0])[:3]
        wp = [base[i] + p[i] for i in range(3)]
        tg = parse_tags(c.get("tags"))
        if c.tag == "group":
            walk(c, wp, body, shape)
        elif c.tag == "body":
            h = new("body", tags=tg, pos=wp, rot=vec(c.get("rot")), dynamic=c.get("dynamic") == "true", name=c.get("name"))
            walk(c, wp, h, shape)
        elif c.tag == "vox":
            b = body
            if body == WORLD_BODY and tg:
                b = new("body", tags={}, pos=wp, rot=[0, 0, 0], dynamic=False)   # (a tagged static shape)
            h = new("shape", tags=tg, pos=wp, body=b, file=c.get("file"))
            walk(c, wp, b, h)
        elif c.tag == "light":
            new("light", tags=tg, pos=wp, shape=shape or 0)
        elif c.tag == "location":
            new("location", tags=tg, pos=wp, rot=vec(c.get("rot")))
        elif c.tag == "vehicle":
            new("vehicle", tags=tg, pos=wp)
        else:
            walk(c, wp, body, shape)
walk(tree, [0, 0, 0], WORLD_BODY, None)
spawn = vec(tree.find("spawnpoint").get("pos"))
kinds = collections.Counter(e["kind"] for e in ent.values())
print("scene:", dict(kinds))

L = lupa.LuaRuntime(unpack_returned_tuples=True)
g = L.globals()
def lt(seq):
    return L.table_from(list(seq))
def T(pos, rot=None):
    return L.table_from({"pos": lt(pos), "rot": lt(rot or [0, 0, 0, 1])})
def q_euler(e):
    x, y, z = (math.radians(a) / 2 for a in e)
    cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    return [sx * cy * cz + cx * sy * sz, cx * sy * cz + sx * cy * sz, cx * cy * sz - sx * sy * cz, cx * cy * cz - sx * sy * sz]
xf = {}            # body / shape handle -> [pos, rot quat]
for h, e in ent.items():
    if e["kind"] in ("body",):
        xf[h] = [list(e["pos"]), q_euler(e["rot"])]
deleted, broken = set(), set()
reg = {}
state = dict(player=list(spawn), interact=0, press=set(), down=set(), health=1.0, vehicle=0, frame=0)

def tags_of(h):
    return ent[h]["tags"] if h in ent else {}
def find(kind, tag, gl=None):
    return [h for h, e in ent.items() if e["kind"] == kind and tag in e["tags"] and h not in deleted]

api = {}
def f(fn):
    api[fn.__name__] = fn
    return fn
for k in ["SetBool", "SetFloat", "SetString", "SetInt"]:
    api[k] = lambda key, v, *_: reg.__setitem__(key, v)
api["GetBool"] = lambda k: bool(reg.get(k, False))
api["GetFloat"] = lambda k: float(reg.get(k, 0) or 0)
api["GetInt"] = lambda k: int(reg.get(k, 0) or 0)
api["GetString"] = lambda k: str(reg.get(k, ""))
api["HasKey"] = lambda k: k in reg
api["ListKeys"] = lambda k: lt([])
api["LoadSound"] = lambda p, *a: p
api["LoadLoop"] = lambda p, *a: p
api["PlaySound"] = lambda *a: 1
api["PlayLoop"] = lambda *a: None
api["GetVersion"] = lambda: "1.6.0"
api["IsHandleValid"] = lambda h: (h in ent and h not in deleted) or h == WORLD_BODY
api["FindBodies"] = lambda t, g_=None: lt(find("body", t))
api["FindBody"] = lambda t, g_=None: (find("body", t) or [0])[0]
api["FindShapes"] = lambda t, g_=None: lt(find("shape", t))
api["FindShape"] = lambda t, g_=None: (find("shape", t) or [0])[0]
api["FindLights"] = lambda t, g_=None: lt(find("light", t))
api["FindLocations"] = lambda t, g_=None: lt(find("location", t))
api["FindLocation"] = lambda t, g_=None: (find("location", t) or [0])[0]
api["FindVehicle"] = lambda t, g_=None: (find("vehicle", t) or [0])[0]
api["HasTag"] = lambda h, t: t in tags_of(h)
api["GetTagValue"] = lambda h, t: tags_of(h).get(t, "")
@f
def SetTag(h, t, v=""):
    if h in ent: ent[h]["tags"][t] = v if v is not None else ""
@f
def RemoveTag(h, t):
    if h in ent: ent[h]["tags"].pop(t, None)
def body_xf(h):
    if h not in xf: return T([0, 0, 0])
    return T(*xf[h])
api["GetBodyTransform"] = body_xf
@f
def SetBodyTransform(h, t):
    xf[h] = [[t["pos"][i] for i in (1, 2, 3)], [t["rot"][i] for i in (1, 2, 3, 4)]]
@f
def GetShapeWorldTransform(s):
    e = ent.get(s)
    if not e or e["kind"] != "shape": return T([0, 0, 0])
    b = e["body"]
    if b in xf and b != WORLD_BODY:
        bp = xf[b][0]; e0 = ent[b]["pos"]
        return T([e["pos"][i] - e0[i] + bp[i] for i in range(3)], xf[b][1])
    return T(e["pos"])
@f
def GetBodyShapes(b):
    return lt([h for h, e in ent.items() if e["kind"] == "shape" and e["body"] == b and h not in deleted])
api["GetShapeBody"] = lambda s: ent[s]["body"] if s in ent and ent[s]["kind"] == "shape" else 0
api["IsShapeBroken"] = lambda s: s in broken or s in deleted
api["GetShapeVoxelCount"] = lambda s: 0 if s in deleted else (50 if s in broken else 100)
api["GetLightShape"] = lambda l: ent[l]["shape"] if l in ent else 0
api["GetLightTransform"] = lambda l: T(ent[l]["pos"]) if l in ent else T([0, 0, 0])
api["SetLightEnabled"] = lambda *a: None
api["SetShapeEmissiveScale"] = lambda *a: None
api["GetLocationTransform"] = lambda h: T(ent[h]["pos"], q_euler(ent[h].get("rot", [0, 0, 0]))) if h in ent else T([0, 0, 0])
@f
def Delete(h):
    deleted.add(h)
    for s, e in ent.items():
        if e["kind"] == "shape" and e["body"] == h: deleted.add(s)
api["SetBodyDynamic"] = lambda h, v: ent[h].__setitem__("dynamic", bool(v)) if h in ent else None
api["IsBodyDynamic"] = lambda h: bool(ent.get(h, {}).get("dynamic", False))
for k in ["SetBodyVelocity", "SetBodyAngularVelocity", "ConstrainVelocity", "ConstrainOrientation", "ConstrainPosition",
          "SpawnParticle", "SpawnFire", "Explosion", "ParticleReset", "ParticleRadius", "ParticleGravity", "ParticleEmissive",
          "ParticleColor", "SetEnvironmentProperty", "UiTranslate", "UiColor", "UiFont", "UiText", "UiPush", "UiPop", "UiRect",
          "UiAlign", "UiMakeInteractive", "UiTextShadow", "SetToolEnabled", "SetToolAmmo"]:
    api[k] = lambda *a: None
api["GetBodyVelocity"] = lambda h: lt([0, 0, 0])
api["GetBodyAngularVelocity"] = lambda h: lt([0, 0, 0])
api["GetBodyCenterOfMass"] = lambda h: lt([0, 0, 0])
api["GetBodyMass"] = lambda h: 50.0
api["UiCenter"] = lambda: 960; api["UiMiddle"] = lambda: 540; api["UiWidth"] = lambda: 1920; api["UiHeight"] = lambda: 1080
api["UiTextButton"] = lambda *a: rnd.random() < 0.01
api["PauseMenuButton"] = lambda *a: rnd.random() < 0.002
api["GetToolAmmo"] = lambda *a: 0
api["InputPressed"] = lambda k: k in state["press"]
api["InputDown"] = lambda k: k in state["down"]
api["GetPlayerTransform"] = lambda *a: T(state["player"])
api["GetCameraTransform"] = lambda *a: T([state["player"][0], state["player"][1] + 1.7, state["player"][2]], q_euler([0, rnd.uniform(-180, 180), 0]))
api["GetPlayerInteractShape"] = lambda *a: state["interact"]
api["GetPlayerHealth"] = lambda *a: state["health"]
api["SetPlayerHealth"] = lambda *a: None
@f
def SetPlayerTransform(t, *a):
    state["player"] = [t["pos"][i] for i in (1, 2, 3)]
api["GetPlayerVehicle"] = lambda *a: state["vehicle"]
api["GetVehicleBody"] = lambda v: WORLD_BODY
api["GetVehicleHealth"] = lambda v: 1.0
@f
def QueryRaycast(o, d, dist, *a):
    if rnd.random() < 0.5:
        shapes = [h for h, e in ent.items() if e["kind"] == "shape"]
        return True, rnd.uniform(0, dist), lt([0, 1, 0]), rnd.choice(shapes)
    return False, 0, lt([0, 1, 0]), 0
def qrot(q, v):
    x, y, z, w = q
    ix = w * v[0] + y * v[2] - z * v[1]; iy = w * v[1] + z * v[0] - x * v[2]
    iz = w * v[2] + x * v[1] - y * v[0]; iw = -x * v[0] - y * v[1] - z * v[2]
    return [ix * w + iw * -x + iy * -z - iz * -y, iy * w + iw * -y + iz * -x - ix * -z, iz * w + iw * -z + ix * -y - iy * -x]
api["TransformToParentVec"] = lambda t, v: lt(qrot([t["rot"][i] for i in (1, 2, 3, 4)], [v[1], v[2], v[3]]))
api["TransformToParentPoint"] = lambda t, v: lt([a + b for a, b in zip(qrot([t["rot"][i] for i in (1, 2, 3, 4)], [v[1], v[2], v[3]]), [t["pos"][i] for i in (1, 2, 3)])])
api["QuatEuler"] = lambda x=0, y=0, z=0: lt(q_euler([x, y, z]))
api["Quat"] = lambda x=0, y=0, z=0, w=1: lt([x, y, z, w])
def get_quat_euler(q):
    x, y, z, w = (q[i] for i in (1, 2, 3, 4))
    return (math.degrees(math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))),
            math.degrees(math.asin(max(-1, min(1, 2 * (w * y - z * x))))),
            math.degrees(math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))))
api["GetQuatEuler"] = get_quat_euler
for k, v in api.items():
    g[k] = v
L.execute('''
function Vec(x,y,z) return {x or 0,y or 0,z or 0} end
function VecCopy(a) return {a[1],a[2],a[3]} end
function VecLength(a) return math.sqrt(a[1]^2+a[2]^2+a[3]^2) end
function VecAdd(a,b) return {a[1]+b[1],a[2]+b[2],a[3]+b[3]} end
function VecSub(a,b) return {a[1]-b[1],a[2]-b[2],a[3]-b[3]} end
function VecScale(a,s) return {a[1]*s,a[2]*s,a[3]*s} end
function VecDot(a,b) return a[1]*b[1]+a[2]*b[2]+a[3]*b[3] end
function VecNormalize(a) local l=VecLength(a) if l==0 then return {0,0,0} end return VecScale(a,1/l) end
function VecLerp(a,b,t) return {a[1]+(b[1]-a[1])*t,a[2]+(b[2]-a[2])*t,a[3]+(b[3]-a[3])*t} end
function Transform(p,r) return {pos=p or {0,0,0}, rot=r or {0,0,0,1}} end
function DebugPrint() end function DebugWatch() end
setmetatable(_G, {__index=function(t,k) if type(k)=="string" and k:match("^[A-Z]") then UNKNOWN[k]=true; return function() return nil end end end})
UNKNOWN = {}
''')
L.execute('function __run(f, ...) local a = {...} local n = select("#", ...) local ok, err = xpcall(function() return f(unpack(a, 1, n)) end, debug.traceback) return ok, err end')
src = open(f"{ROOT}/main.lua").read()
L.execute(src)
run = g["__run"]
errors = collections.Counter()
def call(name, *a):
    fn = g[name]
    if fn is None: return
    ok, err = run(fn, *a) if a else run(fn)
    if not ok:
        first = str(err).split("\n")[0]
        if first not in errors:
            print("ERROR in", name, "frame", state["frame"], ":\n", err)
        errors[first] += 1
call("init")
interesting = [h for h, e in ent.items() if e["kind"] == "shape" and e["tags"]] + \
              [s for h, e in ent.items() if e["kind"] == "body" and e["tags"] for s in [x for x, ee in ent.items() if ee["kind"] == "shape" and ee["body"] == h][:1]]
all_shapes = [h for h, e in ent.items() if e["kind"] == "shape"]
print("interesting shapes:", len(interesting))
dt = 1 / 60
for fr in range(FRAMES):
    state["frame"] = fr
    state["press"] = set(); state["down"] = set()
    if fr % 30 == 0:
        tgt = rnd.choice(interesting)
        p = api["GetShapeWorldTransform"](tgt)["pos"]
        state["player"] = [p[1] + rnd.uniform(-1, 1), p[2] - 0.5, p[3] + rnd.uniform(-1, 1)]
        state["interact"] = tgt if rnd.random() < 0.8 else 0
    if rnd.random() < 0.15: state["press"].add("interact")
    if rnd.random() < 0.02: state["press"].add(rnd.choice(["n", "m", "esc", "lmb", "rmb", "space", "jump", "crouch"]))
    if rnd.random() < 0.3: state["down"].add(rnd.choice(["up", "down", "left", "right", "jump", "crouch", "space", "ctrl", "w", "s", "a", "d"]))
    if rnd.random() < 0.01: broken.add(rnd.choice(all_shapes))
    if rnd.random() < 0.002: Delete(rnd.choice(all_shapes))
    if rnd.random() < 0.001: state["health"] = 0.0
    elif rnd.random() < 0.01: state["health"] = 1.0
    call("tick", dt); call("update", dt)
    if fr % 2 == 0: call("draw", dt)
print("frames:", FRAMES, "errors:", dict(errors) if errors else "none")
print("unknown API used:", list(L.eval("UNKNOWN").keys()))
