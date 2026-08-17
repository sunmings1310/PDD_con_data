# 当前项目功能清单 V0.1

> 本功能清单基于当前开发分支代码盘点，其中可能包含尚未合并至 main 的 T003 功能。待 T003 完成最终验收并合并 main 后，应再次校准并形成正式功能基线版本。

## 1. 文档说明

| 项目 | 值 |
|---|---|
| Branch | `task/T003-task-state-machine` |
| HEAD | `4b692ec91e0416779ac7a0e72326bba78abe1a2d` |
| 生成日期 | 2026-08-15 |
| 基线状态 | 开发基线盘点版，不是 Release Baseline |
| Working tree | 盘点开始时已有未提交修改：`docs/tasks/T003-oracle-test-env.md`；本任务保持该文件原状 |
| 相对 main 的提交 | `e7328c9`、`bcc6e43`、`c7d89b7`、`4b692ec`（共 4 个） |
| T003 | `PENDING_MERGE`；相关能力可进入本清单，但不代表已进入 main 正式基线 |

### 1.1 扫描范围与判定方法

本次逐项核对了 `server/`、`web/`、`android_collector/`、根目录 Desktop Python 链路、`docs/`、API Router、Vue 路由与菜单、Oracle/Room/SQLite 数据模型、配置、RBAC、任务、商品、设备、报表、日志、OTA、投屏、Excel/CSV 和图片模块。判定优先级为当前代码调用链与测试/验收记录，其次才是 Roadmap/GAP；仅有页面、路由、常量或表结构不判定为完整实现。

状态口径：`IMPLEMENTED` 表示主要业务链完整；`PARTIALLY_IMPLEMENTED` 表示仅部分链路或存在已确认缺口；`LEGACY` 表示旧 Desktop 交付链；`PLANNED` 仅表示文档明确规划且不计入当前已有功能；`UNKNOWN` 表示仅凭仓库不能确认。

## 2. 产品总体说明

当前系统用于组织拼多多商品数据采集与管理：管理人员在 Web 中维护人员权限、设备、平台账号和采集任务；FastAPI/Oracle 负责审核、调度、状态、数据与日志；Android Agent 在手机端领取任务，通过无障碍驱动拼多多 App，上传商品、图片、进度和异常；Web 再完成商品入库、Excel 匹配、报表、OTA 和投屏。根目录仍保留一条独立的 Desktop Legacy 采集链，但它不接入当前 Server/Oracle 调度。

## 3. 功能模块树

- **登录与账号**
  - 身份认证：账号密码登录
  - 登录会话：Bearer 会话校验
  - 个人中心：查看个人资料
  - 密码管理：修改本人密码
  - 退出登录：退出管理端
  - 个人审计：查看本人操作记录
- **人员管理**
  - 人员查询：人员列表与筛选
  - 人员维护：新增人员、编辑人员与启停、删除人员
  - 密码管理：管理员重置密码
- **角色权限**
  - 预置角色：预置管理角色
  - 权限目录：查看权限项
  - 角色维护：查看角色与权限、新增角色、编辑角色权限
- **设备管理**
  - 设备接入：Agent 设备注册
  - 在线状态：设备心跳、离线自动判定
  - 设备查询：设备列表与平台筛选
  - 设备归属：绑定运营人员
  - 运行策略：设备分组与休息参数
  - 任务历史：查看设备历史任务
  - 远程控制：远程终止当前任务
  - 实时监控：设备实时任务与日志
- **任务管理**
  - 任务创建：手工创建任务、配置采集范围与节奏
  - 养号任务：创建账号养护任务
  - 任务审核：审核通过或驳回
  - 设备分配：指定执行设备
  - 任务调度：Agent 自动领取任务
  - 任务查询：任务列表与状态筛选、任务详情
  - 进度管理：上报任务进度
  - 状态管理：服务端权威任务状态机、任务项状态管理
  - 任务取消：取消待执行或执行中任务
  - 任务完成：任务完成与结果聚合
  - 失败处理：失败/取消项重新下发
  - 超时处理：超时状态表示
- **商品采集**
  - 搜索采集：拼多多关键词搜索
  - 搜索结果：综合排序前 N 个
  - 搜索排序：价格升序首项采集、销量降序首项采集
  - 目标匹配：批准文号/品名/规格/厂家匹配
  - 详情采集：商品详情字段解析
  - SKU采集：多规格与多盒装价格采集
  - 商品识别：商品 ID 与分享链接解析
  - 图片采集：商品图片采集与上传
  - 拟人节奏：采集节奏与拟人动作
  - 养号执行：仅浏览不入库
  - 异常策略：繁忙/风控/售罄处理
- **商品数据管理**
  - 数据接收：Agent 商品上报
  - 商品查询：商品库查询与筛选
  - 商品查看：商品详情与图片/SKU查看
  - 任务结果维护：编辑本次采集草稿、删除本次采集草稿
  - 商品入库：批量保存到正式商品库
  - 正式资料维护：超级管理员修改或删除正式资料
  - 变更审计：商品变更记录
  - 数据导出：选中商品导出 CSV
- **Excel/CSV**
  - Excel模板：下载匹配模板
  - Excel匹配：导入并匹配商品库
  - 匹配复核：多候选查看与人工选择
  - 批量导出：已匹配商品批量打包
  - 兼容导出：旧版单 Excel 匹配结果导出
  - 补采任务：未匹配行转 Android 任务
  - 补采回填：Android 逐行匹配结果回填
- **报表与看板**
  - 运行看板：顶部运行摘要
  - 经营分析：条件化报表分析
  - 排行分析：销量排行与最低价排行
  - 价格分析：价格段分布
  - 规格分析：热门规格统计
  - 单价分析：多盒装单盒价
- **日志与异常**
  - 操作审计：后台操作日志查询
  - 个人审计：本人操作日志
  - 任务日志：任务运行日志
  - 实时日志：WebSocket 日志推送
  - 异常现场：任务异常记录
  - 进程日志：各执行端本地运行日志
- **平台账号管理**
  - 账号维护：平台账号查询与维护
  - 养护周期：到期自动转成熟
  - 设备绑定：账号绑定所属设备
  - 异常告警：全部账号异常告警与确认
- **OTA升级**
  - 版本包管理：上传 Android APK
  - 升级下发：一键下发全部设备
  - Agent升级：下载并请求安装 APK
  - 升级状态：版本查询、待更新与确认
- **实时投屏**
  - 投屏发起：管理端请求设备投屏
  - Agent推流：设备画面采集与上传
  - Web观看：浏览器实时观看设备画面
  - 投屏控制：停止投屏
  - 现场留存：下载当前截图与页面日志
- **系统配置与平台**
  - 服务配置：环境变量配置与启动校验
  - 页面配置：默认平台/限速/心跳页面设置
  - 平台字典：平台列表与启停标识
  - 健康检查：服务健康信息
  - 数据结构：Oracle 初始化与启动补丁
- **Android Agent**
  - 独立采集：手机端手工启动采集
  - 本地存储：Room 保存任务和商品
  - 本地导出：导出并分享任务 CSV
  - 联机设置：配置并测试 Server 连接
  - 运行前置：无障碍/通知/电池与安装权限引导
- **Desktop Legacy**
  - 桌面工作台：PyQt6 桌面采集工作台
  - 浏览器接入：BitBrowser 环境接管
  - 本地任务：关键词采集任务
  - Excel靶标：Excel目标任务与续跑
  - 本地存储：SQLite 增量落库
  - 本地导出：Excel/CSV 导出
  - 桌面配置：采集与浏览器配置

## 4. 完整功能清单

| 功能ID | 一级模块 | 二级模块 | 功能名称 | 功能说明 | 使用角色 | Web | Server API | Android | Desktop | 主要数据 | 当前状态 | 备注 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F-001 | 登录与账号 | 身份认证 | 账号密码登录 | 管理端用户使用账号密码登录并取得登录令牌。 | 全体管理端用户 | 登录页 | POST /api/auth/login | 无 | 无 | 用户、角色、登录时间/IP | IMPLEMENTED | 失败与成功登录均写操作日志。 |
| F-002 | 登录与账号 | 登录会话 | Bearer 会话校验 | 管理端请求自动携带令牌，服务端解析用户、角色与权限。 | 全体管理端用户 | 全局请求拦截器 | GET /api/auth/me | 无 | 无 | JWT、用户、权限 | IMPLEMENTED | 令牌默认有效期由服务端环境配置。 |
| F-003 | 登录与账号 | 个人中心 | 查看个人资料 | 查看本人账号、姓名、角色和权限信息。 | 全体管理端用户 | 个人中心 | GET /api/auth/me | 无 | 无 | 当前用户 | IMPLEMENTED |  |
| F-004 | 登录与账号 | 密码管理 | 修改本人密码 | 校验原密码后修改当前用户密码。 | 全体管理端用户 | 个人中心 | POST /api/auth/change-password | 无 | 无 | 密码摘要、操作日志 | IMPLEMENTED |  |
| F-005 | 登录与账号 | 退出登录 | 退出管理端 | 清除浏览器会话并返回登录页。 | 全体管理端用户 | 顶部用户菜单 | 无 | 无 | 无 | 浏览器令牌 | IMPLEMENTED | 客户端退出；未发现服务端令牌吊销表。 |
| F-006 | 登录与账号 | 个人审计 | 查看本人操作记录 | 查看本人最近的后台操作记录。 | 全体管理端用户 | 个人中心 | GET /api/auth/my-logs | 无 | 无 | 操作日志 | IMPLEMENTED |  |
| F-007 | 人员管理 | 人员查询 | 人员列表与筛选 | 按账号、角色和启用状态查询人员。 | 具备 user:manage 权限 | 人员管理页 | GET /api/users | 无 | 无 | 用户、角色 | IMPLEMENTED |  |
| F-008 | 人员管理 | 人员维护 | 新增人员 | 创建账号并指定角色、姓名、手机和初始状态。 | 具备 user:manage 权限 | 人员管理页 | POST /api/users | 无 | 无 | 用户、角色 | IMPLEMENTED |  |
| F-009 | 人员管理 | 人员维护 | 编辑人员与启停 | 修改人员资料、角色及 enabled/disabled 状态。 | 具备 user:manage 权限 | 人员管理页 | PUT /api/users/{user_id} | 无 | 无 | 用户、角色 | IMPLEMENTED |  |
| F-010 | 人员管理 | 密码管理 | 管理员重置密码 | 管理员为指定人员设置新的临时密码。 | 具备 user:manage 权限 | 人员管理页 | POST /api/users/{user_id}/reset-password | 无 | 无 | 用户密码摘要 | IMPLEMENTED |  |
| F-011 | 人员管理 | 人员维护 | 删除人员 | 删除指定人员，且阻止当前用户删除自己。 | 具备 user:manage 权限 | 人员管理页 | DELETE /api/users/{user_id} | 无 | 无 | 用户 | IMPLEMENTED | 未发现关联数据的数据库外键级约束。 |
| F-012 | 角色权限 | 预置角色 | 预置管理角色 | 初始化超级管理员、业务操作员和只读查看员。 | 部署管理员 | 无 | 初始化脚本 | 无 | 无 | 角色、角色权限 | IMPLEMENTED |  |
| F-013 | 角色权限 | 权限目录 | 查看权限项 | 查看设备、任务、数据、Excel、日志、账号、报表和系统等权限项。 | 已登录用户 | 角色权限页 | GET /api/perms/catalog | 无 | 无 | 权限目录 | IMPLEMENTED |  |
| F-014 | 角色权限 | 角色维护 | 查看角色与权限 | 查看角色及其权限集合。 | 已登录用户 | 角色权限页 | GET /api/roles | 无 | 无 | 角色、角色权限 | IMPLEMENTED |  |
| F-015 | 角色权限 | 角色维护 | 新增角色 | 创建自定义角色并配置权限。 | 具备 role:manage 权限 | 角色权限页 | POST /api/roles | 无 | 无 | 角色、角色权限 | IMPLEMENTED |  |
| F-016 | 角色权限 | 角色维护 | 编辑角色权限 | 修改角色名称、备注并重建权限集合。 | 具备 role:manage 权限 | 角色权限页 | PUT /api/roles/{role_id} | 无 | 无 | 角色、角色权限 | IMPLEMENTED |  |
| F-017 | 设备管理 | 设备接入 | Agent 设备注册 | Android Agent 首次接入时登记设备，后续注册更新设备版本和状态。 | Android Agent | 设备列表可见 | POST /api/devices/register | 有 | 无 | 设备、版本、系统、机型、IP | IMPLEMENTED |  |
| F-018 | 设备管理 | 在线状态 | 设备心跳 | Agent 周期上报存活与版本，服务端保持任务归属为权威状态。 | Android Agent | 设备列表/顶部统计 | POST /api/devices/heartbeat | 有 | 无 | 设备、心跳、当前任务 | IMPLEMENTED | T003 - PENDING_MERGE；心跳不再覆盖服务端任务归属。 |
| F-019 | 设备管理 | 设备查询 | 设备列表与平台筛选 | 查看设备名称、平台、版本、在线状态、当前任务和运行统计。 | 具备 device:view 权限 | 设备管理页 | GET /api/devices | 无 | 无 | 设备、用户、任务 | IMPLEMENTED |  |
| F-020 | 设备管理 | 在线状态 | 离线自动判定 | 按数据库时钟和心跳超时把陈旧设备显示为离线。 | 具备 device:view 权限 | 设备管理页/顶部统计 | GET /api/devices；GET /api/dashboard/summary | 有 | 无 | 最后心跳、设备状态 | IMPLEMENTED |  |
| F-021 | 设备管理 | 设备归属 | 绑定运营人员 | 把设备绑定给运营人员；非超级管理员仅可绑定本人，单人最多两台。 | 超级管理员/业务操作员 | 设备管理页 | PUT /api/devices/{device_id}/binding | 无 | 无 | 设备、所属用户 | IMPLEMENTED |  |
| F-022 | 设备管理 | 运行策略 | 设备分组与休息参数 | 维护设备分组、连续运行分钟数和休息分钟数。 | 具备 device:manage 权限 | 设备管理页 | PUT /api/devices/{device_id}/binding | 无 | 无 | 设备分组、运行参数 | PARTIALLY_IMPLEMENTED | 字段和页面存在，但服务端 REST_LOGIC_ENABLED=False，强制休息未实际启用。 |
| F-023 | 设备管理 | 任务历史 | 查看设备历史任务 | 服务端可返回设备最近 100 条任务。 | 具备 device:view 权限 | 无明确页面入口 | GET /api/devices/{device_id}/tasks | 无 | 无 | 设备、任务 | PARTIALLY_IMPLEMENTED | API 已实现，当前 Vue 页面未调用该接口。 |
| F-024 | 设备管理 | 远程控制 | 远程终止当前任务 | 管理端终止设备当前任务，收口任务明细并向 Agent 下发停止指令。 | 具备 device:manage 权限 | 设备管理页 | POST /api/devices/{device_id}/abort-task | 有 | 无 | 设备、任务、任务项、操作日志 | IMPLEMENTED | T003 - PENDING_MERGE；校验设备任务归属。 |
| F-025 | 设备管理 | 实时监控 | 设备实时任务与日志 | 查看设备当前任务进度，并通过 WebSocket 接收新增任务日志。 | 具备 device:view 权限 | 实时监控页 | GET /api/devices；GET /api/tasks/{id}；WS /ws/realtime | 间接参与 | 无 | 设备、任务、任务日志 | IMPLEMENTED | 同时每 8 秒轮询用于状态校准。 |
| F-026 | 任务管理 | 任务创建 | 手工创建任务 | 从链接、短码或关键词列表创建采集任务。 | 具备 task:create 权限 | 创建任务页 | POST /api/tasks | 执行 | 无 | 任务、任务项、配置 | IMPLEMENTED |  |
| F-027 | 任务管理 | 任务创建 | 配置采集范围与节奏 | 设置综合前 N 个、价格/销量排序、等待区间、批次冷却和异常策略。 | 具备 task:create 权限 | 创建任务页 | POST /api/tasks | 执行 | 无 | 任务配置 JSON | IMPLEMENTED |  |
| F-028 | 任务管理 | 养号任务 | 创建账号养护任务 | 选择账号后下发只搜索和浏览、不采集入库的养护任务。 | 具备 task:create 权限 | 创建任务页 | POST /api/tasks | 执行 | 无 | 任务、平台账号、配置 | IMPLEMENTED | Android TaskEngine 存在 nurture 分支。 |
| F-029 | 任务管理 | 任务审核 | 审核通过或驳回 | 审核待下发任务；运营只能审核本人创建的任务。 | 具备 task:review 权限 | 任务列表 | POST /api/tasks/{task_id}/review | 无 | 无 | 任务审核状态、审核人 | IMPLEMENTED |  |
| F-030 | 任务管理 | 设备分配 | 指定执行设备 | 创建任务时指定在线设备，并校验运营设备归属。 | 具备 task:create 权限 | 创建任务页 | POST /api/tasks | 领取执行 | 无 | 任务、设备、创建人 | IMPLEMENTED |  |
| F-031 | 任务管理 | 任务调度 | Agent 自动领取任务 | 空闲 Agent 优先领取指定给自己的已审核任务，其次领取同平台未指定任务。 | Android Agent | 任务列表显示执行设备 | POST /api/tasks/pull | 有 | 无 | 任务、设备、任务项 | IMPLEMENTED | T003 - PENDING_MERGE；Device→Task 锁顺序，真实 Oracle 并发验收仍待环境。 |
| F-032 | 任务管理 | 任务查询 | 任务列表与状态筛选 | 按任务状态和平台查询任务，并显示结果计数、审核与设备。 | 具备 task:view 权限 | 任务调度页 | GET /api/tasks | 无 | 无 | 任务、审核、设备 | IMPLEMENTED |  |
| F-033 | 任务管理 | 任务查询 | 任务详情 | 查看任务配置、任务项、日志、异常和本次采集商品。 | 具备 task:view 权限 | 任务详情页 | GET /api/tasks/{task_id}；GET /api/products?task_id= | 无 | 无 | 任务、任务项、日志、异常、商品 | IMPLEMENTED |  |
| F-034 | 任务管理 | 进度管理 | 上报任务进度 | Agent 上报日志、关键词执行增量及任务项结果。 | Android Agent | 任务详情/实时监控 | POST /api/tasks/progress | 有 | 无 | 任务、任务项、进度回执、设备统计 | IMPLEMENTED | T003 - PENDING_MERGE；非零增量要求 progress_id 并持久化去重。 |
| F-035 | 任务管理 | 状态管理 | 服务端权威任务状态机 | 服务端集中约束 pending、running 与五类终态的合法迁移。 | 多端共同 | 任务列表/详情 | 任务相关 API | 映射本地状态 | 仅保留兼容映射 | 任务状态 | IMPLEMENTED | T003 - PENDING_MERGE；Oracle 部分成功暂存 partial_success。 |
| F-036 | 任务管理 | 状态管理 | 任务项状态管理 | 区分待处理、执行中、成功、未匹配、技术失败和取消，并禁止终态改写。 | 多端共同 | 任务详情页 | POST /api/tasks/progress；POST /api/products/upload | 有 | 无 | 任务项、商品 | IMPLEMENTED | T003 - PENDING_MERGE。 |
| F-037 | 任务管理 | 任务取消 | 取消待执行或执行中任务 | 任务创建人或超级管理员取消任务并释放设备占用。 | 任务创建人/超级管理员 | 任务详情页 | POST /api/tasks/{task_id}/cancel | 响应停止 | 无 | 任务、任务项、设备 | IMPLEMENTED | T003 - PENDING_MERGE。 |
| F-038 | 任务管理 | 任务完成 | 任务完成与结果聚合 | Agent 上报完成后，服务端依据任务项或结果计数形成成功、部分成功或失败。 | Android Agent | 任务详情页 | POST /api/tasks/finish | 有 | 无 | 任务、任务项、设备 | IMPLEMENTED | T003 - PENDING_MERGE；重复相同完成结果可幂等。 |
| F-039 | 任务管理 | 失败处理 | 失败/取消项重新下发 | 复制失败或取消任务项及匹配目标，创建一条新的待审核任务。 | 任务创建人/超级管理员 | 任务详情页 | POST /api/tasks/{task_id}/requeue-failed | 后续执行 | 无 | 原任务、新任务、任务项 | IMPLEMENTED | 原任务不回退；历史缺失目标可按祖先任务尝试恢复。 |
| F-040 | 任务管理 | 超时处理 | 超时状态表示 | 状态机可记录 timed_out，并允许前端展示与重采。 | 多端共同 | 任务列表/详情 | POST /api/tasks/finish（timed_out） | 可上报协议值 | 无 | 任务状态 | PARTIALLY_IMPLEMENTED | 没有 Task Lease、服务端超时检测或自动回收机制。T003 - PENDING_MERGE。 |
| F-041 | 商品采集 | 搜索采集 | 拼多多关键词搜索 | 在拼多多 App 中按关键词发起搜索。 | Android Agent/桌面旧工具 | 通过任务配置 | 任务领取与进度 API | 有 | 旧实现 | 关键词、搜索页 | IMPLEMENTED | 产品功能只计一次；Desktop 为同业务的 LEGACY 实现。 |
| F-042 | 商品采集 | 搜索结果 | 综合排序前 N 个 | 按综合结果逐个进入前 N 个商品详情。 | Android Agent/桌面旧工具 | 创建任务配置 | 任务配置下发 | 有 | 旧实现 | 搜索结果、采集上限 | IMPLEMENTED |  |
| F-043 | 商品采集 | 搜索排序 | 价格升序首项采集 | 按配置切换价格排序并采集首项。 | Android Agent/桌面旧工具 | 创建任务配置 | 任务配置下发 | 有 | 旧实现 | 排序方式、商品 | IMPLEMENTED |  |
| F-044 | 商品采集 | 搜索排序 | 销量降序首项采集 | 按配置切换销量排序并采集首项。 | Android Agent/桌面旧工具 | 创建任务配置 | 任务配置下发 | 有 | 旧实现 | 排序方式、商品 | IMPLEMENTED |  |
| F-045 | 商品采集 | 目标匹配 | 批准文号/品名/规格/厂家匹配 | 逐个核对目标字段，命中后停止并回填对应任务项。 | Android Agent | Excel匹配与任务详情 | progress/product API | 有 | 旧工具有独立靶标模式 | 目标字段、任务项、商品 | IMPLEMENTED |  |
| F-046 | 商品采集 | 详情采集 | 商品详情字段解析 | 解析标题、品牌、店铺、价格、销量、规格、批准文号、厂家等字段。 | Android Agent/桌面旧工具 | 商品详情查看结果 | POST /api/products/upload | 有 | 旧实现 | 商品详情字段 | PARTIALLY_IMPLEMENTED | 主要代码链完整，但 Android DetailReader 仍有 3 项已登记单测失败，真机页面兼容性未验收。 |
| F-047 | 商品采集 | SKU采集 | 多规格与多盒装价格采集 | 读取 SKU 名称、价格文本/JSON，并支持报表折算单盒价。 | Android Agent/桌面旧工具 | 商品详情/报表 | POST /api/products/upload；GET /api/reports/overview | 有 | 旧实现 | SKU、价格 | PARTIALLY_IMPLEMENTED | 解析链存在，但同受 DetailReader 已知失败与页面版本影响。 |
| F-048 | 商品采集 | 商品识别 | 商品 ID 与分享链接解析 | 从页面、分享短链和可访问数据中补齐商品 ID 与链接。 | Android Agent/桌面旧工具 | 结果字段 | POST /api/products/upload | 有 | 旧实现 | 商品 ID、URL | PARTIALLY_IMPLEMENTED | 包含多级降级路径，当前设备/页面版本的命中率未知。 |
| F-049 | 商品采集 | 图片采集 | 商品图片采集与上传 | 收集图片 URL 或本地文件，并随商品元数据/附件上传服务端。 | Android Agent | 商品详情/图片画廊 | POST /api/products/upload；POST /api/products/{id}/images | 有 | 旧实现主要保存 URL | 商品、图片文件、图片元数据 | PARTIALLY_IMPLEMENTED | 链路存在，但真机图库/分享面板采图成功率未验收；图片规则开关仍禁用。 |
| F-050 | 商品采集 | 拟人节奏 | 采集节奏与拟人动作 | 按任务配置执行操作停顿、阅读、商品间隔、关键词间隔和批次冷却。 | Android Agent/桌面旧工具 | 创建任务页 | 任务配置下发 | 有 | 旧实现 | 任务配置、运行节奏 | IMPLEMENTED |  |
| F-051 | 商品采集 | 养号执行 | 仅浏览不入库 | 养号任务执行搜索、滚动和进入首个商品，但不保存商品资料。 | Android Agent | 创建任务页/任务日志 | 任务 API | 有 | 无 | 任务、平台账号 | IMPLEMENTED |  |
| F-052 | 商品采集 | 异常策略 | 繁忙/风控/售罄处理 | 识别访问繁忙、疑似风控和售罄，按跳过、有限重试或停止策略处理。 | Android Agent | 创建任务页/任务日志 | progress/anomaly API | 有 | 旧工具有局部重试 | 异常、任务配置、日志 | IMPLEMENTED | 不是持久化 Retry Queue。 |
| F-053 | 商品数据管理 | 数据接收 | Agent 商品上报 | 接收商品字段、远端图片 URL 与任务关联，并写入草稿。 | Android Agent | 任务详情可见 | POST /api/products/upload | 有 | 无 | 商品、图片、任务、设备 | IMPLEMENTED | T003 - PENDING_MERGE；写入前校验运行任务与设备归属。 |
| F-054 | 商品数据管理 | 商品查询 | 商品库查询与筛选 | 按平台、关键词、品牌、商品 ID、批准文号查询正式商品库。 | 具备 data:view 权限 | 商品资料库 | GET /api/products | 无 | 无 | 商品、图片 | IMPLEMENTED |  |
| F-055 | 商品数据管理 | 商品查看 | 商品详情与图片/SKU查看 | 查看商品完整字段、SKU 列表、链接和图片附件。 | 具备 data:view 权限 | 商品资料库详情弹窗 | GET /api/products/{product_id} | 无 | 无 | 商品、图片 | IMPLEMENTED |  |
| F-056 | 商品数据管理 | 任务结果维护 | 编辑本次采集草稿 | 任务创建人或超级管理员可修改本次任务草稿字段。 | 任务创建人/超级管理员 | 任务详情页 | PUT /api/products/{product_id} | 无 | 无 | 商品草稿、变更记录 | IMPLEMENTED |  |
| F-057 | 商品数据管理 | 任务结果维护 | 删除本次采集草稿 | 任务创建人或超级管理员可软删除本次任务草稿。 | 任务创建人/超级管理员 | 任务详情页 | DELETE /api/products/{product_id} | 无 | 无 | 商品草稿、变更记录 | IMPLEMENTED |  |
| F-058 | 商品数据管理 | 商品入库 | 批量保存到正式商品库 | 将选中的任务草稿批量标记为正式商品资料。 | 任务创建人/超级管理员 | 任务详情页 | POST /api/products/save-batch | 无 | 无 | 商品库状态、保存人 | IMPLEMENTED |  |
| F-059 | 商品数据管理 | 正式资料维护 | 超级管理员修改或删除正式资料 | 超级管理员维护正式商品字段或软删除商品。 | 超级管理员 | 商品资料库 | PUT/DELETE /api/products/{product_id} | 无 | 无 | 正式商品、变更记录 | IMPLEMENTED |  |
| F-060 | 商品数据管理 | 变更审计 | 商品变更记录 | 服务端记录修改、删除和正式入库前后的快照。 | 管理人员 | 无独立查询页面 | 随商品维护 API 写入 | 无 | 无 | 商品变更 | PARTIALLY_IMPLEMENTED | 已写 SJZQ_PRODUCT_CHANGE，但未发现查询 API 或 Web 审计页面。 |
| F-061 | 商品数据管理 | 数据导出 | 选中商品导出 CSV | 在浏览器把选中商品字段导出为 UTF-8 CSV。 | 具备 data:export 权限 | 商品资料库 | 无，前端本地生成 | 无 | 无 | 选中商品 | IMPLEMENTED |  |
| F-062 | Excel/CSV | Excel模板 | 下载匹配模板 | 下载包含批准文号、品名、规格和生产厂家的 Excel 模板。 | 具备 excel:import 权限 | Excel匹配页 | GET /api/excel/template | 无 | 无 | 模板文件 | IMPLEMENTED |  |
| F-063 | Excel/CSV | Excel匹配 | 导入并匹配商品库 | 解析 xls/xlsx，按四个核心字段在正式商品库中匹配。 | 具备 excel:match 权限 | Excel匹配页 | POST /api/excel/match | 无 | 无 | Excel 行、商品库 | IMPLEMENTED |  |
| F-064 | Excel/CSV | 匹配复核 | 多候选查看与人工选择 | 查看多个候选商品并人工选定回填结果。 | 具备 excel:match 权限 | Excel匹配页 | 匹配 API 返回候选集 | 无 | 无 | 候选商品、匹配结果 | IMPLEMENTED |  |
| F-065 | Excel/CSV | 批量导出 | 已匹配商品批量打包 | 每个商品生成 Excel，并可附主图后打包 ZIP 下载。 | 具备 excel:export 权限 | Excel匹配页 | POST /api/excel/export-batch | 无 | 无 | 匹配结果、Excel、图片 | IMPLEMENTED |  |
| F-066 | Excel/CSV | 兼容导出 | 旧版单 Excel 匹配结果导出 | 服务端保留把全部结果导出为一个 Excel 的兼容接口。 | 具备 excel:export 权限 | 当前页面无按钮 | POST /api/excel/export-matched | 无 | 无 | 匹配结果 | PARTIALLY_IMPLEMENTED | API 存在，但当前 Vue 页面使用批量 ZIP 导出。 |
| F-067 | Excel/CSV | 补采任务 | 未匹配行转 Android 任务 | 把未匹配 Excel 行连同目标字段和原始行转为待审核采集任务。 | 具备 task:dispatch 权限 | Excel匹配页 | POST /api/excel/unmatched-to-task | 执行 | 无 | Excel 行、任务、任务项、设备 | IMPLEMENTED |  |
| F-068 | Excel/CSV | 补采回填 | Android 逐行匹配结果回填 | Agent 上报匹配成功/未匹配并在任务详情显示逐行状态。 | Android Agent/管理人员 | 任务详情页 | POST /api/tasks/progress；POST /api/products/upload | 有 | 无 | 任务项、商品 | IMPLEMENTED |  |
| F-069 | 报表与看板 | 运行看板 | 顶部运行摘要 | 显示在线设备、进行中任务、待执行任务和商品总数。 | 已登录用户 | 全局顶部栏 | GET /api/dashboard/summary | 无 | 无 | 设备、任务、商品统计 | IMPLEMENTED |  |
| F-070 | 报表与看板 | 经营分析 | 条件化报表分析 | 按平台、商品、规格、厂家、批准文号和价格范围筛选正式商品。 | 具备 report:view 权限 | 报表分析页 | GET /api/reports/overview | 无 | 无 | 正式商品 | IMPLEMENTED |  |
| F-071 | 报表与看板 | 排行分析 | 销量排行与最低价排行 | 分别查看销量靠前与价格最低的商品。 | 具备 report:view 权限 | 报表分析页 | GET /api/reports/overview | 无 | 无 | 商品、价格、销量 | IMPLEMENTED |  |
| F-072 | 报表与看板 | 价格分析 | 价格段分布 | 按可调价格区间统计商品数和销量。 | 具备 report:view 权限 | 报表分析页 | GET /api/reports/overview | 无 | 无 | 价格、商品数、销量 | IMPLEMENTED |  |
| F-073 | 报表与看板 | 规格分析 | 热门规格统计 | 服务端按规格汇总商品数和销量。 | 具备 report:view 权限 | 报表分析页 | GET /api/reports/overview | 无 | 无 | 规格、商品数、销量 | PARTIALLY_IMPLEMENTED | 服务端返回 spec_text，当前页面列绑定为 spec，存在前后端字段不一致。 |
| F-074 | 报表与看板 | 单价分析 | 多盒装单盒价 | 解析多盒 SKU 并按盒数折算、排序单盒价。 | 具备 report:view 权限 | 报表分析页 | GET /api/reports/overview | 无 | 无 | SKU、总价、盒数、单盒价 | IMPLEMENTED |  |
| F-075 | 日志与异常 | 操作审计 | 后台操作日志查询 | 按用户和动作查询登录、人员、角色、任务、商品、设备、账号、OTA 等操作。 | 具备 log:view 权限 | 操作日志页 | GET /api/op-logs | 无 | 无 | 操作日志 | IMPLEMENTED |  |
| F-076 | 日志与异常 | 个人审计 | 本人操作日志 | 用户在个人中心查看自己的最近操作。 | 已登录用户 | 个人中心 | GET /api/auth/my-logs | 无 | 无 | 操作日志 | IMPLEMENTED |  |
| F-077 | 日志与异常 | 任务日志 | 任务运行日志 | 记录任务创建、领取、进度、异常、完成和终止信息。 | 具备 task:view 权限 | 任务详情/设备实时页 | GET /api/tasks/{task_id} | 上报 | 旧工具本地日志 | 任务日志 | IMPLEMENTED |  |
| F-078 | 日志与异常 | 实时日志 | WebSocket 日志推送 | 服务端尽力广播新增任务日志，页面同时轮询校准。 | 具备 device:view 权限 | 设备实时页 | WS /ws/realtime | 触发上报 | 无 | 内存连接、任务日志 | PARTIALLY_IMPLEMENTED | 无 WS 鉴权、断线补偿或多实例广播。 |
| F-079 | 日志与异常 | 异常现场 | 任务异常记录 | Agent 上传动作、消息、页面文本和可选截图，任务详情集中查看。 | Android Agent/管理人员 | 任务详情页 | POST /api/tasks/{task_id}/anomalies；GET /api/tasks/{id} | 有 | 无 | 任务异常、截图、页面文本 | IMPLEMENTED |  |
| F-080 | 日志与异常 | 进程日志 | 各执行端本地运行日志 | Desktop 使用 Loguru，Android 使用 UI/Logcat 回调，Server 使用运行进程输出。 | 运维/执行人员 | 部分可见 | 无统一查询 API | 有 | 有 | 文件日志、Logcat、stdout | PARTIALLY_IMPLEMENTED | 缺统一结构、关联 ID、集中检索、保留与脱敏策略。 |
| F-081 | 平台账号管理 | 账号维护 | 平台账号查询与维护 | 按权限查看本人或全部平台账号，并新增、更新养护天数和状态。 | 超级管理员/业务操作员/只读人员 | 账号养护页 | GET/POST/PUT /api/accounts | 无 | 无 | 平台账号、所属用户 | IMPLEMENTED |  |
| F-082 | 平台账号管理 | 养护周期 | 到期自动转成熟 | 读取账号列表时把到达成熟日期的 nurturing 账号更新为 ready。 | 账号管理人员 | 账号养护页 | GET /api/accounts | 无 | 无 | 养护起始、天数、成熟日期 | IMPLEMENTED |  |
| F-083 | 平台账号管理 | 设备绑定 | 账号绑定所属设备 | 账号仅能绑定到同一运营名下设备。 | 超级管理员/业务操作员 | 账号养护页 | POST/PUT /api/accounts | 无 | 无 | 账号、设备、所属用户 | IMPLEMENTED |  |
| F-084 | 平台账号管理 | 异常告警 | 全部账号异常告警与确认 | 当某运营全部有效账号均异常/封禁时生成严重告警，并支持确认。 | 超级管理员/业务操作员 | 账号养护页 | GET /api/accounts/alerts；POST /alerts/{id}/ack | 无 | 无 | 账号、告警、确认人 | IMPLEMENTED |  |
| F-085 | OTA升级 | 版本包管理 | 上传 Android APK | 上传 latest.apk 并记录版本名、versionCode、大小与下载地址。 | 具备 system:config 权限 | 系统设置页 | POST /api/ota/upload | 查询 | 无 | APK、版本元数据、操作日志 | IMPLEMENTED |  |
| F-086 | OTA升级 | 升级下发 | 一键下发全部设备 | 终止合法的进行中任务，并通过设备心跳向全部 Agent 下发更新命令。 | 具备 system:config 权限 | 系统设置页 | POST /api/ota/push | 响应 | 无 | 设备、任务、APK命令 | IMPLEMENTED | T003 - PENDING_MERGE；终止前校验任务归属。 |
| F-087 | OTA升级 | Agent升级 | 下载并请求安装 APK | Agent 接收更新命令，停止本地任务、下载 APK 并调用系统安装流程。 | Android Agent | 更新提示条 | GET /api/ota/latest；POST /api/ota/ack | 有 | 无 | APK、设备版本 | PARTIALLY_IMPLEMENTED | 依赖允许安装未知应用及签名连续性；未见完整真机灰度/回滚验收。 |
| F-088 | OTA升级 | 升级状态 | 版本查询、待更新与确认 | 管理端查看当前包和待更新设备；Agent 查询最新版本并确认开始更新。 | 管理员/Android Agent | 系统设置/Agent首页 | GET /api/ota/status；GET /api/ota/latest；POST /api/ota/ack | 有 | 无 | 版本元数据、内存待更新状态 | IMPLEMENTED | 待更新状态保存在单进程内存。 |
| F-089 | 实时投屏 | 投屏发起 | 管理端请求设备投屏 | 从设备页发起投屏，命令随心跳到达 Agent。 | 具备 device:cast 权限 | 设备投屏页 | POST /api/cast/{device_id}/start | 响应 | 无 | 设备、内存投屏房间 | IMPLEMENTED |  |
| F-090 | 实时投屏 | Agent推流 | 设备画面采集与上传 | Agent 使用 MediaProjection 截取 JPEG 帧并经 WebSocket 推送。 | Android Agent | 无 | WS /ws/cast/pub/{device_key} | 有 | 无 | 屏幕帧、设备 | PARTIALLY_IMPLEMENTED | 实现链存在，但授权、性能、断线与真机稳定性未形成验收记录。 |
| F-091 | 实时投屏 | Web观看 | 浏览器实时观看设备画面 | 浏览器通过 WebSocket 接收设备 JPEG 帧并显示推流状态。 | 具备 device:view 权限 | 设备投屏页 | WS /ws/cast/view/{device_id} | 推流 | 无 | 屏幕帧、观看者 | IMPLEMENTED |  |
| F-092 | 实时投屏 | 投屏控制 | 停止投屏 | 管理端通知发布端和观看端停止，并清理请求状态。 | 具备 device:cast 权限 | 设备投屏页 | POST /api/cast/{device_id}/stop | 响应 | 无 | 投屏房间 | IMPLEMENTED |  |
| F-093 | 实时投屏 | 现场留存 | 下载当前截图与页面日志 | 浏览器本地保存当前帧 JPEG 和可见任务/投屏日志文本。 | 具备 device:view 权限 | 设备投屏页 | 无，前端本地生成 | 无 | 无 | 当前画面、可见日志 | IMPLEMENTED |  |
| F-094 | 系统配置与平台 | 服务配置 | 环境变量配置与启动校验 | 通过环境变量/.env 配置 Oracle、HTTP、JWT、图片目录和心跳超时，并校验必填值。 | 部署运维 | 无 | Server 启动配置 | 读取服务地址配置 | 旧工具独立配置 | 运行配置、Secret | IMPLEMENTED |  |
| F-095 | 系统配置与平台 | 页面配置 | 默认平台/限速/心跳页面设置 | 页面可编辑默认平台、限速和心跳值。 | 具备 system:config 权限 | 系统设置页 | 无保存 API | 无 | 无 | 页面表单 | PARTIALLY_IMPLEMENTED | 保存仅提示“后续接入”，SJZQ_SYS_CONFIG 表存在但无读写路由。 |
| F-096 | 系统配置与平台 | 平台字典 | 平台列表与启停标识 | 返回拼多多及预留平台字典，页面区分启用和预留。 | 管理人员 | 任务/商品/Excel页面 | GET /api/platforms | 使用 platform_code | 旧工具仅拼多多 | 平台字典 | PARTIALLY_IMPLEMENTED | 只有拼多多采集器；天猫/京东/抖音不构成完整平台支持。 |
| F-097 | 系统配置与平台 | 健康检查 | 服务健康信息 | 返回服务进程可响应、Oracle DSN、图片目录、Web构建与 OCR 可用标记。 | 运维/Agent | 系统设置/Agent连接测试 | GET /api/health | 有 | 无 | 运行配置、OCR状态 | PARTIALLY_IMPLEMENTED | 未实际探测 Oracle 连接，也不是分离的 liveness/readiness。 |
| F-098 | 系统配置与平台 | 数据结构 | Oracle 初始化与启动补丁 | 初始化核心/RBAC表，并在启动时补充任务、账号、告警、异常、商品库视图等结构。 | 部署运维 | 无 | 初始化/启动过程 | 无 | 无 | Oracle表、序列、视图 | IMPLEMENTED | 属于轻量补丁，尚非正式版本化 migration 体系。 |
| F-099 | Android Agent | 独立采集 | 手机端手工启动采集 | 在 Agent 本地输入关键词和采集范围，不依赖 Web 任务即可执行。 | 设备操作员 | 无 | 无 | 本地首页 | 无 | 本地任务、配置 | IMPLEMENTED |  |
| F-100 | Android Agent | 本地存储 | Room 保存任务和商品 | 本地保存任务执行记录与采集商品。 | 设备操作员 | 无 | 无 | Room | 无 | 本地任务、商品 | IMPLEMENTED |  |
| F-101 | Android Agent | 本地导出 | 导出并分享任务 CSV | 把本地任务商品导出为 CSV 并调用系统分享。 | 设备操作员 | 无 | 无 | 本地首页 | 无 | CSV、商品 | IMPLEMENTED |  |
| F-102 | Android Agent | 联机设置 | 配置并测试 Server 连接 | 配置主机、端口、设备名、设备键、平台和联机开关，并探测健康接口。 | 设备操作员 | 无 | GET /api/health | 设置页 | 无 | SharedPreferences、设备键 | IMPLEMENTED |  |
| F-103 | Android Agent | 运行前置 | 无障碍/通知/电池与安装权限引导 | 声明并引导采集、前台服务、投屏、通知和 APK 安装所需权限。 | 设备操作员 | 无 | 无 | 系统设置/Manifest | 无 | Android权限 | PARTIALLY_IMPLEMENTED | 代码与清单存在，但不同机型权限流程的实际完成度需真机确认。 |
| F-104 | Desktop Legacy | 桌面工作台 | PyQt6 桌面采集工作台 | 通过桌面 GUI 配置、启动、停止任务并查看日志和历史。 | 旧桌面操作员 | 无 | 未接 Server | 无 | 有 | 本地任务、配置 | LEGACY | 旧链路与当前 Web→Server→Android 链路并存。 |
| F-105 | Desktop Legacy | 浏览器接入 | BitBrowser 环境接管 | 调用本地 BitBrowser API 并通过 Playwright CDP 接管已登录页面。 | 旧桌面操作员 | 无 | 未接 Server | 无 | 有 | 浏览器环境、CDP会话 | LEGACY |  |
| F-106 | Desktop Legacy | 本地任务 | 关键词采集任务 | 在桌面端本地执行拼多多搜索、排序和详情采集。 | 旧桌面操作员 | 无 | 未接 Server | 无 | 有 | 任务、商品 | LEGACY | 与商品采集模块业务重复，因此不作为第二套产品采集能力重复统计。 |
| F-107 | Desktop Legacy | Excel靶标 | Excel目标任务与续跑 | 读取 Excel 目标，按批准文号/规格匹配，并以 checkpoint 续跑未完成行。 | 旧桌面操作员 | 无 | 未接 Server | 无 | 有 | Excel任务、行状态 | LEGACY |  |
| F-108 | Desktop Legacy | 本地存储 | SQLite 增量落库 | 把桌面任务、商品和 Excel checkpoint 保存到 workbench.db。 | 旧桌面操作员 | 无 | 未接 Server | 无 | 有 | SQLite任务、商品、Excel行 | LEGACY |  |
| F-109 | Desktop Legacy | 本地导出 | Excel/CSV 导出 | 把桌面任务结果导出为 xlsx 或 CSV。 | 旧桌面操作员 | 无 | 未接 Server | 无 | 有 | 商品、导出文件 | LEGACY |  |
| F-110 | Desktop Legacy | 桌面配置 | 采集与浏览器配置 | 维护 BitBrowser API、节奏、排序、过滤、重试和输出目录。 | 旧桌面操作员 | 无 | 未接 Server | 无 | 有 | config.json | LEGACY |  |
| F-111 | 规划中能力 | 任务可靠性 | Task Lease 与续租 | 为运行任务建立租约、续租和过期判定。 | 待定 | 无 | 无 | 无 | 无 | 租约、执行尝试 | PLANNED | 来源：docs/gap-analysis.md、docs/backlog.md、docs/roadmap.md。 |
| F-112 | 规划中能力 | 任务可靠性 | 超时自动回收与 reconciliation | 服务端检测卡死任务并安全回收设备与任务。 | 待定 | 无 | 无 | 无 | 无 | 任务、设备、执行尝试 | PLANNED | 当前只有 timed_out 状态，没有自动产生机制。 |
| F-113 | 规划中能力 | 可靠上报 | Android 持久化 Outbox | 持久化待上报 progress/product/finish，并在重启后重放。 | 待定 | 无 | 无 | 无 | 无 | 待上报事件 | PLANNED | 来源：BL-008。 |
| F-114 | 规划中能力 | 失败处理 | Retry Queue 与退避策略 | 按错误类型、次数和退避策略持久化重试。 | 待定 | 无 | 无 | 无 | 无 | 重试任务、错误分类 | PLANNED | 当前只有局部有限重试和人工重采。 |
| F-115 | 规划中能力 | 失败处理 | Dead Letter Queue | 把超过重试策略的事件进入人工处理队列。 | 待定 | 无 | 无 | 无 | 无 | 死信、人工处置 | PLANNED | 来源：Gap/Roadmap。 |
| F-116 | 规划中能力 | 性能扩展 | Redis/通用缓存 | 建立缓存接口、键规范、TTL、失效和监控。 | 待定 | 无 | 无 | 无 | 无 | 缓存键值 | PLANNED | 当前无通用缓存；投屏/WS内存状态不等同于缓存体系。 |
| F-117 | 规划中能力 | 可观测性 | 完整指标、告警、追踪与 SLO | 覆盖服务、Oracle、任务、设备、质量、存储和告警处置。 | 待定 | 无 | 无 | 无 | 无 | 指标、追踪、告警 | PLANNED | 当前健康、心跳、日志和看板不等同完整监控。 |
| F-118 | 规划中能力 | 工程保障 | CI/CD 与发布门禁 | 建立自动构建、测试、制品、灰度与回滚门禁。 | 待定 | 无 | 无 | 无 | 无 | 构建与发布记录 | PLANNED | 仓库当前未发现 CI 配置。 |
| F-119 | 规划中能力 | 多平台 | 天猫/京东/抖音完整采集适配 | 为每个平台建立独立采集器、字段契约和验收。 | 待定 | 预留字典 | 预留字典 | 无 | 无 | 平台适配 | PLANNED | 现有常量、种子和下拉项不能视为已支持。 |
| F-120 | 规划中能力 | 数据治理 | 正式迁移、备份恢复与质量闭环 | 建立版本化 schema migration、备份恢复、去重和字段质量规则。 | 待定 | 无 | 无 | 无 | 无 | Schema、备份、质量结果 | PLANNED | 来源：Gap/Roadmap。 |
| F-121 | 待确认事项 | 运行基线 | 当前 Oracle 实际结构与数据 | 仅凭仓库无法确认部署库已执行全部初始化/补丁、数据量和索引状态。 | 项目负责人/DBA | 未知 | 未知 | 未知 | 未知 | Oracle实例 | UNKNOWN | 需用隔离或已授权环境核验，不把源码 DDL 当作部署事实。 |
| F-122 | 待确认事项 | 真机兼容 | 当前拼多多版本真机采集成功率 | 无法从仓库确认现网机型、App版本、页面结构和字段命中率。 | 项目负责人/设备负责人 | 无 | 无 | 未知 | 未知 | 真机、App版本、样本结果 | UNKNOWN |  |
| F-123 | 待确认事项 | 旧链路定位 | Desktop 是否仍属于正式交付 | 代码完整保留，但未发现其接入当前 Server/Oracle 调度的实现或明确退役决定。 | 项目负责人 | 无 | 无 | 无 | 未知 | 部署与使用记录 | UNKNOWN |  |
| F-124 | 待确认事项 | 发布状态 | 当前部署版本与 T003 验收状态 | 当前分支含 T003 且未合并 main；实际部署是否包含这些提交无法从仓库确认。 | 项目负责人/发布负责人 | 未知 | 未知 | 未知 | 未知 | 部署制品、提交、版本 | UNKNOWN |  |
| F-125 | 待确认事项 | 数据质量 | 现有商品数据准确率与重复率 | 代码有字段采集和匹配，但缺现网样本质量报告、去重口径和验收阈值。 | 项目负责人/业务负责人 | 未知 | 未知 | 未知 | 未知 | 商品库、质量样本 | UNKNOWN |  |

## 5. Web 管理端功能

Web 已形成登录、设备、任务、商品、Excel、账号、报表、人员、角色、日志、设置、个人中心和投屏页面。对应功能 ID：F-001、F-002、F-003、F-004、F-005、F-006、F-007、F-008、F-009、F-010、F-011、F-013、F-014、F-015、F-016、F-017、F-018、F-019、F-020、F-021、F-022、F-023、F-024、F-025、F-026、F-027、F-028、F-029、F-030、F-031、F-032、F-033、F-034、F-035、F-036、F-037、F-038、F-039、F-040、F-041、F-042、F-043、F-044、F-045、F-046、F-047、F-048、F-049、F-050、F-051、F-052、F-053、F-054、F-055、F-056、F-057、F-058、F-059、F-060、F-061、F-062、F-063、F-064、F-065、F-066、F-067、F-068、F-069、F-070、F-071、F-072、F-073、F-074、F-075、F-076、F-077、F-078、F-079、F-080、F-081、F-082、F-083、F-084、F-085、F-086、F-087、F-088、F-089、F-091、F-092、F-093、F-095、F-096、F-097。

需注意：系统设置的通用配置保存、设备历史任务入口、商品变更审计页面和旧版单 Excel 导出没有形成当前 Web 完整链路；具体见部分实现清单。

## 6. Android Agent 功能

Android 同时具有两种使用方式：

1. **联机 Agent**：注册→心跳→领取已审核任务→执行拼多多搜索/详情/目标匹配→上报商品/图片/进度/异常→完成；同时接收终止、投屏和 OTA 命令。
2. **本地独立模式**：设备上手工输入关键词并采集，结果写 Room，可导出 CSV。

对应功能 ID：F-017、F-018、F-020、F-024、F-025、F-026、F-027、F-028、F-030、F-031、F-034、F-035、F-036、F-037、F-038、F-039、F-040、F-041、F-042、F-043、F-044、F-045、F-046、F-047、F-048、F-049、F-050、F-051、F-052、F-053、F-067、F-068、F-077、F-078、F-079、F-080、F-085、F-086、F-087、F-088、F-089、F-090、F-091、F-092、F-094、F-096、F-097、F-099、F-100、F-101、F-102、F-103。Android 构建和部分单元测试有现存记录，但当前拼多多版本的真机端到端成功率仍是 UNKNOWN。

## 7. Server 后台能力

Server 提供 JWT/RBAC、Oracle 访问、业务路由、任务状态、设备权威归属、商品/图片存储、Excel 处理、报表、日志、OTA、WebSocket、静态资源和启动补丁。主要 API 已在完整清单逐项列出。T003 引入的状态机、锁顺序、进度回执、终态保护与客户端状态映射均标注 `T003 - PENDING_MERGE`；真实 Oracle 多连接并发套件仍受隔离测试环境阻塞。

## 8. Desktop Legacy 功能

Desktop 是 `PyQt6 + BitBrowser + Playwright + SQLite + Excel/CSV` 的独立旧链路。它与 Android 都能完成拼多多搜索/详情采集，但这是同一产品采集能力的两种实现，未重复计算为两个业务功能。Desktop 未调用当前 `/api/tasks`、`/api/products` 或 Oracle 调度接口；T003 仅增加隔离状态映射。Legacy 功能：F-104、F-105、F-106、F-107、F-108、F-109、F-110。

## 9. 端到端核心业务流程

### 9.1 Web → Server → Android 任务链

```text
Web 创建任务
→ Server 写任务/任务项（pending + review pending）
→ Web 审核 approved
→ Android 注册/心跳并 pull
→ Server 锁定设备与任务、写 running/设备占用
→ Android 执行搜索/详情/匹配
→ Android progress/product/images/anomalies
→ Server 写 Oracle、任务项、日志和图片文件
→ Android finish
→ Server 聚合终态并释放设备
→ Web 查看任务、商品和异常
```

### 9.2 Excel 未匹配补采链

```text
Web 导入 Excel
→ Server 对正式商品库匹配
→ Web 人工选择多候选并导出已匹配项
→ 未匹配行选择设备并转任务
→ 审核
→ Android 按批准文号+品名+规格+厂家核对
→ Server 回填任务项与商品草稿
→ Web 修改/删除草稿并批量保存正式商品库
```

### 9.3 OTA 链

```text
Web 上传 APK
→ Server 保存版本元数据
→ Web 一键下发
→ Server 合法终止进行中任务并在内存登记命令
→ Android 心跳取得命令
→ Android 停止任务、下载并请求系统安装
→ Android ack
→ Web 查看待更新状态
```

### 9.4 投屏链

```text
Web 请求投屏
→ Server 在内存投屏房间登记请求
→ Android 心跳取得投屏命令
→ Android MediaProjection 采帧并通过发布 WebSocket 上行
→ Server 转发 JPEG 帧
→ Web 观看 WebSocket 展示、截图或停止
```

## 10. 部分实现功能

| 功能ID | 一级模块 | 二级模块 | 功能名称 | 功能说明 | 备注 |
|---|---|---|---|---|---|
| F-022 | 设备管理 | 运行策略 | 设备分组与休息参数 | 维护设备分组、连续运行分钟数和休息分钟数。 | 字段和页面存在，但服务端 REST_LOGIC_ENABLED=False，强制休息未实际启用。 |
| F-023 | 设备管理 | 任务历史 | 查看设备历史任务 | 服务端可返回设备最近 100 条任务。 | API 已实现，当前 Vue 页面未调用该接口。 |
| F-040 | 任务管理 | 超时处理 | 超时状态表示 | 状态机可记录 timed_out，并允许前端展示与重采。 | 没有 Task Lease、服务端超时检测或自动回收机制。T003 - PENDING_MERGE。 |
| F-046 | 商品采集 | 详情采集 | 商品详情字段解析 | 解析标题、品牌、店铺、价格、销量、规格、批准文号、厂家等字段。 | 主要代码链完整，但 Android DetailReader 仍有 3 项已登记单测失败，真机页面兼容性未验收。 |
| F-047 | 商品采集 | SKU采集 | 多规格与多盒装价格采集 | 读取 SKU 名称、价格文本/JSON，并支持报表折算单盒价。 | 解析链存在，但同受 DetailReader 已知失败与页面版本影响。 |
| F-048 | 商品采集 | 商品识别 | 商品 ID 与分享链接解析 | 从页面、分享短链和可访问数据中补齐商品 ID 与链接。 | 包含多级降级路径，当前设备/页面版本的命中率未知。 |
| F-049 | 商品采集 | 图片采集 | 商品图片采集与上传 | 收集图片 URL 或本地文件，并随商品元数据/附件上传服务端。 | 链路存在，但真机图库/分享面板采图成功率未验收；图片规则开关仍禁用。 |
| F-060 | 商品数据管理 | 变更审计 | 商品变更记录 | 服务端记录修改、删除和正式入库前后的快照。 | 已写 SJZQ_PRODUCT_CHANGE，但未发现查询 API 或 Web 审计页面。 |
| F-066 | Excel/CSV | 兼容导出 | 旧版单 Excel 匹配结果导出 | 服务端保留把全部结果导出为一个 Excel 的兼容接口。 | API 存在，但当前 Vue 页面使用批量 ZIP 导出。 |
| F-073 | 报表与看板 | 规格分析 | 热门规格统计 | 服务端按规格汇总商品数和销量。 | 服务端返回 spec_text，当前页面列绑定为 spec，存在前后端字段不一致。 |
| F-078 | 日志与异常 | 实时日志 | WebSocket 日志推送 | 服务端尽力广播新增任务日志，页面同时轮询校准。 | 无 WS 鉴权、断线补偿或多实例广播。 |
| F-080 | 日志与异常 | 进程日志 | 各执行端本地运行日志 | Desktop 使用 Loguru，Android 使用 UI/Logcat 回调，Server 使用运行进程输出。 | 缺统一结构、关联 ID、集中检索、保留与脱敏策略。 |
| F-087 | OTA升级 | Agent升级 | 下载并请求安装 APK | Agent 接收更新命令，停止本地任务、下载 APK 并调用系统安装流程。 | 依赖允许安装未知应用及签名连续性；未见完整真机灰度/回滚验收。 |
| F-090 | 实时投屏 | Agent推流 | 设备画面采集与上传 | Agent 使用 MediaProjection 截取 JPEG 帧并经 WebSocket 推送。 | 实现链存在，但授权、性能、断线与真机稳定性未形成验收记录。 |
| F-095 | 系统配置与平台 | 页面配置 | 默认平台/限速/心跳页面设置 | 页面可编辑默认平台、限速和心跳值。 | 保存仅提示“后续接入”，SJZQ_SYS_CONFIG 表存在但无读写路由。 |
| F-096 | 系统配置与平台 | 平台字典 | 平台列表与启停标识 | 返回拼多多及预留平台字典，页面区分启用和预留。 | 只有拼多多采集器；天猫/京东/抖音不构成完整平台支持。 |
| F-097 | 系统配置与平台 | 健康检查 | 服务健康信息 | 返回服务进程可响应、Oracle DSN、图片目录、Web构建与 OCR 可用标记。 | 未实际探测 Oracle 连接，也不是分离的 liveness/readiness。 |
| F-103 | Android Agent | 运行前置 | 无障碍/通知/电池与安装权限引导 | 声明并引导采集、前台服务、投屏、通知和 APK 安装所需权限。 | 代码与清单存在，但不同机型权限流程的实际完成度需真机确认。 |

## 11. Legacy 功能

| 功能ID | 一级模块 | 二级模块 | 功能名称 | 功能说明 | 备注 |
|---|---|---|---|---|---|
| F-104 | Desktop Legacy | 桌面工作台 | PyQt6 桌面采集工作台 | 通过桌面 GUI 配置、启动、停止任务并查看日志和历史。 | 旧链路与当前 Web→Server→Android 链路并存。 |
| F-105 | Desktop Legacy | 浏览器接入 | BitBrowser 环境接管 | 调用本地 BitBrowser API 并通过 Playwright CDP 接管已登录页面。 |  |
| F-106 | Desktop Legacy | 本地任务 | 关键词采集任务 | 在桌面端本地执行拼多多搜索、排序和详情采集。 | 与商品采集模块业务重复，因此不作为第二套产品采集能力重复统计。 |
| F-107 | Desktop Legacy | Excel靶标 | Excel目标任务与续跑 | 读取 Excel 目标，按批准文号/规格匹配，并以 checkpoint 续跑未完成行。 |  |
| F-108 | Desktop Legacy | 本地存储 | SQLite 增量落库 | 把桌面任务、商品和 Excel checkpoint 保存到 workbench.db。 |  |
| F-109 | Desktop Legacy | 本地导出 | Excel/CSV 导出 | 把桌面任务结果导出为 xlsx 或 CSV。 |  |
| F-110 | Desktop Legacy | 桌面配置 | 采集与浏览器配置 | 维护 BitBrowser API、节奏、排序、过滤、重试和输出目录。 |  |

## 12. 规划中功能

以下项目来源于 `docs/gap-analysis.md`、`docs/backlog.md` 和 `docs/roadmap.md`，未混入当前已实现功能。

| 功能ID | 一级模块 | 二级模块 | 功能名称 | 功能说明 | 当前状态 | 备注 |
|---|---|---|---|---|---|---|
| F-111 | 规划中能力 | 任务可靠性 | Task Lease 与续租 | 为运行任务建立租约、续租和过期判定。 | PLANNED | 来源：docs/gap-analysis.md、docs/backlog.md、docs/roadmap.md。 |
| F-112 | 规划中能力 | 任务可靠性 | 超时自动回收与 reconciliation | 服务端检测卡死任务并安全回收设备与任务。 | PLANNED | 当前只有 timed_out 状态，没有自动产生机制。 |
| F-113 | 规划中能力 | 可靠上报 | Android 持久化 Outbox | 持久化待上报 progress/product/finish，并在重启后重放。 | PLANNED | 来源：BL-008。 |
| F-114 | 规划中能力 | 失败处理 | Retry Queue 与退避策略 | 按错误类型、次数和退避策略持久化重试。 | PLANNED | 当前只有局部有限重试和人工重采。 |
| F-115 | 规划中能力 | 失败处理 | Dead Letter Queue | 把超过重试策略的事件进入人工处理队列。 | PLANNED | 来源：Gap/Roadmap。 |
| F-116 | 规划中能力 | 性能扩展 | Redis/通用缓存 | 建立缓存接口、键规范、TTL、失效和监控。 | PLANNED | 当前无通用缓存；投屏/WS内存状态不等同于缓存体系。 |
| F-117 | 规划中能力 | 可观测性 | 完整指标、告警、追踪与 SLO | 覆盖服务、Oracle、任务、设备、质量、存储和告警处置。 | PLANNED | 当前健康、心跳、日志和看板不等同完整监控。 |
| F-118 | 规划中能力 | 工程保障 | CI/CD 与发布门禁 | 建立自动构建、测试、制品、灰度与回滚门禁。 | PLANNED | 仓库当前未发现 CI 配置。 |
| F-119 | 规划中能力 | 多平台 | 天猫/京东/抖音完整采集适配 | 为每个平台建立独立采集器、字段契约和验收。 | PLANNED | 现有常量、种子和下拉项不能视为已支持。 |
| F-120 | 规划中能力 | 数据治理 | 正式迁移、备份恢复与质量闭环 | 建立版本化 schema migration、备份恢复、去重和字段质量规则。 | PLANNED | 来源：Gap/Roadmap。 |

## 13. UNKNOWN 事项

| 功能ID | 一级模块 | 二级模块 | 功能名称 | 功能说明 | 当前状态 | 备注 |
|---|---|---|---|---|---|---|
| F-121 | 待确认事项 | 运行基线 | 当前 Oracle 实际结构与数据 | 仅凭仓库无法确认部署库已执行全部初始化/补丁、数据量和索引状态。 | UNKNOWN | 需用隔离或已授权环境核验，不把源码 DDL 当作部署事实。 |
| F-122 | 待确认事项 | 真机兼容 | 当前拼多多版本真机采集成功率 | 无法从仓库确认现网机型、App版本、页面结构和字段命中率。 | UNKNOWN |  |
| F-123 | 待确认事项 | 旧链路定位 | Desktop 是否仍属于正式交付 | 代码完整保留，但未发现其接入当前 Server/Oracle 调度的实现或明确退役决定。 | UNKNOWN |  |
| F-124 | 待确认事项 | 发布状态 | 当前部署版本与 T003 验收状态 | 当前分支含 T003 且未合并 main；实际部署是否包含这些提交无法从仓库确认。 | UNKNOWN |  |
| F-125 | 待确认事项 | 数据质量 | 现有商品数据准确率与重复率 | 代码有字段采集和匹配，但缺现网样本质量报告、去重口径和验收阈值。 | UNKNOWN |  |

## 14. 当前功能统计

| 统计项 | 数量 |
|---|---:|
| 一级业务模块（不含规划/待确认分组） | 16 |
| 二级模块（不含规划/待确认分组） | 100 |
| 总清单功能点（含 PLANNED/UNKNOWN） | 125 |
| 当前确认已有功能点（IMPLEMENTED + PARTIALLY_IMPLEMENTED + LEGACY） | 110 |
| IMPLEMENTED | 85 |
| PARTIALLY_IMPLEMENTED | 18 |
| LEGACY | 7 |
| PLANNED（不计入当前已有） | 10 |
| UNKNOWN | 5 |

### 14.1 统计解释

- Android 与 Desktop 对同一“拼多多搜索/详情采集”业务只记一次；Desktop 只在其独立交付方式、本地存储、续跑和导出等条目中记为 `LEGACY`。
- `PLANNED` 不进入当前已有功能数量。
- `UNKNOWN` 不等同于未实现，只表示仓库不能证明其实际运行状态。
