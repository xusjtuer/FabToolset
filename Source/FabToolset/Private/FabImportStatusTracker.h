// Copyright XUSJTUER. All Rights Reserved.

#pragma once

#include "Containers/Map.h"
#include "Containers/UnrealString.h"
#include "HAL/CriticalSection.h"
#include "Misc/DateTime.h"
#include "Misc/OutputDevice.h"

/**
 * Tracks the lifecycle of Fab import workflows started through FabToolset.
 * The Fab plugin reports a workflow's end only via C++ delegates and one
 * LogFab line, none of which Python can reach, so this output device listens
 * for that line ("Fab workflow completed/cancelled for asset <id>") to flip a
 * pending entry recorded at start to its terminal state. Entries live for the
 * editor session only.
 */
class FFabImportStatusTracker : public FOutputDevice
{
public:
	/** Marks AssetId pending; the entry a later workflow log line flips. */
	void RecordStarted(const FString& AssetId);

	/** 'unknown' when never started in this session, else pending/completed/cancelled. */
	FString GetStatus(const FString& AssetId) const;

	/** RFC 3339 UTC of the terminal transition; empty while pending or unknown. */
	FString GetFinishedAt(const FString& AssetId) const;

	//~ Begin FOutputDevice Interface
	virtual void Serialize(const TCHAR* Message, ELogVerbosity::Type Verbosity, const FName& Category) override;
	//~ End FOutputDevice Interface

private:
	struct FEntry
	{
		FString Status;
		FDateTime StartedAt;
		FDateTime FinishedAt;
	};

	mutable FCriticalSection EntriesLock;
	TMap<FString, FEntry> Entries;
};
