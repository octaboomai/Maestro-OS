import streamlit as st
import streamlit.components.v1 as components
import sys
import os
import re
import json
import datetime

sys.path.append(os.path.dirname(__file__))
import apex_engine
import dealscout_engine

# ─────────────────────────────────────────────────────────────────────────────
# 1. CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
# Neutral shell name -- this app now serves two different products, so it
# isn't really "Apex Swarm OS" or "DealScout" anymore. Easy one-line rename.
CONSOLE_NAME = "Apex Console"

ENGINES = {
    "apex": {
        "label": "⚡ General (Apex OS)",
        "tagline": "Research, strategy, or build an app -- open-ended agentic work.",
        "placeholder": "Ask for Research, Strategy, or Build an App...",
        "module": apex_engine,
    },
    "dealscout": {
        "label": "🎯 Market Intelligence (DealScout)",
        "tagline": "Real-time opportunity identification & market/competitor analysis.",
        "placeholder": "e.g. Give me a deep dive on Ola Electric vs Ather Energy...",
        "module": dealscout_engine,
    },
}

# Usage limits shared across BOTH engines, since they're one app now -- a
# Long Context run costs roughly the same either way, so one shared pool is
# simpler than tracking two separate quotas the user has to keep track of.
RESET_WINDOW_HOURS = 4
LONG_CONTEXT_LIMIT = 3
SHORT_CONTEXT_LIMIT = 4
LONG_CONTEXT_MAX_TOKENS = 8192
SHORT_CONTEXT_MAX_TOKENS = 1536  # a bit higher than Apex's solo default --
                                  # DealScout's Strategy_Associate has more
                                  # required sections to fill even on a
                                  # "quick" pass

st.set_page_config(page_title=CONSOLE_NAME, layout="centered", initial_sidebar_state="expanded")

# ─────────────────────────────────────────────────────────────────────────────
# 2. STYLING (DealScout's shell, kept as the one shared theme; Apex content
#    renders as themed Markdown inside the same cards rather than each
#    product carrying its own competing visual identity)
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

#MainMenu, header, footer, [data-testid="stToolbar"] { display: none !important; }
html, body, [data-testid="stAppViewContainer"] { background: #020617 !important; font-family: 'Inter', sans-serif !important; color: #f8fafc; }
[data-testid="stMain"] > div { max-width: 850px !important; margin: 0 auto !important; padding: 2rem !important; }

.agency-header { display: flex; align-items: center; gap: 12px; padding: 20px 0; border-bottom: 1px solid #1e293b; margin-bottom: 24px; }
.agency-logo { background: linear-gradient(135deg, #34d399, #06b6d4); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 28px; font-weight: 700; }
.agency-sub { color: #94a3b8; font-size: 14px; font-weight: 500; }

.ds-card { background: #0f172a; border: 1px solid #1e293b; border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.2); }
.ds-card-title { display: flex; align-items: center; gap: 8px; color: #f8fafc; font-size: 18px; font-weight: 600; border-bottom: 1px solid #1e293b; padding-bottom: 12px; margin-bottom: 16px; margin-top: 0;}
.ds-icon { font-size: 20px; }
.ds-text { color: #cbd5e1; font-size: 16px; line-height: 1.7; margin: 0; }

.ds-metric-row { display: flex; justify-content: space-between; align-items: center; background: #020617; border: 1px solid #1e293b; border-radius: 8px; padding: 12px 16px; margin-bottom: 10px; }
.ds-metric-label { color: #94a3b8; font-weight: 500; font-size: 14px; }
.ds-metric-value { color: #f8fafc; font-weight: 700; font-size: 18px; display: flex; gap: 12px; align-items: center;}
.ds-trend-up { color: #34d399; font-size: 14px; }
.ds-trend-down { color: #f43f5e; font-size: 14px; }
.ds-trend-flat { color: #94a3b8; font-size: 14px; }

.ds-risk-row { display: flex; justify-content: space-between; align-items: flex-start; padding: 12px 0; border-bottom: 1px solid #1e293b; }
.ds-risk-row:last-child { border-bottom: none; }
.ds-risk-title { color: #e2e8f0; font-weight: 500; font-size: 15px; }
.ds-badge { padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; letter-spacing: 0.5px; text-transform: uppercase; }
.ds-badge-high { background: rgba(244, 63, 94, 0.15); color: #fb7185; border: 1px solid rgba(244, 63, 94, 0.3); box-shadow: 0 0 10px rgba(244, 63, 94, 0.2); }
.ds-badge-medium { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }
.ds-badge-low { background: rgba(148, 163, 184, 0.15); color: #cbd5e1; border: 1px solid rgba(148, 163, 184, 0.3); }

/* Apex's Markdown output, themed to match the same shell (teal accent
   instead of Apex's old amber, so both engines feel like one product) */
[data-testid="stMarkdownContainer"] p { font-size: 15px !important; line-height: 1.75 !important; color: #cbd5e1 !important; }
[data-testid="stMarkdownContainer"] h2 { font-size: 13px !important; font-weight: 700 !important; color: #34d399 !important; text-transform: uppercase; letter-spacing: 0.8px; margin-top: 24px !important; margin-bottom: 10px !important; padding-top: 16px !important; border-top: 1px solid #1e293b !important; }
[data-testid="stMarkdownContainer"] h2:first-child { margin-top: 0 !important; padding-top: 0 !important; border-top: none !important; }
[data-testid="stMarkdownContainer"] strong { color: #f8fafc !important; font-weight: 600 !important; }
[data-testid="stMarkdownContainer"] li { color: #cbd5e1 !important; line-height: 1.75 !important; }
[data-testid="stMarkdownContainer"] table { border-collapse: collapse !important; width: 100% !important; margin: 8px 0 16px 0 !important; }
[data-testid="stMarkdownContainer"] th { background: #0f172a !important; color: #34d399 !important; text-transform: uppercase; font-size: 11px !important; padding: 8px 12px !important; border-bottom: 1px solid #1e293b !important; text-align: left !important; }
[data-testid="stMarkdownContainer"] td { padding: 8px 12px !important; border-bottom: 1px solid #1e293b !important; color: #cbd5e1 !important; font-size: 14px !important; }

.route-pill { display: inline-flex; align-items: center; gap: 6px; background: #0f172a; border: 1px solid #1e293b; border-radius: 6px; padding: 4px 12px; font-size: 11px; color: #94a3b8; margin-bottom: 14px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px; }
.route-dot { width: 6px; height: 6px; border-radius: 50%; background: #34d399; display: inline-block; }

[data-testid="stChatInput"] { background: #0f172a !important; border: 1px solid #334155 !important; }
[data-testid="stChatInput"] textarea { color: #f8fafc !important; }
.stButton>button { background: #34d399 !important; color: #020617 !important; border: none !important; font-weight: 600 !important; border-radius: 8px !important; }
div[role="radiogroup"] { gap: 10px !important; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# 3. RENDERING -- APEX (Markdown / generated HTML apps)
# ─────────────────────────────────────────────────────────────────────────────
def extract_html(content: str):
    if not content:
        return None
    fence_match = re.search(r"```html\s*\n?(.*?)```", content, re.DOTALL | re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()
    generic_fence = re.search(r"```\s*\n?(<!DOCTYPE html.*?)```", content, re.DOTALL | re.IGNORECASE)
    if generic_fence:
        return generic_fence.group(1).strip()
    doctype_match = re.search(r"<!DOCTYPE html.*", content, re.DOTALL | re.IGNORECASE)
    if doctype_match:
        return doctype_match.group(0).strip()
    html_tag_match = re.search(r"<html[\s>].*", content, re.DOTALL | re.IGNORECASE)
    if html_tag_match:
        return html_tag_match.group(0).strip()
    return None


def render_apex_output(content: str):
    html_code = extract_html(content)
    if html_code:
        with st.expander("💻 View Generated Code"):
            st.code(html_code, language="html")
        components.html(html_code, height=500, scrolling=True)
        return
    st.markdown(content)

# ─────────────────────────────────────────────────────────────────────────────
# 4. RENDERING -- DEALSCOUT (structured JSON dashboard)
# ─────────────────────────────────────────────────────────────────────────────
def extract_json_from_text(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
    return None


def render_dealscout_dashboard(data: dict):
    html = f"""
    <div style="margin-bottom: 12px;">
        <h2 style="color: #f8fafc; font-size: 24px; font-weight: 700; margin-bottom: 20px;">
            {data.get('title', 'Intelligence Report')}
        </h2>
        <div class="ds-card">
            <h3 class="ds-card-title"><span class="ds-icon">💼</span> Executive Bottom Line</h3>
            <p class="ds-text">{data.get('executive_summary', 'No summary provided.')}</p>
        </div>
    """
    html += '<div style="display: flex; gap: 20px; flex-wrap: wrap;">'

    html += '<div class="ds-card" style="flex: 1; min-width: 280px;"><h3 class="ds-card-title"><span class="ds-icon">📊</span> Key Data Points</h3>'
    metrics = data.get('market_data', [])
    if not isinstance(metrics, list):
        metrics = []
    for m in metrics:
        if isinstance(m, dict):
            label = str(m.get('label', 'Metric'))
            val = str(m.get('value', 'N/A'))
            trend = str(m.get('trend') or '')
            trend_class = "ds-trend-up" if "+" in trend else "ds-trend-down" if "-" in trend else "ds-trend-flat"
            html += f"""
            <div class="ds-metric-row">
                <span class="ds-metric-label">{label}</span>
                <span class="ds-metric-value">{val} <span class="{trend_class}">{trend}</span></span>
            </div>
            """
        else:
            html += f'<div class="ds-metric-row"><span class="ds-metric-label">{m}</span></div>'
    html += '</div>'

    html += '<div class="ds-card" style="flex: 1; min-width: 280px;"><h3 class="ds-card-title"><span class="ds-icon">🚨</span> Risk Matrix</h3>'
    risks = data.get('risk_matrix', [])
    if not isinstance(risks, list):
        risks = []
    for r in risks:
        if isinstance(r, dict):
            risk_text = str(r.get('risk', 'Unknown Risk'))
            sev = str(r.get('severity') or 'Medium')
            badge_class = "ds-badge-high" if sev.lower() == "high" else "ds-badge-low" if sev.lower() == "low" else "ds-badge-medium"
            html += f"""
            <div class="ds-risk-row">
                <span class="ds-risk-title">{risk_text}</span>
                <span class="ds-badge {badge_class}">{sev.upper()}</span>
            </div>
            """
        else:
            html += f'<div class="ds-risk-row"><span class="ds-risk-title">{r}</span></div>'
    html += '</div>'
    html += '</div>'

    # Strip newlines + leading whitespace: 4+ spaces of indentation after a
    # blank line makes Streamlit's markdown parser treat the rest as a
    # literal code block instead of HTML.
    html = re.sub(r'\n\s*', '', html)
    st.markdown(html, unsafe_allow_html=True)


def render_dealscout_output(content: str):
    parsed = extract_json_from_text(content)
    if parsed and isinstance(parsed, dict):
        render_dealscout_dashboard(parsed)
    else:
        st.warning("Data format error: showing raw output instead of the structured dashboard.")
        st.markdown(content)

# ─────────────────────────────────────────────────────────────────────────────
# 5. USAGE LIMITS (shared across both engines)
# ─────────────────────────────────────────────────────────────────────────────
def _init_usage_state():
    if "usage_window_start" not in st.session_state:
        st.session_state.usage_window_start = datetime.datetime.now()
        st.session_state.long_used = 0
        st.session_state.short_used = 0


def _maybe_reset_usage_window():
    elapsed = datetime.datetime.now() - st.session_state.usage_window_start
    if elapsed >= datetime.timedelta(hours=RESET_WINDOW_HOURS):
        st.session_state.usage_window_start = datetime.datetime.now()
        st.session_state.long_used = 0
        st.session_state.short_used = 0


def _time_until_reset() -> datetime.timedelta:
    elapsed = datetime.datetime.now() - st.session_state.usage_window_start
    remaining = datetime.timedelta(hours=RESET_WINDOW_HOURS) - elapsed
    return remaining if remaining.total_seconds() > 0 else datetime.timedelta(0)


_init_usage_state()
_maybe_reset_usage_window()

# ─────────────────────────────────────────────────────────────────────────────
# 5b. STARTUP KEY CHECK -- fails loudly and clearly instead of letting a
#     missing secret surface later as a confusing low-level SDK error
# ─────────────────────────────────────────────────────────────────────────────
_groq_set = bool(os.environ.get("GROQ_API_KEY"))
_nvidia_set = bool(os.environ.get("NVIDIA_API_KEY"))
if not _groq_set and not _nvidia_set:
    st.error(
        "No API keys configured. Add `GROQ_API_KEY` and/or `NVIDIA_API_KEY` "
        "as root-level secrets (locally in `.streamlit/secrets.toml`, or in "
        "your Community Cloud app's Settings → Secrets), then rerun/redeploy."
    )
    st.stop()
elif not _groq_set:
    st.warning("`GROQ_API_KEY` is not set — Short Context requests will fail until it's added.")
elif not _nvidia_set:
    st.warning("`NVIDIA_API_KEY` is not set — Long Context requests will fail until it's added.")

# ─────────────────────────────────────────────────────────────────────────────
# 6. SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("<h3 style='color: #f8fafc; font-weight: 600;'>📊 Usage This Window</h3>", unsafe_allow_html=True)
    long_left = max(0, LONG_CONTEXT_LIMIT - st.session_state.long_used)
    short_left = max(0, SHORT_CONTEXT_LIMIT - st.session_state.short_used)
    st.markdown(f"🧠 **Long Context:** {long_left} / {LONG_CONTEXT_LIMIT} left")
    st.markdown(f"⚡ **Short Context:** {short_left} / {SHORT_CONTEXT_LIMIT} left")
    remaining = _time_until_reset()
    hrs, rem_secs = divmod(int(remaining.total_seconds()), 3600)
    mins = rem_secs // 60
    st.caption(f"🔁 Resets in {hrs}h {mins}m · shared across both modes")
    st.divider()
    st.caption("**Long Context** = full token budget on the stronger model tier. **Short Context** = fast, lightweight pass.")

# ─────────────────────────────────────────────────────────────────────────────
# 7. MAIN DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="agency-header">
    <div style="font-size: 32px;">⚡</div>
    <div>
        <div class="agency-logo">{CONSOLE_NAME}</div>
        <div class="agency-sub">Two swarms, one workspace</div>
    </div>
</div>
""", unsafe_allow_html=True)

if "engine_choice" not in st.session_state:
    st.session_state.engine_choice = "apex"

engine_label = st.radio(
    "Specialist",
    options=[ENGINES["apex"]["label"], ENGINES["dealscout"]["label"]],
    horizontal=True,
    label_visibility="collapsed",
    key="engine_radio",
)
engine_key = "apex" if engine_label == ENGINES["apex"]["label"] else "dealscout"
st.session_state.engine_choice = engine_key
st.caption(ENGINES[engine_key]["tagline"])

if "history" not in st.session_state:
    st.session_state.history = []

for item in st.session_state.history:
    with st.chat_message("user"):
        st.markdown(item["prompt"])
    with st.chat_message("assistant"):
        if item.get("route"):
            route_text = " ➔ ".join(item["route"])
            st.markdown(f'<div class="route-pill"><span class="route-dot"></span>{item.get("mode_label","")} · {route_text} · {item.get("tokens",0)} tokens</div>', unsafe_allow_html=True)
        if item["engine"] == "apex":
            render_apex_output(item["output"])
        else:
            render_dealscout_output(item["output"])

# ─────────────────────────────────────────────────────────────────────────────
# 8. MODE SELECTOR + CHAT INPUT
# ─────────────────────────────────────────────────────────────────────────────
mode_choice = st.radio(
    "Response depth",
    options=["⚡ Short Context", "🧠 Long Context"],
    horizontal=True,
    key="context_mode",
    label_visibility="collapsed",
)
is_long = mode_choice.startswith("🧠")

if prompt := st.chat_input(ENGINES[engine_key]["placeholder"]):
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        _maybe_reset_usage_window()

        if is_long and st.session_state.long_used >= LONG_CONTEXT_LIMIT:
            remaining = _time_until_reset()
            hrs, rem_secs = divmod(int(remaining.total_seconds()), 3600)
            mins = rem_secs // 60
            st.error(f"🚫 You've used all {LONG_CONTEXT_LIMIT} Long Context requests for this window. Resets in {hrs}h {mins}m, or switch to Short Context.")
            st.stop()
        if (not is_long) and st.session_state.short_used >= SHORT_CONTEXT_LIMIT:
            remaining = _time_until_reset()
            hrs, rem_secs = divmod(int(remaining.total_seconds()), 3600)
            mins = rem_secs // 60
            st.error(f"🚫 You've used all {SHORT_CONTEXT_LIMIT} Short Context requests for this window. Resets in {hrs}h {mins}m.")
            st.stop()

        tier = "pro" if is_long else "free"
        mode_label = "🧠 Long" if is_long else "⚡ Short"
        max_output_tokens = LONG_CONTEXT_MAX_TOKENS if is_long else SHORT_CONTEXT_MAX_TOKENS

        with st.spinner(f"{ENGINES[engine_key]['label']} is working..."):
            try:
                if engine_key == "apex":
                    result = apex_engine.run_swarm(prompt, tier=tier, max_output_tokens=max_output_tokens)
                else:
                    result = dealscout_engine.run_swarm(prompt, tier=tier, max_output_tokens=max_output_tokens)
            except Exception as e:
                result = {"plan": [], "final_answer": f"⚠️ Critical Error: `{e}`", "tokens_used": 0}

        if is_long:
            st.session_state.long_used += 1
        else:
            st.session_state.short_used += 1

        tokens_consumed = result.get("tokens_used", 0)
        clean_route = list(dict.fromkeys(result.get("plan", [])))

        if clean_route:
            route_text = " ➔ ".join(clean_route)
            st.markdown(f'<div class="route-pill"><span class="route-dot"></span>{mode_label} · {route_text} · {tokens_consumed} tokens</div>', unsafe_allow_html=True)

        final_output = result.get("final_answer", "Swarm failed.")

        if engine_key == "apex":
            render_apex_output(final_output)
        else:
            render_dealscout_output(final_output)

        st.session_state.history.append({
            "engine": engine_key,
            "prompt": prompt,
            "output": final_output,
            "route": clean_route,
            "mode_label": mode_label,
            "tokens": tokens_consumed,
        })
