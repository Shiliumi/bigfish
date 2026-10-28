# 图标和社区参考

本机「大肥鱼」使用社区二创的 DeepSeek 鲸鱼娘形象，非 DeepSeek 官方应用或官方人物。

图标原文件：https://github.com/Loping151/dsh-nekowhale-stickers/blob/main/icon.webp
作者：可以叫我云大人 / 雾雪；作者页 https://space.bilibili.com/103739 ，网站 https://kiriyuki.com 。
形象设计基于 ZipZipPipe https://space.bilibili.com/4168597 与 上善无形 https://space.bilibili.com/4456176 。
图像按该仓库 LICENSE-ASSETS 的非商业分享条件用于本机个人应用，保留原作者与网站。原文同目录 LICENSE-ASSETS.txt。

人格是为这个程序重新编写的文本，参考社区相处方式，不整段复制第三方角色卡：
- https://zlb.ink/t/topic/49758
- https://www.reddit.com/r/DeepSeek/comments/1vvwno1/sharing_some_fancreated_images_of_deepseek_from/
- https://aigengtu.com/persona
- https://github.com/YunYueSama/codex-deepseek-pet/blob/main/docs/角色设定.md

# 小鲸鱼动画署名

动画与源视频：PC2005-cloud/dsh-pet https://github.com/PC2005-cloud/dsh-pet ，源视频包 https://github.com/PC2005-cloud/dsh-pet/releases/tag/assets-videos 。
形象：上善无形 https://space.bilibili.com/4456176 与 ZipZipPipe https://space.bilibili.com/4168597 。

使用16段1280×720、24fps原视频：待机、思考、忙碌、挥手、开心、挠痒、害羞、傲娇、悬空拖起、睡眠、哈欠、伸懒腰、张望、吃白饭、尾巴拍地、庆祝。
本地改编：按颜色与连通区域去除绿幕，保留人物和近身道具；统一站立基准，输出640×720、24fps、完整时长的透明WebM与HEVC-alpha MOV，以及海报帧。不使用旧版220px序列图。
准备脚本 scripts/prepare_pet_assets.py；原生HEVC编码器 scripts/PetVideoEncoder.swift 改编自上游同名编码器，代码MIT，保留许可证。

形象及改编动画按 CC BY-NC-SA 4.0 署名、非商业、相同方式共享。https://creativecommons.org/licenses/by-nc-sa/4.0/deed.zh-hans
素材不得商用；原作者的素材条款与代码MIT许可见同目录 LICENSE-ASSETS.txt / LICENSE-CODE.txt。
