// Copyright XUSJTUER. All Rights Reserved.

#include "FabImportStatusTracker.h"

#include "Logging/LogMacros.h"

namespace
{
	// The Fab plugin logs a workflow's end exactly once as one of these lines
	// (FAB_LOG = UE_LOG(LogFab, Display, ...), FabLog.h). cancelled covers both
	// user cancellation and failure: PackImportWorkflow cancels on download
	// errors.
	const TCHAR* const CompletedPrefix = TEXT("Fab workflow completed for asset ");
	const TCHAR* const CancelledPrefix = TEXT("Fab workflow cancelled for asset ");
	const FName LogFabCategory(TEXT("LogFab"));
}

void FFabImportStatusTracker::RecordStarted(const FString& AssetId)
{
	FScopeLock Lock(&EntriesLock);
	FEntry& Entry = Entries.FindOrAdd(AssetId);
	Entry.Status = TEXT("pending");
	Entry.StartedAt = FDateTime::UtcNow();
	Entry.FinishedAt = FDateTime::MinValue();
}

FString FFabImportStatusTracker::GetStatus(const FString& AssetId) const
{
	FScopeLock Lock(&EntriesLock);
	if (const FEntry* Entry = Entries.Find(AssetId))
	{
		return Entry->Status;
	}
	return TEXT("unknown");
}

FString FFabImportStatusTracker::GetFinishedAt(const FString& AssetId) const
{
	FScopeLock Lock(&EntriesLock);
	if (const FEntry* Entry = Entries.Find(AssetId))
	{
		if (Entry->Status != TEXT("pending"))
		{
			const FDateTime& Time = Entry->FinishedAt;
			return FString::Printf(TEXT("%04d-%02d-%02dT%02d:%02d:%02d.%03dZ"),
				Time.GetYear(), Time.GetMonth(), Time.GetDay(),
				Time.GetHour(), Time.GetMinute(), Time.GetSecond(), Time.GetMillisecond());
		}
	}
	return FString();
}

void FFabImportStatusTracker::Serialize(const TCHAR* Message, ELogVerbosity::Type Verbosity, const FName& Category)
{
	if (Category != LogFabCategory || !Message)
	{
		return;
	}

	const FStringView Text(Message);
	FStringView AssetIdView;
	const TCHAR* NewStatus = nullptr;
	if (Text.StartsWith(CompletedPrefix, ESearchCase::CaseSensitive))
	{
		NewStatus = TEXT("completed");
		AssetIdView = Text.RightChop(FCString::Strlen(CompletedPrefix));
	}
	else if (Text.StartsWith(CancelledPrefix, ESearchCase::CaseSensitive))
	{
		NewStatus = TEXT("cancelled");
		AssetIdView = Text.RightChop(FCString::Strlen(CancelledPrefix));
	}
	else
	{
		return;
	}

	const FString AssetId(AssetIdView.TrimEnd());
	if (AssetId.IsEmpty())
	{
		return;
	}

	FScopeLock Lock(&EntriesLock);
	if (FEntry* Entry = Entries.Find(AssetId))
	{
		Entry->Status = NewStatus;
		Entry->FinishedAt = FDateTime::UtcNow();
	}
	// A completed/cancelled line for an asset never started through
	// FabAddToProject (e.g. an import launched from the Fab window) is not
	// tracked: the entry stays absent so GetStatus keeps reporting 'unknown'.
}
