-- Liminal Atrium: interactive doors.
-- Every body tagged "hoteldoor" becomes a door the player can open / close with
-- the interact key (E).  Swing doors rotate about a vertical axis through the
-- world point (px, pz) by `ang` degrees; sliding doors move by (sx, 0, sz).

local doors = {}
local byBody = {}
local SPEED = 1.6          -- full open/close per second (fraction of the motion)

local function num(body, tag, default)
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

function init()
	local bodies = FindBodies("hoteldoor", true)
	for i = 1, #bodies do
		local b = bodies[i]
		local d = { body = b, t0 = GetBodyTransform(b), amount = 0, target = 0 }
		if HasTag(b, "slide") then
			d.kind = "slide"
			d.slide = Vec(num(b, "sx", 0), 0, num(b, "sz", 0))
		else
			d.kind = "swing"
			d.pivot = Vec(num(b, "px", d.t0.pos[1]), d.t0.pos[2], num(b, "pz", d.t0.pos[3]))
			d.ang = num(b, "ang", 90)
		end
		if HasTag(b, "startopen") then
			d.amount = 1
			d.target = 1
			apply(d)
		end
		tagShapes(d)
		doors[#doors + 1] = d
		byBody[b] = d
	end
end

function tick(dt)
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
	for i = 1, #doors do
		local d = doors[i]
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
