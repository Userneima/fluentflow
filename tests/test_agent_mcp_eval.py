from __future__ import annotations

from scripts import evaluate_agent_mcp as eval_script


def test_eval_cases_can_be_loaded() -> None:
    mock_cases = eval_script.load_eval_cases("mock")
    backend_cases = eval_script.load_eval_cases("backend-e2e")

    assert [case.name for case in mock_cases] == [
        "video_link_success_note_export",
        "video_link_failure_diagnosis",
    ]
    assert [case.name for case in backend_cases] == ["backend_transcript_package_diagnosis"]


def test_mock_eval_outputs_metrics() -> None:
    result = eval_script.run_eval("mock")

    assert result["ok"] is True
    assert result["mode"] == "mock"
    assert result["summary"] == {"total": 2, "passed": 2, "failed": 0}

    success_case = result["cases"][0]
    assert success_case["name"] == "video_link_success_note_export"
    assert success_case["status"] == "passed"
    assert success_case["elapsed_seconds"] >= 0
    assert [call["name"] for call in success_case["tool_calls"]] == [
        "submit_video_link",
        "wait_task",
        "get_task_package",
        "regenerate_note",
        "export_result",
    ]
    assert success_case["task_id"] == "eval-success"
    assert success_case["package"]["source_type"] == "video_link"
    assert success_case["package"]["note_status"] == "completed"
    assert success_case["export"]["target"] == "lark"
    assert success_case["export"]["url_present"] is True


def test_failure_diagnosis_case_records_diagnosis_instead_of_crashing() -> None:
    result = eval_script.run_eval("mock")
    failure_case = next(case for case in result["cases"] if case["name"] == "video_link_failure_diagnosis")

    assert failure_case["status"] == "passed"
    assert failure_case["task_id"] == "eval-failure"
    assert failure_case["package"]["task_status"] == "failed"
    assert failure_case["diagnosis"]["code"] == "video_source_unavailable"
    assert failure_case["error"] is None
    assert [call["name"] for call in failure_case["tool_calls"]] == [
        "submit_video_link",
        "wait_task",
        "diagnose_task",
        "get_task_package",
    ]
