"""Engine choice and tool conversion for the course-key backend (no network calls)."""
from claude_agent_sdk import tool

from app.pipeline import llm


def test_course_key_wins_in_auto(monkeypatch):
    monkeypatch.setenv("DUTYBACK_BACKEND", "auto")
    monkeypatch.setenv("PORTKEY_API_KEY", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    assert llm.backend() == "portkey"


def test_openai_key_when_no_course_key(monkeypatch):
    monkeypatch.setenv("DUTYBACK_BACKEND", "auto")
    monkeypatch.delenv("PORTKEY_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    assert llm.backend() == "openai"


def test_forced_backend(monkeypatch):
    monkeypatch.setenv("DUTYBACK_BACKEND", "claude")
    monkeypatch.setenv("PORTKEY_API_KEY", "test")
    assert llm.backend() == "claude"


def test_course_key_only_uses_gpt_6_luna(monkeypatch):
    monkeypatch.setenv("DUTYBACK_BACKEND", "portkey")
    for agent in ("reader", "checker", "advisor", "baseline"):
        assert llm.model_for(agent) == "gpt-6-luna"


def test_tool_spec_is_strict():
    @tool("read_page", "Full text of one page.", {"doc": str, "page": int})
    async def read_page(_args):
        return {"content": []}

    spec = llm._tool_spec(read_page)
    assert spec["name"] == "read_page" and spec["strict"] is True
    assert spec["parameters"]["properties"] == {"doc": {"type": "string"}, "page": {"type": "integer"}}
    assert spec["parameters"]["required"] == ["doc", "page"]
    assert spec["parameters"]["additionalProperties"] is False
