# 自制样例与成品

| 文件 | 来源与用途 |
| --- | --- |
| [`brief.json`](brief.json) | 自制保研直播活动简报，初始开播时间为 19:00 |
| [`lecture.mp4`](lecture.mp4)、[`lecture.srt`](lecture.srt) | 用自制讲义和中文合成语音制作的录屏及对应字幕 |
| `planner.jpg`、`opening.mp4`、`music.wav` | 可复现的背景图、开场动画和配乐 |
| [`exports/promo/`](exports/promo) | 从样例简报制作预热，改期至 20:00 后实际导出的成品 |
| [`exports/replay-parents/`](exports/replay-parents) | 从样例录屏选取 01:03.000–01:40.800 实际剪出的家长版成品 |

样例的讲稿、图卡与视频均为演示素材。生成逻辑与讲义内容见 [`scripts/make_examples.py`](../scripts/make_examples.py)。每份成品目录中的 `record.json` 保存输入、批准的方案或剪辑点及成品时长。
