# Copyright XUSJTUER. All Rights Reserved.

import json
import urllib.error
import urllib.parse
import urllib.request

import unreal

import toolset_registry


@unreal.ustruct()
class FabCatalogListing(unreal.StructBase):
    """One Fab marketplace listing from a catalog search page."""
    uid = unreal.uproperty(str)
    title = unreal.uproperty(str)
    category = unreal.uproperty(str)
    seller_name = unreal.uproperty(str)
    price = unreal.uproperty(float, meta={'ToolTip': 'USD; 0.0 for free listings.'})
    is_free = unreal.uproperty(bool)
    is_discounted = unreal.uproperty(bool)
    listing_type = unreal.uproperty(str, meta={'ToolTip': "e.g. '3d-model', 'material', 'blueprint'."})
    rating_average = unreal.uproperty(float)
    rating_total = unreal.uproperty(int)
    tags = unreal.uproperty(unreal.Array(str))
    asset_formats = unreal.uproperty(unreal.Array(str), meta={'ToolTip': "Format codes available for this listing, e.g. ['unreal-engine', 'fbx']."})
    thumbnail_url = unreal.uproperty(str, meta={'ToolTip': 'URL of the largest preview image of the first thumbnail set; empty when none.'})


@unreal.ustruct()
class FabListingDetail(unreal.StructBase):
    """Public detail page data of one Fab listing (description, pricing, licenses)."""
    listing_uid = unreal.uproperty(str)
    title = unreal.uproperty(str)
    description = unreal.uproperty(str, meta={'ToolTip': 'HTML description as served by fab.com.'})
    product_type = unreal.uproperty(str)
    listing_type = unreal.uproperty(str)
    category = unreal.uproperty(str)
    seller_name = unreal.uproperty(str)
    price = unreal.uproperty(float, meta={'ToolTip': 'List price; 0.0 when absent. Note price 0.0 does not imply is_free — some free assets are claim-based.'})
    currency_code = unreal.uproperty(str)
    rating_average = unreal.uproperty(float)
    rating_total = unreal.uproperty(int)
    tags = unreal.uproperty(unreal.Array(str))
    asset_formats = unreal.uproperty(unreal.Array(str))
    license_names = unreal.uproperty(unreal.Array(str), meta={'ToolTip': "License names, e.g. ['Personal', 'Extended']."})
    discounted_price = unreal.uproperty(float, meta={'ToolTip': 'Current price after the platform discount; only meaningful when discount_percentage > 0.'})
    discount_percentage = unreal.uproperty(float, meta={'ToolTip': 'Discount percent: 0 = no discount, 100 = free for a limited time (rotating offer that expires back to list price).'})
    discount_end_date = unreal.uproperty(str, meta={'ToolTip': "ISO 8601 timestamp when the discount expires; empty when there is no discount."})
    created_at = unreal.uproperty(str, meta={'ToolTip': 'ISO 8601 timestamp.'})
    published_at = unreal.uproperty(str, meta={'ToolTip': 'ISO 8601 timestamp.'})


@unreal.ustruct()
class FabCatalogSearchResult(unreal.StructBase):
    """One page of Fab catalog search results."""
    query = unreal.uproperty(str)
    entries = unreal.uproperty(unreal.Array(FabCatalogListing))
    next_cursor = unreal.uproperty(str, meta={'ToolTip': 'Cursor for the next page; empty when there are no more results.'})


@unreal.ustruct()
class FabListingFormatsSummary(unreal.StructBase):
    """Format availability of one listing in a batch check."""
    listing_uid = unreal.uproperty(str)
    asset_formats = unreal.uproperty(unreal.Array(str), meta={'ToolTip': 'Format codes; empty when not found.'})
    found = unreal.uproperty(bool, meta={'ToolTip': 'False when the listing is unreachable (404: nonexistent or delisted).'})


@unreal.uclass()
class FabCatalogTools(unreal.ToolsetDefinition):
    """Searches the public Fab marketplace catalog via the fab.com listing
    search API. Free-text search, sort order and cursor pagination over
    publicly visible listings; read-only HTTP, no authentication."""

    @staticmethod
    def _request_json(url: str) -> dict:
        """Fetches one anonymous fab.com JSON URL with the catalog UA header."""
        request = urllib.request.Request(url, headers={
            'Accept': 'application/json',
            # Anonymous requests carrying the default Python User-Agent get 403.
            'User-Agent': 'FabToolset (Unreal Editor)',
        })
        try:
            with urllib.request.urlopen(request, timeout=30.0) as response:
                return json.loads(response.read())
        except (urllib.error.URLError, json.JSONDecodeError) as error:
            raise RuntimeError(f'Fab catalog request failed: {error}')

    @staticmethod
    def _request_json_or_404(url: str):
        """Fetches one anonymous fab.com JSON URL; returns None on HTTP 404,
        raises on any other failure."""
        request = urllib.request.Request(url, headers={
            'Accept': 'application/json',
            'User-Agent': 'FabToolset (Unreal Editor)',
        })
        try:
            with urllib.request.urlopen(request, timeout=30.0) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise RuntimeError(f'Fab catalog request failed: {error}')
        except (urllib.error.URLError, json.JSONDecodeError) as error:
            raise RuntimeError(f'Fab catalog request failed: {error}')

    @staticmethod
    def _to_listing(entry: dict) -> FabCatalogListing:
        """Maps one raw API listing onto FabCatalogListing."""
        price = entry.get('startingPrice') or {}
        rating = entry.get('ratings') or {}
        category = entry.get('category') or {}
        user = entry.get('user') or {}
        listing = FabCatalogListing()
        listing.uid = entry.get('uid', '')
        listing.title = entry.get('title', '')
        listing.category = category.get('name', '')
        listing.seller_name = user.get('sellerName', '')
        listing.price = price.get('price', 0.0)
        listing.is_free = bool(entry.get('isFree'))
        listing.is_discounted = bool(entry.get('isDiscounted'))
        listing.listing_type = entry.get('listingType', '')
        listing.rating_average = rating.get('averageRating', 0.0)
        listing.rating_total = rating.get('total', 0)
        listing.tags = [tag.get('name', '') for tag in entry.get('tags') or []]
        listing.asset_formats = [
            ((fmt.get('assetFormatType') or {}).get('code', ''))
            for fmt in entry.get('assetFormats') or []]
        listing.thumbnail_url = FabCatalogTools._largest_thumbnail_url(entry.get('thumbnails'))
        return listing

    @staticmethod
    def _largest_thumbnail_url(thumbnails) -> str:
        """Returns the widest image URL of the first thumbnail set, or ''."""
        for thumb in thumbnails or []:
            images = [img for img in (thumb.get('images') or []) if img.get('url')]
            if images:
                return max(images, key=lambda img: img.get('width') or 0)['url']
        return ''

    @toolset_registry.tool_call
    @staticmethod
    def search_fab_catalog(query: str = '', sort_by: str = '-relevance', cursor: str = '', is_free: bool = False, categories: list[str] = []) -> FabCatalogSearchResult:
        """Searches public Fab marketplace listings, one page per call.

        Args:
            query: Free-text search terms; empty browses the full catalog.
            sort_by: Sort order: '-relevance' (default), 'price', '-price', '-ratingAverage' or '-publishedAt'.
            cursor: Pagination cursor from a previous call's next_cursor; empty for the first page.
            is_free: When true, only returns listings obtainable for free (price 0; includes claim-based ones whose is_free flag is false).
            categories: Category slugs to filter by, e.g. ['furniture-fixtures']. Slugs join into one comma-separated parameter; verified slugs include environments, nature, objects-decor, furniture-fixtures, buildings-architecture.

        Returns:
            One page: up to 24 entries plus next_cursor for the following page.
        """
        for slug in categories:
            if not slug:
                raise ValueError('categories must not contain empty strings.')
        params = {'q': query, 'sort_by': sort_by}
        if cursor:
            params['cursor'] = cursor
        if is_free:
            params['is_free'] = 'true'
        if categories:
            params['categories'] = ','.join(categories)
        payload = FabCatalogTools._request_json(
            'https://www.fab.com/i/listings/search?' + urllib.parse.urlencode(params))
        result = FabCatalogSearchResult()
        result.query = query
        result.entries = [FabCatalogTools._to_listing(entry) for entry in payload.get('results', [])]
        result.next_cursor = (payload.get('cursors') or {}).get('next') or ''
        return result

    @staticmethod
    def _to_detail(entry: dict) -> FabListingDetail:
        """Maps one raw listing detail payload onto FabListingDetail."""
        price = entry.get('startingPrice') or {}
        rating = entry.get('ratings') or {}
        category = entry.get('category') or {}
        user = entry.get('user') or {}
        detail = FabListingDetail()
        detail.listing_uid = entry.get('uid', '')
        detail.title = entry.get('title', '')
        detail.description = entry.get('description', '')
        detail.product_type = entry.get('productType', '')
        detail.listing_type = entry.get('listingType', '')
        detail.category = category.get('name', '')
        detail.seller_name = user.get('sellerName', '')
        detail.price = price.get('price', 0.0)
        detail.currency_code = price.get('currencyCode', '')
        detail.rating_average = rating.get('averageRating', 0.0)
        detail.rating_total = rating.get('total', 0)
        detail.tags = [tag.get('name', '') for tag in entry.get('tags') or []]
        detail.asset_formats = [
            ((fmt.get('assetFormatType') or {}).get('code', ''))
            for fmt in entry.get('assetFormats') or []]
        detail.license_names = [lic.get('name', '') for lic in entry.get('licenses') or []]
        # Discount numbers live in the nested priceTier (raw payload: all six
        # discount keys under startingPrice.priceTier.*, null when no discount);
        # the search page carries only the isDiscounted/hasEffectiveDiscounts flags.
        price_tier = price.get('priceTier') or {}
        detail.discounted_price = price_tier.get('discountedPrice') or 0.0
        detail.discount_percentage = price_tier.get('effectiveDiscountPercentage') or 0.0
        detail.discount_end_date = price_tier.get('discountEndDate') or ''
        detail.created_at = entry.get('createdAt', '')
        detail.published_at = entry.get('publishedAt', '')
        return detail

    @toolset_registry.tool_call
    @staticmethod
    def get_fab_listing_detail(listing_uid: str) -> FabListingDetail:
        """Returns the public detail page data of one listing: HTML description,
        pricing with currency, licenses, tags and available asset formats.

        Args:
            listing_uid: Listing uid from search_fab_catalog.

        Returns:
            The listing detail. Prices are served in the seller-configured
            currency (currency_code), not necessarily USD.
        """
        if not listing_uid:
            raise ValueError('listing_uid must not be empty.')
        payload = FabCatalogTools._request_json(f'https://www.fab.com/i/listings/{listing_uid}')
        return FabCatalogTools._to_detail(payload)

    @toolset_registry.tool_call
    @staticmethod
    def get_fab_listings_formats(listing_uids: list[str]) -> list[FabListingFormatsSummary]:
        """Checks format availability for a batch of listings in one call;
        the per-listing alternative to calling get_fab_listing_detail N times
        when screening candidates.

        Args:
            listing_uids: Listing uids to check; up to 50 per call.

        Returns:
            One summary per uid, in input order. found is False when the
            listing is unreachable (404: nonexistent or delisted); its
            asset_formats is then empty. A 404 here does not imply the
            listing has no formats — unreachable and formatless look the
            same on the public detail endpoint for anonymous callers.
        """
        if not listing_uids:
            raise ValueError('listing_uids must not be empty.')
        if len(listing_uids) > 50:
            raise ValueError('listing_uids supports up to 50 uids per call.')
        for uid in listing_uids:
            if not uid:
                raise ValueError('listing_uids must not contain empty strings.')
        summaries = []
        for uid in listing_uids:
            payload = FabCatalogTools._request_json_or_404(
                f'https://www.fab.com/i/listings/{uid}')
            summary = FabListingFormatsSummary()
            summary.listing_uid = uid
            if payload is None:
                summary.asset_formats = []
                summary.found = False
            else:
                summary.asset_formats = [
                    ((fmt.get('assetFormatType') or {}).get('code', ''))
                    for fmt in payload.get('assetFormats') or []]
                summary.found = True
            summaries.append(summary)
        return summaries
