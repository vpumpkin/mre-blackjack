--[[
	Beispiel (Script in ServerScriptService)

	Voraussetzungen:
	  * ModuleScript "SandMonsterVFX" (SandMonsterVFX.lua) in ReplicatedStorage
	  * ein Modell "SandGolem" im Workspace (importiertes SandGolem.fbx oder ein beliebiger NPC)
]]

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local SandMonsterVFX = require(ReplicatedStorage:WaitForChild("SandMonsterVFX"))

-- Asset-IDs können auch direkt im ModuleScript eingetragen werden
-- SandMonsterVFX.Assets.Burst = "rbxassetid://..."
-- SandMonsterVFX.Assets.Grain = "rbxassetid://..."
-- SandMonsterVFX.Assets.Dust  = "rbxassetid://..."

local golem = workspace:WaitForChild("SandGolem")
local triggered = false

local function onTouched(hit: BasePart)
	local character = hit.Parent
	if triggered or not character or character == golem then
		return
	end
	if character:FindFirstChildOfClass("Humanoid") then
		triggered = true
		SandMonsterVFX.collapse(golem)
	end
end

-- Golem zerfällt, sobald ein Spieler ihn berührt
for _, part in golem:GetDescendants() do
	if part:IsA("BasePart") then
		part.Touched:Connect(onTouched)
	end
end

-- Weitere Varianten:
--   SandMonsterVFX.playFlipbook(Vector3.new(0, 0, 0), { sheet = "Collapse" })  -- kompletter Blender-Golem als Billboard
--   SandMonsterVFX.playFlipbook(Vector3.new(0, 0, 0), { sheet = "Rise", scale = 1.5 }) -- Golem entsteht aus Sand
--   SandMonsterVFX.disintegrate(someNpc)                                        -- beliebigen NPC zerbröseln lassen
