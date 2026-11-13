-- Liminal Atrium - runs automatically when the map is played (mod-root main.lua).
--  1) gives the player the base-game tools with plenty of ammo
--  2) working elevators (call buttons / floor buttons with E) with chime, motor hum, door and music sounds
--  3) building ambience, flickering corridor lights with fluorescent buzz
--  4) creak / thud sounds for the physical (grab-and-pull) doors
--  5) curtains that open / close with E, room lights + TVs switchable with E, automatic sliding doors in the basement (B1)
--  6) the dreamcore mission "SWEET DREAMS": six lost memories, pastel dreamers that show the way

----------------------------------------------------------------------------------------------------
-- tools
----------------------------------------------------------------------------------------------------
-- base-game tools that use ammo (sledge, spraycan, extinguisher, leafblower ... do not)
local AMMO_TOOLS = { blowtorch = true, shotgun = true, plank = true, pipebomb = true, gun = true, bomb = true,
	wire = true, rocket = true, booster = true, rifle = true, explosive = true, steroid = true, turbo = true }

-- every tool the game really has (base game + tool mods), from the registry
local function allTools()
	local ids = {}
	if ListKeys then
		local keys = ListKeys("game.tool")
		for i = 1, #keys do
			-- only real tools (they always have a display name); skip internal / leftover registry nodes
			if HasKey("game.tool." .. keys[i] .. ".name") then ids[#ids + 1] = keys[i] end
		end
	end
	return ids
end

local function giveTools()
	local ids = allTools()
	for i = 1, #ids do
		local id = ids[i]
		SetBool("game.tool." .. id .. ".enabled", true)
		if SetToolEnabled then pcall(SetToolEnabled, id, true) end      -- 2.x API
	end
end

-- write ammo every way the game might read it: 2.x per-player API (no id / host 0 / player 1) and the registry
local function setAmmo(id, n)
	if SetToolAmmo then
		pcall(SetToolAmmo, id, n)
		pcall(SetToolAmmo, id, n, 0)
		pcall(SetToolAmmo, id, n, 1)
	end
	SetFloat("game.tool." .. id .. ".ammo", n)
end

-- lowest ammo the game reports for a tool over all the ways of asking (nil if it cannot tell)
local function readAmmo(id)
	local low = nil
	if GetToolAmmo then
		for _, args in ipairs({ { id }, { id, 0 }, { id, 1 } }) do
			local ok, v = pcall(GetToolAmmo, unpack(args))
			if ok and type(v) == "number" then low = (low == nil) and v or math.min(low, v) end
		end
	end
	local key = "game.tool." .. id .. ".ammo"
	if HasKey(key) then
		local v = GetFloat(key)
		low = (low == nil) and v or math.min(low, v)
	end
	return low
end

local function topUpAmmo()
	local ids = allTools()
	for i = 1, #ids do
		local id = ids[i]
		if AMMO_TOOLS[id] or HasKey("game.tool." .. id .. ".ammo") then
			local a = readAmmo(id)
			if a == nil or a < 200 then setAmmo(id, 999) end
		end
	end
end

-- the tool in the player's hands (2.x API, else 1.x registry)
local function currentTool()
	if GetPlayerTool then
		local ok, v = pcall(GetPlayerTool)
		if ok and type(v) == "string" and v ~= "" then return v end
	end
	return GetString("game.player.tool")
end

----------------------------------------------------------------------------------------------------
-- sounds
----------------------------------------------------------------------------------------------------
local snd = {}

local function loadSounds()
	snd.ding      = LoadSound("MOD/snd/elev_ding.ogg")
	snd.elevDoor  = LoadSound("MOD/snd/elev_door.ogg")
	snd.click     = LoadSound("MOD/snd/btn_click.ogg")
	snd.doorOpen  = LoadSound("MOD/snd/door_open.ogg")
	snd.doorClose = LoadSound("MOD/snd/door_close.ogg")
	snd.hum       = LoadLoop("MOD/snd/elev_hum.ogg")
	snd.muzak     = LoadLoop("MOD/snd/muzak.ogg")
	snd.ambience  = LoadLoop("MOD/snd/ambience.ogg")
	snd.buzz      = LoadLoop("MOD/snd/buzz.ogg")
	snd.pool      = LoadLoop("MOD/snd/pool_ambience.ogg")
	snd.spa       = LoadLoop("MOD/snd/spa_bubbles.ogg")
	snd.song      = LoadLoop("MOD/snd/radio_song.ogg")
	snd.curtain   = LoadSound("MOD/snd/curtain.ogg")
	snd.autodoor  = LoadSound("MOD/snd/autodoor.ogg")
	snd.mall      = LoadLoop("MOD/snd/mall_song.ogg")
	snd.garage    = LoadLoop("MOD/snd/garage_drips.ogg")
	snd.deskbell  = LoadSound("MOD/snd/deskbell.ogg")
	snd.musicbox  = LoadSound("MOD/snd/musicbox.ogg")
	snd.hum       = LoadSound("MOD/snd/dream_hum.ogg")
	snd.checkout  = LoadSound("MOD/snd/checkout.ogg")
	snd.pad       = LoadLoop("MOD/snd/dream_pad.ogg")
end

local function dist(a, b)
	return VecLength(VecSub(a, b))
end

----------------------------------------------------------------------------------------------------
-- physical doors: only sounds (opening / closing is done by hand, physics does the rest)
----------------------------------------------------------------------------------------------------
local doors = {}

local function quatAngle(a, b)
	local d = math.abs(a[1] * b[1] + a[2] * b[2] + a[3] * b[3] + a[4] * b[4])
	if d > 1 then d = 1 end
	return math.deg(2 * math.acos(d))
end

local function doorsInit()
	local bodies = FindBodies("hoteldoor", true)
	for i = 1, #bodies do
		local b = bodies[i]
		local t = GetBodyTransform(b)
		local closedRot = t.rot
		local open = false
		-- doors that start open were placed rotated: their closed orientation is identity
		if quatAngle(t.rot, Quat()) > 5 then
			closedRot = Quat()
			open = true
		end
		doors[#doors + 1] = { body = b, closed = closedRot, open = open }
	end
end

local function doorsTick(cam)
	for i = 1, #doors do
		local d = doors[i]
		if IsHandleValid(d.body) then
			local t = GetBodyTransform(d.body)
			if dist(t.pos, cam) < 25 then
				local ang = quatAngle(t.rot, d.closed)
				if not d.open and ang > 8 then
					d.open = true
					PlaySound(snd.doorOpen, t.pos, 0.7)
				elseif d.open and ang < 3 then
					d.open = false
					PlaySound(snd.doorClose, t.pos, 0.9)
				end
			end
		end
	end
end

----------------------------------------------------------------------------------------------------
-- elevators
--  "elevcar" bodies (dynamic cabs)   tags: shaft floor
--  "elevbtn" shapes (in a cab)       tag : floor
--  "elevcall" shapes (landings)      tags: shaft floor
--  "elevdoor" bodies (landing doors) tags: shaft floor sx sz
----------------------------------------------------------------------------------------------------
local FLOOR_H   = 3.0
local CAB_SPEED = 1.2
local DOOR_RATE = 0.8
local HOLD_TIME = 6.0

local B1_H      = 3.6               -- the basement storey is taller (floor index -1 = B1)
local cars = {}
local carByShaft = {}
local carByBody = {}

local function tagNum(h, t, def)
	local v = tonumber(GetTagValue(h, t))
	if v == nil then return def end
	return v
end

local function floorOff(f)
	if f < 0 then return f * B1_H end
	return f * FLOOR_H
end

local function doorBroken(door)
	if door.loose or not IsHandleValid(door.body) then return true end
	local shapes = GetBodyShapes(door.body)
	return #shapes == 0 or IsShapeBroken(shapes[1])
end

-- turn a landing door into a normal physics object (it will fall / can be knocked around)
local function releaseDoor(door)
	if door.loose then return end
	door.loose = true
	if IsHandleValid(door.body) then
		SetBodyDynamic(door.body, true)
	end
end

-- every half second: a landing door whose wall support has been blown away, or which got damaged, drops
local function supportCheck(c, dt)
	c.supportTimer = (c.supportTimer or 0) - dt
	if c.supportTimer > 0 then return end
	c.supportTimer = 0.5
	for _, door in pairs(c.doors) do
		if not door.loose then
			local gone = 0
			if door.sdir then
				for k = 1, #door.supports do
					-- short ray from just in front of the wall into it: the wall voxel is there or it is not
					local hit, d = QueryRaycast(door.supports[k], door.sdir, 0.2)
					if not hit then gone = gone + 1 end
				end
			end
			if doorBroken(door) or (door.sdir and gone >= 2) then
				releaseDoor(door)
			end
		end
	end
end

local function setDoor(door, amount)
	door.amount = amount
	if doorBroken(door) then return end     -- a damaged landing door stays where it is
	SetBodyTransform(door.body, Transform(VecAdd(door.t0.pos, VecScale(door.slide, amount)), door.t0.rot))
end

local function cabCenter(c)
	return VecAdd(GetBodyTransform(c.body).pos, Vec(0, 1.4, 0))
end

local function elevInit()
	local bodies = FindBodies("elevcar", true)
	for i = 1, #bodies do
		local b = bodies[i]
		local t = GetBodyTransform(b)
		local f = tagNum(b, "floor", 0)
		local shapes = GetBodyShapes(b)
		local count = 0
		for j = 1, #shapes do count = count + GetShapeVoxelCount(shapes[j]) end
		local c = {
			body = b, shaft = GetTagValue(b, "shaft"), floor = f, target = f,
			vox0 = count, broken = false, checkTimer = 0,
			x = t.pos[1], z = t.pos[3], rot = t.rot, y = t.pos[2],
			base = t.pos[2] - floorOff(f), state = "opening", hold = HOLD_TIME, doors = {},
		}
		cars[#cars + 1] = c
		carByShaft[c.shaft] = c
		carByBody[b] = c
	end
	local doorBodies = FindBodies("elevdoor", true)
	for i = 1, #doorBodies do
		local b = doorBodies[i]
		local c = carByShaft[GetTagValue(b, "shaft")]
		if c then
			local d = { body = b, t0 = GetBodyTransform(b), amount = 0, loose = false,
				slide = Vec(tagNum(b, "sx", 0), 0, tagNum(b, "sz", 0)), supports = {} }
			-- support points: world points inside the wall beside / above the door (tags s1..s3 = "x,y,z")
			for k = 1, 3 do
				local v = GetTagValue(b, "s" .. k)
				if v ~= "" then
					local p = {}
					for num in string.gmatch(v, "[^,]+") do p[#p + 1] = tonumber(num) end
					d.supports[#d.supports + 1] = Vec(p[1], p[2], p[3])
				end
			end
			local sd = {}
			for num in string.gmatch(GetTagValue(b, "sdir"), "[^,]+") do sd[#sd + 1] = tonumber(num) end
			d.sdir = (#sd == 2) and Vec(sd[1], 0, sd[2]) or nil
			c.doors[tagNum(b, "floor", 0)] = d
		end
	end
	local btns = FindShapes("elevbtn", true)
	for i = 1, #btns do
		local f = tagNum(btns[i], "floor", 0)
		SetTag(btns[i], "interact", f < 0 and "Floor B1 (arcade)" or ("Floor " .. (f + 1)))
	end
	local calls = FindShapes("elevcall", true)
	for i = 1, #calls do
		SetTag(calls[i], "interact", "Call elevator")
	end
end

local function setState(c, state)
	c.state = state
	local door = c.doors[c.floor]
	if state == "closing" or state == "autoclose" or state == "opening" then
		if door and IsHandleValid(door.body) then
			PlaySound(snd.elevDoor, GetBodyTransform(door.body).pos, 0.8)
		end
	end
	if state == "opening" then
		local p = door and GetBodyTransform(door.body).pos or cabCenter(c)
		PlaySound(snd.ding, p, 0.9)
		PlaySound(snd.ding, cabCenter(c), 0.5)
	end
end

local function request(c, floor)
	if c == nil or floor == nil or c.broken then return end
	c.target = floor
	if (c.state == "idle" or c.state == "autoclose") and floor == c.floor then
		setState(c, "opening")
	end
	c.hold = HOLD_TIME
end

local function elevTick(dt)
	if InputPressed("interact") then
		local s = GetPlayerInteractShape()
		if s ~= 0 and not interactHandled then
			if IsShapeBroken(s) then
				-- a smashed button does nothing
			elseif HasTag(s, "elevbtn") then
				PlaySound(snd.click, GetShapeWorldTransform(s).pos, 0.8)
				request(carByBody[GetShapeBody(s)], tagNum(s, "floor", nil))
			elseif HasTag(s, "elevcall") then
				PlaySound(snd.click, GetShapeWorldTransform(s).pos, 0.8)
				request(carByShaft[GetTagValue(s, "shaft")], tagNum(s, "floor", nil))
			end
		end
	end
	-- continuous sounds: a loop handle plays at one place, so use the cab nearest to the player
	local cam = GetCameraTransform().pos
	local near, nd = nil, 30
	for i = 1, #cars do
		local c = cars[i]
		if IsHandleValid(c.body) and not c.broken then
			local d = dist(cabCenter(c), cam)
			if d < nd then near, nd = c, d end
		end
	end
	if near then
		local p = cabCenter(near)
		if near.state == "moving" then PlayLoop(snd.hum, p, 0.55) end
		PlayLoop(snd.muzak, p, 0.28)
	end
end

-- a cab that lost more than 12% of its voxels (or its handle) is wrecked: it is released and falls
local function checkBroken(c, dt)
	if c.broken then return end
	c.checkTimer = c.checkTimer - dt
	if c.checkTimer > 0 then return end
	c.checkTimer = 0.25
	if not IsHandleValid(c.body) then c.broken = true return end
	local shapes = GetBodyShapes(c.body)
	local count = 0
	for j = 1, #shapes do count = count + GetShapeVoxelCount(shapes[j]) end
	if count < c.vox0 * 0.88 then
		c.broken = true
	end
end

local function elevUpdate(dt)
	for i = 1, #cars do
		local c = cars[i]
		checkBroken(c, dt)
		supportCheck(c, dt)
		if not c.broken then
		local door = c.doors[c.floor]
		if c.state == "idle" then
			if c.target ~= c.floor then
				setState(c, "closing")
			elseif door and door.amount > 0 then
				c.hold = c.hold - dt
				if c.hold <= 0 then setState(c, "autoclose") end
			end
		elseif c.state == "closing" or c.state == "autoclose" then
			if door and door.amount > 0 then
				setDoor(door, math.max(0, door.amount - dt * DOOR_RATE))
			else
				c.state = (c.target ~= c.floor) and "moving" or "idle"
			end
		elseif c.state == "moving" then
			local goal = c.base + floorOff(c.target)
			local step = CAB_SPEED * dt
			if math.abs(goal - c.y) <= step then
				c.y = goal
				c.floor = c.target
				setState(c, "opening")
			else
				c.y = c.y + (goal > c.y and step or -step)
			end
		elseif c.state == "opening" then
			if door and door.amount < 1 then
				setDoor(door, math.min(1, door.amount + dt * DOOR_RATE))
			else
				c.state = "idle"
				c.hold = HOLD_TIME
			end
		end
		if IsHandleValid(c.body) then
			local t = GetBodyTransform(c.body)
			ConstrainPosition(c.body, 0, t.pos, Vec(c.x, c.y, c.z), 4)
			ConstrainOrientation(c.body, 0, t.rot, c.rot)
		end
		end -- not broken
	end
end

----------------------------------------------------------------------------------------------------
-- lamps: every lamp is its own small shape carrying its light, so the engine switches a light off
-- exactly when its lamp is shot. We only need to know which lights are broken (for the flicker).
----------------------------------------------------------------------------------------------------
local function lightBroken(l)
	if GetLightShape and IsShapeBroken then
		local sh = GetLightShape(l)
		if sh and sh ~= 0 and IsShapeBroken(sh) then return true end
	end
	return false
end

----------------------------------------------------------------------------------------------------
-- flickering corridor lights
----------------------------------------------------------------------------------------------------
local flick = {}

local function flickerInit()
	local lights = FindLights("flicker", true)
	for i = 1, #lights do
		flick[#flick + 1] = { light = lights[i], timer = math.random() * 4, on = true }
	end
end

local function flickerTick(dt, cam)
	local nearest, nd = nil, 8
	for i = 1, #flick do
		local f = flick[i]
		local dead = lightBroken(f.light)
		if dead then f.on = false end
		f.timer = f.timer - dt
		if f.timer <= 0 then
			if f.on then
				f.on = false
				f.timer = 0.03 + math.random() * 0.12                -- short drop-out
			else
				f.on = true
				f.timer = (math.random() < 0.35) and (0.05 + math.random() * 0.1) or (1.5 + math.random() * 5)
			end
			if not dead then SetLightEnabled(f.light, f.on) end
		end
		local p = GetLightTransform(f.light).pos
		local d = dist(p, cam)
		if d < nd then nearest, nd = f, d end
	end
	if nearest then
		PlayLoop(snd.buzz, GetLightTransform(nearest.light).pos, nearest.on and 0.12 or 0.04)
	end
end

----------------------------------------------------------------------------------------------------
-- positional ambience (pool hall, spa)
----------------------------------------------------------------------------------------------------
local spots = {}

local function spotsInit()
	local locs = FindLocations("ambsound", true)
	for i = 1, #locs do
		spots[#spots + 1] = { pos = GetLocationTransform(locs[i]).pos, kind = GetTagValue(locs[i], "kind") }
	end
end

-- poolside radio: plays the song while it is intact; shoot / smash it and the music stops
local radio = 0
local radioDead = false

local function radioTick(cam)
	if radioDead then return end
	if radio == 0 then radio = FindShape("radio", true) end
	if radio == 0 or not IsHandleValid(radio) or IsShapeBroken(radio) then
		if radio ~= 0 then radioDead = true end
		return
	end
	local p = GetShapeWorldTransform(radio).pos
	if dist(p, cam) < 60 then
		PlayLoop(snd.song, p, 0.9)
	end
end

local function spotsTick(cam)
	-- arcade music: the nearest speaker, only while the player is down in B1
	local near, nd = nil, 45
	for i = 1, #spots do
		local sp = spots[i]
		if sp.kind == "mall" and cam[2] < sp.pos[2] + 2.2 then
			local d = dist(sp.pos, cam)
			if d < nd then near, nd = sp, d end
		end
	end
	if near then PlayLoop(snd.mall, near.pos, 0.8) end
	-- car park: dripping water + ventilation hum from the nearest spot (also only down in B1)
	near, nd = nil, 40
	for i = 1, #spots do
		local sp = spots[i]
		if sp.kind == "garage" and cam[2] < sp.pos[2] + 2.2 then
			local d = dist(sp.pos, cam)
			if d < nd then near, nd = sp, d end
		end
	end
	if near then PlayLoop(snd.garage, near.pos, 0.55) end
	for i = 1, #spots do
		local sp = spots[i]
		local d = dist(sp.pos, cam)
		if sp.kind == "pool" and d < 45 then
			PlayLoop(snd.pool, sp.pos, 0.45)
		elseif sp.kind == "spa" and d < 18 then
			PlayLoop(snd.spa, sp.pos, 0.5)
		end
	end
end

----------------------------------------------------------------------------------------------------
-- hotel rooms: E on the light switch by the door turns the room's lights on / off,
-- E on the TV screen turns the TV on / off.
--  lights tagged room=<id> rl=ceil|lamp|bath|tv, "roomswitch" shapes (room on tv), lit curtains (room)
----------------------------------------------------------------------------------------------------
local rooms = {}
local roomBySwitch, roomByScreen = {}, {}

local function roomOf(id)
	local r = rooms[id]
	if not r then
		r = { lights = {}, tv = {}, screens = {}, curtains = {}, on = false, tvOn = false }
		rooms[id] = r
	end
	return r
end

local function setLamp(l, on)
	if on and lightBroken(l) then return end          -- a shot lamp stays dead
	SetLightEnabled(l, on)
	local sh = GetLightShape and GetLightShape(l) or 0
	if sh ~= 0 and IsHandleValid(sh) and SetShapeEmissiveScale then SetShapeEmissiveScale(sh, on and 1 or 0) end
end

local function roomApply(r)
	for i = 1, #r.lights do setLamp(r.lights[i], r.on) end
	for i = 1, #r.tv do setLamp(r.tv[i], r.tvOn) end
	for i = 1, #r.curtains do
		local sh = r.curtains[i]
		if IsHandleValid(sh) and SetShapeEmissiveScale then SetShapeEmissiveScale(sh, r.on and 1 or 0) end
	end
	if r.switch and IsHandleValid(r.switch) then
		SetTag(r.switch, "interact", r.on and "Lights off" or "Lights on")
	end
	for i = 1, #r.screens do
		if IsHandleValid(r.screens[i]) then SetTag(r.screens[i], "interact", r.tvOn and "Turn TV off" or "Turn TV on") end
	end
end

local function roomsInit()
	local ls = FindLights("room", true)
	for i = 1, #ls do
		local l = ls[i]
		local r = roomOf(GetTagValue(l, "room"))
		if GetTagValue(l, "rl") == "tv" then
			r.tv[#r.tv + 1] = l
			local sh = GetLightShape and GetLightShape(l) or 0
			if sh ~= 0 then
				r.screens[#r.screens + 1] = sh
				roomByScreen[sh] = r
			end
		else
			r.lights[#r.lights + 1] = l
		end
	end
	local sw = FindShapes("roomswitch", true)
	for i = 1, #sw do
		local r = roomOf(GetTagValue(sw[i], "room"))
		r.switch = sw[i]
		r.on = GetTagValue(sw[i], "on") == "1"
		r.tvOn = GetTagValue(sw[i], "tv") == "1"
		roomBySwitch[sw[i]] = r
	end
	local cb = FindBodies("curtain", true)
	for i = 1, #cb do
		if HasTag(cb[i], "room") then
			local r = roomOf(GetTagValue(cb[i], "room"))
			local shapes = GetBodyShapes(cb[i])
			for j = 1, #shapes do r.curtains[#r.curtains + 1] = shapes[j] end
		end
	end
	for _, r in pairs(rooms) do roomApply(r) end
end

-- returns true when the pressed shape was a room switch or a TV
local function roomsInteract(s)
	local r = roomBySwitch[s]
	if r then
		if not IsShapeBroken(s) then
			r.on = not r.on
			roomApply(r)
			PlaySound(snd.click, GetShapeWorldTransform(s).pos, 0.7)
		end
		return true
	end
	r = roomByScreen[s]
	if r then
		r.tvOn = not r.tvOn
		roomApply(r)
		PlaySound(snd.click, GetShapeWorldTransform(s).pos, 0.5)
		return true
	end
	return false
end

----------------------------------------------------------------------------------------------------
-- automatic sliding doors (B1: car park <-> arcade). Open when someone walks up, close after.
--  "autodoor" bodies   tags: grp sx sz (slide offset of the leaf when open)
----------------------------------------------------------------------------------------------------
local autoGroups = {}

local function autoInit()
	local bodies = FindBodies("autodoor", true)
	for i = 1, #bodies do
		local b = bodies[i]
		local grp = GetTagValue(b, "grp")
		local g = autoGroups[grp]
		if not g then
			g = { leaves = {}, amount = 0, target = 0, hold = 0 }
			autoGroups[grp] = g
		end
		g.leaves[#g.leaves + 1] = { body = b, t0 = GetBodyTransform(b), shapes = GetBodyShapes(b),
			slide = Vec(tagNum(b, "sx", 0), 0, tagNum(b, "sz", 0)) }
	end
	for _, g in pairs(autoGroups) do
		local c = Vec(0, 0, 0)
		for i = 1, #g.leaves do c = VecAdd(c, g.leaves[i].t0.pos) end
		g.center = VecScale(c, 1 / #g.leaves)
	end
end

local function autoTick(dt)
	local pp = GetPlayerTransform().pos
	for _, g in pairs(autoGroups) do
		local dx, dz = pp[1] - g.center[1], pp[3] - g.center[3]
		local near = math.sqrt(dx * dx + dz * dz) < 3.2 and math.abs(pp[2] - g.center[2]) < 2.5
		if near then g.hold = 1.2 else g.hold = g.hold - dt end
		local want = g.hold > 0 and 1 or 0
		if want ~= g.target then
			g.target = want
			PlaySound(snd.autodoor, VecAdd(g.center, Vec(0, 1.2, 0)), 0.6)
		end
		if g.amount ~= g.target then
			if g.amount < g.target then g.amount = math.min(1, g.amount + dt * 1.8)
			else g.amount = math.max(0, g.amount - dt * 1.4) end
			local e = g.amount * g.amount * (3 - 2 * g.amount)
			for i = 1, #g.leaves do
				local l = g.leaves[i]
				local ok = IsHandleValid(l.body)
				for j = 1, #l.shapes do
					if not IsHandleValid(l.shapes[j]) or IsShapeBroken(l.shapes[j]) then ok = false end
				end
				if ok then     -- a smashed glass leaf stays where it is
					SetBodyTransform(l.body, Transform(VecAdd(l.t0.pos, VecScale(l.slide, e)), l.t0.rot))
				end
			end
		end
	end
end

----------------------------------------------------------------------------------------------------
-- curtains: two panels per window, E on either panel opens / closes both
--  "curtain" bodies   tags: cid sx sz (slide offset when open) startopen
----------------------------------------------------------------------------------------------------
local curtainGroups = {}
local curtainByShape = {}

local function curtainLabel(g)
	return g.target > 0.5 and "Close curtains" or "Open curtains"
end

local function curtainsInit()
	local bodies = FindBodies("curtain", true)
	for i = 1, #bodies do
		local b = bodies[i]
		local cid = GetTagValue(b, "cid")
		local g = curtainGroups[cid]
		if not g then
			g = { panels = {}, amount = 0, target = 0 }
			if HasTag(b, "startopen") then g.amount, g.target = 1, 1 end
			curtainGroups[cid] = g
		end
		local p = { body = b, t0 = GetBodyTransform(b), slide = Vec(tagNum(b, "sx", 0), 0, tagNum(b, "sz", 0)) }
		p.shapes = GetBodyShapes(b)
		g.panels[#g.panels + 1] = p
		for j = 1, #p.shapes do curtainByShape[p.shapes[j]] = g end
	end
	for _, g in pairs(curtainGroups) do
		for i = 1, #g.panels do
			local p = g.panels[i]
			SetBodyTransform(p.body, Transform(VecAdd(p.t0.pos, VecScale(p.slide, g.amount)), p.t0.rot))
			for j = 1, #p.shapes do SetTag(p.shapes[j], "interact", curtainLabel(g)) end
		end
	end
end

local function panelBroken(p)
	if not IsHandleValid(p.body) then return true end
	for j = 1, #p.shapes do
		if not IsHandleValid(p.shapes[j]) or IsShapeBroken(p.shapes[j]) then return true end
	end
	return false
end

-- returns true when the pressed shape was a curtain
local function curtainsInteract(s)
	local g = curtainByShape[s]
	if not g then return false end
	g.target = 1 - g.target
	g.moving = true
	local p0 = g.panels[1]
	PlaySound(snd.curtain, GetBodyTransform(p0.body).pos, 0.7)
	for i = 1, #g.panels do
		for j = 1, #g.panels[i].shapes do
			if IsHandleValid(g.panels[i].shapes[j]) then SetTag(g.panels[i].shapes[j], "interact", curtainLabel(g)) end
		end
	end
	return true
end

local function curtainsTick(dt)
	for _, g in pairs(curtainGroups) do
		if g.moving then
			local step = dt * 1.6
			if g.amount < g.target then g.amount = math.min(g.target, g.amount + step)
			else g.amount = math.max(g.target, g.amount - step) end
			if g.amount == g.target then g.moving = false end
			local e = g.amount * g.amount * (3 - 2 * g.amount)          -- ease in / out
			for i = 1, #g.panels do
				local p = g.panels[i]
				if not panelBroken(p) then    -- a shot-up panel stays where it is
					SetBodyTransform(p.body, Transform(VecAdd(p.t0.pos, VecScale(p.slide, e)), p.t0.rot))
				end
			end
		end
	end
end

----------------------------------------------------------------------------------------------------
-- mission "SWEET DREAMS" (dreamcore, nothing scary)
--  ring the front-desk bell -> six lost memories appear, one on a room desk on every floor.
--  the pastel dreamers in the corridors slowly walk to the door of their floor's memory and look at it.
--  each dreamer says one soft line when you pass. bring all six back, ring again, and wake up.
--  "deskbell" body, "keycard" bodies (floor=), "mannequin" bodies (seg= fx= fz=), "missionstart" location
----------------------------------------------------------------------------------------------------
local M = { state = "idle", keys = 0, t = 0, msg = nil, msgT = 0, dream = 0, found = {} }
LIMINAL_MISSION = M          -- (read by the offline tests)
local bell = { shapes = {} }
local cards = {}
local mqs = {}               -- guiding dreamers (corridors)
local decor = {}             -- standing dreamers (rooms, lobby, pool)
local startT = nil
local HIDE = Vec(0, -500, 0)
local GLIDE = 0.7            -- m/s, a slow sleepwalk
local TURN = 90              -- deg/s

local MEMORY_LINES = {
	"a red carpet that went on forever",
	"a soda from the vending machine at 3 a.m.",
	"a phone call you always meant to make",
	"a door you dreamed about as a child",
	"a pink sky in the hallway mirror",
	"cartoons on an old TV, late at night",
}
local DREAMER_LINES = {
	"have we met before?", "it's always 3 a.m. here, and that's okay", "the pool is warm tonight",
	"you used to love this hallway", "nothing bad happens here", "your room is just as you left it",
	"listen... the elevator music", "it's okay to rest a little", "the carpet remembers your footsteps",
	"someone left the lights on for you", "you're almost awake", "this place missed you",
}

local function say(text, sec)
	M.msg, M.msgT = text, sec or 5
end

local function segNums(s)
	local out = {}
	for v in string.gmatch(s or "", "[^,]+") do out[#out + 1] = tonumber(v) end
	return out
end

local function heading(x, z)
	return math.deg(math.atan2(x, z))
end

local function angleTo(cur, want, maxStep)
	local d = (want - cur + 180) % 360 - 180
	if math.abs(d) <= maxStep then return want end
	return cur + (d > 0 and maxStep or -maxStep)
end

local function cardsHide()
	for i = 1, #cards do
		local c = cards[i]
		c.taken = false
		if IsHandleValid(c.body) then
			SetBodyTransform(c.body, Transform(VecAdd(c.t0.pos, HIDE), c.t0.rot))
			for j = 1, #c.shapes do
				if IsHandleValid(c.shapes[j]) then RemoveTag(c.shapes[j], "interact") end
			end
		end
	end
end

local function cardsShow()
	for i = 1, #cards do
		local c = cards[i]
		c.taken = false
		if IsHandleValid(c.body) then
			SetBodyTransform(c.body, c.t0)
			for j = 1, #c.shapes do
				if IsHandleValid(c.shapes[j]) then SetTag(c.shapes[j], "interact", "Take memory") end
			end
		end
	end
end

local function damaged(m)
	if not IsHandleValid(m.body) then return true end
	local count = 0
	for j = 1, #m.shapes do
		if not IsHandleValid(m.shapes[j]) or IsShapeBroken(m.shapes[j]) then return true end
		count = count + GetShapeVoxelCount(m.shapes[j])
	end
	return count < m.voxels * 0.92
end

local function eachDreamer(fn)
	for i = 1, #mqs do fn(mqs[i]) end
	for i = 1, #decor do fn(decor[i]) end
end

-- dreamers exist only while dreaming: outside the mission they are parked far below the map
local function dreamersHide()
	eachDreamer(function(m)
		m.hidden = true
		if IsHandleValid(m.body) then
			SetBodyDynamic(m.body, false)
			SetBodyVelocity(m.body, Vec(0, 0, 0))
			SetBodyAngularVelocity(m.body, Vec(0, 0, 0))
			SetBodyTransform(m.body, Transform(VecAdd(m.t0.pos, HIDE), m.t0.rot))
		end
	end)
end

local function dreamersShow()
	eachDreamer(function(m)
		m.spoke = false
		m.rotY = 0
		m.pos = VecCopy(m.t0.pos)
		if damaged(m) then              -- one that was shot to pieces does not come back
			m.dead = true
			return
		end
		m.dead = false
		m.hidden = false
		SetBodyTransform(m.body, m.t0)
	end)
end

local function missionInit()
	local bb = FindBody("deskbell", true)
	if bb ~= 0 then
		bell.body = bb
		bell.shapes = GetBodyShapes(bb)
		for j = 1, #bell.shapes do SetTag(bell.shapes[j], "interact", "Ring the bell") end
	end
	local loc = FindLocation("missionstart", true)
	if loc ~= 0 then startT = GetLocationTransform(loc) end
	local cb = FindBodies("keycard", true)
	for i = 1, #cb do
		cards[#cards + 1] = { body = cb[i], t0 = GetBodyTransform(cb[i]), shapes = GetBodyShapes(cb[i]),
			floor = tagNum(cb[i], "floor", i) }
	end
	cardsHide()
	local mb = FindBodies("mannequin", true)
	for i = 1, #mb do
		local b = mb[i]
		local s = segNums(GetTagValue(b, "seg"))
		local shapes = GetBodyShapes(b)
		local count = 0
		for j = 1, #shapes do count = count + GetShapeVoxelCount(shapes[j]) end
		local t0 = GetBodyTransform(b)
		mqs[#mqs + 1] = { body = b, shapes = shapes, voxels = count, t0 = t0, pos = VecCopy(t0.pos), rotY = 0,
			a = Vec(s[1] or t0.pos[1], t0.pos[2], s[2] or t0.pos[3]), b = Vec(s[3] or t0.pos[1], t0.pos[2], s[4] or t0.pos[3]),
			h0 = heading(tagNum(b, "fx", 0), tagNum(b, "fz", -1)), line = DREAMER_LINES[(i - 1) % #DREAMER_LINES + 1] }
	end
	local db = FindBodies("dreamdecor", true)
	for i = 1, #db do
		local shapes = GetBodyShapes(db[i])
		local count = 0
		for j = 1, #shapes do count = count + GetShapeVoxelCount(shapes[j]) end
		local t0 = GetBodyTransform(db[i])
		decor[#decor + 1] = { body = db[i], shapes = shapes, voxels = count, t0 = t0, pos = VecCopy(t0.pos), rotY = 0, still = true }
	end
	dreamersHide()
end

local function closestOnSeg(a, b, p)
	local ab = VecSub(b, a)
	local l2 = VecDot(ab, ab)
	local t = 0
	if l2 > 0 then t = VecDot(VecSub(Vec(p[1], a[2], p[3]), a), ab) / l2 end
	t = math.max(0, math.min(1, t))
	return VecAdd(a, VecScale(ab, t))
end

-- pastel dream look: softer colours, more bloom; eased in and out
local function setDreamLook(k)
	if not SetPostProcessingProperty then return end
	local function lerp(a, b) return a + (b - a) * k end
	pcall(SetPostProcessingProperty, "saturation", lerp(0.92, 0.78))
	pcall(SetPostProcessingProperty, "colorbalance", lerp(1.0, 1.08), lerp(0.94, 0.97), lerp(1.1, 1.16))
	pcall(SetPostProcessingProperty, "brightness", lerp(1.05, 1.14))
	pcall(SetPostProcessingProperty, "bloom", lerp(1.3, 2.4))
end

local function missionStart()
	M.state = "active"
	M.keys = 0
	M.found = {}
	M.woke = false
	cardsShow()
	dreamersShow()
	say("SWEET DREAMS\nYou left six memories in this hotel, one on every floor.\nThe dreamers in the hallways will show you the way.\nBring them back and ring the bell.", 9)
end

-- stop the mission at any time (M key or the pause menu): everything quietly goes away
local function missionStop()
	if M.state ~= "active" then return end
	M.state = "idle"
	M.keys = 0
	M.found = {}
	cardsHide()
	dreamersHide()
	PlaySound(snd.hum, GetCameraTransform().pos, 0.5)
	say("You woke up early.\nRing the bell to dream again.", 5)
end

local function missionInteract(s)
	for j = 1, #bell.shapes do
		if s == bell.shapes[j] then
			PlaySound(snd.deskbell, GetShapeWorldTransform(s).pos, 1.0)
			if M.state == "idle" or M.state == "won" then
				missionStart()
			elseif M.state == "active" then
				if M.keys >= #cards then
					M.state = "won"
					M.woke = false
					M.t = 0
					PlaySound(snd.checkout, GetCameraTransform().pos, 0.9)
					say("GOOD MORNING\nYou can wake up now. Sweet dreams.", 10)
				else
					local n = #cards - M.keys
					say(n .. " memor" .. (n == 1 and "y is" or "ies are") .. " still waiting for you.\nThe dreamers will show you the way.  (M: wake up early)", 4)
				end
			end
			return true
		end
	end
	if M.state ~= "active" then return false end
	for i = 1, #cards do
		local c = cards[i]
		for j = 1, #c.shapes do
			if s == c.shapes[j] and not c.taken then
				c.taken = true
				M.keys = M.keys + 1
				M.found[c.floor] = true
				PlaySound(snd.musicbox, GetShapeWorldTransform(s).pos, 0.9)
				SetBodyTransform(c.body, Transform(VecAdd(c.t0.pos, HIDE), c.t0.rot))
				for k = 1, #c.shapes do
					if IsHandleValid(c.shapes[k]) then RemoveTag(c.shapes[k], "interact") end
				end
				local line = MEMORY_LINES[c.floor] or "a memory"
				if M.keys >= #cards then
					say("memory " .. M.keys .. " / " .. #cards .. "  -  " .. line .. "\nThat's all of them. Ring the bell at the front desk.", 7)
				else
					say("memory " .. M.keys .. " / " .. #cards .. "  -  " .. line, 4)
				end
				return true
			end
		end
	end
	return false
end

local function dreamersTick(dt)
	local pt = GetPlayerTransform().pos
	for i = 1, #mqs do
		local m = mqs[i]
		if not m.dead then
			-- this floor's memory, while it is still lying there
			local target = nil
			for k = 1, #cards do
				local c = cards[k]
				if not c.taken and math.abs(c.t0.pos[2] - m.pos[2]) < 2.0 then target = c.t0.pos end
			end
			local flatP = Vec(pt[1] - m.pos[1], 0, pt[3] - m.pos[3])
			local near = math.abs(pt[2] - m.pos[2]) < 1.6 and VecLength(flatP) < 2.5
			local wantH = m.h0
			if target then
				local goal = closestOnSeg(m.a, m.b, target)
				local to = VecSub(goal, m.pos)
				local d = VecLength(to)
				if d > 0.05 and not (near and VecLength(flatP) < 1.4) then     -- never walks into you
					m.pos = VecAdd(m.pos, VecScale(to, math.min(d, GLIDE * dt) / d))
					wantH = heading(to[1], to[3])
				else
					wantH = heading(target[1] - m.pos[1], target[3] - m.pos[3])
				end
			end
			m.rotY = angleTo(m.rotY, wantH - m.h0, TURN * dt)
			SetBodyTransform(m.body, Transform(m.pos, QuatEuler(0, m.rotY, 0)))
			if near and not m.spoke then
				m.spoke = true
				PlaySound(snd.hum, m.pos, 0.6)
				say("\"" .. m.line .. "\"", 4)
			end
		end
	end
end

local function missionTick(dt)
	if M.msgT > 0 then M.msgT = M.msgT - dt end
	-- a shot-up dreamer just falls over (sandbox)
	eachDreamer(function(m)
		if not m.dead and not m.hidden and damaged(m) then
			m.dead = true
			if IsHandleValid(m.body) and not IsBodyDynamic(m.body) then SetBodyDynamic(m.body, true) end
		end
	end)
	if M.state == "active" and (InputPressed("m") or (PauseMenuButton and PauseMenuButton("Stop Sweet Dreams"))) then
		missionStop()
	end
	local want = (M.state == "active") and 1 or 0
	if M.dream ~= want then
		M.dream = want > M.dream and math.min(1, M.dream + dt / 2.5) or math.max(0, M.dream - dt / 4)
		setDreamLook(M.dream)
	end
	if M.dream > 0 then PlayLoop(snd.pad, GetCameraTransform().pos, 0.4 * M.dream) end
	if M.state == "active" then
		dreamersTick(dt)
	elseif M.state == "won" then
		M.t = M.t + dt
		if M.t > 1.5 and not M.woke then       -- they fade away with the morning light
			M.woke = true
			dreamersHide()
		end
	end
end

local function drawMission()
	UiPush()
	if M.state == "won" and M.t < 6 then
		local a = M.t < 1.5 and (M.t / 1.5) * 0.8 or math.max(0, 0.8 * (1 - (M.t - 1.5) / 4.5))
		UiColor(1, 0.96, 0.99, a)                   -- soft morning light
		UiRect(UiWidth(), UiHeight())
	end
	if M.state == "active" then
		UiPush()
			UiAlign("center top")
			UiTranslate(UiCenter(), 18)
			UiColor(1, 0.92, 0.97, 0.35)
			UiRect(420, 86)
			UiTranslate(0, 8)
			UiFont("bold.ttf", 24)
			UiColor(0.95, 0.5, 0.78, 1)
			UiText("MEMORIES  " .. M.keys .. " / " .. #cards)
			UiTranslate(0, 30)
			UiFont("regular.ttf", 18)
			local left = {}
			for i = 1, #cards do
				if not cards[i].taken then left[#left + 1] = tostring(cards[i].floor) end
			end
			UiColor(0.55, 0.5, 0.85, 1)
			if #left > 0 then
				UiText("floors: " .. table.concat(left, "  ") .. "   -  follow the dreamers")
				UiTranslate(0, 22)
				UiFont("regular.ttf", 15)
				UiColor(0.55, 0.5, 0.85, 0.75)
				UiText("M: wake up (stop)")
			else
				UiText("ring the bell at the front desk")
			end
		UiPop()
	end
	if M.msg and M.msgT > 0 then
		UiPush()
			UiAlign("center middle")
			UiTranslate(UiCenter(), UiHeight() * 0.72)
			UiFont("regular.ttf", 26)
			UiColor(1, 0.9, 0.97, math.min(1, M.msgT))
			if UiTextShadow then UiTextShadow(0.45, 0.3, 0.6, 0.6, 2) end
			UiText(M.msg)
		UiPop()
	end
	UiPop()
end

----------------------------------------------------------------------------------------------------
-- the map's own spawn menu (N key, or "Liminal Spawn" in the pause menu)
----------------------------------------------------------------------------------------------------
local SPAWN_ITEMS = {
	{ "Car (blue)", "car_a" }, { "Car (silver)", "car_b" }, { "Car (red)", "car_c" },
	{ "Luggage cart", "luggage_cart" }, { "Beach ball", "beach_ball" }, { "Swim ring", "swim_ring" },
	{ "Kickboard", "kickboard" }, { "Wooden crate", "crate" }, { "Red barrel", "barrel" },
	{ "Lobby sofa", "sofa" }, { "Old TV", "crt_tv" },
}
local menuOpen = false

local function spawnItem(id)
	local ct = GetCameraTransform()
	local fwd = TransformToParentVec(ct, Vec(0, 0, -1))
	local pos = VecAdd(ct.pos, VecScale(fwd, 4))
	pos[2] = pos[2] + 0.5
	local yaw = math.deg(math.atan2(-fwd[1], -fwd[3]))
	Spawn("MOD/prefab/" .. id .. ".xml", Transform(pos, QuatEuler(0, yaw, 0)))
	PlaySound(snd.click, ct.pos, 0.6)
end

local function spawnMenuTick()
	if PauseMenuButton and PauseMenuButton("Liminal Spawn") then menuOpen = true end
	if InputPressed("n") then menuOpen = not menuOpen end
	if menuOpen and InputPressed("esc") then menuOpen = false end
end

local function drawAmmoDebug()
	local id = currentTool() or "?"
	local lines = { "LIMINAL AMMO DEBUG (K)", "tool: " .. tostring(id),
		"SetToolAmmo: " .. tostring(SetToolAmmo ~= nil) .. "   GetToolAmmo: " .. tostring(GetToolAmmo ~= nil) ..
		"   GetPlayerTool: " .. tostring(GetPlayerTool ~= nil) }
	if GetToolAmmo then
		for _, args in ipairs({ { id }, { id, 0 }, { id, 1 } }) do
			local ok, v = pcall(GetToolAmmo, unpack(args))
			lines[#lines + 1] = "GetToolAmmo(" .. (args[2] and tostring(args[2]) or "-") .. ") = " .. tostring(ok and v or "error")
		end
	end
	local key = "game.tool." .. id .. ".ammo"
	lines[#lines + 1] = key .. " = " .. (HasKey(key) and tostring(GetFloat(key)) or "(none)")
	lines[#lines + 1] = "level.unlimitedammo = " .. tostring(GetBool("level.unlimitedammo"))
	UiPush()
		UiTranslate(20, 20)
		UiColor(0, 0, 0, 0.6)
		UiRect(560, 24 * #lines + 16)
		UiTranslate(10, 26)
		UiFont("regular.ttf", 20)
		UiColor(1, 1, 0.6, 1)
		for i = 1, #lines do
			UiText(lines[i])
			UiTranslate(0, 24)
		end
	UiPop()
end

function draw()
	drawMission()
	if ammoDebug then drawAmmoDebug() end
	if not menuOpen then return end
	UiMakeInteractive()
	UiPush()
		local w, rowH = 360, 38
		local h = 80 + #SPAWN_ITEMS * rowH + 50
		UiTranslate(UiCenter() - w / 2, UiMiddle() - h / 2)
		UiColor(0.05, 0.04, 0.08, 0.85)
		UiRect(w, h)
		UiColor(1, 1, 1, 1)
		UiFont("bold.ttf", 26)
		UiTranslate(w / 2, 40)
		UiAlign("center middle")
		UiText("LIMINAL SPAWN")
		UiFont("regular.ttf", 22)
		UiTranslate(0, 40)
		for i = 1, #SPAWN_ITEMS do
			UiColor(0.85, 0.8, 1, 1)
			if UiTextButton(SPAWN_ITEMS[i][1], w - 40, rowH - 6) then
				spawnItem(SPAWN_ITEMS[i][2])
			end
			UiTranslate(0, rowH)
		end
		UiTranslate(0, 10)
		UiColor(1, 0.6, 0.6, 1)
		if UiTextButton("Close (N)", w - 40, rowH - 6) then menuOpen = false end
	UiPop()
end

----------------------------------------------------------------------------------------------------
-- callbacks
----------------------------------------------------------------------------------------------------
local toolTimer = 0
local ammoTimer = 0
ammoDebug = false
interactHandled = false

function init()
	SetBool("level.sandbox", true)          -- sandbox level (spawn menu etc.)
	SetBool("level.unlimitedammo", true)
	loadSounds()
	giveTools()
	doorsInit()
	elevInit()
	flickerInit()
	spotsInit()
	curtainsInit()
	roomsInit()
	autoInit()
	missionInit()
	say("Front desk: ring the bell when you are ready to dream.", 7)
end

function tick(dt)
	if toolTimer < 3 then
		toolTimer = toolTimer + dt
		giveTools()
	end
	ammoTimer = (ammoTimer or 0) - dt
	if ammoTimer <= 0 then
		ammoTimer = 0.5
		giveTools()
		topUpAmmo()
	end
	local held = currentTool()
	if held and held ~= "" and (AMMO_TOOLS[held] or HasKey("game.tool." .. held .. ".ammo")) then
		local a = readAmmo(held)
		if a == nil or a < 200 then setAmmo(held, 999) end
	end
	if InputPressed("k") then ammoDebug = not ammoDebug end
	interactHandled = false
	if InputPressed("interact") then
		local s = GetPlayerInteractShape()
		if s ~= 0 then
			interactHandled = curtainsInteract(s) or roomsInteract(s) or missionInteract(s)
		end
	end
	curtainsTick(dt)
	autoTick(dt)
	missionTick(dt)
	local cam = GetCameraTransform().pos
	PlayLoop(snd.ambience, cam, 0.3)
	doorsTick(cam)
	elevTick(dt)
	flickerTick(dt, cam)
	spotsTick(cam)
	radioTick(cam)
	spawnMenuTick()
end

function update(dt)
	elevUpdate(dt)
end
