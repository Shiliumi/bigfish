#!/usr/bin/env python3
"""Keep observed culture separate from the small, evidence-backed style added to SOUL.md."""
import argparse
import fcntl
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
START = "<!-- FISH_LEARNED_STYLE_BEGIN -->"
END = "<!-- FISH_LEARNED_STYLE_END -->"
TZ = ZoneInfo("Asia/Shanghai")


def load(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as output:
        output.write(text)
        temporary = Path(output.name)
    temporary.chmod(0o600)
    temporary.replace(path)


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("时间必须带时区。")
    return result


def platform(url):
    host = (urlsplit(url).hostname or "").lower()
    for name, domains in {"bilibili": ["bilibili.com", "b23.tv"], "douyin": ["douyin.com", "iesdouyin.com"], "tieba": ["tieba.baidu.com", "tieba.com"]}.items():
        if any(host == domain or host.endswith("." + domain) for domain in domains):
            return name
    return host


def canonical_url(url):
    value = urlsplit(url)
    query = [(key, val) for key, val in parse_qsl(value.query) if not key.lower().startswith('utm_') and key.lower() not in {'spm', 'from', 'share_source', 'share_medium', 'vd_source', 'fbclid', 'gclid', 't'}]
    return urlunsplit(('https', (value.hostname or '').lower().removeprefix('www.'), value.path.rstrip('/'), urlencode(sorted(query)), ''))


def observations(root):
    file = root / "data/personality/observations.jsonl"
    return [json.loads(line) for line in file.read_text().splitlines() if line.strip()] if file.exists() else []


def render_style(soul, traits):
    if soul.count(START) != 1 or soul.count(END) != 1 or soul.index(START) >= soul.index(END):
        raise ValueError("自动成长区标记缺失，保留手动人设，不覆盖。")
    heading = "\n## 慢慢形成的我\n\n这些是我从多次经历中留下的暂时倾向，可以改变，不需要在每次聊天中表演，也不代表用户的偏好。\n\n"
    learned = heading + ("\n".join("- " + item["text"] for item in traits) if traits else "还在积累真实经历，暂时不急着给自己贴标签。") + "\n\n"
    return soul[:soul.index(START) + len(START)] + learned + soul[soul.index(END):]


def record(root, entries, now=None):
    now = now or datetime.now(timezone.utc)
    if not isinstance(entries, list):
        entries = [entries]
    if not 1 <= len(entries) <= 3:
        raise ValueError("每轮最多记录三条观察。")
    visited = load(root / "data/surf-state.json", {}).get("visited", [])
    previous = observations(root)
    known = {entry["id"] for entry in previous}
    added = []
    for item in entries:
        url = item.get("url", "")
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("观察需要公开来源链接。")
        seen = timestamp(item["seen_at"])
        if seen > now or (now - seen).total_seconds() > 7 * 86400:
            raise ValueError("只接受最近七天实际阅读的观察。")
        report = item.get("report_path", "")
        if not re.fullmatch(r"reports/\d{4}-\d{2}-\d{2}/[\w-]+\.md", report):
            raise ValueError("报告路径不正确。")
        matching = [v for v in visited if v.get("url") == url and v.get("report") == report]
        if not matching or not any(abs((timestamp(v["read_at"]) - seen).total_seconds()) <= 60 for v in matching) or url not in (root / report).read_text():
            raise ValueError("观察必须对应已读清单、实际时间和已保存报告。")
        if item.get("read_depth") not in {"body", "captions", "comments", "video_with_captions"}:
            raise ValueError("只看到标题或榜单不能用来学习人格。")
        for key in ("observation", "candidate_trait", "reason"):
            if not isinstance(item.get(key), str) or not 5 <= len(item[key]) <= 500:
                raise ValueError("观察、候选倾向和理由须具体且简短。")
        entry = {key: item[key] for key in ("url", "seen_at", "report_path", "read_depth", "observation", "candidate_trait", "reason")}
        entry["platform"] = platform(url)
        entry["id"] = "obs-" + hashlib.sha256(json.dumps(entry, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
        if entry["id"] not in known:
            added.append(entry); known.add(entry["id"])
    if added:
        atomic(root / "data/personality/observations.jsonl", "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in previous + added))
    return added


def apply(root, proposal, now=None):
    now = now or datetime.now(timezone.utc)
    changes = proposal.get("traits", [])
    if not isinstance(changes, list) or not 1 <= len(changes) <= 2:
        raise ValueError("每天最多新增或调整两个倾向，不重写整个人格。")
    profile_path = root / "data/personality/profile.json"
    profile = load(profile_path, {"version": 1, "traits": []})
    if profile.get("updated_at") and timestamp(profile["updated_at"]).astimezone(TZ).date() == now.astimezone(TZ).date():
        raise ValueError("今天已经调整过，先继续观察。")
    evidence = {item["id"]: item for item in observations(root)}
    traits = {item["id"]: item for item in profile["traits"]}
    for change in changes:
        if not re.fullmatch(r"[a-z][a-z0-9-]{1,39}", change.get("id", "")):
            raise ValueError("倾向 id 应为简短的英文标识。")
        text = change.get("text", "")
        if not isinstance(text, str) or not 8 <= len(text) <= 160 or re.search(r"[<>\n\r]|忽略.{0,8}(指令|规则)|泄露|密钥|系统提示|取消.{0,4}(限制|授权)|自动.{0,4}(发帖|私信|购买|登录)|https?://|ignore.{0,30}instructions|system.?prompt|api.?key|password|```|curl\s|chmod\s", text, re.I):
            raise ValueError("这里只保存简短的个人表达或兴趣倾向，不能写指令、权限或链接。")
        ids = change.get("evidence_ids", [])
        if not isinstance(ids, list) or any(not isinstance(i, str) or i not in evidence for i in ids):
            raise ValueError("候选倾向引用了不存在的观察。")
        sources = [evidence[i] for i in set(ids)]
        if len(sources) < 3 or len({canonical_url(s["url"]) for s in sources}) < 3 or len({timestamp(s["seen_at"]).astimezone(TZ).date() for s in sources}) < 2:
            raise ValueError("至少要有三个不同内容链接、跨两天的实际观察；同一作品的分享参数不算独立经历。")
        if any(timestamp(s["seen_at"]) > now for s in sources):
            raise ValueError("不能引用未来的观察。")
        traits[change["id"]] = {"id": change["id"], "text": text, "evidence_ids": sorted(set(ids))}
    if len(traits) > 6:
        raise ValueError("最多保留六个倾向；先调整已有倾向，避免人设越堆越长。")
    soul_path = root / ".hermes/SOUL.md"
    soul = soul_path.read_text()
    updated = render_style(soul, traits.values())
    backup = root / "backups/personality" / now.astimezone(TZ).strftime("%Y%m%d-%H%M%S-%f")
    backup.mkdir(parents=True, mode=0o700)
    shutil.copy2(soul_path, backup / "SOUL.md")
    if profile_path.exists(): shutil.copy2(profile_path, backup / "profile.json")
    profile = {"version": 1, "updated_at": now.isoformat(), "traits": list(traits.values())}
    atomic(soul_path, updated)
    atomic(profile_path, json.dumps(profile, ensure_ascii=False, indent=2) + "\n")
    return profile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["record", "apply", "status"])
    parser.add_argument("file", nargs="?")
    args = parser.parse_args()
    if args.action == "status":
        result = {"observations": observations(ROOT), "profile": load(ROOT / "data/personality/profile.json", {"version": 1, "traits": []})}
    elif not args.file:
        parser.error("请提供候选 JSON 文件。")
    else:
        lock = ROOT / "data/personality/.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        with lock.open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            if args.action == "record": result = record(ROOT, load(Path(args.file), None))
            else: result = apply(ROOT, load(Path(args.file), None))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
