# FluentFlow 封闭 Beta 上线检查清单

FluentFlow 当前适合先做小范围封闭 Beta，不适合直接开放匿名公网上传。上线目标是验证真实用户是否愿意用它处理长音视频笔记，而不是先做完整 SaaS。

## 已落地的 P0 边界

### 访问口令

设置环境变量后启用：

```bash
export FLUENTFLOW_ACCESS_TOKEN="your-beta-code"
```

也可以配置多个访问码：

```bash
export FLUENTFLOW_ACCESS_TOKENS="code-a,code-b,code-c"
```

未设置时保持本地开发模式，不要求访问码。

访问码只是封闭 Beta 的低成本门禁，不等同于完整账号系统。它不能区分每个用户的任务、额度和历史记录。

### 设备级历史隔离

前端会在浏览器 `localStorage` 中生成一个 `fluentflow_client_id`，之后所有 API 请求都会带上该 ID。后端 `jobs` 表会保存 `client_id`，并且任务列表、任务详情、源文件下载、产物下载、转录稿编辑和取消任务都会按当前 `client_id` 过滤。

这能保证封闭 Beta 中不同设备、不同浏览器默认看不到彼此的历史任务。但它仍然不是正式账号系统：用户清空浏览器数据或换浏览器后会变成新的设备身份，无法自动找回旧任务。

### 上传与任务限制

可通过环境变量调整：

```bash
export FLUENTFLOW_MAX_UPLOAD_MB=2048
export FLUENTFLOW_MAX_QUEUE_FILES=5
export FLUENTFLOW_MAX_ACTIVE_JOBS_PER_CLIENT=2
export FLUENTFLOW_MAX_MEDIA_DURATION_SECONDS=14400
```

默认口径：

- 单文件最大 2048 MB
- 单次批量最多 5 个文件
- 每个设备最多 2 个排队/运行中的任务
- 单个媒体最长 4 小时

`FLUENTFLOW_MAX_MEDIA_DURATION_SECONDS=0` 可关闭时长限制。

### 云服务器用户模式

上线给外部试用者使用时，普通用户不应该看到本地 faster-whisper、Azure Key、Blob/SAS、pyannote token、DeepSeek/OpenAI Key、飞书 App Secret 等维护者配置。

推荐云服务器最小配置：

```bash
export FLUENTFLOW_PUBLIC_MODE=1
export FLUENTFLOW_ALLOWED_STT_PROVIDERS=azure_batch
export FLUENTFLOW_DEFAULT_STT_PROVIDER=azure_batch
export FLUENTFLOW_ACCESS_TOKEN="your-beta-code"
export FLUENTFLOW_MAX_ACTIVE_JOBS_PER_CLIENT=2
```

效果：

- 后端会把客户端传来的 `local` 转录路线强制改为 `azure_batch`。
- 前端处理设置页只显示云端转录，不再让普通用户选择本地转录。
- API Key、飞书 App 凭证、pyannote token 等维护者字段会隐藏为“后台统一配置”。
- `/runtime-config` 只暴露运行模式、允许的转录路线和限制，不暴露任何密钥。

本地开发时不要开启 `FLUENTFLOW_PUBLIC_MODE`，仍可显式设置：

```bash
export FLUENTFLOW_ALLOWED_STT_PROVIDERS=local,azure_batch
```

### 本地文件清理

先 dry-run 查看将清理哪些文件：

```bash
python3 scripts/cleanup_storage.py
```

确认后执行：

```bash
python3 scripts/cleanup_storage.py --apply
```

默认保留策略：

- `data/sources`：1 天
- `data/artifacts`：30 天
- `data/edited_transcripts`：90 天
- `data/transcript_edit_records`：90 天
- `视频文件`：7 天

可用环境变量或命令参数调整保留天数。

### 失败信息与产物入口

封闭 Beta 的用户不应该看到 Azure 原始错误码作为主要提示。当前后端会把常见 `InvalidModel`、`InvalidLocale`、`InvalidSubscription`、上传中断、文件过大、链接无法解析、队列调用失败等错误转换为中文失败原因；原始错误保留在 job metadata 中供维护者排障。

后台任务页是长任务的主入口，需要确认：

- 运行中任务能显示当前阶段和阶段详情。
- 链接下载能显示解析、下载和保存状态。
- 失败任务能看到可理解的失败原因。
- 完成任务能直接打开编辑器，并下载 SRT/TXT/VTT/Markdown。
- 自动导出成功时能看到飞书文档入口。

## 推荐阿里云部署形态

第一版用单机部署即可：

- ECS 跑 FastAPI、前端静态文件、FFmpeg
- Nginx 做 HTTPS、反向代理和请求体大小限制
- Azure Batch 作为默认云转录路线
- SQLite 继续用于小规模任务历史和事件日志
- OSS 暂缓，等 Beta 用户和文件量上来再迁移

如果 ECS 在中国大陆并绑定域名，需要先完成 ICP 备案。未备案前可以先用服务器 IP 或临时测试域名做内部验证。

项目内已经提供可复制的部署模板：

- `deploy/fluentflow.env.example`：公共模式环境变量模板，不包含真实密钥。
- `deploy/fluentflow.service.example`：systemd 服务模板。
- `deploy/nginx.fluentflow.conf.example`：Nginx 反向代理模板，包含大文件上传和 SSE 所需配置。
- `deploy/README.md`：从服务器依赖、环境变量、自检到 smoke test 的操作顺序。

上线前先运行：

```bash
set -a
. /etc/fluentflow/fluentflow.env
set +a
./venv/bin/python scripts/check_deployment_readiness.py
```

所有 `FAIL` 都要先处理。`lark_export` 如果暂时不开放自动导出，可以接受 `WARN`；如果上线承诺飞书导出，则使用：

```bash
./venv/bin/python scripts/check_deployment_readiness.py --require-lark
```

## Nginx 需要额外配置

后端限制不能替代 Nginx 限制。Nginx 仍应配置：

```nginx
client_max_body_size 2048m;
proxy_read_timeout 86400s;
proxy_send_timeout 86400s;
proxy_request_buffering off;
proxy_buffering off;
```

`proxy_buffering off` 对 SSE 进度流很关键；删掉后，前端可能长时间看不到阶段更新。如果启用 HTTPS，建议强制 HTTP 跳转 HTTPS。

## 当前仍未完成的多人能力

这些不要在产品介绍里过度承诺：

- 没有正式用户账号
- 没有按用户隔离任务历史
- 没有按用户统计额度和成本
- 没有多人权限管理
- 没有支付或套餐
- 没有完整隐私协议和服务条款

封闭 Beta 阶段可以接受这些限制，但公开推广前至少需要补齐账号、用户级任务隔离、额度与隐私说明。

## Beta 测试建议

先邀请 3-5 个真实试用者，每人处理 2-3 个真实材料。

必须记录：

- 是否能独立完成上传、转录、生成笔记、导出
- 单个任务是否成功完成
- 失败发生在哪个阶段
- 笔记是否需要大量修改
- 是否愿意继续使用
- 是否愿意把它推荐给同类用户

这些数据比继续堆功能更能支撑简历中的产品验证能力。
