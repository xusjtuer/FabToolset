# FabToolset

> 中文文档:[README.md](README.md)

A Fab toolset plugin for AI agents (MCP): search the fab.com catalog, obtain download info for assets, and trigger the Fab plugin's Add to Project import workflow; also browse the signed-in account's "My Library" (owned assets) through the same import chain; plus a read-only inventory of this project's Fab holdings (imported assets + Vault cache).

## Architecture

Follows the engine's Toolsets family shape: `Source/FabToolset/` is the C++ module shell, all tool logic lives in `Content/Python/fabtoolset/` (Python toolset classes + tests), and registration happens in the startup script `init_unreal.py`.

The C++ shell handles one bridge Python cannot reach directly: `FabToolsetLibrary::FabAddToProject`. The Fab plugin's `UFabBrowserApi::AddToProject` (the only entry point that starts the import workflow) has its header under the plugin's Private/ so it cannot be included, and it is not BlueprintCallable (never exported to reflection/Python). The bridge function uses `FindFunction` + constructs the parms and calls the CDO via `ProcessEvent`; the parameter struct `FFabAssetMetadata` directly includes `Workflows/FabWorkflow.h` (a Public/ export header of the Fab plugin).

## Toolsets

MCP registered names are prefixed `fabtoolset.toolsets.*`; tool names below omit that prefix.

### FabCatalogTools (search, no auth)

| Tool | Description |
|---|---|
| `search_fab_catalog(query, sort_by, cursor, is_free, categories)` | Search the public fab.com catalog: 24 items per page + `next_cursor` pagination. Items carry `uid/title/price/is_free/listing_type/seller_name/tags/asset_formats/thumbnail_url`. `sort_by`: `-relevance` (default) / `price` / `-price` / `-ratingAverage` / `-publishedAt`. `is_free=true` returns zero-priced assets (in practice this includes claim-based free items and owned paid assets — see "Usage Constraints"). `categories` takes category slugs (e.g. `['furniture-fixtures']`) as a server-side structured filter, verified working; valid slugs under "Search Behavior". Anonymous HTTP, no sign-in required. |
| `get_fab_listing_detail(listing_uid)` | Fetch one listing's details: description (HTML) / product_type / listing_type / category / seller / price / rating / tags / `asset_formats` / license; `licenses[].offer_id` is one source of the offer_id needed for claiming (`grant_fab_listing_to_library`). Also three discount fields: `discounted_price` / `discount_percentage` / `discount_end_date` — limited-time-free criterion is `discount_percentage=100 + discounted_price=0 + non-empty end date`; with no discount all three are 0/empty. |
| `get_fab_listings_formats(listing_uids)` | Batch format availability check (≤50 per call), replacing N detail queries for candidate screening. Returns `{asset_formats, found}` per uid; `found=false` = listing unreachable (404: missing or delisted). |

### FabImportTools (download & import, sign-in required)

| Tool | Description |
|---|---|
| `get_fab_listing_format(listing_uid, format_code)` | List downloadable files for one format of a listing. `format_code`: `unreal-engine` / `glb` / `gltf` / `fbx` / `blender`. The unreal-engine format returns `versions[]` (with `engine_versions` / `target_platforms`); glb/gltf/fbx return a flat file list. Pass the returned `version_uid` to the next step. |
| `get_fab_download_info(listing_uid, file_uid, format_code, platform)` | Fetch signed download data for a single file: `download_url` (expires in ~1 hour, use promptly) and `distribution_point_base_urls`. |
| `grant_fab_listing_to_library(listing_uid, offer_id)` | Claim a free asset into My Library (claim-based free assets: zero-priced but `is_free=false`; the direct download chain 404s, so this step is mandatory). POST `/i/listings/{uid}/add-to-library` + `offerId` (camelCase). The server grants asynchronously: the asset enters the library as `pending`, and `download-info` is unavailable until `approved` (minutes to hours). `offer_id` comes from the search item's `startingPrice.offer_id` or the detail endpoint's license entries. Note: the `grant-entitlement` endpoint on the same path means "purchased but not entitled" and 404s for assets you don't own — it is not the claim endpoint. |
| `add_fab_listing_to_project(download_url, asset_id, asset_name, asset_type, listing_type, ..., expires)` | Trigger the Fab plugin's Add to Project import (the same workflow as the button in the Fab browser window), executed asynchronously. On completion the asset appears in Content (path decided by the Fab plugin, usually `/Game/<AssetName>/` or the package's own directory). Pass the ISO 8601 expiry from the download info as `expires`; an expired URL refuses to start the import (guards against silent failure of stale URLs). |
| `get_fab_import_status(asset_id)` | Query the status of an import started via `add_fab_listing_to_project` in this session: `pending` (running) → `completed` (success) / `cancelled` (user-cancelled or failed); `unknown` = this session never started it (including imports started manually from the Fab window). `finished_at` is an RFC 3339 UTC timestamp for terminal states, empty while pending/unknown. Implemented in C++ by hooking GLog to capture LogFab workflow lines; state lives only for the editor session. |

Auth: reads the Fab plugin's EOS token (persisted once the Fab browser window has been opened and signed in), exchanges it internally for a fab.com session cookie, then uses the download chain. Tools error out when not signed in, prompting you to open the Fab window and log in first.

### FabLibraryTools (My Library, sign-in required)

| Tool | Description |
|---|---|
| `search_my_library(query, product_type, sort_by, cursor)` | Search assets owned by the signed-in account (acquired), 24 per page + `next_cursor` pagination. `query` filters by keyword; `product_type` filters by product type (e.g. `3d-model`); `sort_by`: `-createdAt` (default) / `title`. Each item returns two uids: `library_asset_uid` (private library surface) and `listing_uid` (public surface, used by the import chain). |
| `get_my_library_formats(library_asset_uid)` | List all formats of an owned asset and their files (e.g. `unreal-engine` / `unity` / `glb`); files carry `file_uid` and byte size. |
| `get_my_library_download_info(library_asset_uid, file_uid, format_code, platform)` | Signed download data for a single file of an owned asset (same fields as FabImportTools' `FabDownloadInfo`). |
| `get_my_library_detail(library_asset_uid)` | Details of one owned asset: `status` (`pending` / `approved` / …) / `can_request_download_url` / acquired_at + nested listing fields (title/description/formats/license). The entry point for checking grant status after claiming. |
| `get_my_library_identity()` | Signed-in account identity (display_name/uid/epic_id/seller_name/is_seller), for chain connectivity and sign-in self-checks. |

Division of labor vs FabImportTools: both drive Add to Project imports. FabImportTools uses public-surface endpoints (input `listing_uid`); FabLibraryTools uses private-surface endpoints (input `library_asset_uid`) and still works for delisted or account-visible-only owned assets. Prefer the FabImportTools chain when the public listing is reachable; switch to the FabLibraryTools chain when formats or download info are unavailable.

### FabLocalLibraryTools (local inventory, read-only)

| Tool | Description |
|---|---|
| `list_local_fab_assets()` | The imported-asset mapping recorded by the Fab plugin (listing id → project path, with an `exists_in_project` check). |
| `get_vault_cache_inventory()` | Inventory of the Vault download cache directory (default `%TEMP%/FabLibrary`, may contain 500 MB+ UE packages). A missing directory returns an empty list, not an error. |
| `export_fab_catalog(output_path)` | Merge both sources into one JSON (static-data export channel). |

## Typical Call Chains

```
search_fab_catalog("free tree")
  → pick an item (uid; confirm is_free/price)
get_fab_listing_format(uid, "unreal-engine")     # or "glb"/"fbx" etc.
  → pick a file version (version_uid)
get_fab_download_info(uid, version_uid, format)
  → download_url + base_urls
add_fab_listing_to_project(download_url, uid, title, format, listing_type, base_urls)
  → poll get_fab_import_status(uid) until completed/cancelled
save_assets([])                                   # important: imported packages are dirty; the Fab workflow does not save
```

My Library chain (owned assets; `library_asset_uid` ≠ `listing_uid`, never mix them):

```
search_my_library("tree")                          # or filter by product_type
  → pick an item (library_asset_uid, listing_uid)
get_my_library_formats(library_asset_uid)
  → pick format and file (file_uid)
get_my_library_download_info(library_asset_uid, file_uid, format)
  → download_url + base_urls
add_fab_listing_to_project(download_url, listing_uid, title, format, listing_type, base_urls)
  → same as above: wait for completion + save_assets([])
```

Claim chain (claim-based free assets: zero-priced in search but the download chain 404s; claim into My Library first, then use the My Library chain):

```
search_fab_catalog("...", is_free=True)
  → pick an item; note listing_uid and asset_formats
get_fab_listing_detail(listing_uid)                # to get offer_id
  → licenses[].offer_id
grant_fab_listing_to_library(listing_uid, offer_id)
  → 204 = claim accepted; server grants asynchronously
get_my_library_detail(library_asset_uid)           # library_asset_uid from search_my_library
  → status "pending" → wait for "approved" (minutes to hours)
  → then use the My Library chain above
```

## Asset Filtering Methodology (Four-Layer Funnel)

### 1. Search & locate

- Keywords: `<subject> + tier words`; append "free" for free assets (matches items with free in title/tags); precise objects use feature-word combos (e.g. "plastic garden chairs table lod0").
- **Single-word queries have no token prefix matching**: q=megaplan scanned 96 pages with 0 hits for Megaplants — truncated words need multi-word queries or the `*` wildcard; `*` works but kills phrase weighting (the exact listing gets pushed out of rank 1).
- **Seller names are indexed**: q=<seller name> returns that seller's full catalog — enumerate a known seller's whole line in one go.
- Sorting: `-relevance` for precise targets; `-ratingAverage` only meaningful for high-rating-count assets (noisy at low counts), coarse pre-filter only.
- Big categories (e.g. tree) have hundreds of items: sample 2–3 pages to pick a direction, then narrow with precise keywords.
- Cascaded reverse lookup (from owned-cache keys / remembered titles back to the real listing; ~90% hit rate in practice): camel-case word split → single-word query → `*` prefix to lock → `listing_types` fan-out to narrow → seller-name search → deep pagination (last resort).
- Structured category filter: with a known target category, `categories=['<slug>']` is an order of magnitude more precise than free text (furniture-fixtures returned 24 items, all Furniture); combinable with keywords/`is_free`.

### 2. Quality signals (tags + rating)

Positive: `Pbr` / `Photogrammetry` (PBR/scan-grade), `Nanite` / `Lumen` (UE ecosystem fit), `Photorealistic` / `Realistic` (photoreal tier), `Wind` / `Animated` (wind animation). Skip on tier mismatch: `Lowpoly` / `Mobile` / `Stylized` / `Cartoon` (for the mobile-downgrade tier you actually want `Lowpoly` + `Gameready`).

Trustworthiness: only counts as a signal when `rating_total ≥ 10` and `rating_average ≥ 4.4` (zero-rating items are half the sample); professional sellers (many works, high ratings) have a visibly higher quality floor; title self-claims ("Game Ready" etc.) are weak signals only.

### 3. Direct usability verification (get_fab_listing_format, the key layer)

Being findable doesn't count — verify the format:

1. Prefer the `unreal-engine` format (LOD/materials/physics/sample maps full set); pre-filter on the search item's `asset_formats`, then verify candidates one by one.
2. Check `engine_versions` contains UE_5.8: yes → directly usable; 5.7 max → importable, verify in practice; UE_4.x → high risk, avoid.
3. 404 on that format = it doesn't exist (e.g. Megascans-class assets); fall back to `glb` (static meshes + materials only, quality downgrade); note some assets have no separate glb format — glb hides in converted-files (`asset_formats` lacks the glb code).
4. Also confirm `status: "ready"` and `is_free`/`price`.

### 4. Post-import acceptance (four-way reconciliation)

Logs (`Fab workflow completed`) → `get_asset_tags` data plane (verts/tris for quality, material assignments for completeness, collision for usability, ApproxSize for plausibility) → thumbnail capture (unlit preview state; judge shape, not color) → performance check (desktop tier: Nanite is a non-issue; mobile tier: watch `NaniteTriangles` against the 30 fps red line).

### Automation gaps

Batch format verification (per-candidate queries are expensive; `asset_formats` mitigates but doesn't eliminate it), rating-trust fields in sort weight, claim-status polling (approved currently requires re-querying detail).

## Usage (editor session integration)

**Prerequisites**: the editor is open (the unreal-mcp server listens after PostEngineInit; probe with MCP `list_toolsets`). Add to Project / the download chain need a Fab sign-in — opening the Fab browser window once persists the login; tools error out when not signed in, and you can trigger sign-in fully automatically via SlateInspectorToolset by clicking the Fab button on the Content Browser toolbar.

**Invocation**: MCP `call_tool`, with `toolset_name` as the full registered name (e.g. `fabtoolset.toolsets.fab_import.FabImportTools`) and `tool_name` as the short name (e.g. `get_fab_download_info`).

**Post-import verification loop** (compile-green doesn't apply; assets need four-way reconciliation):

1. `LogsToolset.GetLogEntries(category="LogFab")` → wait for `Fab workflow completed for asset <uid>` (async import; large packages take minutes)
2. `AssetTools.save_assets([])` → save all dirty packages (the Fab workflow does not save)
3. `AssetTools.find_assets` / `get_asset_tags` → data plane (verts/tris/material assignments/collision)
4. `EditorAppToolset.CaptureAssetImage` → visual evidence (base64 overflows get truncated to disk; parse the tool-results file and decode the PNG)

**Python-layer iteration**: hot-reload after editing toolset scripts (requires Python Remote Execution):

```bash
python <EngineInstallDir>/Plugins/Experimental/ToolsetRegistry/Content/Python/toolset_registry/tests/reload_remote.py fabtoolset
```

**The reload scope must be the top-level package `fabtoolset`**: passing `fabtoolset.toolsets` makes the reload's module scan (sys.modules prefix match) miss the tests package, so tests keep old class references and fail with `Cannot nativize '<Class>' as 'ToolsetDefinition'` (a half-updated registry; re-running with the same args does not recover — reload the top-level package to recover).

**Tests**: in the editor, `AutomationTestToolset.RunTestsByFilter("StartsWith:AI.Toolsets.FabToolset")` — 68 tests, fully mocked, no real endpoints hit.

## Pros & Cons

**Pros**

- **Full-chain automation**: search → pick asset → download info → import → status polling → verification, all via MCP calls. Sign-in happens once by the user in the editor's Fab window (persisted); after that the EOS-token exchange is fully automatic — browser-automated sign-in on fab.com is a dead end (Cloudflare CDP fingerprinting loops even with human interaction), and this architecture never automates the browser, sidestepping it by design. Uses the same plugin workflow as the Fab window's "Add to Project" button, so import quality matches the official one (UE packages carry the full LOD/materials/physics/sample-map set).
- **Both import forms covered end to end**: unreal-engine packages (manifest + BuildPatchServices) and glb/gltf/fbx (Interchange) both verified in practice; UE packages are directly usable, glb covers assets without UE packages.
- **Layered auth**: search works anonymously; only the download chain and import need a sign-in state.
- **Native MCP toolset**: 68 mocked tests with no network dependency; local inventory supports JSON export (static-data channel).

**Cons**

- The search surface is free-text + sorting + `is_free` + `categories` structured filtering (verified slugs: `environments` / `nature` (not nature-and-plants) / `objects-decor` / `furniture-fixtures` / `buildings-architecture`); poly-count-style spec filters are unsupported server-side, so description/tech-parameter screening needs per-item `get_fab_listing_detail`. Search items carry no discount numbers (only the detail endpoint's nested priceTier has them), so batch screening of limited-time free items still requires per-item detail queries.
- `add_fab_listing_to_project` is async; completion is determined by polling `get_fab_import_status` (the C++ shell hooks GLog to capture LogFab lines; the Fab plugin exposes no Python-reachable completion callback). Imports started manually from the Fab window are not tracked (status=unknown).
- Imported packages are dirty — the caller must explicitly `save_assets`, or they are lost when the editor closes.
- The C++ bridge depends on the Fab plugin's reflection layout (function names / parms structs); a Fab plugin upgrade can break it — there is a signature guard (fails loudly, not silently), but the bridge needs a matching fix.
- Config-only properties of the local-inventory data (the reflection-export gate) are unreadable from Python both ways; they are read via raw C++ reflection in the same module — one extra C++ maintenance surface.

## Two Import Forms

| asset_type | Workflow | download_url form |
|---|---|---|
| `unreal-engine` | FPackImportWorkflow (BuildPatchServices) | Signed `.manifest` URL + non-empty `distribution_point_base_urls` (CDN base list, must be passed along) |
| `glb`/`gltf`/`fbx` | FGenericImportWorkflow (Interchange) | Signed direct file link, `distribution_point_base_urls` empty |

The unreal-engine format imports with the most complete quality (LOD/materials/physics/sample maps); glb et al. bring static meshes + materials only.

## Build

New C++ modules / structural changes need a full build (module dependencies: `Core` + `CoreUObject`/`Engine`/`Fab`, the last three Private). With the editor open, Python-layer changes go through the hot-reload command in "Usage"; do not manually unregister+register — that leaves a half-updated registry and the MCP surface reports "Invalid Toolset Class".

## Tests

68 tests, rooted at `AI.Toolsets.FabToolset`, covering: the four toolsets' schemas, search pagination & filter parameter encoding (is_free / categories single & multi-slug join / empty-slug errors / asset_formats / thumbnail_url mapping), listing detail mapping (including nested priceTier discount trio: all-zero no-discount and limited-time-free shapes), batch format verification (ordering / 404 tolerance / empty-arg & cap errors), format versions/files dual-shape mapping and empty-arg errors, auth request construction, download-info mapping and empty results, claim request construction (endpoint/offerId/Referer/CSRF headers) and empty-arg errors, Add to Project parameter forwarding / expiry validation / empty-arg errors, import-status mapping (terminal fields / empty→unknown normalization / empty-arg errors), unified RuntimeError on auth-chain network errors, My Library item mapping & private-surface request URLs, account identity & single-asset detail mapping, and the empty local-library path. Network and import calls are fully mocked; no real endpoints are hit in tests.

**Note**: AutomationTestToolset's ListTests snapshot is fixed at editor startup and won't discover newly added test modules (the in-editor Python `unittest_runner.discover_tests` sees the full set); restart the editor or run the new tests directly by full test ID via MCP RunTests.

```python
# In the editor: AutomationTestToolset.RunTestsByFilter("StartsWith:AI.Toolsets.FabToolset")
```

## Usage Constraints

**Auth & network**

- Sign-in depends on the Fab plugin's EOS token: a fresh editor instance that never opened the Fab window has an empty token, and tools report "Fab is not logged in"; a failed exchange (non-200 HTTP) errors out the same way. Complete the persisted sign-in first.
- EOS access/refresh tokens are sensitive credentials (read via this plugin's C++ shell reflection `GetFabAuthToken`/`GetFabRefreshToken`, used only by the internal exchange chain); when writing your own probes, print only bool/len — never print values or write them to disk.
- The session cookie from an exchange is valid only within a single tool call and is never cached across calls; each download-chain step exchanges independently.
- `download_url` is a signed URL that expires in ~1 hour (`expires` field is authoritative); pass it to add_fab_listing_to_project before expiry (the `expires` parameter makes the import refuse to start on an expired URL).
- fab.com write requests (POST) hit a Django backend that requires the trio: `Referer: https://www.fab.com/` (else 403 "Referer checking failed") + `X-CSRFToken` (value = `fab_csrftoken` from the session cookie) + UA; `_post_json` includes all three — don't forget them in hand-written probes.
- In-editor urllib follows system proxy settings; fab.com just needs to be directly reachable, no extra proxy configuration.

**Search behavior (verified matrix; 50-minute Dreamscape soak)**

- Page size is fixed at 24; `pageSize`/`limit`/`size` are all ignored server-side; `cursor` pagination works and preserves the query.
- The query parameter is `q=`; `query=` is silently ignored (returns the default trending page, no error) — beware in hand-written probes.
- `categories=<slug>` works server-side (furniture-fixtures returned 24 items, all Furniture; valid slugs: `environments` / `nature` / `objects-decor` / `furniture-fixtures` / `buildings-architecture`); the multi-slug comma-join form was not separately verified.
- `sort_by=title` is a whole-catalog alphabetical scan mode: **the q filter is dropped** and cursor becomes base64("o=<offset>") with arbitrary offsets — this is the channel for full sequential enumeration of the Fab catalog (cataloging scenarios), and it also explains why pagination "ignores the query" in this mode.
- Rate: anonymous ~1.6 s/req for 50 straight minutes, zero 429s; 3 exponential-backoff retries suffice for long runs, no fancier rate limiting needed.
- `sitemap-listings.xml` is useless (878 per-day files, all bare uids with no titles); don't use it for full enumeration.

**Assets & formats**

- Free-ness is judged by the returned `is_free`/`price`; `search_fab_catalog(is_free=True)` returns zero-priced assets (including claim-based ones whose `is_free` flag is false) **and owned paid assets** (item `price` shows the original price while the detail's `discounted_price=0` — free for the account; still reproduced with anonymous in-editor requests, mechanism not yet forensically confirmed). Verify candidates against the detail endpoint's discount fields; don't trust the search page `price` alone. Paid assets use the same chain but require the account to own them; the tools do not handle purchase/checkout.
- **Limited-time free vs permanently free**: two kinds of zero-price — `isFree: true` = permanently free; limited-time free = the detail trio `discount_percentage=100 + discounted_price=0 + non-empty discount_end_date` (a rotating platform tier; reverts to original price on expiry — note the deadline when cataloging). Discount numbers exist only in the detail endpoint's nested `startingPrice.priceTier.*`; search items carry only the `is_discounted` boolean. The true limited-time shape is asserted from the nested structure (fixture); no real rotating-tier sample captured yet (neither the first 96 is_free results nor a 16-item zero-price detail sample had one).
- Claim-based free assets (zero-priced but `is_free=false`) 404 on the direct download chain; claim with `grant_fab_listing_to_library` first. After the 204 acceptance, the server grants asynchronously: the asset enters the library as `pending`, and download-info 404s ("No LibraryAsset matches the given query" — the query set filters out pending) until `approved`; grant duration is minutes to hours, while the formats listing endpoint stays usable throughout. The `grant-entitlement` endpoint means "purchased but not entitled" — it is not the claim endpoint.
- For the unreal-engine format pick packages by `engine_versions`: packages explicitly containing UE_5.8 are directly usable; 5.7-and-below packages may import but are unsupported (this machine runs 5.8.4); UE_4.x packages carry high compatibility risk.
- Quixel Megascans-class assets usually have no unreal-engine format (404 semantics = "this format doesn't exist") and cannot use this chain; glb is the fallback.
- glb/gltf/fbx import as static meshes + materials: no LOD grouping/physics/sample maps; if LOD names use the `Name_LOD0` suffix style, Interchange emits pattern warnings (non-fatal).
- My Library items carry two uids with different semantics: `library_asset_uid` (the libraryAsset entity id, for the private `/i/library/assets/{uid}/...` surface) and `listing_uid` (the public listing id, used by FabImportTools' public surface) — mixing them 404s.

**Import behavior**

- `add_fab_listing_to_project` success only means the workflow started; completion is determined by `get_fab_import_status` polling (status flips to `completed`/`cancelled`; multi-hundred-MB packages take minutes), with the log line `LogFab: Fab workflow completed/cancelled for asset <uid>` as the data-source fallback. Tracking is per editor session only; after a restart history goes `unknown`.
- After import the package is dirty — the Fab workflow does not save; without `save_assets([])` everything is lost when the editor closes (Autosaves only rescue crashes, not deliverables).
- UE-package import landing paths follow the package's own directory structure (e.g. `Content/DZ_Assets/...`); not caller-controlled.
- FabLocalLibraryTools is a read-only view of Fab plugin data; import records/caches are maintained by the Fab plugin, never written by this plugin. An empty list for a missing Vault cache directory is a legitimate state, not an error.

**Engineering constraints**

- Python toolset changes must reload via the official `reload_remote.py`; manual unregister+register leaves a half-updated registry reporting "Invalid Toolset Class" on the MCP surface — only the official channel or an editor restart recovers.
- The FabToolset module is Editor-only (uplugin TargetAllowList=Editor); runtime modules must not depend on it.
- Large MCP responses (thumbnails/long asset lists) get truncated to disk by the tool-result channel; callers must parse the tool-results file or use smaller-size parameters.

## Related Tools & Complementary Channels (from the Dreamscape hands-on tutorial, 2026-11)

FabToolset covers the "online search → download → import" main chain; the channels below cover its blind spots — combine as needed:

| Channel | Blind spot it fills | Relationship to FabToolset |
|---|---|---|
| **Direct read of the EOS ownership cache (R1)** | All owned asset keys, **across both eras** (including legacy Marketplace; 2954 keys in practice), **zero sign-in** | `search_my_library` only paginates the signed-in API (24/page; 1.1K items = 46 pages) and covers only the Fab era. R1 reads `%LOCALAPPDATA%\EpicGamesLauncher\Saved\Data\OC_<AccountId>.dat` (verify AccountId: search Output Log for `LogEOS: AccountId:`), regex-extracts printable strings + strips engine-version suffixes + filters noise — full key list in five minutes. **Keys are truncated prefixes + 12/32-hex, no real titles** — pair with `search_fab_catalog` cascaded reverse lookup. The OC cache is written from download/access records, so library items may be missing from it (4 missing in practice). Not yet toolized; method in tutorial §3 |
| **Save library page HTML (R2)** | Manual fallback when the signed-in API is unavailable; embedded JSON metadata is the fullest (637 KB preloaded block, keys are endpoint paths) | FabToolset's exchange channel is the programmatic equivalent of the same endpoints; R2 is normally unnecessary. If the API surface breaks (token invalidated / endpoints changed), save `fab.com/library` with Ctrl+S in your own browser and extract 24 items per page by hand |
| **Copy as cURL handoff (§8)** | Same as above, one-shot full pagination handoff | Zero credential handling, but contains the session cookie — delete after use, never commit. Prefer FabToolset's exchange channel; cURL is the manual fallback only |
| **LocalVault plugin** | Long-term management of downloaded assets: backup/tags/checksums/Git-friendly Database.json | Complements `get_vault_cache_inventory` (read-only inventory); LocalVault cannot enumerate ownership and cannot start Fab downloads — it's a download manager, not an enumeration tool |

**Why browser automation for sign-in is a dead end**: a CDP-attached browser gets flagged by Cloudflare behavioral detection and loops even with genuine human clicks; Edge/Chromium 136+ default profiles silently ignore `--remote-debugging-port` (anti login-token theft; the flag appears on the command line but nothing listens); CEF content (Fab window / Epic Launcher) is invisible to UIA and keyboard injection fails. All three roads blocked → the only correct way to get a sign-in state is one user sign-in in the editor's Fab window + persisted EOS token (this toolset's architecture).

## Extensibility Roadmap (tutorial-informed)

Ordered by value; all from empirically verified conclusions of the Dreamscape tutorial. The first two are implemented (2026-11-09):

1. ~~Expose `categories` on search_fab_catalog~~ **done** — server-side filtering verified; five valid slugs (see "Search Behavior").
2. ~~Expose discount fields on FabListingDetail~~ **done** — `discounted_price` / `discount_percentage` / `discount_end_date`; the mapping path was corrected against raw JSON forensics (nested `startingPrice.priceTier.*`; the tutorial's top-level-field claim is wrong). No real limited-time sample captured yet; the shape is inferred (see "Usage Constraints").
3. **Toolize R1 ownership reading** (e.g. `get_owned_asset_keys()`) — zero-sign-in full owned-key enumeration across both eras, complementing search_my_library. Implementation notes: extract printable runs `[ -~]{8,}`, variable-length hex suffixes `{12,32}` (fixed {16} only matched 3/2148 — don't), strip `_\d+\.\d+` engine-version suffixes, filter noise (replacement chars + alnum ratio < 0.55).
4. **Full-catalog mode** — toolize the `sort_by=title` offset-scan channel (skip per-page cursors, resume from any offset) for cataloging the entire free catalog or scanning limited-time tiers.

## UE 5.9 Comparison & Migration (2026-11-10 research)

### Conclusion first

**UE 5.9 has no official Fab automation comparable to this plugin, and the 5.9 Launcher no longer ships the Fab plugin** — the only blocker for migrating to 5.9 is the Fab plugin itself; the Python tool code carries over directly.

### Does 5.9 officially support importing Fab assets?

Layered answer (each with evidence):

| Layer | 5.9 status | Notes |
|---|---|---|
| In-editor Fab window (Fab plugin) | ❌ absent on this 5.9 | The 5.8 Launcher preinstalls it at `Engine\Plugins\Fab` (v0.0.21, EnabledByDefault, source + prebuilt DLL); on 5.9 Launcher (5.9.0 promoted, `Build.version` IsPromotedBuild:1) a six-way search all came up empty (`Fab.uplugin` / `*Fab*` / `*FabBrowser*` / `LogFab` / `*Fab*.dll` / BaseEngine.ini), and there is no `Engine\Plugins\Marketplace` directory for on-demand installs; no release info found for a per-engine-version 5.9 Fab plugin as of 2026-11-10 (5.9 Preview just shipped) |
| Launcher Vault → Add to Project | ⚠️ channel exists, unverified | The Launcher-side flow is decoupled from the engine Fab plugin and officially still supported; not exercised locally |
| Direct glb/fbx import (Interchange) | ✅ | Always available, but that's file import, not Fab library integration |
| Official automation (FabToolset C++ module) | ❌ UE6-line | Already exists in Fab plugin v0.0.22 (`Public/FabCatalogTypes.h`), but the fork's `Engine\Plugins\Experimental\Toolsets\UE59-DISABLED.md` states explicitly: it needs the catalog API and was excluded from 5.9 (10 more toolsets including CommonUIToolset were excluded in the same batch) |
| 5.9 Release Notes | — | Fab mentions only "Fab image and mesh generation" (generative AI service integration); no asset-library import entry |

### Any comparable toolset in 5.9?

Grepping all 51 official toolsets under `Engine\Plugins\Experimental\Toolsets` for `fab|vault|marketplace|asset lib|asset download` (case-insensitive) hits only empty `"MarketplaceURL"` fields in the .uplugins — **no Fab/asset-library toolset exists, so this plugin faces no official replacement**. The official FabToolset (UE6 line) is the sole name-sharer: this plugin's Python implementation already covers, ahead of time, the capability set the official one plans for UE6 (public catalog search → My Library → download → import, full chain).

### API compatibility (5.8 → 5.9, verified)

| Surface | Verdict | Basis |
|---|---|---|
| Python: `unreal.ToolsetDefinition` subclasses | ✅ compatible | Base class remains in 5.9; registration unchanged |
| Python: `@toolset_registry.tool_call` | ✅ compatible | 5.9 signature widened to `tool_call(func=None, mode=..., meta=...)`, backward compatible |
| Python: `Registration.register()/unregister()` | ✅ compatible | Same names; 5.9 only adds reload parsing |
| Python: `unreal.PythonTestRunner` | ✅ compatible | Class and `PythonTestRunnerSearchOptions` unchanged; implementation moved from ToolsetRegistry to the `PythonScriptPlugin/Source/PythonScriptPluginTests` module |
| C++ shell (bridge/status tracker) | ✅ unaffected | 5.9 ToolsetRegistry C++ breaking changes (`UToolsetDefinition : UObject, IToolsetProvider`, `GetToolsetVersion()` removed, `AIRuntimeCallable`/`AIAccessMode` added) only affect C++ toolset subclasses — this plugin's toolsets are all Python; the C++ shell never touches that base class |
| Build deps (`Core/CoreUObject/Engine/Fab`) | ⚠️ Fab self-provided | First three ship with 5.9; `Fab` — see migration paths |

### Migration paths (choose one)

> Placeholder convention: `<EngineInstallDir>` = root of the Launcher-installed engine (e.g. the `UE_5.x` directory), `<EngineSourceRepo>` = root of a source-built engine checkout. Substitute for your machine.

1. **Recommended: copy the Fab plugin into 5.9 + rebuild** — source options: the 5.8 Launcher's bundled v0.0.21 (`<EngineInstallDir>\Engine\Plugins\Fab`) or a source fork's v0.0.22 (`<EngineSourceRepo>\Engine\Plugins\Fab`, includes the official FabToolset module and catalog API source). Land it at 5.9's `<EngineInstallDir>\Engine\Plugins\Fab` or the project's `Plugins/Fab`; dependencies Interchange / EditorDataStorageFeatures / EditorScriptingUtilities / EOSShared all ship with 5.9, but ThirdParty's BuildPatchInstallerLib.dll must be copied along. Two cautions: DLLs built for 5.8 do not load across versions — rebuild both the Fab plugin and this plugin's C++ shell on 5.9; with v0.0.22, Fab plugin upgrades can break the C++ bridge's reflection layout (a signature guard fails loudly, not silently — fix the bridge in sync).
2. **Work inside a source-built engine fork** (`<EngineSourceRepo>`, branch "5.9", ships Fab v0.0.22 + UE6-line toolsets): widest feature surface, but source engines need a full integration build — high startup cost.
3. **Stay on 5.8 for now**: the full chain works today; reassess once a 5.9 Fab plugin ships or the official UE6-line FabToolset lands.

## License

Copyright 2026 XUSJTUER

This project is available under two licensing options:

- **Open Source License**: Apache License 2.0
  Subject to the terms of the Apache License 2.0 (see [LICENSE](./LICENSE)), you are free to use, modify and redistribute this project for any purpose, including commercial use.
  This open-source license is non-exclusive and irrevocable for versions already released.

- **Commercial Closed-Source License**:
  If you wish to use this project without complying with the obligations of Apache License 2.0 (such as open-source disclosure requirements, modification notice requirements), a separate commercial closed-source license can be negotiated.

For commercial licensing, custom development or support inquiries, please contact: **xusjtuer@163.com**
