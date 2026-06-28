# FluentFlow Accent Color Design Rules

## Principle

FluentFlow 整体是黑白单色系统（snapvee 弥散风格）。accent color 仅在传达**语义信号**时出现——不用颜色做纯装饰。日常浏览时页面几乎看不到颜色，只有当状态变化（成功/失败/警告）或关键交互需要引导时，颜色才进入视线。

参考：snapvee.com 的色彩克制程度。

## Semantic Color Assignment

| Semantic | Color | Tailwind Classes (light) | Tailwind Classes (dark) | Usage |
|----------|-------|--------------------------|-------------------------|-------|
| **Success / Complete** | Green / Emerald | `text-green-700 bg-green-50 border-green-200` | `dark:text-emerald-300 dark:bg-emerald-400/10 dark:border-emerald-400/30` | 任务完成、处理成功、正数增量、导出成功 |
| **Highlight / Active / Brand** | Purple / Violet | `text-purple-700 bg-purple-50 border-purple-200/50` | `dark:text-purple-300 dark:bg-purple-400/10 dark:border-purple-400/30` | 选中态、保存/确认按钮、AI 功能标识、focus ring |
| **Warning / Info** | Amber | `text-amber-700 bg-amber-50 border-amber-400/25` | `dark:text-amber-300 dark:bg-amber-500/10 dark:border-amber-400/25` | 警告信息、Beta 标签、需要注意但不阻塞的提示 |
| **Error / Destructive** | Red | `text-red-600 bg-red-50 border-red-200` | `dark:text-red-300 dark:bg-red-400/10 dark:border-red-400/30` | 错误、删除、取消、失败状态 |
| **Media Playback** | Blue | `text-blue-700 bg-blue-50` | `dark:text-blue-300 dark:bg-blue-400/10` | 仅播放器进度条和时间轴相关（不与 purple 冲突） |

## Color Roles by Purpose

### Purple — Interactive Highlight（替代 Amber）

Purple 是唯一代表"系统主动性"的颜色——AI 操作、选中态、确认提交。不应大面积使用，仅在关键 CTA 和小面积指示器出现。

- **Filled CTA button**: `bg-purple-600 text-white hover:bg-purple-700`
- **Selected chip / active preset**: `bg-purple-600 text-white border-purple-600`
- **AI feature icon**: `text-purple-600` on `bg-purple-50`
- **Focus ring**: `focus:ring-purple-300/50 focus:border-purple-300`
- **Blockquote accent bar**: `border-purple-400/40 bg-purple-50`

### Green — Success Feedback Only

Green 只在"事情做完了"时出现——任务完成通知、导出成功、确认结果。不要用于普通按钮或非成功相关的交互。

- **Success alert**: `border-emerald-200 bg-emerald-50 text-emerald-800`
- **Processing completed badge**: emerald border/background
- **Positive delta (admin)**: `text-green-700`

### Amber — Warning Only

Amber 回归其警告语义——只是提醒注意，不阻塞操作。不要用 amber 做选中态或主按钮。

- **Warning banner**: `border-amber-400/25 bg-amber-50 text-amber-700`
- **Beta/experimental label**: `text-amber-600 bg-amber-50`
- **Info note**: amber icon on neutral background

### Red — Error / Destructive

保持现有语义不变。

### Blue — Media Playback Only

仅用于播放器时间轴——与 purple 区分，避免两个交互色竞争。不要在非播放器场景使用 blue。

## Migration from Current State

Current problem: Amber is overloaded as both "warning" AND "interactive highlight" (PromptTemplateDialog active chips, save-as-preset buttons, all focus rings). This dilutes amber's warning meaning and leaves no distinct color for the system's active/highlight signal.

### Changes to apply:

1. **PromptTemplateDialog**: active preset chips + save button → purple (not amber)
2. **settings.jsx**: save-as-preset button, prompt icon container → purple
3. **markdown.js**: blockquote accent bar → purple (not tertiary with purple bg)
4. **existing purple uses** (editor download button): keep as purple
5. **Amber uses to KEEP**: warning banners, beta labels, info notes, processing warnings

## Adding New Pages

When adding color to a new page:
1. Does it convey a semantic signal (success/error/warning/active-highlight)?
2. Could a monochrome alternative (bold text, border change, elevation shift) work instead?
3. Use the color table above — don't invent new color roles
4. Always include `dark:` variants for both foreground and background

## Visual Check

With a correctly applied palette, a fully loaded idle page (no warnings, no active jobs) should show almost no color — only the sidebar active nav item (subtle primary highlight) and any purple accent on AI-feature or CTA buttons. Green, amber, red should be absent unless something happened.
