# 桌宠素材

完整视频以 Release 素材包分发，源码库只保留 PNG 海报、专门补绘的探头素材、播放清单、哈希和署名。不要将本机 data/stickers 或截图当作发布素材。

## 恢复当前版本

运行 `python3 scripts/restore_pet_assets.py`。需要 GitHub CLI 和仓库访问权限。手动下载时使用 `--archive 路径`，只校验本地文件用 `--check`。仓库迁移可用 `--repo owner/repo`，仍按固定标签与校验清单恢复。

## 从上游视频重新制作

上游：[PC2005-cloud/dsh-pet](https://github.com/PC2005-cloud/dsh-pet)；原片位于 [assets-videos Release](https://github.com/PC2005-cloud/dsh-pet/releases/tag/assets-videos)。遵循上游素材授权和署名，不执行第三方仓库安装脚本。

1. 将所需 16 段 1280×720 / 24fps 原视频放入 `.setup/references/dsh-pet/original/`。`config/pet-sources.json` 列出英文动作名与中文原片名的对应关系；保存为英文动作名 `.mp4`。
2. 准备 Python 虚拟环境与编码器：

```bash
python3 -m venv .setup/media-tools/venv
.setup/media-tools/venv/bin/pip install pillow numpy scipy imageio-ffmpeg
xcrun swiftc -O scripts/PetVideoEncoder.swift -o .setup/media-tools/pet-video-encoder
.setup/media-tools/venv/bin/python scripts/prepare_pet_assets.py
```

3. 脚本完整保留 24fps 和片长，去绿幕并统一站立基准，输出透明 HEVC MOV、VP9 WebM、海报和清单。重新编码可能随编码器版本产生不同字节，不能冒充已发布素材的哈希；发布新素材时需同步更新 `config/pet-assets.json`、标签与 Release 文件。

探头姿态不来自视频旋转；三张 PNG 及 `peek-manifest.json` 已随源码提供。补绘记录见 `desktop/assets/peek-prompts.md`。授权说明见 `ui/public/pet/ATTRIBUTION.md`、`LICENSE-ASSETS.txt` 和 `LICENSE-CODE.txt`。
