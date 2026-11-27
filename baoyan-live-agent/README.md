# 保研直播智能剪辑与内容生产 Agent

面向升学内容运营的 Web 工作台。直播前，运营可以根据一份活动简报审核分镜并导出海报、预热视频和群文案。直播结束后，运营可以按受众与时长筛选片段，跳到原片核对，再导出带字幕的竖屏短视频。

[72 秒工作台实操录屏（下载播放）](docs/workbench-demo.mp4) · [系统架构](docs/architecture.md) · [部署与模型配置](docs/deployment.md)

## 快速开始

可使用 macOS 或 Linux。首次启动需要 Python 3.11+、Node.js 22.12+、中文字体，以及包含 `libx264` 和 `libass` 的 FFmpeg。macOS 可用 `brew install ffmpeg`，Debian / Ubuntu 可用 `sudo apt-get install ffmpeg fonts-noto-cjk`。

在项目根目录运行：

```bash
bash start.sh
```

打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。脚本会建立 Python 虚拟环境并从源码构建前端。本地样例模式可直接使用。

## 操作与样例成品

| 流程 | 怎么操作 | 可核对的成品 |
| --- | --- | --- |
| 直播预热 | 「制作预热」→「填入样例简报」→ 生成方案 → 审核分镜、活动时间和文案 → 导出 | [活动海报](examples/exports/promo/poster.jpg) · [预热视频](examples/exports/promo/preview.mp4) · [群文案](examples/exports/promo/copy.txt) · [制作记录](examples/exports/promo/record.json) |
| 回放剪辑 | 「剪辑回放」→「使用示例录屏」→ 生成候选 → 点击时间码核对原片 → 审核切点并导出 | [37.8 秒家长版](examples/exports/replay-parents/clip.mp4) · [对应字幕](examples/exports/replay-parents/clip.srt) · [原片时间码与原话](examples/exports/replay-parents/record.json) |

预热演示先生成首版，再把开播时间从 **19:00 改成 20:00**。一处修改会更新海报、视频片尾和群文案。回放演示从原片 **01:03.000–01:40.800** 裁切，保留原音频并把字幕时间轴平移到成片起点。

应用支持上传自有 **MP4 + UTF-8 SRT**，也支持编辑已完成的任务、重新选片和按成品版本下载。素材、输入与对应成品的来源见 [样例说明](examples/README.md)。

## 本地处理与实时调用

| 功能 | 本地样例模式 | 实时模式 |
| --- | --- | --- |
| 预热方案和文案 | 从活动简报提取议题，按模板整理内容 | 文本模型生成预热方案、分镜和渠道文案 |
| 海报、视频合成 | 使用仓库内自制背景、开场素材和配乐，按实际输入重新排版和渲染 | 可生成背景图、一个约 4 秒的开场镜头和旁白，再交给本地媒体模块合成 |
| 录屏选片 | 用已有 SRT 按受众、关键词和字幕边界推荐片段 | 可转写录屏音频，并通过文本模型按字幕内容选片 |
| 审核、裁切、字幕、下载 | 在本地实际执行 | 在本地实际执行 |

实时模式默认关闭。模型适配层已经实现，验证覆盖本地流程、模拟服务响应和视频任务重试。真实账号下的付费调用与公司内网部署仍待环境验收。README 里的成品均可用自制样例和本地模式复现。

## 项目结构

| 路径 | 负责什么 |
| --- | --- |
| [`ui/src/`](ui/src) | React + TypeScript 工作台。包含创建任务、方案审核、切点编辑和成品预览 |
| [`app/main.py`](app/main.py)、[`app/models.py`](app/models.py) | FastAPI 入口、请求校验、素材上传与下载 |
| [`app/workflow.py`](app/workflow.py)、[`app/store.py`](app/store.py) | 后台任务、SQLite 状态、审核后执行、生成素材复用和成品版本 |
| [`app/planning.py`](app/planning.py) | 预热方案、字幕解析、候选片段推荐和校验 |
| [`app/media.py`](app/media.py)、[`app/providers.py`](app/providers.py) | Pillow 海报排版、FFmpeg 剪接与压字幕、第三方模型 API |
| [`examples/`](examples)、[`scripts/`](scripts) | 可复现的自制输入、样例成品和素材生成脚本 |
| [`tests/`](tests)、[`.github/workflows/ci.yml`](.github/workflows/ci.yml) | 端到端导出测试、付费接口重试合约测试、GitHub 验证流程 |

## 验证

完成启动依赖安装后，可在另一个终端运行：

```bash
.venv/bin/python -m unittest discover -s tests -v
```

测试会通过 API 创建并审核任务，调用本机 FFmpeg 实际导出文件，检查竖屏分辨率、视频时长、字幕起点、改期后的海报与片尾，以及历史成品版本。付费视频重试测试用本地模拟响应验证同一任务编号的复用。GitHub 工作流执行前端构建和这套自动测试。
