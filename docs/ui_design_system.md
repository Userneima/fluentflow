# FluentFlow UI / Dark Mode Design System

本文档把 FluentFlow 的页面设计方法固定下来，尤其用于暗黑模式、工作台、编辑器、设置页、后台任务和管理页。目标不是做一套炫技视觉，而是让长期维护时每个页面都能保持清晰、稳定、可读、可扩展。

## Product Read

FluentFlow 是一个长任务工具产品。用户目标是上传音视频、等待后台转录、编辑字幕、生成笔记、查看历史和管理账号额度。

默认设计判断：

- 页面类型：工具型产品，不是营销落地页。
- 视觉目标：安静、可信、信息密度适中，支持反复使用。
- 交互目标：核心动作明确，后台状态可追踪，错误可理解。
- 暗黑模式目标：降低视觉疲劳，但不能牺牲可读性和操作识别。

设计参数：

- `DESIGN_VARIANCE: 4`
- `MOTION_INTENSITY: 2`
- `VISUAL_DENSITY: 7`

含义：布局可以有轻微层次，但不做大幅艺术化；动效只服务状态反馈；信息密度要高于普通官网，但不能变成拥挤后台。

## Typography Constraints

先定字体层级，再做页面。

### 允许 display-scale 的位置

- 开始处理页的主标题。
- 空状态的核心行动提示。
- 少量产品介绍或演示入口。

### 必须使用 operational-scale 的位置

- 编辑器标题、字幕列表、摘要面板、任务列表、设置页、账号面板、管理页。
- 表单标签、输入框、按钮、卡片标题、表格行、状态徽标。

### 默认字号上限

| 场景 | 推荐上限 |
| --- | --- |
| 工具页主标题 | `text-3xl` 到 `text-4xl` |
| 面板标题 | `text-lg` 到 `text-2xl` |
| 卡片标题 | `text-base` 到 `text-xl` |
| 表单标签 | `text-xs` 到 `text-sm` |
| 按钮文字 | `text-sm` 到 `text-base` |
| 表格、任务列表、元信息 | `text-xs` 到 `text-sm` |
| 字幕正文 | `text-base` 到 `text-lg`，按阅读距离调整 |

不要用 viewport width 驱动工具页文字大小。需要 `clamp()` 时必须有明确上限，避免宽屏下控件和面板标题膨胀成海报字。

## Theme Model

FluentFlow 使用 Tailwind `darkMode: "class"`，并通过 CSS 变量提供语义色。语义 token 是主题的事实来源。

优先使用这些类：

- 背景：`bg-surface`、`bg-surface-dim`、`bg-surface-container-lowest`、`bg-surface-container-low`、`bg-surface-container`、`bg-surface-container-high`
- 文本：`text-on-surface`、`text-on-surface-variant`、`text-on-background`
- 边框：`border-outline`、`border-outline-variant`、`ff-border-muted`、`ff-border-control`
- 重点动作：`bg-primary text-on-primary` 或 `text-primary`
- AI 摘要或次级智能动作：`tertiary` 系列，但要克制使用

不要新增长期存在的原始颜色工具类作为主界面表面，例如：

- `bg-white`
- `bg-black`
- `bg-slate-*`
- `bg-gray-*`
- `text-gray-*`
- `text-slate-*`
- `bg-blue-50`

如果只是局部迁移期间保留旧类，可以接受，但改到相关区域时应该顺手替换为语义 token。

## Surface Stack

暗黑模式的层次靠表面和边框，不靠强阴影、发光和大面积渐变。

| 层级 | 用途 | 推荐类 |
| --- | --- | --- |
| Page shell | 页面底层背景 | `bg-surface text-on-surface` |
| Sidebar / app chrome | 侧栏、顶部导航、固定导航 | `bg-surface-container-lowest` |
| Main workspace | 工作台、编辑器主体区域 | `bg-surface-container-low` |
| Panel / section | 转录面板、摘要面板、设置分组 | `bg-surface-container-lowest ff-border-muted` |
| Nested control row | 工具栏、筛选条、输入组 | `bg-surface-container-low ff-border-control` |
| Active / selected | 当前菜单项、选中任务、当前步骤 | `bg-primary/10 text-primary` |
| Popover / modal | 弹窗、菜单、浮层 | `bg-surface-container-lowest ff-border-muted shadow-sm` |

不要把卡片套卡片。页面分区用宽度、间距和分隔线组织；卡片只用于重复条目、弹窗、真正需要边界的工具面板。

## Text Hierarchy

| 信息类型 | 推荐类 |
| --- | --- |
| 主要内容 | `text-on-surface` |
| 次级说明、时间、来源、状态描述 | `text-on-surface-variant` |
| 弱化信息、禁用态 | `text-outline` 配合透明度 |
| 时间戳、额度、数量、耗时 | `tabular-nums`，必要时用 `font-mono` |
| 错误 | `text-error` 或错误容器 token |

不要用低对比度灰色承载关键状态。暗黑模式里“看起来很淡”不等于高级，状态和操作必须能一眼识别。

## Color Rules

- 不用纯黑 `#000000` 作为页面背景。
- 不用纯白 `#ffffff` 作为暗黑模式文字大面积输出。
- 蓝色是主操作色。
- 紫色只用于 AI 摘要、模型生成、智能处理这类语义，不要泛化成全站装饰色。
- 不使用大面积蓝紫渐变、发光边框、霓虹阴影作为默认暗黑风格。
- 状态色必须有语义：成功、警告、错误、进行中、禁用。不要为了“丰富”随意加色。

## Component Rules

### Buttons

- 主按钮：用于提交、上传、保存、开始处理、下载等核心动作。
- 次按钮：用于导入、查看、重试、复制等辅助动作。
- 图标按钮必须有可访问标签或悬浮提示。
- 所有按钮都要有 `hover`、`focus-visible`、`active`、`disabled` 状态。
- 不要让按钮文字换行导致按钮高度跳动。

### Inputs

- 标签在输入框上方，不能只靠 placeholder 当标签。
- 默认使用 `bg-surface-container-low`、`ff-border-control`、`text-on-surface`。
- Focus 使用 `border-primary/60` 或轻量 ring，不要强发光。
- 说明文字只保留必要信息。普通用户不需要理解的维护者说明应隐藏到高级设置、帮助文档或管理员入口。

### Cards

- 卡片半径遵循项目现有 scale：小半径、克制，不做大圆角气泡。
- 卡片只表达真实边界：任务项、历史项、账号信息、弹窗、编辑工具。
- 避免“为了排版好看”给每个 section 套一个大卡片。

### Tables / Admin

- 管理页优先密度和扫描效率。
- 行高稳定，数字对齐，操作列固定宽度。
- 错误和权限状态用明确文本，不只靠颜色。

### Editor / Transcript

- 文件名、任务名、字幕标题必须允许截断，并通过 `title` 或 tooltip 暴露全名。
- 长标题不要撑开操作按钮区。
- 字幕正文优先阅读节奏，时间戳列宽固定，跟随播放不能因为文本换行导致定位混乱。

## Layout Rules

- 固定格式 UI 元素要有稳定尺寸：工具栏、按钮组、时间戳列、状态徽标、历史卡片。
- 侧栏和主内容之间保持清晰分隔，避免大面积同色块混在一起。
- 工作台页面左侧应优先显示当前可行动内容，最近活动不能压过上传和任务入口。
- 设置页按用户目标分组，不按技术服务供应商暴露复杂性。
- 移动端如果支持，需要明确单列折叠，不依赖“自然挤压”。

## Dark Mode Checklist

每次改 UI 前后检查：

- 浅色和暗黑模式都可读。
- 表面层级清楚，不靠纯黑背景和强阴影。
- 主要动作在暗黑模式中仍然突出。
- 输入框边界、禁用态、错误态能看出来。
- 长标题、长邮箱、长文件名不会挤压布局。
- Hover、focus、active、disabled 状态齐全。
- 没有新增大面积原始颜色类。
- 没有把说明性小字堆到普通用户主流程。

## Anti-Patterns

以下模式默认不要引入：

- 工具页里使用巨型海报标题。
- 暗黑模式用大片纯黑和荧光蓝紫表现“科技感”。
- 大面积渐变、发光、装饰性纹理。
- 卡片嵌套卡片。
- 每个 section 都做成浮动卡片。
- 用解释性文案替代清晰控件。
- 输入框只靠 placeholder 传达含义。
- 同一页面多套圆角、阴影、边框风格混用。
- 为了视觉丰富混用蓝、紫、绿、橙等多个强调色。
- 标题换行超过两行并挤占主要操作区。

## Validation

文档约束之外，实际改动后仍需验证：

- 前端代码变更后运行 `npm run build:frontend`。
- 如果涉及核心页面视觉变化，启动本地服务并检查至少一个桌面视口截图。
- 涉及暗黑模式时，要在浅色和暗黑模式各检查一次。
- 涉及长文本显示时，用长文件名、长邮箱、长任务名测试。

本规范不是替代判断的模板。它的作用是防止 FluentFlow 在长期迭代中出现主题漂移、暗黑模式失控、工具页文字过大和控件风格不统一。
