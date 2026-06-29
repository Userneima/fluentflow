# FluentFlow 运维手册

这份文档面向单台云服务器 Beta 运行，不是正式 SaaS 运维体系。

## 常用路径

- 项目代码：`/opt/fluentflow`
- 环境变量：`/etc/fluentflow/fluentflow.env`
- 账号数据库：`/var/lib/fluentflow/fluentflow_accounts.sqlite`
- 任务数据库：`/var/lib/fluentflow/fluentflow_jobs.sqlite`
- 上传源文件：`/var/lib/fluentflow/sources`
- 结果产物：`/var/lib/fluentflow/artifacts`
- 视频链接下载缓存：`/var/lib/fluentflow/video-sources`
- 数据备份：`/var/backups/fluentflow`

## 日常检查

```bash
systemctl status fluentflow --no-pager
systemctl status nginx --no-pager
curl -fsS http://127.0.0.1:8000/health
```

更完整的状态：

```bash
cd /opt/fluentflow
./venv/bin/python scripts/monitor_health.py --base-url http://127.0.0.1:8000 --skip-ops
```

如果要看受保护的 `/ops/status`，需要账号 session token；没有 token 时先用 `/health` 判断服务是否活着。

## 查看日志

```bash
journalctl -u fluentflow -n 100 --no-pager
journalctl -u nginx -n 100 --no-pager
```

## 部署新版本

```bash
cd /opt/fluentflow
bash deploy/deploy_server.sh
```

脚本会先备份，再拉取代码、安装依赖、构建前端、跑部署自检、重启服务和检查 `/health`。如果检查失败，会回滚到部署前的 Git 版本。

## 手动备份

默认不备份 `/etc/fluentflow/fluentflow.env`，避免密钥进入备份包。

```bash
cd /opt/fluentflow
./venv/bin/python scripts/backup_server_state.py --env-file /etc/fluentflow/fluentflow.env
```

## 恢复数据

先 dry-run：

```bash
cd /opt/fluentflow
./venv/bin/python scripts/restore_server_state.py /var/backups/fluentflow/fluentflow-backup-YYYYMMDDTHHMMSSZ.tar.gz --env-file /etc/fluentflow/fluentflow.env
```

确认路径无误后再恢复：

```bash
systemctl stop fluentflow
cd /opt/fluentflow
./venv/bin/python scripts/restore_server_state.py /var/backups/fluentflow/fluentflow-backup-YYYYMMDDTHHMMSSZ.tar.gz --env-file /etc/fluentflow/fluentflow.env --apply
systemctl start fluentflow
```

## 任务卡住

服务重启后，仍有源文件的 queued/running 任务会自动重新入队；源文件已经丢失的任务会标记失败。

如果任务持续不更新：

```bash
curl -fsS http://127.0.0.1:8000/health
journalctl -u fluentflow -n 200 --no-pager
systemctl restart fluentflow
```

## 磁盘空间

```bash
df -h
du -sh /var/lib/fluentflow/*
```

任务完成后会删除原始视频，只保留字幕、笔记和一份用于校对的压缩 MP3。默认每个用户只保留最近 20 条历史，产物最多保留 30 天。

## 视频截图 / 关键帧

FluentFlow 的截图能力分成本地和云端 provider：

- `FLUENTFLOW_KEYFRAME_PROVIDER=local_ffmpeg`：在当前后端机器上用 FFmpeg 抽帧，适合单台阿里云 ECS 或 Docker 部署。
- `FLUENTFLOW_KEYFRAME_PROVIDER=cloud_ffmpeg_worker`：预留给独立 Worker；Worker 需要能读取源视频，生成图片，并把图片写回 OSS 或产物目录。未配置 `FLUENTFLOW_KEYFRAME_WORKER_URL` 时会跳过，不影响转录和笔记。
- `FLUENTFLOW_KEYFRAME_EXTRACTION=0`：完全关闭截图抽帧。

自动把截图写入笔记还需要多模态摘要链路。当前后端只把 Qwen 视为可用多模态 provider，因此服务器需要同时配置：

```bash
AI_PROVIDER=qwen
QWEN_API_KEY=...
```

ElevenLabs 只负责转录，不会看视频画面；只配置 DeepSeek / OpenAI 时可以生成文字笔记，但不会自动把视频关键截图插入笔记。

如果使用本机/服务器 FFmpeg，先确认：

```bash
ffmpeg -version
ffprobe -version
du -sh /var/lib/fluentflow/artifacts
```

上线前可用严格自检确认插图链路：

```bash
./venv/bin/python scripts/check_deployment_readiness.py --require-visual-evidence
```

如果严格自检通过，再跑本地 FFmpeg 抽帧烟测：

```bash
./venv/bin/python scripts/smoke_visual_evidence.py --output-dir /tmp/fluentflow-visual-smoke
```

关键帧图片属于任务产物，受 `FLUENTFLOW_ARTIFACT_RETENTION_DAYS` 清理策略影响。公开视频部署时不应把本地文件路径写入笔记或 Agent 任务包，图片应通过 `/jobs/{task_id}/artifacts/frame?file=...` 或后续 OSS URL 访问。

## 飞书图片导出

如果笔记中包含 Agent 选中的关键截图，OpenAPI 飞书导出会尝试把本地 artifact 图片上传为飞书文档图片块，而不是把 `/jobs/{task_id}/artifacts/frame?...` 这种私有下载地址直接写进云文档。

上线前需要确认飞书应用权限同时覆盖：

- 创建和写入 docx 文档。
- 上传文档图片素材。
- 替换 docx 图片块。

如果缺少图片相关权限，文本笔记仍应优先可导出；截图会记录在导出返回的 `image_upload_errors` 中。排障时先看 `/export-lark` 或 `lark_export_completed` 的错误信息，再确认飞书开放平台权限和应用发布状态。
