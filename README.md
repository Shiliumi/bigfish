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
python3 scripts/install_budget.py
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

对话效果的开发抽样见 [逐轮互动回放](docs/conversation-dialogues.md)：显式 `--live` 才调用配置的付费 API，材料使用公共模板与虚构对话，计入后台额度；实验候选不自动安装到人设，也不作为应用日常任务运行。

另有 [本地语义检索隔离实验](docs/semantic-memory-study.md)，使用单独环境与虚构记忆比较漏召回、误召回和资源开销。向量模型与依赖是可选开发材料，正式应用没有接入。

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

## 1.14.1：读取回忆少争一把写锁

已初始化、索引一致的回忆库不再在每次查询时重跑建表与版本写入；旧库升级和过期索引修复仍在事务内执行，失败回滚。虚构并发检查中，另一个写事务未提交时仍能读取已提交内容；固定回放的召回文本保持一致。本轮不增加面板、工具或模型调用，也不改变 token 输入。详见 [持续改进记录与验证](docs/research-2026-10-29.md)。

已有安装执行 `python3 scripts/install_memory.py`，在空闲时重载 gateway 插件、重启内部接口；退出应用后构建新应用。无需重设人设、模型或日常任务。旧库首次打开会进行一次事务升级，运行中的数据库备份使用 SQLite 在线备份。

## 1.14：接住前面的铺垫，没懂也不装懂

- 接话说明补上当前会话的多轮铺垫、谐音和反话：新线索出现时回看前文，认出被逗后自然回应，不机械认领玩笑昵称，也不逐字科普。
- 没接住就承认，理解晚了不说早已知道；对方想结束就收住。临时玩笑不作为改名、用户事实或持续事项，认真问题和真诚表达继续按当下请求处理。
- 增加十组虚构对话回放及可选的实际模型对比脚本，使用真实后台额度，结果留在本机。小样本中仍有多层梗接不全、解释过长等问题，不能视为普遍提升或模型训练。详见 [多轮接话验证](docs/conversation-play.md)。

已有安装执行 `python3 scripts/install_memory.py` 和 `python3 scripts/update_conversation_guide.py`，空闲时重载 gateway 插件、重启内部接口，退出应用后运行 `python3 scripts/build_app.py` 再打开。新对话加载完整说明；保留私人命名与成长区，无需重新设定模型或日常安排。

## 1.13：记得事情正在往前走

- 「记忆空间」新增 **持续事项**：目标、待解决问题与约定，可以记录进展、暂停、完成、续留或遗忘。默认保留 90 天，最多二十件有效的进行中或暂停事项；保留时间不是事情的截止日期。相关聊天最多带两条当前状态，泛泛询问近况只带进行中的，不自行创建日程或催办。
- 主聊天可通过 `fish_matters` 保存和更新。写入引用当前真人原话，标题必须摘自原话；更新需要具体话题、明确状态与版本，拒绝转述代码、否定完成和不明确指代。调用仍取决于模型选择；历史聊天不会自动回填。原话与来源留在本机，不把鱼的建议当作用户事实。
- 事项在同一 `episodes.sqlite3` 内保存来源事件。聊天结束后关联实际共同经历；关联来源被更正或到期时先待核实，遗忘来源会清除关联事项及其进展文本。面板可重新核实当前状态；已载入模型的旧上下文需在新对话中完整更新，原始 Hermes 聊天与私有备份另行保留。
- 回忆上下文移除完全重复的摘要、空元数据和多余 JSON 空格，保留说话人、原话、来源与更正。普通闲聊没有重复节奏或真实兴趣材料时，沿用静态接话说明。91 个虚构回放中，回忆片段由 40,851 降到 27,653 字符，原有来源与原话保留；这约 32.3% 只针对该回放的回忆片段。新增工具定义也增加约 563 字符，事项内容和工具往返有成本，不代表账单或总输入按此比例下降。

升级已有安装：先备份本机记忆数据库（SQLite 运行中应用在线备份），构建界面并执行 `python3 scripts/install_memory.py`；在空闲时重载 gateway 插件并重启内部服务，退出应用后运行 `python3 scripts/build_app.py` 再打开。无需重设人设、provider 或定时任务。新对话加载完整工具说明。详见 [持续事项与上下文验证](docs/ongoing-matters.md)。

## 1.12：兴趣也能先放一边

- 「探索日志 → 她最近惦记的」增加 **先放三天** 和 **放下这个问题**；在「放在一边的」列表里可以恢复。显示全部当前问题，最多八个。三天暂停自动到期，放下保留到手动恢复；恢复只解除用户限制，不延长原问题有效期，也不绕过原有冷却。
- 同一份本地选择作用于兴趣聊天提示、冲浪候选、近期观察入口、同来源的新问题以及待发送来信。已经出发的阅读正常收好，相关问题与分享可跳过；收尾中断恢复也保留之后做出的用户选择，来信投递前再检查。已经收到的来信和阅读报告保留。
- 这是对具体问题编号和当时已关联来源的控制，不是屏蔽整个领域的语义分类器，也不自动将聊天里的随口一句话变成永久禁令。它不修改已形成的人格、核心档案或成长证据，不增加模型调用；尚未测得日常 token 节省比例。

已有安装升级时构建界面并执行 `python3 scripts/install_memory.py`，在空闲时重载 gateway 插件、重启内部服务，退出应用后运行 `python3 scripts/build_app.py` 并重新打开。无需重新设置定时任务或人设。私有选择在 `data/curiosity/controls.json`，已被忽略。格式损坏时保留原文件、暂停兴趣推荐和相关新来信，不默认为已恢复；应用会显示读取失败。

## 1.11：接得住当前的话，也记得上次的好奇

- 主聊天按当前话题加入一小段本地接话提示：认真求助先解决问题，想安静时少派任务，闲聊不硬造梗。最近几轮若频繁喊称呼、重复开场或用问句收尾，会提示换回具体内容；不保存情绪评分，不额外调用模型评审。手写规则仍会漏判，当前用户要求优先。
- 有真实阅读报告、已读回执与观察支持的未完问题，可以进入相关聊天和下次冲浪。附上阅读日期，区分旧见闻与新进展；聊天里引用过的来源另记轻量标记，不增加人格成长证据。认真求助只取相关来源，用户明确想听见闻时可转移话题；过期、已放下、冷却中的兴趣不推送。
- 沿旧问题出发的新来信，在实际完成记录和阅读回执核验后标注跟进。早晚问候避开最近三次同类已发用语，保留静默、冷却和去重。自定义日常显示真实任务名与执行时间，不再统一标成冲浪。
- 接话说明只更新自己的标记区，并替换与旧公共模板完全一致的整段示例；升级前备份，保留个人命名、手动档案和自动成长区。详见 [接话与兴趣衔接验证](docs/conversation-checks.md)。

已有安装升级：

```bash
npm run build --prefix ui
python3 scripts/install_memory.py
python3 scripts/update_conversation_guide.py
python3 scripts/setup_jobs.py
```

在聊天和任务空闲时重载 gateway 插件并重启内部服务，退出应用后执行 `python3 scripts/build_app.py`，再打开应用并开启新对话。已有对话中的旧提示可能继续影响回复。不要运行 `setup_profile.py` 覆盖个人档案。新增私有文件 `data/curiosity/chat-references.json` 只保存兴趣编号和引用时间，已被忽略；相关来源片段仍按原有方式随请求发往已配置的模型 API。

这轮没有训练模型或新增逐轮情绪模型调用；提示仍有 token 成本。固定场景测试验证程序选择与来源边界，少量实际生成只作人工抽查，不能证明每轮都自然或回答正确。

## 1.10：找得更准，也知道何时没找到

- 共同经历支持少量常见同义词、全角英文、数字和手动别名。打开一条经历，可填写最多八个简称或昵称；标签帮助定位，不改写原话或成为新事实。聊天纠错时默认清除该条旧别名，遗忘同时清掉别名与派生索引。
- 支持“昨天聊的”“前天说的”、上周、上个月和明确日期。按原聊天记录的北京时间筛选；自动召回会区分聊天日期与事件日期，不把“昨天买的键盘”当作“昨天聊过键盘”。找不到时保守留空，不再因一句“记得我吗”或一个泛泛词牵出无关片段。
- 固定只小幅影响相关结果，不会把弱相关内容硬推到前面。长对话返回双方原话中的相关窗口并保留说话人标记，更正后的旧说法不回流；仍最多四段、4,200 字符，不新增模型请求。首次升级会从当前有效意义重建本机派生索引，保留原经历、版本与删除标记。
- 修复 Hermes 在初始化前登记工具路由时，回忆适配尚未公布工具的问题；同时避免旧回合的异步保存清掉新回合纠错状态。已用固定版本的真实 MemoryManager 离线验证整个调用衔接，不修改上游源码。
- 新增 91 个虚构查询的开发回放：首条目标命中由 74/79 到 78/79，应留空由 8/12 到 12/12。不是独立盲测、真实聊天成功率或回答正确率，仍有同义转述漏召回，深层语义压力样例尚未解决。详见 [回放说明](docs/memory-replay.md)。

升级后执行 `python3 scripts/install_memory.py`，在聊天空闲时重启内部 Hermes 接口并开启新对话加载；通常不需要重新激活 provider。不要运行 `setup_profile.py` 覆盖个人档案。检索本轮仍采用本地词法方案，没有下载向量模型。

## 1.9：后台有额度，冲浪一次收好

- 「鱼塘控制室 → 鱼粮账本」新增每日后台 token 额度，首次安装默认启用 200 万，可调整或关闭。覆盖本应用 Hermes 的全部 cron 定时任务，包括自行添加的任务；聊天主请求独立记录，不被此额度拦截。原来的活动暂停开关仍只控制项目自带的冲浪和整理。
- 主后台请求通过 Hermes 的 `llm_execution` 扩展先原子预留，再调用供应商，成功后按实际用量结算、退回差额。跨进程共享额度；失联和未知用量暂按预留消耗，不按零计算。每日北京时间零点重新计额，按请求开始日归属。额度包含输入（含缓存）及输出，推理不重复相加；这是总 token 活动额度，不是金额或供应商硬封顶。
- 主后台单次输出最多 8,192 token，并保留原请求的工具与推理消息。UTF-8 文本字节加输出上限作为保守预留，可能因剩余额度不足而提前停止；不为补写收尾自动追加模型调用。辅助调用使用原生观察钩子记账，能够归属 cron 的计入后台；会话标题和对话后的复盘按用途计入后台，即使由聊天触发；其他聊天辅助保持独立。该接口不能逐次拦截辅助调用。归属未知的单列，在途、辅助、底层隐藏重试和未返回的用量仍可能超额，最终以供应商账单为准。
- 新账本从安装启用后开始记录，不导入已有消耗。只保存随机请求编号、时间、来源、用途、模型标识、token 桶、状态和会话编号哈希；不保存提示、回复、密钥、地址和原始工具数据。缺少 usage 显示未知。
- `scripts/surf_complete.py` 将一轮的报告、已读记录、观察、未完问题、可选人格反馈、结局与来信候选统一验证提交。程序串联真实编号，减少模型分别写文件、调用工具和修正引用的往返。相同出发与候选可重试；中断保留可恢复记录，冲突停止覆盖，来信最后排队，避免重复投递。没有成功读到正文时只能记录受阻，不制造发现。

升级已有安装：

```bash
npm run build --prefix ui
python3 scripts/install_budget.py
python3 scripts/setup_jobs.py
```

预算扩展安装到私有 `.hermes/plugins/fish-budget/`；需要在任务与聊天空闲时重启项目 Hermes 内部接口及 gateway，随后重新打开应用。源码不修改固定的 Hermes 上游。首次启用会影响自行添加的 cron 的后续模型请求，请在账本中按实际使用调整额度；已有任务定义保留。请求账本 `data/automation/requests.sqlite3`、收尾恢复记录 `data/surf-completions/` 均被 Git 忽略，可能包含私有状态。完整候选协议见 [SURF_COMPLETE.md](config/SURF_COMPLETE.md)。目前只验证了流程与故障边界，尚未测得日常费用下降比例。

## 1.8：可以纠错的回忆，有观察期的偏好

- 「记忆空间」可更正共同经历、查看旧版本、设置到期时间或标记过时。更正后的内容替代召回与检索中的旧说法；来源原文留在历史中。到期记录不参与当前召回，固定也不会绕过有效期；情境印象默认保留 30 天。
- 用户在聊天中明确纠正旧回忆时，模型可先用 `fish_recall` 取得当前版本，再用 `fish_correct_memory` 引用这次用户原话更新。工具要求当前真人消息、明确纠错表达和版本匹配，不接受自行编写的引语。核心 MEMORY / USER 仍使用原生记忆工具；修改共同经历不会自动覆盖核心档案。已经进入当前模型上下文的旧片段需在新对话中完整更新。
- 「人格尝试」区分试着喜欢、形成倾向、待复核和已放下。最多同时尝试四项，试行默认 21 天；稳定倾向要求至少 72 小时、三个独立来源、跨两个日期，并有尝试开始后的真实跟进。重复材料不算成长，网站打不开不算不喜欢；反例会影响后续判断，用户也可直接让某项习惯停下来。
- 支持材料被更正、过时或遗忘后，关联倾向会待复核。核心相处约定保留，人格状态仅辅助选择话题和表达；没有新增独立的模型评审调用，也不会靠等待自动成熟。日终整理按新增材料与偏好事件增量进行。

升级命令见下方。`data/personality/trials.json` 与回忆版本历史均为本机私有数据，不进入 Git。应用内「放下」只移除由本项目试行形成的对应倾向，历史手动人设保留。

## 1.7：按需醒来，记得共同经历

- 项目自带的冲浪与记忆整理挂接本地预检脚本。冷却、出发次数已满、后台暂停或没有新整理材料时，通过 Hermes 的 `wakeAgent:false` 在模型调用前跳过。每次预检有短租约；数据异常时脚本返回跳过，原因可在「鱼塘控制室 → 鱼粮账本」查看。
- 整理使用不可变快照，每批最多 12 篇浏览报告、12 条观察和12段经历。只有来源没有改变、整理报告已保存并带快照标记，才推进消费游标；新到材料留给下一批。初次启用会逐批处理现有未消费来源，不把它们默认为已读。
- 鱼粮账本按 7 / 30 / 90 天查看主调用来源和辅助用途，缓存输入、未缓存输入、输出分开，推理不重复相加。总量与 Hermes 官方分析接口核对，无法分到可见会话的消耗列入其他来源。统计按会话起始时间归窗，不是逐日账单。
- 冲浪与整理可暂停（不影响自行添加的其他任务），或将每日实际出发次数设为 1–3；这些是唤醒与活动额度，不是金额或 token 硬上限。已经执行的工作继续收尾。
- 新增项目自有 `fish-episodes` 记忆适配。保留 Hermes 内置 MEMORY / USER 和记忆工具；只为真人主对话保存本地来源片段，跳过 cron、子任务和已标记机器人消息。重复回调幂等，不导入旧聊天、不新增记忆提炼模型。
- 「记忆空间 → 共同经历」可检索来源、编辑摘要、固定或遗忘。遗忘擦除这一层的文本与索引并保留删除标记，原始 Hermes 聊天仍在；不是供应商数据删除或原会话删除。当前检索基于中文二字片段与英文词项，适合具体线索；尚未引入语义向量，换词很大的问法可能找不到。
- 相关旧经历按需召回，默认排除当前会话以免重复上下文；模型也可使用只读 `fish_recall` 工具。无结果不会编造回忆，旧对话中的模型猜测不自动变成用户事实。
- 此版的人格稳定倾向要求三个不同内容链接与跨两天的证据；1.8 进一步加入试行期和来源失效复核。链接追踪参数不算独立经历。

升级已有安装：

```bash
npm ci --prefix ui
npm run build --prefix ui
python3 scripts/install_memory.py --activate
python3 scripts/setup_jobs.py
```

适配源码在 `plugins/fish-episodes/`，安装脚本复制到私有 `.hermes/plugins/fish-episodes/`，不修改 Hermes 上游。激活会切换 `memory.provider`，已有其他外部 provider 的用户应先确定要使用哪一个；配置与适配文件自动备份。重启项目内部服务并开启新会话后加载适配，之后退出并重新构建原生应用即可更新版本号。日常升级不要运行 `setup_profile.py` 覆盖个人模型和人设。

新数据：`data/memory/episodes.sqlite3` 保存来源片段与可重建全文索引；`data/automation/` 保存预检、增量快照和消费游标。两者均被 Git 忽略。自动记忆遵循模型服务的既有使用方式：相关片段可能随模型请求送往你配置的 API；导出分享前不要直接打包私有 data/。
