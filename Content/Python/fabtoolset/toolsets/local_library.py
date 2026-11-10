# Copyright XUSJTUER. All Rights Reserved.

import json
import os

import unreal

import toolset_registry


@unreal.ustruct()
class FabAssetEntry(unreal.StructBase):
    """One Fab listing recorded as imported into this project."""
    listing_id = unreal.uproperty(str)
    project_path = unreal.uproperty(str, meta={'ToolTip': '/Game/... package path as recorded by the Fab plugin; may point at a folder.'})
    exists_in_project = unreal.uproperty(bool)


@unreal.ustruct()
class FabCacheEntry(unreal.StructBase):
    """One file in the local Fab Vault download cache."""
    name = unreal.uproperty(str, meta={'ToolTip': 'Path relative to the cache root.'})
    size_bytes = unreal.uproperty(int)


@unreal.ustruct()
class FabCacheInventory(unreal.StructBase):
    """Inventory of the local Fab Vault download cache."""
    cache_root = unreal.uproperty(str)
    entry_count = unreal.uproperty(int)
    entries = unreal.uproperty(unreal.Array(FabCacheEntry), meta={'ToolTip': 'Empty when the cache directory does not exist yet (no downloads) — not an error.'})


@unreal.ustruct()
class FabCatalogExportResult(unreal.StructBase):
    """Result of writing the combined Fab catalog to a JSON file."""
    output_path = unreal.uproperty(str)
    asset_count = unreal.uproperty(int)
    cache_entry_count = unreal.uproperty(int)


@unreal.uclass()
class FabLocalLibraryTools(unreal.ToolsetDefinition):
    """Catalogs Fab library data in this project: assets the Fab plugin has
    imported and the local Vault download cache. Read-only view over data the
    Fab plugin maintains."""

    @staticmethod
    def _get_imported_pairs() -> list:
        """Returns (listing_id, project_path) pairs from the Fab plugin config.

        Reads via UFabToolsetLibrary (raw reflection; the Fab config classes
        have no Python wrappers and their properties refuse editor access).
        A listing imported at several paths yields several pairs.
        """
        paths_to_ids = unreal.FabToolsetLibrary.get_fab_paths_listing_id()
        return [(listing_id, path) for path, listing_id in paths_to_ids.items()]

    @staticmethod
    def _get_cache_root() -> str:
        """Returns the Fab Vault cache directory (may not exist on disk)."""
        root = unreal.FabToolsetLibrary.get_fab_cache_directory_path()
        if not root:
            raise RuntimeError('Fab settings not available; is the Fab plugin loaded?')
        return root

    @staticmethod
    def _path_exists(path: str) -> bool:
        """Checks a /Game/... path as asset or directory, anything else on disk."""
        if not path:
            return False
        if path.startswith('/'):
            return (unreal.EditorAssetLibrary.does_asset_exist(path)
                    or unreal.EditorAssetLibrary.does_directory_exist(path))
        return os.path.exists(path)

    @staticmethod
    def _scan_cache(root: str) -> list:
        """Walks the cache directory and returns plain entries: name relative to
        the root, size in bytes."""
        entries = []
        if not os.path.isdir(root):
            return entries
        for dirpath, _dirnames, filenames in os.walk(root):
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                try:
                    size = os.path.getsize(file_path)
                except OSError:
                    continue
                entries.append({
                    'name': os.path.relpath(file_path, root),
                    'size_bytes': size,
                })
        return entries

    @toolset_registry.tool_call
    @staticmethod
    def list_local_fab_assets() -> list[FabAssetEntry]:
        """Lists Fab assets recorded as imported into this project.

        Returns:
            One entry per Fab listing. Empty list when nothing has been imported.
        """
        assets = []
        for listing_id, project_path in FabLocalLibraryTools._get_imported_pairs():
            entry = FabAssetEntry()
            entry.listing_id = listing_id
            entry.project_path = project_path
            entry.exists_in_project = FabLocalLibraryTools._path_exists(project_path)
            assets.append(entry)
        return assets

    @toolset_registry.tool_call
    @staticmethod
    def get_vault_cache_inventory() -> FabCacheInventory:
        """Inventories the local Fab Vault download cache.

        Returns:
            Cache root, entry count and per-file entries. Entries are empty
            when the cache directory does not exist yet (no downloads) — this
            is not an error.
        """
        root = FabLocalLibraryTools._get_cache_root()
        plain_entries = FabLocalLibraryTools._scan_cache(root)
        entries = []
        for plain in plain_entries:
            entry = FabCacheEntry()
            entry.name = plain['name']
            entry.size_bytes = plain['size_bytes']
            entries.append(entry)
        inventory = FabCacheInventory()
        inventory.cache_root = root
        inventory.entry_count = len(entries)
        inventory.entries = entries
        return inventory

    @toolset_registry.tool_call
    @staticmethod
    def export_fab_catalog(output_path: str) -> FabCatalogExportResult:
        """Writes the combined Fab catalog (imported assets + Vault cache inventory) as JSON.

        Args:
            output_path: Absolute path of the JSON file to write. Parent
                directories are created as needed.

        Returns:
            Output path and the counts of assets and cache entries written.
        """
        if not output_path:
            raise ValueError('output_path must not be empty.')

        assets = [
            {
                'listing_id': entry.listing_id,
                'project_path': entry.project_path,
                'exists_in_project': entry.exists_in_project,
            }
            for entry in FabLocalLibraryTools.list_local_fab_assets()
        ]
        inventory = FabLocalLibraryTools.get_vault_cache_inventory()

        catalog = {
            'assets': assets,
            'cache': {
                'cache_root': inventory.cache_root,
                'entry_count': inventory.entry_count,
                'entries': [
                    {'name': entry.name, 'size_bytes': entry.size_bytes}
                    for entry in inventory.entries
                ],
            },
        }
        parent = os.path.dirname(output_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as stream:
            json.dump(catalog, stream, ensure_ascii=False, indent=2)

        result = FabCatalogExportResult()
        result.output_path = output_path
        result.asset_count = len(assets)
        result.cache_entry_count = inventory.entry_count
        return result
