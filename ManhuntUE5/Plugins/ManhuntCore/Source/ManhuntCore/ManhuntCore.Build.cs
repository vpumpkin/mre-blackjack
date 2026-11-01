using UnrealBuildTool;

public class ManhuntCore : ModuleRules
{
	public ManhuntCore(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core",
			"CoreUObject",
			"Engine",
			"InputCore",
			"EnhancedInput",
			"NetCore",       // FFastArraySerializer (Tuer-/Fensterzustaende)
			"PhysicsCore"    // UPhysicalMaterial / EPhysicalSurface (Fahrzeug-Untergrund)
		});
	}
}
