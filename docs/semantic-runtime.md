# 项目自有的可选编码运行时

本文保留当时实验与测量记录。后续记忆适配器 1.6.0 已完成可选接入及本机验证，当前行为、安装与限制以 [语义回忆接入说明](semantic-recall.md) 为准；默认安装仍不下载模型。

2026-10-29 补齐语义检索候选的部署与进程边界。此前开发环境的 Python 来自 Codex，不能作为项目的运行依赖。本轮在项目自己的 `.runtime/semantic/` 中安装了 Python 3.12.14、哈希锁定的依赖和固定中文模型；正式聊天仍沿用现有召回，没有新增面板、后台服务或自动索引任务。

## 参考与设计

[uv 的 Python 管理文档](https://docs.astral.sh/uv/guides/install-python/) 提供独立安装 Python 的方式；[环境变量说明](https://docs.astral.sh/uv/reference/environment/#uv_python_install_dir) 允许把安装目录限定到项目内。安装过程不改系统 Python、全局 PATH 或 Hermes 依赖。每台机器按脚本重建环境；这不表示整个项目可以随意移动目录，也不是公证后的通用应用包。

[Hermes 问题 #35218](https://github.com/NousResearch/hermes-agent/issues/35218) 记录了外部记忆组件失去响应后，聊天长时间等待的案例。它是问题报告，不是本机当前故障的证明；本轮没有据此修改 Hermes 核心。候选编码改用可结束的子进程，避免只给线程设等待超时、计算却仍在后台运行。

共享编码实现在 `scripts/fish_embeddings.py`，仍按原实验校验权重和 tokenizer，再加载 ONNX Runtime，取归一化 CLS 向量。开发回放也引用它，没有把测试脚本当作运行时依赖。父端 `fish_embedding_process.py` 只导入标准库；NumPy、ONNX Runtime 和 tokenizers 在显式启动的工作进程里加载。

## 显式准备

这是可选开发步骤，不属于应用正常安装或聊天操作。需要联网下载公开的 Python、软件包和模型；完成后编码通路不再下载任何内容。

```bash
python3 -m venv .runtime/semantic-tools
.runtime/semantic-tools/bin/python -m pip install --disable-pip-version-check --only-binary=:all: --index-url https://pypi.org/simple uv==0.13.6
python3 scripts/setup_semantic_runtime.py --uv .runtime/semantic-tools/bin/uv
```

已有前次下载的固定模型时，可避免重新下载：

```bash
python3 scripts/setup_semantic_runtime.py --uv .runtime/semantic-tools/bin/uv --model-dir .setup/semantic-model
```

主依赖仍固定为 NumPy 2.3.4、ONNX Runtime 1.23.2、tokenizers 0.22.1。`tests/requirements-semantic.lock` 锁定本次解析的全部 24 个依赖及分发文件哈希，安装只接收二进制 wheel，不执行源码构建。Python patch 版本固定，具体 standalone build 由 uv 选择；没有声称跨平台逐字节一致。此次实际验证平台是 Apple Silicon macOS。

安装器先校验模型、创建新一代虚拟环境、同步依赖，再运行一次真实离线编码检查，最后原子替换 `active.json`。失败保留之前的有效代；相同安装配方通过检查后直接复用。新解释器及其基础 Python 均校验位于本项目运行时目录内，不能悄悄借用 Codex 或系统解释器。配置、下载缓存、模型及依赖全被 Git 忽略。

## 进程接口与降级约定

`encode(runtime_home, texts, query=True)` 返回向量列表或 `None`。**调用方遇到 `None` 应保留已有词法路径**，不能构造零向量或假装召回成功。本轮未把这个调用挂进正式适配器，因此还不能称为真实聊天已启用语义降级。

- 每批最多 16 段、每段最多 2,000 字符，输入字节上限 64 KiB；输入输出两条管道均以非阻塞方式读写，避免子进程不读输入时父端卡在写管道。
- 默认工作进程期限 2 秒。超时、异常退出、过量输出或协议错误返回不可用；失败时结束其进程组并回收直接子进程。进程启动及操作系统清理也有开销，不把该期限声称为整次聊天的硬延迟保证。
- 输出上限 512,000 字节。父端核对协议版本、请求随机编号、固定模型身份、数量、512 维数值及单位范数；拒绝非有限数、布尔值、巨大数值和异常 JSON。
- 一份运行时只允许一个客户端编码请求持锁运行，繁忙时直接返回不可用，不排队。故障后该代冷却 60 秒；新的有效代或成功的安装检查可以重新尝试。持久状态只有运行时代的摘要与重试时间，不保存文本、异常堆栈或模型输出。
- 工作进程通过 stdin 接收文本，命令行不带查询。它不接触记忆数据库，不导入 Journal，也不调用网络 API；离线与关闭遥测的环境标志开启，父进程的模型 API 密钥不会继承。这里使用可信的本地代码和已校验模型，**不是操作系统级网络或文件沙箱**。

模型与查询仍会短暂存在进程内存和本地管道中。查询编码成功不意味着记忆相关；来源核验、缓存发布、更正和删除仍由 [同库事务层](semantic-cache-transactions.md) 处理。历史经历批量编码是单独的准备工作，不应偷偷塞进每次聊天查询。

## 实际验证

```bash
python3 -m unittest discover -s scripts -p 'test_embedding_process.py'
```

18 项标准库测试覆盖双向管道、卡死与回收、部分输出、输出过量、stderr 填充、异常退出、不继承凭据、协议与数值异常、路径与锁文件归属、缺失环境、冷却与繁忙状态，以及安装失败保留旧代和重复安装。测试内容为虚构文本；本轮全部 Python 检查共 208 项通过。

本机还实际安装并重复执行了安装器，第二次复用原代；读取解释器元数据确认基础 Python 位于项目内。真实模型先通过单次检查，再通过进程客户端重跑完整隔离回放。可用 `active.json` 中的相对 Python 路径执行：

```bash
python3 - <<'PY'
import json, subprocess
from pathlib import Path
home = Path('.runtime/semantic')
python = home / json.loads((home / 'active.json').read_text())['python']
subprocess.run([str(python), 'scripts/eval_semantic_cache.py',
                '--runtime-home', str(home),
                '--output', '.setup/semantic-process-results.json'], check=True)
PY
```

56 条虚构有效经历、61 个窗口、154 个查询中，缓存排序与重新编码、固定补充门槛及原有词法结果均一致；15 个生命周期断言通过。健康重开无需重新编码来源，查询逻辑写入仍为零。

本机一次完整回放：61 个窗口准备、编码和提交约 1,531 ms；每次新启动工作进程的单查询编码中位数约 125 ms，排名与来源重读中位数约 8.70 ms。开发父进程峰值约 49.6 MiB，操作系统报告的子进程峰值约 362.4 MiB；二者不是整个应用内存测量。前一次单次启动约 272 ms，差异说明文件缓存与启动条件会影响耗时。没有将这些数据当作通用性能保证。

这次安装会占本机磁盘，编码也消耗 CPU；没有付费 API 编码调用。原有词法检索本来就不调用 embedding API，因此不能据此宣称当前账单已降低。正式召回的误联想测试与降级联调仍需完成，运行时就绪并未自动改变聊天行为。
