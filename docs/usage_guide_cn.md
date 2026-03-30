# FluentFlow 使用说明书（小白版）

FluentFlow 是一套“本地转录 + AI 生成结构化笔记 + 可选飞书导出”的软件。
它的特点是：**音频/转录过程尽量在本机完成**，生成摘要与导出会调用外部 API。

本文档面向第一次使用的用户，从“安装准备 → 配置 → 使用步骤 → 导出 → 常见问题”完整讲清楚。

---

## 1. 你需要准备什么

### 1.1 系统依赖：`ffmpeg`（必须）
软件会用 `ffmpeg` 把视频/音频转换成低码率 MP3，再进行转录。

macOS 推荐安装方式：

```bash
brew install ffmpeg
```

安装成功后建议验证：

```bash
ffmpeg -version
```

### 1.2 Python 环境
建议使用 Python 3.10+（项目本身以 venv 形式运行）。

---

## 2. 第一次安装（本地配置）

进入项目根目录：`fluentflow/`

### 2.1 创建虚拟环境并安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> 如果你用的是系统自带 Python，记得激活 `.venv` 后再运行后续命令。

### 2.2 配置 DeepSeek API Key（两种方式二选一）

FluentFlow 允许你把 DeepSeek 的 Key 放在：
1) 后端 `.env`（后端会自动读取）
2) 前端“设置”页面（更推荐，避免反复改文件）

#### 方式 A：写入 `.env`
在项目根目录创建/编辑 `.env`：

```env
DEEPSEEK_API_KEY=你的key
```

#### 方式 B：在前端设置里填
打开前端后，进入 `Settings & Export` 页面填写：
- `API Key`（DeepSeek Key）

填写完会保存在浏览器 `localStorage` 中（不需要每次重填）。

---

## 3. 飞书（Lark/Feishu）导出前的准备

如果你希望把摘要导出到飞书，需要准备一个飞书开放平台应用，并让它具备创建文档的权限。

### 3.1 必须申请的权限范围（Scopes）
在飞书开放平台的应用权限里，至少需要包含：
- `docx:document`
- `docx:document:create`

> 权限不对时会出现“Access denied / no folder permission / 创建失败”等错误。

### 3.2 填写飞书 App 配置
在前端 `Settings & Export` 页面填写：
- `App ID`
- `App Secret`

也可以打开开关：
- `Auto-export to Lark after processing`（自动导出）

---

## 4. 启动软件并使用（端到端操作步骤）

你有两种启动方式：

### 4.1 推荐方式：使用桌面快捷方式
双击桌面快捷方式后，浏览器会自动打开应用页面（端口 `5185`）。

### 4.2 手动方式（如果你不使用桌面快捷方式）
在终端启动后端服务（端口 `8000`）：

```bash
python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

然后在浏览器访问前端页面（通常快捷方式已经帮你做完了）。

---

## 5. 在“仪表盘 Dashboard”里处理文件

进入后你会看到一个大卡片区域：

### 5.1 上传文件
你可以：
- 拖拽文件到页面
- 或点击选择文件

支持视频/音频（常见格式）：
- 视频：MP4 / MOV / AVI / MKV / WEBM / ……
- 音频：MP3 / WAV / FLAC / AAC / OGG / M4A / WMA / OPUS / ……

### 5.2 进度与取消
页面右下/底部会显示实时进度。
如果你不想等，可以点击 `Cancel` 取消当前任务。

> 说明：转录（STT）是 CPU 密集型过程，进度条会在该阶段逐步变化。

### 5.3 处理完成后的下一步
当处理完成后：
- 点击 `View in Editor` 进入编辑器

---

## 6. 在“编辑器 Editor”里查看、重新生成与导出

编辑器分为左右两个区域：
- 左：完整转录（segments 带时间）
- 右：AI 摘要（结构化 Markdown，方便复制到飞书）

### 6.1 选择“提示词模板”（让摘要产出不同风格）
在编辑器顶部有一个按钮可以展开“提示词模板”：
- `课程笔记（默认）`
- `会议纪要`
- `研究/论文摘要`
- `快速要点提炼`
- `自定义提示词`

选择后点击 `Regenerate / 重新生成`，摘要会按新风格输出。

### 6.2 导出到飞书（Lark/Feishu）
点击顶部按钮 `Export to Lark`：
- 若你开启了 `Auto-export`，则上传完成后会自动导出
- 导出完成后会显示飞书文档链接
- 同时会把链接记录到“Export History”（导出历史）

---

## 7. 转录文本/AI 摘要的本地下载（TXT / SRT / VTT / PDF / Word）

### 7.1 导出“转录文本 Transcript”
在左侧“导出转录文本”下拉里选择：
- `TXT`：纯文本
- `SRT`：字幕（含时间戳）
- `VTT`：WebVTT 字幕（含时间戳）

注意：SRT/VTT 需要 segments 数据（通常是正常转录结果后就有）。

### 7.2 下载“AI 摘要 Summary”
在右侧“下载摘要”下拉里选择：
- `TXT`：把摘要 Markdown 转为纯文本下载
- `PDF`：把当前摘要渲染成 PDF（A4）
- `Word (DOC)`：生成 Word 可打开的文档

---

## 8. 常见问题（Troubleshooting）

### 8.1 上传后卡在某个阶段不动 / 很热
转录和摘要属于重计算任务，尤其在较低配置机器上会比较慢。
建议：
1. 先等待 STT 段落进度变化（它会在 22 到 60 之间持续推进）
2. 若你不需要，点击 `Cancel` 终止

### 8.2 报错：连接被拒绝 / 无法访问某些网站
如果你使用 VPN，可能存在 DNS/代理劫持问题。
建议：
- 关闭 VPN 后重试（或者尝试更换网络）

### 8.3 飞书导出失败（Access denied / 权限不足）
通常是飞书应用权限范围缺失。
请确认你已经添加并授权：
- `docx:document`
- `docx:document:create`

### 8.4 找不到飞书文档
由于文档是通过飞书 API 创建并设置“组织级链接可编辑/可访问”策略，你通常可以直接用导出的 URL 打开。
并且该链接会出现在“Export History”里。

---

## 9. 隐私与本地优先说明

- 音频/转录处理尽量在本机完成
- 你上传的原始文件会在处理结束后临时清理
- 生成摘要会调用外部 LLM API（需要你的 DeepSeek Key 或前端填写的 Key）
- 飞书导出会调用飞书开放平台 API（需要 App ID/Secret）

---

## 10. 你接下来可以做什么

如果你愿意，我可以把这份说明文档进一步“贴合你的桌面快捷方式使用方式”，例如：
- 你的快捷方式实际启动命令是什么
- 需要打开哪个窗口/授权什么权限（macOS TCC）
- 常见“导出失败”你遇到的具体错误码对应的解决步骤

