# 本地语义检索隔离实验（2026-10-29）

目标是理解“换个说法就找不到”的原因，同时检查错误联想与本机开销。本轮只新增开发回放、虚构样本与测试，不改正式召回、人设、模型配置或界面；应用继续 1.14.1。模型文件和独立依赖留在已忽略的 `.setup/`，不加入安装包，也没有常驻推理进程。

## 参考与候选

[Mnemosyne 文档](https://github.com/kirocop/mnemosyne/blob/main/docs/configuration.md) 提供本地向量与词法检索的选择；[FastEmbed 的模型注册和处理源码](https://github.com/qdrant/fastembed/blob/main/fastembed/text/onnx_embedding.py) 包含中文 BGE 模型及归一化 CLS 处理。保留大肥鱼现有的来源、更正和有效期，先测试本地补充检索，不直接换整个记忆系统。

选择 [BAAI/bge-small-zh-v1.5](https://huggingface.co/BAAI/bge-small-zh-v1.5) 的 [Qdrant ONNX 转换](https://huggingface.co/Qdrant/bge-small-zh-v1.5/tree/46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59)。它是中文模型，512 维；模型卡提供检索查询指令。本实验按官方处理方式取 CLS 并做 L2 归一化，查询带指令，原文不带。没有运行远端 Python 模型代码。

固定转换仓库 revision 为 `46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59`，权重 SHA-256 为 `1294ea4b6331115a353d81f96b85e8c8d7fdcc284453d5b2fab5b016230aad38`；分词文件也有固定 SHA-256。脚本先检查两者，再加载 ONNX Runtime。它本身不联网、不下载文件、不调用付费 API，也不读本机实际聊天或私人人设。

## 数据与边界

校准沿用 33 段虚构经历、91 个已有查询和三个已知深层转述：82 个应找回、12 个应留空。它们是开发数据，不是新的独立测试。

新增 `tests/fixtures/semantic_transfer.json`：20 段虚构经历、20 个应找回的转述、16 个没有对应目标经历的干扰查询，以及四个“相关事件存在，但所问细节没有记录”的控制查询。新用户问法在首次模型推理前固定；全部由开发者编写且后来已人工查看，不称为独立盲测。

四个细节控制不计入应留空指标。例如只记得调整眼镜鼻托，问镜片度数时取回那段经历不一定错，但它不能证明度数。相关事件检索与回答所需细节是否存在分开记录；本实验不调用生成模型评估答案。

两份隔离数据库分别用于旧校准集与加入新经历的开发集。只为当前有效来源编码，更正后只编码更正记法；过期、遗忘、未来记录不进该次快照。长原话按 280 字符窗口、220 字符步长编码，保留原别名，分词仍受 512 token 上限限制。单条经历的相似度取窗口最大值。日期和空泛查询先沿用当前召回的结构约束。

对照三种方法：现有词法召回；结构过滤后直接取向量第一名；以及保留现有词法结果、仅在没有结果时用向量补一条。补充检索需要同时过相似度和前两名差距门槛。它没有替换已有弱相关命中的能力。

门槛只用旧校准查询选择：先减少负例误取，再提高正例目标进入结果的数量，平手偏向更严格门槛。初始网格从 0.65 开始，实际校准分数较低，补充检索未触发。观察该分布后把网格拓宽到 0.25–0.90；最终选择相似度 0.55、差距 0.06。新集标签未参与程序选门槛，但新输出已经人工查看，不以此声称没有开发者观察偏差。原运行记录保留在本机；补充哈希与校验后的同条件复核，检索结果保持一致。

## 结果

| 检查 | 现有词法 | 直接取向量第一名 | 词法为空时带门槛补充 |
| --- | --- | --- | --- |
| 旧校准正例目标进入结果 | 78/82 | 79/82 | 80/82 |
| 旧校准负例误取 | 0/12 | 8/12 | 0/12 |
| 新转述正例目标进入结果 | 5/20 | 19/20 | 12/20 |
| 新干扰查询误取 | 5/16 | 16/16 | 5/16 |

这里比较的是检索编号，不是回答正确率或真实聊天成功率。正例都是刻意挑选的转述压力场景，不代表普通聊天分布。直接取第一名没有足够的拒答机制，负例表现不能当作整个向量技术的上限；带门槛候选也只验证了一个小模型与一种融合方式。

向量能找回“落在大巴后排的挡雨家伙”对应的雨伞等七个原词法空结果。但当前词法仍可能只因“最后”“恢复”或某个宽泛词取到另一件事；例如洗碗池渗水的问题被配到齿轮/电脑维修，问蓝牙耳机升级被配到打印的耳机支架。保留词法命中优先的候选无法修正这些错误，也不能把“度数没记过”补成一个数值。

一次同条件复核的本机资源记录：模型目录逻辑大小约 95.2MB，独立 Python 环境占约 228MiB 磁盘；实验进程峰值约 376MiB 内存。权重校验与加载约 190ms，热进程单查询编码中位数约 3.68ms；五十条有效经历的 55 个窗口批量编码约 948ms。这不是整个应用延迟；首次下载、Python 进程启动、持续索引维护和更大的库都可能改变成本。

本轮没有付费生成或 embedding API token 消耗。若今后接入聊天，取回的原话仍会占模型输入并按当前配置发给模型 API；不能把本地向量计算等同于总 token 开销为零。

## 复现

用独立 Python 3.12 环境，避免修改 Hermes 或应用现有依赖：

```bash
python3.12 -m venv .setup/semantic-runtime
.setup/semantic-runtime/bin/python -m pip install -r tests/requirements-semantic.txt
mkdir -p .setup/semantic-model
curl --fail --location https://huggingface.co/Qdrant/bge-small-zh-v1.5/resolve/46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59/model_optimized.onnx -o .setup/semantic-model/model_optimized.onnx
curl --fail --location https://huggingface.co/Qdrant/bge-small-zh-v1.5/resolve/46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59/tokenizer.json -o .setup/semantic-model/tokenizer.json
.setup/semantic-runtime/bin/python scripts/eval_semantic_memory.py --model-dir .setup/semantic-model --output .setup/semantic-results.json
```

主要依赖固定为 NumPy 2.3.4、ONNX Runtime 1.23.2、tokenizers 0.22.1。结果保存模型与样本哈希、所有查询的候选、分数、选定门槛及资源记录。脚本使用临时数据库，结束后清理；不产生可被正式应用自动加载的向量索引。

新增五项无需下载模型的测试，检查低分/相近第一名应拒取、缺失属性不混入负例统计、权重先校验再导入可选依赖、日期语义，以及快照里只有更正后的当前有效来源。全部 Python 152 项通过。它们没有证明真实模型始终正确，也没有覆盖持久向量缓存之后的来源变更。

## 后续决定

本地补充检索值得保留为候选，正式应用暂沿用现有召回。先修复泛词触发的误取，再验证向量缓存对纠正、遗忘、到期、版本变化的同步失效，以及真实生命周期中的查询耗时。小型开发集里增加七个目标且未增加误取，仍不足以证明可安全泛化；不为这一结果增加设置面板或后台常驻服务。

后续已分别完成 [泛词召回证据调整](recall-evidence.md)、[持久缓存的隔离验证](semantic-cache-study.md)、[同库事务清理](semantic-cache-transactions.md)，以及 [项目自有运行时与限时编码进程](semantic-runtime.md)。候选仍未安装到正式应用；召回层降级联调与误联想测试尚待接入前处理。
