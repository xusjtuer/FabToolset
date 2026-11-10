// Copyright XUSJTUER. All Rights Reserved.

#pragma once

#include "Modules/ModuleInterface.h"
#include "Logging/LogMacros.h"

DECLARE_LOG_CATEGORY_EXTERN(LogFabToolset, Log, Log);

class FFabImportStatusTracker;

/**
 * Shell module for the FabToolset plugin. Toolset registration and all tools
 * live in Content/Python (see init_unreal.py); this module also hosts the
 * import status tracker that watches GLog for the Fab plugin's workflow lines.
 */
class FFabToolsetModule : public IModuleInterface
{
public:
	virtual void StartupModule() override;
	virtual void ShutdownModule() override;

	/** Import status tracker; null outside StartupModule/ShutdownModule. */
	FFabImportStatusTracker* GetImportStatusTracker() const { return ImportStatusTracker; }

private:
	FFabImportStatusTracker* ImportStatusTracker = nullptr;
};
