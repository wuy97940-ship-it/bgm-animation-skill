---
name: bgm-animation
description: 给 AI 编程助手的视频技能——从参考视频提取 BGM，纯代码渲染一支踩点歌词的手绘风原创角色动画短片并合成 mp4。任何能跑 Python 的 agent（ZCode / Claude Code / Codex / Cursor / iFlow…）都可用，不绑定特定平台。
---

# BGM 手绘动画（bgm-animation）

一句话：丢给 agent 一个参考视频 + 一句需求，它提取背景音乐、读出歌词节奏、写好分镜时间线，用 PIL 逐帧渲染一支**原创角色**手绘风小动画，合成 720x720@30fps 的 mp4 直接可发短视频。

## 环境

```bash
pip install pillow numpy imageio-ffmpeg
```

> imageio-ffmpeg 自带 ffmpeg 静态二进制，系统无需单独安装 ffmpeg。取二进制：`imageio_ffmpeg.get_ffmpeg_exe()`。

## 执行流程（agent 按此逐步执行）

### 1. 探测参考片

`ffmpeg -i ref.mp4` 读分辨率 / 帧率 / 时长。抖音导出多为 720x720 方形或 720x1280 竖屏，成片保持同尺寸同帧率。

### 2. 提取 BGM 并分析

```bash
ffmpeg -y -i ref.mp4 -vn -acodec copy bgm.m4a        # 无损抽音轨
python scripts/probe_bgm.py ref.mp4                  # RMS 包络 + 歌曲结束点
```

`probe_bgm.py` 输出 0.25s 粒度的 RMS 柱状图，两个关键用途：

- **找歌曲真实结束点**：参考片尾常带原作者的搜索卡 / 水印 / 静音尾巴（可达数秒）。成片时长 = 最后一个 >15% 能量窗 + 0.4s，结尾加 `afade` 淡出，别把尾巴带上
- **核对歌词窗口**：能量突变处基本就是歌词/乐句起点

### 3. 建歌词时间轴

从参考视频逐秒抽帧读字幕（`ffmpeg -ss <秒> -i ref.mp4 -frames:v 1 f.png`），记录每条字幕的起止时间 → 得到 `[(start, end, 歌词)]` 列表。参考片没字幕就按 RMS 拍点自拟分镜节拍。

### 4. 设计原创角色与分镜（铁律：不搬参考片画面）

参考片里有什么角色都**不要复刻**——画风可以致敬，角色必须原创。推荐 chibi 比例（大头短身、2-3 种主色），按歌词情绪排 4-8 个演出节拍。模板的时间线可当骨架参考：

```
起手画圆 → 画脸 → 画头发身体 → 挥手 → 道具/事件 → 情绪低谷（落泪）→ 释放（做梦/擦泪）→ 收尾（星星/彩蛋）
```

### 5. 渲染与合成

复制 `scripts/render_anim.py`，只改三处：顶部调色板、`SUBS` 歌词表、`main()` 时间线。然后：

```bash
python render_anim.py    # 逐帧输出 frames/0000.png ...
ffmpeg -y -framerate 30 -i frames/%04d.png -i bgm.m4a \
  -c:v libx264 -crf 18 -pix_fmt yuv420p \
  -af "afade=t=out:st=<歌尾-0.6>:d=0.6" -shortest -movflags +faststart final.mp4
```

### 6. 自查后交付

抽 10-13 个关键帧拼成 4x4 网格图自己先看一遍：文字有没有穿模、脸有没有画崩、字幕有没有越界、道具和手的位置对不对。有问题改时间线重渲，没问题再交给用户。

## 风格工艺（手绘感三件套，别省）

- **boiling line**：每 2 帧换一次随机种子，让所有轮廓整体抖动 ±1.6px——逐帧手绘的"呼吸感"全靠它，没有它就是死板的矢量图
- **2x 超采样**：1440x1440 绘制后 LANCZOS 降到 720，线条抗锯齿
- **partial polyline**：折线按总长比例截断，做"起手画圆 / 逐笔成形"的演出（参考片开场那个慢慢画出来的圆就是它）

## PIL 陷阱速查（每条都真踩过）

- `ellipse / rectangle / rounded_rectangle` 收 4 值 bbox，不是两个点元组
- `ImageDraw.text` 的 xy 必须是元组 `(x, y)`，传两个标量会把文字内容挤进 fill 参数报错
- 全程 RGBA 层合成，最后统一 `convert('RGB')`；淡出用 `Image.blend` 到白（纸感）而不是黑
- 抬手姿势的肘部要向外撑——沿用垂臂的肘点，手臂细线会横穿脸
- 填充多边形和描边要用**同一个抖动种子**，否则填充露出轮廓外一截
