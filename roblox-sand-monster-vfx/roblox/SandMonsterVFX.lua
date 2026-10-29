--[[
	SandMonsterVFX  (ModuleScript, z. B. in ReplicatedStorage)

	Sand-Golem-Effekt aus Blender (siehe ../blender/sand_monster_vfx.py) für Roblox.

	Bausteine, frei kombinierbar:
	  SandMonsterVFX.collapse(model, options)          -- alles zusammen, wie im Video
	  SandMonsterVFX.playFlipbook(position, options)   -- Blender-Render als Billboard (Flipbook 8x8)
	  SandMonsterVFX.disintegrate(model, options)      -- echtes 3D-Modell zerbröselt von oben nach unten
	  SandMonsterVFX.spawnPile(position, options)      -- Sandhaufen, der wächst (und optional verschwindet)

	Vorher die PNGs aus ../output in Roblox hochladen (Asset Manager oder Creator Hub)
	und die IDs unten in SandMonsterVFX.Assets eintragen.
]]

local Debris = game:GetService("Debris")
local TweenService = game:GetService("TweenService")

local SandMonsterVFX = {}

-- Asset-IDs der hochgeladenen Bilder ("rbxassetid://123456789")
SandMonsterVFX.Assets = {
	Collapse = "", -- SandMonster_Collapse_8x8.png  (Golem brüllt + zerfällt)
	Collapse4x4 = "", -- SandMonster_Collapse_4x4.png (16 Frames, dafür doppelte Auflösung)
	Rise = "", -- SandMonster_Rise_8x8.png      (Golem setzt sich aus Sand zusammen)
	Burst = "", -- SandBurst_8x8.png             (nur Sandexplosion, für echte 3D-Modelle)
	Grain = "", -- SandGrain.png
	Dust = "", -- SandDust.png
}

-- Werte aus output/vfx_meta.json (vom Blender-Skript erzeugt)
SandMonsterVFX.Meta = {
	duration = 4.267, -- 64 Frames bei 15 fps
	frameWorldSize = 3.9, -- Bildbreite eines Flipbook-Frames in Metern
	groundV = 0.2263, -- Höhe des Bodens im Frame (0 = unten, 1 = oben)
	golemHeight = 1.948, -- Golem-Höhe in Metern
	burstStart = 0.9, -- Burst-Sheet beginnt bei dieser Zeit des Collapse-Sheets
	frontStart = 0.967, -- Zerfall erreicht den Kopf ...
	frontEnd = 2.5, -- ... und die Füße (Sekunden im Collapse-Sheet)
	pileRadius = 1.3, -- Radius des gerenderten Sandhaufens in Metern
}

local STUDS_PER_METER = 1 / 0.28
local DEFAULT_GRAIN = "rbxasset://textures/particles/sparkles_main.dds"
local DEFAULT_DUST = "rbxasset://textures/particles/smoke_main.dds"

local SAND_LIGHT = Color3.fromRGB(196, 168, 136)
local SAND_DARK = Color3.fromRGB(122, 96, 72)
local SAND_DUST = Color3.fromRGB(184, 158, 128)
local SAND_PILE = Color3.fromRGB(205, 182, 150)

local function kp(t: number, v: number, e: number?)
	return NumberSequenceKeypoint.new(t, v, e or 0)
end

local function hasAsset(id: string?): boolean
	return id ~= nil and id ~= "" and id ~= "rbxassetid://0"
end

-- Maßstab: 1 = Golem so groß wie in Blender (ca. 7 Studs)
local function studScale(scale: number?): number
	return STUDS_PER_METER * (scale or 1)
end

local function invisibleAnchor(name: string, cframe: CFrame, parent: Instance?): (Part, Attachment)
	local part = Instance.new("Part")
	part.Name = name
	part.Anchored = true
	part.CanCollide = false
	part.CanQuery = false
	part.CanTouch = false
	part.CastShadow = false
	part.Transparency = 1
	part.Size = Vector3.new(0.2, 0.2, 0.2)
	part.CFrame = cframe
	local attachment = Instance.new("Attachment")
	attachment.Parent = part
	part.Parent = parent or workspace
	return part, attachment
end

--[[
	Spielt ein Blender-Flipbook als Billboard ab. position = Bodenpunkt (Füße des Golems).
	options:
	  sheet          "Collapse" | "Collapse4x4" | "Rise" | "Burst"   (Standard "Collapse")
	  scale          Größe relativ zum Blender-Golem (1 = ca. 7 Studs hoch)
	  lightInfluence 0..1, wie stark die Roblox-Beleuchtung das Bild abdunkelt (Standard 0.5)
	  parent         wohin das Hilfs-Part kommt (Standard workspace)
]]
function SandMonsterVFX.playFlipbook(position: Vector3, options: { [string]: any }?): Part?
	local opts = options or {}
	local sheet = opts.sheet or "Collapse"
	local texture = SandMonsterVFX.Assets[sheet]
	if not hasAsset(texture) then
		warn(`SandMonsterVFX: Asset-ID für "{sheet}" fehlt (SandMonsterVFX.Assets.{sheet})`)
		return nil
	end

	local meta = SandMonsterVFX.Meta
	local size = meta.frameWorldSize * studScale(opts.scale)
	-- Partikel sitzen mittig auf ihrer Position -> so weit anheben, dass der Boden im Bild auf position liegt
	local center = position + Vector3.new(0, (0.5 - meta.groundV) * size, 0)
	local part, attachment = invisibleAnchor("SandFlipbook", CFrame.new(center), opts.parent)

	local emitter = Instance.new("ParticleEmitter")
	emitter.Name = "SandFlipbook"
	emitter.Texture = texture
	emitter.FlipbookLayout = if string.find(sheet, "4x4") then Enum.ParticleFlipbookLayout.Grid4x4 else Enum.ParticleFlipbookLayout.Grid8x8
	emitter.FlipbookMode = Enum.ParticleFlipbookMode.OneShot
	emitter.Lifetime = NumberRange.new(meta.duration)
	emitter.Size = NumberSequence.new(size)
	emitter.Transparency = NumberSequence.new({ kp(0, 0), kp(0.96, 0), kp(1, 1) })
	emitter.Speed = NumberRange.new(0)
	emitter.Rotation = NumberRange.new(0)
	emitter.RotSpeed = NumberRange.new(0)
	emitter.Orientation = Enum.ParticleOrientation.FacingCamera
	emitter.LightInfluence = opts.lightInfluence or 0.5
	emitter.LightEmission = 0
	emitter.ZOffset = size * 0.2 -- etwas zur Kamera hin, damit der Boden den Haufen nicht abschneidet
	emitter.LockedToPart = true
	emitter.Rate = 0
	emitter.Enabled = false
	emitter.Parent = attachment

	emitter:Emit(1)
	Debris:AddItem(part, meta.duration + 0.5)
	return part
end

local function grainEmitter(s: number): ParticleEmitter
	local e = Instance.new("ParticleEmitter")
	e.Name = "SandGrains"
	e.Texture = if hasAsset(SandMonsterVFX.Assets.Grain) then SandMonsterVFX.Assets.Grain else DEFAULT_GRAIN
	e.Color = ColorSequence.new(SAND_LIGHT, SAND_DARK)
	e.Size = NumberSequence.new({ kp(0, 0.35 * s, 0.15 * s), kp(1, 0.2 * s, 0.1 * s) })
	e.Transparency = NumberSequence.new({ kp(0, 0), kp(0.75, 0), kp(1, 1) })
	e.Lifetime = NumberRange.new(0.8, 1.6)
	e.Speed = NumberRange.new(2 * s, 6 * s)
	e.SpreadAngle = Vector2.new(180, 180)
	e.Acceleration = Vector3.new(0, -30 * s, 0)
	e.Drag = 1.2
	e.Rotation = NumberRange.new(0, 360)
	e.RotSpeed = NumberRange.new(-120, 120)
	e.LightInfluence = 1
	e.Shape = Enum.ParticleEmitterShape.Box
	e.ShapeStyle = Enum.ParticleEmitterShapeStyle.Volume
	e.Rate = 0
	e.Enabled = false
	return e
end

local function dustEmitter(s: number): ParticleEmitter
	local e = Instance.new("ParticleEmitter")
	e.Name = "SandDust"
	e.Texture = if hasAsset(SandMonsterVFX.Assets.Dust) then SandMonsterVFX.Assets.Dust else DEFAULT_DUST
	e.Color = ColorSequence.new(SAND_DUST)
	e.Size = NumberSequence.new({ kp(0, 1.2 * s, 0.4 * s), kp(1, 4 * s, 1 * s) })
	e.Transparency = NumberSequence.new({ kp(0, 0.4), kp(0.6, 0.65), kp(1, 1) })
	e.Lifetime = NumberRange.new(1.5, 2.8)
	e.Speed = NumberRange.new(1 * s, 3 * s)
	e.SpreadAngle = Vector2.new(180, 180)
	e.Acceleration = Vector3.new(0, -1.5 * s, 0)
	e.Drag = 2
	e.Rotation = NumberRange.new(0, 360)
	e.RotSpeed = NumberRange.new(-40, 40)
	e.LightInfluence = 1
	e.Shape = Enum.ParticleEmitterShape.Box
	e.ShapeStyle = Enum.ParticleEmitterShapeStyle.Volume
	e.Rate = 0
	e.Enabled = false
	return e
end

local function crumblePart(part: BasePart, s: number, density: number)
	if not part.Parent then
		return
	end
	local volume = part.Size.X * part.Size.Y * part.Size.Z
	local grains = grainEmitter(s)
	local dust = dustEmitter(s)
	grains.Parent = part
	dust.Parent = part
	grains:Emit(math.floor(math.clamp(volume * 6 / s, 8, 120) * density))
	dust:Emit(math.floor(math.clamp(volume * 0.8 / s, 2, 20) * density))

	local info = TweenInfo.new(0.35, Enum.EasingStyle.Quad, Enum.EasingDirection.In)
	TweenService:Create(part, info, { Transparency = 1, Size = part.Size * 0.7 }):Play()
	for _, child in part:GetChildren() do
		if child:IsA("Decal") or child:IsA("Texture") then
			TweenService:Create(child, info, { Transparency = 1 }):Play()
		end
	end
	Debris:AddItem(grains, 4)
	Debris:AddItem(dust, 4)
end

--[[
	Lässt ein Modell (NPC, Charakter oder den importierten SandGolem) von oben nach unten zu Sand zerbröseln.
	options:
	  sweepTime   Sekunden, bis der Zerfall vom Kopf bei den Füßen ist (Standard 1.5)
	  delay       Wartezeit vor dem Start (Standard 0)
	  scale       Größe relativ zum Blender-Golem (steuert Partikelgröße/-tempo)
	  density     Partikelmenge (Standard 1)
	  destroy     Modell danach löschen (Standard true)
]]
function SandMonsterVFX.disintegrate(model: Instance, options: { [string]: any }?)
	local opts = options or {}
	local sweepTime = opts.sweepTime or 1.5
	local delay = opts.delay or 0
	local s = opts.scale or 1
	local density = opts.density or 1

	local parts: { BasePart } = {}
	for _, d in model:GetDescendants() do
		if d:IsA("BasePart") and d.Transparency < 1 then
			table.insert(parts, d)
		end
	end
	if #parts == 0 then
		return
	end

	local humanoid = model:FindFirstChildOfClass("Humanoid")
	if humanoid then
		humanoid.DisplayDistanceType = Enum.HumanoidDisplayDistanceType.None
	end

	local top, bottom = -math.huge, math.huge
	for _, p in parts do
		top = math.max(top, p.Position.Y)
		bottom = math.min(bottom, p.Position.Y)
	end
	local range = math.max(top - bottom, 0.001)

	-- Pose einfrieren, dann von oben nach unten zerbröseln
	for _, p in model:GetDescendants() do
		if p:IsA("BasePart") then
			p.Anchored = true
			p.CanCollide = false
		end
	end
	for _, p in parts do
		task.delay(delay + (top - p.Position.Y) / range * sweepTime, crumblePart, p, s, density)
	end

	if opts.destroy ~= false then
		task.delay(delay + sweepTime + 4, function()
			if model.Parent then
				model:Destroy()
			end
		end)
	end
end

--[[
	Flacher Sandhaufen aus zwei Sand-Scheiben, der wächst.
	options:
	  scale       Größe relativ zum Blender-Golem
	  radius      Radius in Studs (Standard: wie im Render)
	  growTime    Sekunden bis zur vollen Größe (Standard 1.5)
	  lifetime    nach so vielen Sekunden wieder ausblenden (Standard nil = bleibt liegen)
	  parent      Standard workspace
]]
function SandMonsterVFX.spawnPile(position: Vector3, options: { [string]: any }?): Model
	local opts = options or {}
	local studs = studScale(opts.scale)
	local radius = opts.radius or SandMonsterVFX.Meta.pileRadius * studs
	local growTime = opts.growTime or 1.5

	local pile = Instance.new("Model")
	pile.Name = "SandPile"
	local layers = {
		{ radius = radius, height = 0.06 * studs },
		{ radius = radius * 0.55, height = 0.14 * studs },
	}
	local info = TweenInfo.new(growTime, Enum.EasingStyle.Quart, Enum.EasingDirection.Out)
	for i, layer in layers do
		local disc = Instance.new("Part")
		disc.Name = "Layer" .. i
		disc.Shape = Enum.PartType.Cylinder
		disc.Material = Enum.Material.Sand
		disc.Color = SAND_PILE
		disc.Anchored = true
		disc.CanCollide = false
		disc.CanQuery = false
		disc.CanTouch = false
		disc.CastShadow = false
		-- Zylinder-Achse = X -> um Z drehen, damit die Scheibe flach liegt
		local function cframeFor(height: number): CFrame
			return CFrame.new(position + Vector3.new(0, height / 2, 0)) * CFrame.Angles(0, 0, math.rad(90))
		end
		local d = layer.radius * 2
		disc.Size = Vector3.new(0.05, d * 0.3, d * 0.3)
		disc.CFrame = cframeFor(0.05)
		disc.Parent = pile
		TweenService:Create(disc, info, {
			Size = Vector3.new(layer.height, d, d),
			CFrame = cframeFor(layer.height),
		}):Play()
	end
	pile.Parent = opts.parent or workspace

	if opts.lifetime then
		task.delay(opts.lifetime, function()
			local fade = TweenInfo.new(1.5)
			for _, disc in pile:GetChildren() do
				TweenService:Create(disc, fade, { Transparency = 1 }):Play()
			end
			Debris:AddItem(pile, 1.6)
		end)
	end
	return pile
end

local function groundBelow(model: Model): (Vector3, number)
	local cframe, size = model:GetBoundingBox()
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = { model }
	local result = workspace:Raycast(cframe.Position, Vector3.new(0, -(size.Y + 50), 0), params)
	local ground = if result then result.Position else cframe.Position - Vector3.new(0, size.Y / 2, 0)
	return ground, size.Y
end

--[[
	Der komplette Effekt wie im Video: das 3D-Modell zerbröselt, gleichzeitig läuft die
	Blender-Sandexplosion (Burst-Flipbook), danach bleibt ein Sandhaufen liegen.
	options:
	  flipbook       false = ohne Blender-Billboard (nur Roblox-Partikel)
	  pileLifetime   Sekunden, bis der Haufen verschwindet (Standard 8, nil-Wert über false = bleibt)
	  destroy        Modell danach löschen (Standard true)
]]
function SandMonsterVFX.collapse(model: Model, options: { [string]: any }?)
	local opts = options or {}
	local meta = SandMonsterVFX.Meta
	local ground, height = groundBelow(model)
	local scale = height / (meta.golemHeight * STUDS_PER_METER)

	-- Zeitachse des Burst-Sheets: der Zerfall beginnt kurz nach dessen erstem Frame
	local delay = meta.frontStart - meta.burstStart
	local sweep = meta.frontEnd - meta.frontStart

	if opts.flipbook ~= false and hasAsset(SandMonsterVFX.Assets.Burst) then
		SandMonsterVFX.playFlipbook(ground, { sheet = "Burst", scale = scale })
	end
	SandMonsterVFX.disintegrate(model, {
		sweepTime = sweep,
		delay = delay,
		scale = scale,
		density = if opts.flipbook == false then 1.5 else 1,
		destroy = opts.destroy,
	})
	task.delay(delay + sweep * 0.35, function()
		SandMonsterVFX.spawnPile(ground, {
			scale = scale,
			growTime = sweep * 1.2,
			lifetime = if opts.pileLifetime == false then nil else (opts.pileLifetime or 8),
		})
	end)
end

return SandMonsterVFX
