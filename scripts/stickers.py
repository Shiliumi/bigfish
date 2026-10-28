#!/usr/bin/env python3
"""A local, attributed whale-girl sticker collection, selectable by the agent."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import re
import struct
import tempfile
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/stickers"
SITE = "https://kiriyuki.com"
META = "https://raw.githubusercontent.com/Loping151/dsh-nekowhale-stickers/main/meta/nekowhale.json"
EXCLUDE = re.compile(r"舌吻|色情|性交|情趣|黄油|调情|诱惑|魅惑|高潮|发情|性欲|色色|瑟瑟|脱衣|亲嘴|亲吻|接吻|成人|舔|恋爱|占有|鱼片|NSFW|R18", re.I)


def load(name, fallback):
    file = DATA / name
    return json.loads(file.read_text()) if file.exists() else fallback


def save(name, value):
    DATA.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=DATA, delete=False) as output:
        json.dump(value, output, ensure_ascii=False, indent=2); output.write("\n")
        tmp = Path(output.name)
    tmp.chmod(0o600); tmp.replace(DATA / name)


def fetch(url, maximum):
    if urllib.parse.urlsplit(url).hostname not in {"kiriyuki.com", "raw.githubusercontent.com"}:
        raise ValueError("只从已确认来源的素材站读取，不下载任意地址。")
    class SourceRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            parsed = urllib.parse.urlsplit(newurl)
            if parsed.scheme != 'https' or parsed.hostname not in {'kiriyuki.com', 'raw.githubusercontent.com'}:
                raise ValueError('素材重定向到其他来源，已跳过。')
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    request = urllib.request.Request(url, headers={"User-Agent": "Bigfish-personal-stickers (+https://kiriyuki.com)"})
    with urllib.request.build_opener(SourceRedirect).open(request, timeout=20) as response:
        if urllib.parse.urlsplit(response.url).hostname not in {"kiriyuki.com", "raw.githubusercontent.com"}:
            raise ValueError("素材被重定向到其他站点，已跳过。")
        data = response.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError("素材过大，已跳过。")
    return data


def sync(force=False):
    existing = load("catalog.json", {})
    if not force and existing and (datetime.now(timezone.utc) - datetime.fromisoformat(existing["updated_at"])).total_seconds() < 86400:
        return existing
    try:
        meta = json.loads(fetch(META, 2 * 1024 * 1024))
        manifest = json.loads(fetch(SITE + "/api/kit/nekowhale", 2 * 1024 * 1024))
    except (OSError, ValueError):
        if existing:
            return existing
        raise
    annotations = {item["id"]: item for item in meta["stickers"]}
    base = manifest["gif_base"]
    if not base.startswith("/") or base.startswith("//"):
        raise ValueError("素材目录不正确。")
    items = []
    for asset in manifest["items"]:
        note = annotations.get(asset["id"])
        if not note or asset["pack"] != "大肥鱼" or EXCLUDE.search(json.dumps(note, ensure_ascii=False)) or asset.get("bytes", 0) > 2 * 1024 * 1024:
            continue
        items.append({"id": hashlib.sha256(asset["id"].encode()).hexdigest()[:16], "original_id": asset["id"], "name": asset["name"], "emotion": note["emotion"], "tags": note["tags"], "use": note["use"], "description": note["desc"], "hash": asset["hash"], "url": SITE + base + "/" + urllib.parse.quote(asset["pack"]) + "/" + urllib.parse.quote(asset["file"], safe="") + "?h=" + asset["hash"], "source": SITE + "/showcase?p=" + urllib.parse.quote(asset["pack"]), "author": meta["attribution"]["author"], "license": "作者允许署名的非商业分享；见 desktop/assets/LICENSE-ASSETS.txt"})
    result = {"updated_at": datetime.now(timezone.utc).isoformat(), "attribution": meta["attribution"], "items": items}
    save("catalog.json", result)
    return result


def search(query, limit=8):
    items = sync()["items"]
    terms = query.lower().split()
    def score(item):
        return sum((6 if term in item["name"].lower() else 0) + (5 if term == item["emotion"].lower() else 0) + (3 if any(term in tag.lower() for tag in item["tags"]) else 0) + (1 if term in item["use"].lower() else 0) for term in terms)
    return sorted([item for item in items if not terms or score(item) > 0 or item["id"] == query], key=score, reverse=True)[:limit]


def collect(item):
    library = load("library.json", {"items": []})
    if any(previous["id"] == item["id"] for previous in library["items"]):
        return next(previous for previous in library["items"] if previous["id"] == item["id"])
    if len(library["items"]) >= 240:
        raise ValueError("已经有 240 张，先用熟悉的表情，不继续堆。")
    assets = DATA / "assets"; assets.mkdir(parents=True, exist_ok=True)
    if sum(file.stat().st_size for file in assets.glob("*.gif")) > 160 * 1024 * 1024:
        raise ValueError("表情收藏已到 160 MB，暂停新增。")
    data = fetch(item["url"], 2 * 1024 * 1024)
    if len(data) < 10 or data[:6] not in {b"GIF87a", b"GIF89a"} or max(struct.unpack("<HH", data[6:10])) > 1200:
        raise ValueError("文件不是大小合适的 GIF。")
    if hashlib.sha1(data).hexdigest()[:12] != item["hash"]:
        raise ValueError("素材版本与作者的清单不一致，已跳过。")
    destination = assets / (item["id"] + ".gif")
    with tempfile.NamedTemporaryFile("wb", dir=assets, delete=False) as output:
        output.write(data); tmp = Path(output.name)
    tmp.chmod(0o600); tmp.replace(destination)
    saved = {**item, "collected_at": datetime.now(timezone.utc).isoformat(), "file": item["id"] + ".gif", "bytes": len(data)}
    library["items"].append(saved); save("library.json", library)
    return saved


def compact(item):
    return {k: item[k] for k in ["id", "name", "emotion", "tags", "use", "author"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["search", "collect", "send", "discover", "status"])
    parser.add_argument("query", nargs="?", default="")
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    DATA.mkdir(parents=True, exist_ok=True)
    with (DATA / ".lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        if args.action == "status":
            library = load("library.json", {"items": []}); print(json.dumps({"collected": len(library["items"]), "available": len(load("catalog.json", {"items": []})["items"]), "items": [compact(i) for i in library["items"]]}, ensure_ascii=False)); return
        if args.action == "search":
            print(json.dumps([compact(i) for i in search(args.query, min(max(args.limit, 1), 12))], ensure_ascii=False, indent=2)); return
        if args.action == "discover":
            owned = {item["id"] for item in load("library.json", {"items": []})["items"]}
            candidates = search(args.query, 240)
            selected, emotions = [], set()
            for item in candidates:
                if item["id"] not in owned and item["emotion"] not in emotions:
                    selected.append(item); emotions.add(item["emotion"])
                if len(selected) >= min(max(args.limit, 1), 48): break
            if len(selected) < min(max(args.limit, 1), 48):
                selected.extend(i for i in candidates if i["id"] not in owned and i not in selected)
                selected = selected[:min(max(args.limit, 1), 48)]
        else:
            selected = [i for i in sync()["items"] if i["id"] == args.query]
            if not selected: raise ValueError("先 search 找到真实的表情 id，再收藏或发送。")
        results, failures = [], []
        for item in selected:
            try: results.append(collect(item))
            except (ValueError, OSError) as error: failures.append({"name": item["name"], "error": str(error)})
        if args.action == "send":
            if not results: raise ValueError("图片下载失败，这次先用文字回复。")
            item = results[0]; print(f'![{item["name"]}](/api/stickers/{item["id"]})')
        else: print(json.dumps({"collected": [compact(i) for i in results], "failed": failures}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
