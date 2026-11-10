// Copyright XUSJTUER. All Rights Reserved.

using UnrealBuildTool;

public class FabToolset : ModuleRules
{
	public FabToolset(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.Add("Core");

		PrivateDependencyModuleNames.AddRange(new string[]
		{
			"CoreUObject",
			"Engine",
			"Fab"
		});
	}
}
