# FluentFlow 云服务器部署模板

这套模板用于封闭 Beta，不是正式 SaaS 多租户部署。

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
```

## 3. 环境变量

```bash
sudo cp deploy/fluentflow.env.example /etc/fluentflow/fluentflow.env
sudo chmod 600 /etc/fluentflow/fluentflow.env
sudo chown fluentflow:fluentflow /etc/fluentflow/fluentflow.env
sudo nano /etc/fluentflow/fluentflow.env
```

必须替换：

- `AZURE_SPEECH_ENDPOINT`
- `AZURE_SPEECH_KEY`
- `AZURE_BLOB_CONTAINER_SAS_URL`
- `DEEPSEEK_API_KEY` 或 `OPENAI_API_KEY`
- 如果需要飞书导出，再配置 `LARK_APP_ID` / `LARK_APP_SECRET`

`FLUENTFLOW_ACCESS_TOKEN` 是封闭 Beta 访问码。若不想设置访问码，可以注释这一行，但必须保留这些异常额度控制：

```bash
FLUENTFLOW_MAX_ACTIVE_JOBS_PER_CLIENT=2
FLUENTFLOW_DAILY_JOB_LIMIT_PER_CLIENT=10
FLUENTFLOW_DAILY_UPLOAD_MB_PER_CLIENT=4096
```

这种方式能限制单设备误用成本，但不能替代正式账号系统。用户清浏览器数据或换设备后会变成新的设备身份。

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
