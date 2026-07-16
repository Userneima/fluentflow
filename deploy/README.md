# FluentFlow 云服务器部署模板

这套模板用于封闭 Beta，不是正式 SaaS 多租户部署。

日常排障、备份、恢复和回滚步骤见 `docs/operations_runbook.md`。

## 1. 服务器依赖

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip ffmpeg nginx git curl ca-certificates
```

Ubuntu 22.04 默认源里的 Node.js 版本偏旧，可能导致前端构建时报 `Cannot find module 'node:path'`。先清理旧包，再安装 NodeSource 20：

```bash
sudo apt remove -y nodejs npm libnode-dev nodejs-doc || true
sudo apt autoremove -y
sudo apt clean
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo bash -
sudo apt install -y nodejs
node -v
npm -v
```

`node -v` 应显示 `v20.x.x`。

## 2. 部署目录

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin fluentflow
sudo mkdir -p /opt/fluentflow /etc/fluentflow /var/lib/fluentflow
sudo chown -R fluentflow:fluentflow /opt/fluentflow /var/lib/fluentflow
```

把项目放到 `/opt/fluentflow` 后。如果后续用 `root` 维护这个目录，需要先把它加入 Git 安全目录；否则会出现 `detected dubious ownership`：

```bash
git config --global --add safe.directory /opt/fluentflow
cd /opt/fluentflow
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
npm ci
npm run build:frontend
python3 scripts/check_release_gate.py
python3 scripts/write_release_manifest.py --environment setup
```

## 3. 环境变量

```bash
sudo cp deploy/fluentflow.env.example /etc/fluentflow/fluentflow.env
sudo chmod 600 /etc/fluentflow/fluentflow.env
sudo chown fluentflow:fluentflow /etc/fluentflow/fluentflow.env
```

必须替换：

- `ELEVENLABS_API_KEY`
- `DEEPSEEK_API_KEY` 或 `OPENAI_API_KEY`
- 如果需要飞书导出，再配置 `LARK_APP_ID` / `LARK_APP_SECRET`

正式多用户飞书导出应使用用户 OAuth connection，而不是维护者账号替所有用户创建文档。`LARK_APP_ID` / `LARK_APP_SECRET` 是 FluentFlow 飞书应用凭证；生产环境还应在飞书开放平台配置回调地址，并设置：

```bash
FEISHU_OAUTH_REDIRECT_URI=https://your-domain.example/account/feishu/oauth/callback
# 国内飞书部署通常还需要：
LARK_OPEN_BASE_URL=https://open.feishu.cn
```

后端账号库会保存 Feishu refresh token。请确保账号库路径只对 FluentFlow 服务用户可读写；更严格的生产环境应接入 KMS 或数据库字段加密。

如果启用“关键截图写入笔记”，飞书应用除了文档创建/写入权限外，还要具备文档图片素材上传和替换 docx 图片块的权限；否则飞书文档可能只有文字，没有截图。

正式上线建议启用账号系统，而不是访问码：

```bash
FLUENTFLOW_AUTH_MODE=accounts
FLUENTFLOW_DATA_DIR=/var/lib/fluentflow
FLUENTFLOW_ACCOUNT_DB_PATH=/var/lib/fluentflow/fluentflow_accounts.sqlite
FLUENTFLOW_JOB_DB_PATH=/var/lib/fluentflow/fluentflow_jobs.sqlite
FLUENTFLOW_EVENT_DB_PATH=/var/lib/fluentflow/fluentflow_events.sqlite
FLUENTFLOW_SESSION_DAYS=30
```

首次访问网页时注册的第一个账号会成为管理员。默认不开放后续自助注册；如果要让更多用户自己创建账号，再设置 `FLUENTFLOW_ALLOW_SIGNUPS=1`。

本地版如果要和云端实时同步，不要再维护一套独立本地账号库。开启云工作区代理后，本地后端会作为同源代理，把登录、任务、上传、历史和产物下载都转发到云端后端；云端任务库成为唯一事实来源，其他设备登录同一账号即可看到同一份历史。

该代理**默认硬禁用**：必须同时设置云端地址**和**显式开关，缺一不可。只设地址不设开关时，后端会忽略地址并在启动日志里明确提示（这是为避免一个残留的 `FLUENTFLOW_CLOUD_WORKSPACE_URL` 环境变量把上传静默转发到云端、导致上传卡死）。

```bash
FLUENTFLOW_CLOUD_WORKSPACE_URL=http://your-cloud-host
FLUENTFLOW_ENABLE_CLOUD_WORKSPACE=1
```

如果不设置（或只设地址、不设开关），本地版仍使用本地账号数据库与本地处理，只适合单机使用，历史不会自动同步到云端。

账号系统之外仍然要保留异常额度控制，用来限制云端成本：

```bash
FLUENTFLOW_MAX_ACTIVE_JOBS_PER_CLIENT=2
FLUENTFLOW_MAX_ACTIVE_JOBS_GLOBAL=6
FLUENTFLOW_DAILY_JOB_LIMIT_PER_CLIENT=10
FLUENTFLOW_DAILY_JOB_LIMIT_GLOBAL=80
FLUENTFLOW_DAILY_UPLOAD_MB_PER_CLIENT=4096
FLUENTFLOW_DAILY_UPLOAD_MB_GLOBAL=32768
FLUENTFLOW_SUBMISSION_RATE_LIMIT_PER_IP=12
FLUENTFLOW_SUBMISSION_RATE_LIMIT_WINDOW_SECONDS=60
FLUENTFLOW_HISTORY_RETENTION_PER_CLIENT=20
FLUENTFLOW_ARTIFACT_RETENTION_DAYS=30
FLUENTFLOW_QUEUE_PROCESS_TIMEOUT_SECONDS=86400
FLUENTFLOW_STALE_JOB_SECONDS=90000
```

### 媒体准入防线与紧急回滚

公开上传会在文件完整保存后、进入队列和调用转录服务前检查：空文件、容器可读性、实际格式与扩展名、可用音轨和首段音频解码；转录前仍会检查提取出的音频是否为数字静音。默认全部开启：

```bash
FLUENTFLOW_MEDIA_PREFLIGHT_ENABLED=1
FLUENTFLOW_MEDIA_GUARD_EMPTY_FILE_ENABLED=1
FLUENTFLOW_MEDIA_GUARD_CONTAINER_ENABLED=1
FLUENTFLOW_MEDIA_GUARD_EXTENSION_ENABLED=1
FLUENTFLOW_MEDIA_GUARD_AUDIO_STREAM_ENABLED=1
FLUENTFLOW_MEDIA_GUARD_AUDIO_DECODE_ENABLED=1
FLUENTFLOW_MEDIA_GUARD_SILENCE_ENABLED=1
```

如果某条防线误判正常媒体，只关闭对应的单条开关并重启服务；不要长期关闭总开关。被拒绝的请求会记录安全的失败分类，不记录媒体内容。上传网络流量已经发生，预检的边界是阻止无效媒体进入队列和消耗转录服务。

如果启用视频截图/关键帧能力，单台 ECS 或 Docker 部署先使用本机 FFmpeg：

```bash
FLUENTFLOW_KEYFRAME_EXTRACTION=1
FLUENTFLOW_KEYFRAME_PROVIDER=local_ffmpeg
DASHSCOPE_API_KEY=...
```

后续如果把截图任务拆到独立 Worker，再切换为：

```bash
FLUENTFLOW_KEYFRAME_PROVIDER=cloud_ffmpeg_worker
FLUENTFLOW_KEYFRAME_WORKER_URL=https://your-worker/keyframes
```

没有配置 Worker URL 时系统会跳过关键帧抽取，不会阻塞转录和笔记生成。关键帧图片属于任务产物，跟随 `FLUENTFLOW_ARTIFACT_RETENTION_DAYS` 清理；如果未来写入 OSS，笔记和 Agent 任务包里只能暴露 OSS/下载 URL，不能暴露服务器本地路径。

ElevenLabs 只负责语音转文字，不会读取视频画面。笔记自动插图需要 `DASHSCOPE_API_KEY` 供 Qwen 视觉模型做局部视觉选图；主摘要服务商可以继续使用 DeepSeek、OpenAI 或 Qwen。`QWEN_API_KEY` 仍作为旧环境变量兼容。只配置 DeepSeek/OpenAI 但没有百炼 / DashScope Key 时，普通文字笔记仍可生成，但视频关键截图不会自动进入笔记。

如果暂时不想启用账号系统，也可以不配置 `FLUENTFLOW_AUTH_MODE`，让用户直接打开产品；此时后端仍会按设备、IP 和全站总量拦截异常提交，但任务历史无法跨设备找回。封闭 Beta 才需要额外设置 `FLUENTFLOW_ACCESS_TOKEN`。

任务完成后，服务器会删除原始视频/上传源文件，只保留字幕、笔记和用于字幕校对的压缩 MP3。每个用户默认只保留最近 20 条历史，且历史产物最多保留 30 天；超过限制的旧任务会连同音频和产物一起清理。

## 4. 备份与恢复

上线前先保证数据能恢复。默认备份不包含 `/etc/fluentflow/fluentflow.env`，避免把 ElevenLabs、DeepSeek 等密钥写进备份包。

```bash
cd /opt/fluentflow
./venv/bin/python scripts/backup_server_state.py --env-file /etc/fluentflow/fluentflow.env
```

恢复前先 dry-run 看会覆盖哪些路径：

```bash
./venv/bin/python scripts/restore_server_state.py /var/backups/fluentflow/fluentflow-backup-YYYYMMDDTHHMMSSZ.tar.gz --env-file /etc/fluentflow/fluentflow.env
```

确认后再执行：

```bash
systemctl stop fluentflow
./venv/bin/python scripts/restore_server_state.py /var/backups/fluentflow/fluentflow-backup-YYYYMMDDTHHMMSSZ.tar.gz --env-file /etc/fluentflow/fluentflow.env --apply
systemctl start fluentflow
```

建议加一个每天凌晨的 cron：

```bash
0 3 * * * cd /opt/fluentflow && /opt/fluentflow/venv/bin/python scripts/backup_server_state.py --env-file /etc/fluentflow/fluentflow.env >/var/log/fluentflow-backup.log 2>&1
```

## 5. 部署前自检

```bash
set -a
. /etc/fluentflow/fluentflow.env
set +a
./venv/bin/python scripts/check_deployment_readiness.py
```

所有 `FAIL` 都需要先处理。飞书导出如果暂时不开放，可以接受 `lark_export` 的 `WARN`。

如果本次上线目标包括“笔记自动带视频关键截图”，使用更严格的检查：

```bash
./venv/bin/python scripts/check_deployment_readiness.py --require-visual-evidence
```

再跑一次不依赖外部 API 的截图链路烟测，确认服务器上的 FFmpeg 能抽帧，且图片能进入 visual evidence 结果结构：

```bash
./venv/bin/python scripts/smoke_visual_evidence.py --output-dir /tmp/fluentflow-visual-smoke
```

## 6. systemd

```bash
sudo cp deploy/fluentflow.service.example /etc/systemd/system/fluentflow.service
sudo systemctl daemon-reload
sudo systemctl enable --now fluentflow
sudo systemctl status fluentflow
```

## 7. Nginx

```bash
sudo cp deploy/nginx.fluentflow.conf.example /etc/nginx/sites-available/fluentflow
sudo ln -s /etc/nginx/sites-available/fluentflow /etc/nginx/sites-enabled/fluentflow
sudo nginx -t
sudo systemctl reload nginx
```

`client_max_body_size` 要不小于 `FLUENTFLOW_MAX_UPLOAD_MB`。SSE 进度依赖 `proxy_buffering off`，不要删。

## 8. 日常部署与回滚

首次部署完成后，后续更新优先使用脚本，而不是手动复制命令。脚本会先备份数据，再拉取 `main`、安装依赖、构建前端、跑就绪检查、重启服务和检查 `/health`；如果健康检查失败，会回滚到部署前的 Git 版本。
脚本还会在健康检查通过后写入 `/var/lib/fluentflow/releases/` 下的 release manifest，用来追踪当前线上版本、Git commit、前端资源、数据备份包和 schema 版本。

```bash
cd /opt/fluentflow
bash deploy/deploy_server.sh
```

如果服务器上项目目录不是 `/opt/fluentflow`，用环境变量覆盖：

```bash
FLUENTFLOW_PROJECT_DIR=/path/to/fluentflow bash deploy/deploy_server.sh
```

查看最近上线记录：

```bash
ls -lt /var/lib/fluentflow/releases | head
cat /var/lib/fluentflow/releases/fluentflow-*.json | tail -n 80
```

## 9. 监控与告警

基础存活检查：

```bash
curl -fsS http://127.0.0.1:8000/health
```

运维状态接口 `/ops/status` 会返回队列、任务、磁盘、配置状态。它受账号/访问控制保护，外部监控如果没有 session token，可以先只检查 `/health`：

```bash
./venv/bin/python scripts/monitor_health.py --base-url http://127.0.0.1:8000 --skip-ops
```

在服务器本机排查时可以直接看日志：

```bash
journalctl -u fluentflow -n 100 --no-pager
journalctl -u nginx -n 100 --no-pager
```

## 10. 上线 smoke test

1. 打开站点，输入访问口令。
2. 上传一个 1-3 分钟的小视频，确认能生成转录和笔记。
3. 上传一个更接近真实体量的视频，确认 ElevenLabs 云端转录能完成。
4. 如果开启飞书导出，确认任务页能显示飞书文档入口。
5. 跑一次清理脚本 dry-run：

```bash
./venv/bin/python scripts/cleanup_storage.py
```
