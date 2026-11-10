# Copyright XUSJTUER. All Rights Reserved.
"""Tests for FabLocalLibraryTools."""

import json
import os
import tempfile

import unreal

from fabtoolset.toolsets.local_library import (
    FabAssetEntry,
    FabCacheInventory,
    FabCatalogExportResult,
    FabLocalLibraryTools,
)
from toolset_registry.tests.toolset_testcase import ToolCallTestCase

FAB_TOOLSET_NAME = f'{FabLocalLibraryTools.__module__}.{FabLocalLibraryTools.__name__}'


class FabLocalLibraryToolsTestCase(ToolCallTestCase):
    """Test case that registers FabLocalLibraryTools for the duration of a test run.

    The production registration from init_unreal.py survives the run: when the
    toolset is already registered, setUpClass leaves it alone and tearDownClass
    skips the unregister. (The engine's own ToolCallTestCase unregisters
    unconditionally, which drops the production registration after a run.)
    """

    _was_registered = False

    @classmethod
    def setUpClass(cls):
        cls._was_registered = unreal.ToolsetRegistry.is_toolset_class_registered(
            FabLocalLibraryTools)
        if not cls._was_registered:
            unreal.ToolsetRegistry.register_toolset_class(FabLocalLibraryTools)

    @classmethod
    def tearDownClass(cls):
        if not cls._was_registered:
            unreal.ToolsetRegistry.unregister_toolset_class(FabLocalLibraryTools)


class TestFabLocalLibraryTools(FabLocalLibraryToolsTestCase):
    """Tests for FabLocalLibraryTools (read-only view over Fab plugin data)."""

    def test_toolset_schema(self):
        """Schema carries the class docstring and the three tools."""
        registry = unreal.ToolsetRegistry
        schema = json.loads(registry.get_toolset_json_schema(FabLocalLibraryTools))
        self.assertEqual(schema['name'], FAB_TOOLSET_NAME)
        self.assertEqual(schema['version'], '1.0')
        tool_names = {tool['name'] for tool in schema['tools']}
        self.assertEqual(tool_names, {
            f'{FAB_TOOLSET_NAME}.list_local_fab_assets',
            f'{FAB_TOOLSET_NAME}.get_vault_cache_inventory',
            f'{FAB_TOOLSET_NAME}.export_fab_catalog',
        })

    def test_list_local_fab_assets_returns_entries(self):
        """Returns entries carrying the three documented fields.

        The library may legitimately be empty on this machine, so only the
        shape is asserted. Struct types are Python-defined, so isinstance is
        checked against the classes from the module, not the unreal module.
        """
        results = FabLocalLibraryTools.list_local_fab_assets()
        for entry in results:
            self.assertIsInstance(entry, FabAssetEntry)
            self.assertIsInstance(entry.listing_id, str)
            self.assertIsInstance(entry.project_path, str)
            self.assertIsInstance(entry.exists_in_project, bool)

    def test_get_vault_cache_inventory_shape(self):
        """Returns cache_root, entry_count and entries of matching length."""
        inventory = FabLocalLibraryTools.get_vault_cache_inventory()
        self.assertIsInstance(inventory, FabCacheInventory)
        self.assertIsInstance(inventory.cache_root, str)
        self.assertEqual(inventory.entry_count, len(inventory.entries))
        for entry in inventory.entries:
            self.assertIsInstance(entry.name, str)
            self.assertIsInstance(entry.size_bytes, int)

    def test_scan_cache_missing_dir_returns_empty(self):
        """A nonexistent cache root yields no entries."""
        missing_root = os.path.join(tempfile.gettempdir(), 'FabToolsetTest_NonexistentDir')
        self.assertEqual(FabLocalLibraryTools._scan_cache(missing_root), [])

    def test_scan_cache_reports_relative_names_and_sizes(self):
        """Entries carry the name relative to the root and the byte size."""
        root = tempfile.mkdtemp(prefix='FabToolsetTest_Cache_')
        try:
            file_path = os.path.join(root, 'asset.pack')
            payload = b'0123456789'
            with open(file_path, 'wb') as stream:
                stream.write(payload)
            entries = FabLocalLibraryTools._scan_cache(root)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]['name'], 'asset.pack')
            self.assertEqual(entries[0]['size_bytes'], len(payload))
        finally:
            os.remove(file_path)
            os.rmdir(root)

    def test_export_fab_catalog_writes_json(self):
        """Writes valid JSON with assets and cache sections to the given path."""
        output_path = os.path.join(tempfile.gettempdir(), 'FabToolsetTest_Catalog',
                                   'catalog.json')
        try:
            result = FabLocalLibraryTools.export_fab_catalog(output_path)
            self.assertIsInstance(result, FabCatalogExportResult)
            self.assertEqual(result.output_path, output_path)
            self.assertEqual(result.asset_count,
                             len(FabLocalLibraryTools.list_local_fab_assets()))
            self.assertEqual(result.cache_entry_count,
                             FabLocalLibraryTools.get_vault_cache_inventory().entry_count)
            with open(output_path, encoding='utf-8') as stream:
                catalog = json.load(stream)
            self.assertIn('assets', catalog)
            self.assertIn('cache', catalog)
        finally:
            if os.path.exists(output_path):
                os.remove(output_path)
            os.rmdir(os.path.dirname(output_path))

    def test_export_fab_catalog_raises_on_empty_path(self):
        """Raises when output_path is empty."""
        with self.assertToolRaisesRuntimeError() as context:
            FabLocalLibraryTools.export_fab_catalog('')
        self.assertIn('ValueError: ', str(context.exception))
