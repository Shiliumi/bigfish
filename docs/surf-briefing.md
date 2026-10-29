# 合并冲浪准备，减少临时脚本往返

2026-10-29，应用保持 1.14.3，记忆适配器保持 1.6.5。没有新增界面、模型工具、定时任务或模型调用；现有冲浪任务增加一个本地准备入口。

## 问题与改动

检查本机执行记录时，发现准备/整理阶段曾临时使用 Python 内联脚本并被终端审批拒绝。这些失败会让模型再决定换什么写法或读取路径，增加往返。历史诊断仅在本机进行，实际提示、命令、日志和浏览内容未作为公开回放材料上传；关键词“错误”不等于真实失败，判断另外核对了工具的退出码和审批错误字段。

现在使用：

```bash
python3 scripts/curiosity.py briefing
```

一次返回当前北京时间、出发判断、已有 agenda，以及 `INTERESTS.md`、`config/CURIOSITY.md`、`config/SURF_COMPLETE.md` 的内容。已有内容无需再分别读取；阅读和收尾仍按原协议进行，候选 JSON 使用已有 write_file / patch 保存，再运行项目的收尾命令。准备入口不会调用 begin、选择兴趣、打开浏览器或自动生成报告。

安静时间、暂停、当天出发额度等不允许出发时，先返回简短判断，不再读取协议或建立 agenda 的可选记忆上下文。允许出发时沿用现有 agenda；它可能初始化或修复本地回忆派生索引，因此不能将整个入口称为严格只读。它不修改出发记录、兴趣或成长档案。

每份文档原文最多内联 24,000 字节，三份合计最多 48,000 字节；大文件标记 `read_required` 并交给原文件工具按需读取，没有悄悄截掉协议末尾。这些是原文容量限制，包含 agenda、JSON 和说明的整个输出可能更大，不是 token 上限。固定文件缺失或指向符号链接时明确报错，保留原数据。文档和 agenda 中的字符串沿用项目凭据脱敏规则。

`checked_at` 只表示准备时刻。出发仍以 begin 的返回为准，页面 read_at 仍需在实际阅读时采集；现有收尾的来源时间验证保持原样，不能复用旧时间或改时间以凑过验证。

## 已有任务迁移

```bash
python3 scripts/install_surf_briefing.py --dry-run
python3 scripts/install_surf_briefing.py
```

安装器通过项目运行时和 Hermes 原生任务锁更新：只替换唯一 fish-surf 中已知模板的第一步，其余提示、模型、工具组合、时间表与学习搭子保持原样。手动改过开场或第一步、重名、任务被移除或计划后有人改过提示时保留现状；不创建替代任务。重复安装不再次修改。执行前保存私有 jobs.json 备份，原有任务的运行状态不会用旧备份覆盖。

新安装直接使用更新后的 surf-prompt 模板。已有安装不运行 setup_jobs.py 重置任务。后续执行读取新的准备步骤，无需重建或重启应用，也不强制中断正在运行的任务。

## 参考与验证

[Hermes 官方审批说明](https://hermes-agent.nousresearch.com/docs/user-guide/security) 区分交互与无人值守任务的审批处理；[社区的实际使用讨论](https://www.reddit.com/r/hermesagent/comments/1t3sjis/anyone_using_smart_approval/) 也涉及内联脚本和 smart approval，评论只是个人经验。本轮查看固定版本的 [审批分类器](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/tools/approval_detection.py) 与 [任务存储](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/cron/jobs.py)，采用固定、有限的项目命令，没有更改审批模式、允许列表或上游源码。

```bash
python3 -m unittest discover -s scripts -p 'test_*.py'
```

296 项 Python 检查通过。其中新增检查覆盖单次完整准备、不隐式出发、休息时短路、文档容量和延后读取、凭据脱敏、缺失/链接文件、从其他工作目录执行、模板与自定义内容保留、重复迁移及并发修改。

另在固定 Hermes 上直接运行静态分类器：新命令没有命中危险命令模式，虚构的 `python3 -c` 与 heredoc 样例仍被标记。只做分类，没有执行样例或请求模型审批；这不意味着其他用户配置的审批规则必然放行。真实原生任务 API 还在临时任务库验证了只改准备步骤、其他字段/任务保留、第二次不再修改，未触发任何 cron 执行。

部署后已核对现有任务仅第一步按计划改变，私人设定、模型和审批配置保留，原 gateway 继续运行。没有实测日常模型往返次数、供应商 token 或账单降幅；模型以后是否按新流程准备仍需观察。此次把准备工作固定成单次本地入口，减少模型临时编排这些读取的需求，不把静态检查当作真实冲浪成功率。
