import re
import uuid
import json
import logging
import pandas as pd
import streamlit as st
from langchain_core.messages import AIMessage, ToolMessage

# ── Logger ────────────────────────────────────────────────────────────────────
_app_log = logging.getLogger("fpl_agent")
if not _app_log.handlers:
    _fh = logging.FileHandler("fpl_agent.log", encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)-5s] %(message)s",
                                       datefmt="%Y-%m-%d %H:%M:%S"))
    _app_log.addHandler(_fh)
    _app_log.setLevel(logging.DEBUG)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FPL Advisor",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

*, *::before, *::after {
    font-family: 'Inter', -apple-system, system-ui, sans-serif !important;
    box-sizing: border-box;
}

::-webkit-scrollbar { width: 3px; height: 3px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.07); border-radius: 2px; }

.stApp { background: #08080c !important; }
.block-container { max-width: 800px !important; padding: 0 1.5rem 5rem !important; margin: 0 auto !important; }
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }
header[data-testid="stHeader"] { background: transparent !important; height: 0 !important; min-height: 0 !important; }

/* ── Sidebar ─────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: #09090e !important;
    border-right: 1px solid rgba(255,255,255,0.06) !important;
}
[data-testid="stSidebar"] > div:first-child { padding: 1.25rem 1rem 1.5rem !important; }
[data-testid="stSidebar"] * { color: #8b8c9e !important; }
[data-testid="stSidebar"] hr { border: none !important; border-top: 1px solid rgba(255,255,255,0.06) !important; margin: 1rem 0 !important; }
[data-testid="stSidebar"] label {
    font-size: 0.64rem !important; font-weight: 600 !important;
    letter-spacing: 0.09em !important; text-transform: uppercase !important;
    color: #2e2e3a !important; margin-bottom: 3px !important;
}
[data-testid="stSidebar"] .stNumberInput input,
[data-testid="stSidebar"] .stTextInput input {
    background: rgba(255,255,255,0.03) !important;
    border: 1px solid rgba(255,255,255,0.09) !important;
    color: #e8e8f0 !important; border-radius: 8px !important;
    font-size: 0.82rem !important; height: 34px !important;
    padding: 0 10px !important; transition: border-color 0.15s !important;
}
[data-testid="stSidebar"] .stNumberInput input:focus,
[data-testid="stSidebar"] .stTextInput input:focus {
    border-color: rgba(0,232,122,0.35) !important;
    box-shadow: 0 0 0 3px rgba(0,232,122,0.07) !important; outline: none !important;
}
[data-testid="stSidebar"] .stButton > button {
    background: transparent !important; border: none !important;
    color: #52525e !important; border-radius: 7px !important;
    width: 100% !important; padding: 7px 10px !important;
    font-size: 0.82rem !important; font-weight: 500 !important;
    text-align: left !important; transition: background 0.1s, color 0.1s !important;
    cursor: pointer !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,255,255,0.04) !important; color: #e8e8f0 !important;
}
[data-testid="stSidebar"] .stButton > button:focus { box-shadow: none !important; }

/* ── Chat input ───────────────────────────────────── */
[data-testid="stChatInput"] > div {
    background: #0e0e15 !important;
    border: 1px solid rgba(255,255,255,0.09) !important;
    border-radius: 14px !important;
    transition: border-color 0.15s, box-shadow 0.15s !important;
}
[data-testid="stChatInput"] > div:focus-within {
    border-color: rgba(0,232,122,0.3) !important;
    box-shadow: 0 0 0 3px rgba(0,232,122,0.06) !important;
}
[data-testid="stChatInput"] textarea { color: #f0f0f5 !important; font-size: 0.875rem !important; }
[data-testid="stChatInput"] textarea::placeholder { color: #3a3a48 !important; }
[data-testid="stChatInput"] button svg { color: #00e87a !important; fill: #00e87a !important; }

/* ── Chat messages ────────────────────────────────── */
[data-testid="stChatMessage"] { background: transparent !important; border: none !important; padding: 0.2rem 0 !important; }
[data-testid="stChatMessage"] p { color: #dddde8 !important; font-size: 0.875rem !important; line-height: 1.78 !important; }
[data-testid="stChatMessage"] li { color: #dddde8 !important; font-size: 0.875rem !important; line-height: 1.72 !important; }
[data-testid="stChatMessage"] strong { color: #ffffff !important; font-weight: 600 !important; }
[data-testid="stChatMessage"] h1,
[data-testid="stChatMessage"] h2,
[data-testid="stChatMessage"] h3 { color: #ffffff !important; font-weight: 700 !important; letter-spacing: -0.03em !important; margin-top: 1.2em !important; }
[data-testid="stChatMessage"] code {
    background: rgba(0,232,122,0.08) !important; color: #6ee7b7 !important;
    border-radius: 5px !important; padding: 1px 6px !important;
    font-size: 0.79em !important; font-family: 'Fira Code', 'JetBrains Mono', monospace !important;
}
[data-testid="stChatMessage"] pre {
    background: #0e0e15 !important; border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: 10px !important; padding: 12px 16px !important;
}
[data-testid="stChatMessage"] hr { border: none !important; border-top: 1px solid rgba(255,255,255,0.07) !important; margin: 12px 0 !important; }
[data-testid="stChatMessage"] table { border-collapse: collapse !important; width: 100% !important; font-size: 0.8rem !important; border: 1px solid rgba(255,255,255,0.07) !important; border-radius: 10px !important; overflow: hidden !important; margin: 8px 0 !important; }
[data-testid="stChatMessage"] th { background: rgba(0,232,122,0.06) !important; color: #00e87a !important; font-size: 0.64rem !important; font-weight: 700 !important; letter-spacing: 0.08em !important; text-transform: uppercase !important; padding: 10px 14px !important; border-bottom: 1px solid rgba(0,232,122,0.1) !important; }
[data-testid="stChatMessage"] td { color: #9494a8 !important; padding: 8px 14px !important; border-bottom: 1px solid rgba(255,255,255,0.04) !important; }
[data-testid="stChatMessage"] tr:last-child td { border-bottom: none !important; }
[data-testid="stChatMessage"] tr:hover td { background: rgba(255,255,255,0.02) !important; }

/* ── Status + Expander ────────────────────────────── */
[data-testid="stStatus"] { background: #0d0d13 !important; border: 1px solid rgba(255,255,255,0.06) !important; border-radius: 10px !important; }
[data-testid="stExpander"] { background: #0d0d13 !important; border: 1px solid rgba(255,255,255,0.06) !important; border-radius: 8px !important; }
[data-testid="stExpander"] details summary { font-size: 0.72rem !important; color: #4a4a5a !important; font-weight: 500 !important; }
[data-testid="stExpander"] details summary:hover { color: #6b6b7e !important; }

/* ── Agent feed ───────────────────────────────────── */
.feed-agent { font-size: 0.66rem; font-weight: 700; color: #00e87a; letter-spacing: 0.1em; text-transform: uppercase; padding: 8px 0 1px; border-top: 1px solid rgba(255,255,255,0.04); margin-top: 4px; }
.feed-agent:first-child { border-top: none; margin-top: 0; padding-top: 1px; }
.feed-tool { font-size: 0.7rem; color: #e08847; padding: 2px 0 1px 12px; font-family: 'JetBrains Mono', 'Fira Code', monospace !important; }
.feed-result { font-size: 0.64rem; color: #2e2e3a; padding: 1px 0 0 12px; font-family: 'JetBrains Mono', 'Fira Code', monospace !important; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.feed-text { font-size: 0.74rem; color: #52525e; padding: 3px 0 2px 12px; line-height: 1.6; }

/* ── Onboarding ───────────────────────────────────── */
.onboard [data-testid="stFormSubmitButton"] button {
    background: #00e87a !important; color: #040408 !important;
    border: none !important; border-radius: 10px !important;
    height: 44px !important; font-size: 0.875rem !important;
    font-weight: 700 !important; letter-spacing: -0.01em !important;
    transition: opacity 0.15s !important; width: 100% !important;
}
.onboard [data-testid="stFormSubmitButton"] button:hover { opacity: 0.85 !important; }
.onboard [data-testid="stTextInputRootElement"] input {
    background: rgba(255,255,255,0.03) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    color: #f0f0f5 !important; border-radius: 10px !important;
    font-size: 0.88rem !important; height: 44px !important; padding: 0 14px !important;
    transition: border-color 0.15s !important;
}
.onboard [data-testid="stTextInputRootElement"] input:focus {
    border-color: rgba(0,232,122,0.4) !important;
    box-shadow: 0 0 0 3px rgba(0,232,122,0.07) !important; outline: none !important;
}
.onboard label { font-size: 0.69rem !important; font-weight: 600 !important; letter-spacing: 0.08em !important; text-transform: uppercase !important; color: #6b6b7e !important; }

/* ── Team bar ─────────────────────────────────────── */
.team-bar-btn button {
    background: transparent !important; border: 1px solid rgba(255,255,255,0.07) !important;
    color: #3a3a48 !important; border-radius: 7px !important;
    font-size: 0.72rem !important; font-weight: 500 !important;
    padding: 5px 12px !important; height: auto !important;
    transition: all 0.12s !important;
}
.team-bar-btn button:hover { border-color: rgba(255,255,255,0.14) !important; color: #8b8c9e !important; }
.team-bar-btn button:focus { box-shadow: none !important; }

/* ── Empty state suggestion cards ─────────────────── */
.suggest-card [data-testid="stButton"] button {
    background: #0d0d14 !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
    color: #8b8c9e !important; border-radius: 12px !important;
    padding: 16px 18px !important; height: auto !important;
    min-height: 68px !important; width: 100% !important;
    text-align: left !important; font-size: 0.84rem !important;
    font-weight: 500 !important; line-height: 1.5 !important;
    transition: all 0.18s ease !important; cursor: pointer !important;
    letter-spacing: -0.01em !important;
}
.suggest-card [data-testid="stButton"] button:hover {
    background: #111119 !important;
    border-color: rgba(0,232,122,0.22) !important;
    color: #f0f0f5 !important;
    box-shadow: 0 4px 20px rgba(0,0,0,0.5) !important;
    transform: translateY(-1px) !important;
}
.suggest-card [data-testid="stButton"] button:focus { box-shadow: none !important; }

/* ── Clarification pills ──────────────────────────── */
[data-testid="stPillsInput"] {
    background: transparent !important; border: none !important; padding: 0 !important;
}
[data-testid="stPillsInput"] > div { gap: 6px !important; flex-wrap: wrap !important; }
[data-testid="stPillsInput"] button {
    background: #111119 !important;
    border: 1px solid rgba(255,255,255,0.09) !important;
    color: #8b8c9e !important; border-radius: 20px !important;
    font-size: 0.79rem !important; font-weight: 500 !important;
    padding: 5px 14px !important; transition: all 0.15s !important;
    white-space: nowrap !important;
}
[data-testid="stPillsInput"] button:hover {
    border-color: rgba(0,232,122,0.3) !important; color: #00e87a !important;
    background: rgba(0,232,122,0.06) !important;
}
[data-testid="stPillsInput"] button[aria-selected="true"] {
    background: rgba(0,232,122,0.1) !important;
    border-color: #00e87a !important; color: #00e87a !important; font-weight: 600 !important;
}
[data-testid="stPillsInput"] label { display: none !important; }

/* ── Clarification action buttons ─────────────────── */
.clarify-go [data-testid="stButton"] button {
    background: #00e87a !important; color: #040408 !important;
    border: none !important; border-radius: 9px !important;
    height: 40px !important; font-size: 0.84rem !important;
    font-weight: 700 !important; letter-spacing: -0.01em !important;
    transition: opacity 0.15s !important; width: 100% !important;
}
.clarify-go [data-testid="stButton"] button:hover { opacity: 0.85 !important; }
.clarify-go [data-testid="stButton"] button:disabled {
    background: #1a1a24 !important; color: #3a3a48 !important; opacity: 1 !important;
}
.clarify-go [data-testid="stButton"] button:focus { box-shadow: none !important; }

.clarify-skip [data-testid="stButton"] button {
    background: transparent !important; border: 1px solid rgba(255,255,255,0.08) !important;
    color: #4a4a5a !important; border-radius: 9px !important;
    height: 40px !important; font-size: 0.8rem !important; font-weight: 500 !important;
    width: 100% !important; transition: all 0.15s !important;
}
.clarify-skip [data-testid="stButton"] button:hover {
    border-color: rgba(255,255,255,0.15) !important; color: #8b8c9e !important;
}
.clarify-skip [data-testid="stButton"] button:focus { box-shadow: none !important; }
</style>
""", unsafe_allow_html=True)

# ── Model (cached) ─────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner="Loading FPL agents...")
def load_model():
    from agent import build_graph
    return build_graph()

model = load_model()

# ── Session state ──────────────────────────────────────────────────────────────
_defaults = {
    "thread_id":           None,
    "messages":            [],
    "user_id":             None,
    "league_id":           None,
    "team_name":           None,
    "manager_name":        None,
    "pending_agent_input": None,   # enriched query ready to run through agents
}
for _k, _v in _defaults.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

if st.session_state.thread_id is None:
    st.session_state.thread_id = str(uuid.uuid4())

# ── Onboarding ─────────────────────────────────────────────────────────────────
if not st.session_state.user_id:
    st.markdown("""<style>
    [data-testid="stSidebar"] { display: none !important; }
    .block-container { max-width: 460px !important; padding-top: 7vh !important; }
    </style>""", unsafe_allow_html=True)

    st.markdown("""
    <div style="text-align:center; padding: 0 0 2.5rem;">
        <div style="width:60px;height:60px;background:#00e87a;border-radius:16px;
                    display:inline-flex;align-items:center;justify-content:center;
                    font-size:1.7rem;margin-bottom:1.4rem;
                    box-shadow:0 0 40px rgba(0,232,122,0.2),0 0 0 1px rgba(0,232,122,0.15);">⚽</div>
        <div style="font-size:1.6rem;font-weight:800;color:#f0f0f5;
                    letter-spacing:-0.045em;line-height:1.1;margin-bottom:0.55rem;">FPL AI Advisor</div>
        <div style="font-size:0.875rem;color:#4a4a5a;line-height:1.72;max-width:300px;margin:0 auto;">
            Connect your FPL team for personalised transfer advice,
            lineup picks, captaincy tips and chip strategy.
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="onboard">', unsafe_allow_html=True)
    with st.form("onboard_form", border=False):
        uid_str = st.text_input("Team ID", placeholder="e.g. 872062",
                                help="The number in your FPL URL: fantasy.premierleague.com/entry/**123456**/transfers")
        lid_str = st.text_input("Mini-league ID  (optional)", placeholder="e.g. 1698003",
                                help="fantasy.premierleague.com/leagues/**123456**/standings/c")
        submitted = st.form_submit_button("Connect my team →", use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("""
    <div style="text-align:center;margin-top:1.5rem;font-size:0.72rem;color:#2e2e3a;line-height:1.9;">
        Your IDs stay in this browser session only — never stored or shared.<br>
        Open FPL → Points — the number in the URL is your Team ID.
    </div>
    """, unsafe_allow_html=True)

    if submitted:
        uid_str = (uid_str or "").strip()
        if not uid_str.isdigit():
            st.error("Please enter a valid numeric Team ID (e.g. 872062).")
            st.stop()
        uid_val = int(uid_str)
        try:
            import requests as _rq
            _resp = _rq.get(f"https://fantasy.premierleague.com/api/entry/{uid_val}/",
                            timeout=8, headers={"User-Agent": "Mozilla/5.0"})
            _resp.raise_for_status()
            _edata = _resp.json()
            st.session_state.team_name    = _edata.get("name", f"Team {uid_val}")
            _first = _edata.get("player_first_name", "")
            _last  = _edata.get("player_last_name", "")
            st.session_state.manager_name = f"{_first} {_last}".strip()
        except Exception:
            st.session_state.team_name    = f"Team {uid_val}"
            st.session_state.manager_name = ""

        st.session_state.user_id   = uid_val
        lid_str = (lid_str or "").strip()
        st.session_state.league_id = int(lid_str) if lid_str.isdigit() else 0
        st.rerun()

    st.stop()

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="display:flex;align-items:center;gap:10px;padding-bottom:1.2rem;
                border-bottom:1px solid rgba(255,255,255,0.06);margin-bottom:1.1rem;">
        <div style="width:28px;height:28px;background:#00e87a;border-radius:7px;flex-shrink:0;
                    display:flex;align-items:center;justify-content:center;
                    box-shadow:0 0 14px rgba(0,232,122,0.2);">
            <span style="font-size:0.85rem;line-height:1;">⚽</span>
        </div>
        <div>
            <div style="font-size:0.88rem;font-weight:700;color:#f0f0f5;letter-spacing:-0.02em;line-height:1.2;">FPL Advisor</div>
            <div style="font-size:0.61rem;color:#2e2e3a;letter-spacing:0.07em;text-transform:uppercase;margin-top:1px;">AI · Multi-agent</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    _tname = st.session_state.team_name or "—"
    _mgr   = st.session_state.manager_name or ""
    _uid   = st.session_state.user_id or ""
    st.markdown(f"""
    <div style="padding:10px 12px;background:rgba(0,232,122,0.04);
                border:1px solid rgba(0,232,122,0.1);border-radius:9px;margin-bottom:8px;">
        <div style="font-size:0.79rem;font-weight:700;color:#f0f0f5;
                    letter-spacing:-0.02em;margin-bottom:2px;">{_tname}</div>
        <div style="font-size:0.67rem;color:#52525e;">{_mgr}</div>
        <div style="font-size:0.61rem;color:#2e2e3a;margin-top:3px;font-family:monospace;">
            ID {_uid}{f' · L {st.session_state.league_id}' if st.session_state.league_id else ''}
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown('<div class="team-bar-btn">', unsafe_allow_html=True)
    if st.button("Change team", use_container_width=True, key="change_team_sidebar"):
        for _k in ("user_id", "league_id", "team_name", "manager_name"):
            st.session_state[_k] = None
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div style="height:1px;background:rgba(255,255,255,0.06);margin:1rem 0;"></div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size:0.61rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#2a2a36;margin-bottom:6px;padding-left:2px;">Quick actions</div>', unsafe_allow_html=True)

    _QUICK_PROMPTS = [
        ("⚽  Recommend transfers",  "Recommend transfers for this gameweek"),
        ("📋  Suggest lineup",       "Suggest my starting lineup"),
        ("👑  Who to captain?",      "Who should I captain?"),
        ("🃏  Chip strategy",        "Should I use a chip this GW?"),
        ("👥  Analyse rivals",       "Analyse my rivals' teams"),
        ("📅  Fixture analysis",     "Show upcoming fixtures analysis"),
    ]
    for _lbl, _pmt in _QUICK_PROMPTS:
        if st.button(_lbl, use_container_width=True, key=f"qp_{_pmt}"):
            st.session_state["quick_prompt"] = _pmt
            st.rerun()

    st.markdown('<div style="height:1px;background:rgba(255,255,255,0.06);margin:1rem 0;"></div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size:0.61rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#2a2a36;margin-bottom:6px;padding-left:2px;">Session</div>', unsafe_allow_html=True)
    if st.button("New conversation", use_container_width=True):
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.messages  = []
        st.session_state.pending_agent_input = None
        # Clear any lingering clarification pill state
        for _k in list(st.session_state.keys()):
            if _k.startswith("clarify_pill_"):
                del st.session_state[_k]
        st.rerun()
    if st.button("Reload agents", use_container_width=True, help="Reload after code changes"):
        load_model.clear()
        st.rerun()

    st.markdown(
        f'<div style="font-size:0.63rem;color:#2a2a36;margin-top:8px;padding-left:2px;font-family:monospace;">'
        f'Session {st.session_state.thread_id[:8]}…</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div style="position:fixed;bottom:1.2rem;font-size:0.6rem;color:#1a1a22;letter-spacing:0.02em;">'
        'LangGraph · OpenRouter</div>',
        unsafe_allow_html=True,
    )

# ── Resolved IDs ───────────────────────────────────────────────────────────────
user_id   = st.session_state.user_id
league_id = st.session_state.league_id or 0

# ── Agent labels ───────────────────────────────────────────────────────────────
AGENT_LABELS = {
    "supervisor":           "Supervisor",
    "researcher":           "Researcher",
    "rival_analyst":        "Rival Analyst",
    "fixture_analyst":      "Fixture Analyst",
    "chips_strategist":     "Chips Strategist",
    "squad_builder":        "Squad Builder",
    "transfers_agent":      "Transfers Planner",
    "outgoing_recommender": "Outgoing Picks",
    "incoming_recommender": "Incoming Picks",
    "constraint_validator": "Constraint Check",
    "lineup_selector":      "Lineup Selector",
    "captaincy_selector":   "Captaincy Selector",
    "final_reviewer":       "Final Review",
}

# ── Clarifying questions definitions ───────────────────────────────────────────
_CLARIFY_DEFS = [
    {
        "triggers": ["transfer", "buy", "sell", "bring in", "let go", "who should i get"],
        "intro":    "A few quick questions to sharpen my transfer advice:",
        "questions": [
            {
                "id":      "free_transfers",
                "text":    "How many free transfers do you have?",
                "options": ["1 free transfer", "2 free transfers", "Not sure"],
            },
            {
                "id":      "hit_openness",
                "text":    "Are you open to taking a points hit?",
                "options": ["Yes, if it's worth it", "No hits this week", "Only for urgent issues"],
            },
        ],
    },
    {
        "triggers": ["captain", "armband", "vc", "vice captain", "captaincy", "who to captain"],
        "intro":    "One quick question before I give captaincy advice:",
        "questions": [
            {
                "id":      "captain_priority",
                "text":    "What's your captaincy priority this week?",
                "options": ["Highest ceiling (big haul)", "Safe consistent scorer", "Best upcoming fixture"],
            },
        ],
    },
    {
        "triggers": ["lineup", "starting 11", "starting xi", "who should start", "who should play", "my team this week"],
        "intro":    "One quick question before I pick your lineup:",
        "questions": [
            {
                "id":      "lineup_context",
                "text":    "Any concerns I should factor in?",
                "options": ["No — just optimise", "Injury doubts in my squad", "I want to protect GD"],
            },
        ],
    },
    {
        "triggers": ["chip", "wildcard", "free hit", "bench boost", "triple captain", "use a chip"],
        "intro":    "Tell me a bit more to sharpen my chip advice:",
        "questions": [
            {
                "id":      "chip_context",
                "text":    "What's driving your chip consideration?",
                "options": ["Upcoming double GW", "Squad injuries / crisis", "Long-term rank planning"],
            },
        ],
    },
]


def _get_clarify_cfg(query: str) -> dict | None:
    ql = query.lower()
    for cfg in _CLARIFY_DEFS:
        if any(t in ql for t in cfg["triggers"]):
            return cfg
    return None


def _build_enriched_query(base: str, questions: list, answers: dict) -> str:
    context = [
        f"• {q['text']}: {answers[q['id']]}"
        for q in questions
        if q["id"] in answers
    ]
    if not context:
        return base
    return base + "\n\n[User context — factor this into your advice]\n" + "\n".join(context)


# ── Squad pitch helpers ────────────────────────────────────────────────────────
_TEAM_COLORS = {
    "Arsenal": "#EF0107", "Aston Villa": "#670E36", "Bournemouth": "#DA291C",
    "Brentford": "#e30613", "Brighton": "#0057B8", "Chelsea": "#034694",
    "Crystal Palace": "#1B458F", "Everton": "#003399", "Fulham": "#CC0000",
    "Ipswich": "#0044A9", "Leicester": "#003090", "Liverpool": "#C8102E",
    "Man City": "#6CABDD", "Man Utd": "#DA291C", "Newcastle": "#241F20",
    "Nott'm Forest": "#DD0000", "Southampton": "#D71920", "Spurs": "#132257",
    "West Ham": "#7A263A", "Wolves": "#FDB913",
}


def _parse_transfers_from_output(text: str) -> list[dict]:
    pattern = r"(?:OUT|SELL)[:\s]+([A-Za-z\s\-\'\.]+?)(?:\s*\([^)]*\))?\s*[→\-]+\s*(?:IN|BUY)[:\s]+([A-Za-z\s\-\'\.]+?)(?:\s*\([^)]*\))?\s*(?:\n|$)"
    swaps = []
    for m in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
        out_name = m.group(1).strip()
        in_name  = m.group(2).strip()
        if out_name and in_name and out_name.lower() != in_name.lower():
            swaps.append({"out": out_name, "in": in_name})
    return swaps


_LINEUP_BLOCK_RE = re.compile(r"\[LINEUP_START\](.*?)\[LINEUP_END\]", re.DOTALL)


def _parse_lineup_block(text: str) -> dict | None:
    """Extract the machine-readable [LINEUP_START]...[LINEUP_END] block from agent output."""
    m = _LINEUP_BLOCK_RE.search(text)
    if not m:
        return None
    result: dict[str, list[str]] = {}
    for line in m.group(1).strip().splitlines():
        line = line.strip()
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip().upper()
        players = [p.strip() for p in val.split(",") if p.strip()]
        result[key] = players
    # Must have at least GKP + one of DEF/MID/FWD to be valid
    return result if ("GKP" in result and "DEF" in result) else None


def _strip_lineup_block(text: str) -> str:
    """Remove the [LINEUP_START]...[LINEUP_END] block from text before displaying."""
    return _LINEUP_BLOCK_RE.sub("", text).rstrip()


def _find_element_by_name(name: str, elements: list) -> dict | None:
    nl = name.lower().strip()
    for el in elements:
        wn = el.get("web_name", "").lower()
        fn = (el.get("first_name", "") + " " + el.get("second_name", "")).lower().strip()
        if nl == wn or nl == fn or nl in fn or nl in wn:
            return el
    return None


def _squad_pitch_html(uid: int, transfers: list[dict] | None = None,
                      lineup: dict | None = None) -> str:
    """Render a pitch visualization.

    If `lineup` (parsed from [LINEUP_START]...[LINEUP_END]) is provided, render
    the suggested lineup with the agent's formation and C/VC choices.
    Otherwise fall back to the user's current FPL picks from the API.
    """
    try:
        from agent import _cached_get, data as fpl_data

        elements  = fpl_data["elements"]
        teams_map = {t["id"]: t["name"] for t in fpl_data["teams"]}

        # ── SHARED: card renderer ──────────────────────────────────────────────
        def _make_card(name: str, team: str, is_cap: bool, is_vc: bool,
                       is_out: bool = False, is_in: bool = False, small: bool = False):
            sz  = "36px" if small else "42px"
            fs  = "0.6rem" if small else "0.65rem"
            tfs = "0.52rem" if small else "0.56rem"
            w   = "70px" if small else "82px"

            c_bg = _TEAM_COLORS.get(team, "#374151")
            ring = ""
            if is_out:
                c_bg = "#7f1d1d"
                ring = "box-shadow:0 0 0 2px #ef4444,0 0 10px rgba(239,68,68,0.4);"
            elif is_in:
                c_bg = "#14532d"
                ring = "box-shadow:0 0 0 2px #22c55e,0 0 10px rgba(34,197,94,0.4);"
            elif is_cap:
                ring = "box-shadow:0 0 0 2px #f59e0b;"
            elif is_vc:
                ring = "box-shadow:0 0 0 2px #6b7280;"

            badge = ""
            if is_cap:
                badge = ('<div style="position:absolute;top:-4px;right:-4px;width:14px;height:14px;'
                         'border-radius:50%;background:#f59e0b;color:#000;font-size:0.5rem;font-weight:800;'
                         'display:flex;align-items:center;justify-content:center;z-index:3;">C</div>')
            elif is_vc:
                badge = ('<div style="position:absolute;top:-4px;right:-4px;width:14px;height:14px;'
                         'border-radius:50%;background:#6b7280;color:#fff;font-size:0.5rem;font-weight:800;'
                         'display:flex;align-items:center;justify-content:center;z-index:3;">V</div>')

            initials = "".join(word[0].upper() for word in name.split()[:2])
            return (
                f'<div style="position:relative;width:{w};flex-shrink:0;text-align:center;">'
                f'<div style="position:relative;display:inline-block;">'
                f'{badge}'
                f'<div style="width:{sz};height:{sz};border-radius:50%;background:{c_bg};{ring}'
                f'margin:0 auto;display:flex;align-items:center;justify-content:center;">'
                f'<span style="color:rgba(255,255,255,0.9);font-size:0.55rem;font-weight:700;'
                f'letter-spacing:0.02em;">{initials}</span>'
                f'</div></div>'
                f'<div style="margin-top:4px;background:rgba(0,0,0,0.7);border:1px solid rgba(255,255,255,0.07);'
                f'border-radius:4px;padding:2px 4px;">'
                f'<div style="font-size:{fs};color:#f0f0f5;font-weight:600;white-space:nowrap;'
                f'overflow:hidden;text-overflow:ellipsis;">{name}</div>'
                f'<div style="font-size:{tfs};color:#52525e;white-space:nowrap;'
                f'overflow:hidden;text-overflow:ellipsis;">{team}</div>'
                f'</div></div>'
            )

        def _row(player_dicts, small=False):
            if not player_dicts:
                return ""
            cards = "".join(
                _make_card(p["name"], p["team"], p["is_cap"], p["is_vc"],
                           p.get("is_out", False), p.get("is_in", False), small)
                for p in player_dicts
            )
            return (
                '<div style="display:flex;justify-content:center;gap:10px;margin-bottom:18px;">'
                + cards + "</div>"
            )

        # ── Resolve player name → team colour ──────────────────────────────────
        def _resolve_player(name: str, is_cap: bool = False, is_vc: bool = False,
                            is_out: bool = False, is_in: bool = False) -> dict:
            el = _find_element_by_name(name, elements)
            team = teams_map.get(el["team"], "") if el else ""
            return {"name": name, "team": team,
                    "is_cap": is_cap, "is_vc": is_vc,
                    "is_out": is_out, "is_in": is_in}

        # ── PATH A: Suggested lineup from agent ────────────────────────────────
        if lineup:
            captain_name = (lineup.get("CAPTAIN") or [""])[0]
            vc_name      = (lineup.get("VC") or [""])[0]
            formation    = (lineup.get("FORMATION") or [""])[0]

            def _make_row(names: list[str]) -> list[dict]:
                return [_resolve_player(n, is_cap=(n == captain_name), is_vc=(n == vc_name))
                        for n in names]

            gkp_row = _make_row(lineup.get("GKP", []))
            def_row = _make_row(lineup.get("DEF", []))
            mid_row = _make_row(lineup.get("MID", []))
            fwd_row = _make_row(lineup.get("FWD", []))
            bench_p = [_resolve_player(n) for n in lineup.get("BENCH", [])]

            # Caption tag showing formation
            formation_tag = (
                f'<span style="font-size:0.6rem;font-weight:600;color:#00e87a;'
                f'background:rgba(0,232,122,0.1);border:1px solid rgba(0,232,122,0.2);'
                f'border-radius:4px;padding:1px 7px;margin-left:8px;">{formation}</span>'
                if formation else ""
            )
            label_text = "Suggested Lineup"

        # ── PATH B: Current FPL picks (fallback) ───────────────────────────────
        else:
            url   = f"https://fantasy.premierleague.com/api/entry/{uid}/event/{_current_gw(fpl_data)}/picks/"
            raw   = json.loads(_cached_get(url))
            picks = raw.get("picks", [])
            if not picks:
                return ""

            el_map = {e["id"]: e for e in elements}
            players = []
            for pk in picks:
                el = el_map.get(pk["element"])
                if not el:
                    continue
                team_name = teams_map.get(el.get("team", 0), "")
                is_out = any(
                    _find_element_by_name(sw["out"], elements) and
                    _find_element_by_name(sw["out"], elements)["id"] == pk["element"]
                    for sw in (transfers or [])
                )
                is_in = any(
                    _find_element_by_name(sw["in"], elements) and
                    _find_element_by_name(sw["in"], elements)["id"] == pk["element"]
                    for sw in (transfers or [])
                )
                players.append({
                    "name":   el.get("web_name", "?"),
                    "team":   team_name,
                    "pos":    el.get("element_type", 4),
                    "slot":   pk.get("position", 99),
                    "is_cap": pk.get("is_captain", False),
                    "is_vc":  pk.get("is_vice_captain", False),
                    "is_out": is_out,
                    "is_in":  is_in,
                })

            starters = sorted([p for p in players if p["slot"] <= 11], key=lambda x: x["slot"])
            bench_p  = sorted([p for p in players if p["slot"] > 11],  key=lambda x: x["slot"])
            gkp_row  = [p for p in starters if p["pos"] == 1]
            def_row  = [p for p in starters if p["pos"] == 2]
            mid_row  = [p for p in starters if p["pos"] == 3]
            fwd_row  = [p for p in starters if p["pos"] == 4]
            formation_tag = ""
            label_text = "Current Squad"

        # ── Render pitch ────────────────────────────────────────────────────────
        pitch = (
            '<div style="background:repeating-linear-gradient(180deg,#14531a 0px,#14531a 44px,#175c1e 44px,#175c1e 88px);'
            'border:2px solid rgba(255,255,255,0.15);border-radius:12px;padding:20px 10px 14px;'
            'position:relative;overflow:hidden;box-shadow:0 12px 40px rgba(0,0,0,0.7),inset 0 1px 0 rgba(255,255,255,0.04);">'
            '<div style="position:absolute;inset:10px;border:1px solid rgba(255,255,255,0.07);border-radius:6px;pointer-events:none;"></div>'
            '<div style="position:absolute;left:10%;right:10%;top:50%;height:1px;background:rgba(255,255,255,0.1);pointer-events:none;"></div>'
            '<div style="position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:58px;height:58px;border-radius:50%;border:1px solid rgba(255,255,255,0.09);pointer-events:none;"></div>'
            '<div style="position:absolute;left:35%;right:35%;top:10px;height:12%;border:1px solid rgba(255,255,255,0.06);border-top:none;pointer-events:none;"></div>'
            '<div style="position:absolute;left:35%;right:35%;bottom:10px;height:12%;border:1px solid rgba(255,255,255,0.06);border-bottom:none;pointer-events:none;"></div>'
            '<div style="position:relative;z-index:1;">'
            + _row(fwd_row) + _row(mid_row) + _row(def_row) + _row(gkp_row)
            + '</div></div>'
        )

        bench_html = (
            '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;'
            'justify-content:center;padding:10px 12px;margin-top:6px;'
            'background:#09090e;border:1px solid rgba(255,255,255,0.06);border-radius:9px;">'
            '<span style="font-size:0.59rem;font-weight:700;letter-spacing:0.1em;'
            'text-transform:uppercase;color:#2a2a36;margin-right:4px;">Bench</span>'
            + "".join(
                _make_card(p["name"], p["team"], p.get("is_cap", False), p.get("is_vc", False),
                           p.get("is_out", False), p.get("is_in", False), small=True)
                for p in bench_p
            )
            + '</div>'
        )

        label = (
            f'<div style="display:flex;align-items:center;gap:0;margin-bottom:10px;">'
            f'<span style="font-size:0.61rem;font-weight:700;letter-spacing:0.09em;'
            f'text-transform:uppercase;color:#2a2a36;">{label_text}</span>'
            f'{formation_tag}</div>'
        )
        return f'<div style="margin-top:20px;">{label}{pitch}{bench_html}</div>'

    except Exception:
        return ""


def _current_gw(fpl_data) -> int:
    try:
        events = pd.DataFrame(fpl_data["events"])
        cur = events[events["is_current"] == True]
        if not cur.empty:
            return int(cur.iloc[0]["id"])
        nxt = events[events["is_next"] == True]
        if not nxt.empty:
            return int(nxt.iloc[0]["id"]) - 1
    except Exception:
        pass
    return 1


# ── Helper: re-render saved agent trace ───────────────────────────────────────
def render_log(log: list):
    for entry in log:
        t     = entry["type"]
        agent = AGENT_LABELS.get(entry.get("agent", ""), entry.get("agent", ""))
        if t == "agent_start":
            st.markdown(f'<div class="feed-agent">▶ {agent}</div>', unsafe_allow_html=True)
        elif t == "tool_call":
            args_str = ", ".join(f"{k}={v}" for k, v in entry.get("args", {}).items())
            st.markdown(f'<div class="feed-tool">🔧 {entry["name"]}({args_str})</div>', unsafe_allow_html=True)
        elif t == "tool_result":
            preview = entry.get("content", "")[:300].replace("\n", " ")
            st.markdown(f'<div class="feed-result">↳ {preview}…</div>', unsafe_allow_html=True)
        elif t == "agent_text":
            st.markdown(f'<div class="feed-text">{entry["content"]}</div>', unsafe_allow_html=True)


# ── Clarification card renderer ────────────────────────────────────────────────
def _render_clarification_card(msg_idx: int, msg: dict):
    questions = msg["questions"]
    intro     = msg.get("intro", "A few quick questions:")

    with st.chat_message("assistant"):
        st.markdown(f"""
        <div style="border-left:2px solid #00e87a;padding-left:14px;margin-bottom:18px;">
            <div style="font-size:0.65rem;font-weight:700;letter-spacing:0.1em;
                        text-transform:uppercase;color:#00e87a;margin-bottom:5px;">Quick context</div>
            <div style="font-size:0.875rem;color:#c8c8d8;line-height:1.65;">{intro}</div>
        </div>
        """, unsafe_allow_html=True)

        for q in questions:
            st.markdown(
                f'<div style="font-size:0.82rem;color:#9494a8;margin-bottom:7px;font-weight:500;">'
                f'{q["text"]}</div>',
                unsafe_allow_html=True,
            )
            st.pills(
                label=q["text"],
                options=q["options"],
                selection_mode="single",
                key=f"clarify_pill_{msg_idx}_{q['id']}",
            )
            st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

        # Collect answers from session state
        all_answers = {
            q["id"]: st.session_state.get(f"clarify_pill_{msg_idx}_{q['id']}")
            for q in questions
            if st.session_state.get(f"clarify_pill_{msg_idx}_{q['id']}")
        }
        all_answered = len(all_answers) == len(questions)

        st.markdown('<div style="height:4px;"></div>', unsafe_allow_html=True)
        col1, col2 = st.columns([3, 1])

        with col1:
            st.markdown('<div class="clarify-go">', unsafe_allow_html=True)
            go_label = "Analyse now →" if all_answered else f"Answer {len(questions) - len(all_answers)} more question(s) to continue"
            if st.button(go_label, key=f"clarify_go_{msg_idx}",
                         disabled=not all_answered, use_container_width=True):
                _submit_clarification(msg["query"], questions, all_answers, msg_idx)
            st.markdown('</div>', unsafe_allow_html=True)

        with col2:
            st.markdown('<div class="clarify-skip">', unsafe_allow_html=True)
            if st.button("Skip →", key=f"clarify_skip_{msg_idx}", use_container_width=True):
                _submit_clarification(msg["query"], questions, {}, msg_idx, skip=True)
            st.markdown('</div>', unsafe_allow_html=True)


def _submit_clarification(query: str, questions: list, answers: dict,
                           msg_idx: int, skip: bool = False):
    enriched = query if (skip or not answers) else _build_enriched_query(query, questions, answers)

    # Clean up pill session state
    for q in questions:
        key = f"clarify_pill_{msg_idx}_{q['id']}"
        if key in st.session_state:
            del st.session_state[key]

    # Remove clarification message from history
    st.session_state.messages = [
        m for m in st.session_state.messages if m.get("role") != "clarification"
    ]
    st.session_state.pending_agent_input = enriched
    st.rerun()


# ── Empty state (no messages) ──────────────────────────────────────────────────
_has_clarification = any(m.get("role") == "clarification" for m in st.session_state.messages)

if not st.session_state.messages and not _has_clarification and not st.session_state.pending_agent_input:
    st.markdown("""
    <div style="text-align:center;padding:3.5rem 0 2.75rem;">
        <div style="width:52px;height:52px;background:#00e87a;border-radius:14px;
                    display:inline-flex;align-items:center;justify-content:center;
                    font-size:1.45rem;margin-bottom:1.2rem;
                    box-shadow:0 0 36px rgba(0,232,122,0.18),0 0 0 1px rgba(0,232,122,0.12);">⚽</div>
        <div style="font-size:1.55rem;font-weight:800;color:#f0f0f5;
                    letter-spacing:-0.045em;margin-bottom:0.45rem;">How can I help?</div>
        <div style="font-size:0.84rem;color:#4a4a5a;max-width:270px;margin:0 auto;line-height:1.7;">
            Ask me anything about your FPL team.
        </div>
    </div>
    """, unsafe_allow_html=True)

    _SUGGESTIONS = [
        ("⚽", "Recommend transfers",    "Recommend transfers for this gameweek"),
        ("👑", "Who should I captain?",  "Who should I captain?"),
        ("📋", "Suggest my lineup",      "Suggest my starting lineup"),
        ("🃏", "Chip strategy",          "Should I use a chip this GW?"),
        ("📅", "Fixture analysis",       "Show upcoming fixtures analysis"),
        ("👥", "Analyse rivals",         "Analyse my rivals' teams"),
    ]
    col1, col2 = st.columns(2, gap="small")
    for i, (icon, title, prompt) in enumerate(_SUGGESTIONS):
        col = col1 if i % 2 == 0 else col2
        col.markdown('<div class="suggest-card">', unsafe_allow_html=True)
        if col.button(f"{icon}  {title}", key=f"suggest_{i}", use_container_width=True):
            st.session_state["quick_prompt"] = prompt
            st.rerun()
        col.markdown('</div>', unsafe_allow_html=True)

else:
    # Minimal header shown once messages exist
    st.markdown("""
    <div style="padding:1rem 0 0.65rem;border-bottom:1px solid rgba(255,255,255,0.06);margin-bottom:0.5rem;">
        <div style="display:flex;align-items:center;justify-content:space-between;">
            <span style="font-size:0.88rem;font-weight:700;color:#f0f0f5;letter-spacing:-0.02em;">FPL AI Advisor</span>
            <div style="display:flex;align-items:center;gap:5px;">
                <span style="width:5px;height:5px;border-radius:50%;background:#00e87a;display:inline-block;
                             box-shadow:0 0 6px rgba(0,232,122,0.5);"></span>
                <span style="font-size:0.65rem;font-weight:600;color:#00e87a;letter-spacing:0.05em;text-transform:uppercase;">Live</span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# ── Render chat history ────────────────────────────────────────────────────────
for _i, _msg in enumerate(st.session_state.messages):
    _role = _msg.get("role", "user")

    if _role == "user":
        with st.chat_message("user"):
            st.markdown(_msg["content"])

    elif _role == "assistant":
        with st.chat_message("assistant"):
            _log = _msg.get("log", [])
            if _log:
                with st.expander(f"Agent trace · {len(_log)} steps", expanded=False):
                    render_log(_log)
            # Strip the machine-readable lineup block before showing text to user
            _hist_lineup  = _parse_lineup_block(_msg["content"])
            _hist_display = _strip_lineup_block(_msg["content"])
            st.markdown(_hist_display)
            _swaps = _parse_transfers_from_output(_msg["content"])
            if not _swaps:
                for _entry in _msg.get("log", []):
                    if _entry.get("type") == "agent_text":
                        _swaps = _parse_transfers_from_output(_entry["content"])
                        if _swaps:
                            break
            _pitch = _squad_pitch_html(user_id, transfers=_swaps, lineup=_hist_lineup)
            if _pitch:
                st.markdown(_pitch, unsafe_allow_html=True)

    elif _role == "clarification":
        _render_clarification_card(_i, _msg)

# ── Handle input ───────────────────────────────────────────────────────────────
_user_input = st.chat_input("Ask about transfers, lineup, captaincy, chips…")
if "quick_prompt" in st.session_state:
    _user_input = st.session_state.pop("quick_prompt")

# Pending agent run from clarification submission
_from_clarification = False
if st.session_state.pending_agent_input:
    _user_input        = st.session_state.pending_agent_input
    st.session_state.pending_agent_input = None
    _from_clarification = True

# Block new chat input while a clarification card is pending
if _user_input and not _from_clarification and _has_clarification:
    _user_input = None

# ── Meta-question short-circuit ───────────────────────────────────────────────
_META_RESPONSE = """\
Here's what you can ask me:

- **Transfers** — "Recommend transfers for this gameweek"
- **Lineup** — "Suggest my starting 11"
- **Captaincy** — "Who should I captain?"
- **Chip strategy** — "Should I use a chip this GW?"
- **Full GW advice** — "Help me with my team this week"
- **Fixture difficulty** — "Show upcoming fixture analysis"
- **Rival analysis** — "Analyse my mini-league rivals"

Just type naturally — I'll figure out what you need.
"""

_META_TRIGGERS = {
    "what can i ask", "what can you do", "what do you do",
    "help", "how do i use", "how does this work", "what are you",
    "what can you help", "commands", "options",
}


def _is_meta(text: str) -> bool:
    t = text.lower().strip().rstrip("?")
    return any(t.startswith(tr) or tr in t for tr in _META_TRIGGERS)


# ── Process input ──────────────────────────────────────────────────────────────
if _user_input:
    _app_log.info("=== NEW QUERY (thread=%s) ===", st.session_state.thread_id[:8])
    _app_log.info("USER: %s", _user_input)

    # Add user message to history (skip if from clarification — already in history)
    if not _from_clarification:
        with st.chat_message("user"):
            st.markdown(_user_input)
        st.session_state.messages.append({"role": "user", "content": _user_input})

        # Meta short-circuit
        if _is_meta(_user_input):
            with st.chat_message("assistant"):
                st.markdown(_META_RESPONSE)
            st.session_state.messages.append({"role": "assistant", "content": _META_RESPONSE, "log": []})
            st.stop()

        # Check if clarification is warranted
        _clarify_cfg = _get_clarify_cfg(_user_input)
        if _clarify_cfg:
            st.session_state.messages.append({
                "role":      "clarification",
                "query":     _user_input,
                "questions": _clarify_cfg["questions"],
                "intro":     _clarify_cfg.get("intro", "A few quick questions:"),
                "answers":   {},
            })
            st.rerun()

    # ── Build final message with context ──────────────────────────────────────
    _full_message = (
        f"{_user_input}\n\n"
        f"My FPL team ID is {user_id} and my league ID is {league_id}."
    )

    # Pre-fetch GW context
    def _prefetch():
        lines = []
        try:
            from agent import _cached_get, data as fpl_data
            events_df = pd.DataFrame(fpl_data["events"])
            cur = events_df[events_df["is_current"] == True]
            nxt = events_df[events_df["is_next"] == True]
            current_gw = int(cur.iloc[0]["id"]) if not cur.empty else None
            next_gw    = int(nxt.iloc[0]["id"]) if not nxt.empty else current_gw
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

    _full_message += _prefetch()

    # ── Stream agent responses ─────────────────────────────────────────────────
    _log        = []
    _final_out  = ""
    _last_agent = None

    _INTERNAL_NODES = {
        "update_pipeline", "update_chip",
        "update_transfers", "update_validation",
        "set_squad_path", "set_incoming_path", "sync_analysis",
        "compress_research", "compress_rival", "compress_fixtures",
        "compress_chips", "compress_squad", "compress_transfers",
        "compress_outgoing", "compress_incoming", "compress_validation",
        "compress_lineup", "compress_captaincy",
    }

    from agent import clear_tool_cache
    clear_tool_cache()

    _config = {
        "configurable": {"thread_id": st.session_state.thread_id},
        "recursion_limit": 150,
    }

    with st.chat_message("assistant"):
        with st.status("Agents working…", expanded=True) as _status:
            try:
                for _chunk in model.stream(
                    {"messages": [{"role": "user", "content": _full_message}]},
                    _config,
                ):
                    for _node, _node_data in _chunk.items():
                        if _node.startswith("__") or not isinstance(_node_data, dict) or _node in _INTERNAL_NODES:
                            continue

                        _label = AGENT_LABELS.get(_node, _node)

                        if _node != _last_agent:
                            _last_agent = _node
                            _app_log.info("AGENT  %s", _node)
                            st.markdown(f'<div class="feed-agent">▶ {_label}</div>', unsafe_allow_html=True)
                            _log.append({"type": "agent_start", "agent": _node})
                            _status.update(label=f"⚙ {_label}…")

                        for _msg in _node_data.get("messages", []):
                            if isinstance(_msg, AIMessage) and getattr(_msg, "tool_calls", None):
                                for _tc in _msg.tool_calls:
                                    _args_str = ", ".join(
                                        f"{k}={repr(v)}" for k, v in _tc.get("args", {}).items()
                                    )
                                    _app_log.info("  TOOL  %s(%s)", _tc["name"], _args_str)
                                    st.markdown(
                                        f'<div class="feed-tool">🔧 {_tc["name"]}({_args_str})</div>',
                                        unsafe_allow_html=True,
                                    )
                                    _log.append({
                                        "type": "tool_call", "agent": _node,
                                        "name": _tc["name"], "args": _tc.get("args", {}),
                                    })

                            elif isinstance(_msg, ToolMessage):
                                _raw     = _msg.content if isinstance(_msg.content, str) else str(_msg.content)
                                _preview = _raw[:300].replace("\n", " ")
                                _ell     = "…" if len(_raw) > 300 else ""
                                _app_log.debug("  RESULT %s…", _raw[:200].replace("\n", " "))
                                st.markdown(
                                    f'<div class="feed-result">↳ {_preview}{_ell}</div>',
                                    unsafe_allow_html=True,
                                )
                                _log.append({"type": "tool_result", "agent": _node, "content": _raw})

                            elif isinstance(_msg, AIMessage):
                                _content = _msg.content if isinstance(_msg.content, str) else ""
                                if not _content.strip():
                                    continue
                                _app_log.info("  TEXT  [%s] %s…", _node, _content[:120].replace("\n", " "))
                                st.markdown(
                                    f'<div class="feed-text">{_content}</div>',
                                    unsafe_allow_html=True,
                                )
                                _log.append({"type": "agent_text", "agent": _node, "content": _content})
                                if _node == "final_reviewer":
                                    _final_out = _content

            except Exception as _e:
                import traceback
                _app_log.error("AGENT ERROR: %s\n%s", _e, traceback.format_exc())
                _status.update(label="❌ Error", state="error")
                st.error(f"Agent error: {_e}")
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"Something went wrong: {_e}",
                    "log": _log,
                })
                st.stop()

            _status.update(label="✅ Done", state="complete", expanded=False)

        # Fall back to last agent text if final_reviewer didn't produce output
        if not _final_out and _log:
            for _entry in reversed(_log):
                if _entry["type"] == "agent_text":
                    _final_out = _entry["content"]
                    break

        # Extract and strip the machine-readable lineup block before showing text
        _lineup_data   = _parse_lineup_block(_final_out or "")
        _display_final = _strip_lineup_block(_final_out or "") if _final_out else ""

        if _display_final:
            st.markdown(_display_final)

        # Squad pitch — prefer agent-suggested lineup; fall back to transfer swaps only
        _swaps = _parse_transfers_from_output(_final_out or "")
        if not _swaps and _log:
            _all_text = "\n".join(e["content"] for e in _log if e["type"] == "agent_text")
            _swaps    = _parse_transfers_from_output(_all_text)
        _pitch = _squad_pitch_html(user_id, transfers=_swaps, lineup=_lineup_data)
        if _pitch:
            st.markdown(_pitch, unsafe_allow_html=True)

    # Save raw content (with lineup block intact) so it can be re-parsed on history replay
    st.session_state.messages.append({
        "role":    "assistant",
        "content": _final_out or "No response generated.",
        "log":     _log,
    })
