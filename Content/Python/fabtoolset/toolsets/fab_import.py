# Copyright XUSJTUER. All Rights Reserved.

import datetime
import http.cookiejar
import json
import urllib.error
import urllib.request

import unreal

import toolset_registry


@unreal.ustruct()
class FabFileVersion(unreal.StructBase):
    """One downloadable file version of a Fab listing format."""
    version_uid = unreal.uproperty(str, meta={'ToolTip': 'File uid; pass to get_fab_download_info.'})
    name = unreal.uproperty(str)
    artifact_id = unreal.uproperty(str)
    file_type = unreal.uproperty(str, meta={'ToolTip': "e.g. 'source', 'converted'."})
    status = unreal.uproperty(str, meta={'ToolTip': "'ready' when downloadable."})
    engine_versions = unreal.uproperty(unreal.Array(str), meta={'ToolTip': "e.g. ['UE_5.8']."})
    target_platforms = unreal.uproperty(unreal.Array(str), meta={'ToolTip': "e.g. ['Windows']."})


@unreal.ustruct()
class FabDownloadInfo(unreal.StructBase):
    """Signed download data for one Fab listing file version."""
    file_uid = unreal.uproperty(str)
    download_url = unreal.uproperty(str, meta={'ToolTip': 'Signed manifest URL; expires within roughly one hour.'})
    distribution_point_base_urls = unreal.uproperty(unreal.Array(str), meta={'ToolTip': 'CDN base URLs the manifest references.'})
    expires = unreal.uproperty(str, meta={'ToolTip': 'ISO 8601 UTC timestamp of download_url expiry.'})


@unreal.ustruct()
class FabImportStatus(unreal.StructBase):
    """Tracked lifecycle state of one Fab import workflow in this editor session."""
    asset_id = unreal.uproperty(str)
    status = unreal.uproperty(str, meta={'ToolTip': "'pending' in flight, 'completed' succeeded, 'cancelled' cancelled or failed, 'unknown' not started in this session."})
    finished_at = unreal.uproperty(str, meta={'ToolTip': "RFC 3339 UTC timestamp of the terminal transition; empty while pending or unknown."})


@unreal.uclass()
class FabImportTools(unreal.ToolsetDefinition):
    """Bridges fab.com listing data into the Fab plugin's Add to Project import.
    Retrieves a listing's downloadable file versions and signed download URLs
    (authenticated via the Fab plugin's EOS tokens), and starts the same import
    workflow the Fab browser window triggers on its "Add to Project" button."""

    @staticmethod
    def _get_fab_tokens() -> tuple:
        """Reads the EOS access and refresh tokens from the Fab plugin."""
        return (
            unreal.FabToolsetLibrary.get_fab_auth_token(),
            unreal.FabToolsetLibrary.get_fab_refresh_token(),
        )

    @staticmethod
    def _authenticated_opener() -> urllib.request.OpenerDirector:
        """Builds an opener carrying a fab.com session cookie exchanged from the
        Fab plugin's EOS tokens. Raises when the user is not logged in."""
        access_token, refresh_token = FabImportTools._get_fab_tokens()
        if not access_token or not refresh_token:
            raise RuntimeError('Fab is not logged in; open the Fab browser window and sign in first.')
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        request = urllib.request.Request(
            'https://www.fab.com/p/authenticate',
            method='POST',
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'User-Agent': 'FabToolset (Unreal Editor)',
                'Authorization': 'Bearer ' + access_token,
            },
            data=json.dumps({'refreshToken': refresh_token}).encode(),
        )
        try:
            opener.open(request, timeout=15.0)
        except urllib.error.HTTPError as error:
            raise RuntimeError(f'Fab authentication failed (HTTP {error.code}); sign in via the Fab browser window.')
        return opener

    @staticmethod
    def _get_json(opener: urllib.request.OpenerDirector, url: str) -> dict:
        """Fetches one authenticated fab.com URL as a parsed JSON dict."""
        request = urllib.request.Request(url, headers={
            'Accept': 'application/json',
            'User-Agent': 'FabToolset (Unreal Editor)',
        })
        try:
            with opener.open(request, timeout=30.0) as response:
                return json.loads(response.read())
        except (urllib.error.URLError, json.JSONDecodeError) as error:
            raise RuntimeError(f'Fab request failed: {error}')

    @staticmethod
    def _post_json(opener: urllib.request.OpenerDirector, url: str, body: dict) -> dict:
        """POSTs a JSON body to one authenticated fab.com URL; returns the parsed
        response (empty dict when the body is empty). Carries the CSRF headers
        fab.com's backend requires on writes: Referer (Django referer checking)
        and X-CSRFToken from the fab_csrftoken/csrftoken session cookie."""
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'FabToolset (Unreal Editor)',
            'Referer': 'https://www.fab.com/',
        }
        for handler in opener.handlers:
            if isinstance(handler, urllib.request.HTTPCookieProcessor):
                jar = handler.cookiejar
                if jar is not None:
                    for cookie in jar:
                        if cookie.name in ('csrftoken', 'fab_csrftoken') and cookie.value:
                            headers['X-CSRFToken'] = cookie.value
                            break
        request = urllib.request.Request(
            url,
            method='POST',
            headers=headers,
            data=json.dumps(body).encode(),
        )
        try:
            with opener.open(request, timeout=30.0) as response:
                raw = response.read()
        except urllib.error.URLError as error:
            raise RuntimeError(f'Fab request failed: {error}')
        return json.loads(raw) if raw else {}

    @toolset_registry.tool_call
    @staticmethod
    def get_fab_listing_format(listing_uid: str, format_code: str = 'unreal-engine') -> list[FabFileVersion]:
        """Returns the downloadable file versions of a Fab listing format.

        Args:
            listing_uid: Listing uid from search_fab_catalog.
            format_code: Asset format code, e.g. 'unreal-engine', 'gltf', 'glb', 'fbx'.

        Returns:
            File versions with their uids, engine versions and target platforms.
            Unreal Engine listings carry engine_versions/target_platforms; the
            gltf/glb/fbx formats report plain files with uids only.
        """
        if not listing_uid:
            raise ValueError('listing_uid must not be empty.')
        if not format_code:
            raise ValueError('format_code must not be empty.')
        opener = FabImportTools._authenticated_opener()
        payload = FabImportTools._get_json(
            opener,
            f'https://www.fab.com/i/listings/{listing_uid}/asset-formats/{format_code}')
        # Unreal Engine listings expose "versions"; converted/plain formats
        # (gltf, glb, fbx, blender) expose "files" with the same uid semantics.
        entries = payload.get('versions') or payload.get('files') or []
        versions = []
        for entry in entries:
            version = FabFileVersion()
            version.version_uid = entry.get('uid', '')
            version.name = entry.get('name', '')
            version.artifact_id = entry.get('artifactId', '')
            version.file_type = entry.get('fileType', '')
            version.status = entry.get('status', '')
            version.engine_versions = list(entry.get('engineVersions') or [])
            version.target_platforms = list(entry.get('targetPlatforms') or [])
            versions.append(version)
        return versions

    @toolset_registry.tool_call
    @staticmethod
    def get_fab_download_info(listing_uid: str, file_uid: str, format_code: str = 'unreal-engine', platform: str = 'Windows') -> FabDownloadInfo:
        """Returns the signed manifest URL and CDN base URLs for one file version.

        Args:
            listing_uid: Listing uid from search_fab_catalog.
            file_uid: File version uid from get_fab_listing_format.
            format_code: Asset format code, e.g. 'unreal-engine'.
            platform: Target platform, e.g. 'Windows' (see FabFileVersion.target_platforms).

        Returns:
            Signed data: download_url expires within roughly one hour.
        """
        if not listing_uid:
            raise ValueError('listing_uid must not be empty.')
        if not file_uid:
            raise ValueError('file_uid must not be empty.')
        opener = FabImportTools._authenticated_opener()
        payload = FabImportTools._get_json(
            opener,
            f'https://www.fab.com/i/listings/{listing_uid}/asset-formats/{format_code}/files/{file_uid}/download-info?platform={platform}')
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
    def grant_fab_listing_to_library(listing_uid: str, offer_id: str) -> None:
        """Claims a free listing into the signed-in user's Fab library so the
        library chain can serve it. Required for claim-based free assets
        (price 0 with is_free false). The claim is asynchronous server-side:
        the asset enters the library as 'pending' and its download-info
        endpoint becomes usable once status reaches 'approved'.

        Args:
            listing_uid: Listing uid from search_fab_catalog.
            offer_id: Offer id from the listing's startingPrice.offer_id or
                get_fab_listing_detail's license entry.
        """
        if not listing_uid:
            raise ValueError('listing_uid must not be empty.')
        if not offer_id:
            raise ValueError('offer_id must not be empty.')
        opener = FabImportTools._authenticated_opener()
        FabImportTools._post_json(
            opener,
            f'https://www.fab.com/i/listings/{listing_uid}/add-to-library',
            {'offerId': offer_id})

    @staticmethod
    def _validate_not_expired(expires: str) -> None:
        """Raises when an ISO 8601 UTC timestamp is already past (local clock)."""
        if not expires:
            return
        try:
            expiry = datetime.datetime.fromisoformat(expires)
        except ValueError as error:
            raise ValueError(f'expires is not an ISO 8601 timestamp: {expires!r}') from error
        if expiry <= datetime.datetime.now(datetime.timezone.utc):
            raise ValueError(
                f'download_url expired at {expires}; fetch a fresh one via get_fab_download_info.')

    @toolset_registry.tool_call
    @staticmethod
    def add_fab_listing_to_project(download_url: str, asset_id: str, asset_name: str, asset_type: str,
                                   listing_type: str, asset_namespace: str = 'fab',
                                   distribution_point_base_urls: list[str] = [],
                                   is_quixel: bool = False, expires: str = '') -> None:
        """Starts the Fab plugin's Add to Project import for a listing; the same
        workflow as the Fab browser window's "Add to Project" button. Runs
        asynchronously: poll get_fab_import_status for the outcome.

        Args:
            download_url: Signed manifest URL from get_fab_download_info; must be used before its expires timestamp.
            asset_id: Listing uid.
            asset_name: Listing title.
            asset_type: Asset format code, e.g. 'unreal-engine'.
            listing_type: Listing type from search_fab_catalog's listing_type.
            asset_namespace: Asset namespace; the Fab frontend sends 'fab'.
            distribution_point_base_urls: CDN base URLs from get_fab_download_info.
            is_quixel: Whether the listing is a Quixel asset.
            expires: ISO 8601 expiry of download_url, from get_fab_download_info's expires; when given, raises instead of starting the import with a stale URL.
        """
        if not download_url:
            raise ValueError('download_url must not be empty.')
        if not asset_id:
            raise ValueError('asset_id must not be empty.')
        FabImportTools._validate_not_expired(expires)
        FabImportTools._invoke_add_to_project(
            download_url, asset_id, asset_name, asset_type, listing_type,
            asset_namespace, list(distribution_point_base_urls), is_quixel)

    @staticmethod
    def _invoke_add_to_project(download_url: str, asset_id: str, asset_name: str, asset_type: str,
                               listing_type: str, asset_namespace: str, base_urls: list, is_quixel: bool) -> None:
        """Forwards to the C++ library call that starts the Fab import workflow."""
        unreal.FabToolsetLibrary.fab_add_to_project(
            download_url, asset_id, asset_name, asset_type, listing_type,
            asset_namespace, base_urls, is_quixel)

    @staticmethod
    def _get_import_status_raw(asset_id: str) -> str:
        """Forwards to the C++ import status query."""
        return unreal.FabToolsetLibrary.get_fab_import_status(asset_id)

    @staticmethod
    def _get_import_finished_raw(asset_id: str) -> str:
        """Forwards to the C++ import finish-time query."""
        return unreal.FabToolsetLibrary.get_fab_import_finished_at(asset_id)

    @toolset_registry.tool_call
    @staticmethod
    def get_fab_import_status(asset_id: str) -> FabImportStatus:
        """Returns the tracked state of one Fab import workflow; the polling
        alternative to watching the output log for the workflow's completion.

        Args:
            asset_id: Listing uid previously passed to add_fab_listing_to_project.

        Returns:
            Status is 'pending' from the import start, then 'completed' or
            'cancelled' once the Fab plugin's workflow ends — cancelled covers
            both user cancellation and failure. 'unknown' when this editor
            session did not start the import (including imports launched from
            the Fab browser window). finished_at is the RFC 3339 UTC time of
            the terminal transition, empty while pending or unknown. Tracking
            lives for the editor session only and does not survive a restart.
        """
        if not asset_id:
            raise ValueError('asset_id must not be empty.')
        status = FabImportStatus()
        status.asset_id = asset_id
        status.status = FabImportTools._get_import_status_raw(asset_id) or 'unknown'
        status.finished_at = FabImportTools._get_import_finished_raw(asset_id)
        return status
