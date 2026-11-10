// Copyright XUSJTUER. All Rights Reserved.

#include "FabToolset.h"

#include "FabImportStatusTracker.h"
#include "CoreGlobals.h"
#include "Misc/OutputDeviceRedirector.h"
#include "Modules/ModuleManager.h"

/*virtual*/ void FFabToolsetModule::StartupModule()
{
	ImportStatusTracker = new FFabImportStatusTracker();
	if (GLog)
	{
		GLog->AddOutputDevice(ImportStatusTracker);
	}
}

/*virtual*/ void FFabToolsetModule::ShutdownModule()
{
	if (ImportStatusTracker)
	{
		if (GLog)
		{
			GLog->RemoveOutputDevice(ImportStatusTracker);
		}
		delete ImportStatusTracker;
		ImportStatusTracker = nullptr;
	}
}

IMPLEMENT_MODULE(FFabToolsetModule, FabToolset);
DEFINE_LOG_CATEGORY(LogFabToolset);
