# 部署与模型配置

## 本地与团队部署

本地运行见 [快速开始](../README.md#快速开始)。团队部署可以使用 Docker Compose。

```bash
cp .env.example .env
docker compose up --build -d
```

Compose 默认监听主机的 127.0.0.1:8000，并使用持久卷保存 SQLite、上传素材和成品。内部使用时，设置 `AGENT_TEAM_USER` 和 `AGENT_TEAM_PASSWORD`，由已有的内网 HTTPS 代理提供访问入口。代理需保留原始 Host，并按 `AGENT_MAX_UPLOAD_MB` 调整请求体大小。应用按单实例运行，团队账号共用一个任务列表。录屏、账单凭证和服务配置由部署端管理。

## 可选实时模式

复制 [`.env.example`](../.env.example) 后，在服务端填写所需配置并重启。

| 服务 | 配置 | 用途 |
| --- | --- | --- |
| OpenAI 文本 | `AGENT_ENABLE_LIVE=1`、`OPENAI_API_KEY`、可选 `AGENT_TEXT_MODEL` | 文案、分镜和按字幕选片 |
| OpenAI 图像与语音 | 同一账号的模型权限、可选 `AGENT_IMAGE_MODEL` / `AGENT_SPEECH_MODEL` | 海报背景、视频旁白、无 SRT 时的录屏音频转写 |
| fal | `FAL_KEY` | 获取 Seedance 竖屏开场镜头，实时预热视频需要此配置 |

首次提交实时任务可能调用文本模型或音频转写。付费图像、视频与旁白在审核确认后按需请求。视频生成一旦取得任务编号，重试会查询同一远端任务。制作记录统计 API 请求次数，实际费用由供应商计费。实时旁白字幕按音频时长和句长近似分配，导出的 SRT 可继续校订。

实时剪辑会向文本服务发送与选片有关的字幕和用户要求。未提供 SRT 时会把分段音频交给语音转写服务。是否使用实时接口由部署方根据素材授权选择。模型请求、视频队列和下载流程已有模拟验证，生产账号权限、实际费用和内网上线仍需在部署方的环境中验证。

- [OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)
- [OpenAI 图像生成](https://developers.openai.com/api/reference/resources/images/methods/generate)
- [OpenAI 语音接口](https://developers.openai.com/api/reference/cli/resources/audio)
- [fal Seedance 视频接口](https://fal.ai/models/bytedance/seedance-2.0/fast/text-to-video/api)
- [fal 队列](https://fal.ai/docs/documentation/model-apis/inference/queue)
