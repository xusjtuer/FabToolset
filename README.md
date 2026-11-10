# FabToolset

> English: [README_EN.md](README_EN.md)

供 AI Agent(MCP)使用的 Fab 工具集插件:搜索 fab.com 商城目录、获取资产的下载信息,并触发 Fab 插件的 Add to Project 导入工作流;也可浏览登录账号"我的库"(已拥有资产)并走同一导入链;同时提供本项目 Fab 库藏(已导入资产 + Vault 缓存)的只读盘点。

## 架构

照引擎 Toolsets 家族形态:`Source/FabToolset/` 为 C++ 模块壳,全部工具逻辑在 `Content/Python/fabtoolset/`(Python toolset 类 + 测试),注册发生在启动脚本 `init_unreal.py`。

C++ 壳承担一处 Python 无法直连的桥接:`FabToolsetLibrary::FabAddToProject`。Fab 插件的 `UFabBrowserApi::AddToProject`(启动导入工作流的唯一入口)头文件在插件 Private/ 下不可 include,且无 BlueprintCallable(反射不导出到 Python)——桥接函数用 `FindFunction` + 属性构造 parms 后 `ProcessEvent` 调用其 CDO,参数结构 `FFabAssetMetadata` 直接 include `Workflows/FabWorkflow.h`(Fab 插件 Public/ 导出头)。

## 工具集

MCP 注册名前缀 `fabtoolset.toolsets.*`;以下工具名均省略该前缀。

### FabCatalogTools(搜索,免认证)

| 工具 | 说明 |
|---|---|
| `search_fab_catalog(query, sort_by, cursor, is_free, categories)` | fab.com 公开目录搜索,单页 24 条 + `next_cursor` 翻页。返回条目含 `uid/title/price/is_free/listing_type/seller_name/tags/asset_formats/thumbnail_url`。`sort_by`:`-relevance`(默认)/`price`/`-price`/`-ratingAverage`/`-publishedAt`。`is_free=true` 返回 0 元资产(实测含领取型与已拥有付费资产,见"使用限制")。`categories` 传分类 slug 列表(如 `['furniture-fixtures']`),服务端结构化过滤,实测生效;有效 slug 见"搜索行为"节。匿名 HTTP,无需登录。 |
| `get_fab_listing_detail(listing_uid)` | 取单个 listing 详情:描述(HTML)/product_type/listing_type/category/seller/price/评分/tags/`asset_formats`/license;`licenses[].offer_id` 是免费领取(`grant_fab_listing_to_library`)所需 offer_id 的来源之一。另有折扣三字段:`discounted_price`/`discount_percentage`/`discount_end_date`——限时免费判据为 `discount_percentage=100 + discounted_price=0 + 截止时间非空`;无折扣时三值均为 0/空。 |
| `get_fab_listings_formats(listing_uids)` | 批量检查格式可用性(≤50 个/次),一次调用替代 N 次详情查询,候选筛选用。每 uid 返回 `{asset_formats, found}`;`found=false` = 该 listing 不可达(404:不存在或下架)。 |

### FabImportTools(下载与导入,需登录)

| 工具 | 说明 |
|---|---|
| `get_fab_listing_format(listing_uid, format_code)` | 列出某 listing 指定格式的可下载文件。`format_code`:`unreal-engine`/`glb`/`gltf`/`fbx`/`blender`。unreal-engine 格式返回 `versions[]`(含 `engine_versions`/`target_platforms`);glb/gltf/fbx 返回平铺文件列表。返回的 `version_uid` 传给下一步。 |
| `get_fab_download_info(listing_uid, file_uid, format_code, platform)` | 取单个文件的签名下载数据:`download_url`(约 1 小时过期,须及时使用)与 `distribution_point_base_urls`。 |
| `grant_fab_listing_to_library(listing_uid, offer_id)` | 领取免费资产入我的库(claim-based 免费资产:0 元但 `is_free=false`,直接下载链 404 必经此步)。POST `/i/listings/{uid}/add-to-library` + `offerId`(camelCase)。服务端异步发放:入库即 `pending`,`download-info` 在 `approved` 前不可用(分钟~小时级)。`offer_id` 来自搜索条目 `startingPrice.offer_id` 或 `get_fab_listing_detail` 的 license 条目。注意:同路径的 `grant-entitlement` 端点是"已购未授权"语义,对未拥有资产 404,不是领取端点。 |
| `add_fab_listing_to_project(download_url, asset_id, asset_name, asset_type, listing_type, ..., expires)` | 触发 Fab 插件的 Add to Project 导入(与 Fab 浏览窗口按钮同一条工作流),异步执行。完成后资产出现在 Content(路径由 Fab 插件决定,通常 `/Game/<资产名>/` 或包自带目录)。`expires` 传入下载信息的 ISO 8601 过期时间戳,已过期则拒绝启动导入(防 stale URL 静默失败)。 |
| `get_fab_import_status(asset_id)` | 查询本会话内经 `add_fab_listing_to_project` 启动的导入工作流状态:`pending`(进行中)→ `completed`(成功)/ `cancelled`(用户取消或失败);`unknown` = 本会话未启动过该导入(含从 Fab 窗口手动发起的)。`finished_at` 为终态 RFC 3339 UTC 时间戳,pending/unknown 时为空。C++ 侧 hook GLog 捕获 LogFab 工作流行实现,状态仅存活于编辑器会话。 |

认证:读取 Fab 插件的 EOS token(Fab 浏览窗口打开过即 persist 登录),内部向 fab.com 换取会话 cookie 后访问下载链。未登录时工具报错,提示先打开 Fab 窗口登录。

### FabLibraryTools(我的库,需登录)

| 工具 | 说明 |
|---|---|
| `search_my_library(query, product_type, sort_by, cursor)` | 搜索登录账号已拥有的资产(acquired),单页 24 条 + `next_cursor` 游标翻页。`query` 关键词过滤;`product_type` 按产品类型过滤(如 `3d-model`);`sort_by`:`-createdAt`(默认)/`title`。每条返回 `library_asset_uid`(我的库私有面用)与 `listing_uid`(公开面导入链用)两个 uid。 |
| `get_my_library_formats(library_asset_uid)` | 列出已拥有资产的全部格式及其文件(如 `unreal-engine`/`unity`/`glb`),文件含 `file_uid` 与字节数。 |
| `get_my_library_download_info(library_asset_uid, file_uid, format_code, platform)` | 取已拥有资产单个文件的签名下载数据(字段同 FabImportTools 的 `FabDownloadInfo`)。 |
| `get_my_library_detail(library_asset_uid)` | 取单个已拥有资产详情:`status`(`pending`/`approved` 等)/`can_request_download_url`/acquired_at + 嵌套 listing 字段(title/description/格式/license)。领取后判断发放状态的入口。 |
| `get_my_library_identity()` | 登录账号身份(display_name/uid/epic_id/seller_name/is_seller),链路连通性与登录态自检用。 |

与 FabImportTools 的分工:两者都走 Add to Project 导入。FabImportTools 用公开面端点(输入 `listing_uid`);FabLibraryTools 用我的库私有面端点(输入 `library_asset_uid`),对下架/仅账号可见的已拥有资产仍可取到文件。公开 listing 可见时优先 FabImportTools 链,取不到格式或下载信息时换 FabLibraryTools 链。

### FabLocalLibraryTools(库藏盘点,只读)

| 工具 | 说明 |
|---|---|
| `list_local_fab_assets()` | Fab 插件记录的已导入资产映射(listing id → 项目路径,含 `exists_in_project` 校验)。 |
| `get_vault_cache_inventory()` | Vault 下载缓存目录盘点(默认 `%TEMP%/FabLibrary`,可含 532MB 级 UE 包)。目录不存在返回空清单,不报错。 |
| `export_fab_catalog(output_path)` | 合并两源写 JSON(静态数据产出通道)。 |

## 典型调用链

```
search_fab_catalog("free tree")
  → 选条目(uid, 确认 is_free/price)
get_fab_listing_format(uid, "unreal-engine")     # 或 "glb"/"fbx" 等
  → 选文件版本(version_uid)
get_fab_download_info(uid, version_uid, format)
  → download_url + base_urls
add_fab_listing_to_project(download_url, uid, title, format, listing_type, base_urls)
  → get_fab_import_status(uid) 轮询到 completed/cancelled
save_assets([])                                   # 重要:导入的包是脏的,Fab 工作流不落盘
```

我的库链(已拥有资产;library_asset_uid 与 listing_uid 不同,勿混用):

```
search_my_library("tree")                          # 或按 product_type 过滤
  → 选条目(library_asset_uid, listing_uid)
get_my_library_formats(library_asset_uid)
  → 选格式与文件(file_uid)
get_my_library_download_info(library_asset_uid, file_uid, format)
  → download_url + base_urls
add_fab_listing_to_project(download_url, listing_uid, title, format, listing_type, base_urls)
  → 同上,等待完成 + save_assets([])
```

领取链(claim-based 免费资产:搜索 0 元但下载链 404,须先领取入我的库再走我的库链):

```
search_fab_catalog("...", is_free=True)
  → 选条目,记 listing_uid 与 asset_formats
get_fab_listing_detail(listing_uid)                # 拿 offer_id
  → licenses[].offer_id
grant_fab_listing_to_library(listing_uid, offer_id)
  → 204 即领取受理;服务端异步发放
get_my_library_detail(library_asset_uid)           # library_asset_uid 从 search_my_library 查
  → status "pending" → 等 "approved"(分钟~小时级)
  → approved 后走上方我的库链
```

## 资产筛选方法(四层漏斗)

### 1. 搜索定位

- 关键词:`<主体词> + 档位词`;免费资产直接带 "free"(命中标题/tags 含 free 的条目);精确物件用特征词组合(如 "plastic garden chairs table lod0")。
- **单词查询无 token 前缀匹配**:q=megaplan 翻 96 页 0 命中 Megaplants——截断词须多词联合或 `*` 通配;`*` 通配有效但杀掉短语加权(精确 listing 会被挤出 rank 1)。
- **卖家名被索引**:q=<卖家名> 返回该卖家全部商品,已知卖家的全系列编目一网打尽。
- 排序:`-relevance` 适合精确目标;`-ratingAverage` 仅对大评数资产有效(低评数 5.0 星噪声大),只当粗筛。
- 大类目(如 tree)数百条翻不完:先翻 2~3 页抽样定方向,再精确关键词定位。
- 级联反查(owned 键/记忆标题反查真 listing,实测 90% 命中):驼峰分词单词查询 → 加 `*` 前缀锁定 → `listing_types` 扇出缩小 → 卖家名搜索 → 深翻页(最后手段)。
- 结构化分类过滤:已知目标类目时 `categories=['<slug>']` 比 free-text 精准一个量级(实测 furniture-fixtures 返回 24 条全 Furniture 类);与关键词/`is_free` 可组合。

### 2. 质量信号(tags + 评分)

加分:`Pbr`/`Photogrammetry`(PBR/扫描级)、`Nanite`/`Lumen`(UE 生态适配)、`Photorealistic`/`Realistic`(写实档)、`Wind`/`Animated`(带风动)。档位不符跳过:`Lowpoly`/`Mobile`/`Stylized`/`Cartoon`(移动降级档反而要找 `Lowpoly`+`Gameready`)。

可信度:`rating_total ≥ 10` 且 `rating_average ≥ 4.4` 才构成信号(样本内 0 评条目占半数);专业卖家(多作品高评分者)质量下限明显更高;title 自述("Game Ready" 等)仅当弱信号。

### 3. 直接可用性验证(get_fab_listing_format,关键层)

搜出来不算数,格式验证后才算数:

1. 首选 `unreal-engine` 格式(LOD/材质/物理/示例地图全套);搜索返回的 `asset_formats` 可先筛,跳过无该格式的候选再逐个验证。
2. 核对 `engine_versions` 含 UE_5.8:含 → 直接可用;只到 5.7 → 可导入需实测;UE_4.x → 高风险慎选。
3. 该格式 404 = 不存在(如 Megascans 类资产),查 `glb` 兜底(仅静态网格+材质,质量降档);注意部分资产无独立 glb 格式,glb 藏在 converted-files 里(`asset_formats` 不含 glb code)。
4. 同时确认 `status: "ready"` 与 `is_free`/`price`。

### 4. 导入后验收(四路对账)

日志(`Fab workflow completed`)→ `get_asset_tags` 数据面(顶点/三角看质量、材质挂接看完整性、碰撞看可用性、ApproxSize 看尺寸合理性)→ 缩略图画取证(无光照预览态,看形态不看颜色)→ 性能对照(桌面档 Nanite 无压力;移动档看 `NaniteTriangles` 与红线 30fps)。

### 待自动化缺口

批量格式验证(候选多时逐个查成本高,`asset_formats` 字段已缓解但未消除逐个验证)、评分可信度字段进排序权重、领取状态轮询(approved 判定目前靠调用方重查 detail)。

## 使用方式(编辑器会话接入)

**前置**:编辑器已打开(unreal-mcp server 于 PostEngineInit 后监听,MCP `list_toolsets` 探活);Add to Project / 下载链需 Fab 登录——Fab 浏览窗口开过一次即 persist 登录;未登录时工具报错,可经 SlateInspectorToolset 点击 Content Browser 工具栏 Fab 按钮全自动触发登录。

**调用入口**:MCP `call_tool`,`toolset_name` 用完整注册名(如 `fabtoolset.toolsets.fab_import.FabImportTools`),`tool_name` 用短名(如 `get_fab_download_info`)。

**导入后验证闭环**(编译绿不适用,资产类改动四路对账):

1. `LogsToolset.GetLogEntries(category="LogFab")` → 等 `Fab workflow completed for asset <uid>`(异步导入,大包分钟级)
2. `AssetTools.save_assets([])` → 保存全部脏包(Fab 工作流不落盘)
3. `AssetTools.find_assets` / `get_asset_tags` → 数据面(顶点/三角/材质挂接/碰撞)
4. `EditorAppToolset.CaptureAssetImage` → 画面取证(base64 超限会截断落盘,解析 tool-results 文件解码 PNG)

**Python 层迭代**:改 toolset 脚本后热重载(前置 Python Remote Execution):

```bash
python <引擎>/Plugins/Experimental/ToolsetRegistry/Content/Python/toolset_registry/tests/reload_remote.py fabtoolset
```

**范围必须传顶层包 `fabtoolset`**:传 `fabtoolset.toolsets` 时 reload 的模块扫描(sys.modules 前缀匹配)不含 tests 包,tests 仍持旧类引用,跑测试报 `Cannot nativize '<Class>' as 'ToolsetDefinition'`(注册表半状态,重跑同参数不恢复;换顶层包重载即恢复)。

**测试**:编辑器内 `AutomationTestToolset.RunTestsByFilter("StartsWith:AI.Toolsets.FabToolset")`,68 个,全 mock 不打真端点。

## 优缺点

**优点**

- **全链自动化**:搜索→选资产→下载信息→导入→状态轮询→验证,全程 MCP 调用;登录在编辑器内 Fab 窗口由用户完成一次(persist),此后 EOS token 换票全自动——自动化浏览器登 fab.com 是 Cloudflare CDP 指纹死路(勾选验证后循环弹回,真人交互也过不了),本架构登录不走自动化浏览器,天然规避。与 Fab 浏览窗口"Add to Project"按钮走同一条插件工作流,导入质量与官方一致(UE 包含 LOD/材质/物理/示例地图全套)。
- **双形态覆盖**:unreal-engine 包(manifest + BuildPatchServices)与 glb/gltf/fbx(Interchange)两条工作流均已端到端实测;UE 包直接可用,glb 兜底无 UE 包的资产。
- **分层认证**:搜索免认证可匿名跑;仅下载链与导入需要登录态。
- **MCP 原生工具集**:68 个测试全 mock,无网络依赖;库藏盘点支持 JSON 导出(静态数据产出通道)。

**缺点**

- 搜索工具面 free-text + 排序 + `is_free` + `categories` 结构化分类过滤(实测有效 slug:`environments`/`nature`(非 nature-and-plants)/`objects-decor`/`furniture-fixtures`/`buildings-architecture`);面数等技术规格过滤端点不支持,描述/技术参数须逐条 `get_fab_listing_detail`。搜索条目不带折扣数值(仅详情端点嵌套 priceTier 有),限时段批量筛查免费件仍需逐条查详情。
- `add_fab_listing_to_project` 异步,完成判定靠轮询 `get_fab_import_status`(C++ 壳 hook GLog 捕获 LogFab 行,Fab 插件无 Python 可达的完成回调);从 Fab 窗口手动发起的导入不在追踪内(status=unknown)。
- 导入产物是脏包,须调用方显式 `save_assets`,否则编辑器关闭即丢。
- C++ 桥依赖 Fab 插件的反射布局(函数名/parms 结构),Fab 插件升级可能破坏——有签名守卫,破坏时报错不静默,但需同步修桥。
- 库藏数据的 config-only 属性(reflection 导出闸门)Python 双拒读,经同文件 C++ 裸反射读取——多一层 C++ 维护面。

## 两种导入形态

| asset_type | 工作流 | download_url 形态 |
|---|---|---|
| `unreal-engine` | FPackImportWorkflow(BuildPatchServices) | 签名 `.manifest` URL + 非空 `distribution_point_base_urls`(CDN base 列表,须一并传入) |
| `glb`/`gltf`/`fbx` | FGenericImportWorkflow(Interchange) | 签名文件直链,`distribution_point_base_urls` 为空数组 |

unreal-engine 格式导入质量最完整(LOD/材质/物理/示例地图全套);glb 等仅静态网格+材质。

## 构建

新 C++ 模块/结构变更走全量构建(模块依赖:`Core` + `CoreUObject`/`Engine`/`Fab`,后三者 Private)。编辑器开着时 Python 层改动走「使用方式」节的热重载命令,勿手工 unregister+register——会留下注册表半状态,MCP 面报 "Invalid Toolset Class"。

## 测试

68 个,根 `AI.Toolsets.FabToolset`,覆盖四个工具集 schema、搜索分页与过滤参数编码(is_free/categories 单 slug 与多 slug join/空 slug 报错/asset_formats/thumbnail_url 映射)、listing 详情映射(含嵌套 priceTier 折扣三字段:无折扣全零与限时免费形态)、批量格式验证(顺序/404 容错/空参与上限报错)、格式 versions/files 双形态映射与空参报错、认证请求构造、下载信息映射与空结果、领取请求构造(端点/offerId/Referer/CSRF 头)与空参报错、Add to Project 参数转发/过期校验/空参报错、导入状态映射(终态字段/空值归一 unknown/空参报错)、认证链网络错误统一 RuntimeError、我的库条目映射与私有面请求 URL、账号身份与单资产详情映射、本地库空库路径。网络与导入调用全部 mock,不在测试中打真实端点。

**注意**:MCP AutomationTestToolset 的 ListTests 快照在编辑器启动时固化,新增测试模块不被其发现(编辑器内 Python 侧 `unittest_runner.discover_tests` 可见全量);重启编辑器或经 MCP RunTests 按完整测试 ID 直跑均可执行新测试。

```python
# 编辑器内:AutomationTestToolset.RunTestsByFilter("StartsWith:AI.Toolsets.FabToolset")
```

## 使用限制

**认证与网络**

- 登录态依赖 Fab 插件的 EOS token:Fab 浏览窗口未开过(新编辑器实例)token 为空,工具报 "Fab is not logged in";换票失败(HTTP 非 200)同样报错,均需先完成 persist 登录。
- EOS access/refresh token 是敏感凭据(经本插件 C++ 壳的 `GetFabAuthToken`/`GetFabRefreshToken` 反射读取,仅供内部换票链使用);自写探针时只打 bool/len,不打印值、不落盘。
- 换票得到的会话 cookie 仅在单次工具调用内有效,不做跨调用缓存;每步下载链调用独立换票。
- `download_url` 为签名 URL,约 1 小时过期(`expires` 字段为准),须在过期前传入 add_fab_listing_to_project(传入 `expires` 参数会在过期时拒绝启动导入)。
- fab.com 的写请求(POST)是 Django 后端,必须携带三件套:`Referer: https://www.fab.com/`(否则 403 "Referer checking failed")+ `X-CSRFToken`(值 = 会话 cookie 里的 `fab_csrftoken`)+ UA;`_post_json` 已内置,自写探针时别漏。
- 编辑器内 urllib 走系统代理设置;fab.com 直连可达即可,无额外代理配置。

**搜索行为(实测矩阵,Dreamscape 50 分钟压测)**

- 页大小固定 24 条,`pageSize`/`limit`/`size` 参数全被服务端忽略;`cursor` 翻页正常且保留查询条件。
- 查询参数是 `q=`;`query=` 被静默忽略(返回默认热门页,不报错)——自写探针时注意。
- `categories=<slug>` 服务端生效(实测 furniture-fixtures 返回 24 条全 Furniture 类目;有效 slug:`environments`/`nature`/`objects-decor`/`furniture-fixtures`/`buildings-architecture`),多 slug 逗号 join 的组合形态未单独实测。
- `sort_by=title` 是全目录字母序扫描模式:**q 过滤被丢弃**,cursor 变为 base64("o=<offset>") 可任意偏移——这是全量顺序枚举 Fab 目录的通道(编目场景),也解释了该模式下翻页"结果与查询无关"的现象。
- 速率:匿名 ~1.6s/req 连续 50 分钟零 429;配 3 次指数退避即可长期跑,无需更复杂限流。
- `sitemap-listings.xml` 无用(878 个按日文件、全部裸 uid 无标题),全量枚举别走它。

**资产与格式**

- 免费判定以返回的 `is_free`/`price` 为准;`search_fab_catalog(is_free=True)` 实测返回 0 元资产(含领取型,其 `is_free` 标志为 false)**以及已拥有的付费资产**(条目 `price` 显示原价,详情 `discounted_price=0`——对账号免费;编辑器内匿名请求仍复现,机制未取证)。筛出的候选须用 `get_fab_listing_detail` 的折扣字段核对,不能只看搜索页 `price`。付费资产走同一链路但需账户已购买,工具不处理购物/结账流程。
- **限时免费与永久免费**:0 元分两类——`isFree: true` = 永久免费;限时免费 = 详情折扣三字段 `discount_percentage=100 + discounted_price=0 + discount_end_date` 非空(平台轮换档,到期即恢复原价,编目时记录截止意识)。折扣数值只存在于详情端点的嵌套 `startingPrice.priceTier.*`,搜索条目仅带 `is_discounted` 布尔;真限时件形态为按嵌套结构构造(fixture 断言),当前轮换档实测未捕获样本(is_free 结果前 96 条 + 16 条零价详情抽样均未见)。
- 领取型免费资产(0 元但 `is_free=false`)直接走下载链 404,须先 `grant_fab_listing_to_library` 领取;领取受理(204)后服务端异步发放,资产以 `pending` 入库,`download-info` 在 `approved` 前一律 404("No LibraryAsset matches the given query",查询集过滤 pending),发放时长分钟~小时级,期间 formats 列表接口照常可用;`grant-entitlement` 端点是"已购未授权"语义,不是领取端点。
- unreal-engine 格式按 `engine_versions` 选包:明确含 UE_5.8 的包直接可用;只到 5.7 及以下的包可尝试导入但未经官方支持(本机 5.8.4);UE_4.x 包兼容风险高。
- Quixel Megascans 类资产通常无 unreal-engine 格式(get_fab_listing_format 返回 404 语义即"该格式不存在"),走不了本工具链;需 glb 形态兜底。
- glb/gltf/fbx 导入为静态网格+材质,无 LOD 分组/物理/示例地图;LOD 命名若为 `Name_LOD0` 后缀式,Interchange 会刷 pattern warning(非致命)。
- 我的库条目带两个 uid,语义不同:`library_asset_uid`(libraryAsset 实体 id,私有面 `/i/library/assets/{uid}/...` 用)与 `listing_uid`(公开 listing id,FabImportTools 公开面用)——混用必 404。

**导入行为**

- `add_fab_listing_to_project` 成功仅代表工作流启动;完成判定以 `get_fab_import_status` 轮询为准(status 翻到 `completed`/`cancelled`,大包数百 MB 耗时分钟级),日志行 `LogFab: Fab workflow completed/cancelled for asset <uid>` 是其数据源兜底。追踪仅本编辑器会话有效,编辑器重启后历史状态归 `unknown`。
- 导入完成后包是脏的,Fab 工作流不落盘;`save_assets([])` 前编辑器关闭即丢失(Autosaves 只救崩溃不作交付)。
- UE 包导入落位路径由包自身目录结构决定(如 `Content/DZ_Assets/...`),不归调用方控制。
- FabLocalLibraryTools 是 Fab 插件数据的只读视图,导入记录/缓存由 Fab 插件维护,本插件不写入;Vault 缓存目录不存在返回空清单是合法态,非错误。

**工程约束**

- Python toolset 改动重载必须走官方 `reload_remote.py`;手工 unregister+register 会让 MCP 面报 "Invalid Toolset Class"(注册表半状态),只能官方通道或重启编辑器恢复。
- FabToolset 模块为 Editor-only(uplugin TargetAllowList=Editor);运行时模块不得依赖。
- MCP 大返回(缩略图/资产列表超长)会被工具结果通道截断落盘,调用方需解析 tool-results 文件或改用小尺寸参数。

## 相关工具与互补通道(借鉴 Dreamscape 实战教程,2026-11)

FabToolset 覆盖"在线检索→下载→导入"主链;以下通道覆盖它不覆盖的盲区,按需组合:

| 通道 | 补什么盲区 | 与 FabToolset 的关系 |
|---|---|---|
| **EOS 所有权缓存直读(R1)** | 全部已拥有资产键,**双时代**(含旧 Marketplace,实测 2954 键),**零登录** | `search_my_library` 只翻登录态 API(24 条/页,1.1K 条要翻 46 页)且只有 Fab 时代;R1 读 `%LOCALAPPDATA%\EpicGamesLauncher\Saved\Data\OC_<AccountId>.dat`(AccountId 核对:Output Log 搜 `LogEOS: AccountId:`),正则提取可打印串 + 剥引擎版本后缀 + 噪声过滤,五分钟出全量键名清单。**键是截断前缀+12/32 位 hex,无真标题**——配 `search_fab_catalog` 级联反查还原。OC 缓存按下载/访问记录写,库页有的资产它不一定有(实测 4 条缺失)。未工具化,方法见教程 §三 |
| **库页面另存 HTML(R2)** | 登录态 API 不可用时的手动兜底,嵌入 JSON 元数据最全(637KB 预取块,键名即端点路径) | FabToolset 的换票通道是同一端点的程序化等价物,正常情况无需 R2;API 面失效(token 失效/端点变更)时,用户自己浏览器 Ctrl+S 另存 `fab.com/library` 手工提取 24 条/页 |
| **Copy as cURL 交接(§八)** | 同上,一次性全量翻页交接 | 凭据零接触,但含会话 Cookie——用完即删不入 git。FabToolset 换票通道优先,cURL 仅手动兜底 |
| **LocalVault 插件** | 已下载资产的长期管理:备份/标签/校验/Database.json Git 友好 | 与 `get_vault_cache_inventory`(只读盘点)定位互补;LocalVault 不能枚举所有权清单、不能发起 Fab 下载——它是下载件管理器不是枚举工具 |

**自动化登录死路(为什么本架构不走自动化浏览器)**:CDP 附加的浏览器被 Cloudflare 行为检测标记,真人点击验证也循环弹回;Edge/Chromium 136+ 默认 profile 静默忽略 `--remote-debugging-port`(防窃登录态,flag 写进命令行但不监听);CEF 内容(Fab 窗口/Epic Launcher)对 UIA 不可见且键盘注入失效。三条路全断 → 登录态获取唯一正解=编辑器内 Fab 窗口用户登录一次 + EOS token persist(本工具集架构)。

## 可扩展方向(教程借鉴)

按价值排序,均来自 Dreamscape 实战教程的实证结论。前两项已实现(2026-11-09):

1. ~~`search_fab_catalog` 暴露 `categories` 参数~~ **已实现**——服务端过滤实测生效,有效 slug 五个(见"搜索行为"节)。
2. ~~FabListingDetail 暴露 discount 字段~~ **已实现**——`discounted_price`/`discount_percentage`/`discount_end_date` 三字段,映射路径经原始 JSON 取证修正(嵌套 `startingPrice.priceTier.*`,教程的顶层字段断言不成立);真限时件样本未捕获,形态为推断(见"使用限制")。
3. **R1 所有权直读工具化**(如 `get_owned_asset_keys()`)——零登录全量已拥有键(双时代),与 search_my_library 互补;实现要点:正则提取 `[ -~]{8,}` 可打印串、`{12,32}` 变长 hex 后缀(实测 {16} 只命中 3/2148,勿用定长)、剥 `_\d+\.\d+` 引擎版本后缀、噪声过滤(替换符 + 字母数字占比 <0.55)。
4. **全量编目模式**——`sort_by=title` 的 offset 扫描通道工具化(跳过逐页 cursor,任意偏移续跑),编目整个免费目录或扫描限时段用。

## 与 UE 5.9 的对比与迁移(2026-11-10 调研)

### 结论先行

**UE 5.9 官方无与本插件同类的 Fab 自动化能力,且 5.9 Launcher 版不再预装 Fab 插件**——本插件迁移 5.9 的唯一堵点是 Fab 插件本体,Python 工具代码可直接复用。

### UE 5.9 官方支持导入 Fab 资产吗?

分层回答(每条附证据):

| 层 | 5.9 状态 | 说明 |
|---|---|---|
| 编辑器内 Fab 窗口(Fab 插件) | ❌ 本机 5.9 无 | 5.8 Launcher 预装于 `Engine\Plugins\Fab`(v0.0.21,EnabledByDefault,源码+预编译 DLL);5.9 Launcher(5.9.0 promoted,`Build.version` IsPromotedBuild:1)六路搜索全空(`Fab.uplugin`/`*Fab*`/`*FabBrowser*`/`LogFab`/`*Fab*.dll`/BaseEngine.ini),且无 `Engine\Plugins\Marketplace` 目录承接按需安装;按引擎版本分发的 5.9 版 Fab 插件截至 2026-11-10 未检索到发布信息(5.9 Preview 刚发布) |
| Launcher Vault → Add to Project | ⚠️ 通道在,未验证 | Launcher 侧流程与引擎 Fab 插件解耦,官方口径仍支持;不经引擎插件,本机未实测 |
| 直接导入 glb/fbx(Interchange) | ✅ | 始终可用,但只是文件导入,不是 Fab 库集成 |
| 官方自动化工具(FabToolset C++ 模块) | ❌ 属 UE6 线 | 已存在于 Fab 插件 v0.0.22(`Public/FabCatalogTypes.h`),但 E 盘 fork `Engine\Plugins\Experimental\Toolsets\UE59-DISABLED.md` 明确:需 catalog API,被排除出 5.9(同批还有 CommonUIToolset 等 10 个) |
| 5.9 Release Notes | — | Fab 相关仅 "Fab image and mesh generation"(生成式 AI 服务集成),无资产库导入条目 |

### 5.9 有无同类 toolset

`Engine\Plugins\Experimental\Toolsets` 下 51 个官方 toolset 全目录 grep `fab|vault|marketplace|asset lib|asset download`(不区分大小写),仅命中各 .uplugin 空 `"MarketplaceURL"` 字段——**无任何 Fab/资产库类 toolset,本插件无被官方取代的风险**。官方 FabToolset(UE6 线)是唯一同名物:本插件的 Python 实现提前覆盖了它计划在 UE6 才提供的能力(公开目录检索→我的库→下载→导入全链)。

### API 兼容性(5.8 → 5.9 实测对比)

| 面 | 判定 | 依据 |
|---|---|---|
| Python:`unreal.ToolsetDefinition` 子类 | ✅ 兼容 | 5.9 基类仍在,注册机制不变 |
| Python:`@toolset_registry.tool_call` | ✅ 兼容 | 5.9 签名扩为 `tool_call(func=None, mode=..., meta=...)`,向后兼容 |
| Python:`Registration.register()/unregister()` | ✅ 兼容 | 同名同方法;5.9 仅加 reload 解析 |
| Python:`unreal.PythonTestRunner` | ✅ 兼容 | 类名与 `PythonTestRunnerSearchOptions` 不变;实现从 ToolsetRegistry 迁至 `PythonScriptPlugin/Source/PythonScriptPluginTests` 模块 |
| C++ 壳(桥接/状态追踪) | ✅ 不受影响 | 5.9 ToolsetRegistry C++ breaking(基类改 `UToolsetDefinition : UObject, IToolsetProvider`、删 `GetToolsetVersion()`、增 `AIRuntimeCallable`/`AIAccessMode`)只影响 C++ toolset 子类——本插件工具集全在 Python,C++ 壳不碰该基类 |
| Build 依赖(`Core/CoreUObject/Engine/Fab`) | ⚠️ Fab 需自备 | 前三项 5.9 自带;`Fab` 见下方迁移路径 |

### 迁移路径(三选一)

> 路径占位符约定:`<引擎安装目录>` = Launcher 安装的引擎根(如 `UE_5.x` 目录),`<引擎源码仓>` = 源码版引擎仓库根。两者按实际机器自行替换。

1. **推荐:Fab 插件随拷进 5.9 + 重编译**——源任选:5.8 Launcher 版自带的 v0.0.21(`<引擎安装目录>\Engine\Plugins\Fab`)或源码 fork 的 v0.0.22(`<引擎源码仓>\Engine\Plugins\Fab`,含官方 FabToolset 模块与 catalog API 源码)。落位 5.9 的 `<引擎安装目录>\Engine\Plugins\Fab` 或项目 `Plugins/Fab`;依赖 Interchange/EditorDataStorageFeatures/EditorScriptingUtilities/EOSShared 均为 5.9 自带,ThirdParty 的 BuildPatchInstallerLib.dll 须随拷。注意两点:5.8 编译的 DLL 不可跨版本加载,须在 5.9 重编译 Fab 插件与本插件 C++ 壳;若用 v0.0.22,Fab 插件升级可能破坏 C++ 桥反射布局(有签名守卫,破坏时报错不静默,需同步修桥)。
2. **引擎源码 fork 工作**(`<引擎源码仓>`,分支 "5.9",已带 Fab v0.0.22 + UE6 线 toolsets):功能面最全,但源码引擎需整编,启动成本高。
3. **暂留 5.8**:当前全链可用;等 5.9 版 Fab 插件发布或官方 6 线 FabToolset 落地后再评估。

## License

Copyright 2026 XUSJTUER

This project is available under two licensing options:

- **Open Source License**: Apache License 2.0
  Subject to the terms of the Apache License 2.0 (see [LICENSE](./LICENSE)), you are free to use, modify and redistribute this project for any purpose, including commercial use.
  This open-source license is non-exclusive and irrevocable for versions already released.

- **Commercial Closed-Source License**:
  If you wish to use this project without complying with the obligations of Apache License 2.0 (such as open-source disclosure requirements, modification notice requirements), a separate commercial closed-source license can be negotiated.

For commercial licensing, custom development or support inquiries, please contact: **xusjtuer@163.com**

> 中文说明:
> 本项目提供两种授权方案:
> 1. 开源授权:Apache License 2.0。在遵守协议前提下,可自由用于包括商业在内的任何用途;已发布版本的开源许可不可撤销、非独占。
> 2. 商业闭源授权:如您希望规避 Apache 2.0 协议约束(无需开源衍生代码、无需标注修改记录等),可单独洽谈商业闭源授权。
> 商业授权、定制开发、技术支持联系:**xusjtuer@163.com**

