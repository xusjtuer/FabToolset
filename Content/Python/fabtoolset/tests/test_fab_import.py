# Copyright XUSJTUER. All Rights Reserved.
"""Tests for FabImportTools."""

import http.cookiejar
import io
import json
import unittest.mock
import urllib.error
import urllib.request

import unreal

from fabtoolset.toolsets.fab_import import (
    FabDownloadInfo,
    FabFileVersion,
    FabImportStatus,
    FabImportTools,
)
from toolset_registry.tests.toolset_testcase import ToolCallTestCase

FAB_IMPORT_TOOLSET_NAME = f'{FabImportTools.__module__}.{FabImportTools.__name__}'

RAW_FORMAT = {
    'assetFormatType': {'code': 'unreal-engine'},
    'versions': [{
        'uid': '2acc45ee-6b86-4be0-b708-57d59cd7bdb9',
        'name': 'Plant_Bracken_Fern_01',
        'artifactId': 'Megaplanae5e4052a7aeV1',
        'fileType': 'source',
        'status': 'ready',
        'engineVersions': ['UE_5.8'],
        'targetPlatforms': ['Windows'],
    }],
}

RAW_DOWNLOAD_INFO = {
    'downloadInfo': [{
        'assetFormat': 'asset-format/game-engine/unreal-engine',
        'distributionPointBaseUrls': [
            'https://egdownload.fastly-edge.com/Builds/Rocket/base1',
            'https://epicgames-download1.akamaized.net/Builds/Rocket/base2',
        ],
        'downloadUrl': 'https://egdownload.fastly-edge.com/Builds/Rocket/base1/file.manifest',
        'expires': '2026-11-09T08:00:15.579Z',
        'metadata': {},
        'type': 'manifest',
    }],
}


class FabImportToolsTestCase(ToolCallTestCase):
    """Test case that registers FabImportTools for the duration of a test run,
    preserving any production registration (see FabCatalogToolsTestCase)."""

    _was_registered = False

    @classmethod
    def setUpClass(cls):
        cls._was_registered = unreal.ToolsetRegistry.is_toolset_class_registered(
            FabImportTools)
        if not cls._was_registered:
            unreal.ToolsetRegistry.register_toolset_class(FabImportTools)

    @classmethod
    def tearDownClass(cls):
        if not cls._was_registered:
            unreal.ToolsetRegistry.unregister_toolset_class(FabImportTools)


class _FakeOpener:
    """Stand-in for the authenticated opener: records requests, replays canned responses.

    Mirrors OpenerDirector.handlers so _post_json's CSRF cookie extraction finds
    a processor when csrf_cookie is given."""

    def __init__(self, responses, csrf_cookie=None):
        self._responses = list(responses)
        self.requests = []
        self.handlers = []
        if csrf_cookie:
            name, value = csrf_cookie
            jar = http.cookiejar.CookieJar()
            jar.set_cookie(http.cookiejar.Cookie(
                version=0, name=name, value=value, port=None, port_specified=False,
                domain='fab.com', domain_specified=False, domain_initial_dot=False,
                path='/', path_specified=True, secure=False, expires=None,
                discard=True, comment=None, comment_url=None, rest={}))
            self.handlers.append(urllib.request.HTTPCookieProcessor(jar))

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


class TestFabImportTools(FabImportToolsTestCase):
    """Tests for FabImportTools (authenticated download info + import trigger).
    Network and the Fab plugin import call are mocked; the live endpoints are
    exercised manually, not in tests."""

    def test_toolset_schema(self):
        """Schema carries the class docstring and the five import tools."""
        registry = unreal.ToolsetRegistry
        schema = json.loads(registry.get_toolset_json_schema(FabImportTools))
        self.assertEqual(schema['name'], FAB_IMPORT_TOOLSET_NAME)
        self.assertEqual(schema['version'], '1.0')
        tool_names = {tool['name'] for tool in schema['tools']}
        self.assertEqual(tool_names, {
            f'{FAB_IMPORT_TOOLSET_NAME}.get_fab_listing_format',
            f'{FAB_IMPORT_TOOLSET_NAME}.get_fab_download_info',
            f'{FAB_IMPORT_TOOLSET_NAME}.add_fab_listing_to_project',
            f'{FAB_IMPORT_TOOLSET_NAME}.grant_fab_listing_to_library',
            f'{FAB_IMPORT_TOOLSET_NAME}.get_fab_import_status',
        })

    def test_get_format_maps_versions(self):
        """Raw version entries land on the documented FabFileVersion fields."""
        opener = _FakeOpener([json.dumps(RAW_FORMAT).encode('utf-8')])
        with unittest.mock.patch.object(
                FabImportTools, '_authenticated_opener', return_value=opener):
            versions = FabImportTools.get_fab_listing_format('listing-uid')
        self.assertEqual(len(versions), 1)
        version = versions[0]
        self.assertIsInstance(version, FabFileVersion)
        self.assertEqual(version.version_uid, '2acc45ee-6b86-4be0-b708-57d59cd7bdb9')
        self.assertEqual(version.name, 'Plant_Bracken_Fern_01')
        self.assertEqual(version.artifact_id, 'Megaplanae5e4052a7aeV1')
        self.assertEqual(version.file_type, 'source')
        self.assertEqual(version.status, 'ready')
        self.assertEqual(list(version.engine_versions), ['UE_5.8'])
        self.assertEqual(list(version.target_platforms), ['Windows'])

    def test_get_format_maps_files_for_converted_formats(self):
        """gltf/glb/fbx listings expose "files"; those uids land on version_uid."""
        raw_files = {
            'assetFormatType': {'code': 'glb'},
            'files': [{
                'uid': '91961a61-2c42-4957-a7b0-92913580d878',
                'name': '397_plastic_garden_chairs_table_lod0.glb',
                'fileType': 'source',
                'status': 'ready',
                'size': 955140,
            }],
        }
        opener = _FakeOpener([json.dumps(raw_files).encode('utf-8')])
        with unittest.mock.patch.object(
                FabImportTools, '_authenticated_opener', return_value=opener):
            versions = FabImportTools.get_fab_listing_format('listing-uid', 'glb')
        self.assertEqual(len(versions), 1)
        version = versions[0]
        self.assertEqual(version.version_uid, '91961a61-2c42-4957-a7b0-92913580d878')
        self.assertEqual(version.name, '397_plastic_garden_chairs_table_lod0.glb')
        self.assertEqual(version.status, 'ready')
        self.assertEqual(list(version.engine_versions), [])

    def test_get_format_request_url_and_auth(self):
        """The authenticate POST carries the refresh token, the format GET hits
        the documented endpoint path."""
        opener = _FakeOpener([json.dumps({}).encode('utf-8'),
                              json.dumps(RAW_FORMAT).encode('utf-8')])
        with unittest.mock.patch.object(
                FabImportTools, '_get_fab_tokens',
                return_value=('test-access-token', 'test-refresh-token')), \
             unittest.mock.patch(
                'fabtoolset.toolsets.fab_import.urllib.request.build_opener',
                return_value=opener):
            FabImportTools.get_fab_listing_format('listing-uid')
        auth_request = opener.requests[0]
        self.assertIn('https://www.fab.com/p/authenticate', auth_request.full_url)
        self.assertEqual(auth_request.get_method(), 'POST')
        auth_body = json.loads(auth_request.data.decode('utf-8'))
        self.assertEqual(auth_body, {'refreshToken': 'test-refresh-token'})
        self.assertEqual(auth_request.get_header('Authorization'), 'Bearer test-access-token')
        format_request = opener.requests[1]
        self.assertEqual(
            format_request.full_url,
            'https://www.fab.com/i/listings/listing-uid/asset-formats/unreal-engine')

    def test_get_format_raises_when_not_logged_in(self):
        """Empty EOS tokens surface as a RuntimeError pointing at the Fab window."""
        with unittest.mock.patch.object(
                FabImportTools, '_get_fab_tokens', return_value=('', '')):
            with self.assertToolRaisesRuntimeError() as context:
                FabImportTools.get_fab_listing_format('listing-uid')
        self.assertIn('Fab is not logged in', str(context.exception))

    def test_get_format_raises_on_empty_listing_uid(self):
        """An empty listing_uid raises before any network activity."""
        with self.assertToolRaisesRuntimeError() as context:
            FabImportTools.get_fab_listing_format('')
        self.assertIn('ValueError', str(context.exception))

    def test_get_format_raises_on_empty_format_code(self):
        """An empty format_code raises before any network activity."""
        with self.assertToolRaisesRuntimeError() as context:
            FabImportTools.get_fab_listing_format('listing-uid', '')
        self.assertIn('ValueError', str(context.exception))

    def test_get_format_raises_on_http_error(self):
        """A failing authenticated request surfaces as a RuntimeError."""
        error = urllib.error.HTTPError(
            'https://www.fab.com/i/listings/gone/asset-formats/unreal-engine',
            404, 'Not Found', None, io.BytesIO(b''))
        opener = _FakeOpener([error])
        with unittest.mock.patch.object(
                FabImportTools, '_authenticated_opener', return_value=opener):
            with self.assertToolRaisesRuntimeError() as context:
                FabImportTools.get_fab_listing_format('gone')
        self.assertIn('Fab request failed', str(context.exception))

    def test_get_download_info_maps_fields(self):
        """Raw downloadInfo[0] lands on the documented FabDownloadInfo fields."""
        opener = _FakeOpener([json.dumps(RAW_DOWNLOAD_INFO).encode('utf-8')])
        with unittest.mock.patch.object(
                FabImportTools, '_authenticated_opener', return_value=opener):
            info = FabImportTools.get_fab_download_info('listing-uid', 'file-uid')
        self.assertIsInstance(info, FabDownloadInfo)
        self.assertEqual(info.file_uid, 'file-uid')
        self.assertEqual(
            info.download_url,
            'https://egdownload.fastly-edge.com/Builds/Rocket/base1/file.manifest')
        self.assertEqual(
            list(info.distribution_point_base_urls),
            ['https://egdownload.fastly-edge.com/Builds/Rocket/base1',
             'https://epicgames-download1.akamaized.net/Builds/Rocket/base2'])
        self.assertEqual(info.expires, '2026-11-09T08:00:15.579Z')

    def test_get_download_info_request_url(self):
        """file_uid and platform land in the download-info endpoint path."""
        opener = _FakeOpener([json.dumps(RAW_DOWNLOAD_INFO).encode('utf-8')])
        with unittest.mock.patch.object(
                FabImportTools, '_authenticated_opener', return_value=opener):
            FabImportTools.get_fab_download_info('listing-uid', 'file-uid', platform='Mac')
        self.assertEqual(
            opener.requests[0].full_url,
            'https://www.fab.com/i/listings/listing-uid/asset-formats/unreal-engine/'
            'files/file-uid/download-info?platform=Mac')

    def test_get_download_info_raises_on_empty_entries(self):
        """An empty downloadInfo list surfaces as a RuntimeError."""
        opener = _FakeOpener([json.dumps({'downloadInfo': []}).encode('utf-8')])
        with unittest.mock.patch.object(
                FabImportTools, '_authenticated_opener', return_value=opener):
            with self.assertToolRaisesRuntimeError() as context:
                FabImportTools.get_fab_download_info('listing-uid', 'file-uid')
        self.assertIn('No download info available', str(context.exception))

    def test_add_to_project_forwards_arguments(self):
        """All arguments reach the C++ library call in documented order."""
        base_urls = ['https://cdn1/base', 'https://cdn2/base']
        with unittest.mock.patch.object(
                FabImportTools, '_invoke_add_to_project') as invoke:
            FabImportTools.add_fab_listing_to_project(
                'https://cdn1/file.manifest', 'listing-uid', 'Fern Plant',
                'unreal-engine', '3d-model', 'fab', base_urls, True)
        invoke.assert_called_once_with(
            'https://cdn1/file.manifest', 'listing-uid', 'Fern Plant',
            'unreal-engine', '3d-model', 'fab', base_urls, True)

    def test_add_to_project_accepts_future_expires(self):
        """A future expires timestamp lets the import start."""
        with unittest.mock.patch.object(
                FabImportTools, '_invoke_add_to_project') as invoke:
            FabImportTools.add_fab_listing_to_project(
                'https://cdn1/file.manifest', 'listing-uid', 'Name',
                'unreal-engine', '3d-model',
                expires='2099-01-01T00:00:00.000Z')
        self.assertEqual(invoke.call_count, 1)

    def test_add_to_project_raises_on_expired_url(self):
        """An already-past expires timestamp raises before the import starts."""
        with unittest.mock.patch.object(
                FabImportTools, '_invoke_add_to_project') as invoke:
            with self.assertToolRaisesRuntimeError() as context:
                FabImportTools.add_fab_listing_to_project(
                    'https://cdn1/file.manifest', 'listing-uid', 'Name',
                    'unreal-engine', '3d-model',
                    expires='2020-01-01T00:00:00.000Z')
        self.assertIn('expired', str(context.exception))
        self.assertEqual(invoke.call_count, 0)

    def test_add_to_project_raises_on_malformed_expires(self):
        """A non-ISO expires timestamp raises instead of skipping validation."""
        with self.assertToolRaisesRuntimeError() as context:
            FabImportTools.add_fab_listing_to_project(
                'https://cdn1/file.manifest', 'listing-uid', 'Name',
                'unreal-engine', '3d-model', expires='not-a-date')
        self.assertIn('ISO 8601', str(context.exception))

    def test_add_to_project_raises_on_empty_download_url(self):
        """An empty download_url raises before touching the Fab plugin."""
        with self.assertToolRaisesRuntimeError() as context:
            FabImportTools.add_fab_listing_to_project(
                '', 'listing-uid', 'Name', 'unreal-engine', '3d-model')
        self.assertIn('ValueError', str(context.exception))

    def test_add_to_project_raises_on_empty_asset_id(self):
        """An empty asset_id raises before touching the Fab plugin."""
        with self.assertToolRaisesRuntimeError() as context:
            FabImportTools.add_fab_listing_to_project(
                'https://cdn1/file.manifest', '', 'Name', 'unreal-engine', '3d-model')
        self.assertIn('ValueError', str(context.exception))

    def test_grant_posts_offer_id_to_claim_endpoint(self):
        """The claim POSTs offerId (camelCase) plus CSRF headers to the
        add-to-library endpoint."""
        opener = _FakeOpener([b''], csrf_cookie=('fab_csrftoken', 'csrf-token-1'))
        with unittest.mock.patch.object(
                FabImportTools, '_authenticated_opener', return_value=opener):
            FabImportTools.grant_fab_listing_to_library('listing-uid', 'offer-123')
        request = opener.requests[0]
        self.assertEqual(
            request.full_url,
            'https://www.fab.com/i/listings/listing-uid/add-to-library')
        self.assertEqual(request.get_method(), 'POST')
        self.assertEqual(json.loads(request.data.decode('utf-8')), {'offerId': 'offer-123'})
        self.assertEqual(request.get_header('Referer'), 'https://www.fab.com/')
        # urllib stores header names capitalized; the wire name is X-CSRFToken.
        self.assertEqual(request.get_header('X-csrftoken'), 'csrf-token-1')

    def test_grant_raises_on_empty_listing_uid(self):
        """An empty listing_uid raises before any network activity."""
        with self.assertToolRaisesRuntimeError() as context:
            FabImportTools.grant_fab_listing_to_library('', 'offer-123')
        self.assertIn('ValueError', str(context.exception))

    def test_grant_raises_on_empty_offer_id(self):
        """An empty offer_id raises before any network activity."""
        with self.assertToolRaisesRuntimeError() as context:
            FabImportTools.grant_fab_listing_to_library('listing-uid', '')
        self.assertIn('ValueError', str(context.exception))

    def test_get_import_status_maps_terminal_state(self):
        """The C++ status and finish time land on the documented fields."""
        with unittest.mock.patch.object(
                FabImportTools, '_get_import_status_raw', return_value='completed'), \
             unittest.mock.patch.object(
                FabImportTools, '_get_import_finished_raw',
                return_value='2026-11-09T12:00:00.000Z'):
            status = FabImportTools.get_fab_import_status('listing-uid')
        self.assertIsInstance(status, FabImportStatus)
        self.assertEqual(status.asset_id, 'listing-uid')
        self.assertEqual(status.status, 'completed')
        self.assertEqual(status.finished_at, '2026-11-09T12:00:00.000Z')

    def test_get_import_status_defaults_blank_to_unknown(self):
        """A blank status from the C++ side reads as 'unknown'."""
        with unittest.mock.patch.object(
                FabImportTools, '_get_import_status_raw', return_value=''), \
             unittest.mock.patch.object(
                FabImportTools, '_get_import_finished_raw', return_value=''):
            status = FabImportTools.get_fab_import_status('listing-uid')
        self.assertEqual(status.status, 'unknown')
        self.assertEqual(status.finished_at, '')

    def test_get_import_status_raises_on_empty_asset_id(self):
        """An empty asset_id raises before touching the C++ side."""
        with self.assertToolRaisesRuntimeError() as context:
            FabImportTools.get_fab_import_status('')
        self.assertIn('ValueError', str(context.exception))
