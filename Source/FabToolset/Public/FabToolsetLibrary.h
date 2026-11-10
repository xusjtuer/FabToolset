// Copyright XUSJTUER. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "FabToolsetLibrary.generated.h"

/**
 * Reflection readers for Fab plugin config objects. The Fab plugin's config
 * classes carry no BlueprintType marker and no Blueprint-visible members, so
 * they never get Python wrappers, and their config-only properties are also
 * refused by editor-property access (CPF_Edit required). These functions read
 * the config CDOs via raw FProperty reflection instead, which no Fab header
 * include or link dependency.
 */
UCLASS(BlueprintType)
class FABTOOLSET_API UFabToolsetLibrary : public UObject
{
	GENERATED_BODY()

public:
	/**
	 * Returns the Fab plugin's imported-asset map as recorded in its local config.
	 * @return Project path -> listing id; empty when nothing has been imported
	 *         or the Fab plugin is not loaded.
	 */
	UFUNCTION(BlueprintCallable, Category = "FabToolset")
	static TMap<FString, FString> GetFabPathsListingId();

	/**
	 * Returns the Fab Vault cache directory configured in the Fab settings.
	 * @return The configured directory path; empty when the Fab settings are
	 *         not available.
	 */
	UFUNCTION(BlueprintCallable, Category = "FabToolset")
	static FString GetFabCacheDirectoryPath();

	/**
	 * Returns the Fab plugin's current EOS access token for the logged-in user.
	 * @return The access token; empty when the Fab plugin is not loaded or no
	 *         user is logged in.
	 */
	UFUNCTION(BlueprintCallable, Category = "FabToolset")
	static FString GetFabAuthToken();

	/**
	 * Returns the Fab plugin's current EOS refresh token.
	 * @return The refresh token; empty when the Fab plugin is not loaded or no
	 *         user is logged in.
	 */
	UFUNCTION(BlueprintCallable, Category = "FabToolset")
	static FString GetFabRefreshToken();

	/**
	 * Returns the tracked status of a Fab import workflow started through
	 * FabAddToProject in this editor session.
	 * @return 'pending' while the workflow runs, 'completed' once it succeeded,
	 *         'cancelled' once it ended by user cancellation or failure,
	 *         'unknown' when this session did not start the import. Tracking
	 *         lives for the editor session only.
	 */
	UFUNCTION(BlueprintCallable, Category = "FabToolset")
	static FString GetFabImportStatus(const FString& AssetId);

	/**
	 * Returns when a tracked Fab import workflow reached its terminal state.
	 * @return RFC 3339 UTC timestamp; empty while the status is pending or
	 *         unknown.
	 */
	UFUNCTION(BlueprintCallable, Category = "FabToolset")
	static FString GetFabImportFinishedAt(const FString& AssetId);

	/**
	 * Starts the Fab plugin's Add to Project import workflow for a Fab listing,
	 * the same path the Fab browser UI triggers on its "Add to Project" button.
	 * Requires the Fab plugin to be loaded. The workflow's progress is queryable
	 * via GetFabImportStatus.
	 * @param DownloadUrl Signed manifest URL from the listing's download info.
	 * @param AssetId Listing uid.
	 * @param AssetName Listing title.
	 * @param AssetType Asset format code, e.g. "unreal-engine".
	 * @param ListingType Listing type from the listing detail.
	 * @param AssetNamespace Asset namespace, "fab" as sent by the Fab web frontend.
	 * @param DistributionPointBaseUrls CDN base URLs from the download info.
	 * @param IsQuixel Whether the listing is a Quixel asset.
	 */
	UFUNCTION(BlueprintCallable, Category = "FabToolset")
	static void FabAddToProject(const FString& DownloadUrl, const FString& AssetId, const FString& AssetName,
		const FString& AssetType, const FString& ListingType, const FString& AssetNamespace,
		const TArray<FString>& DistributionPointBaseUrls, bool IsQuixel);

private:
	/**
	 * Invokes a parameterless, FString-returning UFUNCTION on the Fab browser
	 * API CDO via ProcessEvent (the class has no module API export, so a direct
	 * link is not possible).
	 * @return The function's FString return value; empty when the Fab plugin
	 *         is not loaded or the function does not exist.
	 */
	static FString InvokeFabBrowserApiTokenFunction(const TCHAR* FunctionName);
};
