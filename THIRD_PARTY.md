# 第三方代码与素材

- **Hermes Agent**：https://github.com/NousResearch/hermes-agent 。独立下载安装，不将运行时、其依赖和用户数据复制进仓库；适用上游许可证。已验证的提交见 `config/runtime.json`。
- **dsh-pet**：https://github.com/PC2005-cloud/dsh-pet 。桌宠动画源视频与 HEVC 编码器参考。编码器改编文件 `scripts/PetVideoEncoder.swift` 保留作者声明，MIT 原文在 `ui/public/pet/LICENSE-CODE.txt`。角色、动画、提示词和改编素材适用独立的非商业与署名条件，详见同目录 `ATTRIBUTION.md` 和 `LICENSE-ASSETS.txt`，不适用代码 MIT 授权。
- **角色设计**：上善无形（https://space.bilibili.com/4456176）、ZipZipPipe（https://space.bilibili.com/4168597），CC BY-NC-SA 4.0。探头姿态是参考角色的 AI 辅助二创，同样保留角色署名与非商业、相同方式共享条件。
- **头像与表情**：可以叫我云大人 / 雾雪（https://space.bilibili.com/103739 ，https://kiriyuki.com），图标参考 https://github.com/Loping151/dsh-nekowhale-stickers 。原文及说明保存在 `desktop/assets/`。运行时收藏的表情在私有 `data/` 中，不随 Git 发布。
- **前端依赖**：React、Vite、TypeScript、Lucide、react-markdown、remark-gfm、ws、yaml 等，版本由 `ui/package-lock.json` 锁定；各依赖保留自身许可证，不随本仓库变更。

更多实现参考见 `REFERENCES.md`。本项目不是 DeepSeek 官方应用。自编代码暂未单独指定开源许可证；公开可读不自动扩大任何第三方素材的授权范围。
