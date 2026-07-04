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

本地模式可以使用本地 faster-whisper；公开产品默认使用 ElevenLabs Scribe 云端转录。不要把本地性能数据直接写成云端产品普遍表现。

### 云服务器公开试用

推荐形态：

- ECS 跑 FastAPI、静态前端、FFmpeg。
- Nginx 做 HTTPS、反向代理、大文件上传限制和 SSE 转发。
- ElevenLabs Scribe 作为默认云转录路径。
- SQLite 用于小规模账号、任务历史和事件日志。
- 定期清理本地源文件和产物。

公开试用建议开启：

```bash
FLUENTFLOW_PUBLIC_MODE=1
FLUENTFLOW_ALLOWED_STT_PROVIDERS=elevenlabs_scribe
FLUENTFLOW_DEFAULT_STT_PROVIDER=elevenlabs_scribe
FLUENTFLOW_AUTH_MODE=accounts
```

如果没有账号系统，只能算封闭 Beta 或临时演示，不要承诺跨设备找回历史。

## 2. 关键目录

默认运行数据目录不在仓库内。macOS 默认是 `~/Library/Application Support/FluentFlow`；Linux 默认是 `$XDG_DATA_HOME/fluentflow` 或 `~/.local/share/fluentflow`；Windows 默认是 `%APPDATA%/FluentFlow`。可以用 `FLUENTFLOW_DATA_DIR` 覆盖。

当前运行目录中的常见路径：

| 路径 | 用途 | 是否可删除 |
| --- | --- | --- |
| `fluentflow_events.sqlite` | 事件日志 | 不要手动删除；需要备份后再处理 |
| `fluentflow_jobs.sqlite` | 任务历史 | 不要手动删除；会影响历史任务 |
| `fluentflow_accounts.sqlite` 或部署指定账号库 | 账号与会话 | 不要删除 |
| `sources/` | 上传源文件 | 可按清理策略删除 |
| `artifacts/` | 生成的字幕、摘要等产物 | 可按清理策略删除 |
| `edited_transcripts/` | 用户编辑后的转录稿 | 谨慎删除，属于用户劳动成果 |
| `transcript_edit_records/` | 转录修改记录 | 谨慎删除，可用于质量评估 |
| `legacy_migration/` | 迁移时保全的同名冲突旧文件 | 迁移验证 14 天后可删除 |
| `logs/uvicorn.log` | 后端运行日志 | 可归档或轮转 |

仓库内 `data/`、`backend/data/`、`视频文件/`、`backend/视频文件/` 是旧路径、测试运行数据或迁移前产物，不是新的默认运行目录。删除前必须先确认迁移 manifest 和当前产品历史都已验证。

迁移旧仓库数据：

```bash
./venv/bin/python scripts/migrate_runtime_storage.py
./venv/bin/python scripts/migrate_runtime_storage.py --apply
```

脚本会复制旧数据，不会删除旧目录；同名但内容不同的目标文件会保存在系统数据目录的 `legacy_migration/` 下。迁移成功后会写入 `legacy_runtime_migration_manifest.json`，其中包含 `legacy_cleanup_after`。默认规则：旧仓库运行数据保留 14 天；迁移验证通过且超过该日期后，才可以删除仓库里的旧 `data/`、`backend/data/`、`视频文件/` 和 `backend/视频文件/`。

云服务器建议显式把长期数据放在 `/var/lib/fluentflow`，环境变量放在 `/etc/fluentflow/fluentflow.env`。

单台云服务器 Beta 的常用路径：

| 路径 | 用途 |
| --- | --- |
| `/opt/fluentflow` | 项目代码 |
| `/etc/fluentflow/fluentflow.env` | 环境变量 |
| `/var/lib/fluentflow/fluentflow_accounts.sqlite` | 账号数据库 |
| `/var/lib/fluentflow/fluentflow_jobs.sqlite` | 任务数据库 |
| `/var/lib/fluentflow/fluentflow_events.sqlite` | 事件日志 |
| `/var/lib/fluentflow/sources` | 上传源文件 |
| `/var/lib/fluentflow/artifacts` | 结果产物 |
| `/var/lib/fluentflow/video-sources` | 视频链接下载缓存 |
| `/var/backups/fluentflow` | 服务器备份 |

## 3. 环境变量分层

### 必需基础配置

```bash
PORT=8000
FLUENTFLOW_PUBLIC_MODE=1
FLUENTFLOW_AUTH_MODE=accounts
FLUENTFLOW_ACCOUNT_DB_PATH=/var/lib/fluentflow/fluentflow_accounts.sqlite
```

### ElevenLabs Scribe

```bash
ELEVENLABS_API_KEY=...
```

`ELEVENLABS_API_KEY` 只应配置在后端环境或后端本地配置中，不要暴露给普通用户或写入前端代码。

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
# 国内飞书可显式指定：
LARK_OPEN_BASE_URL=https://open.feishu.cn
# 生产回调 URL 要和飞书开放平台里配置的一致：
FEISHU_OAUTH_REDIRECT_URI=https://your-domain.example/account/feishu/oauth/callback
```

`LARK_APP_ID` / `LARK_APP_SECRET` 是 FluentFlow 自己的飞书 OAuth 应用凭证，不应该作为“维护者身份替所有用户创建文档”的正式商业默认路径。多用户上线时，用户需要先连接自己的飞书账号，后端保存账号级 Feishu connection，导出时使用该用户的 `user_access_token` 写入用户自己的飞书空间。

当前兼容路径仍然存在：

- `lark_openapi`：维护者 App / tenant-token 路径，适合内部自用或兼容旧部署，不适合作为多用户默认导出。
- `lark_cli`：本机 lark-cli 登录身份路径，适合个人桌面自动化。
- `user_oauth` / `feishu_user_oauth`：用户授权路径，适合正式多用户产品。缺少用户连接时 `/export-lark` 会要求先连接飞书。

账号库会保存 Feishu refresh token。当前项目没有引入专用加密依赖，生产部署必须至少保护账号数据库和磁盘权限；更严格的商业部署应接入 KMS 或数据库字段加密。

如果暂时不开放飞书导出，部署自检里的飞书项可以接受 `WARN`；如果页面承诺能导出飞书，则必须配置应用权限并 smoke test。

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

如果有长任务正在进行，不要随便重启后端。重启会中断当前进程内运行的任务；任务状态恢复取决于任务持久化和队列恢复逻辑。

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

### 云服务器部署脚本

```bash
cd /opt/fluentflow
bash deploy/deploy_server.sh
```

脚本会先备份，再拉取代码、安装依赖、构建前端、跑部署自检、重启服务和检查 `/health`。如果检查失败，会回滚到部署前的 Git 版本。

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
- ElevenLabs、LLM、Nginx 大文件上传和 SSE 配置不能靠用户试出来，应该上线前先查。

## 6. Smoke Test

每次部署后至少跑一遍：

1. 注册或登录测试账号。
2. 上传 1-3 分钟小视频，确认能生成转录和摘要。
3. 上传接近真实体量的视频，确认 ElevenLabs 云端转录能完成。
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
sqlite3 "$HOME/Library/Application Support/FluentFlow/fluentflow_jobs.sqlite" ".backup 'backups/jobs-YYYYMMDD.sqlite'"
sqlite3 "$HOME/Library/Application Support/FluentFlow/fluentflow_events.sqlite" ".backup 'backups/events-YYYYMMDD.sqlite'"
```

备份文件可能包含文件名、任务状态、错误原因和飞书 URL，不要公开上传。

服务器数据备份：

```bash
cd /opt/fluentflow
./venv/bin/python scripts/backup_server_state.py --env-file /etc/fluentflow/fluentflow.env
```

默认不备份 `/etc/fluentflow/fluentflow.env`，避免密钥进入备份包。

恢复前先 dry-run：

```bash
cd /opt/fluentflow
./venv/bin/python scripts/restore_server_state.py /var/backups/fluentflow/fluentflow-backup-YYYYMMDDTHHMMSSZ.tar.gz --env-file /etc/fluentflow/fluentflow.env
```

确认路径无误后再恢复：

```bash
sudo systemctl stop fluentflow
cd /opt/fluentflow
./venv/bin/python scripts/restore_server_state.py /var/backups/fluentflow/fluentflow-backup-YYYYMMDDTHHMMSSZ.tar.gz --env-file /etc/fluentflow/fluentflow.env --apply
sudo systemctl start fluentflow
```

## 8. 常见故障处理

### 前端显示还在转录，但任务其实已完成

优先检查：

```bash
sudo journalctl -u fluentflow -n 200 --no-pager
```

然后确认 `/jobs/{task_id}` 是否能返回最新状态。若后端已完成但前端旧状态不刷新，重点排查任务轮询和 SSE 重连逻辑。

### ElevenLabs 云端转录失败或长时间等待

先判断是配置、额度、网络还是文件体量问题：

```bash
./venv/bin/python scripts/check_deployment_readiness.py
```

检查：

- `ELEVENLABS_API_KEY` 是否已配置。
- ElevenLabs 账户额度或套餐是否足够。
- 上传后的 MP3 是否过大或音频时长是否超出当前限制。
- 后端日志里 ElevenLabs 返回的是认证、额度、格式还是网络错误。

不要用假的百分比掩盖云端等待；界面应该展示真实等待状态和可理解的失败原因。

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
du -sh "$HOME/Library/Application Support/FluentFlow"/*
```

先 dry-run 清理，再决定是否 apply。不要直接删除整个运行数据目录，也不要在迁移验证前删除旧仓库 `data/`；那会破坏任务历史、事件日志、编辑稿和账号数据。

## 9. 维护记录规则

每次上线或重要修复后：

1. 在 `docs/changelog.md` 记录用户可见变化和注意事项。
2. 如果是产品判断或方案取舍，补到 `docs/product_growth_log.md`。
3. 如果改变埋点或指标口径，更新 `docs/event_logging.md`。
4. 如果改变部署、环境变量、清理策略或上线检查，更新本手册或 `deploy/README.md`。
5. 跑 `docs/regression_checklist.md` 中对应级别的检查。

文档不是装饰，它的作用是减少下一次修改时的误判。
