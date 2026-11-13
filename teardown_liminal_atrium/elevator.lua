-- Liminal Atrium: working elevators.
--  * "elevcar"  bodies  : the cabs (dynamic). Tags: shaft=<id> floor=<start floor>
--  * "elevbtn"  shapes  : buttons inside a cab.  Tag: floor=<n>
--  * "elevcall" shapes  : call buttons on the landings. Tags: shaft=<id> floor=<n>
--  * "elevdoor" bodies  : landing doors (static, sliding). Tags: shaft floor sx sz
-- Press E on a button. The landing door closes, the cab travels, the door opens.

local FLOOR_H   = 3.0     -- metres between floors
local SPEED     = 1.2     -- cab speed m/s
local DOOR_RATE = 1.0     -- door open/close per second
local HOLD_TIME = 6.0     -- door stays open this long when idle

local cars = {}
local carByShaft = {}
local carByBody = {}

local function tagNum(h, t, def)
	local v = tonumber(GetTagValue(h, t))
	if v == nil then return def end
	return v
end

local function setDoor(door, amount)
	door.amount = amount
	SetBodyTransform(door.body, Transform(VecAdd(door.t0.pos, VecScale(door.slide, amount)), door.t0.rot))
end

function init()
	local bodies = FindBodies("elevcar", true)
	for i = 1, #bodies do
		local b = bodies[i]
		local t = GetBodyTransform(b)
		local f = tagNum(b, "floor", 0)
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
				slide = Vec(tagNum(b, "sx", 0), 0, tagNum(b, "sz", 0)) }
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

local function request(c, floor)
	if c == nil or floor == nil then return end
	c.target = floor
	if (c.state == "idle" or c.state == "autoclose") and floor == c.floor then
		c.state = "opening"
	end
	c.hold = HOLD_TIME
end

function tick(dt)
	if InputPressed("interact") then
		local s = GetPlayerInteractShape()
		if s ~= 0 then
			if HasTag(s, "elevbtn") then
				request(carByBody[GetShapeBody(s)], tagNum(s, "floor", nil))
			elseif HasTag(s, "elevcall") then
				request(carByShaft[GetTagValue(s, "shaft")], tagNum(s, "floor", nil))
			end
		end
	end
end

function update(dt)
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
			local step = SPEED * dt
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
