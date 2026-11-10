# Copyright XUSJTUER. All Rights Reserved.

import urllib.parse

import unreal

import toolset_registry

from fabtoolset.toolsets.fab_import import FabDownloadInfo, FabImportTools


@unreal.ustruct()
class FabLibraryEntry(unreal.StructBase):
    """One owned asset from the signed-in user's Fab library."""
    library_asset_uid = unreal.uproperty(str, meta={'ToolTip': 'Library asset uid; pass to get_my_library_formats/get_my_library_download_info.'})
    listing_uid = unreal.uproperty(str, meta={'ToolTip': 'Public listing uid; pass to the FabImportTools chain (get_fab_listing_format, add_fab_listing_to_project).'})
    title = unreal.uproperty(str)
    publisher_name = unreal.uproperty(str)
    product_type = unreal.uproperty(str, meta={'ToolTip': "e.g. '3d-model', 'tool-and-plugin', 'vfx'."})
    created_at = unreal.uproperty(str, meta={'ToolTip': 'ISO 8601 UTC timestamp of library acquisition.'})
    can_request_download_url = unreal.uproperty(bool)


@unreal.ustruct()
class FabLibrarySearchResult(unreal.StructBase):
    """One page of the signed-in user's Fab library."""
    query = unreal.uproperty(str)
    product_type = unreal.uproperty(str)
    entries = unreal.uproperty(unreal.Array(FabLibraryEntry))
    next_cursor = unreal.uproperty(str, meta={'ToolTip': 'Cursor for the next page; empty when there are no more results.'})


@unreal.ustruct()
class FabOwnedFile(unreal.StructBase):
    """One downloadable file inside an owned asset's format."""
    file_uid = unreal.uproperty(str, meta={'ToolTip': 'Pass to get_my_library_download_info.'})
    name = unreal.uproperty(str)
    file_size_bytes = unreal.uproperty(int, meta={'ToolTip': 'File size in bytes; 0 when the API reports no size.'})


@unreal.ustruct()
class FabOwnedFormat(unreal.StructBase):
    """One asset format of an owned asset, with its downloadable files."""
    format_code = unreal.uproperty(str, meta={'ToolTip': "e.g. 'unreal-engine', 'unity', 'glb'."})
    files = unreal.uproperty(unreal.Array(FabOwnedFile))


@unreal.ustruct()
class FabUserIdentity(unreal.StructBase):
    """Identity of the signed-in Fab user."""
    display_name = unreal.uproperty(str)
    uid = unreal.uproperty(str)
    epic_id = unreal.uproperty(str)
    seller_name = unreal.uproperty(str, meta={'ToolTip': "Empty when the account is not a seller."})
    is_seller = unreal.uproperty(bool)


@unreal.ustruct()
class FabOwnedAssetDetail(unreal.StructBase):
    """Detail page data of one owned asset; the only detail channel for
    delisted listings the public catalog no longer serves."""
    library_asset_uid = unreal.uproperty(str)
    status = unreal.uproperty(str, meta={'ToolTip': "Library asset status, e.g. 'approved'."})
    can_request_download_url = unreal.uproperty(bool)
    acquired_at = unreal.uproperty(str, meta={'ToolTip': 'ISO 8601 UTC timestamp of library acquisition.'})
    listing_uid = unreal.uproperty(str)
    title = unreal.uproperty(str)
    description = unreal.uproperty(str, meta={'ToolTip': 'HTML description as served by fab.com.'})
    product_type = unreal.uproperty(str)
    listing_type = unreal.uproperty(str)
    category = unreal.uproperty(str)
    seller_name = unreal.uproperty(str)
    rating_average = unreal.uproperty(float)
    review_count = unreal.uproperty(int)
    tags = unreal.uproperty(unreal.Array(str))
    asset_formats = unreal.uproperty(unreal.Array(str))
    license_names = unreal.uproperty(unreal.Array(str))


@unreal.uclass()
class FabLibraryTools(unreal.ToolsetDefinition):
    """Reads the signed-in user's Fab library (owned assets) via the fab.com
    authenticated library API. Browses owned assets with filters and cursor
    pagination, and resolves their file formats and signed download URLs for
    the Add to Project import."""

    @staticmethod
    def _to_entry(entry: dict) -> FabLibraryEntry:
        """Maps one raw library entry onto FabLibraryEntry."""
        listing = entry.get('listing') or {}
        publisher = listing.get('publisher') or {}
        item = FabLibraryEntry()
        item.library_asset_uid = entry.get('uid', '')
        item.listing_uid = listing.get('uid', '')
        item.title = listing.get('title', '')
        item.publisher_name = publisher.get('sellerName', '')
        item.product_type = listing.get('productType', '')
        item.created_at = entry.get('createdAt', '')
        item.can_request_download_url = bool(entry.get('canRequestDownloadUrl'))
        return item

    @toolset_registry.tool_call
    @staticmethod
    def search_my_library(query: str = '', product_type: str = '', sort_by: str = '-createdAt', cursor: str = '') -> FabLibrarySearchResult:
        """Searches the signed-in user's Fab library (owned assets), one page per call.

        Args:
            query: Free-text filter on owned assets; empty returns the library unfiltered.
            product_type: Filter by product type, e.g. '3d-model'; empty for all types.
            sort_by: Sort order: '-createdAt' (default) or 'title'.
            cursor: Pagination cursor from a previous call's next_cursor; empty for the first page.

        Returns:
            One page: up to 24 entries plus next_cursor for the following page.
        """
        params = {'sort_by': sort_by}
        if query:
            params['q'] = query
        if product_type:
            params['productTypes'] = product_type
        if cursor:
            params['cursor'] = cursor
        opener = FabImportTools._authenticated_opener()
        payload = FabImportTools._get_json(
            opener, 'https://www.fab.com/i/library/search?' + urllib.parse.urlencode(params))
        result = FabLibrarySearchResult()
        result.query = query
        result.product_type = product_type
        result.entries = [FabLibraryTools._to_entry(entry) for entry in payload.get('results', [])]
        result.next_cursor = (payload.get('cursors') or {}).get('next') or ''
        return result

    @toolset_registry.tool_call
    @staticmethod
    def get_my_library_formats(library_asset_uid: str) -> list[FabOwnedFormat]:
        """Returns the asset formats and downloadable files of an owned asset.

        Args:
            library_asset_uid: Library asset uid from search_my_library.

        Returns:
            Formats with their file uids; pass a file uid to get_my_library_download_info.
        """
        if not library_asset_uid:
            raise ValueError('library_asset_uid must not be empty.')
        opener = FabImportTools._authenticated_opener()
        payload = FabImportTools._get_json(
            opener, f'https://www.fab.com/i/library/assets/{library_asset_uid}/asset-formats')
        formats = []
        for entry in payload:
            owned_format = FabOwnedFormat()
            owned_format.format_code = (entry.get('assetFormatType') or {}).get('code', '')
            files = []
            for raw_file in entry.get('files') or []:
                owned_file = FabOwnedFile()
                owned_file.file_uid = raw_file.get('uid', '')
                owned_file.name = raw_file.get('name', '')
                owned_file.file_size_bytes = raw_file.get('fileSize') or 0
                files.append(owned_file)
            owned_format.files = files
            formats.append(owned_format)
        return formats

    @toolset_registry.tool_call
    @staticmethod
    def get_my_library_download_info(library_asset_uid: str, file_uid: str, format_code: str = 'unreal-engine', platform: str = 'Windows') -> FabDownloadInfo:
        """Returns the signed manifest URL and CDN base URLs for one file of an
        owned asset.

        Args:
            library_asset_uid: Library asset uid from search_my_library.
            file_uid: File uid from get_my_library_formats.
            format_code: Asset format code from get_my_library_formats, e.g. 'unreal-engine'.
            platform: Target platform, e.g. 'Windows'.

        Returns:
            Signed data: download_url expires within roughly one hour.
        """
        if not library_asset_uid:
            raise ValueError('library_asset_uid must not be empty.')
        if not file_uid:
            raise ValueError('file_uid must not be empty.')
        opener = FabImportTools._authenticated_opener()
        payload = FabImportTools._get_json(
            opener,
            f'https://www.fab.com/i/library/assets/{library_asset_uid}/asset-formats/{format_code}/files/{file_uid}/download-info?platform={platform}')
        entries = payload.get('downloadInfo') or []
        if not entries:
            raise RuntimeError(f'No download info available for file {file_uid}.')
        info = FabDownloadInfo()
        info.file_uid = file_uid
        info.download_url = entries[0].get('downloadUrl', '')
        info.distribution_point_base_urls = list(entries[0].get('distributionPointBaseUrls') or [])
        info.expires = entries[0].get('expires', '')
        return info

    @toolset_registry.tool_call
    @staticmethod
    def get_my_library_identity() -> FabUserIdentity:
        """Returns the identity of the signed-in Fab user.

        Returns:
            Display name, platform ids and seller flag. Also usable as a
            lightweight login-state check before the download chain.
        """
        opener = FabImportTools._authenticated_opener()
        payload = FabImportTools._get_json(opener, 'https://www.fab.com/i/users/me')
        identity = FabUserIdentity()
        identity.display_name = payload.get('displayName', '')
        identity.uid = payload.get('uid', '')
        identity.epic_id = payload.get('epicId', '')
        identity.seller_name = payload.get('sellerName', '')
        identity.is_seller = bool(payload.get('isSeller'))
        return identity

    @toolset_registry.tool_call
    @staticmethod
    def get_my_library_detail(library_asset_uid: str) -> FabOwnedAssetDetail:
        """Returns the detail page data of one owned asset: library status,
        capabilities and the listing's description, tags, licenses and formats.

        Args:
            library_asset_uid: Library asset uid from search_my_library.

        Returns:
            The owned asset detail. Serves delisted listings that
            get_fab_listing_detail can no longer reach.
        """
        if not library_asset_uid:
            raise ValueError('library_asset_uid must not be empty.')
        opener = FabImportTools._authenticated_opener()
        payload = FabImportTools._get_json(
            opener, f'https://www.fab.com/i/library/assets/{library_asset_uid}')
        listing = payload.get('listing') or {}
        category = listing.get('category') or {}
        user = listing.get('user') or {}
        capabilities = payload.get('capabilities') or {}
        detail = FabOwnedAssetDetail()
        detail.library_asset_uid = payload.get('uid', '')
        detail.status = payload.get('status', '')
        detail.can_request_download_url = bool(capabilities.get('requestDownloadUrl'))
        detail.acquired_at = payload.get('createdAt', '')
        detail.listing_uid = listing.get('uid', '')
        detail.title = listing.get('title', '')
        detail.description = listing.get('description', '')
        detail.product_type = listing.get('productType', '')
        detail.listing_type = listing.get('listingType', '')
        detail.category = category.get('name', '')
        detail.seller_name = user.get('sellerName', '')
        detail.rating_average = listing.get('averageRating', 0.0)
        detail.review_count = listing.get('reviewCount', 0)
        detail.tags = [tag.get('name', '') for tag in listing.get('tags') or []]
        detail.asset_formats = [
            ((fmt.get('assetFormatType') or {}).get('code', ''))
            for fmt in listing.get('assetFormats') or []]
        detail.license_names = [lic.get('name', '') for lic in listing.get('licenses') or []]
        return detail
