# 当前项目功能清单 V0.1（简版）

> **Historical implementation inventory / 非权威需求与状态来源。** 稳定产品需求及 Requirement ID 以 [`../../PRODUCT.md`](../../PRODUCT.md) 为准，当前实现与任务状态分别以 [`../CURRENT_STATE.md`](../CURRENT_STATE.md) 和 [`../backlog.md`](../backlog.md) 为准。下列状态只保留历史沟通语境，不自动授权开发。
>
> 本功能清单基于当前开发分支代码盘点，其中可能包含尚未合并至 main 的 T003 功能。待 T003 完成最终验收并合并 main 后，应再次校准并形成正式功能基线版本。

## 使用说明

本简版用于项目会议、客户沟通和产品讨论。它保留业务模块、功能说明与真实状态，不包含源文件、类名、路由名、SQL 或实现细节。状态含义与完整版一致；`PLANNED` 不计入当前已有功能。

## 简版功能清单

| 一级模块 | 二级模块 | 功能名称 | 功能说明 | 当前状态 |
|---|---|---|---|---|
| 登录与账号 | 身份认证 | 账号密码登录 | 管理端用户使用账号密码登录并取得登录令牌。 | IMPLEMENTED |
| 登录与账号 | 登录会话 | Bearer 会话校验 | 管理端请求自动携带令牌，服务端解析用户、角色与权限。 | IMPLEMENTED |
| 登录与账号 | 个人中心 | 查看个人资料 | 查看本人账号、姓名、角色和权限信息。 | IMPLEMENTED |
| 登录与账号 | 密码管理 | 修改本人密码 | 校验原密码后修改当前用户密码。 | IMPLEMENTED |
| 登录与账号 | 退出登录 | 退出管理端 | 清除浏览器会话并返回登录页。 | IMPLEMENTED |
| 登录与账号 | 个人审计 | 查看本人操作记录 | 查看本人最近的后台操作记录。 | IMPLEMENTED |
| 人员管理 | 人员查询 | 人员列表与筛选 | 按账号、角色和启用状态查询人员。 | IMPLEMENTED |
| 人员管理 | 人员维护 | 新增人员 | 创建账号并指定角色、姓名、手机和初始状态。 | IMPLEMENTED |
| 人员管理 | 人员维护 | 编辑人员与启停 | 修改人员资料、角色及 enabled/disabled 状态。 | IMPLEMENTED |
| 人员管理 | 密码管理 | 管理员重置密码 | 管理员为指定人员设置新的临时密码。 | IMPLEMENTED |
| 人员管理 | 人员维护 | 删除人员 | 删除指定人员，且阻止当前用户删除自己。 | IMPLEMENTED |
| 角色权限 | 预置角色 | 预置管理角色 | 初始化超级管理员、业务操作员和只读查看员。 | IMPLEMENTED |
| 角色权限 | 权限目录 | 查看权限项 | 查看设备、任务、数据、Excel、日志、账号、报表和系统等权限项。 | IMPLEMENTED |
| 角色权限 | 角色维护 | 查看角色与权限 | 查看角色及其权限集合。 | IMPLEMENTED |
| 角色权限 | 角色维护 | 新增角色 | 创建自定义角色并配置权限。 | IMPLEMENTED |
| 角色权限 | 角色维护 | 编辑角色权限 | 修改角色名称、备注并重建权限集合。 | IMPLEMENTED |
| 设备管理 | 设备接入 | Agent 设备注册 | Android Agent 首次接入时登记设备，后续注册更新设备版本和状态。 | IMPLEMENTED |
| 设备管理 | 在线状态 | 设备心跳 | Agent 周期上报存活与版本，服务端保持任务归属为权威状态。 | IMPLEMENTED |
| 设备管理 | 设备查询 | 设备列表与平台筛选 | 查看设备名称、平台、版本、在线状态、当前任务和运行统计。 | IMPLEMENTED |
| 设备管理 | 在线状态 | 离线自动判定 | 按数据库时钟和心跳超时把陈旧设备显示为离线。 | IMPLEMENTED |
| 设备管理 | 设备归属 | 绑定运营人员 | 把设备绑定给运营人员；非超级管理员仅可绑定本人，单人最多两台。 | IMPLEMENTED |
| 设备管理 | 运行策略 | 设备分组与休息参数 | 维护设备分组、连续运行分钟数和休息分钟数。 | PARTIALLY_IMPLEMENTED |
| 设备管理 | 任务历史 | 查看设备历史任务 | 服务端可返回设备最近 100 条任务。 | PARTIALLY_IMPLEMENTED |
| 设备管理 | 远程控制 | 远程终止当前任务 | 管理端终止设备当前任务，收口任务明细并向 Agent 下发停止指令。 | IMPLEMENTED |
| 设备管理 | 实时监控 | 设备实时任务与日志 | 查看设备当前任务进度，并通过 WebSocket 接收新增任务日志。 | IMPLEMENTED |
| 任务管理 | 任务创建 | 手工创建任务 | 从链接、短码或关键词列表创建采集任务。 | IMPLEMENTED |
| 任务管理 | 任务创建 | 配置采集范围与节奏 | 设置综合前 N 个、价格/销量排序、等待区间、批次冷却和异常策略。 | IMPLEMENTED |
| 任务管理 | 养号任务 | 创建账号养护任务 | 选择账号后下发只搜索和浏览、不采集入库的养护任务。 | IMPLEMENTED |
| 任务管理 | 任务审核 | 审核通过或驳回 | 审核待下发任务；运营只能审核本人创建的任务。 | IMPLEMENTED |
| 任务管理 | 设备分配 | 指定执行设备 | 创建任务时指定在线设备，并校验运营设备归属。 | IMPLEMENTED |
| 任务管理 | 任务调度 | Agent 自动领取任务 | 空闲 Agent 优先领取指定给自己的已审核任务，其次领取同平台未指定任务。 | IMPLEMENTED |
| 任务管理 | 任务查询 | 任务列表与状态筛选 | 按任务状态和平台查询任务，并显示结果计数、审核与设备。 | IMPLEMENTED |
| 任务管理 | 任务查询 | 任务详情 | 查看任务配置、任务项、日志、异常和本次采集商品。 | IMPLEMENTED |
| 任务管理 | 进度管理 | 上报任务进度 | Agent 上报日志、关键词执行增量及任务项结果。 | IMPLEMENTED |
| 任务管理 | 状态管理 | 服务端权威任务状态机 | 服务端集中约束 pending、running 与五类终态的合法迁移。 | IMPLEMENTED |
| 任务管理 | 状态管理 | 任务项状态管理 | 区分待处理、执行中、成功、未匹配、技术失败和取消，并禁止终态改写。 | IMPLEMENTED |
| 任务管理 | 任务取消 | 取消待执行或执行中任务 | 任务创建人或超级管理员取消任务并释放设备占用。 | IMPLEMENTED |
| 任务管理 | 任务完成 | 任务完成与结果聚合 | Agent 上报完成后，服务端依据任务项或结果计数形成成功、部分成功或失败。 | IMPLEMENTED |
| 任务管理 | 失败处理 | 失败/取消项重新下发 | 复制失败或取消任务项及匹配目标，创建一条新的待审核任务。 | IMPLEMENTED |
| 任务管理 | 超时处理 | 超时状态表示 | 状态机可记录 timed_out，并允许前端展示与重采。 | PARTIALLY_IMPLEMENTED |
| 商品采集 | 搜索采集 | 拼多多关键词搜索 | 在拼多多 App 中按关键词发起搜索。 | IMPLEMENTED |
| 商品采集 | 搜索结果 | 综合排序前 N 个 | 按综合结果逐个进入前 N 个商品详情。 | IMPLEMENTED |
| 商品采集 | 搜索排序 | 价格升序首项采集 | 按配置切换价格排序并采集首项。 | IMPLEMENTED |
| 商品采集 | 搜索排序 | 销量降序首项采集 | 按配置切换销量排序并采集首项。 | IMPLEMENTED |
| 商品采集 | 目标匹配 | 批准文号/品名/规格/厂家匹配 | 逐个核对目标字段，命中后停止并回填对应任务项。 | IMPLEMENTED |
| 商品采集 | 详情采集 | 商品详情字段解析 | 解析标题、品牌、店铺、价格、销量、规格、批准文号、厂家等字段。 | PARTIALLY_IMPLEMENTED |
| 商品采集 | SKU采集 | 多规格与多盒装价格采集 | 读取 SKU 名称、价格文本/JSON，并支持报表折算单盒价。 | PARTIALLY_IMPLEMENTED |
| 商品采集 | 商品识别 | 商品 ID 与分享链接解析 | 从页面、分享短链和可访问数据中补齐商品 ID 与链接。 | PARTIALLY_IMPLEMENTED |
| 商品采集 | 图片采集 | 商品图片采集与上传 | 收集图片 URL 或本地文件，并随商品元数据/附件上传服务端。 | PARTIALLY_IMPLEMENTED |
| 商品采集 | 拟人节奏 | 采集节奏与拟人动作 | 按任务配置执行操作停顿、阅读、商品间隔、关键词间隔和批次冷却。 | IMPLEMENTED |
| 商品采集 | 养号执行 | 仅浏览不入库 | 养号任务执行搜索、滚动和进入首个商品，但不保存商品资料。 | IMPLEMENTED |
| 商品采集 | 异常策略 | 繁忙/风控/售罄处理 | 识别访问繁忙、疑似风控和售罄，按跳过、有限重试或停止策略处理。 | IMPLEMENTED |
| 商品数据管理 | 数据接收 | Agent 商品上报 | 接收商品字段、远端图片 URL 与任务关联，并写入草稿。 | IMPLEMENTED |
| 商品数据管理 | 商品查询 | 商品库查询与筛选 | 按平台、关键词、品牌、商品 ID、批准文号查询正式商品库。 | IMPLEMENTED |
| 商品数据管理 | 商品查看 | 商品详情与图片/SKU查看 | 查看商品完整字段、SKU 列表、链接和图片附件。 | IMPLEMENTED |
| 商品数据管理 | 任务结果维护 | 编辑本次采集草稿 | 任务创建人或超级管理员可修改本次任务草稿字段。 | IMPLEMENTED |
| 商品数据管理 | 任务结果维护 | 删除本次采集草稿 | 任务创建人或超级管理员可软删除本次任务草稿。 | IMPLEMENTED |
| 商品数据管理 | 商品入库 | 批量保存到正式商品库 | 将选中的任务草稿批量标记为正式商品资料。 | IMPLEMENTED |
| 商品数据管理 | 正式资料维护 | 超级管理员修改或删除正式资料 | 超级管理员维护正式商品字段或软删除商品。 | IMPLEMENTED |
| 商品数据管理 | 变更审计 | 商品变更记录 | 服务端记录修改、删除和正式入库前后的快照。 | PARTIALLY_IMPLEMENTED |
| 商品数据管理 | 数据导出 | 选中商品导出 CSV | 在浏览器把选中商品字段导出为 UTF-8 CSV。 | IMPLEMENTED |
| Excel/CSV | Excel模板 | 下载匹配模板 | 下载包含批准文号、品名、规格和生产厂家的 Excel 模板。 | IMPLEMENTED |
| Excel/CSV | Excel匹配 | 导入并匹配商品库 | 解析 xls/xlsx，按四个核心字段在正式商品库中匹配。 | IMPLEMENTED |
| Excel/CSV | 匹配复核 | 多候选查看与人工选择 | 查看多个候选商品并人工选定回填结果。 | IMPLEMENTED |
| Excel/CSV | 批量导出 | 已匹配商品批量打包 | 每个商品生成 Excel，并可附主图后打包 ZIP 下载。 | IMPLEMENTED |
| Excel/CSV | 兼容导出 | 旧版单 Excel 匹配结果导出 | 服务端保留把全部结果导出为一个 Excel 的兼容接口。 | PARTIALLY_IMPLEMENTED |
| Excel/CSV | 补采任务 | 未匹配行转 Android 任务 | 把未匹配 Excel 行连同目标字段和原始行转为待审核采集任务。 | IMPLEMENTED |
| Excel/CSV | 补采回填 | Android 逐行匹配结果回填 | Agent 上报匹配成功/未匹配并在任务详情显示逐行状态。 | IMPLEMENTED |
| 报表与看板 | 运行看板 | 顶部运行摘要 | 显示在线设备、进行中任务、待执行任务和商品总数。 | IMPLEMENTED |
| 报表与看板 | 经营分析 | 条件化报表分析 | 按平台、商品、规格、厂家、批准文号和价格范围筛选正式商品。 | IMPLEMENTED |
| 报表与看板 | 排行分析 | 销量排行与最低价排行 | 分别查看销量靠前与价格最低的商品。 | IMPLEMENTED |
| 报表与看板 | 价格分析 | 价格段分布 | 按可调价格区间统计商品数和销量。 | IMPLEMENTED |
| 报表与看板 | 规格分析 | 热门规格统计 | 服务端按规格汇总商品数和销量。 | PARTIALLY_IMPLEMENTED |
| 报表与看板 | 单价分析 | 多盒装单盒价 | 解析多盒 SKU 并按盒数折算、排序单盒价。 | IMPLEMENTED |
| 日志与异常 | 操作审计 | 后台操作日志查询 | 按用户和动作查询登录、人员、角色、任务、商品、设备、账号、OTA 等操作。 | IMPLEMENTED |
| 日志与异常 | 个人审计 | 本人操作日志 | 用户在个人中心查看自己的最近操作。 | IMPLEMENTED |
| 日志与异常 | 任务日志 | 任务运行日志 | 记录任务创建、领取、进度、异常、完成和终止信息。 | IMPLEMENTED |
| 日志与异常 | 实时日志 | WebSocket 日志推送 | 服务端尽力广播新增任务日志，页面同时轮询校准。 | PARTIALLY_IMPLEMENTED |
| 日志与异常 | 异常现场 | 任务异常记录 | Agent 上传动作、消息、页面文本和可选截图，任务详情集中查看。 | IMPLEMENTED |
| 日志与异常 | 进程日志 | 各执行端本地运行日志 | Desktop 使用 Loguru，Android 使用 UI/Logcat 回调，Server 使用运行进程输出。 | PARTIALLY_IMPLEMENTED |
| 平台账号管理 | 账号维护 | 平台账号查询与维护 | 按权限查看本人或全部平台账号，并新增、更新养护天数和状态。 | IMPLEMENTED |
| 平台账号管理 | 养护周期 | 到期自动转成熟 | 读取账号列表时把到达成熟日期的 nurturing 账号更新为 ready。 | IMPLEMENTED |
| 平台账号管理 | 设备绑定 | 账号绑定所属设备 | 账号仅能绑定到同一运营名下设备。 | IMPLEMENTED |
| 平台账号管理 | 异常告警 | 全部账号异常告警与确认 | 当某运营全部有效账号均异常/封禁时生成严重告警，并支持确认。 | IMPLEMENTED |
| OTA升级 | 版本包管理 | 上传 Android APK | 上传 latest.apk 并记录版本名、versionCode、大小与下载地址。 | IMPLEMENTED |
| OTA升级 | 升级下发 | 一键下发全部设备 | 终止合法的进行中任务，并通过设备心跳向全部 Agent 下发更新命令。 | IMPLEMENTED |
| OTA升级 | Agent升级 | 下载并请求安装 APK | Agent 接收更新命令，停止本地任务、下载 APK 并调用系统安装流程。 | PARTIALLY_IMPLEMENTED |
| OTA升级 | 升级状态 | 版本查询、待更新与确认 | 管理端查看当前包和待更新设备；Agent 查询最新版本并确认开始更新。 | IMPLEMENTED |
| 实时投屏 | 投屏发起 | 管理端请求设备投屏 | 从设备页发起投屏，命令随心跳到达 Agent。 | IMPLEMENTED |
| 实时投屏 | Agent推流 | 设备画面采集与上传 | Agent 使用 MediaProjection 截取 JPEG 帧并经 WebSocket 推送。 | PARTIALLY_IMPLEMENTED |
| 实时投屏 | Web观看 | 浏览器实时观看设备画面 | 浏览器通过 WebSocket 接收设备 JPEG 帧并显示推流状态。 | IMPLEMENTED |
| 实时投屏 | 投屏控制 | 停止投屏 | 管理端通知发布端和观看端停止，并清理请求状态。 | IMPLEMENTED |
| 实时投屏 | 现场留存 | 下载当前截图与页面日志 | 浏览器本地保存当前帧 JPEG 和可见任务/投屏日志文本。 | IMPLEMENTED |
| 系统配置与平台 | 服务配置 | 环境变量配置与启动校验 | 通过环境变量/.env 配置 Oracle、HTTP、JWT、图片目录和心跳超时，并校验必填值。 | IMPLEMENTED |
| 系统配置与平台 | 页面配置 | 默认平台/限速/心跳页面设置 | 页面可编辑默认平台、限速和心跳值。 | PARTIALLY_IMPLEMENTED |
| 系统配置与平台 | 平台字典 | 平台列表与启停标识 | 返回拼多多及预留平台字典，页面区分启用和预留。 | PARTIALLY_IMPLEMENTED |
| 系统配置与平台 | 健康检查 | 服务健康信息 | 返回服务进程可响应、Oracle DSN、图片目录、Web构建与 OCR 可用标记。 | PARTIALLY_IMPLEMENTED |
| 系统配置与平台 | 数据结构 | Oracle 初始化与启动补丁 | 初始化核心/RBAC表，并在启动时补充任务、账号、告警、异常、商品库视图等结构。 | IMPLEMENTED |
| Android Agent | 独立采集 | 手机端手工启动采集 | 在 Agent 本地输入关键词和采集范围，不依赖 Web 任务即可执行。 | IMPLEMENTED |
| Android Agent | 本地存储 | Room 保存任务和商品 | 本地保存任务执行记录与采集商品。 | IMPLEMENTED |
| Android Agent | 本地导出 | 导出并分享任务 CSV | 把本地任务商品导出为 CSV 并调用系统分享。 | IMPLEMENTED |
| Android Agent | 联机设置 | 配置并测试 Server 连接 | 配置主机、端口、设备名、设备键、平台和联机开关，并探测健康接口。 | IMPLEMENTED |
| Android Agent | 运行前置 | 无障碍/通知/电池与安装权限引导 | 声明并引导采集、前台服务、投屏、通知和 APK 安装所需权限。 | PARTIALLY_IMPLEMENTED |
| Desktop Legacy | 桌面工作台 | PyQt6 桌面采集工作台 | 通过桌面 GUI 配置、启动、停止任务并查看日志和历史。 | LEGACY |
| Desktop Legacy | 浏览器接入 | BitBrowser 环境接管 | 调用本地 BitBrowser API 并通过 Playwright CDP 接管已登录页面。 | LEGACY |
| Desktop Legacy | 本地任务 | 关键词采集任务 | 在桌面端本地执行拼多多搜索、排序和详情采集。 | LEGACY |
| Desktop Legacy | Excel靶标 | Excel目标任务与续跑 | 读取 Excel 目标，按批准文号/规格匹配，并以 checkpoint 续跑未完成行。 | LEGACY |
| Desktop Legacy | 本地存储 | SQLite 增量落库 | 把桌面任务、商品和 Excel checkpoint 保存到 workbench.db。 | LEGACY |
| Desktop Legacy | 本地导出 | Excel/CSV 导出 | 把桌面任务结果导出为 xlsx 或 CSV。 | LEGACY |
| Desktop Legacy | 桌面配置 | 采集与浏览器配置 | 维护 BitBrowser API、节奏、排序、过滤、重试和输出目录。 | LEGACY |
| 规划中能力 | 任务可靠性 | Task Lease 与续租 | 为运行任务建立租约、续租和过期判定。 | PLANNED |
| 规划中能力 | 任务可靠性 | 超时自动回收与 reconciliation | 服务端检测卡死任务并安全回收设备与任务。 | PLANNED |
| 规划中能力 | 可靠上报 | Android 持久化 Outbox | 持久化待上报 progress/product/finish，并在重启后重放。 | PLANNED |
| 规划中能力 | 失败处理 | Retry Queue 与退避策略 | 按错误类型、次数和退避策略持久化重试。 | PLANNED |
| 规划中能力 | 失败处理 | Dead Letter Queue | 把超过重试策略的事件进入人工处理队列。 | PLANNED |
| 规划中能力 | 性能扩展 | Redis/通用缓存 | 建立缓存接口、键规范、TTL、失效和监控。 | PLANNED |
| 规划中能力 | 可观测性 | 完整指标、告警、追踪与 SLO | 覆盖服务、Oracle、任务、设备、质量、存储和告警处置。 | PLANNED |
| 规划中能力 | 工程保障 | CI/CD 与发布门禁 | 建立自动构建、测试、制品、灰度与回滚门禁。 | PLANNED |
| 规划中能力 | 多平台 | 天猫/京东/抖音完整采集适配 | 为每个平台建立独立采集器、字段契约和验收。 | PLANNED |
| 规划中能力 | 数据治理 | 正式迁移、备份恢复与质量闭环 | 建立版本化 schema migration、备份恢复、去重和字段质量规则。 | PLANNED |
| 待确认事项 | 运行基线 | 当前 Oracle 实际结构与数据 | 仅凭仓库无法确认部署库已执行全部初始化/补丁、数据量和索引状态。 | UNKNOWN |
| 待确认事项 | 真机兼容 | 当前拼多多版本真机采集成功率 | 无法从仓库确认现网机型、App版本、页面结构和字段命中率。 | UNKNOWN |
| 待确认事项 | 旧链路定位 | Desktop 是否仍属于正式交付 | 代码完整保留，但未发现其接入当前 Server/Oracle 调度的实现或明确退役决定。 | UNKNOWN |
| 待确认事项 | 发布状态 | 当前部署版本与 T003 验收状态 | 当前分支含 T003 且未合并 main；实际部署是否包含这些提交无法从仓库确认。 | UNKNOWN |
| 待确认事项 | 数据质量 | 现有商品数据准确率与重复率 | 代码有字段采集和匹配，但缺现网样本质量报告、去重口径和验收阈值。 | UNKNOWN |

## 汇总

| 统计项 | 数量 |
|---|---:|
| 一级业务模块 | 16 |
| 总清单功能点 | 125 |
| 当前确认已有功能点 | 110 |
| IMPLEMENTED | 85 |
| PARTIALLY_IMPLEMENTED | 18 |
| LEGACY | 7 |
| PLANNED | 10 |
| UNKNOWN | 5 |
