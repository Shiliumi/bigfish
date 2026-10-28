# 大肥鱼 · Bigfish

住在 Mac 里的蓝色小鲸鱼：可以聊天、带着好奇心浏览公开网页、整理长期记忆，也会从屏幕边缘探头，偶尔带一条消息回来。

基于 [Hermes Agent](https://github.com/NousResearch/hermes-agent)、模型 API 和本地浏览器。原生应用使用 AppKit / WebKit / AVFoundation；内部界面使用 React + TypeScript + Vite，本地服务使用 Node.js。支持 DeepSeek 官方 API 和 OpenAI 兼容的 Chat Completions API。非 DeepSeek 官方产品。

## 可以做什么

- **聊天与记忆**：流式回复、历史会话、长期记忆、用户画像、可编辑人设与兴趣。
- **兴趣驱动的冲浪**：沿作品、作者和未完问题继续探索，记录真实阅读证据；允许换方向、休息或什么都不分享。
- **慢慢形成表达习惯**：区分临时兴趣和长期性格，用跨链接、平台和日期的观察支持小幅调整。
- **桌宠**：16 组完整透明动画、拖动、多显示器边缘吸附、专门绘制的探头姿态、消息气泡和展开互动。
- **主动来信**：值得聊的发现、早晚问候、真实余额不足时的鱼粮提醒；本地去重与限频。
- **表情包**：按话题收藏和发送鲸鱼娘表情，记录作者、用途和来源。
- **应用内控制室**：任务、工具组、技能、全部来源的历史会话与全文检索。
- **模型设置**：自定义 API 地址和密钥、读取模型列表、手动填写模型 ID、实际生成连通性测试。

默认是“爸爸与爱冲浪的小鲸鱼女儿”的 AI 角色互动。可编辑 `config/SOUL.md` 与 `INTERESTS.md` 改成自己喜欢的相处方式。人格成长是持久提示词与记忆的更新，不是训练模型。

抖音不接账号、不读取登录态。仅尝试可直接读取的公开页面，遇到登录墙或验证码会换方向；不自动发布、评论或私信。视频内容按实际取得的正文、字幕、文案和评论理解。

## 安装（macOS 源码版）

要求 macOS 13+、Xcode Command Line Tools、Git、Python 3.10+、Node.js 22+ / npm，以及 [GitHub CLI](https://cli.github.com/)。本机开发验证使用 Apple Silicon；其他架构尚未完整验证。模型须支持工具调用。当前仓库提供源码与桌宠素材包，未提供公证的通用安装包；构建应用会绑定这个项目的数据目录。

### 1. 克隆与准备

私有仓库需要先执行 `gh auth login`：

```bash
gh repo clone Shiliumi/bigfish
cd bigfish
npm ci --prefix ui
python3 scripts/restore_pet_assets.py
```

32 个视频约 248 MiB，放在 `v1.6.0` Release 的 `bigfish-pet-v1.6.0.tar.gz` 中，不进入 Git 历史。恢复脚本核对整个压缩包和逐文件 SHA-256，拒绝路径、链接和非预期文件。透明探头图片、海报、清单与署名直接保存在仓库。

也可以手动下载 Release 后执行：

```bash
python3 scripts/restore_pet_assets.py --archive /path/to/bigfish-pet-v1.6.0.tar.gz
python3 scripts/restore_pet_assets.py --check
```

### 2. 安装独立 Hermes 运行时

本项目使用独立的 `HERMES_HOME`，不会共享你其他 Hermes 的记忆和密钥。以下从上游固定版本获取安装脚本；先查看脚本再执行。已联调版本记录在 `config/runtime.json`，上游升级后需要重新验证内部 API 兼容性。

```bash
mkdir -p .setup .runtime
curl -fL https://raw.githubusercontent.com/NousResearch/hermes-agent/bf0203a794a07aac3ff764972ab9087baa4e4f4e/scripts/install.sh -o .setup/install-hermes.sh
less .setup/install-hermes.sh
HERMES_HOME="$PWD/.hermes" HERMES_INSTALL_DIR="$PWD/.runtime/hermes-agent" bash .setup/install-hermes.sh --commit bf0203a794a07aac3ff764972ab9087baa4e4f4e --skip-setup
python3 scripts/setup_profile.py
python3 scripts/install_memory.py --activate
```

安装器可能下载自己的 Python、Node 和浏览器依赖，具体要求见 [Hermes 安装文档](https://hermes-agent.nousresearch.com/docs/getting-started/installation)。运行时不随仓库分发。不要在已有使用数据的目录中重复应用初始模板：`setup_profile.py` 会覆盖当前配置及手动人设，保留核心记忆、密钥和已形成的自动成长区。

### 3. 配置、构建与启动

初次使用 DeepSeek 官方 API，可以在终端的隐藏输入框中配置密钥：

```bash
python3 scripts/configure_key.py
```

其他兼容服务也可以等应用打开后，在「偏好设置」填写地址、密钥和模型。密钥只保存在本机 `.hermes/.env`；不要写进源码、Git 或聊天消息。`.env.example` 仅展示格式，不参与运行。

```bash
npm run build --prefix ui
python3 scripts/build_app.py
python3 scripts/setup_jobs.py
python3 scripts/service.py install
open 大肥鱼.app
```

`build_app.py` 编译并安装到可写的 `/Applications` 或 `~/Applications`，注册 `bigfish://` 链接和登录后后台启动。关闭主窗口后继续接收本地来信；菜单「退出大肥鱼」退出应用。首次使用可能需要在系统弹窗允许文稿访问与通知。后台活动需要电脑开机、登录并保持唤醒，睡眠期间不补跑过期活动。

应用内部连接 `127.0.0.1:9120`，Hermes 内部接口在 `127.0.0.1:9119`。界面仅允许原生应用建立会话，普通浏览器入口已停用。请保留项目目录的位置，移动后需重新构建应用和安装项目登录服务。

## 日常使用

| 入口 | 用途 |
| --- | --- |
| `打开大肥鱼.command` | 打开原生应用 |
| `配置模型.command` | 模型设置、列表选择与连通性测试 |
| `打开控制台.command` | Hermes 控制室 |
| `立即冲浪.command` | 手动触发冲浪决策 |
| `查看状态.command` | 后台状态 |
| `暂停自动活动.command` / `恢复自动活动.command` | 暂停或恢复日常任务 |
| `停止后台.command` / `启动后台.command` | 管理独立 Hermes 后台 |

每日 09、12、15、18、21 点是出发机会，实际浏览最多三次、至少间隔两小时；22:30 整理记忆。时间使用 Asia/Shanghai。分享资讯每天最多两条、至少间隔四小时；早晚问候另计。正在聊天、夜间与重复内容会延后或跳过，不因未回复而催促。

设置里的「主动分享」控制新来信，不会自动停止记忆整理。任务与限制可在 `config/` 和应用面板调整。实际用量以模型服务商账单为准，工具轮数和时限并非金额上限。

```bash
./scripts/fish chat
./scripts/fish cron list
python3 scripts/service.py status
python3 scripts/personality.py status
python3 scripts/stickers.py search 开心 --limit 5
```

## 开发与验证

```bash
npm ci --prefix ui
npm run build --prefix ui
python3 -m unittest discover -s scripts -p 'test_*.py'
```

接口集成测试需要已经初始化并运行的本机 Hermes 和界面服务；它们不能直接在空仓库上运行：

```bash
python3 scripts/ui.py --no-open
node --test ui/tests/*.test.mjs
```

原生几何与行为测试：

```bash
swiftc desktop/PetDock.swift scripts/test_pet_dock.swift -o /tmp/bigfish-test-dock && /tmp/bigfish-test-dock
swiftc desktop/PetDock.swift desktop/PetPeek.swift scripts/test_pet_peek.swift -o /tmp/bigfish-test-peek && /tmp/bigfish-test-peek
swiftc desktop/PetBehavior.swift scripts/test_pet_behavior.swift -o /tmp/bigfish-test-behavior && /tmp/bigfish-test-behavior
```

更新界面后重新执行 `npm run build --prefix ui`；更新原生代码或素材后先退出应用，再运行 `python3 scripts/build_app.py`。需要重新生成视频时，参见 [素材说明](docs/ASSETS.md)。

## 数据与 Git 忽略规则

| 路径 | 内容 | 上传 Git |
| --- | --- | --- |
| `config/`、`INTERESTS.md` | 初始模板、规则与素材校验清单 | 是 |
| `ui/src/`、`ui/server/`、`desktop/*.swift`、`scripts/` | 应用源码与测试 | 是 |
| `.hermes/` | 密钥、会话数据库、长期记忆、实际人设和任务状态 | 否 |
| `data/`、`reports/`、`backups/` | 来信、浏览记录、人格观察、表情收藏及备份 | 否 |
| `.runtime/`、`.setup/` | Hermes 源码、依赖、内部凭证、下载缓存和日志 | 否 |
| `ui/node_modules/`、`ui/dist/`、`desktop/build/`、`*.app` | 依赖与构建结果 | 否 |
| `ui/public/pet/*.mov`、`*.webm` | 完整桌宠视频，单独从 Release 恢复 | 否 |
| 本地界面截图和录屏 | 可能含聊天或账号信息的验证产物 | 否 |

原生访问凭证位于 `~/Library/Application Support/Bigfish/desktop-access.key`；原生日志及 launchd 日志位于 `~/Library/Logs/AI-Fish/`，均在仓库之外。不要把整个项目目录直接打包分享，源码上传以 Git 实际跟踪的文件为准。

## 素材与参考

形象、动画与表情均保留各自作者及使用条件；自编代码尚未单独指定开源许可证。第三方 MIT 代码的许可证原文也保留在仓库。详见 [第三方说明](THIRD_PARTY.md)、[图标署名](desktop/assets/ATTRIBUTION.md)、[桌宠素材署名](ui/public/pet/ATTRIBUTION.md) 及 [参考项目](REFERENCES.md)。

桌宠改编自 [PC2005-cloud/dsh-pet](https://github.com/PC2005-cloud/dsh-pet)，角色设计来自 [上善无形](https://space.bilibili.com/4456176) 与 [ZipZipPipe](https://space.bilibili.com/4168597)，遵循 CC BY-NC-SA 4.0 及上游的非商业条件。头像与表情来自 [可以叫我云大人 / 雾雪](https://kiriyuki.com)，保留作者说明。探头图片是基于该角色参考的 AI 辅助补绘，仍按角色素材条件处理。

## 1.7：按需醒来，记得共同经历

- 项目自带的冲浪与记忆整理挂接本地预检脚本。冷却、出发次数已满、后台暂停或没有新整理材料时，通过 Hermes 的 `wakeAgent:false` 在模型调用前跳过。每次预检有短租约；数据异常时脚本返回跳过，原因可在「鱼塘控制室 → 鱼粮账本」查看。
- 整理使用不可变快照，每批最多 12 篇浏览报告、12 条观察和12段经历。只有来源没有改变、整理报告已保存并带快照标记，才推进消费游标；新到材料留给下一批。初次启用会逐批处理现有未消费来源，不把它们默认为已读。
- 鱼粮账本按 7 / 30 / 90 天查看主调用来源和辅助用途，缓存输入、未缓存输入、输出分开，推理不重复相加。总量与 Hermes 官方分析接口核对，无法分到可见会话的消耗列入其他来源。统计按会话起始时间归窗，不是逐日账单。
- 冲浪与整理可暂停（不影响自行添加的其他任务），或将每日实际出发次数设为 1–3；这些是唤醒与活动额度，不是金额或 token 硬上限。已经执行的工作继续收尾。
- 新增项目自有 `fish-episodes` 记忆适配。保留 Hermes 内置 MEMORY / USER 和记忆工具；只为真人主对话保存本地来源片段，跳过 cron、子任务和已标记机器人消息。重复回调幂等，不导入旧聊天、不新增记忆提炼模型。
- 「记忆空间 → 共同经历」可检索来源、编辑摘要、固定或遗忘。遗忘擦除这一层的文本与索引并保留删除标记，原始 Hermes 聊天仍在；不是供应商数据删除或原会话删除。当前检索基于中文二字片段与英文词项，适合具体线索；尚未引入语义向量，换词很大的问法可能找不到。
- 相关旧经历按需召回，默认排除当前会话以免重复上下文；模型也可使用只读 `fish_recall` 工具。无结果不会编造回忆，旧对话中的模型猜测不自动变成用户事实。
- 人格稳定倾向仍需三个不同内容链接与跨两天的证据，不再强迫跨平台。链接追踪参数不算独立经历；暂时兴趣继续放在 curiosity 中。

升级已有安装：

```bash
npm ci --prefix ui
npm run build --prefix ui
python3 scripts/install_memory.py --activate
python3 scripts/setup_jobs.py
```

适配源码在 `plugins/fish-episodes/`，安装脚本复制到私有 `.hermes/plugins/fish-episodes/`，不修改 Hermes 上游。激活会切换 `memory.provider`，已有其他外部 provider 的用户应先确定要使用哪一个；配置与适配文件自动备份。重启项目内部服务并开启新会话后加载适配，之后退出并重新构建原生应用即可更新版本号。日常升级不要运行 `setup_profile.py` 覆盖个人模型和人设。

新数据：`data/memory/episodes.sqlite3` 保存来源片段与可重建全文索引；`data/automation/` 保存预检、增量快照和消费游标。两者均被 Git 忽略。自动记忆遵循模型服务的既有使用方式：相关片段可能随模型请求送往你配置的 API；导出分享前不要直接打包私有 data/。
