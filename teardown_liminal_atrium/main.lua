-- Liminal Atrium - runs automatically when the map is played (mod-root main.lua).
-- 1) gives the player the base-game tools with plenty of ammo
-- 2) interactive doors (E)          3) working elevators (call / floor buttons, E)

local TOOLS = { "sledge", "spraycan", "extinguisher", "blowtorch", "shotgun", "plank", "pipebomb",
	"gun", "bomb", "wire", "rocket", "booster", "leafblower", "turbo", "explosive", "rifle", "steroid" }

local function giveTools()
	for i = 1, #TOOLS do
		SetBool("game.tool." .. TOOLS[i] .. ".enabled", true)
	end
end

local function topUpAmmo()
	for i = 1, #TOOLS do
		local key = "game.tool." .. TOOLS[i] .. ".ammo"
		if HasKey(key) and GetFloat(key) < 50 then
			SetFloat(key, 99)
		end
	end
end

-- ===================== doors =====================
-- Liminal Atrium: interactive doors.
-- Every body tagged "hoteldoor" becomes a door the player can open / close with
-- the interact key (E).  Swing doors rotate about a vertical axis through the
-- world point (px, pz) by `ang` degrees; sliding doors move by (sx, 0, sz).

local doorList = {}
local byBody = {}
local SPEED = 1.6          -- full open/close per second (fraction of the motion)

local function doorNum(body, tag, default)
	local v = tonumber(GetTagValue(body, tag))
	if v == nil then return default end
	return v
end

local function apply(d)
	local t = d.t0
	if d.kind == "slide" then
		SetBodyTransform(d.body, Transform(VecAdd(t.pos, VecScale(d.slide, d.amount)), t.rot))
	else
		local q = QuatEuler(0, d.ang * d.amount, 0)
		local rel = VecSub(t.pos, d.pivot)
		SetBodyTransform(d.body, Transform(VecAdd(d.pivot, QuatRotateVec(q, rel)), QuatRotateQuat(q, t.rot)))
	end
end

local function tagShapes(d)
	local shapes = GetBodyShapes(d.body)
	for j = 1, #shapes do
		SetTag(shapes[j], "interact", "Open / Close")
	end
end

local function doorsInit()
	local bodies = FindBodies("hoteldoor", true)
	for i = 1, #bodies do
		local b = bodies[i]
		local d = { body = b, t0 = GetBodyTransform(b), amount = 0, target = 0 }
		if HasTag(b, "slide") then
			d.kind = "slide"
			d.slide = Vec(doorNum(b, "sx", 0), 0, doorNum(b, "sz", 0))
		else
			d.kind = "swing"
			d.pivot = Vec(doorNum(b, "px", d.t0.pos[1]), d.t0.pos[2], doorNum(b, "pz", d.t0.pos[3]))
			d.ang = doorNum(b, "ang", 90)
		end
		if HasTag(b, "startopen") then
			d.amount = 1
			d.target = 1
			apply(d)
		end
		tagShapes(d)
		doorList[#doorList + 1] = d
		byBody[b] = d
	end
end

local function doorsTick(dt)
	if InputPressed("interact") then
		local s = GetPlayerInteractShape()
		if s ~= 0 then
			local d = byBody[GetShapeBody(s)]
			if d then
				d.target = 1 - d.target
				tagShapes(d)   -- pieces broken off keep working
			end
		end
	end
	for i = 1, #doorList do
		local d = doorList[i]
		if d.amount ~= d.target then
			if d.amount < d.target then
				d.amount = math.min(d.target, d.amount + dt * SPEED)
			else
				d.amount = math.max(d.target, d.amount - dt * SPEED)
			end
			apply(d)
		end
	end
end

-- ===================== elevators =====================
-- Liminal Atrium: working elevators.
--  * "elevcar"  bodies  : the cabs (dynamic). Tags: shaft=<id> floor=<start floor>
--  * "elevbtn"  shapes  : buttons inside a cab.  Tag: floor=<n>
--  * "elevcall" shapes  : call buttons on the landings. Tags: shaft=<id> floor=<n>
--  * "elevdoor" bodies  : landing doors (static, sliding). Tags: shaft floor sx sz
-- Press E on a button. The landing door closes, the cab travels, the door opens.

local FLOOR_H   = 3.0     -- metres between floors
local CAB_SPEED = 1.2     -- cab speed m/s
local DOOR_RATE = 1.0     -- door open/close per second
local HOLD_TIME = 6.0     -- door stays open this long when idle

local cars = {}
local carByShaft = {}
local carByBody = {}

local function elevTagNum(h, t, def)
	local v = tonumber(GetTagValue(h, t))
	if v == nil then return def end
	return v
end

local function setDoor(door, amount)
	door.amount = amount
	SetBodyTransform(door.body, Transform(VecAdd(door.t0.pos, VecScale(door.slide, amount)), door.t0.rot))
end

local function elevInit()
	local bodies = FindBodies("elevcar", true)
	for i = 1, #bodies do
		local b = bodies[i]
		local t = GetBodyTransform(b)
		local f = elevTagNum(b, "floor", 0)
		local c = {
			body = b, shaft = GetTagValue(b, "shaft"), floor = f, target = f,
			x = t.pos[1], z = t.pos[3], rot = t.rot, y = t.pos[2],
			base = t.pos[2] - f * FLOOR_H, state = "opening", hold = HOLD_TIME, doors = {},
		}
		cars[#cars + 1] = c
		carByShaft[c.shaft] = c
		carByBody[b] = c
	end
	local doors = FindBodies("elevdoor", true)
	for i = 1, #doors do
		local b = doors[i]
		local c = carByShaft[GetTagValue(b, "shaft")]
		if c then
			local d = { body = b, t0 = GetBodyTransform(b), amount = 0,
				slide = Vec(elevTagNum(b, "sx", 0), 0, elevTagNum(b, "sz", 0)) }
			c.doors[elevTagNum(b, "floor", 0)] = d
		end
	end
	local btns = FindShapes("elevbtn", true)
	for i = 1, #btns do
		SetTag(btns[i], "interact", "Floor " .. (elevTagNum(btns[i], "floor", 0) + 1))
	end
	local calls = FindShapes("elevcall", true)
	for i = 1, #calls do
		SetTag(calls[i], "interact", "Call elevator")
	end
end

local function request(c, floor)
	if c == nil or floor == nil then return end
	c.target = floor
	if (c.state == "idle" or c.state == "autoclose") and floor == c.floor then
		c.state = "opening"
	end
	c.hold = HOLD_TIME
end

local function elevTick(dt)
	if InputPressed("interact") then
		local s = GetPlayerInteractShape()
		if s ~= 0 then
			if HasTag(s, "elevbtn") then
				request(carByBody[GetShapeBody(s)], elevTagNum(s, "floor", nil))
			elseif HasTag(s, "elevcall") then
				request(carByShaft[GetTagValue(s, "shaft")], elevTagNum(s, "floor", nil))
			end
		end
	end
end

local function elevUpdate(dt)
	for i = 1, #cars do
		local c = cars[i]
		local door = c.doors[c.floor]
		if c.state == "idle" then
			if c.target ~= c.floor then
				c.state = "closing"
			elseif door and door.amount > 0 then
				c.hold = c.hold - dt
				if c.hold <= 0 then c.state = "autoclose" end
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
				c.state = "opening"
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
		-- drive the cab: hold it on its rail at the commanded height, keep it upright
		if IsHandleValid(c.body) then
			local t = GetBodyTransform(c.body)
			ConstrainPosition(c.body, 0, t.pos, Vec(c.x, c.y, c.z), 4)
			ConstrainOrientation(c.body, 0, t.rot, c.rot)
		end
	end
end


local toolTimer = 0

function init()
	giveTools()
	doorsInit()
	elevInit()
end

function tick(dt)
	-- re-apply tools for the first seconds (in case the game resets the inventory after init)
	if toolTimer < 3 then
		toolTimer = toolTimer + dt
		giveTools()
	end
	topUpAmmo()
	doorsTick(dt)
	elevTick(dt)
end

function update(dt)
	elevUpdate(dt)
end
