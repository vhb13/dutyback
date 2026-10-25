"""One place where agents are called, with budgets and usage logging.

Two backends, same contract (system prompt + prompt + JSON schema -> structured result):
  - "portkey" / "openai": the course key (PORTKEY_API_KEY, gpt-6-luna only) or an OpenAI key
    (OPENAI_API_KEY), through the OpenAI Responses API.
  - "claude": the Claude Agent SDK, using the Claude Code login on this computer.

Each agent runs with no built-in tools (no file system, no shell, no web). The only
tools an agent can call are the ones this app gives it explicitly.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
USAGE_FILE = ROOT / "logs" / "daily_usage.json"


def _load_env() -> None:
    """Settings from .env in the repo folder, then the parent folder (values already set win)."""
    for path in (ROOT / ".env", ROOT.parent / ".env"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
COURSE_MODEL = "gpt-6-luna"          # the only model allowed on the course key
CLAUDE_MODELS = {
    "reader": os.environ.get("DUTYBACK_READER_MODEL", "opus"),
    "checker": os.environ.get("DUTYBACK_CHECKER_MODEL", "sonnet"),
    "advisor": os.environ.get("DUTYBACK_ADVISOR_MODEL", "sonnet"),
    "baseline": os.environ.get("DUTYBACK_BASELINE_MODEL", "opus"),
}
OPENAI_MODEL = os.environ.get("DUTYBACK_OPENAI_MODEL", COURSE_MODEL)
# USD per 1M tokens (gpt-6-luna list prices); override if you use another OpenAI model.
PRICE_IN = float(os.environ.get("DUTYBACK_PRICE_IN", "0.10"))
PRICE_CACHED = float(os.environ.get("DUTYBACK_PRICE_CACHED", "0.01"))
PRICE_OUT = float(os.environ.get("DUTYBACK_PRICE_OUT", "0.50"))
MAX_OUTPUT_TOKENS = int(os.environ.get("DUTYBACK_MAX_OUTPUT_TOKENS", "32000"))

MAX_USD_PER_CALL = float(os.environ.get("DUTYBACK_MAX_USD_PER_CALL", "1.50"))
MAX_RUNS_PER_DAY = int(os.environ.get("DUTYBACK_MAX_RUNS_PER_DAY", "40"))

# Kept for callers that read the model names.
MODELS = CLAUDE_MODELS


class BudgetError(RuntimeError):
    pass


@dataclass
class AgentCall:
    agent: str
    model: str
    seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    turns: int = 0
    tool_calls: list[dict] = field(default_factory=list)
    ok: bool = True
    error: str | None = None
    model_id: str | None = None

    def to_dict(self):
        return self.__dict__.copy()


def count_run() -> None:
    """Daily run cap, so a public link can't burn through the key or subscription."""
    USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    data = {}
    if USAGE_FILE.exists():
        try:
            data = json.loads(USAGE_FILE.read_text())
        except json.JSONDecodeError:
            data = {}
    n = data.get(today, 0)
    if n >= MAX_RUNS_PER_DAY:
        raise BudgetError(f"Daily limit of {MAX_RUNS_PER_DAY} runs reached. Try again tomorrow or use demo mode.")
    USAGE_FILE.write_text(json.dumps({today: n + 1}))


# ---------------------------------------------------------------- backend choice

def _claude_logged_in() -> bool:
    import shutil
    import subprocess
    if not shutil.which("claude"):
        return False
    try:
        out = subprocess.run(["claude", "auth", "status"], capture_output=True, text=True, timeout=15)
        return '"loggedIn": true' in out.stdout
    except Exception:
        return False


def backend() -> str | None:
    """DUTYBACK_BACKEND = auto | portkey | openai | claude. Auto prefers the course key."""
    want = os.environ.get("DUTYBACK_BACKEND", "auto").lower()
    if want in ("portkey", "openai", "claude"):
        return want
    if os.environ.get("PORTKEY_API_KEY"):
        return "portkey"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if _claude_logged_in():
        return "claude"
    return None


def model_for(agent: str, be: str | None = None) -> str:
    be = be or backend()
    if be == "portkey":
        return COURSE_MODEL
    if be == "openai":
        return OPENAI_MODEL
    return CLAUDE_MODELS[agent]


def backend_label() -> str:
    be = backend()
    return {"portkey": f"{COURSE_MODEL} (course key)", "openai": f"{OPENAI_MODEL} (OpenAI key)",
            "claude": "Claude (Claude Code login)"}.get(be or "", "none")


def live_available() -> bool:
    """True if any live backend is configured: the course key, an OpenAI key, or a Claude Code login."""
    return backend() is not None


# ---------------------------------------------------------------- entry point

async def run_agent(agent: str, system: str, prompt: str, schema: dict, *,
                    tools: list | None = None, mcp_servers: dict | None = None,
                    allowed_tools: list[str] | None = None,
                    max_turns: int = 3, model: str | None = None) -> tuple[dict | None, AgentCall]:
    be = backend()
    if be in ("portkey", "openai"):
        return await _run_openai(be, agent, system, prompt, schema, tools=tools or [],
                                 max_turns=max_turns, model=model)
    return await _run_claude(agent, system, prompt, schema, mcp_servers=mcp_servers,
                             allowed_tools=allowed_tools, max_turns=max_turns, model=model)


# ---------------------------------------------------------------- Claude Agent SDK

async def _run_claude(agent, system, prompt, schema, *, mcp_servers, allowed_tools, max_turns, model):
    from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ResultMessage, ToolUseBlock,
                                  query)
    model = model or CLAUDE_MODELS[agent]
    call = AgentCall(agent=agent, model=model)
    opts = ClaudeAgentOptions(
        model=model,
        system_prompt=system,
        tools=[],                         # no built-in tools at all
        mcp_servers=mcp_servers or {},
        allowed_tools=allowed_tools or [],
        setting_sources=[],               # ignore any local Claude settings or CLAUDE.md
        permission_mode="dontAsk",
        max_turns=max_turns,
        max_budget_usd=MAX_USD_PER_CALL,
        output_format={"type": "json_schema", "schema": schema},
        cwd=str(ROOT / "logs"),
    )
    t0 = time.time()
    result = None
    try:
        async for m in query(prompt=prompt, options=opts):
            if isinstance(m, AssistantMessage):
                call.model_id = getattr(m, "model", None) or call.model_id
                for b in m.content:
                    if isinstance(b, ToolUseBlock) and b.name != "StructuredOutput":
                        call.tool_calls.append({"tool": b.name.split("__")[-1], "input": b.input})
            elif isinstance(m, ResultMessage):
                u = m.usage or {}
                call.input_tokens = int(u.get("input_tokens") or 0)
                call.output_tokens = int(u.get("output_tokens") or 0)
                call.cache_read_tokens = int(u.get("cache_read_input_tokens") or 0)
                call.cache_write_tokens = int(u.get("cache_creation_input_tokens") or 0)
                call.cost_usd = round(float(m.total_cost_usd or 0), 4)
                call.turns = int(m.num_turns or 0)
                result = m.structured_output
                if m.subtype != "success" or result is None:
                    call.ok = False
                    call.error = f"agent ended with {m.subtype}"
    except Exception as exc:
        call.ok = False
        call.error = f"{exc.__class__.__name__}: {str(exc)[:300]}"
    call.seconds = round(time.time() - t0, 1)
    return result, call


# ---------------------------------------------------------------- OpenAI Responses API (course key)

_PY_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean"}


def _tool_spec(t) -> dict:
    """An SDK tool (name, description, {arg: python type}) as a strict function tool."""
    props = {k: {"type": _PY_TYPES.get(v, "string")} for k, v in (t.input_schema or {}).items()}
    return {"type": "function", "name": t.name, "description": t.description, "strict": True,
            "parameters": {"type": "object", "properties": props, "required": list(props),
                           "additionalProperties": False}}


def _client(be: str):
    from openai import AsyncOpenAI
    if be == "portkey":
        return AsyncOpenAI(api_key=os.environ["PORTKEY_API_KEY"], base_url=PORTKEY_BASE_URL, max_retries=3)
    return AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"], max_retries=3)


async def _run_openai(be, agent, system, prompt, schema, *, tools, max_turns, model):
    model = COURSE_MODEL if be == "portkey" else (model if model and "gpt" in model else OPENAI_MODEL)
    call = AgentCall(agent=agent, model=model)
    by_name = {t.name: t for t in tools}
    specs = [_tool_spec(t) for t in tools]
    fmt = {"format": {"type": "json_schema", "name": f"{agent.split()[0]}_output", "strict": True, "schema": schema}}
    history: list = [{"role": "user", "content": prompt}]
    t0 = time.time()
    result = None
    try:
        client = _client(be)
        for turn in range(1, max_turns + 1):
            kwargs = dict(model=model, instructions=system, input=history, text=fmt,
                          max_output_tokens=MAX_OUTPUT_TOKENS, store=False)
            if specs:
                kwargs["tools"] = specs
            r = await client.responses.create(**kwargs)
            call.turns = turn
            call.model_id = r.model
            u = r.usage
            cached = int(getattr(getattr(u, "input_tokens_details", None), "cached_tokens", 0) or 0)
            call.input_tokens += int(u.input_tokens) - cached
            call.cache_read_tokens += cached
            call.output_tokens += int(u.output_tokens)
            call.cost_usd = round((call.input_tokens * PRICE_IN + call.cache_read_tokens * PRICE_CACHED
                                   + call.output_tokens * PRICE_OUT) / 1e6, 4)
            if call.cost_usd > MAX_USD_PER_CALL:
                raise BudgetError(f"cost cap of ${MAX_USD_PER_CALL:.2f} per call reached")

            calls = [o for o in r.output if o.type == "function_call"]
            if not calls:
                if r.status != "completed":
                    raise RuntimeError(f"response {r.status}: {getattr(r.incomplete_details, 'reason', '')}")
                result = json.loads(r.output_text)
                break
            if turn == max_turns:
                raise RuntimeError("turn limit reached before a final answer")
            history += [{"type": "function_call", "call_id": c.call_id, "name": c.name, "arguments": c.arguments}
                        for c in calls]
            for c in calls:
                args = json.loads(c.arguments or "{}")
                call.tool_calls.append({"tool": c.name, "input": args})
                t = by_name.get(c.name)
                if t is None:
                    text = f"Unknown tool {c.name}."
                else:
                    out = await t.handler(args)
                    text = "\n".join(b.get("text", "") for b in out.get("content", []))
                history.append({"type": "function_call_output", "call_id": c.call_id, "output": text})
    except Exception as exc:
        call.ok = False
        call.error = f"{exc.__class__.__name__}: {str(exc)[:300]}"
        result = None
    if result is None and call.ok:
        call.ok = False
        call.error = "agent ended without a result"
    call.seconds = round(time.time() - t0, 1)
    return result, call


async def _selftest():  # python -m app.pipeline.llm
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"],
              "additionalProperties": False}
    print("backend:", backend_label())
    res, call = await run_agent("advisor", "Answer in JSON.", "Say ok=true.", schema)
    print(res, call.to_dict())


if __name__ == "__main__":
    asyncio.run(_selftest())
