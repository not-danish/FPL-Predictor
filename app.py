import re
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
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

*, *::before, *::after { font-family: 'Inter', system-ui, -apple-system, sans-serif !important; }

::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 2px; }

.stApp { background: #09090b !important; }
.block-container { max-width: 820px !important; padding: 0 1.5rem 3rem !important; margin: 0 auto !important; }

#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }
header[data-testid="stHeader"] { background: transparent !important; height: 0 !important; min-height: 0 !important; }

/* ─ Sidebar ──────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: #100016 !important;
    border-right: 1px solid rgba(255,255,255,0.05) !important;
}
[data-testid="stSidebar"] > div:first-child { padding: 1.5rem 1rem !important; }
[data-testid="stSidebar"] * { color: #a1a1aa !important; }
[data-testid="stSidebar"] hr { border: none !important; border-top: 1px solid rgba(255,255,255,0.06) !important; margin: 1.1rem 0 !important; }

[data-testid="stSidebar"] .stNumberInput input,
[data-testid="stSidebar"] .stTextInput input {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.09) !important;
    color: #e4e4e7 !important;
    border-radius: 7px !important;
    font-size: 0.83rem !important;
    height: 34px !important;
    padding: 0 10px !important;
    transition: border-color 0.15s !important;
}
[data-testid="stSidebar"] .stNumberInput input:focus,
[data-testid="stSidebar"] .stTextInput input:focus {
    border-color: rgba(0,255,135,0.35) !important;
    box-shadow: 0 0 0 3px rgba(0,255,135,0.06) !important;
    outline: none !important;
}
[data-testid="stSidebar"] label {
    font-size: 0.67rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    color: rgba(161,161,170,0.5) !important;
    margin-bottom: 4px !important;
}
[data-testid="stSidebar"] .stButton > button {
    background: transparent !important;
    border: none !important;
    color: #71717a !important;
    border-radius: 6px !important;
    width: 100% !important;
    padding: 6px 10px !important;
    font-size: 0.8rem !important;
    font-weight: 500 !important;
    text-align: left !important;
    transition: background 0.12s, color 0.12s !important;
    margin-bottom: 1px !important;
    cursor: pointer !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,255,255,0.06) !important;
    color: #e4e4e7 !important;
}
[data-testid="stSidebar"] .stButton > button:focus { box-shadow: none !important; }

/* ─ Chat input ───────────────────────────────────── */
[data-testid="stChatInput"] > div {
    background: #111113 !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 12px !important;
    transition: border-color 0.15s !important;
}
[data-testid="stChatInput"] > div:focus-within {
    border-color: rgba(0,255,135,0.3) !important;
    box-shadow: 0 0 0 3px rgba(0,255,135,0.05) !important;
}
[data-testid="stChatInput"] textarea { color: #e4e4e7 !important; font-size: 0.875rem !important; }
[data-testid="stChatInput"] textarea::placeholder { color: #3f3f46 !important; }
[data-testid="stChatInput"] button svg { color: #00FF87 !important; fill: #00FF87 !important; }

/* ─ Chat messages ────────────────────────────────── */
[data-testid="stChatMessage"] { background: transparent !important; border: none !important; padding: 0.15rem 0 !important; }
[data-testid="stChatMessage"] p  { color: #d4d4d8 !important; font-size: 0.875rem !important; line-height: 1.75 !important; }
[data-testid="stChatMessage"] li { color: #d4d4d8 !important; font-size: 0.875rem !important; line-height: 1.7 !important; }
[data-testid="stChatMessage"] strong { color: #fafafa !important; font-weight: 600 !important; }
[data-testid="stChatMessage"] h1,
[data-testid="stChatMessage"] h2,
[data-testid="stChatMessage"] h3 { color: #fafafa !important; font-weight: 700 !important; letter-spacing: -0.02em !important; }
[data-testid="stChatMessage"] code {
    background: rgba(0,255,135,0.07) !important;
    color: #6ee7b7 !important;
    border-radius: 4px !important;
    padding: 1px 5px !important;
    font-size: 0.8em !important;
    font-family: 'Fira Code','Cascadia Code','SF Mono',monospace !important;
}
[data-testid="stChatMessage"] hr { border: none !important; border-top: 1px solid rgba(255,255,255,0.07) !important; margin: 10px 0 !important; }

/* Tables */
[data-testid="stChatMessage"] table { border-collapse: collapse !important; width: 100% !important; font-size: 0.8rem !important; border: 1px solid rgba(255,255,255,0.07) !important; border-radius: 8px !important; overflow: hidden !important; }
[data-testid="stChatMessage"] th { background: rgba(0,255,135,0.05) !important; color: #00FF87 !important; font-size: 0.66rem !important; font-weight: 700 !important; letter-spacing: 0.08em !important; text-transform: uppercase !important; padding: 9px 13px !important; border-bottom: 1px solid rgba(0,255,135,0.1) !important; }
[data-testid="stChatMessage"] td { color: #a1a1aa !important; padding: 7px 13px !important; border-bottom: 1px solid rgba(255,255,255,0.04) !important; }
[data-testid="stChatMessage"] tr:last-child td { border-bottom: none !important; }
[data-testid="stChatMessage"] tr:hover td { background: rgba(255,255,255,0.02) !important; }

/* ─ Status + Expander ────────────────────────────── */
[data-testid="stStatus"] {
    background: #111113 !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: 10px !important;
}
[data-testid="stExpander"] {
    background: #0d0d10 !important;
    border: 1px solid rgba(255,255,255,0.06) !important;
    border-radius: 8px !important;
}
[data-testid="stExpander"] details summary { font-size: 0.74rem !important; color: #52525b !important; font-weight: 500 !important; letter-spacing: 0.01em !important; }
[data-testid="stExpander"] details summary:hover { color: #71717a !important; }

/* ─ Agent feed ───────────────────────────────────── */
.feed-agent {
    font-size: 0.69rem;
    font-weight: 700;
    color: #00FF87;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    padding: 9px 0 2px;
    border-top: 1px solid rgba(255,255,255,0.04);
    margin-top: 4px;
}
.feed-agent:first-child { border-top: none; margin-top: 0; padding-top: 2px; }
.feed-tool {
    font-size: 0.72rem;
    color: #d97706;
    padding: 2px 0 2px 14px;
    font-family: 'Fira Code','Cascadia Code','SF Mono',monospace !important;
}
.feed-result {
    font-size: 0.67rem;
    color: #3f3f46;
    padding: 1px 0 1px 14px;
    font-family: 'Fira Code','Cascadia Code','SF Mono',monospace !important;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.feed-text {
    font-size: 0.76rem;
    color: #71717a;
    padding: 4px 0 2px 14px;
    line-height: 1.55;
}

/* ─ Onboarding ───────────────────────────────────── */
.onboard [data-testid="stFormSubmitButton"] button {
    background: #00FF87 !important;
    color: #09090b !important;
    border: none !important;
    border-radius: 10px !important;
    height: 46px !important;
    font-size: 0.875rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.01em !important;
    transition: opacity 0.15s !important;
}
.onboard [data-testid="stFormSubmitButton"] button:hover { opacity: 0.88 !important; }
.onboard [data-testid="stFormSubmitButton"] button:focus { box-shadow: 0 0 0 3px rgba(0,255,135,0.15) !important; }
.onboard [data-testid="stTextInputRootElement"] input {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    color: #e4e4e7 !important;
    border-radius: 10px !important;
    font-size: 0.9rem !important;
    height: 44px !important;
    padding: 0 14px !important;
}
.onboard [data-testid="stTextInputRootElement"] input:focus {
    border-color: rgba(0,255,135,0.4) !important;
    box-shadow: 0 0 0 3px rgba(0,255,135,0.08) !important;
}
.onboard label { font-size: 0.7rem !important; font-weight: 600 !important; letter-spacing: 0.07em !important; text-transform: uppercase !important; color: #71717a !important; }

/* ─ Team profile bar ─────────────────────────────── */
.team-bar-btn button {
    background: transparent !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    color: #52525b !important;
    border-radius: 7px !important;
    font-size: 0.72rem !important;
    font-weight: 500 !important;
    padding: 5px 12px !important;
    height: auto !important;
    transition: border-color 0.12s, color 0.12s !important;
}
.team-bar-btn button:hover { border-color: rgba(255,255,255,0.15) !important; color: #a1a1aa !important; }
.team-bar-btn button:focus { box-shadow: none !important; }
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
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "league_id" not in st.session_state:
    st.session_state.league_id = None
if "team_name" not in st.session_state:
    st.session_state.team_name = None
if "manager_name" not in st.session_state:
    st.session_state.manager_name = None

# ── Onboarding (first visit) ───────────────────────────────────────────────────
if not st.session_state.user_id:
    st.markdown("""<style>
    [data-testid="stSidebar"] { display: none !important; }
    .block-container { max-width: 480px !important; padding-top: 4vh !important; }
    </style>""", unsafe_allow_html=True)

    st.markdown("""
    <div style="text-align:center; padding: 2.5rem 0 2.5rem;">
        <div style="width:60px;height:60px;background:#00FF87;border-radius:16px;
                    display:inline-flex;align-items:center;justify-content:center;
                    font-size:1.75rem;margin-bottom:1.6rem;
                    box-shadow:0 0 32px rgba(0,255,135,0.25);">⚽</div>
        <div style="font-size:1.75rem;font-weight:800;color:#fafafa;
                    letter-spacing:-0.04em;margin-bottom:0.5rem;">FPL AI Advisor</div>
        <div style="font-size:0.875rem;color:#52525b;line-height:1.65;max-width:320px;margin:0 auto;">
            Connect your FPL team to get personalised transfer advice,
            lineup picks, captaincy tips and chip strategy.
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="onboard">', unsafe_allow_html=True)
    with st.form("onboard_form", border=False):
        uid_str = st.text_input("Team ID", placeholder="e.g. 872062",
                                help="The number in the URL of your FPL team page: fantasy.premierleague.com/entry/**123456**/transfers")
        lid_str = st.text_input("Mini-league ID  (optional)", placeholder="e.g. 1698003",
                                help="Found in the URL of your mini-league: fantasy.premierleague.com/leagues/**123456**/standings/c")
        submitted = st.form_submit_button("Connect my team →", use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("""
    <div style="text-align:center;margin-top:1.5rem;font-size:0.75rem;color:#3f3f46;line-height:1.8;">
        Your IDs are stored only in this browser session and are never shared.<br>
        Not sure where to find them? Open FPL, go to <em>Points</em> or <em>Leagues</em> — the number in the URL is your ID.
    </div>
    """, unsafe_allow_html=True)

    if submitted:
        uid_str = (uid_str or "").strip()
        if not uid_str.isdigit():
            st.error("Please enter a valid numeric Team ID (e.g. 872062).")
            st.stop()
        uid_val = int(uid_str)
        # Fetch team info from FPL API
        try:
            import requests as _rq
            _resp = _rq.get(
                f"https://fantasy.premierleague.com/api/entry/{uid_val}/",
                timeout=8,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            _resp.raise_for_status()
            _edata = _resp.json()
            st.session_state.team_name = _edata.get("name", f"Team {uid_val}")
            _first = _edata.get("player_first_name", "")
            _last  = _edata.get("player_last_name", "")
            st.session_state.manager_name = f"{_first} {_last}".strip()
        except Exception:
            st.session_state.team_name = f"Team {uid_val}"
            st.session_state.manager_name = ""

        st.session_state.user_id = uid_val
        lid_str = (lid_str or "").strip()
        st.session_state.league_id = int(lid_str) if lid_str.isdigit() else 0
        st.rerun()

    st.stop()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="display:flex;align-items:center;gap:10px;padding-bottom:1.4rem;border-bottom:1px solid rgba(255,255,255,0.06);margin-bottom:1.2rem;">
        <div style="width:30px;height:30px;background:#00FF87;border-radius:7px;display:flex;align-items:center;justify-content:center;flex-shrink:0;">
            <span style="font-size:0.95rem;line-height:1;">⚽</span>
        </div>
        <div>
            <div style="font-size:0.9rem;font-weight:700;color:#fafafa;letter-spacing:-0.01em;line-height:1.2;">FPL Advisor</div>
            <div style="font-size:0.65rem;color:#3f3f46;letter-spacing:0.04em;text-transform:uppercase;margin-top:1px;">AI · Multi-agent</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Team identity chip
    _tname = st.session_state.team_name or "—"
    _mgr   = st.session_state.manager_name or ""
    _uid   = st.session_state.user_id or ""
    st.markdown(f"""
    <div style="padding:10px 10px 12px;background:rgba(0,255,135,0.04);
                border:1px solid rgba(0,255,135,0.1);border-radius:9px;margin-bottom:12px;">
        <div style="font-size:0.82rem;font-weight:700;color:#fafafa;
                    letter-spacing:-0.01em;margin-bottom:2px;">{_tname}</div>
        <div style="font-size:0.68rem;color:#52525b;">{_mgr}</div>
        <div style="font-size:0.63rem;color:#3f3f46;margin-top:3px;font-family:monospace;">
            ID {_uid}{f' · L {st.session_state.league_id}' if st.session_state.league_id else ''}
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown('<div class="team-bar-btn">', unsafe_allow_html=True)
    if st.button("Change team", use_container_width=True, key="change_team_sidebar"):
        st.session_state.user_id = None
        st.session_state.league_id = None
        st.session_state.team_name = None
        st.session_state.manager_name = None
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div style="height:1px;background:rgba(255,255,255,0.06);margin:1.1rem 0 1rem;"></div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size:0.64rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#3f3f46;margin-bottom:6px;">Actions</div>', unsafe_allow_html=True)

    _QUICK_PROMPTS = [
        ("Recommend transfers",          "Recommend transfers for this gameweek"),
        ("Suggest starting lineup",      "Suggest my starting lineup"),
        ("Who should I captain?",        "Who should I captain?"),
        ("Chip strategy",                "Should I use a chip this GW?"),
        ("Analyse rival teams",          "Analyse my rivals' teams"),
        ("Fixture difficulty",           "Show upcoming fixtures analysis"),
    ]
    for label, prompt in _QUICK_PROMPTS:
        if st.button(label, use_container_width=True, key=f"qp_{prompt}"):
            st.session_state["quick_prompt"] = prompt
            st.rerun()

    st.markdown('<div style="height:1px;background:rgba(255,255,255,0.06);margin:1.1rem 0 1rem;"></div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size:0.64rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#3f3f46;margin-bottom:6px;">Session</div>', unsafe_allow_html=True)
    if st.button("New conversation", use_container_width=True):
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()
    if st.button("Reload agents", use_container_width=True, help="Reloads agent code — use after code changes"):
        load_model.clear()
        st.rerun()
    st.markdown(
        f'<div style="font-size:0.67rem;color:#3f3f46;margin-top:8px;font-family:monospace;">'
        f'{st.session_state.thread_id[:8]}...</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div style="position:fixed;bottom:1.25rem;font-size:0.62rem;color:#27272a;letter-spacing:0.02em;">'
        'LangGraph &middot; OpenRouter</div>',
        unsafe_allow_html=True,
    )

# ── Resolved IDs (always set after onboarding guard) ──────────────────────────
user_id   = st.session_state.user_id
league_id = st.session_state.league_id or 0

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="padding: 1.25rem 0 0.75rem; border-bottom: 1px solid rgba(255,255,255,0.06); margin-bottom: 0.75rem;">
    <div style="display:flex;align-items:baseline;justify-content:space-between;">
        <div>
            <span style="font-size:1.15rem;font-weight:800;color:#fafafa;letter-spacing:-0.03em;">FPL AI Advisor</span>
            <span style="font-size:0.75rem;color:#3f3f46;margin-left:12px;letter-spacing:0.01em;">Transfers · Lineup · Captaincy · Chips</span>
        </div>
        <div style="display:flex;align-items:center;gap:6px;">
            <span style="width:6px;height:6px;border-radius:50%;background:#00FF87;display:inline-block;"></span>
            <span style="font-size:0.7rem;font-weight:600;color:#00FF87;letter-spacing:0.04em;text-transform:uppercase;">Live</span>
        </div>
    </div>
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

def _parse_transfers_from_output(text: str) -> list:
    """Extract [(out_name, in_name), ...] pairs from agent output.

    Tries multiple formats:
    1. Final reviewer: "OUT: Player A (£Xm) → IN: Player B (£Xm)"
    2. Incoming recommender: "REPLACING: Player A (...)" + "BUY: Player B (...)"
    3. Outgoing/incoming pair: "SELL: Player A (...)" near "BUY: Player B (...)"
    """
    swaps = []

    # Pattern 1: Final reviewer format
    for m in re.finditer(
        r'OUT:\s*(.+?)\s*\(£[\d.]+m\)\s*(?:→|->|—|[-–])\s*IN:\s*(.+?)\s*\(£',
        text,
    ):
        swaps.append((m.group(1).strip(), m.group(2).strip()))

    if not swaps:
        # Pattern 2: REPLACING + OPTION 1 BUY format from incoming_recommender
        replacing = re.findall(r'REPLACING:\s*(.+?)\s*\(', text)
        buying = re.findall(r'BUY:\s*(.+?)\s*\(', text)
        if replacing and buying:
            # Take the first REPLACING and first BUY as the primary recommendation
            swaps.append((replacing[0].strip(), buying[0].strip()))

    if not swaps:
        # Pattern 3: SELL + BUY pair
        selling = re.findall(r'SELL:\s*(.+?)\s*\(', text)
        buying = re.findall(r'BUY:\s*(.+?)\s*\(', text)
        if selling and buying:
            swaps.append((selling[0].strip(), buying[0].strip()))

    if swaps:
        _app_log.info("PITCH SWAP parsed: %s", swaps)
    return swaps


def _find_element_by_name(name: str, elements: dict) -> dict | None:
    """Find FPL element by player name. Tries full name then last name token."""
    name_lower = name.lower()
    for el in elements.values():
        full = (el.get("first_name", "") + " " + el.get("second_name", "")).lower()
        web  = el.get("web_name", "").lower()
        if name_lower == full or name_lower == web:
            return el
    # Fallback: substring match on any part of the name
    for el in elements.values():
        full = (el.get("first_name", "") + " " + el.get("second_name", "")).lower()
        web  = el.get("web_name", "").lower()
        if name_lower in full or name_lower in web:
            return el
    return None


def _squad_pitch_html(user_id: int, transfers: list | None = None) -> str:
    """Return HTML for a pitch-style squad visualization, or empty string on failure.

    transfers: optional list of (out_name, in_name) to apply before rendering.
    """
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

        # Apply proposed transfers: swap out player → in player in-place
        if transfers:
            for out_name, in_name in transfers:
                in_el = _find_element_by_name(in_name, elements)
                if not in_el:
                    _app_log.warning("PITCH SWAP: could not find element for IN='%s'", in_name)
                    continue
                out_lower = out_name.lower()
                matched = False
                for p in players:
                    # p["name"] is web_name (e.g. "Fernandes"); out_lower is the full
                    # extracted name (e.g. "bruno borges fernandes").  Check if
                    # web_name appears inside the extracted name.
                    if p["name"].lower() in out_lower:
                        new_team = teams.get(in_el["team"], "")
                        _app_log.info(
                            "PITCH SWAP: '%s' (slot %s) → '%s' (%s)",
                            p["name"], p["slot"],
                            in_el.get("web_name", in_el["second_name"]), new_team,
                        )
                        p["name"]  = in_el.get("web_name", in_el["second_name"])
                        p["team"]  = new_team
                        p["pos"]   = pos_map.get(in_el["element_type"], p["pos"])
                        p["color"] = _TEAM_COLORS.get(new_team, "#546e7a")
                        p["is_captain"] = False
                        p["is_vc"]      = False
                        matched = True
                        break
                if not matched:
                    _app_log.warning(
                        "PITCH SWAP: no player card matched OUT='%s' (tried web_names: %s)",
                        out_name, [p["name"] for p in players],
                    )

        starters = sorted([p for p in players if p["is_starter"]], key=lambda x: x["slot"])
        bench    = sorted([p for p in players if not p["is_starter"]], key=lambda x: x["slot"])

        fwd_row = [p for p in starters if p["pos"] == "FWD"]
        mid_row = [p for p in starters if p["pos"] == "MID"]
        def_row = [p for p in starters if p["pos"] == "DEF"]
        gkp_row = [p for p in starters if p["pos"] == "GKP"]

        def _card(p, small=False):
            sz  = "28px" if small else "34px"
            fs  = "0.67rem" if small else "0.72rem"
            tfs = "0.55rem" if small else "0.58rem"
            w   = "58px"  if small else "66px"
            c_bg = p["color"]

            # Captain / VC ring
            ring = ""
            if p["is_captain"]:
                ring = f'border: 2px solid #f59e0b !important;box-shadow:0 0 0 2px rgba(245,158,11,0.25);'
            elif p["is_vc"]:
                ring = f'border: 2px solid #71717a !important;box-shadow:0 0 0 2px rgba(113,113,122,0.2);'
            else:
                ring = 'border: 2px solid rgba(255,255,255,0.18);'

            badge = ""
            if p["is_captain"]:
                badge = ('<div style="position:absolute;top:-4px;right:-4px;width:14px;height:14px;'
                         'border-radius:50%;background:#f59e0b;color:#000;font-size:0.5rem;font-weight:800;'
                         'display:flex;align-items:center;justify-content:center;z-index:3;'
                         'box-shadow:0 1px 4px rgba(0,0,0,0.4);">C</div>')
            elif p["is_vc"]:
                badge = ('<div style="position:absolute;top:-4px;right:-4px;width:14px;height:14px;'
                         'border-radius:50%;background:#71717a;color:#fff;font-size:0.5rem;font-weight:800;'
                         'display:flex;align-items:center;justify-content:center;z-index:3;">V</div>')

            initials = "".join(w[0].upper() for w in p["name"].split()[:2])
            return (
                f'<div style="position:relative;width:{w};flex-shrink:0;text-align:center;">'
                f'<div style="position:relative;display:inline-block;">'
                f'{badge}'
                f'<div style="width:{sz};height:{sz};border-radius:50%;background:{c_bg};{ring}'
                f'margin:0 auto;display:flex;align-items:center;justify-content:center;">'
                f'<span style="color:rgba(255,255,255,0.9);font-size:0.55rem;font-weight:700;'
                f'letter-spacing:0.02em;">{initials}</span>'
                f'</div></div>'
                f'<div style="margin-top:4px;background:rgba(0,0,0,0.75);border:1px solid rgba(255,255,255,0.07);'
                f'border-radius:4px;padding:2px 4px;">'
                f'<div style="font-size:{fs};color:#f4f4f5;font-weight:600;white-space:nowrap;'
                f'overflow:hidden;text-overflow:ellipsis;letter-spacing:-0.01em;">{p["name"]}</div>'
                f'<div style="font-size:{tfs};color:#52525b;white-space:nowrap;'
                f'overflow:hidden;text-overflow:ellipsis;">{p["team"]}</div>'
                f'</div></div>'
            )

        def _row(plist):
            if not plist:
                return ""
            return (
                '<div style="display:flex;justify-content:center;gap:10px;margin-bottom:18px;">'
                + "".join(_card(p) for p in plist) + "</div>"
            )

        pitch = (
            '<div style="'
            'background: repeating-linear-gradient('
            '  180deg,'
            '  #14531a 0px, #14531a 44px,'
            '  #175c1e 44px, #175c1e 88px'
            ');'
            'border: 2px solid rgba(255,255,255,0.18);'
            'border-radius: 12px;'
            'padding: 20px 10px 14px;'
            'position: relative;'
            'overflow: hidden;'
            'box-shadow: 0 12px 40px rgba(0,0,0,0.7), inset 0 1px 0 rgba(255,255,255,0.05);">'
            # Field outline
            '<div style="position:absolute;inset:10px;border:1px solid rgba(255,255,255,0.08);'
            'border-radius:6px;pointer-events:none;"></div>'
            # Half-way line
            '<div style="position:absolute;left:10%;right:10%;top:50%;height:1px;'
            'background:rgba(255,255,255,0.12);pointer-events:none;"></div>'
            # Centre circle
            '<div style="position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);'
            'width:60px;height:60px;border-radius:50%;border:1px solid rgba(255,255,255,0.1);'
            'pointer-events:none;"></div>'
            '<div style="position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);'
            'width:4px;height:4px;border-radius:50%;background:rgba(255,255,255,0.25);pointer-events:none;"></div>'
            # Top 6-yard box
            '<div style="position:absolute;left:35%;right:35%;top:10px;height:12%;'
            'border:1px solid rgba(255,255,255,0.07);border-top:none;pointer-events:none;"></div>'
            # Bottom 6-yard box
            '<div style="position:absolute;left:35%;right:35%;bottom:10px;height:12%;'
            'border:1px solid rgba(255,255,255,0.07);border-bottom:none;pointer-events:none;"></div>'
            '<div style="position:relative;z-index:1;">'
            + _row(fwd_row) + _row(mid_row) + _row(def_row) + _row(gkp_row)
            + '</div></div>'
        )

        bench_cards = "".join(_card(p, small=True) for p in bench)
        bench_html = (
            '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;'
            'justify-content:center;padding:10px 12px;margin-top:6px;'
            'background:#0d0d10;border:1px solid rgba(255,255,255,0.06);border-radius:9px;">'
            '<span style="font-size:0.6rem;font-weight:700;letter-spacing:0.1em;'
            'text-transform:uppercase;color:#27272a;margin-right:4px;">Bench</span>'
            + bench_cards + '</div>'
        )

        label = (
            '<div style="font-size:0.62rem;font-weight:700;letter-spacing:0.09em;'
            'text-transform:uppercase;color:#27272a;margin-bottom:10px;">Squad</div>'
        )
        return f'<div style="margin-top:20px;">{label}{pitch}{bench_html}</div>'

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
                with st.expander(f"Agent trace  ·  {len(log)} events", expanded=False):
                    render_log(log)
        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            swaps = _parse_transfers_from_output(msg["content"])
            if not swaps:
                # Also check agent log entries for transfer info
                for entry in msg.get("log", []):
                    if entry.get("type") == "agent_text":
                        swaps = _parse_transfers_from_output(entry["content"])
                        if swaps:
                            break
            pitch = _squad_pitch_html(user_id, transfers=swaps)
            if pitch:
                st.markdown(pitch, unsafe_allow_html=True)

# ── Handle input ───────────────────────────────────────────────────────────────
user_input = st.chat_input("Ask about transfers, lineup, captaincy, chip strategy...")
if "quick_prompt" in st.session_state:
    user_input = st.session_state.pop("quick_prompt")

_META_RESPONSE = """\
Here's what you can ask me:

- **Transfers** — "Recommend transfers for this gameweek"
- **Lineup** — "Suggest my starting 11"
- **Captaincy** — "Who should I captain?"
- **Chip strategy** — "Should I use a chip this GW?"
- **Full GW advice** — "Help me with my team this week"
- **Fixture difficulty** — "Show upcoming fixture analysis"
- **Rival analysis** — "Analyse my mini-league rivals"
- **Squad view** — "Show me my squad"

Just type naturally — I'll figure out what you need.
"""

_META_TRIGGERS = {
    "what can i ask", "what can you do", "what do you do",
    "help", "how do i use", "how does this work", "what are you",
    "what can you help", "commands", "options",
}

def _is_meta_question(text: str) -> bool:
    t = text.lower().strip().rstrip("?")
    return any(t.startswith(trigger) or trigger in t for trigger in _META_TRIGGERS)

if user_input:
    _app_log.info("=== NEW QUERY (thread=%s) ===", st.session_state.thread_id[:8])
    _app_log.info("USER: %s", user_input)

    # ── Short-circuit meta / help questions without running the agent ──────
    if _is_meta_question(user_input):
        with st.chat_message("user"):
            st.markdown(user_input)
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("assistant"):
            st.markdown(_META_RESPONSE)
        st.session_state.messages.append({"role": "assistant", "content": _META_RESPONSE, "log": []})
        st.stop()

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
        with st.status("Agents working...", expanded=True) as status:
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

        # Parse transfer swaps — check final_output first, then all logged agent text
        swaps = _parse_transfers_from_output(final_output or "")
        if not swaps and log:
            all_agent_text = "\n".join(
                e["content"] for e in log if e["type"] == "agent_text"
            )
            swaps = _parse_transfers_from_output(all_agent_text)
            if swaps:
                _app_log.info("PITCH SWAP: found transfer in agent log (not in final_output)")
        pitch = _squad_pitch_html(user_id, transfers=swaps)
        if pitch:
            st.markdown(pitch, unsafe_allow_html=True)

    st.session_state.messages.append({
        "role": "assistant",
        "content": final_output or "No response generated.",
        "log": log,
    })
