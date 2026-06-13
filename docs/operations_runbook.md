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
curl -fsS http://127.0.0.1/health
```

更完整的状态：

```bash
cd /opt/fluentflow
./venv/bin/python scripts/monitor_health.py --base-url http://127.0.0.1 --skip-ops
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
curl -fsS http://127.0.0.1/health
journalctl -u fluentflow -n 200 --no-pager
systemctl restart fluentflow
```

## 磁盘空间

```bash
df -h
du -sh /var/lib/fluentflow/*
```

任务完成后会删除原始视频，只保留字幕、笔记和一份用于校对的压缩 MP3。默认每个用户只保留最近 20 条历史，产物最多保留 30 天。
