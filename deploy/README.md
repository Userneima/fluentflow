# FluentFlow 云服务器部署模板

这套模板用于封闭 Beta，不是正式 SaaS 多租户部署。

## 1. 服务器依赖

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip ffmpeg nginx git
```

## 2. 部署目录

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin fluentflow
sudo mkdir -p /opt/fluentflow /etc/fluentflow /var/lib/fluentflow
sudo chown -R fluentflow:fluentflow /opt/fluentflow /var/lib/fluentflow
```

把项目放到 `/opt/fluentflow` 后：

```bash
cd /opt/fluentflow
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
npm ci
npm run build:frontend
```

## 3. 环境变量

```bash
sudo cp deploy/fluentflow.env.example /etc/fluentflow/fluentflow.env
sudo chmod 600 /etc/fluentflow/fluentflow.env
sudo chown fluentflow:fluentflow /etc/fluentflow/fluentflow.env
sudo nano /etc/fluentflow/fluentflow.env
```

必须替换：

- `FLUENTFLOW_ACCESS_TOKEN`
- `AZURE_SPEECH_ENDPOINT`
- `AZURE_SPEECH_KEY`
- `AZURE_BLOB_CONTAINER_SAS_URL`
- `DEEPSEEK_API_KEY` 或 `OPENAI_API_KEY`
- 如果需要飞书导出，再配置 `LARK_APP_ID` / `LARK_APP_SECRET`

## 4. 部署前自检

```bash
set -a
. /etc/fluentflow/fluentflow.env
set +a
./venv/bin/python scripts/check_deployment_readiness.py
```

所有 `FAIL` 都需要先处理。飞书导出如果暂时不开放，可以接受 `lark_export` 的 `WARN`。

## 5. systemd

```bash
sudo cp deploy/fluentflow.service.example /etc/systemd/system/fluentflow.service
sudo systemctl daemon-reload
sudo systemctl enable --now fluentflow
sudo systemctl status fluentflow
```

## 6. Nginx

```bash
sudo cp deploy/nginx.fluentflow.conf.example /etc/nginx/sites-available/fluentflow
sudo ln -s /etc/nginx/sites-available/fluentflow /etc/nginx/sites-enabled/fluentflow
sudo nginx -t
sudo systemctl reload nginx
```

`client_max_body_size` 要不小于 `FLUENTFLOW_MAX_UPLOAD_MB`。SSE 进度依赖 `proxy_buffering off`，不要删。

## 7. 上线 smoke test

1. 打开站点，输入访问口令。
2. 上传一个 1-3 分钟的小视频，确认能生成转录和笔记。
3. 上传一个更接近真实体量的视频，确认 Azure Batch 能完成。
4. 如果开启飞书导出，确认任务页能显示飞书文档入口。
5. 跑一次清理脚本 dry-run：

```bash
./venv/bin/python scripts/cleanup_storage.py
```
