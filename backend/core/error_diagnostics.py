"""User-facing error diagnostics shared by backend surfaces."""

from __future__ import annotations

from typing import Any


def _text(value: Any) -> str:
    return str(value or "").strip()


def _diag(
    *,
    code: str,
    title: str,
    detail: str,
    next_action: str,
    severity: str = "error",
    retryable: bool = True,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "title": title,
        "detail": detail,
        "next_action": next_action,
        "retryable": retryable,
    }


def diagnose_error(error: Any) -> dict[str, Any]:
    """Convert raw infrastructure/model errors into stable product diagnostics."""

    raw = _text(error)
    if not raw:
        return _diag(
            code="unknown_error",
            title="任务处理失败",
            detail="处理失败，但没有返回具体原因。请重试一次。",
            next_action="重新提交任务；如果连续失败，请把任务详情发给维护者排查。",
        )
    lowered = raw.lower()

    if "云端文件下载失败" in raw:
        return _diag(
            code="oss_source_download_failed",
            title="云端文件下载失败",
            detail="已上传的云端文件暂时无法下载到处理服务。",
            next_action="文件仍保留在云端，可以在处理记录中点击“重新处理”，无需再次上传。",
        )
    if ("wiki:" in lowered or "知识库" in raw) and (
        "99991679" in lowered or "permission" in lowered or "unauthorized" in lowered
    ):
        return _diag(
            code="feishu_wiki_permission_required",
            title="飞书授权缺少知识库权限",
            detail="飞书账号已连接，但当前授权不能写入“我的文档库”。",
            next_action="在飞书开放平台为 FluentFlow 应用启用知识库权限后，重新连接飞书账号并确认授权。",
        )
    if "feishu wiki personal library was not found" in lowered:
        return _diag(
            code="feishu_my_library_unavailable",
            title="未找到飞书我的文档库",
            detail="当前飞书账号没有可写入的“我的文档库”。",
            next_action="先在飞书中创建或启用“我的文档库”，然后重新导出。",
        )
    if "99991679" in lowered or (
        "docx:document" in lowered and "permission" in lowered
    ):
        return _diag(
            code="feishu_document_permission_required",
            title="飞书授权缺少文档权限",
            detail="飞书账号已连接，但当前授权不能创建云文档。",
            next_action="在飞书开放平台为 FluentFlow 应用启用文档创建权限后，重新连接飞书账号并确认授权。",
        )
    if "queued transcript summary request failed" in lowered and (
        "401" in lowered or "login" in lowered or "auth" in lowered or "account" in lowered
    ):
        return _diag(
            code="auth_required",
            title="需要重新登录",
            detail="账号未登录或登录态已失效，AI 笔记没有生成。请重新登录后重试；已完成的转录不会因此损坏。",
            next_action="重新登录后重试；如果转录已保存，打开结果后重生笔记。",
        )
    if any(token in lowered for token in ("incorrect api key", "invalid_api_key", "apikey-error", "api-key-error")):
        return _diag(
            code="invalid_api_key",
            title="百炼 / DashScope API Key 无效",
            detail="AI 笔记没有生成：当前百炼 / DashScope API Key 无效或已失效。转录和字幕已保存。",
            next_action="到设置页更新百炼 / DashScope API Key 后，回到编辑器点击“重生笔记”。",
        )
    if (
        "fluentflow account login is required" in lowered
        or any(token in lowered for token in ("http 401", "unauthorized"))
        or any(token in raw for token in ("账号未登录", "登录态", "重新登录"))
    ):
        if "ai 笔记" in raw.lower() or "转录不会因此损坏" in raw:
            return _diag(
                code="auth_required",
                title="需要重新登录",
                detail="账号未登录或登录态已失效，AI 笔记没有生成。请重新登录后重试；已完成的转录不会因此损坏。",
                next_action="重新登录后重试；如果转录已保存，打开结果后重生笔记。",
            )
        return _diag(
            code="auth_required",
            title="需要重新登录",
            detail="账号未登录或登录态已失效，请重新登录后重试。",
            next_action="重新登录后从同一条记录继续；如果仍失败，重新提交任务。",
        )
    if any(token in lowered for token in ("quota", "balance", "额度", "余额", "insufficientbalance")):
        return _diag(
            code="quota_insufficient",
            title="额度不足",
            detail="当前账号处理额度不足，请充值或联系维护者增加额度。",
            next_action="补足额度后重试，或降低本次处理成本。",
        )

    if "elevenlabs api key is not configured" in lowered or "elevenlabs transcription backend configuration is incomplete" in lowered:
        return _diag(
            code="cloud_stt_config_missing",
            title="云端转录配置缺失",
            detail="云端转录暂不可用：后端 ElevenLabs API Key 未配置。请联系产品维护者检查 ELEVENLABS_API_KEY。",
            next_action="联系维护者补齐云端转录配置，或改用本地转录。",
            retryable=False,
        )
    if "elevenlabs transcription request failed" in lowered:
        return _diag(
            code="cloud_stt_network_failed",
            title="云端转录请求失败",
            detail="ElevenLabs 云端转录请求失败。请检查网络连接后重试。",
            next_action="稍后重试；如果连续失败，改用本地转录。",
        )
    if "elevenlabs transcription failed" in lowered:
        return _diag(
            code="cloud_stt_failed",
            title="云端转录失败",
            detail="ElevenLabs 云端转录失败。请检查 API Key、账户额度、文件格式和音频长度后重试。",
            next_action="检查云端转录配置和额度；如果材料敏感或较长，改用本地转录。",
        )
    if "no position encodings are defined" in lowered:
        return _diag(
            code="local_diarization_too_long",
            title="本地说话人区分失败",
            detail="本地说话人区分模型无法处理当前音频长度。请关闭说话人区分，或切换云端转录。",
            next_action="关闭说话人区分后重试；如果必须区分讲话人，改用云端转录。",
        )
    if "eof occurred in violation of protocol" in lowered or "broken pipe" in lowered:
        return _diag(
            code="cloud_upload_interrupted",
            title="云端上传中断",
            detail="云端上传中断：通常是网络或云端转录服务断开连接。请重试；如果文件很大，先压缩或拆分音频。",
            next_action="重试；如果文件较大，压缩或拆分后再提交。",
        )
    if (
        "po token" in lowered
        or "gvs po token" in lowered
        or "sabr streaming" in lowered
        or "the page needs to be reloaded" in lowered
        or "youtube 原视频下载受限" in raw
    ):
        return _diag(
            code="youtube_media_restricted",
            title="YouTube 原视频下载受限",
            detail="YouTube 字幕不可用或不足以继续处理，同时原视频下载被 YouTube 客户端校验拦住。当前通常需要 PO Token、cookies 或高级本地下载环境，不是这条记录本身损坏。",
            next_action="上传本地视频或字幕文件；如果要继续尝试链接下载，请在高级本地模式配置 YouTube 下载环境后重试。",
        )
    if (
        "没有可用字幕" in raw
        or "no captions" in lowered
        or "no subtitles" in lowered
        or "there are missing subtitles languages" in lowered
    ):
        return _diag(
            code="youtube_no_captions",
            title="YouTube 没有可用字幕",
            detail="这个 YouTube 视频没有拿到可用字幕。FluentFlow 无法只靠链接稳定生成笔记，需要原视频、音频或字幕文件作为输入。",
            next_action="上传本地视频、音频或字幕文件；如果开启高级本地下载，可以尝试重新获取原视频。",
        )
    if "http error 403" in lowered or "视频下载失败：403" in raw or "forbidden" in lowered:
        return _diag(
            code="platform_forbidden",
            title="平台拒绝下载",
            detail="平台拒绝下载当前视频。已尽量优先使用字幕；如果仍失败，请稍后重试、配置浏览器 cookies，或上传本地视频。",
            next_action="稍后重试、配置浏览器 cookies，或上传本地视频。",
        )
    if "http error 429" in lowered or "too many requests" in lowered:
        return _diag(
            code="platform_rate_limited",
            title="平台请求过于频繁",
            detail="平台请求过于频繁，暂时限制了视频或字幕获取。请稍后重试，或上传本地视频/字幕文件。",
            next_action="稍后重试，或直接上传本地视频/字幕文件。",
        )
    if "视频下载超时" in raw or "timed out" in lowered or "timeout" in lowered:
        return _diag(
            code="video_download_timeout",
            title="视频下载超时",
            detail="视频下载时间过长，可能是视频较大或当前网络较慢。笔记会优先尝试使用字幕；如仍失败，请稍后重试或上传本地视频。",
            next_action="稍后重试，或上传本地视频。",
        )
    if "暂时无法自动解析这个视频链接" in raw:
        return _diag(
            code="video_link_parse_failed",
            title="链接暂时无法解析",
            detail="暂时无法自动解析这个视频链接。请换一个分享链接，或直接上传视频文件。",
            next_action="换一个分享链接，或直接上传视频文件。",
        )
    if "没有识别到视频链接" in raw:
        return _diag(
            code="video_link_missing",
            title="没有识别到视频链接",
            detail="没有识别到视频链接。请粘贴完整的分享文本或视频 URL。",
            next_action="粘贴完整分享文本或视频 URL 后重试。",
        )

    if "downloaded video is too large" in lowered or "file is too large" in lowered or "视频文件过大" in raw:
        return _diag(
            code="file_too_large",
            title="文件超过限制",
            detail="文件超过当前上传限制。请压缩视频、拆分文件，或调高后端上传大小限制。",
            next_action="压缩或拆分文件后重试。",
        )
    if "unsupported transcript file type" in lowered:
        return _diag(
            code="unsupported_transcript_type",
            title="字幕格式不支持",
            detail="不支持这个字幕/转录文件格式。请上传 SRT、VTT、TXT 或 Markdown 文件。",
            next_action="换成 SRT、VTT、TXT 或 Markdown 后重试。",
            retryable=False,
        )
    if "unsupported file type" in lowered:
        return _diag(
            code="unsupported_file_type",
            title="文件格式不支持",
            detail="不支持这个文件格式。请上传视频或音频文件。",
            next_action="换成支持的视频或音频文件后重试。",
            retryable=False,
        )
    if "no file uploaded" in lowered:
        return _diag(
            code="file_missing",
            title="没有收到文件",
            detail="没有收到上传文件。请重新选择文件后再试。",
            next_action="重新选择文件后提交。",
        )
    if "媒体文件为空" in raw:
        return _diag(
            code="media_file_empty",
            title="媒体文件为空",
            detail="上传的文件没有实际内容，未进入处理队列。",
            next_action="重新选择原始媒体文件后提交。",
            retryable=False,
        )
    if "媒体内容与文件扩展名不一致" in raw:
        return _diag(
            code="media_extension_mismatch",
            title="媒体格式与扩展名不一致",
            detail="文件的实际媒体格式与名称扩展名不一致，未进入处理队列。",
            next_action="使用原始文件或正确的扩展名后重新提交。",
            retryable=False,
        )
    if "没有可转录的音轨" in raw:
        return _diag(
            code="media_audio_stream_missing",
            title="没有可转录的音轨",
            detail="该媒体没有可用于转录的音频流，未进入处理队列。",
            next_action="上传包含系统声音或麦克风声音的音视频文件。",
            retryable=False,
        )
    if "媒体文件无法读取" in raw or "媒体中的音频无法读取" in raw:
        return _diag(
            code="media_unreadable",
            title="媒体文件无法读取",
            detail="文件可能已损坏，或内容与扩展名不匹配，未进入转录服务。",
            next_action="重新导出或更换媒体文件后提交。",
            retryable=False,
        )
    if "媒体预检暂不可用" in raw:
        return _diag(
            code="media_preflight_unavailable",
            title="媒体预检暂不可用",
            detail="服务暂时无法安全检查媒体文件，任务没有提交给转录服务。",
            next_action="稍后重试；如果持续出现，请联系维护者检查 FFmpeg 环境。",
        )
    if "queued source file is missing" in lowered or "原始文件已不存在" in raw:
        return _diag(
            code="source_file_missing",
            title="原始文件已不存在",
            detail="后台任务找不到原始文件。文件可能已被清理，请重新上传。",
            next_action="重新上传原始文件后再处理。",
            retryable=False,
        )

    if "queued processing request failed" in lowered:
        return _diag(
            code="queue_processing_failed",
            title="后台队列调用失败",
            detail="后台任务调用转录接口失败。请重试；如果连续出现，请重启后端服务并检查上传大小限制。",
            next_action="重试；如果连续出现，重启后端服务后再提交。",
        )
    if "queued transcript summary request failed" in lowered:
        return _diag(
            code="queue_summary_failed",
            title="后台笔记生成调用失败",
            detail="后台任务调用笔记生成接口失败。请重试；如果连续出现，请重启后端服务。",
            next_action="重试；如果转录已保存，打开结果后重生笔记。",
        )
    if "job not found" in lowered or "404" in lowered or "归属" in raw:
        return _diag(
            code="job_scope_mismatch",
            title="任务归属不一致",
            detail="任务记录没有在当前账号或本机范围内找到。可能是登录状态、任务归属或本地/云端路线不一致。",
            next_action="刷新历史记录后从同一条记录继续；如果仍失败，重新提交任务。",
        )

    if "unsupported note generation mode" in lowered or "chapter_coverage" in lowered:
        return _diag(
            code="unsupported_note_mode",
            title="笔记模式不受当前版本支持",
            detail="当前版本不支持这类笔记生成模式。请选择“自动”或“高保真”后重新提交任务。",
            next_action="切换为“自动”或“高保真”后重新提交任务。",
            retryable=False,
        )
    if "empty result" in lowered or "returned empty" in lowered or "空笔记" in raw:
        return _diag(
            code="empty_ai_note",
            title="AI 返回了空笔记",
            detail="AI 返回了空笔记，没有生成可用内容。",
            next_action="重生笔记；如果重复出现，换用直接生成模式或调整提示词。",
        )

    if "lark-cli" in lowered and any(token in lowered for token in ("login", "not logged", "unauthorized", "auth")):
        return _diag(
            code="lark_cli_login_required",
            title="本机飞书登录失效",
            detail="飞书导出失败：当前 lark-cli 没有可用登录身份。",
            next_action="在本机重新登录 lark-cli 后重试导出。",
        )
    if any(token in raw for token in ("Access denied", "no folder permission", "权限不足")) or any(token in lowered for token in ("permission", "forbidden")) and "feishu" in lowered:
        return _diag(
            code="feishu_permission_denied",
            title="飞书权限不足",
            detail="飞书导出失败：当前账号或应用没有目标文档/知识库权限。",
            next_action="检查飞书授权、目标文件夹或知识库权限后重试导出。",
        )
    if "feishu 图片上传失败" in raw or "图片上传失败" in raw:
        return _diag(
            code="feishu_image_upload_failed",
            title="飞书图片上传失败",
            detail="飞书导出时图片上传失败，文本笔记可能仍可用。",
            next_action="先使用 Markdown/PDF 产物；需要图片时检查飞书图片上传权限后重试。",
        )
    if "feishu" in lowered or "飞书" in raw or "lark" in lowered:
        return _diag(
            code="feishu_export_failed",
            title="飞书导出失败",
            detail="飞书导出失败。请检查授权、导出路线和目标文档权限。",
            next_action="检查飞书授权和导出路线后重试导出。",
        )

    if "视频下载失败" in raw:
        return _diag(
            code="video_download_failed",
            title="视频下载失败",
            detail=raw,
            next_action="稍后重试、配置浏览器 cookies，或上传本地视频。",
        )

    return _diag(
        code="unknown_error",
        title="任务处理失败",
        detail=raw,
        next_action="重试一次；如果连续失败，请把任务详情发给维护者排查。",
    )
