from __future__ import annotations

import json

from scripts import fluentflow_mcp_server as server


def test_submit_video_link_wraps_agent_create_task(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_agent_request(method: str, path: str, **kwargs):
        captured.update({"method": method, "path": path, **kwargs})
        return {"ok": True, "task_id": "task-mcp"}

    monkeypatch.setattr(server, "_agent_request", fake_agent_request)

    result = server.submit_video_link(
        "https://youtu.be/demo",
        title="Demo",
        stt_provider="local",
        skip_summary=True,
        note_mode="auto",
        prompt_preset="default",
        api_base="http://127.0.0.1:8000",
        client_id="client-a",
    )

    assert result["task_id"] == "task-mcp"
    assert captured["method"] == "POST"
    assert captured["path"] == "/agent/v1/tasks"
    assert captured["api_base"] == "http://127.0.0.1:8000"
    assert captured["client_id"] == "client-a"
    assert captured["payload"]["input_type"] == "video_link"
    assert captured["payload"]["input"] == "https://youtu.be/demo"
    assert captured["payload"]["title"] == "Demo"
    assert captured["payload"]["options"] == {
        "stt_provider": "local",
        "skip_summary": "true",
        "note_mode": "auto",
        "prompt_preset": "default",
    }


def test_task_tools_map_to_stable_agent_api(monkeypatch) -> None:
    calls: list[tuple[str, str, dict[str, object]]] = []

    def fake_agent_request(method: str, path: str, **kwargs):
        calls.append((method, path, kwargs))
        return {"ok": True}

    monkeypatch.setattr(server, "_agent_request", fake_agent_request)

    server.get_task("task-1")
    server.wait_task("task-1", timeout_seconds=5, poll_interval_seconds=1)
    server.get_task_package("task-1")
    server.diagnose_task("task-1")
    server.regenerate_note("task-1", note_mode="high_fidelity")
    server.export_result("task-1", target="lark", title="Demo")

    assert [(method, path) for method, path, _ in calls] == [
        ("GET", "/agent/v1/tasks/task-1"),
        ("POST", "/agent/v1/tasks/task-1/wait"),
        ("GET", "/agent/v1/tasks/task-1/package"),
        ("GET", "/agent/v1/tasks/task-1/diagnosis"),
        ("POST", "/agent/v1/tasks/task-1/note/regenerate"),
        ("POST", "/agent/v1/tasks/task-1/exports"),
    ]
    assert calls[1][2]["payload"] == {"timeout_seconds": 5, "poll_interval_seconds": 1}
    assert calls[4][2]["payload"] == {"note_mode": "high_fidelity"}
    assert calls[5][2]["payload"] == {"target": "lark", "title": "Demo"}


def test_agent_request_returns_structured_error(monkeypatch) -> None:
    def fake_api_request(*args, **kwargs):
        raise server.FluentFlowApiError("Job not found", status=404, payload={"detail": "Job not found"})

    monkeypatch.setattr(server, "api_request", fake_api_request)

    result = server.get_task_package("missing")

    assert result == {
        "ok": False,
        "error": "Job not found",
        "status": 404,
        "payload": {"detail": "Job not found"},
    }


def test_jsonrpc_tools_list_exposes_product_level_actions() -> None:
    response = server.handle_jsonrpc_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

    tools = response["result"]["tools"]
    names = [tool["name"] for tool in tools]
    assert names == [
        "submit_video_link",
        "submit_transcript",
        "get_task",
        "wait_task",
        "get_task_package",
        "diagnose_task",
        "regenerate_note",
        "export_result",
    ]
    assert tools[0]["inputSchema"]["required"] == ["input_text"]


def test_jsonrpc_tools_call_returns_mcp_content(monkeypatch) -> None:
    monkeypatch.setitem(server.TOOL_FUNCTIONS, "get_task_package", lambda task_id, **kwargs: {"ok": True, "task_id": task_id})

    response = server.handle_jsonrpc_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "get_task_package", "arguments": {"task_id": "task-1", "ignored": "value"}},
        }
    )

    result = response["result"]
    assert result["structuredContent"] == {"ok": True, "task_id": "task-1"}
    assert json.loads(result["content"][0]["text"]) == {"ok": True, "task_id": "task-1"}


def test_jsonrpc_initialize_returns_tools_capability() -> None:
    response = server.handle_jsonrpc_message({"jsonrpc": "2.0", "id": 3, "method": "initialize", "params": {}})

    assert response["result"]["protocolVersion"] == server.PROTOCOL_VERSION
    assert response["result"]["capabilities"] == {"tools": {"listChanged": False}}
    assert response["result"]["serverInfo"]["name"] == "fluentflow"
