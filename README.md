# FluentFlow

FluentFlow 是一个面向长视频、课堂录音、讲座录音、会议录音和已有字幕的 AI 笔记工作流工具。

它把“导入材料 -> 转写/整理字幕 -> 生成结构化笔记 -> 下载或导出飞书”集中在一个产品里，减少多工具跳转、复制粘贴、长任务等待不可见和笔记格式整理成本。

当前项目处于封闭 Beta / 自用产品迭代阶段，不是完整 SaaS 多租户模板。

## 核心能力

- 本地音视频上传，支持多文件后台队列。
- SRT、VTT、TXT、MD 字幕或文本导入。
- 抖音分享文本或视频链接解析。
- 本地 `faster-whisper` 或 Azure Batch 云转录。
- FFmpeg 音频预处理。
- 字幕时间码清理、段落重组、重复幻觉清洗。
- DeepSeek / OpenAI 兼容接口生成结构化笔记。
- 转录稿编辑和自动保存。
- 下载 TXT、SRT、VTT、Markdown、PDF、Word 等产物。
- 手动或自动导出到飞书 / Lark。
- SQLite 任务历史、事件日志和账号隔离。

## 技术栈

- Backend: FastAPI + SQLite
- Frontend: React + Vite + Tailwind CSS
- STT: faster-whisper / Azure Batch Transcription
- AI Summary: DeepSeek / OpenAI compatible API
- Export: Feishu OpenAPI / local `lark-cli`
- Runtime media processing: FFmpeg

## 本地运行

### 1. 系统依赖

需要先安装 FFmpeg 和 Node.js 20+。

macOS:

```bash
brew install ffmpeg
```

Ubuntu:

```bash
sudo apt update
sudo apt install -y ffmpeg python3-venv python3-pip
```

### 2. Python 依赖

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

如果需要本地说话人区分，再安装：

```bash
./venv/bin/pip install -r requirements-speaker.txt
```

### 3. 前端依赖与构建

```bash
npm ci
npm run build:frontend
```

构建产物会输出到 `frontend/dist/`。不要手动编辑 `frontend/dist/`。

### 4. 启动后端

```bash
./venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

然后打开：

```text
http://127.0.0.1:8000
```

### 5. 前端开发模式

如果只调前端，可以同时运行：

```bash
./venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
npm run dev:frontend
```

Vite 默认跑在 `127.0.0.1:5185`，前端会把 API 指向本地 `8000` 后端。

## 常用环境变量

只列关键项，完整部署参考 `deploy/fluentflow.env.example`。

```bash
# AI summary
DEEPSEEK_API_KEY=...
OPENAI_API_KEY=...

# Azure Batch transcription
AZURE_SPEECH_ENDPOINT=...
AZURE_SPEECH_KEY=...
AZURE_BLOB_CONTAINER_SAS_URL=...

# Feishu / Lark OpenAPI export
LARK_APP_ID=...
LARK_APP_SECRET=...

# Account mode
FLUENTFLOW_AUTH_MODE=accounts
# Optional. Defaults to ~/Library/Application Support/FluentFlow on macOS.
FLUENTFLOW_DATA_DIR=/path/to/fluentflow-data
```

本机 `lark-cli` 导出可通过应用设置开启；后端进程需要能在 PATH 中调用 `lark-cli`。

## 目录结构

```text
backend/                 FastAPI 后端入口和 API
backend/core/            转录、摘要、飞书、账号、任务存储等核心模块
frontend/src/            React 前端源码
frontend/src/routes/     页面级前端模块
frontend/dist/           Vite 构建产物
scripts/                 备份、恢复、评估、构建辅助脚本
deploy/                  服务器部署模板
docs/                    产品、架构、运维、回归和设计文档
tests/                   后端和关键行为测试
data/                    旧版本地运行数据目录；新默认在系统应用数据目录
```

## 常用命令

```bash
# 构建前端
npm run build:frontend

# 后端语法检查
python3 -m py_compile backend/main.py

# 跑测试
./venv/bin/python -m pytest

# 部署检查
./venv/bin/python scripts/check_deployment_readiness.py
```

## 部署

服务器部署模板在 `deploy/` 下。

推荐流程：

```bash
cd /opt/fluentflow
npm ci
npm run build:frontend
./venv/bin/pip install -r requirements.txt
bash deploy/deploy_server.sh
```

详细步骤见：

- `deploy/README.md`
- `docs/operations_runbook.md`

## 进一步了解

- 产品边界：`docs/product_overview.md`
- 架构说明：`docs/architecture.md`
- UI 设计系统：`docs/ui_design_system.md`
- 回归检查：`docs/regression_checklist.md`
- 更新记录：`docs/changelog.md`

## 注意

- 不要提交密钥、token、SAS URL 或 `.env` 文件。
- 长音视频任务可能消耗较多本地 CPU、磁盘和云端转录额度。
- 公开试用或服务器部署前，应配置账号、额度、上传限制、历史保留和备份策略。
