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
    page_title="The Regista",
    page_icon="🟢",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

*, *::before, *::after {
    font-family: 'Inter', -apple-system, system-ui, sans-serif;
    box-sizing: border-box;
}

/* Restore Material Symbols Rounded for Streamlit icon spans — critical:
   must use !important to override Streamlit's own styled-components specificity,
   but the global rule above must NOT be !important or it would break these too. */
[data-testid="stIconMaterial"] {
    font-family: "Material Symbols Rounded" !important;
    font-feature-settings: "liga" !important;
    -moz-font-feature-settings: "liga" !important;
    -webkit-font-feature-settings: "liga" !important;
    -webkit-font-smoothing: antialiased !important;
    text-rendering: optimizeLegibility !important;
}
[data-testid="stIconEmoji"] {
    font-family: inherit !important;
}

::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.14); }

.stApp { background: #060609 !important; }
.block-container { max-width: 820px !important; padding: 0 1.75rem 6rem !important; margin: 0 auto !important; }
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }
header[data-testid="stHeader"] { background: transparent !important; height: 0 !important; min-height: 0 !important; }

/* ── Sidebar ─────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: #07070b !important;
    border-right: 1px solid rgba(255,255,255,0.055) !important;
}
[data-testid="stSidebar"] > div:first-child { padding: 1.4rem 1.1rem 1.75rem !important; }
[data-testid="stSidebar"] * { color: #8b8c9e !important; }
[data-testid="stSidebar"] hr { border: none !important; border-top: 1px solid rgba(255,255,255,0.055) !important; margin: 1rem 0 !important; }
[data-testid="stSidebar"] label {
    font-size: 0.62rem !important; font-weight: 700 !important;
    letter-spacing: 0.1em !important; text-transform: uppercase !important;
    color: #252530 !important; margin-bottom: 4px !important;
}
[data-testid="stSidebar"] .stNumberInput input,
[data-testid="stSidebar"] .stTextInput input {
    background: rgba(255,255,255,0.025) !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    color: #e8e8f0 !important; border-radius: 8px !important;
    font-size: 0.83rem !important; height: 36px !important;
    padding: 0 11px !important; transition: border-color 0.15s, box-shadow 0.15s !important;
}
[data-testid="stSidebar"] .stNumberInput input:focus,
[data-testid="stSidebar"] .stTextInput input:focus {
    border-color: rgba(0,232,122,0.3) !important;
    box-shadow: 0 0 0 3px rgba(0,232,122,0.06) !important; outline: none !important;
}
[data-testid="stSidebar"] .stButton > button {
    background: transparent !important; border: none !important;
    color: #3a3a4a !important; border-radius: 8px !important;
    width: 100% !important; padding: 7px 10px !important;
    font-size: 0.8rem !important; font-weight: 500 !important;
    text-align: left !important; transition: background 0.12s, color 0.12s !important;
    cursor: pointer !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,255,255,0.04) !important; color: #c8c8d8 !important;
}
[data-testid="stSidebar"] .stButton > button:focus { box-shadow: none !important; }

/* ── Chat input ───────────────────────────────────── */
[data-testid="stChatInput"],
[data-testid="stChatInput"] > div,
[data-testid="stChatInput"] form {
    background: transparent !important;
    border: none !important; box-shadow: none !important;
}
[data-testid="stChatInput"] > div > div,
[data-testid="stChatInput"] [data-testid="stChatInputTextArea"] {
    background: #0c0c13 !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 14px !important;
    transition: border-color 0.2s, box-shadow 0.2s !important;
}
[data-testid="stChatInput"] > div > div:focus-within,
[data-testid="stChatInput"] [data-testid="stChatInputTextArea"]:focus-within {
    border-color: rgba(0,232,122,0.28) !important;
    box-shadow: 0 0 0 3px rgba(0,232,122,0.05) !important;
}
[data-testid="stChatInput"] textarea {
    color: #e8e8f2 !important; font-size: 0.875rem !important;
    line-height: 1.6 !important; border: none !important;
    background: transparent !important;
}
[data-testid="stChatInput"] textarea::placeholder { color: #2e2e3c !important; }
[data-testid="stChatInput"] button {
    background: transparent !important; border: none !important;
}
[data-testid="stChatInput"] button svg { color: #00e87a !important; fill: #00e87a !important; }

/* ── Chat message avatars — hide emoji, show colored dot ── */
[data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessageAvatarAssistant"],
[data-testid="stChatMessage"] [data-testid*="Avatar"] {
    width: 8px !important; height: 8px !important;
    min-width: 8px !important; max-width: 8px !important;
    min-height: 8px !important; max-height: 8px !important;
    border-radius: 50% !important; overflow: hidden !important;
    flex-shrink: 0 !important; margin-top: 6px !important;
    font-size: 0 !important; color: transparent !important;
}
[data-testid="stChatMessageAvatarUser"] *,
[data-testid="stChatMessageAvatarAssistant"] *,
[data-testid="stChatMessage"] [data-testid*="Avatar"] * {
    display: none !important;
}
[data-testid="stChatMessageAvatarUser"] {
    background: #00e87a !important;
    box-shadow: 0 0 6px rgba(0,232,122,0.5) !important;
}
[data-testid="stChatMessageAvatarAssistant"] {
    background: #3a3a50 !important;
}

/* ── Chat messages ────────────────────────────────── */
[data-testid="stChatMessage"] {
    background: transparent !important; border: none !important;
    padding: 0.15rem 0 !important; gap: 14px !important;
    align-items: flex-start !important;
}
[data-testid="stChatMessage"] [data-testid="stChatMessageAvatarUser"] {
    background: rgba(0,232,122,0.15) !important;
    border: 1px solid rgba(0,232,122,0.2) !important;
    color: #00e87a !important;
}
[data-testid="stChatMessage"] p {
    color: #d4d4e0 !important; font-size: 0.875rem !important;
    line-height: 1.8 !important; margin-bottom: 0.6em !important;
}
[data-testid="stChatMessage"] li {
    color: #d4d4e0 !important; font-size: 0.875rem !important;
    line-height: 1.75 !important; margin-bottom: 0.2em !important;
}
[data-testid="stChatMessage"] strong { color: #f2f2fa !important; font-weight: 600 !important; }
[data-testid="stChatMessage"] h1,
[data-testid="stChatMessage"] h2,
[data-testid="stChatMessage"] h3 {
    color: #ffffff !important; font-weight: 700 !important;
    letter-spacing: -0.035em !important; margin-top: 1.4em !important;
    margin-bottom: 0.4em !important;
}
[data-testid="stChatMessage"] h3 { font-size: 0.95rem !important; }
[data-testid="stChatMessage"] code {
    background: rgba(0,232,122,0.07) !important; color: #5dd9a4 !important;
    border: 1px solid rgba(0,232,122,0.12) !important;
    border-radius: 5px !important; padding: 1px 6px !important;
    font-size: 0.8em !important; font-family: 'JetBrains Mono', 'Fira Code', monospace !important;
}
[data-testid="stChatMessage"] pre {
    background: #0b0b12 !important;
    border: 1px solid rgba(255,255,255,0.06) !important;
    border-radius: 10px !important; padding: 14px 18px !important;
    overflow-x: auto !important;
}
[data-testid="stChatMessage"] pre code {
    background: transparent !important; border: none !important;
    padding: 0 !important; color: #8b8c9e !important; font-size: 0.78rem !important;
}
[data-testid="stChatMessage"] hr {
    border: none !important;
    border-top: 1px solid rgba(255,255,255,0.06) !important;
    margin: 14px 0 !important;
}
[data-testid="stChatMessage"] table {
    border-collapse: collapse !important; width: 100% !important;
    font-size: 0.8rem !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: 10px !important; overflow: hidden !important;
    margin: 10px 0 !important;
}
[data-testid="stChatMessage"] th {
    background: rgba(0,232,122,0.06) !important; color: #00e87a !important;
    font-size: 0.62rem !important; font-weight: 700 !important;
    letter-spacing: 0.09em !important; text-transform: uppercase !important;
    padding: 10px 14px !important;
    border-bottom: 1px solid rgba(0,232,122,0.1) !important;
}
[data-testid="stChatMessage"] td {
    color: #8b8c9e !important; padding: 8px 14px !important;
    border-bottom: 1px solid rgba(255,255,255,0.04) !important;
}
[data-testid="stChatMessage"] tr:last-child td { border-bottom: none !important; }
[data-testid="stChatMessage"] tr:hover td { background: rgba(255,255,255,0.018) !important; }

/* ── Status widget (agent trace container) ──────── */
[data-testid="stStatus"] {
    background: #08080d !important;
    border: 1px solid rgba(255,255,255,0.055) !important;
    border-radius: 12px !important;
    font-size: 0.72rem !important;
    overflow: hidden !important;
    transition: border-color 0.2s !important;
}
[data-testid="stStatus"] summary {
    font-size: 0.72rem !important;
    color: #3a3a52 !important;
    font-weight: 600 !important;
    padding: 10px 14px !important;
    letter-spacing: 0.01em !important;
    transition: background 0.15s, color 0.15s !important;
}
[data-testid="stStatus"] summary:hover {
    background: rgba(255,255,255,0.018) !important;
    color: #5a5a72 !important;
}
[data-testid="stStatus"][data-expanded="true"],
[data-testid="stStatus"] details[open] {
    border-color: rgba(0,232,122,0.1) !important;
}
/* Toggle arrow in status/expander — subtle chevron */
[data-testid="stStatus"] summary [data-testid="stIconMaterial"],
[data-testid="stExpander"] summary [data-testid="stIconMaterial"]:not([data-testid="stExpanderIconCheck"]):not([data-testid="stExpanderIconError"]):not([data-testid="stExpanderIconSpinner"]) {
    font-size: 18px !important;
    color: rgba(255,255,255,0.15) !important;
    transition: color 0.15s ease !important;
    flex-shrink: 0 !important;
}
[data-testid="stStatus"] summary:hover [data-testid="stIconMaterial"],
[data-testid="stExpander"] summary:hover [data-testid="stIconMaterial"] {
    color: rgba(255,255,255,0.3) !important;
}
/* Status check/error icons */
[data-testid="stExpanderIconCheck"] {
    color: #00e87a !important;
    font-size: 16px !important;
}
[data-testid="stExpanderIconError"] {
    color: #ef4444 !important;
    font-size: 16px !important;
}

/* ── Expander ────────────────────────────────────── */
[data-testid="stExpander"] {
    background: #08080d !important;
    border: 1px solid rgba(255,255,255,0.055) !important;
    border-radius: 10px !important;
    margin-bottom: 4px !important;
    overflow: hidden !important;
    transition: border-color 0.2s !important;
}
[data-testid="stExpander"] details summary {
    font-size: 0.67rem !important; color: #3a3a52 !important;
    font-weight: 700 !important; letter-spacing: 0.08em !important;
    text-transform: uppercase !important; padding: 11px 14px !important;
    transition: background 0.15s, color 0.15s !important;
}
[data-testid="stExpander"] details summary:hover {
    background: rgba(255,255,255,0.018) !important;
    color: #6a6a82 !important;
}
[data-testid="stExpander"] details[open] summary {
    color: #5a5a72 !important;
    border-bottom: 1px solid rgba(255,255,255,0.04) !important;
}
[data-testid="stExpander"] details[open] {
    border-color: rgba(255,255,255,0.08) !important;
}
[data-testid="stExpander"] > details > div { padding: 12px 14px 16px !important; }

/* ── Dashboard section headers ──────────────────── */
.dash-section-label {
    font-size: 0.59rem !important; font-weight: 800 !important;
    letter-spacing: 0.12em !important; text-transform: uppercase !important;
    color: #3a7a5a !important; padding: 18px 0 8px !important;
}

/* ── Agent feed (inside status) ─────────────────── */
.feed-agent {
    font-size: 0.64rem; font-weight: 700; color: #00e87a;
    letter-spacing: 0.09em; text-transform: uppercase;
    padding: 9px 0 2px;
    border-top: 1px solid rgba(255,255,255,0.04);
    margin-top: 5px;
}
.feed-agent:first-child { border-top: none; margin-top: 0; padding-top: 2px; }
.feed-tool {
    font-size: 0.68rem; color: #c47c3a; padding: 2px 0 1px 14px;
    font-family: 'JetBrains Mono', 'Fira Code', monospace !important;
    letter-spacing: -0.01em;
}
.feed-result {
    font-size: 0.62rem; color: #272733; padding: 1px 0 0 14px;
    font-family: 'JetBrains Mono', 'Fira Code', monospace !important;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.feed-text {
    font-size: 0.72rem; color: #3e3e50; padding: 3px 0 2px 14px;
    line-height: 1.55;
}

/* ── Onboarding form ─────────────────────────────── */
.onboard [data-testid="stFormSubmitButton"] button {
    background: #00e87a !important; color: #030806 !important;
    border: none !important; border-radius: 11px !important;
    height: 46px !important; font-size: 0.88rem !important;
    font-weight: 700 !important; letter-spacing: -0.015em !important;
    transition: opacity 0.15s, transform 0.1s !important; width: 100% !important;
}
.onboard [data-testid="stFormSubmitButton"] button:hover {
    opacity: 0.88 !important; transform: translateY(-1px) !important;
}
.onboard [data-testid="stTextInputRootElement"] input {
    background: rgba(255,255,255,0.025) !important;
    border: 1px solid rgba(255,255,255,0.09) !important;
    color: #f0f0f8 !important; border-radius: 11px !important;
    font-size: 0.88rem !important; height: 46px !important; padding: 0 15px !important;
    transition: border-color 0.15s, box-shadow 0.15s !important;
}
.onboard [data-testid="stTextInputRootElement"] input:focus {
    border-color: rgba(0,232,122,0.35) !important;
    box-shadow: 0 0 0 4px rgba(0,232,122,0.06) !important; outline: none !important;
}
.onboard label {
    font-size: 0.67rem !important; font-weight: 700 !important;
    letter-spacing: 0.09em !important; text-transform: uppercase !important;
    color: #5a5a6e !important;
}

/* ── Team bar in sidebar ─────────────────────────── */
.team-bar-btn button {
    background: transparent !important;
    border: 1px solid rgba(255,255,255,0.06) !important;
    color: #2e2e3c !important; border-radius: 8px !important;
    font-size: 0.72rem !important; font-weight: 500 !important;
    padding: 6px 12px !important; height: auto !important;
    transition: all 0.12s !important;
}
.team-bar-btn button:hover {
    border-color: rgba(255,255,255,0.12) !important; color: #6a6a7e !important;
}
.team-bar-btn button:focus { box-shadow: none !important; }

/* ── Suggestion cards (empty state) ─────────────── */
.suggest-card [data-testid="stButton"] button {
    background: #0c0c14 !important;
    border: 1px solid rgba(255,255,255,0.065) !important;
    color: #7a7a8e !important; border-radius: 14px !important;
    padding: 18px 20px !important; height: auto !important;
    min-height: 72px !important; width: 100% !important;
    text-align: left !important; font-size: 0.83rem !important;
    font-weight: 500 !important; line-height: 1.5 !important;
    transition: all 0.2s ease !important; cursor: pointer !important;
    letter-spacing: -0.01em !important;
}
.suggest-card [data-testid="stButton"] button:hover {
    background: #101019 !important;
    border-color: rgba(0,232,122,0.2) !important;
    color: #e8e8f2 !important;
    box-shadow: 0 6px 24px rgba(0,0,0,0.5), 0 0 0 1px rgba(0,232,122,0.08) !important;
    transform: translateY(-2px) !important;
}
.suggest-card [data-testid="stButton"] button:focus { box-shadow: none !important; }

/* ── Clarification pills (broad selectors) ────────── */
[data-testid="stPillsInput"],
[data-testid="stChatMessage"] [data-testid="stPillsInput"] {
    background: transparent !important; border: none !important; padding: 0 !important;
}
[data-testid="stPillsInput"] > div,
[data-testid="stPillsInput"] [role="tablist"] { gap: 7px !important; flex-wrap: wrap !important; }
[data-testid="stPillsInput"] button,
[data-testid="stPillsInput"] [role="tab"] {
    background: #0f0f17 !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    color: #7a7a8e !important; border-radius: 20px !important;
    font-size: 0.78rem !important; font-weight: 500 !important;
    padding: 6px 15px !important; transition: all 0.15s !important;
    white-space: nowrap !important;
}
[data-testid="stPillsInput"] button:hover,
[data-testid="stPillsInput"] [role="tab"]:hover {
    border-color: rgba(0,232,122,0.28) !important; color: #00e87a !important;
    background: rgba(0,232,122,0.05) !important;
}
[data-testid="stPillsInput"] button[aria-selected="true"],
[data-testid="stPillsInput"] [role="tab"][aria-selected="true"] {
    background: rgba(0,232,122,0.09) !important;
    border-color: rgba(0,232,122,0.5) !important;
    color: #00e87a !important; font-weight: 600 !important;
}
[data-testid="stPillsInput"] label { display: none !important; }

/* ── Clarification action buttons (broad selectors) ── */
.clarify-go button,
.clarify-go [data-testid="stButton"] button,
.clarify-go [data-testid="baseButton-secondary"] {
    background: #00e87a !important; color: #030806 !important;
    border: none !important; border-radius: 10px !important;
    height: 42px !important; font-size: 0.84rem !important;
    font-weight: 700 !important; letter-spacing: -0.01em !important;
    transition: opacity 0.15s, transform 0.1s !important; width: 100% !important;
}
.clarify-go button:hover,
.clarify-go [data-testid="stButton"] button:hover {
    opacity: 0.88 !important; transform: translateY(-1px) !important;
}
.clarify-go button:disabled,
.clarify-go [data-testid="stButton"] button:disabled,
.clarify-go [data-testid="baseButton-secondary"]:disabled {
    background: #141420 !important; color: #2e2e3c !important; opacity: 1 !important;
    transform: none !important;
}
.clarify-go button:focus { box-shadow: none !important; }

.clarify-skip button,
.clarify-skip [data-testid="stButton"] button,
.clarify-skip [data-testid="baseButton-secondary"] {
    background: #0c0c14 !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
    color: #3e3e50 !important; border-radius: 10px !important;
    height: 42px !important; font-size: 0.79rem !important; font-weight: 500 !important;
    width: 100% !important; transition: all 0.15s !important;
}
.clarify-skip button:hover,
.clarify-skip [data-testid="stButton"] button:hover {
    border-color: rgba(255,255,255,0.13) !important; color: #7a7a8e !important;
    background: #101019 !important;
}
.clarify-skip button:focus { box-shadow: none !important; }
</style>
""", unsafe_allow_html=True)

# ── Logo SVG ──────────────────────────────────────────────────────────────────
def _logo_svg(size: int = 36) -> str:
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg">'
        f'<rect width="40" height="40" rx="10" fill="#00e87a"/>'
        f'<path d="M11 8h12c3.9 0 7 3.1 7 7s-3.1 7-7 7h-5l8 10h-6l-8-10V8z M11 8v26" '
        f'stroke="#020905" stroke-width="2.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
        f'<line x1="7" y1="34" x2="33" y2="34" stroke="#020905" stroke-width="1" opacity="0.18"/>'
        f'</svg>'
    )

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

    st.markdown(f"""
    <div style="text-align:center; padding: 0 0 2.8rem;">
        <div style="display:inline-flex;align-items:center;justify-content:center;
                    margin-bottom:1.6rem;
                    filter:drop-shadow(0 0 28px rgba(0,232,122,0.22));">
            {_logo_svg(64)}
        </div>
        <div style="font-size:1.75rem;font-weight:800;color:#f2f2fa;
                    letter-spacing:-0.055em;line-height:1.05;margin-bottom:0.35rem;">The Regista</div>
        <div style="font-size:0.72rem;font-weight:600;letter-spacing:0.18em;
                    text-transform:uppercase;color:#2e2e3c;margin-bottom:1.1rem;">FPL AI ADVISOR</div>
        <div style="font-size:0.875rem;color:#3e3e50;line-height:1.75;max-width:310px;margin:0 auto;">
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
    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:10px;padding-bottom:1.3rem;
                border-bottom:1px solid rgba(255,255,255,0.055);margin-bottom:1.2rem;">
        <div style="flex-shrink:0;filter:drop-shadow(0 0 8px rgba(0,232,122,0.15));">
            {_logo_svg(32)}
        </div>
        <div>
            <div style="font-size:0.92rem;font-weight:800;color:#f2f2fa;
                        letter-spacing:-0.03em;line-height:1.15;">The Regista</div>
            <div style="font-size:0.59rem;color:#252530;letter-spacing:0.1em;
                        text-transform:uppercase;margin-top:2px;font-weight:600;">FPL · AI · Multi-agent</div>
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
        '<div style="position:fixed;bottom:1.2rem;font-size:0.58rem;color:#16161e;'
        'letter-spacing:0.03em;font-weight:500;">The Regista · LangGraph</div>',
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
        "intro":    "One quick question to sharpen my transfer advice:",
        "questions": [
            {
                "id":      "risk_tolerance",
                "text":    "How do you feel about taking a points hit for an extra transfer?",
                "options": ["Avoid hits — only free transfers", "Happy to hit if clearly worth it", "Aggressive — hits don't scare me"],
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


def _squad_pitch_html(lineup: dict | None = None) -> str:
    """Render the agent's suggested lineup as a pitch visualization.

    Only renders when `lineup` (parsed from [LINEUP_START]...[LINEUP_END]) is provided.
    Returns empty string otherwise — never falls back to current FPL picks.
    """
    try:
        from agent import data as fpl_data

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

        # No lineup block from agent — do not fall back to current picks
        else:
            return ""

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


# ── Dashboard renderer ────────────────────────────────────────────────────────

def _fdr_chip(fdr_str: str) -> str:
    """Return a colored FDR badge span."""
    try:
        v = float(re.sub(r"[^\d.]", "", fdr_str.split(",")[0]))
    except Exception:
        return f'<span style="color:#8b8c9e;">{fdr_str}</span>'
    if v <= 2:
        bg, fg = "rgba(0,100,60,0.5)", "#34d399"
    elif v == 3:
        bg, fg = "rgba(100,70,0,0.5)", "#f59e0b"
    elif v == 4:
        bg, fg = "rgba(140,30,0,0.5)", "#f87171"
    else:
        bg, fg = "rgba(100,0,0,0.6)", "#ef4444"
    return (
        f'<span style="background:{bg};color:{fg};padding:2px 8px;border-radius:5px;'
        f'font-weight:700;font-size:0.74rem;white-space:nowrap;">{fdr_str}</span>'
    )


def _parse_md_table(text: str) -> tuple[list[str], list[list[str]]]:
    """Parse a markdown table into (headers, rows). Skips separator rows."""
    lines = [l for l in text.strip().splitlines() if l.strip().startswith("|")]
    if len(lines) < 3:
        return [], []
    headers = [c.strip() for c in lines[0].split("|")[1:-1]]
    rows = []
    for line in lines[2:]:
        if re.match(r"^\s*\|[\s\-\|:]+\|\s*$", line):
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if cells:
            rows.append(cells)
    return headers, rows


def _render_checks_html(content: str) -> str:
    """Render reality-check lines as colored status cards."""
    cards = []
    for line in content.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        ok   = line.startswith("✅")
        fail = line.startswith("❌")
        color  = "#34d399" if ok else ("#f87171" if fail else "#8b8c9e")
        bg     = "rgba(0,200,100,0.05)" if ok else ("rgba(239,68,68,0.06)" if fail else "transparent")
        border = "rgba(0,200,100,0.18)" if ok else ("rgba(239,68,68,0.18)" if fail else "rgba(255,255,255,0.06)")
        cards.append(
            f'<div style="padding:9px 14px;background:{bg};border:1px solid {border};'
            f'border-radius:8px;font-size:0.8rem;color:{color};line-height:1.55;margin-bottom:6px;">'
            f'{line}</div>'
        )
    return '<div style="margin-bottom:4px;">' + "".join(cards) + '</div>'


def _render_transfer_cards_html(content: str) -> str:
    """Render 🔄 OUT → IN lines as visual split cards."""
    xfer_re = re.compile(
        r"🔄\s*OUT:\s*(.+?)\s*\(£([\d.]+)m\)\s*[→\-]+\s*IN:\s*(.+?)\s*\(£([\d.]+)m\)",
        re.IGNORECASE,
    )
    footer_re = re.compile(r"💰\s*(.+)", re.IGNORECASE)

    cards, footer_html = [], ""
    for line in content.strip().splitlines():
        m = xfer_re.search(line)
        if m:
            out_name, out_p, in_name, in_p = (
                m.group(1).strip(), float(m.group(2)),
                m.group(3).strip(), float(m.group(4)),
            )
            diff      = in_p - out_p
            diff_str  = (f"+£{diff:.1f}m" if diff > 0 else f"-£{abs(diff):.1f}m") if diff else "±£0"
            diff_col  = "#f87171" if diff > 0.05 else ("#34d399" if diff < -0.05 else "#6b7280")
            cards.append(f"""
<div style="display:flex;align-items:stretch;border-radius:12px;overflow:hidden;
            border:1px solid rgba(255,255,255,0.07);margin-bottom:10px;box-shadow:0 4px 16px rgba(0,0,0,0.3);">
  <div style="flex:1;background:rgba(239,68,68,0.07);padding:14px 18px;">
    <div style="font-size:0.57rem;font-weight:800;letter-spacing:0.12em;text-transform:uppercase;
                color:#f87171;margin-bottom:5px;">Transferring out</div>
    <div style="font-size:1.05rem;font-weight:700;color:#f0f0f5;letter-spacing:-0.025em;line-height:1.2;">{out_name}</div>
    <div style="font-size:0.8rem;color:#6b7280;margin-top:3px;">£{out_p:.1f}m</div>
  </div>
  <div style="display:flex;align-items:center;padding:0 14px;background:#07070d;flex-shrink:0;">
    <div style="text-align:center;">
      <div style="font-size:1.2rem;color:#2a2a3a;line-height:1;">→</div>
      <div style="font-size:0.65rem;font-weight:700;color:{diff_col};margin-top:3px;">{diff_str}</div>
    </div>
  </div>
  <div style="flex:1;background:rgba(0,232,122,0.07);padding:14px 18px;">
    <div style="font-size:0.57rem;font-weight:800;letter-spacing:0.12em;text-transform:uppercase;
                color:#00e87a;margin-bottom:5px;">Bringing in</div>
    <div style="font-size:1.05rem;font-weight:700;color:#f0f0f5;letter-spacing:-0.025em;line-height:1.2;">{in_name}</div>
    <div style="font-size:0.8rem;color:#6b7280;margin-top:3px;">£{in_p:.1f}m</div>
  </div>
</div>""")
        fm = footer_re.search(line)
        if fm:
            footer_html = (
                f'<div style="font-size:0.78rem;color:#3a3a50;padding:3px 2px 10px;">💰 {fm.group(1)}</div>'
            )
    if not cards:
        return f'<div style="font-size:0.875rem;color:#8b8c9e;">{content}</div>'
    return "".join(cards) + footer_html


def _render_starting_xi_html(content: str) -> str:
    """Render the Starting XI table with color-coded FDR and xPts mini-bars."""
    table_lines, other_lines = [], []
    in_table = False
    for line in content.strip().splitlines():
        if line.strip().startswith("|"):
            in_table = True
            table_lines.append(line)
        else:
            if in_table and not line.strip():
                in_table = False
            if not in_table:
                other_lines.append(line)

    if not table_lines:
        return f'<div style="font-size:0.875rem;color:#8b8c9e;white-space:pre-wrap;">{content}</div>'

    headers, rows = _parse_md_table("\n".join(table_lines))
    if not headers:
        return f'<div style="font-size:0.875rem;color:#8b8c9e;white-space:pre-wrap;">{content}</div>'

    h_lower = [h.lower().strip("* ") for h in headers]

    def _col_idx(name):
        for i, h in enumerate(h_lower):
            if name in h:
                return i
        return -1

    fdr_idx  = _col_idx("fdr")
    xpts_idx = _col_idx("xpts")

    def _xpts_bar(val_str: str) -> str:
        clean = re.sub(r"[~+\s]", "", val_str)
        try:
            v   = float(clean)
            pct = min(100, max(0, v / 14 * 100))
            return (
                f'<div style="display:flex;align-items:center;gap:7px;">'
                f'<div style="flex:1;max-width:60px;height:4px;background:rgba(255,255,255,0.06);'
                f'border-radius:3px;overflow:hidden;">'
                f'<div style="width:{pct:.0f}%;height:100%;background:#00e87a;border-radius:3px;"></div>'
                f'</div>'
                f'<span style="font-size:0.76rem;color:#d4d4e0;font-weight:600;">{val_str}</span>'
                f'</div>'
            )
        except Exception:
            return val_str

    header_cells = "".join(
        f'<th style="text-align:left;padding:9px 13px;font-size:0.59rem;font-weight:700;'
        f'letter-spacing:0.09em;text-transform:uppercase;color:#3a7a5a;'
        f'border-bottom:1px solid rgba(0,232,122,0.09);background:rgba(0,232,122,0.04);">'
        f'{h.strip("* ")}</th>'
        for h in headers
    )

    row_htmls = []
    for i, row in enumerate(rows):
        player_raw = row[0].strip("* ") if row else ""
        is_total   = "total" in player_raw.lower()
        is_bonus   = "bonus" in player_raw.lower() or "c bonus" in player_raw.lower()
        row_bg     = "rgba(0,232,122,0.04)" if is_total else ("transparent" if i % 2 else "rgba(255,255,255,0.008)")

        cells = []
        for j, cell in enumerate(row):
            cell_clean = cell.strip("* ").strip()

            if j == fdr_idx and cell_clean and not is_total and not is_bonus:
                inner = _fdr_chip(cell_clean)
            elif j == xpts_idx and not is_total and not is_bonus:
                inner = _xpts_bar(cell_clean)
            elif j == xpts_idx and (is_total or is_bonus):
                inner = f'<span style="color:#00e87a;font-weight:700;font-size:0.85rem;">{cell_clean}</span>'
            elif j == 0 and is_total:
                inner = f'<span style="font-weight:700;color:#f0f0f5;">{cell_clean}</span>'
            elif j == 0:
                inner = f'<span style="color:#d4d4e0;font-weight:500;">{cell_clean}</span>'
            else:
                inner = f'<span style="color:#7a7a8e;">{cell_clean}</span>'

            cells.append(
                f'<td style="padding:8px 13px;border-bottom:1px solid rgba(255,255,255,0.03);'
                f'font-size:0.8rem;background:{row_bg};">{inner}</td>'
            )
        row_htmls.append(f'<tr>{"".join(cells)}</tr>')

    risk_html = ""
    for line in other_lines:
        if line.strip().startswith("⚠️"):
            risk_html = (
                f'<div style="margin-top:10px;padding:9px 14px;background:rgba(245,158,11,0.07);'
                f'border:1px solid rgba(245,158,11,0.18);border-radius:8px;'
                f'font-size:0.8rem;color:#d97706;line-height:1.55;">{line.strip()}</div>'
            )

    return (
        f'<div style="border:1px solid rgba(255,255,255,0.07);border-radius:10px;'
        f'overflow:hidden;margin-bottom:14px;box-shadow:0 4px 20px rgba(0,0,0,0.25);">'
        f'<table style="width:100%;border-collapse:collapse;">'
        f'<thead><tr>{header_cells}</tr></thead>'
        f'<tbody>{"".join(row_htmls)}</tbody>'
        f'</table></div>'
        + risk_html
    )


def _analysis_table_html(table_lines: list[str]) -> str:
    """Render a markdown table in the analysis section with light styling."""
    headers, rows = _parse_md_table("\n".join(table_lines))
    if not headers or not rows:
        return ""
    h_lower = [h.lower().strip("* ") for h in headers]

    header_cells = "".join(
        f'<th style="text-align:left;padding:7px 11px;font-size:0.59rem;font-weight:700;'
        f'letter-spacing:0.08em;text-transform:uppercase;color:#3a7a5a;'
        f'border-bottom:1px solid rgba(0,232,122,0.08);background:rgba(0,232,122,0.03);">'
        f'{h.strip("* ")}</th>'
        for h in headers
    )

    row_htmls = []
    for i, row in enumerate(rows):
        cells = []
        for j, (h, cell) in enumerate(zip(h_lower, row)):
            cell_clean = cell.strip("* ").strip()
            is_highlighted = "✓" in cell_clean or cell_clean.endswith("✓")

            if "fdr" in h and cell_clean:
                nums = re.findall(r"\d+(?:\.\d+)?", cell_clean)
                if nums:
                    inner = _fdr_chip(nums[0])
                else:
                    inner = f'<span style="color:#8b8c9e;">{cell_clean}</span>'
            elif "score" in h or "weighted" in h:
                inner = f'<span style="color:#00e87a;font-weight:600;">{cell_clean}</span>'
            elif j == 0:
                color = "#d4d4e0" if is_highlighted else "#a0a0b0"
                fw = "600" if is_highlighted else "400"
                inner = f'<span style="color:{color};font-weight:{fw};">{cell_clean}</span>'
            else:
                inner = f'<span style="color:#7a7a8e;">{cell_clean}</span>'

            cells.append(
                f'<td style="padding:6px 11px;border-bottom:1px solid rgba(255,255,255,0.03);font-size:0.78rem;">'
                f'{inner}</td>'
            )
        row_htmls.append(f'<tr>{"".join(cells)}</tr>')

    return (
        f'<div style="border:1px solid rgba(255,255,255,0.06);border-radius:8px;'
        f'overflow:hidden;margin:8px 0;">'
        f'<table style="width:100%;border-collapse:collapse;">'
        f'<thead><tr>{header_cells}</tr></thead>'
        f'<tbody>{"".join(row_htmls)}</tbody>'
        f'</table></div>'
    )


def _render_analysis_html(content: str) -> str:
    """Render the DATA-BACKED ANALYSIS section as styled HTML."""
    parts       = []
    table_buf   = []
    text_buf    = []

    def flush_table():
        if table_buf:
            parts.append(_analysis_table_html(table_buf))
            table_buf.clear()

    def flush_text():
        if text_buf:
            parts.append(_analysis_text_block(text_buf))
            text_buf.clear()

    for line in content.strip().splitlines():
        if line.strip().startswith("|"):
            flush_text()
            table_buf.append(line)
        else:
            flush_table()
            text_buf.append(line)

    flush_table()
    flush_text()
    return "".join(parts)


def _analysis_text_block(lines: list[str]) -> str:
    parts = []
    for line in lines:
        s = line.strip()
        if not s:
            parts.append('<div style="height:4px;"></div>')
        elif s.startswith("🔄 TRANSFER"):
            parts.append(
                f'<div style="font-size:0.65rem;font-weight:800;letter-spacing:0.1em;'
                f'text-transform:uppercase;color:#00e87a;padding:14px 0 4px;'
                f'border-top:1px solid rgba(255,255,255,0.05);margin-top:6px;">{s}</div>'
            )
        elif s.startswith(("📋", "👑")):
            parts.append(
                f'<div style="font-size:0.65rem;font-weight:800;letter-spacing:0.1em;'
                f'text-transform:uppercase;color:#5a5a70;padding:14px 0 4px;'
                f'border-top:1px solid rgba(255,255,255,0.04);margin-top:4px;">{s}</div>'
            )
        elif s.startswith("━") or s.startswith("─") or s.startswith("===="):
            pass  # skip horizontal dividers
        elif s.lower().startswith("verdict"):
            parts.append(
                f'<div style="padding:9px 14px;background:rgba(0,232,122,0.05);'
                f'border-left:2px solid #00e87a;border-radius:0 7px 7px 0;margin:8px 0;'
                f'font-size:0.8rem;color:#c8c8d8;line-height:1.6;">{s}</div>'
            )
        elif s.lower().startswith(("key factor", "closest call")):
            parts.append(
                f'<div style="font-size:0.79rem;color:#5a5a6e;padding:3px 0;">{s}</div>'
            )
        elif s.startswith("- "):
            parts.append(
                f'<div style="font-size:0.79rem;color:#52526a;padding:2px 0 2px 12px;'
                f'line-height:1.55;">{s}</div>'
            )
        elif s.startswith("captain_score"):
            parts.append(
                f'<div style="font-size:0.72rem;color:#3a3a50;padding:2px 0;font-family:monospace;">{s}</div>'
            )
        else:
            parts.append(
                f'<div style="font-size:0.8rem;color:#8b8c9e;line-height:1.65;padding:2px 0;">{s}</div>'
            )
    return "".join(parts)


_DASH_SECTION_RE = re.compile(
    r"(?:^|\n)((?:🔍|📝|📋|📊|💡)[^\n]*)\n",
    re.MULTILINE,
)
_DASH_EMOJI_MAP = {
    "🔍": "reality_checks",
    "📝": "transfer_summary",
    "📋": "lineup",
    "📊": "starting_xi",
    "💡": "analysis",
}


def _is_dashboard_output(text: str) -> bool:
    return any(h in text for h in ("🔍 REALITY", "📝 TRANSFER SUMMARY", "📊 STARTING XI"))


_DIVIDER_RE = re.compile(r"^[━─=\-]{3,}\s*$", re.MULTILINE)


def _clean_section(text: str) -> str:
    """Remove horizontal divider lines and strip whitespace."""
    return _DIVIDER_RE.sub("", text).strip()


def _split_dashboard_sections(text: str) -> list[tuple[str, str]]:
    boundaries = []
    for m in re.finditer(r"(?:^|\n)((?:🔍|📝|📋|📊|💡)[^\n]*)", text, re.MULTILINE):
        emoji = m.group(1).strip()[0]
        sec   = _DASH_EMOJI_MAP.get(emoji, "other")
        boundaries.append((m.start(1), m.end(), sec))

    if not boundaries:
        return [("other", text)]

    sections = []
    pre = _clean_section(text[: boundaries[0][0]])
    if pre:
        sections.append(("other", pre))
    for i, (start, end, sec) in enumerate(boundaries):
        next_start = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
        content = _clean_section(text[end:next_start])
        sections.append((sec, content))
    return sections


def _render_section_header(label: str, color: str = "#3a3a50"):
    st.markdown(
        f'<div style="font-size:0.6rem;font-weight:800;letter-spacing:0.12em;'
        f'text-transform:uppercase;color:{color};padding:18px 0 8px;">{label}</div>',
        unsafe_allow_html=True,
    )


def _render_final_output(raw_text: str, lineup: dict | None = None):
    """Parse and render the final_reviewer output as a dashboard."""
    text = _strip_lineup_block(raw_text)

    if not _is_dashboard_output(text):
        # Plain response — render as markdown then pitch
        st.markdown(text)
        _pitch = _squad_pitch_html(lineup=lineup)
        if _pitch:
            st.markdown(_pitch, unsafe_allow_html=True)
        return

    sections      = _split_dashboard_sections(text)
    pitch_done    = False

    for sec_type, content in sections:

        # ── Reality Checks ──────────────────────────────────────────
        if sec_type == "reality_checks":
            _render_section_header("🔍  Reality checks", "#3a7a5a")
            html = _render_checks_html(content)
            if html:
                st.markdown(html, unsafe_allow_html=True)

        # ── Transfer Summary ─────────────────────────────────────────
        elif sec_type == "transfer_summary":
            _render_section_header("⇄  Transfers", "#3a7a5a")
            html = _render_transfer_cards_html(content)
            if html:
                st.markdown(html, unsafe_allow_html=True)

        # ── Suggested Lineup (pitch visual replaces the text) ────────
        elif sec_type == "lineup":
            _render_section_header("📋  Suggested lineup", "#3a7a5a")
            if not pitch_done:
                _pitch = _squad_pitch_html(lineup=lineup)
                if _pitch:
                    st.markdown(_pitch, unsafe_allow_html=True)
                    pitch_done = True
                else:
                    st.markdown(content)
            # else: skip duplicate lineup section

        # ── Starting XI Form & Fixtures ──────────────────────────────
        elif sec_type == "starting_xi":
            _render_section_header("📊  Starting XI — form & fixtures", "#3a7a5a")
            html = _render_starting_xi_html(content)
            if html:
                st.markdown(html, unsafe_allow_html=True)
            else:
                st.markdown(content)

        # ── Data-Backed Analysis (collapsible) ───────────────────────
        elif sec_type == "analysis":
            with st.expander("💡  Detailed data analysis", expanded=False):
                html = _render_analysis_html(content)
                if html:
                    st.markdown(html, unsafe_allow_html=True)
                else:
                    st.markdown(content)

        # ── Fallback ─────────────────────────────────────────────────
        elif content.strip():
            st.markdown(content)

    # If pitch never rendered (no lineup section in output), append at end
    if not pitch_done and lineup:
        _render_section_header("📋  Suggested lineup", "#3a7a5a")
        _pitch = _squad_pitch_html(lineup=lineup)
        if _pitch:
            st.markdown(_pitch, unsafe_allow_html=True)


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
    st.markdown(f"""
    <div style="text-align:center;padding:4rem 0 3rem;">
        <div style="display:inline-flex;align-items:center;justify-content:center;
                    margin-bottom:1.4rem;filter:drop-shadow(0 0 22px rgba(0,232,122,0.18));">
            {_logo_svg(52)}
        </div>
        <div style="font-size:1.55rem;font-weight:800;color:#f2f2fa;
                    letter-spacing:-0.05em;margin-bottom:0.3rem;line-height:1.1;">The Regista</div>
        <div style="font-size:0.69rem;font-weight:600;letter-spacing:0.18em;
                    text-transform:uppercase;color:#252530;margin-bottom:1rem;">Your FPL AI Advisor</div>
        <div style="font-size:0.84rem;color:#3a3a4e;max-width:280px;margin:0 auto;line-height:1.75;">
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
    st.markdown(f"""
    <div style="padding:1.1rem 0 0.8rem;border-bottom:1px solid rgba(255,255,255,0.055);margin-bottom:0.6rem;">
        <div style="display:flex;align-items:center;justify-content:space-between;">
            <div style="display:flex;align-items:center;gap:9px;">
                <div style="filter:drop-shadow(0 0 6px rgba(0,232,122,0.12));">{_logo_svg(26)}</div>
                <span style="font-size:0.9rem;font-weight:800;color:#f2f2fa;letter-spacing:-0.03em;">The Regista</span>
            </div>
            <div style="display:flex;align-items:center;gap:5px;">
                <span style="width:6px;height:6px;border-radius:50%;background:#00e87a;display:inline-block;
                             box-shadow:0 0 8px rgba(0,232,122,0.55);"></span>
                <span style="font-size:0.62rem;font-weight:700;color:#00e87a;letter-spacing:0.07em;text-transform:uppercase;">Live</span>
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
            _hist_lineup = _parse_lineup_block(_msg["content"])
            _render_final_output(_msg["content"], lineup=_hist_lineup)

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

        # Extract lineup block and render full dashboard
        _lineup_data = _parse_lineup_block(_final_out or "")
        if _final_out:
            _render_final_output(_final_out, lineup=_lineup_data)

    # Save raw content (with lineup block intact) so it can be re-parsed on history replay
    st.session_state.messages.append({
        "role":    "assistant",
        "content": _final_out or "No response generated.",
        "log":     _log,
    })
