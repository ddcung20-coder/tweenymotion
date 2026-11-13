-- Liminal Atrium - runs automatically when the map is played (mod-root main.lua).
--  1) gives the player the base-game tools with plenty of ammo
--  2) working elevators (call buttons / floor buttons with E) with chime, motor hum, door and music sounds
--  3) building ambience, flickering corridor lights with fluorescent buzz
--  4) creak / thud sounds for the physical (grab-and-pull) doors

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
		for i = 1, #keys do ids[#ids + 1] = keys[i] end
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

local function topUpAmmo()
	-- refill every tool that uses ammo: registry (1.x and most tool mods) and SetToolAmmo (2.x, per player)
	local ids = allTools()
	for i = 1, #ids do
		local id = ids[i]
		local key = "game.tool." .. id .. ".ammo"
		local usesAmmo = AMMO_TOOLS[id] or HasKey(key)
		if usesAmmo then
			if HasKey(key) and GetFloat(key) < 50 then
				SetFloat(key, 999)
			end
			if SetToolAmmo then
				local cur = 0
				if GetToolAmmo then
					local ok, v = pcall(GetToolAmmo, id)
					if ok and type(v) == "number" then cur = v end
				end
				if cur < 50 then pcall(SetToolAmmo, id, 999) end
			end
		end
	end
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

local cars = {}
local carByShaft = {}
local carByBody = {}

local function tagNum(h, t, def)
	local v = tonumber(GetTagValue(h, t))
	if v == nil then return def end
	return v
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
			base = t.pos[2] - f * FLOOR_H, state = "opening", hold = HOLD_TIME, doors = {},
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
		SetTag(btns[i], "interact", "Floor " .. (tagNum(btns[i], "floor", 0) + 1))
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
		if s ~= 0 then
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
			local goal = c.base + c.target * FLOOR_H
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
	local nearest, nd = nil, 12
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
		PlayLoop(snd.buzz, GetLightTransform(nearest.light).pos, nearest.on and 0.35 or 0.12)
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

local function spotsTick(cam)
	for i = 1, #spots do
		local sp = spots[i]
		local d = dist(sp.pos, cam)
		if sp.kind == "pool" and d < 45 then
			PlayLoop(snd.pool, sp.pos, 0.7)
		elseif sp.kind == "spa" and d < 18 then
			PlayLoop(snd.spa, sp.pos, 0.5)
		end
	end
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

function draw()
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

function init()
	SetBool("level.sandbox", true)          -- sandbox level (spawn menu etc.)
	SetBool("level.unlimitedammo", true)
	loadSounds()
	giveTools()
	doorsInit()
	elevInit()
	flickerInit()
	spotsInit()
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
	local cam = GetCameraTransform().pos
	PlayLoop(snd.ambience, cam, 0.3)
	doorsTick(cam)
	elevTick(dt)
	flickerTick(dt, cam)
	spotsTick(cam)
	spawnMenuTick()
end

function update(dt)
	elevUpdate(dt)
end
