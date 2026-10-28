# 小鲸鱼动画署名

动画与源视频：PC2005-cloud/dsh-pet https://github.com/PC2005-cloud/dsh-pet ，源视频包 https://github.com/PC2005-cloud/dsh-pet/releases/tag/assets-videos 。
形象：上善无形 https://space.bilibili.com/4456176 与 ZipZipPipe https://space.bilibili.com/4168597 。

使用16段1280×720、24fps原视频：待机、思考、忙碌、挥手、开心、挠痒、害羞、傲娇、悬空拖起、睡眠、哈欠、伸懒腰、张望、吃白饭、尾巴拍地、庆祝。
本地改编：按颜色与连通区域去除绿幕，保留人物和近身道具；统一站立基准，输出640×720、24fps、完整时长的透明WebM与HEVC-alpha MOV，以及海报帧。不使用旧版220px序列图。
准备脚本 scripts/prepare_pet_assets.py；原生HEVC编码器 scripts/PetVideoEncoder.swift 改编自上游同名编码器，代码MIT，保留许可证。

形象及改编动画按 CC BY-NC-SA 4.0 署名、非商业、相同方式共享。https://creativecommons.org/licenses/by-nc-sa/4.0/deed.zh-hans
素材不得商用；原作者的素材条款与代码MIT许可见同目录 LICENSE-ASSETS.txt / LICENSE-CODE.txt。

## 1.6 专用探头素材

`peek-right-v2.png`、`peek-bottom-v2.png`、`peek-top-v2.png` 由本项目使用内置 imagegen 工具，以本项目已署名的待机形象作为参考补绘，分别为侧边探身、底部探头、顶部悬挂。左侧在渲染时水平镜像侧边素材。不是原视频的旋转裁切，不声称是上游原作动画。使用真实透明 alpha；原始输出未被像素编辑，显示位置根据 alpha 包围盒与屏幕真实外缘对齐。沿用形象的 CC BY-NC-SA 4.0 条件及上方形象作者署名；仅个人非商业使用。提示词与生成说明见项目 desktop/assets/peek-prompts.md。
