# Copyright XUSJTUER. All Rights Reserved.
"""Tests for FabLibraryTools."""

import json
import unittest.mock

import unreal

from fabtoolset.toolsets.fab_import import FabDownloadInfo, FabImportTools
from fabtoolset.toolsets.fab_library import (
    FabLibrarySearchResult,
    FabOwnedAssetDetail,
    FabOwnedFormat,
    FabLibraryTools,
    FabUserIdentity,
)
from toolset_registry.tests.toolset_testcase import ToolCallTestCase

FAB_LIBRARY_TOOLSET_NAME = f'{FabLibraryTools.__module__}.{FabLibraryTools.__name__}'

RAW_LIBRARY_PAGE = {
    'results': [{
        'uid': '1cb1ac49-f0c7-4d09-a904-22d19c6bae95',
        'createdAt': '2026-11-07T14:33:38.314358+00:00',
        'canRequestDownloadUrl': True,
        'source': 'acquired',
        'listing': {
            'uid': '1898b906-d481-4a05-8515-f2b4d3b28378',
            'title': '3D Platformer Game Bundle',
            'productType': 'game-system',
            'publisher': {'sellerName': 'Raul Jaramillo'},
        },
    }],
    'cursors': {'next': 'bz0wJnA9MjAyNg=='},
}

RAW_FORMATS = [
    {
        'assetFormatType': {'code': 'unreal-engine'},
        'files': [{
            'uid': 'fb0d9258-2885-4c23-b345-66af0d9ba890',
            'name': '1',
            'fileSize': None,
        }],
    },
    {
        'assetFormatType': {'code': 'unity'},
        'files': [{
            'uid': '6e6ae625-d4bd-40d9-bb96-6e2039a22f70',
            'name': 'scifi_beast06.unitypackage',
            'fileSize': 348243907,
        }],
    },
]

RAW_DOWNLOAD_INFO = {
    'downloadInfo': [{
        'assetFormat': 'asset-format/game-engine/unreal-engine',
        'distributionPointBaseUrls': [
            'https://google.epicgamescdn.com/Builds/Rocket/base1',
            'https://epicgames-download1.akamaized.net/Builds/Rocket/base2',
        ],
        'downloadUrl': 'https://google.epicgamescdn.com/Builds/Rocket/base1/file.manifest',
        'expires': '2026-11-09T11:14:19.373Z',
        'metadata': {},
        'type': 'manifest',
    }],
}

RAW_ME = {
    'displayName': 'XUSJTUER',
    'uid': '1d8ae21b-a936-416b-b841-fd6188711270',
    'epicId': 'xusjtuer-epic',
    'sellerName': 'XUSJTUER Studio',
    'isSeller': True,
}

RAW_OWNED_DETAIL = {
    'uid': '0861c47f-6d65-4919-b83c-093fcefe911d',
    'status': 'approved',
    'createdAt': '2026-11-07T14:33:38.314317Z',
    'capabilities': {'addByVerse': False, 'requestDownloadUrl': True},
    'listing': {
        'uid': '126120a3-996e-4dc3-94f1-6550f0adac03',
        'title': 'SciFi Beast06 Bull',
        'description': '<p>A scifi creature.</p>',
        'productType': '3d-model',
        'listingType': '3d-model',
        'category': {'name': 'Characters & Creatures'},
        'user': {'sellerName': 'Shumniy'},
        'averageRating': 5.0,
        'reviewCount': 19,
        'tags': [{'name': 'Pbr'}, {'name': 'Animated'}],
        'assetFormats': [{'assetFormatType': {'code': 'unreal-engine'}}],
        'licenses': [{'name': 'Personal'}],
    },
}


class FabLibraryToolsTestCase(ToolCallTestCase):
    """Test case that registers FabLibraryTools for the duration of a test run,
    preserving any production registration (see FabCatalogToolsTestCase)."""

    _was_registered = False

    @classmethod
    def setUpClass(cls):
        cls._was_registered = unreal.ToolsetRegistry.is_toolset_class_registered(
            FabLibraryTools)
        if not cls._was_registered:
            unreal.ToolsetRegistry.register_toolset_class(FabLibraryTools)

    @classmethod
    def tearDownClass(cls):
        if not cls._was_registered:
            unreal.ToolsetRegistry.unregister_toolset_class(FabLibraryTools)


class _FakeOpener:
    """Stand-in for the authenticated opener: records requests, replays canned responses."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response

        class _Response:
            def __init__(self, body):
                self._body = body

            def read(self):
                return self._body

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        return _Response(response)


class TestFabLibraryTools(FabLibraryToolsTestCase):
    """Tests for FabLibraryTools (authenticated library browsing). Network is
    mocked; the live endpoints are exercised manually, not in tests."""

    def test_toolset_schema(self):
        """Schema carries the class docstring and the five library tools."""
        registry = unreal.ToolsetRegistry
        schema = json.loads(registry.get_toolset_json_schema(FabLibraryTools))
        self.assertEqual(schema['name'], FAB_LIBRARY_TOOLSET_NAME)
        self.assertEqual(schema['version'], '1.0')
        tool_names = {tool['name'] for tool in schema['tools']}
        self.assertEqual(tool_names, {
            f'{FAB_LIBRARY_TOOLSET_NAME}.search_my_library',
            f'{FAB_LIBRARY_TOOLSET_NAME}.get_my_library_formats',
            f'{FAB_LIBRARY_TOOLSET_NAME}.get_my_library_download_info',
            f'{FAB_LIBRARY_TOOLSET_NAME}.get_my_library_identity',
            f'{FAB_LIBRARY_TOOLSET_NAME}.get_my_library_detail',
        })

    def test_search_maps_entries(self):
        """Raw library entries land on the documented FabLibraryEntry fields."""
        opener = _FakeOpener([json.dumps(RAW_LIBRARY_PAGE).encode('utf-8')])
        with unittest.mock.patch.object(
                FabImportTools, '_authenticated_opener', return_value=opener):
            page = FabLibraryTools.search_my_library()
        self.assertIsInstance(page, FabLibrarySearchResult)
        self.assertEqual(page.query, '')
        self.assertEqual(len(page.entries), 1)
        entry = page.entries[0]
        self.assertEqual(entry.library_asset_uid, '1cb1ac49-f0c7-4d09-a904-22d19c6bae95')
        self.assertEqual(entry.listing_uid, '1898b906-d481-4a05-8515-f2b4d3b28378')
        self.assertEqual(entry.title, '3D Platformer Game Bundle')
        self.assertEqual(entry.publisher_name, 'Raul Jaramillo')
        self.assertEqual(entry.product_type, 'game-system')
        self.assertEqual(entry.created_at, '2026-11-07T14:33:38.314358+00:00')
        self.assertTrue(entry.can_request_download_url)
        self.assertEqual(page.next_cursor, 'bz0wJnA9MjAyNg==')

    def test_search_request_url_encodes_filters(self):
        """Non-empty filters land in the endpoint URL; empty ones are omitted."""
        opener = _FakeOpener([json.dumps(RAW_LIBRARY_PAGE).encode('utf-8')])
        with unittest.mock.patch.object(
                FabImportTools, '_authenticated_opener', return_value=opener):
            FabLibraryTools.search_my_library('tree', '3d-model', '-createdAt', 'cur1')
        self.assertEqual(
            opener.requests[0].full_url,
            'https://www.fab.com/i/library/search?sort_by=-createdAt&q=tree'
            '&productTypes=3d-model&cursor=cur1')

    def test_search_default_url_has_sort_only(self):
        """With no filters the URL carries just the sort order."""
        opener = _FakeOpener([json.dumps(RAW_LIBRARY_PAGE).encode('utf-8')])
        with unittest.mock.patch.object(
                FabImportTools, '_authenticated_opener', return_value=opener):
            FabLibraryTools.search_my_library()
        self.assertEqual(
            opener.requests[0].full_url,
            'https://www.fab.com/i/library/search?sort_by=-createdAt')

    def test_formats_maps_entries(self):
        """Raw format entries land on the documented FabOwnedFormat fields;
        a missing fileSize maps to 0."""
        opener = _FakeOpener([json.dumps(RAW_FORMATS).encode('utf-8')])
        with unittest.mock.patch.object(
                FabImportTools, '_authenticated_opener', return_value=opener):
            formats = FabLibraryTools.get_my_library_formats('library-uid')
        self.assertEqual(len(formats), 2)
        self.assertIsInstance(formats[0], FabOwnedFormat)
        ue = formats[0]
        self.assertEqual(ue.format_code, 'unreal-engine')
        self.assertEqual(len(ue.files), 1)
        self.assertEqual(ue.files[0].file_uid, 'fb0d9258-2885-4c23-b345-66af0d9ba890')
        self.assertEqual(ue.files[0].name, '1')
        self.assertEqual(ue.files[0].file_size_bytes, 0)
        unity = formats[1]
        self.assertEqual(unity.format_code, 'unity')
        self.assertEqual(unity.files[0].name, 'scifi_beast06.unitypackage')
        self.assertEqual(unity.files[0].file_size_bytes, 348243907)

    def test_formats_request_url(self):
        """library_asset_uid lands in the formats endpoint path."""
        opener = _FakeOpener([json.dumps(RAW_FORMATS).encode('utf-8')])
        with unittest.mock.patch.object(
                FabImportTools, '_authenticated_opener', return_value=opener):
            FabLibraryTools.get_my_library_formats('library-uid')
        self.assertEqual(
            opener.requests[0].full_url,
            'https://www.fab.com/i/library/assets/library-uid/asset-formats')

    def test_formats_raises_on_empty_uid(self):
        """An empty library_asset_uid raises before any network activity."""
        with self.assertToolRaisesRuntimeError() as context:
            FabLibraryTools.get_my_library_formats('')
        self.assertIn('ValueError', str(context.exception))

    def test_download_info_maps_fields(self):
        """Raw downloadInfo[0] lands on the documented FabDownloadInfo fields."""
        opener = _FakeOpener([json.dumps(RAW_DOWNLOAD_INFO).encode('utf-8')])
        with unittest.mock.patch.object(
                FabImportTools, '_authenticated_opener', return_value=opener):
            info = FabLibraryTools.get_my_library_download_info('library-uid', 'file-uid')
        self.assertIsInstance(info, FabDownloadInfo)
        self.assertEqual(info.file_uid, 'file-uid')
        self.assertEqual(
            info.download_url,
            'https://google.epicgamescdn.com/Builds/Rocket/base1/file.manifest')
        self.assertEqual(
            list(info.distribution_point_base_urls),
            ['https://google.epicgamescdn.com/Builds/Rocket/base1',
             'https://epicgames-download1.akamaized.net/Builds/Rocket/base2'])
        self.assertEqual(info.expires, '2026-11-09T11:14:19.373Z')

    def test_download_info_request_url(self):
        """file_uid and platform land in the download-info endpoint path."""
        opener = _FakeOpener([json.dumps(RAW_DOWNLOAD_INFO).encode('utf-8')])
        with unittest.mock.patch.object(
                FabImportTools, '_authenticated_opener', return_value=opener):
            FabLibraryTools.get_my_library_download_info('library-uid', 'file-uid', platform='Mac')
        self.assertEqual(
            opener.requests[0].full_url,
            'https://www.fab.com/i/library/assets/library-uid/asset-formats/unreal-engine/'
            'files/file-uid/download-info?platform=Mac')

    def test_download_info_raises_on_empty_uid(self):
        """An empty library_asset_uid raises before any network activity."""
        with self.assertToolRaisesRuntimeError() as context:
            FabLibraryTools.get_my_library_download_info('', 'file-uid')
        self.assertIn('ValueError', str(context.exception))

    def test_download_info_raises_on_empty_file_uid(self):
        """An empty file_uid raises before any network activity."""
        with self.assertToolRaisesRuntimeError() as context:
            FabLibraryTools.get_my_library_download_info('library-uid', '')
        self.assertIn('ValueError', str(context.exception))

    def test_download_info_raises_on_empty_entries(self):
        """An empty downloadInfo list surfaces as a RuntimeError."""
        opener = _FakeOpener([json.dumps({'downloadInfo': []}).encode('utf-8')])
        with unittest.mock.patch.object(
                FabImportTools, '_authenticated_opener', return_value=opener):
            with self.assertToolRaisesRuntimeError() as context:
                FabLibraryTools.get_my_library_download_info('library-uid', 'file-uid')
        self.assertIn('No download info available', str(context.exception))

    def test_identity_maps_fields(self):
        """Raw /i/users/me fields land on the documented FabUserIdentity fields."""
        opener = _FakeOpener([json.dumps(RAW_ME).encode('utf-8')])
        with unittest.mock.patch.object(
                FabImportTools, '_authenticated_opener', return_value=opener):
            identity = FabLibraryTools.get_my_library_identity()
        self.assertIsInstance(identity, FabUserIdentity)
        self.assertEqual(identity.display_name, 'XUSJTUER')
        self.assertEqual(identity.uid, '1d8ae21b-a936-416b-b841-fd6188711270')
        self.assertEqual(identity.epic_id, 'xusjtuer-epic')
        self.assertEqual(identity.seller_name, 'XUSJTUER Studio')
        self.assertTrue(identity.is_seller)

    def test_identity_request_url(self):
        """Identity hits the /i/users/me endpoint."""
        opener = _FakeOpener([json.dumps(RAW_ME).encode('utf-8')])
        with unittest.mock.patch.object(
                FabImportTools, '_authenticated_opener', return_value=opener):
            FabLibraryTools.get_my_library_identity()
        self.assertEqual(opener.requests[0].full_url, 'https://www.fab.com/i/users/me')

    def test_detail_maps_fields(self):
        """Raw library-asset detail fields land on the documented FabOwnedAssetDetail."""
        opener = _FakeOpener([json.dumps(RAW_OWNED_DETAIL).encode('utf-8')])
        with unittest.mock.patch.object(
                FabImportTools, '_authenticated_opener', return_value=opener):
            detail = FabLibraryTools.get_my_library_detail('library-uid')
        self.assertIsInstance(detail, FabOwnedAssetDetail)
        self.assertEqual(detail.library_asset_uid, RAW_OWNED_DETAIL['uid'])
        self.assertEqual(detail.status, 'approved')
        self.assertTrue(detail.can_request_download_url)
        self.assertEqual(detail.acquired_at, '2026-11-07T14:33:38.314317Z')
        self.assertEqual(detail.listing_uid, '126120a3-996e-4dc3-94f1-6550f0adac03')
        self.assertEqual(detail.title, 'SciFi Beast06 Bull')
        self.assertEqual(detail.description, '<p>A scifi creature.</p>')
        self.assertEqual(detail.product_type, '3d-model')
        self.assertEqual(detail.category, 'Characters & Creatures')
        self.assertEqual(detail.seller_name, 'Shumniy')
        self.assertAlmostEqual(detail.rating_average, 5.0, delta=1e-5)
        self.assertEqual(detail.review_count, 19)
        self.assertEqual(list(detail.tags), ['Pbr', 'Animated'])
        self.assertEqual(list(detail.asset_formats), ['unreal-engine'])
        self.assertEqual(list(detail.license_names), ['Personal'])

    def test_detail_request_url(self):
        """library_asset_uid lands in the private detail endpoint path."""
        opener = _FakeOpener([json.dumps(RAW_OWNED_DETAIL).encode('utf-8')])
        with unittest.mock.patch.object(
                FabImportTools, '_authenticated_opener', return_value=opener):
            FabLibraryTools.get_my_library_detail('0861c47f-6d65')
        self.assertEqual(
            opener.requests[0].full_url,
            'https://www.fab.com/i/library/assets/0861c47f-6d65')

    def test_detail_raises_on_empty_library_asset_uid(self):
        """An empty library_asset_uid raises before any network activity."""
        with self.assertToolRaisesRuntimeError() as context:
            FabLibraryTools.get_my_library_detail('')
        self.assertIn('ValueError', str(context.exception))
