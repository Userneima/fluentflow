# FluentFlow 运维手册

本文档面向长期维护。目标不是替代部署教程，而是让维护者知道“出问题时先看哪里、怎么安全重启、哪些数据不能乱删”。

相关文档：

- `deploy/README.md`：云服务器部署步骤。
- `docs/beta_deployment_checklist.md`：公开试用前检查清单。
- `docs/event_logging.md`：事件日志和指标口径。
- `docs/regression_checklist.md`：每次改动后的回归验证。

## 1. 运行形态

### 本地开发 / 本地使用

常用命令：

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
npm ci
npm run build:frontend
python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

访问：

```text
http://127.0.0.1:8000
```

本地模式可以使用本地 faster-whisper，也可以配置 Azure Batch。不要把本地性能数据直接写成云端产品普遍表现。

### 云服务器公开试用

推荐形态：

- ECS 跑 FastAPI、静态前端、FFmpeg。
- Nginx 做 HTTPS、反向代理、大文件上传限制和 SSE 转发。
- Azure Batch 作为默认云转录路径。
- SQLite 用于小规模账号、任务历史和事件日志。
- 定期清理本地源文件和产物。

公开试用建议开启：

```bash
FLUENTFLOW_PUBLIC_MODE=1
FLUENTFLOW_ALLOWED_STT_PROVIDERS=azure_batch
FLUENTFLOW_DEFAULT_STT_PROVIDER=azure_batch
FLUENTFLOW_AUTH_MODE=accounts
```

如果没有账号系统，只能算封闭 Beta 或临时演示，不要承诺跨设备找回历史。

## 2. 关键目录

本地仓库中常见路径：

| 路径 | 用途 | 是否可删除 |
| --- | --- | --- |
| `data/fluentflow_events.sqlite` | 事件日志 | 不要手动删除；需要备份后再处理 |
| `data/jobs.sqlite` | 任务历史 | 不要手动删除；会影响历史任务 |
| `data/accounts.sqlite` 或部署指定账号库 | 账号与会话 | 不要删除 |
| `data/sources/` | 上传源文件 | 可按清理策略删除 |
| `data/artifacts/` | 生成的字幕、摘要等产物 | 可按清理策略删除 |
| `data/edited_transcripts/` | 用户编辑后的转录稿 | 谨慎删除，属于用户劳动成果 |
| `data/transcript_edit_records/` | 转录修改记录 | 谨慎删除，可用于质量评估 |
| `logs/uvicorn.log` | 后端运行日志 | 可归档或轮转 |

云服务器建议把长期数据放在 `/var/lib/fluentflow`，环境变量放在 `/etc/fluentflow/fluentflow.env`。

## 3. 环境变量分层

### 必需基础配置

```bash
PORT=8000
FLUENTFLOW_PUBLIC_MODE=1
FLUENTFLOW_AUTH_MODE=accounts
FLUENTFLOW_ACCOUNT_DB_PATH=/var/lib/fluentflow/fluentflow_accounts.sqlite
```

### Azure Batch

```bash
AZURE_SPEECH_ENDPOINT=...
AZURE_SPEECH_KEY=...
AZURE_BLOB_CONTAINER_SAS_URL=...
```

前端可以显示“地址”，但后端应该负责把地区或地址转成真实调用 URL。不要把 Key、SAS 或 App Secret 暴露给普通用户。

### AI 摘要

```bash
DEEPSEEK_API_KEY=...
# 或
OPENAI_API_KEY=...
```

至少配置一个可用的 LLM Provider。没有 LLM Key 时，只能跑仅转录或字幕整理链路。

### 飞书导出

```bash
LARK_APP_ID=...
LARK_APP_SECRET=...
```

如果暂时不开放飞书导出，部署自检里的飞书项可以接受 `WARN`；如果页面承诺能导出飞书，则必须配置并 smoke test。

### 额度限制

```bash
FLUENTFLOW_MAX_UPLOAD_MB=2048
FLUENTFLOW_MAX_QUEUE_FILES=5
FLUENTFLOW_MAX_ACTIVE_JOBS_PER_CLIENT=2
FLUENTFLOW_MAX_ACTIVE_JOBS_GLOBAL=6
FLUENTFLOW_DAILY_JOB_LIMIT_PER_CLIENT=10
FLUENTFLOW_DAILY_JOB_LIMIT_GLOBAL=80
FLUENTFLOW_DAILY_UPLOAD_MB_PER_CLIENT=4096
FLUENTFLOW_DAILY_UPLOAD_MB_GLOBAL=32768
FLUENTFLOW_SUBMISSION_RATE_LIMIT_PER_IP=12
FLUENTFLOW_SUBMISSION_RATE_LIMIT_WINDOW_SECONDS=60
FLUENTFLOW_MAX_MEDIA_DURATION_SECONDS=14400
```

公开试用时不要关闭这些限制。它们不是为了“限制用户”，而是为了避免单机服务被少量长任务拖垮。

## 4. 构建、启动、重启

### 本地重新构建前端

```bash
npm run build:frontend
```

只改 `frontend/src/` 后，需要重新构建。Vite 会输出新的 `frontend/dist/` hash 资源，后端会优先托管这个目录。

### 本地启动后端

```bash
python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

如果有长任务正在进行，不要随便重启后端。重启会中断当前进程内运行的任务；Azure Batch 外部任务可能仍在云端跑，但本地状态恢复取决于任务持久化和轮询恢复逻辑。

### 云服务器重启服务

```bash
sudo systemctl restart fluentflow
sudo systemctl status fluentflow
```

查看日志：

```bash
sudo journalctl -u fluentflow -n 200 --no-pager
sudo journalctl -u fluentflow -f
```

修改 Nginx 配置后：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## 5. 上线前自检

在服务器上执行：

```bash
set -a
. /etc/fluentflow/fluentflow.env
set +a
./venv/bin/python scripts/check_deployment_readiness.py
```

如果上线承诺飞书导出：

```bash
./venv/bin/python scripts/check_deployment_readiness.py --require-lark
```

原则：

- `FAIL` 必须处理。
- 飞书如果不是本次开放能力，可以接受 `WARN`。
- Azure、LLM、Nginx 大文件上传和 SSE 配置不能靠用户试出来，应该上线前先查。

## 6. Smoke Test

每次部署后至少跑一遍：

1. 注册或登录测试账号。
2. 上传 1-3 分钟小视频，确认能生成转录和摘要。
3. 上传接近真实体量的视频，确认 Azure Batch 能完成。
4. 导入一份 SRT/TXT，确认跳过 STT 后可以生成摘要。
5. 在编辑器修改一段转录，刷新页面后确认修改没有丢。
6. 下载 TXT/SRT/Markdown。
7. 如果开放飞书导出，确认飞书文档 URL 可打开。
8. 换浏览器或账号，确认看不到上一个用户的历史。

详细回归项见 `docs/regression_checklist.md`。

## 7. 清理与备份

先 dry-run：

```bash
python3 scripts/cleanup_storage.py
```

确认后执行：

```bash
python3 scripts/cleanup_storage.py --apply
```

清理前要理解：

- 上传源文件通常可以短保留。
- 字幕、摘要、编辑稿和修改记录属于用户可复用产物，保留周期应长于源文件。
- 事件日志和任务数据库不应该通过清理脚本随意删除。

建议公开试用阶段定期备份：

```bash
sqlite3 data/jobs.sqlite ".backup 'backups/jobs-YYYYMMDD.sqlite'"
sqlite3 data/fluentflow_events.sqlite ".backup 'backups/events-YYYYMMDD.sqlite'"
```

备份文件可能包含文件名、任务状态、错误原因和飞书 URL，不要公开上传。

## 8. 常见故障处理

### 前端显示还在转录，但任务其实已完成

优先检查：

```bash
sudo journalctl -u fluentflow -n 200 --no-pager
```

然后确认 `/jobs/{task_id}` 是否能返回最新状态。若后端已完成但前端旧状态不刷新，重点排查任务轮询和 SSE 重连逻辑。

### Azure Batch 长时间等待

先判断是正常排队还是配置问题：

```bash
./venv/bin/python scripts/check_azure_batch_transcription.py /path/to/sample.mp4 --dry-run
```

检查：

- Speech 地址和 Key 是否正确。
- Blob container SAS 是否过期。
- 上传后的 MP3 是否过大。
- Azure 返回状态是否为 `NotStarted`、`Running`、`Succeeded` 或失败状态。

不要用假的百分比掩盖 Azure 排队；界面应该展示真实等待状态。

### 上传失败或 Nginx 直接断开

检查 Nginx：

```nginx
client_max_body_size 2048m;
proxy_read_timeout 86400s;
proxy_send_timeout 86400s;
proxy_request_buffering off;
proxy_buffering off;
```

`client_max_body_size` 要不小于后端 `FLUENTFLOW_MAX_UPLOAD_MB`。

### 摘要质量差

先判断是转录质量问题，还是摘要策略问题：

- 如果转录稿本身错漏多，优先评估 STT provider、语言、模型和音频质量。
- 如果转录稿完整但笔记漏内容，优先尝试高保真笔记模式。
- 不要只靠改提示词掩盖长字幕被过度概括的问题。

### 飞书导出失败

检查：

- `LARK_APP_ID` / `LARK_APP_SECRET` 是否配置。
- 飞书应用权限是否包含文档创建和写入。
- 目标父文档或知识库节点是否有权限。
- 如果使用 lark-cli，确认服务器 PATH 中有可执行命令，并且登录态有效。

### 磁盘增长过快

查看目录：

```bash
du -sh data/*
```

先 dry-run 清理，再决定是否 apply。不要直接 `rm -rf data`，那会删除任务历史、事件日志、编辑稿和账号数据。

## 9. 维护记录规则

每次上线或重要修复后：

1. 在 `docs/changelog.md` 记录用户可见变化和注意事项。
2. 如果是产品判断或方案取舍，补到 `docs/product_growth_log.md`。
3. 如果改变埋点或指标口径，更新 `docs/event_logging.md`。
4. 如果改变部署、环境变量、清理策略或上线检查，更新本手册或 `deploy/README.md`。
5. 跑 `docs/regression_checklist.md` 中对应级别的检查。

文档不是装饰，它的作用是减少下一次修改时的误判。
