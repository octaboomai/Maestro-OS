import os
import json
import re
from typing import List, Dict
from openai import OpenAI

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

print("[*] Initializing Apex Swarm OS™ (v22.1 - Stability & Render Fix)...")

# ==============================================================================
# 1. DYNAMIC AI BRAIN ROUTER (NVIDIA Qwen 3.5 Elite Stack)
# ==============================================================================
# NOTE (fix): Groq decommissioned llama3-8b-8192 a long time ago, and on
# 2026-06-17 it ALSO decommissioned llama-3.1-8b-instant and
# llama-3.3-70b-versatile for free/developer-tier usage. That means every
# single free-tier agent in the old config was calling a dead model ID and
# would fail on every request. Swapped to Groq's own recommended
# replacements (openai/gpt-oss-20b / openai/gpt-oss-120b), which are
# current, tool-calling capable, and fast.
AGENT_MODELS = {
    "Master_Orchestrator": {
        "free": "groq/openai/gpt-oss-20b",
        "pro": "meta/llama-3.1-8b-instruct"
    },
    "Apex_Researcher": {
        "free": "groq/openai/gpt-oss-120b",
        "pro": "qwen/qwen3-next-80b-a3b-instruct"
    },
    "Apex_Strategist": {
        "free": "groq/openai/gpt-oss-120b",
        "pro": "meta/llama-3.1-70b-instruct"
    },
    "Apex_Coder": {
        "free": "groq/openai/gpt-oss-120b",
        "pro": "qwen/qwen3-next-80b-a3b-instruct"
    }
}

def get_client_for_model(tier: str, agent_name: str):
    """Returns (client, actual_model_id, is_groq)."""
    model_name = AGENT_MODELS.get(agent_name, {}).get(tier, "groq/openai/gpt-oss-120b")

    # fix: use startswith() on the explicit "groq/" marker prefix instead of
    # a loose substring check, so routing can't be fooled by a future model
    # id that happens to contain "groq" somewhere else in its name.
    is_groq = model_name.startswith("groq/")

    if is_groq:
        client = OpenAI(
            api_key=os.environ.get("GROQ_API_KEY"),
            base_url="https://api.groq.com/openai/v1"
        )
        actual_model_name = model_name[len("groq/"):]
        return client, actual_model_name, True
    else:
        client = OpenAI(
            api_key=os.environ.get("NVIDIA_API_KEY"),
            base_url="https://integrate.api.nvidia.com/v1"
        )
        return client, model_name, False

# ==============================================================================
# 2. SHARED WORKSPACE & TOKEN TRACKING
# ==============================================================================
class SwarmState:
    def __init__(self, query: str):
        self.query = query
        self.plan = []
        self.artifacts = {}
        self.messages = []
        self.current_agent = None
        self.tokens_used = 0  # Track total tokens consumed
        self.tokens_by_agent = {}  # fix: per-agent breakdown, for diagnosing
                                    # "high token cost, thin output" cases
        self.has_searched = False  # fix: tracks whether Apex_Researcher has
                                    # actually called tool_web_search yet --
                                    # used to make searching mandatory at the
                                    # code level instead of hoping the model
                                    # follows optional prompt wording

    def add_artifact(self, key: str, value: str): self.artifacts[key] = value
    def get_artifact(self, key: str) -> str: return self.artifacts.get(key, "No data available.")
    def to_dict(self): return {
        "plan": self.plan,
        "final_answer": self.artifacts.get("final_answer", "Error: No final answer generated."),
        "history": self.messages,
        "tokens_used": self.tokens_used,
        "tokens_by_agent": self.tokens_by_agent
    }

# ==============================================================================
# 3. AGENT DEFINITIONS
# ==============================================================================
AGENT_DEFS = {
    "Master_Orchestrator": {
        "system_prompt": (
            "You are the Master Orchestrator of the Apex Swarm OS. Analyze the user's request and route it instantly.\n"
            "ROUTING RULES:\n"
            "- If they want CODE, a WEB APP, a UI, or a DASHBOARD: Delegate to Apex_Coder.\n"
            "- If they want RESEARCH, WEB DATA, or MARKET ANALYSIS: Delegate to Apex_Researcher.\n"
            "- If they want WRITING, STRATEGY, or EMAILS: Delegate to Apex_Strategist.\n"
            "Be fast. Do not ask follow-up questions. Just route."
        ),
        "tools": ["delegate_to_agent"],
        "allowed_transitions": ["Apex_Coder", "Apex_Researcher", "Apex_Strategist"]
    },
    "Apex_Researcher": {
        "system_prompt": (
            "You are an Apex Researcher. Gather raw intelligence at lightning speed.\n"
            "WORKFLOW:\n"
            "1. Call `tool_web_search` at least once. Always -- even if you think you already "
            "know the answer, your training data may predate recent developments, so verify "
            "with a live search before reporting anything as fact.\n"
            "2. Extract specific facts, numbers, and names. No fluff.\n"
            "3. Save findings using `save_artifact` with key 'research_data'.\n"
            "4. Delegate to Apex_Strategist to format the final answer.\n"
            "NEVER delegate to yourself."
        ),
        "tools": ["tool_web_search", "save_artifact", "delegate_to_agent"],
        "allowed_transitions": ["Apex_Strategist"]
    },
    "Apex_Strategist": {
        "system_prompt": (
            "You are an Apex Strategist. You turn raw research into a polished answer a busy "
            "executive can scan in seconds and still find every detail in. Structure is not "
            "optional decoration -- it is the product.\n\n"
            "WORKFLOW:\n"
            "1. Read 'research_data' using `read_artifact` if available.\n"
            "2. Write the final answer following the FORMAT RULES below.\n"
            "3. Save it as 'final_answer' using `save_artifact`.\n"
            "4. Call `finish_task`.\n\n"
            "FORMAT RULES (this is rendered as real Markdown, not shown as plain text -- use it):\n"
            "- Open with ONE bolded sentence that directly answers the question. No preamble. "
            "This is the FIRST line of a longer answer, not the entire answer -- always continue "
            "into the sections below after it.\n"
            "- A single sentence is NEVER a complete final answer to a 'tell me about X' or "
            "'give me details' style question, even if research_data is thin. If the research "
            "is limited, say so explicitly in a section (e.g. '## ⚠️ Limited Information') and "
            "share whatever was actually found -- don't collapse everything into one vague line.\n"
            "- Break the body into sections using `## ` headers. Choose headers that fit THIS "
            "answer -- don't force unrelated content into a fixed template.\n"
            "  * For a factual/research question about a product, company, or technology, "
            "good headers look like: `## 🔑 What It Is`, `## 🏆 Performance & Benchmarks`, "
            "`## 📐 How It Works`, `## 🌍 Why It Matters`.\n"
            "  * For a business strategy, market-entry, or go/no-go recommendation, use exactly: "
            "`## 🎯 Executive Bottom Line`, `## 🧠 Strategic Context`, `## 🚨 Risk Matrix`, "
            "`## 📊 Key Data Points`.\n"
            "- Inside a section, use `- ` bullets with a bolded label for each fact, e.g. "
            "`- **Founded:** 2023`. Do not bury facts inside paragraph prose.\n"
            "- Comparing two or more things? Use a Markdown table, not a paragraph.\n"
            "- Code belongs ONLY inside a fenced ```language block. Never describe code in "
            "prose instead of showing it, and never put prose inside a code fence -- code is "
            "code, a story is a story, keep them apart.\n"
            "- Keep narrative explanation (the 'why' / backstory) as its own short paragraph, "
            "separate from bullet-point facts.\n"
            "- Close with one bolded line starting with '**In short:**' that sums up the answer.\n"
            "- Never invent a specific number, date, or quote (benchmark scores, prices, "
            "funding figures) that isn't actually in `research_data`. If the research doesn't "
            "cover a detail, say so plainly instead of making one up -- a wrong number is worse "
            "than an honest gap.\n"
            "- Never repeat a fact, sentence, or section you've already written. If you notice "
            "yourself about to restate something, stop the section there instead -- a shorter "
            "answer that doesn't loop is better than a long one that does."
        ),
        "tools": ["read_artifact", "save_artifact", "finish_task"],
        "allowed_transitions": []
    },
    "Apex_Coder": {
        "system_prompt": (
            "You are an Apex Coder and Elite Debugger. You use deep reasoning to build flawless applications and fix complex bugs.\n"
            "WORKFLOW FOR BUILDING APPS:\n"
            "1. Think step-by-step about the architecture before writing code.\n"
            "2. Write a SINGLE FILE HTML app using Tailwind CSS (via CDN) and Vanilla JS.\n"
            "3. It must be fully self-contained and runnable in an iframe.\n"
            "4. Wrap the HTML code in ```html ... ``` markdown blocks.\n\n"
            "WORKFLOW FOR DEBUGGING:\n"
            "1. Analyze the provided code or error message carefully.\n"
            "2. Identify the root cause of the bug using step-by-step logic.\n"
            "3. Provide the fully corrected code, highlighting what was changed.\n"
            "4. Wrap corrected code in the appropriate markdown blocks (e.g., ```python, ```javascript).\n\n"
            "Save the output as 'final_answer' using `save_artifact`.\n"
            "Call `finish_task`."
        ),
        "tools": ["save_artifact", "finish_task"],
        "allowed_transitions": []
    }
}

# ==============================================================================
# 4. TOOL IMPLEMENTATIONS
# ==============================================================================
def tool_web_search(query: str) -> str:
    clean_query = query.replace("top 3", "").replace("latest", "").strip()
    if not clean_query: clean_query = "market analysis"
    print(f"    [TOOL_EXEC] Searching: {clean_query!r}")
    try:
        with DDGS(timeout=10) as ddgs:
            results = list(ddgs.text(clean_query, region="wt-wt", safesearch="off", max_results=5))
        if not results: return "LIVE SEARCH FAILED: No results found."
        # fix: cap each snippet's length. Untruncated search bodies can
        # balloon the shared context every downstream agent reads from --
        # a noisy wall of raw search text is a likely contributor to
        # rambling/repetitive output in Long Context runs, especially once
        # it's been carried through Researcher -> Strategist.
        def _trim(text: str, limit: int = 280) -> str:
            text = " ".join(text.split())
            return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"
        return "\n".join(f"[{i+1}] {r.get('title', '')}: {_trim(r.get('body', ''))}" for i, r in enumerate(results))
    except Exception as e:
        return f"LIVE SEARCH FAILED: Search engine error ({e})."

TOOL_SCHEMAS = [
    {"type": "function", "function": {"name": "delegate_to_agent", "description": "Hand off the current task to another agent.", "parameters": {"type": "object", "properties": {"agent_name": {"type": "string", "enum": list(AGENT_DEFS.keys())}, "message": {"type": "string"}}, "required": ["agent_name", "message"]}}},
    {"type": "function", "function": {"name": "tool_web_search", "description": "Search the web for market data, competitor info, or news.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "save_artifact", "description": "Save work to the shared workspace.", "parameters": {"type": "object", "properties": {"key": {"type": "string", "enum": ["research_data", "final_answer"]}, "content": {"type": "string"}}, "required": ["key", "content"]}}},
    {"type": "function", "function": {"name": "read_artifact", "description": "Read an artifact from the workspace.", "parameters": {"type": "object", "properties": {"key": {"type": "string", "enum": ["research_data"]}}, "required": ["key"]}}},
    {"type": "function", "function": {"name": "finish_task", "description": "End the swarm process.", "parameters": {"type": "object", "properties": {}}}}
]

def get_tool_schemas_for_agent(agent_name: str) -> list:
    allowed = set(AGENT_DEFS[agent_name]["tools"])
    return [s for s in TOOL_SCHEMAS if s["function"]["name"] in allowed]

def dispatch_tool_call(state: SwarmState, agent_name: str, agent_def: dict, func_name: str, func_args: dict):
    """
    fix: every argument is now read with .get() and validated instead of
    raw dict indexing (func_args["key"]). Previously, a model that emitted
    a tool call with a missing/misnamed argument (which free-tier models do
    occasionally, especially mid self-heal) would raise an uncaught
    KeyError and kill the whole agent turn. Now it returns a descriptive
    error string back to the model so the loop can recover gracefully.
    """
    if func_name not in agent_def["tools"]:
        return f"ERROR: {agent_name} is not permitted to use '{func_name}'.", False

    if func_name == "delegate_to_agent":
        next_agent = func_args.get("agent_name")
        if not next_agent:
            return "ERROR: delegate_to_agent call is missing the required 'agent_name' argument.", False
        if next_agent == agent_name:
            return f"CRITICAL ERROR: You cannot delegate to yourself! You are {agent_name}.", False
        if next_agent not in agent_def["allowed_transitions"]:
            return f"ERROR: You cannot delegate to {next_agent}.", False
        # fix: this is the actual root cause of the "9426 tokens, one
        # sentence" result. Apex_Researcher's old prompt made searching
        # optional ("if you need live data"), so a model that assumed it
        # already knew the answer could skip straight to delegating with
        # no real research_data -- leaving Apex_Strategist nothing to work
        # with. Enforcing this here means it no longer depends on the model
        # choosing to follow that instruction.
        if agent_name == "Apex_Researcher" and not state.has_searched:
            return "ERROR: You must call tool_web_search at least once before delegating to Apex_Strategist. Search first, then delegate.", False
        state.current_agent = next_agent
        handoff_note = func_args.get("message", "")
        return f"Control handed over to {next_agent}. Handoff note from {agent_name}: {handoff_note}", False

    elif func_name == "save_artifact":
        key = func_args.get("key")
        content = func_args.get("content")
        if not key or content is None:
            return "ERROR: save_artifact requires both a 'key' and 'content' argument.", False
        state.add_artifact(key, content)
        return f"Artifact '{key}' saved successfully.", False

    elif func_name == "read_artifact":
        key = func_args.get("key")
        if not key:
            return "ERROR: read_artifact requires a 'key' argument.", False
        return state.get_artifact(key), False

    elif func_name == "tool_web_search":
        query = func_args.get("query")
        if not query:
            return "ERROR: tool_web_search requires a 'query' argument.", False
        state.has_searched = True  # fix: mark searched even if the search
                                    # itself comes back empty/failed -- the
                                    # requirement is that an attempt was
                                    # made, not that it succeeded
        return tool_web_search(query), False

    elif func_name == "finish_task":
        if "final_answer" not in state.artifacts: state.add_artifact("final_answer", "Task finished, but no final answer was saved.")
        return "Task finished.", True

    return f"Error: Tool {func_name} not found.", False

# ==============================================================================
# 4b. SELF-HEAL HELPER
# ==============================================================================
def extract_self_healed_call(error_str: str):
    """
    fix (this is the bug behind the screenshot): the old code used the regex
    r'<function=(\\w+)>(\\{.*?\\})</function>' to pull the JSON arguments out
    of a malformed tool call. `.*?` is non-greedy, so it stops at the FIRST
    closing brace it finds. Any time the tool call's content contains its
    own braces -- which is guaranteed for generated HTML/CSS/JS, e.g.
    `body { margin: 0; }` -- the regex truncated the JSON at that inner
    brace instead of the real end of the object. That produced invalid JSON
    (or, when it happened to still parse, badly truncated HTML), which is
    exactly the raw, unrendered "<!DOCTYPE html>..." text from the
    screenshot.

    Fix: find where the JSON object starts, then let Python's own JSON
    decoder (`raw_decode`) walk forward and find the real matching closing
    brace, since it understands string escaping and nesting correctly.
    """
    start_match = re.search(r'<function=(\w+)>\s*(\{)', error_str)
    if not start_match:
        return None, None

    func_name = start_match.group(1)
    json_start = start_match.start(2)

    decoder = json.JSONDecoder()
    try:
        func_args, _end_idx = decoder.raw_decode(error_str, json_start)
    except json.JSONDecodeError:
        return func_name, None

    return func_name, func_args


def extract_tool_validation_error(error_str: str):
    """
    A second, different malformed-tool-call shape than extract_self_healed_call
    handles. Groq's schema-validation rejections come back as a clean
    `tool_use_failed` error with NO `<function=...>` wrapper at all, e.g.:

        Error code: 400 - {'error': {'message': "...did not match schema:
        errors: [missing properties: 'query']", 'code': 'tool_use_failed',
        'failed_generation': '{"name": "tool_web_search", "arguments":
        {"cursor": 5, "id": 1}}'}}

    Here the model didn't almost get it right (like the HTML case) -- it
    invented parameters that don't exist in the schema and omitted the
    required one. There's nothing safe to "repair" in the arguments, so
    instead of trying to dispatch a guessed call, this pulls out which tool
    was attempted and why it was rejected, so the model can be told exactly
    what to fix and try again.
    """
    name_match = re.search(r'"name":\s*"(\w+)"', error_str)
    func_name = name_match.group(1) if name_match else None

    msg_match = re.search(r"'message':\s*[\"'](.+?)[\"'],\s*'type'", error_str, re.DOTALL)
    message = msg_match.group(1) if msg_match else error_str

    return func_name, message

# ==============================================================================
# 5. THE AGENTIC EXECUTION LOOP
# ==============================================================================
def execute_agent_loop(state: SwarmState, tier: str = "free", max_output_tokens: int = 4096, max_steps: int = 15) -> dict:
    step = 0
    while step < max_steps:
        step += 1
        agent_name = state.current_agent
        agent_def = AGENT_DEFS[agent_name]

        client, model_name, is_groq = get_client_for_model(tier, agent_name)
        print(f"\n[STEP {step}] Agent: {agent_name} | Model: {model_name} | Tier: {tier}")

        state.plan.append(agent_name)
        api_messages = [{"role": "system", "content": agent_def["system_prompt"]}] + state.messages
        agent_tools = get_tool_schemas_for_agent(agent_name)

        # fix: Groq has deprecated `max_tokens` in favor of `max_completion_tokens`
        # for its current reasoning-capable lineup (openai/gpt-oss-*, qwen3,
        # deepseek-r1 variants) -- every current Groq doc example for these
        # models uses max_completion_tokens. NVIDIA NIM's OpenAI-compatible
        # endpoint still expects max_tokens. Pick the right kwarg per-provider
        # instead of hardcoding one that silently breaks the other.
        token_kwarg = {"max_completion_tokens": max_output_tokens} if is_groq else {"max_tokens": max_output_tokens}

        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=api_messages,
                tools=agent_tools,
                tool_choice="auto",
                temperature=0.3,
                **token_kwarg
            )

            if hasattr(response, 'usage') and response.usage:
                used = response.usage.total_tokens
                state.tokens_used += used
                state.tokens_by_agent[agent_name] = state.tokens_by_agent.get(agent_name, 0) + used
                print(f"    [TOKENS] {agent_name} used {used} this call ({state.tokens_by_agent[agent_name]} total for this agent)")

        except Exception as e:
            error_str = str(e)
            if "failed_generation" in error_str and "<function=" in error_str:
                print("    [SELF-HEAL] Caught malformed function call. Parsing manually...")
                func_name, func_args = extract_self_healed_call(error_str)

                if func_name and func_args is not None:
                    print(f"    [SELF-HEAL] Manually executing: {func_name}({str(func_args)[:200]})")
                    try:
                        observation, finished = dispatch_tool_call(state, agent_name, agent_def, func_name, func_args)
                    except Exception as dispatch_err:
                        observation, finished = f"ERROR while executing self-healed call: {dispatch_err}", False

                    healed_id = f"healed_call_{step}"
                    state.messages.append({"role": "assistant", "content": None, "tool_calls": [{"id": healed_id, "type": "function", "function": {"name": func_name, "arguments": json.dumps(func_args)}}]})
                    state.messages.append({"role": "tool", "name": func_name, "content": str(observation), "tool_call_id": healed_id})
                    if finished: return state.to_dict()
                    continue
                else:
                    state.add_artifact("final_answer", f"⚠️ Swarm API Error (could not self-heal malformed call): {e}")
                    return state.to_dict()
            elif "tool_use_failed" in error_str or "did not match schema" in error_str:
                # This is the 400 from the screenshot: a clean schema-validation
                # rejection with no <function=> wrapper, so the block above
                # never matches it. Give the model specific, correctable
                # feedback and let it retry instead of aborting the run.
                func_name, message = extract_tool_validation_error(error_str)
                print(f"    [SELF-HEAL] Tool call rejected for '{func_name}': {message[:200]}")
                feedback = (
                    f"Your previous call to `{func_name}` was rejected by the API: {message} "
                    f"Re-check that tool's required parameters and call it again with all of "
                    f"them filled in correctly -- do not invent parameter names that don't exist."
                )
                state.messages.append({"role": "user", "content": feedback})
                continue
            elif "429" in error_str or "rate_limit" in error_str.lower():
                state.add_artifact("final_answer", "⚠️ **Swarm is at Capacity:** High traffic. Please wait 60 seconds or upgrade to Pro for priority."); return state.to_dict()
            state.add_artifact("final_answer", f"⚠️ Swarm API Error: {e}"); return state.to_dict()

        choice = response.choices[0]
        if choice.finish_reason == "tool_calls":
            state.messages.append(choice.message)
            for tool_call in choice.message.tool_calls:
                try: func_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    state.messages.append({"role": "tool", "name": tool_call.function.name, "content": f"ERROR: Could not parse arguments as JSON: {tool_call.function.arguments!r}", "tool_call_id": tool_call.id}); continue
                func_name = tool_call.function.name
                print(f"    [ACTION] {func_name}({str(func_args)[:200]})")
                try:
                    observation, finished = dispatch_tool_call(state, agent_name, agent_def, func_name, func_args)
                except Exception as dispatch_err:
                    observation, finished = f"ERROR while executing tool: {dispatch_err}", False
                state.messages.append({"role": "tool", "name": func_name, "content": str(observation), "tool_call_id": tool_call.id})
                if finished: return state.to_dict()
        elif choice.finish_reason == "stop":
            content = choice.message.content or ""
            # fix: Apex_Strategist and Apex_Coder are terminal agents (empty
            # allowed_transitions) -- they have nowhere left to delegate to.
            # The old code always nagged "you must use a tool" even when a
            # terminal agent had already produced a perfectly good final
            # answer as plain content (which free-tier models do regularly,
            # since they don't always force a tool call). That nag loop is
            # exactly what produced the 20k-token cost in the screenshot:
            # the same large HTML response got repeated back into context
            # on every retry. Now we just accept the content directly.
            is_terminal_agent = len(agent_def["allowed_transitions"]) == 0
            if is_terminal_agent and content.strip():
                print(f"    [AUTO-ACCEPT] {agent_name} answered directly without a tool call; accepting it as the final answer.")
                state.add_artifact("final_answer", content)
                return state.to_dict()
            state.messages.append({"role": "assistant", "content": content})
            state.messages.append({"role": "user", "content": "You must use a tool to proceed. Delegate, save, or finish."})
        else: state.add_artifact("final_answer", f"⚠️ Swarm stopped unexpectedly (finish_reason='{choice.finish_reason}')."); break

    if "final_answer" not in state.artifacts: state.add_artifact("final_answer", "⚠️ Swarm exceeded maximum steps without finishing.")
    return state.to_dict()

# ==============================================================================
# 6. ENTRY POINT
# ==============================================================================
def run_swarm(user_prompt: str, tier: str = "free", max_output_tokens: int = 4096) -> dict:
    print(f"\n[SWARM v22.1] Query: {user_prompt[:60]}... (Tier: {tier} | Max Output: {max_output_tokens})")
    state = SwarmState(query=user_prompt)
    state.current_agent = "Master_Orchestrator"
    state.messages.append({"role": "user", "content": f"Client Request: {user_prompt}\n\nPlease delegate this to the appropriate specialist."})
    return execute_agent_loop(state, tier=tier, max_output_tokens=max_output_tokens)
