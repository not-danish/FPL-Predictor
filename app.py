import uuid
import json
import logging
import pandas as pd
import streamlit as st
from langchain_core.messages import AIMessage, ToolMessage

# ── App-level logger (shares fpl_agent.log with agent.py) ────────────────────
_app_log = logging.getLogger("fpl_agent")
if not _app_log.handlers:
    _fh = logging.FileHandler("fpl_agent.log", encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)-5s] %(message)s",
                                        datefmt="%Y-%m-%d %H:%M:%S"))
    _app_log.addHandler(_fh)
    _app_log.setLevel(logging.DEBUG)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FPL AI Assistant",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
}
[data-testid="stSidebar"] * { color: #e0e0e0 !important; }
[data-testid="stSidebar"] .stTextInput input,
[data-testid="stSidebar"] .stNumberInput input {
    background: #0f3460;
    border: 1px solid #00d4aa;
    color: #fff !important;
    border-radius: 6px;
}
[data-testid="stChatInput"] textarea { border-color: #00d4aa !important; }
.fpl-header {
    background: linear-gradient(90deg, #1a1a2e, #0f3460);
    padding: 1rem 1.5rem;
    border-radius: 10px;
    margin-bottom: 1rem;
    border-left: 4px solid #00d4aa;
}
/* Live feed rows */
.feed-agent  { font-weight:700; color:#00d4aa; font-size:0.85rem; margin-top:8px; }
.feed-tool   { font-size:0.8rem; color:#f0a500; padding-left:12px; }
.feed-result { font-size:0.75rem; color:#888; padding-left:12px; font-family:monospace; }
.feed-text   { font-size:0.82rem; color:#ccc; padding-left:12px; }
</style>
""", unsafe_allow_html=True)

# ── Load model (cached across reruns) ─────────────────────────────────────────
@st.cache_resource(show_spinner="Loading FPL agent (this takes ~30s on first run)...")
def load_model():
    from agent import build_graph
    return build_graph()

model = load_model()

# ── Session state ──────────────────────────────────────────────────────────────
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    # each entry: {"role", "content", "log": [{"type", "agent", "text"}, ...]}
    st.session_state.messages = []

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚽ FPL AI Assistant")
    st.markdown("---")
    st.markdown("### Your FPL Details")
    user_id = st.number_input("Team ID", min_value=1, value=872062, step=1)
    league_id = st.number_input("League ID", min_value=1, value=1698003, step=1)
    st.markdown("---")
    st.markdown("### Conversation")
    if st.button("🔄 New Conversation", use_container_width=True):
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()
    st.markdown(f"<small>Thread: `{st.session_state.thread_id[:8]}...`</small>",
                unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("### Quick Prompts")
    for prompt in [
        "Recommend transfers for this gameweek",
        "Suggest my starting lineup",
        "Who should I captain?",
        "Should I use a chip this GW?",
        "Analyse my rivals' teams",
        "Show upcoming fixtures analysis",
    ]:
        if st.button(prompt, use_container_width=True, key=f"qp_{prompt}"):
            st.session_state["quick_prompt"] = prompt
            st.rerun()
    st.markdown("---")
    st.markdown("<small style='color:#666'>Powered by LangGraph · OpenRouter</small>",
                unsafe_allow_html=True)

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="fpl-header">
    <h2 style="margin:0;color:#00d4aa">⚽ FPL AI Assistant</h2>
    <p style="margin:0;color:#aaa;font-size:0.9rem">
        Multi-agent analysis · Transfers · Lineup · Captaincy · Chips
    </p>
</div>
""", unsafe_allow_html=True)

AGENT_LABELS = {
    "supervisor": "🧠 Supervisor",
    "researcher": "🔍 Researcher",
    "rival_analyst": "👥 Rival Analyst",
    "fixture_analyst": "📅 Fixture Analyst",
    "chips_strategist": "🃏 Chips Strategist",
    "squad_builder": "🏗️ Squad Builder",
    "transfers_agent": "🔄 Transfers Planner",
    "outgoing_recommender": "📤 Outgoing Picks",
    "incoming_recommender": "📥 Incoming Picks",
    "constraint_validator": "✅ Constraint Check",
    "lineup_selector": "📋 Lineup Selector",
    "captaincy_selector": "👑 Captaincy Selector",
    "final_reviewer": "📝 Final Review",
}

# ── Squad pitch visualization ─────────────────────────────────────────────────
_TEAM_COLORS = {
    "Arsenal": "#EF0107", "Aston Villa": "#670E36", "Bournemouth": "#DA291C",
    "Brentford": "#e30613", "Brighton": "#0057B8", "Chelsea": "#034694",
    "Crystal Palace": "#1B458F", "Everton": "#003399", "Fulham": "#CC0000",
    "Ipswich": "#0044A9", "Leicester": "#003090", "Liverpool": "#C8102E",
    "Man City": "#6CABDD", "Man Utd": "#DA291C", "Newcastle": "#241F20",
    "Nott'm Forest": "#DD0000", "Southampton": "#D71920", "Tottenham": "#132257",
    "West Ham": "#7A263A", "Wolves": "#FDB913",
}

def _squad_pitch_html(user_id: int) -> str:
    """Return HTML for a pitch-style squad visualization, or empty string on failure."""
    try:
        from agent import _cached_get, data as fpl_data

        events_df = pd.DataFrame(fpl_data["events"])
        cur = events_df[events_df["is_current"] == True]
        if cur.empty:
            return ""
        current_gw = int(cur.iloc[0]["id"])

        url = f"https://fantasy.premierleague.com/api/entry/{user_id}/event/{current_gw}/picks/"
        raw = json.loads(_cached_get(url))
        if "picks" not in raw:
            return ""

        elements = {e["id"]: e for e in fpl_data["elements"]}
        teams    = {t["id"]: t["name"] for t in fpl_data["teams"]}
        pos_map  = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}

        players = []
        for p in raw["picks"]:
            el = elements.get(p["element"])
            if not el:
                continue
            team_name = teams.get(el["team"], "")
            players.append({
                "slot":       p["position"],
                "name":       el.get("web_name", el["second_name"]),
                "team":       team_name,
                "pos":        pos_map.get(el["element_type"], "UNK"),
                "is_captain": p["is_captain"],
                "is_vc":      p["is_vice_captain"],
                "color":      _TEAM_COLORS.get(team_name, "#546e7a"),
                "is_starter": p["position"] <= 11,
            })

        starters = sorted([p for p in players if p["is_starter"]], key=lambda x: x["slot"])
        bench    = sorted([p for p in players if not p["is_starter"]], key=lambda x: x["slot"])

        fwd_row = [p for p in starters if p["pos"] == "FWD"]
        mid_row = [p for p in starters if p["pos"] == "MID"]
        def_row = [p for p in starters if p["pos"] == "DEF"]
        gkp_row = [p for p in starters if p["pos"] == "GKP"]

        def _card(p, w="66px", fs="0.72rem"):
            badge = ""
            if p["is_captain"]:
                badge = ('<span style="position:absolute;top:-5px;right:-5px;background:#f0a500;'
                         'color:#000;border-radius:50%;width:15px;height:15px;font-size:0.55rem;'
                         'font-weight:bold;display:flex;align-items:center;justify-content:center;'
                         'z-index:2;">C</span>')
            elif p["is_vc"]:
                badge = ('<span style="position:absolute;top:-5px;right:-5px;background:#aaaaaa;'
                         'color:#000;border-radius:50%;width:15px;height:15px;font-size:0.55rem;'
                         'font-weight:bold;display:flex;align-items:center;justify-content:center;'
                         'z-index:2;">V</span>')
            return (
                f'<div style="position:relative;width:{w};flex-shrink:0;text-align:center;">'
                f'{badge}'
                f'<div style="width:34px;height:34px;border-radius:50%;background:{p["color"]};'
                f'border:2px solid rgba(255,255,255,0.55);margin:0 auto 3px;display:flex;'
                f'align-items:center;justify-content:center;">'
                f'<span style="color:#fff;font-size:0.55rem;font-weight:bold;">{p["pos"]}</span></div>'
                f'<div style="background:rgba(0,0,0,0.62);border-radius:4px;padding:2px 3px;">'
                f'<div style="font-size:{fs};color:#fff;font-weight:600;white-space:nowrap;'
                f'overflow:hidden;text-overflow:ellipsis;">{p["name"]}</div>'
                f'<div style="font-size:0.58rem;color:#bbb;white-space:nowrap;overflow:hidden;'
                f'text-overflow:ellipsis;">{p["team"]}</div>'
                f'</div></div>'
            )

        def _row(plist, gap="8px"):
            if not plist:
                return ""
            return (f'<div style="display:flex;justify-content:center;gap:{gap};margin-bottom:14px;">'
                    + "".join(_card(p) for p in plist) + "</div>")

        pitch = (
            '<div style="background:linear-gradient(180deg,#1b5e20 0%,#2e7d32 20%,'
            '#388e3c 50%,#2e7d32 80%,#1b5e20 100%);border:3px solid #fff;'
            'border-radius:12px;padding:16px 8px 8px;position:relative;overflow:hidden;">'
            '<div style="position:absolute;left:8%;right:8%;top:50%;height:2px;'
            'background:rgba(255,255,255,0.18);pointer-events:none;"></div>'
            '<div style="position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);'
            'width:72px;height:72px;border-radius:50%;border:2px solid rgba(255,255,255,0.15);'
            'pointer-events:none;"></div>'
            '<div style="position:relative;z-index:1;">'
            + _row(fwd_row) + _row(mid_row) + _row(def_row) + _row(gkp_row)
            + '</div></div>'
        )

        bench_cards = "".join(_card(p, w="58px", fs="0.65rem") for p in bench)
        bench_html = (
            '<div style="background:#0d1f0d;border:1px solid #2a4a2a;border-radius:8px;'
            'padding:10px 8px;margin-top:6px;display:flex;align-items:center;gap:10px;'
            'flex-wrap:wrap;justify-content:center;">'
            '<span style="color:#556;font-size:0.65rem;letter-spacing:1px;margin-right:4px;">'
            'BENCH</span>'
            + bench_cards + '</div>'
        )

        return f'<div style="margin-top:16px;">{pitch}{bench_html}</div>'

    except Exception:
        return ""


# ── Helper: render a saved log entry ──────────────────────────────────────────
def render_log(log: list):
    """Re-render a saved activity log (used for chat history replay)."""
    for entry in log:
        t = entry["type"]
        agent = AGENT_LABELS.get(entry.get("agent", ""), entry.get("agent", ""))
        if t == "agent_start":
            st.markdown(f'<div class="feed-agent">▶ {agent}</div>', unsafe_allow_html=True)
        elif t == "tool_call":
            args_str = ", ".join(f"{k}={v}" for k, v in entry.get("args", {}).items())
            st.markdown(f'<div class="feed-tool">🔧 {entry["name"]}({args_str})</div>',
                        unsafe_allow_html=True)
        elif t == "tool_result":
            preview = entry.get("content", "")[:300].replace("\n", " ")
            st.markdown(f'<div class="feed-result">↳ {preview}…</div>', unsafe_allow_html=True)
        elif t == "agent_text":
            st.markdown(f'<div class="feed-text">{entry["content"]}</div>',
                        unsafe_allow_html=True)

# ── Render existing chat history ───────────────────────────────────────────────
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            log = msg.get("log", [])
            if log:
                with st.expander(f"🤖 Agent activity ({len(log)} events)", expanded=False):
                    render_log(log)
        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            pitch = _squad_pitch_html(user_id)
            if pitch:
                st.markdown(pitch, unsafe_allow_html=True)

# ── Handle input ───────────────────────────────────────────────────────────────
user_input = st.chat_input("Ask about transfers, lineup, captaincy, chips...")
if "quick_prompt" in st.session_state:
    user_input = st.session_state.pop("quick_prompt")

if user_input:
    _app_log.info("=== NEW QUERY (thread=%s) ===", st.session_state.thread_id[:8])
    _app_log.info("USER: %s", user_input)

    full_message = (
        f"{user_input}\n\n"
        f"My FPL team ID is {user_id} and my league ID is {league_id}."
    )

    with st.chat_message("user"):
        st.markdown(user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})

    config = {
        "configurable": {"thread_id": st.session_state.thread_id},
        "recursion_limit": 150,
    }

    from agent import clear_tool_cache, _cached_get, data as fpl_data
    clear_tool_cache()

    # Pre-fetch basic context so researcher skips redundant tool calls
    def _prefetch_context():
        lines = []
        try:
            events_df = pd.DataFrame(fpl_data["events"])
            cur = events_df[events_df["is_current"] == True]
            nxt = events_df[events_df["is_next"] == True]
            current_gw = int(cur.iloc[0]["id"]) if not cur.empty else None
            next_gw = int(nxt.iloc[0]["id"]) if not nxt.empty else current_gw
            if current_gw:
                lines.append(f"Current GW: {current_gw}. Next GW: {next_gw}.")
                url = f"https://fantasy.premierleague.com/api/entry/{user_id}/event/{current_gw}/picks/"
                raw = json.loads(_cached_get(url))
                if "entry_history" in raw:
                    bank = raw["entry_history"].get("bank", 0) / 10
                    lines.append(f"User ITB: £{bank}m.")
        except Exception:
            pass
        if lines:
            return "\n\n---\n**Pre-fetched context (do not re-fetch):**\n" + "\n".join(lines)
        return ""

    full_message_with_context = full_message + _prefetch_context()

    # ── Live streaming ─────────────────────────────────────────────────────────
    log = []          # persisted activity log
    final_output = ""
    last_agent = None

    # Internal plumbing nodes — no messages to display, skip them entirely
    _INTERNAL_NODES = {
        "update_pipeline", "update_chip",
        "update_transfers", "update_validation",
        "set_squad_path", "set_incoming_path", "sync_analysis",
        "compress_research", "compress_rival", "compress_fixtures",
        "compress_chips", "compress_squad", "compress_transfers",
        "compress_outgoing", "compress_incoming", "compress_validation",
        "compress_lineup", "compress_captaincy",
    }

    with st.chat_message("assistant"):
        with st.status("🤖 Agents working...", expanded=True) as status:
            try:
                for chunk in model.stream(
                    {"messages": [{"role": "user", "content": full_message_with_context}]},
                    config,
                ):
                    for node, node_data in chunk.items():
                        if node.startswith("__") or not isinstance(node_data, dict) or node in _INTERNAL_NODES:
                            continue

                        label = AGENT_LABELS.get(node, node)

                        # ── New agent ──────────────────────────────────────────
                        if node != last_agent:
                            last_agent = node
                            _app_log.info("AGENT  %s", node)
                            st.markdown(f'<div class="feed-agent">▶ {label}</div>',
                                        unsafe_allow_html=True)
                            log.append({"type": "agent_start", "agent": node})
                            status.update(label=f"⚙ {label}...")

                        for msg in node_data.get("messages", []):

                            # ── Tool calls (agent decided to call a tool) ──────
                            if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                                for tc in msg.tool_calls:
                                    args_str = ", ".join(
                                        f"{k}={repr(v)}" for k, v in tc.get("args", {}).items()
                                    )
                                    _app_log.info("  TOOL  %s(%s)", tc["name"], args_str)
                                    st.markdown(
                                        f'<div class="feed-tool">🔧 {tc["name"]}({args_str})</div>',
                                        unsafe_allow_html=True,
                                    )
                                    log.append({
                                        "type": "tool_call",
                                        "agent": node,
                                        "name": tc["name"],
                                        "args": tc.get("args", {}),
                                    })

                            # ── Tool results ───────────────────────────────────
                            elif isinstance(msg, ToolMessage):
                                raw = msg.content if isinstance(msg.content, str) else str(msg.content)
                                preview = raw[:300].replace("\n", " ")
                                ellipsis = "…" if len(raw) > 300 else ""
                                _app_log.debug("  RESULT %s…", raw[:200].replace("\n", " "))
                                st.markdown(
                                    f'<div class="feed-result">↳ {preview}{ellipsis}</div>',
                                    unsafe_allow_html=True,
                                )
                                log.append({
                                    "type": "tool_result",
                                    "agent": node,
                                    "content": raw,
                                })

                            # ── Agent final text ───────────────────────────────
                            elif isinstance(msg, AIMessage):
                                content = msg.content if isinstance(msg.content, str) else ""
                                if not content.strip():
                                    continue
                                _app_log.info("  TEXT  [%s] %s…", node, content[:120].replace("\n", " "))
                                st.markdown(
                                    f'<div class="feed-text">{content}</div>',
                                    unsafe_allow_html=True,
                                )
                                log.append({
                                    "type": "agent_text",
                                    "agent": node,
                                    "content": content,
                                })
                                if node == "final_reviewer":
                                    final_output = content

            except Exception as e:
                import traceback
                _app_log.error("AGENT ERROR: %s\n%s", e, traceback.format_exc())
                status.update(label="❌ Error", state="error")
                st.error(f"Agent error: {e}")
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"Something went wrong: {e}",
                    "log": log,
                })
                st.stop()

            status.update(label="✅ Done", state="complete", expanded=False)

        # ── Final response shown prominently below the status box ──────────────
        if not final_output and log:
            # Fall back to last agent text if final_reviewer didn't run
            for entry in reversed(log):
                if entry["type"] == "agent_text":
                    final_output = entry["content"]
                    break

        if final_output:
            st.markdown(final_output)

        pitch = _squad_pitch_html(user_id)
        if pitch:
            st.markdown(pitch, unsafe_allow_html=True)

    st.session_state.messages.append({
        "role": "assistant",
        "content": final_output or "No response generated.",
        "log": log,
    })
