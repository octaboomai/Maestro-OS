import os
import json
import re
from datetime import datetime
from typing import List, Dict
from openai import OpenAI  # Using OpenAI SDK for both Groq and NVIDIA NIM

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

print("[*] Initializing DealScout Swarm™ (v19.1 - Stability Pass)...")

# ==============================================================================
# 1. DYNAMIC AI BRAIN ROUTER (Verified Sovereign Models)
# ==============================================================================
# Groq decommissioned llama3-8b-8192 on 08/30/2025, then deprecated
# llama-3.3-70b-versatile on 06/17/2026 (shutdown 08/16/2026) -- already
# migrated straight to the GPT-OSS models. Pro-tier strings are NVIDIA NIM
# catalog IDs (build.nvidia.com), not OpenRouter.
AGENT_MODELS = {
    "Engagement_Manager": {
        "free": "groq/openai/gpt-oss-20b",
        "pro": "mistralai/mistral-small-4-119b-2603"
    },
    "Market_Intelligence_Analyst": {
        "free": "groq/openai/gpt-oss-120b",
        "pro": "qwen/qwen3-next-80b-a3b-instruct"
    },
    "Strategy_Associate": {
        "free": "groq/openai/gpt-oss-120b",
        "pro": "meta/llama-3.1-70b-instruct"
    },
    "Risk_Director": {
        "free": "groq/openai/gpt-oss-120b",
        "pro": "meta/llama-3.1-70b-instruct"
    },
    "Managing_Partner": {
        "free": "groq/openai/gpt-oss-20b",
        "pro": "mistralai/mistral-small-4-119b-2603"
    }
}

def get_client_for_model(tier: str, agent_name: str):
    """Returns (client, actual_model_id, is_groq)."""
    model_name = AGENT_MODELS.get(agent_name, {}).get(tier, "groq/openai/gpt-oss-120b")
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
# 2. SHARED WORKSPACE
# ==============================================================================
class SwarmState:
    def __init__(self, query: str):
        self.query = query
        self.plan = []
        self.artifacts = {}
        self.messages = []
        self.current_agent = None
        self.total_tokens = 0
        self.tokens_by_agent = {}
        self.has_searched = False  # enforced before Market_Intelligence_Analyst can delegate

    def add_artifact(self, key: str, value: str):
        self.artifacts[key] = value

    def get_artifact(self, key: str) -> str:
        return self.artifacts.get(key, "No data available.")

    def to_dict(self):
        return {
            "plan": self.plan,
            "final_answer": self.artifacts.get("final_answer", "Error: No final answer generated."),
            "history": self.messages,
            "tokens_used": self.total_tokens,
            "tokens_by_agent": self.tokens_by_agent
        }

# ==============================================================================
# 3. AGENT DEFINITIONS (B2B CONSULTING PERSONAS)
# ==============================================================================
AGENT_DEFS = {
    "Engagement_Manager": {
        "system_prompt": "You are the Engagement Manager at a top-tier consulting firm. Analyze the client's request. If they need market research, competitor analysis, or deal evaluation, delegate to Market_Intelligence_Analyst. Otherwise, delegate to Strategy_Associate. Be professional and concise.",
        "tools": ["delegate_to_agent"],
        "allowed_transitions": ["Market_Intelligence_Analyst", "Strategy_Associate"]
    },
    "Market_Intelligence_Analyst": {
        "system_prompt": (
            "You are a Senior Market Intelligence Analyst. Your job is to gather raw, actionable intelligence and hand off to the Strategy_Associate.\n"
            "WORKFLOW:\n"
            "1. Call `tool_web_search` at least once -- always, even if you think you already know the answer. "
            "Find competitor data, market sizing, or recent news. Prefer the most recent figures available — explicitly include the current year in at least one of your search queries, and avoid settling for outdated annual figures if a more recent quarter/update exists.\n"
            "2. CRITICAL: Extract specific company names, financial figures, and market shares. DO NOT output generic fluff like 'the market is growing'. Find the exact data points, and note the date/period each figure is from (e.g. 'Q3 FY26') so stale data isn't presented as current.\n"
            "3. If search FAILS, save an artifact stating: 'LIVE SEARCH FAILED. Strategy_Associate must rely on provided documents or inform client that live data is unavailable.'\n"
            "4. Save detailed findings using `save_artifact` with key 'market_intel'.\n"
            "5. Delegate to 'Strategy_Associate'.\n"
            "NEVER delegate to yourself."
        ),
        "tools": ["tool_web_search", "save_artifact", "delegate_to_agent"],
        "allowed_transitions": ["Strategy_Associate"]
    },
    "Strategy_Associate": {
        "system_prompt": (
            "You are a Strategy Associate. You write high-value executive memos.\n"
            "WORKFLOW:\n"
            "1. Read 'market_intel' from workspace using `read_artifact`.\n"
            "2. Write a comprehensive strategy draft. Tone: Objective, analytical, direct. No fluff.\n"
            "3. REQUIRED FORMAT (No exceptions):\n\n"
            "🎯 EXECUTIVE BOTTOM LINE:\n(2-3 sentences stating the exact strategic outcome or risk)\n\n"
            "🧠 STRATEGIC CONTEXT:\n(3-4 sentences on market positioning, implications, or competitive landscape)\n\n"
            "🚨 RISK FACTORS:\n- (Specific risk 1)\n- (Specific risk 2)\n\n"
            "📊 KEY DATA POINTS:\n- (Specific metric/fact 1)\n- (Specific metric/fact 2)\n\n"
            "4. Save draft using `save_artifact` with key 'strategy_draft'.\n"
            "5. Delegate to 'Risk_Director'.\n"
            "NEVER delegate to yourself."
        ),
        "tools": ["read_artifact", "save_artifact", "delegate_to_agent"],
        "allowed_transitions": ["Risk_Director"]
    },
    "Risk_Director": {
        "system_prompt": (
            "You are the Risk Director. You are the bad cop. Your job is to stress-test the Strategy_Associate's draft.\n"
            "WORKFLOW:\n"
            "1. Read 'strategy_draft' from workspace using `read_artifact`.\n"
            "CHECKS:\n"
            "- Is it too generic? (e.g., 'AI is growing'). If yes, REJECT and delegate back to Strategy_Associate with note: 'Too generic. Require specific competitor names and financial metrics.'\n"
            "- Are there missing risks? If yes, REJECT and delegate back to Strategy_Associate.\n"
            "- Did it follow the exact format? If no, REJECT.\n"
            "If it is sharp, accurate, and executive-ready, delegate to Managing_Partner. DO NOT delegate to yourself."
        ),
        "tools": ["read_artifact", "save_artifact", "delegate_to_agent"],
        "allowed_transitions": ["Strategy_Associate", "Managing_Partner"]
    },
    "Managing_Partner": {
        "system_prompt": (
            "You are the Managing Partner. Read the 'strategy_draft' using `read_artifact`.\n"
            "Convert it into a polished executive report and output it as a SINGLE valid JSON object "
            "(no markdown code fences, no commentary before or after) with EXACTLY this shape:\n"
            "{\n"
            '  "title": "<short report title>",\n'
            '  "executive_summary": "<2-3 sentence bottom line, plain text>",\n'
            '  "market_data": [{"label": "<metric name>", "value": "<metric value>", "trend": "<e.g. +12% or -3%, or empty string>"}],\n'
            '  "risk_matrix": [{"risk": "<risk description>", "severity": "High" or "Medium" or "Low"}]\n'
            "}\n"
            "Pull the metrics and risks directly from the strategy_draft — do not invent data that isn't there. "
            "Save ONLY that JSON string as 'final_answer' using `save_artifact`. Then use the `finish_task` tool to end the engagement. "
            "DO NOT change the core strategic insights, just restructure them into the JSON shape above."
        ),
        "tools": ["read_artifact", "save_artifact", "finish_task"],
        "allowed_transitions": []
    }
}

# ==============================================================================
# 4. TOOL IMPLEMENTATIONS
# ==============================================================================
def tool_web_search(query: str) -> str:
    clean_query = query.replace("top 3", "").strip()
    if not clean_query:
        clean_query = "market analysis"
    current_year = datetime.now().year
    if str(current_year) not in clean_query and str(current_year - 1) not in clean_query:
        clean_query = f"{clean_query} {current_year}"
    print(f"    [TOOL_EXEC] Searching: {clean_query!r}")
    try:
        with DDGS(timeout=10) as ddgs:
            results = list(ddgs.text(clean_query, region="in-en", safesearch="off", timelimit="y", max_results=5))
        if not results:
            with DDGS(timeout=10) as ddgs:
                results = list(ddgs.text(clean_query, region="wt-wt", safesearch="off", max_results=5))
        if not results:
            return "LIVE SEARCH FAILED: No results found."

        def _trim(text: str, limit: int = 280) -> str:
            text = " ".join(text.split())
            return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"

        return "\n".join(f"[{i+1}] {r.get('title', '')}: {_trim(r.get('body', ''))}" for i, r in enumerate(results))
    except Exception as e:
        return f"LIVE SEARCH FAILED: Search engine error ({e})."

TOOL_SCHEMAS = [
    {"type": "function", "function": {"name": "delegate_to_agent", "description": "Hand off the current task to another agent.", "parameters": {"type": "object", "properties": {"agent_name": {"type": "string", "enum": list(AGENT_DEFS.keys())}, "message": {"type": "string"}}, "required": ["agent_name", "message"]}}},
    {"type": "function", "function": {"name": "tool_web_search", "description": "Search the web for market data, competitor info, or news.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "save_artifact", "description": "Save work to the shared workspace.", "parameters": {"type": "object", "properties": {"key": {"type": "string", "enum": ["market_intel", "strategy_draft", "final_answer"]}, "content": {"type": "string"}}, "required": ["key", "content"]}}},
    {"type": "function", "function": {"name": "read_artifact", "description": "Read an artifact from the workspace.", "parameters": {"type": "object", "properties": {"key": {"type": "string", "enum": ["market_intel", "strategy_draft"]}}, "required": ["key"]}}},
    {"type": "function", "function": {"name": "finish_task", "description": "End the swarm process.", "parameters": {"type": "object", "properties": {}}}}
]

def get_tool_schemas_for_agent(agent_name: str) -> list:
    allowed = set(AGENT_DEFS[agent_name]["tools"])
    return [s for s in TOOL_SCHEMAS if s["function"]["name"] in allowed]

def dispatch_tool_call(state: SwarmState, agent_name: str, agent_def: dict, func_name: str, func_args: dict):
    """
    fix: every argument now read with .get() + validated instead of raw
    dict indexing (func_args["key"]). A tool call with a missing/misnamed
    argument used to raise an uncaught KeyError and kill the whole turn;
    now it returns a descriptive error the model can act on instead.
    """
    if func_name not in agent_def["tools"]:
        return (f"ERROR: {agent_name} is not permitted to use '{func_name}'. "
                f"Permitted tools: {agent_def['tools']}."), False

    if func_name == "delegate_to_agent":
        next_agent = func_args.get("agent_name")
        if not next_agent:
            return "ERROR: delegate_to_agent call is missing the required 'agent_name' argument.", False
        if next_agent == agent_name:
            return (f"CRITICAL ERROR: You cannot delegate to yourself! You are {agent_name}. "
                     f"Delegate to: {agent_def['allowed_transitions']}."), False
        if next_agent not in agent_def["allowed_transitions"]:
            return (f"ERROR: You cannot delegate to {next_agent}. "
                     f"Delegate to: {agent_def['allowed_transitions']}."), False
        # fix: same root cause as Apex's "9426 tokens, one sentence" bug --
        # the prompt told Market_Intelligence_Analyst to search, but nothing
        # enforced it. This makes it impossible to skip straight to
        # delegating without at least attempting a live search first.
        if agent_name == "Market_Intelligence_Analyst" and not state.has_searched:
            return "ERROR: You must call tool_web_search at least once before delegating to Strategy_Associate. Search first, then delegate.", False
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
        state.has_searched = True
        return tool_web_search(query), False

    elif func_name == "finish_task":
        if "final_answer" not in state.artifacts:
            state.add_artifact("final_answer", "Task finished, but no final answer was saved.")
        return "Task finished.", True

    return f"Error: Tool {func_name} not found.", False

# ==============================================================================
# 4b. SELF-HEAL HELPERS (ported from apex_engine.py, same Groq failure modes)
# ==============================================================================
def extract_self_healed_call(error_str: str):
    """
    Handles malformed <function=NAME>{...}</function> calls. Uses
    json.JSONDecoder.raw_decode instead of a non-greedy regex so nested
    braces inside the arguments (common in any generated structured text)
    don't truncate the match early.
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
    Handles Groq's OTHER malformed-tool-call shape: a clean tool_use_failed
    schema-validation rejection with no <function=...> wrapper at all.
    There's nothing safe to repair in the arguments here (the model
    invented or omitted parameters), so this just pulls out which tool was
    attempted and why, so the model can be told exactly what to fix.
    """
    name_match = re.search(r'"name":\s*"(\w+)"', error_str)
    func_name = name_match.group(1) if name_match else None
    msg_match = re.search(r"'message':\s*[\"'](.+?)[\"'],\s*'type'", error_str, re.DOTALL)
    message = msg_match.group(1) if msg_match else error_str
    return func_name, message

# ==============================================================================
# 5. THE AGENTIC EXECUTION LOOP (Self-Healing + Dynamic Model Loading)
# ==============================================================================
def execute_agent_loop(state: SwarmState, tier: str = "free", max_output_tokens: int = 2000, max_steps: int = 30) -> dict:
    step = 0
    while step < max_steps:
        step += 1
        agent_name = state.current_agent
        agent_def = AGENT_DEFS[agent_name]

        client, model_name, is_groq = get_client_for_model(tier, agent_name)
        print(f"\n[STEP {step}] Executing Agent: {agent_name} | Model: {model_name} | Tier: {tier}")

        state.plan.append(agent_name)
        api_messages = [{"role": "system", "content": agent_def["system_prompt"]}] + state.messages
        agent_tools = get_tool_schemas_for_agent(agent_name)

        # fix: Groq's current reasoning-capable lineup (openai/gpt-oss-*)
        # expects max_completion_tokens, not the deprecated max_tokens.
        # NVIDIA NIM's endpoint still expects max_tokens. Pick per-provider
        # instead of hardcoding one that silently breaks the other.
        token_kwarg = {"max_completion_tokens": max_output_tokens} if is_groq else {"max_tokens": max_output_tokens}

        try:
            response = client.chat.completions.create(
                model=model_name, messages=api_messages, tools=agent_tools,
                tool_choice="auto", temperature=0.3,
                parallel_tool_calls=False,
                **token_kwarg
            )
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
                    state.messages.append({
                        "role": "assistant", "content": None,
                        "tool_calls": [{"id": healed_id, "type": "function",
                                        "function": {"name": func_name, "arguments": json.dumps(func_args)}}]
                    })
                    state.messages.append({"role": "tool", "name": func_name, "content": str(observation), "tool_call_id": healed_id})
                    if finished:
                        return state.to_dict()
                    continue
                else:
                    state.add_artifact("final_answer", f"⚠️ Swarm API Error (could not self-heal malformed call): {e}")
                    return state.to_dict()
            elif "tool_use_failed" in error_str or "did not match schema" in error_str:
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
                state.add_artifact("final_answer", "⚠️ **Swarm is at Capacity:** Servers experiencing high traffic. Please wait 60 seconds and try again.")
                return state.to_dict()
            state.add_artifact("final_answer", f"⚠️ Swarm API Error: {e}")
            return state.to_dict()

        choice = response.choices[0]
        if getattr(response, "usage", None):
            used = getattr(response.usage, "total_tokens", 0) or 0
            state.total_tokens += used
            state.tokens_by_agent[agent_name] = state.tokens_by_agent.get(agent_name, 0) + used
            print(f"    [TOKENS] {agent_name} used {used} this call ({state.tokens_by_agent[agent_name]} total for this agent)")

        if choice.finish_reason == "tool_calls":
            state.messages.append(choice.message)
            for tool_call in choice.message.tool_calls:
                try:
                    func_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    state.messages.append({
                        "role": "tool", "name": tool_call.function.name,
                        "content": f"ERROR: Could not parse arguments as JSON: {tool_call.function.arguments!r}",
                        "tool_call_id": tool_call.id
                    })
                    continue
                func_name = tool_call.function.name
                print(f"    [ACTION] {func_name}({str(func_args)[:200]})")
                try:
                    observation, finished = dispatch_tool_call(state, agent_name, agent_def, func_name, func_args)
                except Exception as dispatch_err:
                    observation, finished = f"ERROR while executing tool: {dispatch_err}", False
                state.messages.append({"role": "tool", "name": func_name, "content": str(observation), "tool_call_id": tool_call.id})
                if finished:
                    return state.to_dict()

        elif choice.finish_reason == "stop":
            content = choice.message.content or ""
            # fix: Managing_Partner is the terminal agent (empty
            # allowed_transitions). If it writes its JSON directly as
            # content instead of going through save_artifact, the old code
            # just nagged it to "use a tool" and re-sent the same content
            # back into context every retry -- wasting tokens on a loop
            # instead of just accepting a perfectly usable answer.
            is_terminal_agent = len(agent_def["allowed_transitions"]) == 0
            if is_terminal_agent and content.strip():
                print(f"    [AUTO-ACCEPT] {agent_name} answered directly without a tool call; accepting it as the final answer.")
                state.add_artifact("final_answer", content)
                return state.to_dict()
            state.messages.append({"role": "assistant", "content": content})
            state.messages.append({"role": "user", "content": "You must use a tool to proceed. Delegate, save, or finish."})
        else:
            state.add_artifact("final_answer", f"⚠️ Swarm stopped unexpectedly (finish_reason='{choice.finish_reason}').")
            break

    if "final_answer" not in state.artifacts:
        state.add_artifact("final_answer", "⚠️ Swarm exceeded maximum steps without finishing.")
    return state.to_dict()

# ==============================================================================
# 6. ENTRY POINT
# ==============================================================================
def run_swarm(user_prompt: str, tier: str = "free", max_output_tokens: int = 2000) -> dict:
    print(f"\n[SWARM v19.1] Query: {user_prompt[:60]}... (Tier: {tier} | Max Output: {max_output_tokens})")
    state = SwarmState(query=user_prompt)
    state.current_agent = "Engagement_Manager"
    state.messages.append({"role": "user", "content": f"Client Request: {user_prompt}\n\nPlease delegate this to the appropriate consultant."})
    return execute_agent_loop(state, tier=tier, max_output_tokens=max_output_tokens)
