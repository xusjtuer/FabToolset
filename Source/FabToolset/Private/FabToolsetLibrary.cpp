// Copyright XUSJTUER. All Rights Reserved.

#include "FabToolsetLibrary.h"

#include "FabImportStatusTracker.h"
#include "FabToolset.h"
#include "Workflows/FabWorkflow.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Modules/ModuleManager.h"
#include "UObject/Class.h"
#include "UObject/StrProperty.h"
#include "UObject/UnrealType.h"
#include "UObject/UObjectGlobals.h"

namespace
{
	constexpr const TCHAR* FabLocalAssetsObjectPath = TEXT("/Script/Fab.Default__FabLocalAssets");
	constexpr const TCHAR* FabSettingsObjectPath = TEXT("/Script/Fab.Default__FabSettings");
	constexpr const TCHAR* FabBrowserApiObjectPath = TEXT("/Script/Fab.Default__FabBrowserApi");
}

TMap<FString, FString> UFabToolsetLibrary::GetFabPathsListingId()
{
	TMap<FString, FString> Result;

	UObject* LocalAssets = FindObject<UObject>(nullptr, FabLocalAssetsObjectPath);
	if (!LocalAssets)
	{
		return Result;
	}

	FMapProperty* MapProp = CastField<FMapProperty>(LocalAssets->GetClass()->FindPropertyByName(TEXT("PathsListingID")));
	if (!MapProp)
	{
		return Result;
	}

	// The Fab module's generated code registers both map sides as FStrProperty;
	// guard anyway so a future Fab type change degrades to an empty map instead
	// of corrupt reads.
	const FStrProperty* KeyProp = CastField<FStrProperty>(MapProp->KeyProp);
	const FStrProperty* ValueProp = CastField<FStrProperty>(MapProp->ValueProp);
	if (!KeyProp || !ValueProp)
	{
		return Result;
	}

	FScriptMapHelper MapHelper(MapProp, MapProp->ContainerPtrToValuePtr<void>(LocalAssets));
	for (int32 Index = 0; Index < MapHelper.Num(); ++Index)
	{
		if (!MapHelper.IsValidIndex(Index))
		{
			continue;
		}
		Result.Add(
			*reinterpret_cast<const FString*>(MapHelper.GetKeyPtr(Index)),
			*reinterpret_cast<const FString*>(MapHelper.GetValuePtr(Index)));
	}
	return Result;
}

FString UFabToolsetLibrary::GetFabCacheDirectoryPath()
{
	UObject* Settings = FindObject<UObject>(nullptr, FabSettingsObjectPath);
	if (!Settings)
	{
		return FString();
	}

	FStructProperty* DirProp = CastField<FStructProperty>(Settings->GetClass()->FindPropertyByName(TEXT("CacheDirectoryPath")));
	if (!DirProp || !DirProp->Struct)
	{
		return FString();
	}
	const FStrProperty* PathProp = CastField<FStrProperty>(DirProp->Struct->FindPropertyByName(TEXT("Path")));
	if (!PathProp)
	{
		return FString();
	}

	return *reinterpret_cast<const FString*>(PathProp->ContainerPtrToValuePtr<void>(DirProp->ContainerPtrToValuePtr<void>(Settings)));
}

FString UFabToolsetLibrary::InvokeFabBrowserApiTokenFunction(const TCHAR* FunctionName)
{
	UObject* BrowserApi = FindObject<UObject>(nullptr, FabBrowserApiObjectPath);
	if (!BrowserApi)
	{
		return FString();
	}

	UFunction* Function = BrowserApi->FindFunction(FunctionName);
	if (!Function)
	{
		return FString();
	}

	TArray<uint8> Parms;
	Parms.SetNumZeroed(Function->ParmsSize);
	BrowserApi->ProcessEvent(Function, Parms.GetData());

	// Both token functions take no parameters, so the sole FStrProperty among
	// the parameter properties is the return value.
	for (TFieldIterator<FProperty> It(Function); It; ++It)
	{
		if (const FStrProperty* ReturnProp = CastField<FStrProperty>(*It))
		{
			return *reinterpret_cast<const FString*>(ReturnProp->ContainerPtrToValuePtr<void>(Parms.GetData()));
		}
	}
	return FString();
}

FString UFabToolsetLibrary::GetFabAuthToken()
{
	return InvokeFabBrowserApiTokenFunction(TEXT("GetAuthToken"));
}

FString UFabToolsetLibrary::GetFabRefreshToken()
{
	return InvokeFabBrowserApiTokenFunction(TEXT("GetRefreshToken"));
}

void UFabToolsetLibrary::FabAddToProject(const FString& DownloadUrl, const FString& AssetId, const FString& AssetName,
	const FString& AssetType, const FString& ListingType, const FString& AssetNamespace,
	const TArray<FString>& DistributionPointBaseUrls, bool IsQuixel)
{
	UObject* BrowserApi = FindObject<UObject>(nullptr, FabBrowserApiObjectPath);
	if (!BrowserApi)
	{
		UKismetSystemLibrary::RaiseScriptError(TEXT("Fab plugin is not loaded; Add to Project is unavailable."));
		return;
	}

	UFunction* Function = BrowserApi->FindFunction(TEXT("AddToProject"));
	if (!Function)
	{
		UKismetSystemLibrary::RaiseScriptError(TEXT("Fab browser API does not expose AddToProject."));
		return;
	}

	TArray<uint8> Parms;
	Parms.SetNumZeroed(Function->ParmsSize);

	FStrProperty* UrlProp = CastField<FStrProperty>(Function->FindPropertyByName(TEXT("DownloadUrl")));
	FStructProperty* MetadataProp = CastField<FStructProperty>(Function->FindPropertyByName(TEXT("AssetMetadata")));
	if (!UrlProp || !MetadataProp || MetadataProp->Struct != FFabAssetMetadata::StaticStruct())
	{
		UKismetSystemLibrary::RaiseScriptError(TEXT("Fab AddToProject parameter signature mismatch."));
		return;
	}

	FString* UrlValue = new (UrlProp->ContainerPtrToValuePtr<void>(Parms.GetData())) FString(DownloadUrl);
	FFabAssetMetadata* MetadataValue = new (MetadataProp->ContainerPtrToValuePtr<void>(Parms.GetData())) FFabAssetMetadata();
	MetadataValue->AssetId = AssetId;
	MetadataValue->AssetName = AssetName;
	MetadataValue->AssetType = AssetType;
	MetadataValue->ListingType = ListingType;
	MetadataValue->AssetNamespace = AssetNamespace;
	MetadataValue->DistributionPointBaseUrls = DistributionPointBaseUrls;
	MetadataValue->IsQuixel = IsQuixel;

	// Record before ProcessEvent: the workflow broadcasts completion through
	// AsyncTask(GameThread), which can only run after this call returns, so
	// the pending entry is in place before the terminal log line arrives.
	if (FFabToolsetModule* Module = FModuleManager::GetModulePtr<FFabToolsetModule>("FabToolset"))
	{
		if (FFabImportStatusTracker* Tracker = Module->GetImportStatusTracker())
		{
			Tracker->RecordStarted(AssetId);
		}
	}

	BrowserApi->ProcessEvent(Function, Parms.GetData());

	// ProcessEvent does not destruct parameter memory; these were placement-new'd.
	MetadataValue->~FFabAssetMetadata();
	UrlValue->~FString();
}

FString UFabToolsetLibrary::GetFabImportStatus(const FString& AssetId)
{
	const FFabToolsetModule* Module = FModuleManager::GetModulePtr<FFabToolsetModule>("FabToolset");
	if (!Module || !Module->GetImportStatusTracker())
	{
		return TEXT("unknown");
	}
	return Module->GetImportStatusTracker()->GetStatus(AssetId);
}

FString UFabToolsetLibrary::GetFabImportFinishedAt(const FString& AssetId)
{
	const FFabToolsetModule* Module = FModuleManager::GetModulePtr<FFabToolsetModule>("FabToolset");
	if (!Module || !Module->GetImportStatusTracker())
	{
		return FString();
	}
	return Module->GetImportStatusTracker()->GetFinishedAt(AssetId);
}
