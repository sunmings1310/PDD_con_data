# 拼多多采集助手（Android 独立 App）

真机侧载 APK，通过**无障碍服务**驱动已登录的「拼多多」App，完成：

1. 关键词搜索 → 综合排序前 N 个详情  
2. 可选：价格排序第 1 个  
3. 可选：销量排序第 1 个  

字段与桌面版导出列对齐，结果落本地 Room，可导出 CSV。

## 环境要求

- JDK 17
- Gradle Wrapper 8.4（随仓库提供）
- Android Gradle Plugin 8.1.4
- Android SDK Platform 34、Build Tools 34.0.0、Platform Tools
- Android Studio Hedgehog 或兼容上述工具链的版本
- 真机 Android 8.0+（API 26+）
- 手机已安装并**登录**拼多多（包名 `com.xunmeng.pinduoduo`）

## 打开与编译

1. 用 Android Studio 打开目录 `android_collector/`
2. 确认 Android Studio 使用 JDK 17，并等待 Gradle Sync（首次会下载依赖）
3. 连接真机，Run → `app`
4. 或：`Build` → `Build Bundle(s) / APK(s)` → `Build APK(s)`，安装 `app/build/outputs/apk/debug/app-debug.apk`

本机若未装 SDK，请先安装 Android Studio 再编译。

命令行构建：

```powershell
$env:JAVA_HOME = '<JDK 17 目录>'
$env:ANDROID_SDK_ROOT = '<Android SDK 目录>'
Copy-Item local.properties.example local.properties
# 编辑 local.properties 中的 sdk.dir 后执行：
.\gradlew.bat assembleDebug testDebugUnitTest --no-daemon
```

也可在设置好上述环境变量后运行 `.\build-apk.ps1`；产物写入 `dist/PddCollector-debug.apk`。

## Release 签名

Release 签名不再保存在源码或公共 `gradle.properties` 中。仅在执行 release
任务时，必须通过 Gradle project property（`-P...`）或对应环境变量提供：

| Gradle property | 环境变量 | 用途 |
|---|---|---|
| `RELEASE_STORE_FILE` | `ANDROID_RELEASE_STORE_FILE` | keystore 外部路径 |
| `RELEASE_STORE_PASSWORD` | `ANDROID_RELEASE_STORE_PASSWORD` | keystore 口令 |
| `RELEASE_KEY_ALIAS` | `ANDROID_RELEASE_KEY_ALIAS` | key alias |
| `RELEASE_KEY_PASSWORD` | `ANDROID_RELEASE_KEY_PASSWORD` | key 口令 |

缺少任一字段或 keystore 文件不存在时，release 构建在配置阶段失败且不输出
Secret。`assembleDebug` 不依赖这些变量。已有 APK 升级必须沿用原签名证书；
签名口令必须轮换，但在发布历史确认前不要擅自更换 keystore/key。

## 使用步骤

1. 打开本 App →「去开启」无障碍 → 打开「拼多多采集助手」
2. （推荐）忽略电池优化
3. 确认拼多多已登录
4. 输入关键词（每行一个），设置 N，按需打开价格/销量开关（默认关）
5. 点「开始」，勿遮挡屏幕；任务日志带 `[时:分:秒]`
6. 结束后点「导出当前任务 CSV」分享/保存

## 工程结构

```
app/src/main/java/com/collector/pdd/
  ui/           配置页与日志
  service/      无障碍服务与节点工具
  engine/       任务状态机、拼多多操作
  parser/       详情文本解析（对齐桌面语义）
  data/         Room 实体
  export/       CSV 导出
```

## 注意

- 拼多多改版可能导致文案定位失效，需调整 `PddActions` / `DetailReader`
- 排序开关会增加点击与刷新，风控压力高于纯综合
- 仅供本人设备、合规采集场景使用
