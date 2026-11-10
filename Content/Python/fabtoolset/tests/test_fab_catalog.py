# Copyright XUSJTUER. All Rights Reserved.
"""Tests for FabCatalogTools."""

import io
import json
import unittest.mock
import urllib.error

import unreal

from fabtoolset.toolsets.fab_catalog import (
    FabCatalogListing,
    FabCatalogSearchResult,
    FabCatalogTools,
    FabListingDetail,
    FabListingFormatsSummary,
)
from toolset_registry.tests.toolset_testcase import ToolCallTestCase

FAB_CATALOG_TOOLSET_NAME = f'{FabCatalogTools.__module__}.{FabCatalogTools.__name__}'

RAW_LISTING = {
    'uid': 'd62376d5-c183-424b-964d-6c3d6a8a0f70',
    'title': 'Modern Minimalist Chair Collection Pack',
    'category': {'name': 'Furniture & Fixtures', 'path': 'furniture-fixtures'},
    'user': {'sellerName': 'Example Seller', 'isSeller': True},
    'startingPrice': {'price': 6.99, 'offerId': 'abc'},
    'isFree': False,
    'isDiscounted': True,
    'listingType': '3d-model',
    'ratings': {'averageRating': 5.0, 'total': 1},
    'tags': [{'name': 'Furniture', 'slug': 'furniture'}, {'name': 'Lowpoly', 'slug': 'lowpoly'}],
    'assetFormats': [
        {'assetFormatType': {'code': 'fbx'}, 'containsPack': False},
        {'assetFormatType': {'code': 'unreal-engine'}, 'containsPack': True},
    ],
    'thumbnails': [{'images': [
        {'url': 'https://media.fab.com/small.jpg', 'width': 144, 'height': 81},
        {'url': 'https://media.fab.com/large.jpg', 'width': 896, 'height': 504},
    ]}],
}

RAW_DETAIL = {
    'uid': '6a955883-baaf-412c-a515-ffccb34b691a',
    'title': 'Free Pack - Stickman (Rigged)',
    'description': '<h4>Hello from PolyOne Studio!</h4>',
    'listingType': '3d-model',
    'productType': '3d-model',
    'category': {'name': 'Humans', 'path': 'characters-creatures/humans'},
    'user': {'sellerName': 'PolyOne Studio'},
    'startingPrice': {'price': 6.99, 'currencyCode': 'CNY', 'priceTier': {
        'price': 6.99, 'discountedPrice': None,
        'effectiveDiscountPercentage': None, 'discountEndDate': None}},
    'ratings': {'averageRating': 5.0, 'total': 3},
    'tags': [{'name': 'Polygon'}, {'name': 'Base'}],
    'assetFormats': [{'assetFormatType': {'code': 'fbx'}}],
    'licenses': [{'name': 'Personal', 'offerId': 'e29fe12e2b67412185b244bcf5340618'}],
    'createdAt': '2022-12-07T11:29:39Z',
    'publishedAt': '2022-12-15T00:00:00Z',
}

# Limited-time free shape: discountedPrice 0 + effectiveDiscountPercentage 100
# inside the nested priceTier (discount keys are null when no discount runs).
RAW_DETAIL_LIMITED = dict(RAW_DETAIL, startingPrice={'price': 29.99, 'priceTier': {
    'price': 29.99, 'discountedPrice': 0.0,
    'effectiveDiscountPercentage': 100.0,
    'discountEndDate': '2026-11-17T00:00:00Z'}})


class FabCatalogToolsTestCase(ToolCallTestCase):
    """Test case that registers FabCatalogTools for the duration of a test run,
    preserving any production registration (see FabLocalLibraryToolsTestCase)."""

    _was_registered = False

    @classmethod
    def setUpClass(cls):
        cls._was_registered = unreal.ToolsetRegistry.is_toolset_class_registered(
            FabCatalogTools)
        if not cls._was_registered:
            unreal.ToolsetRegistry.register_toolset_class(FabCatalogTools)

    @classmethod
    def tearDownClass(cls):
        if not cls._was_registered:
            unreal.ToolsetRegistry.unregister_toolset_class(FabCatalogTools)


class _FakeResponse:
    """Minimal urlopen() stand-in: context manager returning fixed bytes."""

    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TestFabCatalogTools(FabCatalogToolsTestCase):
    """Tests for FabCatalogTools (fab.com listing search). Network access is
    mocked; the live endpoint is exercised manually, not in tests."""

    def test_toolset_schema(self):
        """Schema carries the class docstring and the three catalog tools."""
        registry = unreal.ToolsetRegistry
        schema = json.loads(registry.get_toolset_json_schema(FabCatalogTools))
        self.assertEqual(schema['name'], FAB_CATALOG_TOOLSET_NAME)
        self.assertEqual(schema['version'], '1.0')
        tool_names = {tool['name'] for tool in schema['tools']}
        self.assertEqual(tool_names, {
            f'{FAB_CATALOG_TOOLSET_NAME}.search_fab_catalog',
            f'{FAB_CATALOG_TOOLSET_NAME}.get_fab_listing_detail',
            f'{FAB_CATALOG_TOOLSET_NAME}.get_fab_listings_formats',
        })

    def test_search_maps_listing_fields(self):
        """Raw API fields land on the documented FabCatalogListing fields."""
        page = {'results': [RAW_LISTING], 'cursors': {'next': 'bz0yNA==', 'previous': None}}
        with unittest.mock.patch(
                'fabtoolset.toolsets.fab_catalog.urllib.request.urlopen',
                return_value=_FakeResponse(json.dumps(page).encode('utf-8'))):
            result = FabCatalogTools.search_fab_catalog('chair')
        self.assertIsInstance(result, FabCatalogSearchResult)
        self.assertEqual(result.query, 'chair')
        self.assertEqual(len(result.entries), 1)
        listing = result.entries[0]
        self.assertIsInstance(listing, FabCatalogListing)
        self.assertEqual(listing.uid, RAW_LISTING['uid'])
        self.assertEqual(listing.title, RAW_LISTING['title'])
        self.assertEqual(listing.category, 'Furniture & Fixtures')
        self.assertEqual(listing.seller_name, 'Example Seller')
        # float properties are 32-bit in UE; compare with a delta, not places.
        self.assertAlmostEqual(listing.price, 6.99, delta=1e-5)
        self.assertFalse(listing.is_free)
        self.assertTrue(listing.is_discounted)
        self.assertEqual(listing.listing_type, '3d-model')
        self.assertAlmostEqual(listing.rating_average, 5.0, delta=1e-5)
        self.assertEqual(listing.rating_total, 1)
        self.assertEqual(list(listing.tags), ['Furniture', 'Lowpoly'])
        self.assertEqual(list(listing.asset_formats), ['fbx', 'unreal-engine'])
        self.assertEqual(listing.thumbnail_url, 'https://media.fab.com/large.jpg')
        self.assertEqual(result.next_cursor, 'bz0yNA==')

    def test_search_url_carries_query_sort_and_cursor(self):
        """q, sort_by and cursor end up as query parameters of the request URL."""
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured['url'] = request.full_url
            return _FakeResponse(b'{"results": [], "cursors": {}}')

        with unittest.mock.patch(
                'fabtoolset.toolsets.fab_catalog.urllib.request.urlopen',
                side_effect=fake_urlopen):
            FabCatalogTools.search_fab_catalog('chair', sort_by='price', cursor='bz0yNA==')
        self.assertIn('q=chair', captured['url'])
        self.assertIn('sort_by=price', captured['url'])
        self.assertIn('cursor=bz0yNA%3D%3D', captured['url'])

    def test_search_first_page_omits_cursor_param(self):
        """An empty cursor leaves the cursor parameter off the request URL."""
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured['url'] = request.full_url
            return _FakeResponse(b'{"results": [], "cursors": {}}')

        with unittest.mock.patch(
                'fabtoolset.toolsets.fab_catalog.urllib.request.urlopen',
                side_effect=fake_urlopen):
            result = FabCatalogTools.search_fab_catalog('chair')
        self.assertNotIn('cursor=', captured['url'])
        self.assertNotIn('is_free=', captured['url'])
        self.assertIsInstance(result, FabCatalogSearchResult)
        self.assertEqual(result.next_cursor, '')

    def test_search_url_carries_is_free_filter(self):
        """is_free=True adds the backend's is_free=true filter parameter."""
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured['url'] = request.full_url
            return _FakeResponse(b'{"results": [], "cursors": {}}')

        with unittest.mock.patch(
                'fabtoolset.toolsets.fab_catalog.urllib.request.urlopen',
                side_effect=fake_urlopen):
            FabCatalogTools.search_fab_catalog('chair', is_free=True)
        self.assertIn('is_free=true', captured['url'])

    def test_search_url_carries_categories_filter(self):
        """Category slugs join into one comma-separated categories parameter."""
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured['url'] = request.full_url
            return _FakeResponse(b'{"results": [], "cursors": {}}')

        with unittest.mock.patch(
                'fabtoolset.toolsets.fab_catalog.urllib.request.urlopen',
                side_effect=fake_urlopen):
            FabCatalogTools.search_fab_catalog('chair', categories=['furniture-fixtures'])
        self.assertIn('categories=furniture-fixtures', captured['url'])

    def test_search_url_joins_multiple_categories(self):
        """Multiple slugs land in one comma-joined parameter."""
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured['url'] = request.full_url
            return _FakeResponse(b'{"results": [], "cursors": {}}')

        with unittest.mock.patch(
                'fabtoolset.toolsets.fab_catalog.urllib.request.urlopen',
                side_effect=fake_urlopen):
            FabCatalogTools.search_fab_catalog(categories=['environments', 'nature'])
        self.assertIn('categories=environments%2Cnature', captured['url'])

    def test_search_empty_categories_omit_param(self):
        """An empty categories list leaves the parameter off the request URL."""
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured['url'] = request.full_url
            return _FakeResponse(b'{"results": [], "cursors": {}}')

        with unittest.mock.patch(
                'fabtoolset.toolsets.fab_catalog.urllib.request.urlopen',
                side_effect=fake_urlopen):
            FabCatalogTools.search_fab_catalog('chair')
        self.assertNotIn('categories=', captured['url'])

    def test_search_raises_on_empty_category_slug(self):
        """An empty string inside categories raises before any network activity."""
        with self.assertToolRaisesRuntimeError() as context:
            FabCatalogTools.search_fab_catalog(categories=['environments', ''])
        self.assertIn('ValueError', str(context.exception))

    def test_get_detail_maps_fields(self):
        """Raw detail fields land on the documented FabListingDetail fields."""
        with unittest.mock.patch(
                'fabtoolset.toolsets.fab_catalog.urllib.request.urlopen',
                return_value=_FakeResponse(json.dumps(RAW_DETAIL).encode('utf-8'))):
            detail = FabCatalogTools.get_fab_listing_detail('detail-uid')
        self.assertIsInstance(detail, FabListingDetail)
        self.assertEqual(detail.listing_uid, RAW_DETAIL['uid'])
        self.assertEqual(detail.title, RAW_DETAIL['title'])
        self.assertEqual(detail.description, RAW_DETAIL['description'])
        self.assertEqual(detail.product_type, '3d-model')
        self.assertEqual(detail.listing_type, '3d-model')
        self.assertEqual(detail.category, 'Humans')
        self.assertEqual(detail.seller_name, 'PolyOne Studio')
        self.assertAlmostEqual(detail.price, 6.99, delta=1e-5)
        self.assertEqual(detail.currency_code, 'CNY')
        self.assertAlmostEqual(detail.rating_average, 5.0, delta=1e-5)
        self.assertEqual(detail.rating_total, 3)
        self.assertEqual(list(detail.tags), ['Polygon', 'Base'])
        self.assertEqual(list(detail.asset_formats), ['fbx'])
        self.assertEqual(list(detail.license_names), ['Personal'])
        # no discount runs: nested priceTier discount keys are all null
        self.assertAlmostEqual(detail.discounted_price, 0.0, delta=1e-5)
        self.assertAlmostEqual(detail.discount_percentage, 0.0, delta=1e-5)
        self.assertEqual(detail.discount_end_date, '')
        self.assertEqual(detail.created_at, '2022-12-07T11:29:39Z')

    def test_get_detail_maps_limited_time_free(self):
        """A limited-time-free listing maps discount fields from the nested
        priceTier: discounted price 0 at 100 percent off until the end date."""
        with unittest.mock.patch(
                'fabtoolset.toolsets.fab_catalog.urllib.request.urlopen',
                return_value=_FakeResponse(json.dumps(RAW_DETAIL_LIMITED).encode('utf-8'))):
            detail = FabCatalogTools.get_fab_listing_detail('limited-uid')
        self.assertAlmostEqual(detail.price, 29.99, delta=1e-5)
        self.assertAlmostEqual(detail.discounted_price, 0.0, delta=1e-5)
        self.assertAlmostEqual(detail.discount_percentage, 100.0, delta=1e-5)
        self.assertEqual(detail.discount_end_date, '2026-11-17T00:00:00Z')
        self.assertEqual(detail.published_at, '2022-12-15T00:00:00Z')

    def test_get_detail_request_url(self):
        """listing_uid lands in the detail endpoint path."""
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured['url'] = request.full_url
            return _FakeResponse(json.dumps(RAW_DETAIL).encode('utf-8'))

        with unittest.mock.patch(
                'fabtoolset.toolsets.fab_catalog.urllib.request.urlopen',
                side_effect=fake_urlopen):
            FabCatalogTools.get_fab_listing_detail('6a955883-baaf')
        self.assertEqual(
            captured['url'], 'https://www.fab.com/i/listings/6a955883-baaf')

    def test_get_detail_raises_on_empty_listing_uid(self):
        """An empty listing_uid raises before any network activity."""
        with self.assertToolRaisesRuntimeError() as context:
            FabCatalogTools.get_fab_listing_detail('')
        self.assertIn('ValueError', str(context.exception))

    def test_search_raises_on_http_error(self):
        """A failing HTTP request surfaces as a RuntimeError."""
        error = urllib.error.URLError('connection refused')
        with unittest.mock.patch(
                'fabtoolset.toolsets.fab_catalog.urllib.request.urlopen',
                side_effect=error):
            with self.assertToolRaisesRuntimeError() as context:
                FabCatalogTools.search_fab_catalog('chair')
        self.assertIn('Fab catalog request failed', str(context.exception))

    def test_search_raises_on_invalid_json(self):
        """Non-JSON response bodies surface as a RuntimeError."""
        with unittest.mock.patch(
                'fabtoolset.toolsets.fab_catalog.urllib.request.urlopen',
                return_value=_FakeResponse(b'<html>not json</html>')):
            with self.assertToolRaisesRuntimeError() as context:
                FabCatalogTools.search_fab_catalog('chair')
        self.assertIn('Fab catalog request failed', str(context.exception))

    def test_batch_formats_maps_entries_in_input_order(self):
        """Each uid gets a summary in input order with its format codes."""
        first = dict(RAW_DETAIL)
        second = {'uid': 'other-uid', 'assetFormats': [
            {'assetFormatType': {'code': 'fbx'}},
            {'assetFormatType': {'code': 'unity'}},
        ]}
        bodies = [json.dumps(first).encode('utf-8'), json.dumps(second).encode('utf-8')]
        with unittest.mock.patch(
                'fabtoolset.toolsets.fab_catalog.urllib.request.urlopen',
                side_effect=[_FakeResponse(body) for body in bodies]):
            summaries = FabCatalogTools.get_fab_listings_formats(
                [RAW_DETAIL['uid'], 'other-uid'])
        self.assertEqual(len(summaries), 2)
        first_summary, second_summary = summaries
        self.assertIsInstance(first_summary, FabListingFormatsSummary)
        self.assertEqual(first_summary.listing_uid, RAW_DETAIL['uid'])
        self.assertTrue(first_summary.found)
        self.assertEqual(list(first_summary.asset_formats), ['fbx'])
        self.assertEqual(second_summary.listing_uid, 'other-uid')
        self.assertTrue(second_summary.found)
        self.assertEqual(list(second_summary.asset_formats), ['fbx', 'unity'])

    def test_batch_formats_marks_404_as_not_found(self):
        """A 404 for one uid marks only that entry not found, others proceed."""
        not_found = urllib.error.HTTPError(
            'https://www.fab.com/i/listings/gone', 404, 'Not Found', None,
            io.BytesIO(b''))
        with unittest.mock.patch(
                'fabtoolset.toolsets.fab_catalog.urllib.request.urlopen',
                side_effect=[not_found,
                             _FakeResponse(json.dumps(RAW_DETAIL).encode('utf-8'))]):
            summaries = FabCatalogTools.get_fab_listings_formats(['gone', RAW_DETAIL['uid']])
        self.assertFalse(summaries[0].found)
        self.assertEqual(list(summaries[0].asset_formats), [])
        self.assertTrue(summaries[1].found)
        self.assertEqual(summaries[1].listing_uid, RAW_DETAIL['uid'])

    def test_batch_formats_request_urls(self):
        """Each summary request hits that uid's public detail endpoint."""
        captured = []

        def fake_urlopen(request, timeout=None):
            captured.append(request.full_url)
            return _FakeResponse(json.dumps(RAW_DETAIL).encode('utf-8'))

        with unittest.mock.patch(
                'fabtoolset.toolsets.fab_catalog.urllib.request.urlopen',
                side_effect=fake_urlopen):
            FabCatalogTools.get_fab_listings_formats(['uid-a', 'uid-b'])
        self.assertEqual(captured, [
            'https://www.fab.com/i/listings/uid-a',
            'https://www.fab.com/i/listings/uid-b',
        ])

    def test_batch_formats_raises_on_empty_uid_list(self):
        """An empty uid list raises before any network activity."""
        with self.assertToolRaisesRuntimeError() as context:
            FabCatalogTools.get_fab_listings_formats([])
        self.assertIn('ValueError', str(context.exception))

    def test_batch_formats_raises_on_over_50_uids(self):
        """More than 50 uids raises before any network activity."""
        with self.assertToolRaisesRuntimeError() as context:
            FabCatalogTools.get_fab_listings_formats([f'uid-{n}' for n in range(51)])
        self.assertIn('50', str(context.exception))

    def test_batch_formats_raises_on_empty_uid_in_list(self):
        """An empty string inside the list raises before any network activity."""
        with self.assertToolRaisesRuntimeError() as context:
            FabCatalogTools.get_fab_listings_formats(['uid-a', ''])
        self.assertIn('ValueError', str(context.exception))
