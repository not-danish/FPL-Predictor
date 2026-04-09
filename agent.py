"""
FPL Agent — extracts all setup from test.ipynb into an importable module.
Call get_model() to get the compiled LangGraph model (cached after first call).
Call clear_tool_cache() before each run to flush HTTP response cache.
"""

import os
import re
import json
import logging
import requests
import pandas as pd
from typing import Annotated
from typing_extensions import TypedDict
from collections import Counter
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_core.messages import (
    RemoveMessage, SystemMessage, HumanMessage, AIMessage, ToolMessage
)
from langchain_openai import ChatOpenAI
from langchain_experimental.utilities import PythonREPL
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import create_react_agent
from langgraph_supervisor import create_supervisor

load_dotenv()

# ── Working directory (prompts loaded with relative paths) ────────────────────
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# ── File logger ───────────────────────────────────────────────────────────────
log = logging.getLogger("fpl_agent")
log.setLevel(logging.DEBUG)
if not log.handlers:
    _fh = logging.FileHandler("fpl_agent.log", encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)-5s] %(message)s",
                                        datefmt="%Y-%m-%d %H:%M:%S"))
    log.addHandler(_fh)

# ── Shared HTTP session with retry logic ─────────────────────────────────────
_session = requests.Session()
_retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
_session.mount("https://", HTTPAdapter(max_retries=_retry))

# ── FPL Bootstrap data (fetched once at import time) ─────────────────────────
base_url = "https://fantasy.premierleague.com/api/"
data = json.loads(_session.get(base_url + "bootstrap-static", timeout=15).text)

# ── HTTP response cache ───────────────────────────────────────────────────────
_tool_cache: dict = {}

def _cached_get(url: str) -> str:
    if url in _tool_cache:
        log.debug("CACHE HIT  %s", url)
        return _tool_cache[url]
    log.info("HTTP GET   %s", url)
    try:
        _tool_cache[url] = _session.get(url, timeout=15).text
        log.debug("HTTP OK    %s (%d bytes)", url, len(_tool_cache[url]))
    except requests.exceptions.RequestException as e:
        log.error("HTTP ERROR %s — %s", url, e)
        return json.dumps({"error": str(e)})
    return _tool_cache[url]

def clear_tool_cache():
    """Flush cached HTTP responses. Call before each graph run."""
    log.info("--- tool cache cleared (new run) ---")
    _tool_cache.clear()

# ── Helper functions ──────────────────────────────────────────────────────────
def get_player_name_from_id(player_id: Annotated[int, "The ID of the EPL player."]) -> str:
    """Look up the name of an EPL player given their player ID."""
    df = pd.DataFrame(data["elements"])
    row = df[df["id"] == player_id]
    if row.empty:
        return f"No data found for player ID: {player_id}"
    return f"{row.iloc[0]['first_name']} {row.iloc[0]['second_name']}"

def get_team_name_from_id(team_id: Annotated[int, "The ID of the EPL team."]) -> str:
    """Look up the name of an EPL team given their team ID."""
    df = pd.DataFrame(data["teams"])
    row = df[df["id"] == team_id]
    if row.empty:
        return f"No data found for team ID: {team_id}"
    return row.iloc[0]["name"]

def get_player_team(player_id: int) -> str:
    df = pd.DataFrame(data["elements"])
    row = df[df["id"] == player_id]
    if row.empty:
        return f"No data found for player ID: {player_id}"
    return get_team_name_from_id(row.iloc[0]["team"])

# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def team_data(team_id: Annotated[int, "The unique identifier for the Premier League Team. Use -1 for all teams."]) -> str:
    """Look up team-level performance data for EPL teams.
    If team_id = -1, returns data for all teams.
    strength fields are ratings between 1000 (worst) and 1400 (best)."""
    df = pd.DataFrame(data["teams"])
    df = df.drop(columns=["code", "draw", "form", "loss", "played", "points",
                           "strength", "team_division", "unavailable", "win"], errors="ignore")
    df = df.rename(columns={"id": "team_id"})
    if team_id == -1:
        return df.to_markdown()
    row = df[df["team_id"] == team_id]
    return row.to_markdown() if not row.empty else f"No data for team ID: {team_id}"

@tool
def fpl_scoring_rules(pos: Annotated[str, "Position code: GKP, DEF, MID, or FWD"]) -> str:
    """Look up FPL scoring rules for a given position.
    long_play: 60+ minutes. short_play: under 60 minutes."""
    scoring_data = dict(data["game_config"]["scoring"])
    for rule in scoring_data:
        if isinstance(scoring_data[rule], dict):
            scoring_data[rule] = scoring_data[rule][pos]
    df = pd.DataFrame([scoring_data])
    drop_cols = ["bps", "bonus", "influence", "creativity", "threat", "ict_index",
                 "tackles", "clearances_blocks_interceptions", "recoveries", "saves",
                 "expected_goals_conceded", "expected_goal_involvements",
                 "mng_clean_sheets", "mng_underdog_win", "mng_underdog_draw",
                 "mng_win", "mng_draw", "mng_loss", "mng_goals_scored",
                 "expected_goals", "expected_assists", "starts", "special_multiplier"]
    df = df.drop(columns=[c for c in drop_cols if c in df.columns])
    return df.to_markdown()

@tool
def player_types() -> str:
    """Look up the different player types/positions in FPL."""
    df = pd.DataFrame(data["element_types"])
    df["squad_min_select"] = [1, 3, 3, 1]
    df["squad_max_select"] = [2, 5, 5, 3]
    df = df.drop(columns=["id", "plural_name", "plural_name_short", "singular_name",
                           "ui_shirt_specific"], errors="ignore")
    df = df.rename(columns={"singular_name_short": "position_code"})
    return df.to_markdown()

@tool
def fixture_info_for_gw(gw: Annotated[int, "The FPL gameweek number."]) -> str:
    """Look up match information for a specific gameweek."""
    url = f"https://fantasy.premierleague.com/api/fixtures/?event={gw}"
    df = pd.DataFrame(json.loads(_cached_get(url)))
    if df.empty:
        return f"No match data found for gameweek: {gw}"
    df = df.rename(columns={"id": "fixture_id"})
    df = df.drop(columns=["code", "finished_provisional", "provisional_start_time",
                           "stats", "pulse_id"], errors="ignore")
    df["team_a"] = df["team_a"].apply(get_team_name_from_id)
    df["team_h"] = df["team_h"].apply(get_team_name_from_id)
    return df.to_markdown()

@tool
def get_team_fixtures(
    team_name: Annotated[str, "Exact team name as shown in FPL data, e.g. 'Chelsea', 'Man Utd', 'Nott'm Forest'."],
    num_gws: Annotated[int, "Number of upcoming gameweeks to show (1-6)."] = 3,
) -> str:
    """Get a team's upcoming fixtures with opponents, home/away, and FDR
    pre-computed. Use this instead of parsing raw fixture_info_for_gw output."""
    # Find the team's id
    teams_df = pd.DataFrame(data["teams"])
    match = teams_df[teams_df["name"] == team_name]
    if match.empty:
        # Try case-insensitive partial match
        match = teams_df[teams_df["name"].str.lower().str.contains(team_name.lower())]
    if match.empty:
        return f"Team '{team_name}' not found. Available teams: {', '.join(teams_df['name'].tolist())}"
    team_id = int(match.iloc[0]["id"])

    # Find next GW
    events_df = pd.DataFrame(data["events"])
    next_rows = events_df[events_df["is_next"] == True]
    if next_rows.empty:
        return "Could not determine next gameweek."
    next_gw = int(next_rows.iloc[0]["id"])

    # Fetch fixtures for each upcoming GW
    rows = []
    for gw in range(next_gw, next_gw + min(num_gws, 6)):
        url = f"https://fantasy.premierleague.com/api/fixtures/?event={gw}"
        fix = json.loads(_cached_get(url))
        for f in fix:
            if f["team_h"] == team_id:
                opp = get_team_name_from_id(f["team_a"])
                rows.append({"GW": gw, "opponent": opp, "venue": "H",
                             "FDR": f.get("team_h_difficulty", "?")})
            elif f["team_a"] == team_id:
                opp = get_team_name_from_id(f["team_h"])
                rows.append({"GW": gw, "opponent": opp, "venue": "A",
                             "FDR": f.get("team_a_difficulty", "?")})

    if not rows:
        return f"No upcoming fixtures found for {team_name}."

    result_df = pd.DataFrame(rows)
    avg_fdr = result_df["FDR"].mean()
    lines = [f"**{team_name}** — next {len(rows)} fixtures (avg FDR: {avg_fdr:.1f}):"]
    lines.append(result_df.to_markdown(index=False))
    return "\n".join(lines)

@tool
def fixture_stats(
    fixture_id: Annotated[int, "The fixture ID."],
    stat: Annotated[str, "One of: goals_scored, assists, own_goals, penalties_saved, penalties_missed, yellow_cards, red_cards, saves, bonus, bps, defensive_contribution"]
) -> str:
    """Look up specific stats for a fixture."""
    url = f"{base_url}fixtures/?id={fixture_id}"
    raw = json.loads(_cached_get(url))
    if len(raw) < 3:
        return f"No data found for fixture ID: {fixture_id}"
    fixture_data = raw[2]
    stats = fixture_data.get("stats", [])
    if not stats:
        return f"No stats found for fixture ID: {fixture_id}"
    df = pd.DataFrame(stats)
    if stat not in df["identifier"].values:
        return f"Stat '{stat}' not found for fixture ID: {fixture_id}"
    df = df[df["identifier"] == stat]
    stat_values = []
    for _, row in df.iterrows():
        for side in ["h", "a"]:
            for item in row[side]:
                stat_values.append({"element": item["element"], "value": item["value"]})
    result = pd.DataFrame(stat_values)
    result = result.rename(columns={"value": stat, "element": "player_id"})
    return result.sort_values(by=stat, ascending=False).to_markdown()

@tool
def current_gw_status() -> str:
    """Look up the current gameweek number and live status."""
    url = base_url + "event-status"
    response = requests.get(url)
    if response.status_code != 200:
        return f"Failed to retrieve GW status. HTTP {response.status_code}"
    return pd.DataFrame(json.loads(response.text)).to_markdown()

@tool
def fpl_gw_info(gw: Annotated[int, "The FPL gameweek number."]) -> str:
    """Look up information about a specific gameweek."""
    df = pd.DataFrame(data["events"])
    row = df[df["id"] == gw]
    if row.empty:
        return f"No data found for gameweek: {gw}"
    row = row.rename(columns={
        "id": "gameweek", "name": "gameweek_name",
        "top_element": "highest_scoring_player_id",
        "top_element_info": "highest_scoring_player_points",
        "most_captained": "most_captained_player_id",
        "most_vice_captained": "most_vice_captained_player_id",
    })
    row["highest_scoring_player_points"] = row["highest_scoring_player_points"].apply(
        lambda x: x["points"] if isinstance(x, dict) else None
    )
    drop_cols = ["overrides", "cup_leagues_created", "h2h_ko_matches_created",
                 "can_enter", "can_manage", "chip_plays",
                 "deadline_time_game_offset", "deadline_time_epoch"]
    row = row.drop(columns=[c for c in drop_cols if c in row.columns])
    return row.to_markdown()

@tool
def fpl_league_standings(league_id: Annotated[int, "The FPL league ID."]) -> str:
    """Look up standings for a specific FPL league."""
    url = f"https://fantasy.premierleague.com/api/leagues-classic/{league_id}/standings/"
    raw = json.loads(_cached_get(url))
    df = pd.DataFrame(raw["standings"]["results"])
    if df.empty:
        return f"No standings data for league ID: {league_id}"
    df = df.drop(columns=["id", "rank_sort", "has_played"], errors="ignore")
    df = df.rename(columns={
        "entry": "fpl_team_id", "entry_name": "fpl_team_name",
        "event_total": "gw_points", "player_name": "fpl_manager_name",
        "rank": "current_rank", "total": "total_fpl_points",
    })
    df["movement"] = df["last_rank"] - df["current_rank"]
    return df.to_markdown()

@tool
def most_valuable_fpl_teams() -> str:
    """Look up the most valuable FPL teams in the current season."""
    url = base_url + "stats/most-valuable-teams"
    df = pd.DataFrame(json.loads(_cached_get(url)))
    if df.empty:
        return "No data found."
    df = df.rename(columns={
        "entry": "fpl_team_id", "name": "fpl_team_name",
        "player_name": "fpl_manager_name", "value": "fpl_team_value",
    })
    df["value_with_bank"] = df["value_with_bank"] / 10
    return df.to_markdown()

@tool
def fpl_team_players(
    user_id: Annotated[int, "The user's FPL team ID."],
    gw: Annotated[int, "FPL gameweek number (1-38). Use the current or most recent gameweek."],
) -> str:
    """Look up the players in a user's FPL team for a specific gameweek."""
    url = f"https://fantasy.premierleague.com/api/entry/{user_id}/event/{gw}/picks/"
    raw = json.loads(_cached_get(url))
    if "picks" not in raw:
        _tool_cache.pop(url, None)
        return f"No picks data for user_id={user_id}, gw={gw}. API said: {raw}"
    df = pd.json_normalize(raw["picks"])
    df = df.rename(columns={
        "element": "player_id", "position": "squad_position",
        "multiplier": "captain_multiplier", "element_type": "player_position",
    })
    df["player_position"] = df["player_position"].replace({1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"})
    df["player_name"] = df["player_id"].apply(get_player_name_from_id)
    df["team_name"] = df["player_id"].apply(get_player_team)

    events_df = pd.DataFrame(data["events"])
    next_gw_rows = events_df[events_df["is_next"] == True]
    current_gw_rows = events_df[events_df["is_current"] == True]
    if not next_gw_rows.empty:
        next_gw = int(next_gw_rows.iloc[0]["id"])
    elif not current_gw_rows.empty:
        next_gw = int(current_gw_rows.iloc[0]["id"])
    else:
        next_gw = None

    if next_gw:
        fix_url = f"https://fantasy.premierleague.com/api/fixtures/?event={next_gw}"
        fix_df = pd.DataFrame(json.loads(_cached_get(fix_url)))
        if fix_df.empty:
            teams_with_fixture, teams_with_double = set(), set()
        else:
            home = fix_df["team_h"].apply(get_team_name_from_id).tolist()
            away = fix_df["team_a"].apply(get_team_name_from_id).tolist()
            teams_with_fixture = set(home + away)
            counts = Counter(home + away)
            teams_with_double = {t for t, c in counts.items() if c >= 2}

        def get_next_gw_status(team):
            if team not in teams_with_fixture:
                return f"BLANK (no GW{next_gw} fixture)"
            elif team in teams_with_double:
                return f"DOUBLE (two GW{next_gw} fixtures)"
            return "NORMAL"

        df["next_gw_status"] = df["team_name"].apply(get_next_gw_status)

    return df.to_markdown()

@tool
def fpl_team_budget(
    user_id: Annotated[int, "The user's FPL team ID."],
    gw: Annotated[int, "The current or most recent gameweek number."],
) -> str:
    """Look up the user's current bank balance (ITB) in FPL."""
    url = f"https://fantasy.premierleague.com/api/entry/{user_id}/event/{gw}/picks/"
    raw = json.loads(_cached_get(url))
    if "entry_history" not in raw:
        _tool_cache.pop(url, None)
        return f"No budget data for user_id={user_id}, gw={gw}. API said: {raw}"
    bank = raw["entry_history"].get("bank", 0) / 10
    value = raw["entry_history"].get("value", 0) / 10
    return f"Bank (ITB): £{bank}m | Squad value: £{value}m"

@tool
def player_stats_by_fixture(player_id: Annotated[int, "The EPL player ID."]) -> str:
    """Look up per-fixture stats for a player this season."""
    url = f"{base_url}element-summary/{player_id}/"
    raw = json.loads(_cached_get(url))
    if not raw.get("history"):
        return f"No stats found for player ID: {player_id}"
    df = pd.DataFrame(raw["history"])
    df = df.rename(columns={"fixture": "fixture_id", "element": "player_id",
                             "total_points": "points", "round": "gw"})
    df["value"] = df["value"] / 10
    df["opponent_team"] = df["opponent_team"].apply(get_team_name_from_id)
    df["player_name"] = df["player_id"].apply(get_player_name_from_id)
    cols = ["player_id", "player_name", "fixture_id", "opponent_team", "gw", "minutes",
            "goals_scored", "assists", "clean_sheets", "goals_conceded", "own_goals",
            "penalties_saved", "penalties_missed", "yellow_cards", "red_cards",
            "saves", "bonus", "bps", "value", "points"]
    return df[[c for c in cols if c in df.columns]].to_markdown()

@tool
def player_upcoming_fixtures(player_id: Annotated[int, "The EPL player ID."]) -> str:
    """Look up upcoming fixtures for a player. Covers next 6 GWs. Marks BLANK and DOUBLE gameweeks."""
    url = f"{base_url}element-summary/{player_id}/"
    raw = json.loads(_cached_get(url))
    raw_df = pd.DataFrame(raw.get("fixtures", []))

    events_df = pd.DataFrame(data["events"])
    next_gw_rows = events_df[events_df["is_next"] == True]
    current_gw_rows = events_df[events_df["is_current"] == True]
    if not next_gw_rows.empty:
        start_gw = int(next_gw_rows.iloc[0]["id"])
    elif not current_gw_rows.empty:
        start_gw = int(current_gw_rows.iloc[0]["id"])
    else:
        start_gw = None

    gw_to_fixtures = {}
    if not raw_df.empty:
        raw_df = raw_df.rename(columns={"id": "fixture_id", "event": "gw"})
        raw_df = raw_df.dropna(subset=["gw"])
        raw_df["gw"] = raw_df["gw"].astype(int)
        raw_df["team_h"] = raw_df["team_h"].apply(get_team_name_from_id)
        raw_df["team_a"] = raw_df["team_a"].apply(get_team_name_from_id)
        for gw_num, group in raw_df.groupby("gw"):
            gw_to_fixtures[gw_num] = group

    if start_gw is None:
        start_gw = min(gw_to_fixtures.keys()) if gw_to_fixtures else 1

    end_gw = min(start_gw + 5, 38)
    player_name = get_player_name_from_id(player_id)
    rows = []
    for gw in range(start_gw, end_gw + 1):
        fixtures_this_gw = gw_to_fixtures.get(gw, pd.DataFrame())
        count = len(fixtures_this_gw)
        if count == 0:
            rows.append({"player_id": player_id, "player_name": player_name,
                         "fixture_id": None, "team_h": None, "team_a": None,
                         "is_home": None, "difficulty": None,
                         "gw": gw, "kickoff_time": None, "gameweek_type": "BLANK"})
        else:
            gw_type = "DOUBLE" if count >= 2 else "NORMAL"
            for _, row in fixtures_this_gw.iterrows():
                rows.append({"player_id": player_id, "player_name": player_name,
                             "fixture_id": row["fixture_id"],
                             "team_h": row["team_h"], "team_a": row["team_a"],
                             "is_home": row.get("is_home"), "difficulty": row.get("difficulty"),
                             "gw": gw, "kickoff_time": row.get("kickoff_time"),
                             "gameweek_type": gw_type})
    return pd.DataFrame(rows).to_markdown()

@tool
def premier_league_players(
    position: Annotated[str, "Filter by position: GKP, DEF, MID, FWD, or ALL."] = "ALL",
    max_price: Annotated[float, "Max price in millions (e.g. 8.5). Use 0 to disable."] = 0,
) -> str:
    """Look up EPL players. Always filter by position and max_price to avoid large results."""
    df = pd.DataFrame(data["elements"])
    # Exclude players who have left PL clubs (status='u' = unavailable/departed)
    df = df[df["status"] != "u"]
    df = df.rename(columns={"id": "player_id", "team": "team_id",
                             "element_type": "position", "now_cost": "price"})
    df["team_name"] = df["team_id"].apply(get_team_name_from_id)
    df["player_name"] = df["first_name"] + " " + df["second_name"]
    df["price"] = df["price"] / 10
    df = df[["player_id", "player_name", "team_name", "position", "price"]]
    df = df.replace({"position": {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}})
    if position != "ALL":
        df = df[df["position"] == position]
    if max_price > 0:
        df = df[df["price"] <= max_price]
    if df.empty:
        return f"No players found for position={position}, max_price={max_price}"
    return df.to_markdown()

@tool
def get_top_form_players(
    position: Annotated[str, "Position filter: GKP, DEF, MID, or FWD."],
    max_price: Annotated[float, "Hard budget cap in millions (e.g. 5.8). No player above this price will be returned."],
    top_n: Annotated[int, "Number of top candidates to return (default 15)."] = 15,
    min_minutes_per_gw: Annotated[float, "Minimum average minutes per GW to filter non-starters (default 45)."] = 45,
) -> str:
    """Return the top N players by current FPL form rating for a given position
    and budget, sorted best-to-worst. Use this INSTEAD OF premier_league_players
    as your starting shortlist — it surfaces candidates from all teams ranked by
    form, not alphabetically by team.

    Each row includes:
    - player_id, player_name, team_name, price
    - form: FPL rolling form score (weighted recent pts/GW)
    - pts_per_game: season average pts/GW
    - total_points: season total
    - minutes: season minutes played
    - goals_scored, assists, clean_sheets (season totals)
    - selected_by_percent: ownership %

    After getting this list, call get_player_summary(player_id) for the top
    candidates to get per-GW breakdown and fixture data.
    """
    df = pd.DataFrame(data["elements"])
    pos_map = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
    df["position_name"] = df["element_type"].map(pos_map)
    df = df[df["position_name"] == position]

    # Filter out players who are no longer at a PL club (status='u' = unavailable/departed)
    df = df[df["status"] != "u"]

    df["price"] = df["now_cost"] / 10
    df = df[df["price"] <= max_price]

    # Filter out non-starters by average minutes per GW played
    df["form"] = pd.to_numeric(df["form"], errors="coerce").fillna(0)
    df["minutes"] = pd.to_numeric(df["minutes"], errors="coerce").fillna(0)

    # Calculate avg minutes per GW (use games played as proxy from minutes/90)
    df["gws_played"] = (df["minutes"] / 90).clip(lower=1)
    df["avg_min_per_gw"] = df["minutes"] / df["gws_played"].clip(lower=1)
    df = df[df["avg_min_per_gw"] >= min_minutes_per_gw]

    if df.empty:
        return f"No players found for position={position}, max_price={max_price}m with avg ≥{min_minutes_per_gw} min/GW."

    df = df.sort_values("form", ascending=False).head(top_n)

    df["team_name"] = df["team"].apply(get_team_name_from_id)
    df["player_name"] = df["first_name"] + " " + df["second_name"]
    df["pts_per_game"] = pd.to_numeric(df["points_per_game"], errors="coerce").fillna(0)

    # ── Pre-fetch next-3-GW fixture FDR for all players (uses cached GW endpoints) ──
    team_avg_fdr: dict = {}
    try:
        _ev = pd.DataFrame(data["events"])
        _next = _ev[_ev["is_next"] == True]
        if not _next.empty:
            next_gw = int(_next.iloc[0]["id"])
            _fdr_lists: dict = {}
            for _gw in range(next_gw, next_gw + 3):
                _url = f"https://fantasy.premierleague.com/api/fixtures/?event={_gw}"
                for _f in json.loads(_cached_get(_url)):
                    for _tid, _key in [(_f["team_h"], "team_h_difficulty"),
                                        (_f["team_a"], "team_a_difficulty")]:
                        _fdr_lists.setdefault(_tid, []).append(_f.get(_key, 3))
            team_avg_fdr = {
                tid: round(sum(v) / len(v), 1) for tid, v in _fdr_lists.items()
            }
    except Exception:
        pass

    df["avg_fdr_3gw"] = df["team"].map(team_avg_fdr)

    # id column is named "id" in bootstrap
    df = df.rename(columns={"id": "player_id"})
    keep = [c for c in ["player_id", "player_name", "team_name", "price", "form",
                        "pts_per_game", "total_points", "minutes",
                        "goals_scored", "assists", "clean_sheets",
                        "selected_by_percent", "avg_fdr_3gw"] if c in df.columns]
    result = df[keep].reset_index(drop=True)
    lines = [
        f"Top {len(result)} {position} players by FPL form (≤ £{max_price}m, avg ≥ {min_minutes_per_gw} min/GW):",
        "avg_fdr_3gw = average fixture difficulty for next 3 GWs (lower = easier). Use this for fixture scoring — no need to call get_team_fixtures for every candidate.",
        result.to_markdown(index=False),
    ]
    return "\n".join(lines)


repl = PythonREPL()

@tool
def python_repl_tool(code: Annotated[str, "Python code to execute."]) -> str:
    """Execute Python code. Use print() to see output."""
    try:
        result = repl.run(code)
    except BaseException as e:
        return f"Failed to execute. Error: {repr(e)}"
    return f"```python\n{code}\n```\nOutput:\n```\n{result}```"

# ── Consolidated tools (replace pairs that always get called together) ─────────

@tool
def get_player_summary(player_id: Annotated[int, "The EPL player ID."]) -> str:
    """Get a player's recent form, underlying stats, AND upcoming fixtures.

    Returns:
    - SEASON STATS: xG/90, xA/90, xGI/90, xGC/90, ICT index rank, threat rank,
      creativity rank, penalty/FK taker status — use these to assess true quality
      beyond FPL points.
    - RECENT FORM (last 6 GW): pts, goals, assists, xG, xA, xGI, ICT per game.
    - UPCOMING FIXTURES (next 5 GW): opponent, H/A, FDR.
    """
    url = f"{base_url}element-summary/{player_id}/"
    raw = json.loads(_cached_get(url))

    player_name = get_player_name_from_id(player_id)
    player_team = get_player_team(player_id)

    # ── Season per-90 stats from bootstrap ────────────────────────────────────
    el_map = {e["id"]: e for e in data["elements"]}
    el = el_map.get(player_id, {})
    pos_map = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
    pos = pos_map.get(el.get("element_type"), "?")

    def _f(v, dp=2):
        try: return round(float(v), dp)
        except: return "—"

    # Set piece / penalty taker flags
    pen_order = el.get("penalties_order") or 0
    fk_order  = el.get("direct_freekicks_order") or 0
    ck_order  = el.get("corners_and_indirect_freekicks_order") or 0
    sp_notes = []
    if pen_order == 1: sp_notes.append("1st penalty taker")
    elif pen_order == 2: sp_notes.append("2nd penalty taker")
    if fk_order == 1: sp_notes.append("1st FK taker")
    if ck_order == 1: sp_notes.append("corner taker")
    sp_str = ", ".join(sp_notes) if sp_notes else "none"

    lines = [
        f"**{player_name}** (ID: {player_id}) | Team: {player_team} | Pos: {pos}",
        "",
        "SEASON STATS (per 90 mins):",
        f"  xG/90: {_f(el.get('expected_goals_per_90'))} | "
        f"xA/90: {_f(el.get('expected_assists_per_90'))} | "
        f"xGI/90: {_f(el.get('expected_goal_involvements_per_90'))}",
        f"  xGC/90: {_f(el.get('expected_goals_conceded_per_90'))} | "
        f"GC/90: {_f(el.get('goals_conceded_per_90'))} | "
        f"CS/90: {_f(el.get('clean_sheets_per_90'))}",
        f"  ICT index: {_f(el.get('ict_index'),1)} (rank #{el.get('ict_index_rank','?')} overall) | "
        f"Threat rank: #{el.get('threat_rank','?')} | "
        f"Creativity rank: #{el.get('creativity_rank','?')}",
        f"  Def. contribution/90: {_f(el.get('defensive_contribution_per_90'))} | "
        f"Starts/90: {_f(el.get('starts_per_90'))}",
        f"  Set pieces: {sp_str}",
    ]

    # ── Recent form: last 6 GWs with xG/xA/ICT ────────────────────────────────
    history = raw.get("history", [])
    if history:
        df = pd.DataFrame(history[-6:])
        df = df.rename(columns={"round": "gw", "total_points": "pts",
                                 "expected_goals": "xG",
                                 "expected_assists": "xA",
                                 "expected_goal_involvements": "xGI",
                                 "expected_goals_conceded": "xGC"})
        df["opp"] = df["opponent_team"].apply(get_team_name_from_id)
        df["h/a"] = df["was_home"].map({True: "H", False: "A"})
        # Round xG columns
        for col in ["xG", "xA", "xGI", "xGC"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").round(2)
        keep = ["gw", "opp", "h/a", "minutes", "goals_scored", "assists",
                "clean_sheets", "goals_conceded", "xG", "xA", "xGI", "xGC",
                "ict_index", "pts"]
        df = df[[c for c in keep if c in df.columns]]
        lines.append("\nRECENT FORM (last 6 GW):")
        lines.append(df.to_markdown(index=False))
        # Compute form_avg from last 5 GW pts rows
        if "pts" in df.columns:
            last5_pts = pd.to_numeric(df["pts"], errors="coerce").dropna().tail(5)
            if not last5_pts.empty:
                form_avg = round(last5_pts.mean(), 1)
                lines.append(f"\nform_avg (last 5 GW): {form_avg} pts/GW")
    else:
        lines.append("\nNo recent form data.")

    # ── Upcoming fixtures: next 5 GWs ─────────────────────────────────────────
    fixtures = raw.get("fixtures", [])
    events_df = pd.DataFrame(data["events"])
    next_rows = events_df[events_df["is_next"] == True]
    cur_rows  = events_df[events_df["is_current"] == True]
    start_gw  = (int(next_rows.iloc[0]["id"]) if not next_rows.empty
                 else int(cur_rows.iloc[0]["id"]) if not cur_rows.empty else 1)

    rows = []
    gw_to_fix = {}
    if fixtures:
        fdf = pd.DataFrame(fixtures)
        fdf = fdf.dropna(subset=["event"])
        fdf["event"] = fdf["event"].astype(int)
        for gw_num, grp in fdf.groupby("event"):
            gw_to_fix[gw_num] = grp

    for gw in range(start_gw, min(start_gw + 5, 39)):
        grp = gw_to_fix.get(gw, pd.DataFrame())
        if grp.empty:
            rows.append({"gw": gw, "opponent": "BLANK", "h/a": "-", "fdr": "-", "type": "BLANK"})
        else:
            gw_type = "DGW" if len(grp) >= 2 else "NORMAL"
            for _, r in grp.iterrows():
                opp_id = r["team_h"] if not r.get("is_home") else r["team_a"]
                opp = get_team_name_from_id(int(opp_id))
                rows.append({"gw": gw, "opponent": opp,
                             "h/a": "H" if r.get("is_home") else "A",
                             "fdr": r.get("difficulty", "-"), "type": gw_type})

    if rows:
        lines.append("\nUPCOMING FIXTURES (next 5 GW):")
        lines.append(pd.DataFrame(rows).to_markdown(index=False))

    return "\n".join(lines)


@tool
def get_user_team(
    user_id: Annotated[int, "The user's FPL team ID."],
    gw: Annotated[int, "Current or most recent gameweek number."],
) -> str:
    """Get the user's full squad AND budget in one call.
    Use this instead of calling fpl_team_players and fpl_team_budget separately."""
    url = f"https://fantasy.premierleague.com/api/entry/{user_id}/event/{gw}/picks/"
    raw = json.loads(_cached_get(url))

    if "picks" not in raw:
        _tool_cache.pop(url, None)
        return f"No team data for user_id={user_id}, gw={gw}. API said: {raw}"

    # Budget
    eh = raw.get("entry_history", {})
    bank  = eh.get("bank", 0) / 10
    value = eh.get("value", 0) / 10

    # Free transfers for next GW: if 0 transfers were used this GW, they rolled → 2 FTs; else 1 FT
    prev_transfers = eh.get("event_transfers", 1)
    free_transfers = 2 if prev_transfers == 0 else 1

    lines = [f"**Budget** — ITB: £{bank}m | Squad value: £{value}m | Free transfers available: {free_transfers}"]

    # Squad
    df = pd.json_normalize(raw["picks"])
    df = df.rename(columns={"element": "player_id", "position": "slot",
                             "multiplier": "cap_mult", "element_type": "pos"})
    df["pos"]  = df["pos"].replace({1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"})
    df["name"] = df["player_id"].apply(get_player_name_from_id)
    _el_df = pd.DataFrame(data["elements"])
    df["web_name"] = df["player_id"].apply(
        lambda pid: _el_df.loc[_el_df["id"] == pid, "web_name"].iloc[0]
        if not _el_df.loc[_el_df["id"] == pid].empty else str(pid)
    )
    df["team"] = df["player_id"].apply(get_player_team)

    # Next GW blank/double status
    events_df = pd.DataFrame(data["events"])
    next_rows = events_df[events_df["is_next"] == True]
    cur_rows  = events_df[events_df["is_current"] == True]
    next_gw   = (int(next_rows.iloc[0]["id"]) if not next_rows.empty
                 else int(cur_rows.iloc[0]["id"]) if not cur_rows.empty else None)

    if next_gw:
        fix_url = f"https://fantasy.premierleague.com/api/fixtures/?event={next_gw}"
        fix_df  = pd.DataFrame(json.loads(_cached_get(fix_url)))
        if not fix_df.empty:
            home   = fix_df["team_h"].apply(get_team_name_from_id).tolist()
            away   = fix_df["team_a"].apply(get_team_name_from_id).tolist()
            played = set(home + away)
            double = {t for t, c in Counter(home + away).items() if c >= 2}
            def _status(t):
                if t not in played: return f"BLANK(GW{next_gw})"
                if t in double:     return f"DGW{next_gw}"
                return "OK"
            df["next_gw"] = df["team"].apply(_status)

    # Include player_id and web_name so downstream agents can use correct names
    keep = ["slot", "player_id", "pos", "name", "web_name", "team", "cap_mult"]
    if "next_gw" in df.columns:
        keep.append("next_gw")
    lines.append("\n**Squad:**")
    lines.append(df[keep].to_markdown(index=False))
    return "\n".join(lines)


@tool
def get_squad_analysis(
    user_id: Annotated[int, "The user's FPL team ID."],
    gw: Annotated[int, "Current or most recent finished gameweek number."],
) -> str:
    """Get the user's full squad pre-ranked by sell urgency using only in-memory data.

    Returns all 15 squad players with: position, price, FPL form score, season
    minutes, season points, status (a/i/d/s/n), and injury news — sorted so the
    highest-priority sell candidates appear at the top.

    Use this INSTEAD OF get_user_team + multiple get_player_summary calls for the
    outgoing recommender. After calling this, only call get_player_summary for the
    TOP 2-3 actual sell candidates to get their per-GW breakdown.
    """
    url = f"https://fantasy.premierleague.com/api/entry/{user_id}/event/{gw}/picks/"
    raw = json.loads(_cached_get(url))
    if "picks" not in raw:
        _tool_cache.pop(url, None)
        return f"No team data for user_id={user_id}, gw={gw}. API said: {raw}"

    eh = raw.get("entry_history", {})
    bank = eh.get("bank", 0) / 10
    value = eh.get("value", 0) / 10
    prev_transfers = eh.get("event_transfers", 1)
    free_transfers = 2 if prev_transfers == 0 else 1

    elements = {e["id"]: e for e in data["elements"]}
    pos_map = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}

    rows = []
    for pick in raw["picks"]:
        el = elements.get(pick["element"], {})
        pos = pos_map.get(el.get("element_type"), "UNK")
        status = el.get("status", "a")
        form = float(el.get("form", 0) or 0)
        minutes = int(el.get("minutes", 0) or 0)
        total_pts = int(el.get("total_points", 0) or 0)
        news = (el.get("news", "") or "")[:60]
        price = (el.get("now_cost", 0) or 0) / 10
        team_id = el.get("team")
        team_name = get_team_name_from_id(team_id) if team_id else "Unknown"

        # Sell urgency (lower number = higher priority to sell)
        if status in ("i", "s", "n"):
            urgency = 0
        elif status == "d":
            urgency = 0.5
        elif minutes == 0:
            urgency = 1.0
        else:
            urgency = 2.0 + form  # high form = low priority to sell

        rows.append({
            "_urgency": urgency,
            "player_id": pick["element"],
            "name": get_player_name_from_id(pick["element"]),
            "pos": pos,
            "team": team_name,
            "price": f"£{price}m",
            "status": status,
            "fpl_form": form,
            "minutes": minutes,
            "season_pts": total_pts,
            "news": news,
        })

    rows.sort(key=lambda x: x["_urgency"])
    for r in rows:
        del r["_urgency"]

    df = pd.DataFrame(rows)
    lines = [
        f"**Budget** — ITB: £{bank}m | Squad value: £{value}m | Free transfers: {free_transfers}",
        "\n**Squad ranked by sell priority** (top rows = highest urgency to sell):",
        df.to_markdown(index=False),
        "\nSTATUS KEY: a=available, i=injured, d=doubtful, s=suspended, n=not available",
        "NOTE: Call get_player_summary(player_id) ONLY for the top 2-3 sell candidates to get per-GW history.",
    ]
    return "\n".join(lines)


@tool
def get_squad_club_counts(
    user_id: Annotated[int, "The user's FPL team ID."],
    gw: Annotated[int, "Current or most recent FINISHED gameweek number."],
    transfer_out: Annotated[str, "Name of the player being sold (or empty string if none)."] = "",
    transfer_in: Annotated[str, "Name of the player being bought (or empty string if none)."] = "",
) -> str:
    """Get club-by-club player counts for a squad, optionally applying a
    proposed transfer. Use this to verify the 3-per-club limit."""
    url = f"https://fantasy.premierleague.com/api/entry/{user_id}/event/{gw}/picks/"
    raw = json.loads(_cached_get(url))
    if "picks" not in raw:
        return f"No team data for user_id={user_id}, gw={gw}."

    elements = {e["id"]: e for e in data["elements"]}
    teams_map = {t["id"]: t["name"] for t in data["teams"]}
    pos_map = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}

    squad = []
    for p in raw["picks"]:
        el = elements.get(p["element"])
        if not el:
            continue
        squad.append({
            "name": el.get("web_name", el["second_name"]),
            "full_name": (el.get("first_name", "") + " " + el.get("second_name", "")).strip(),
            "team": teams_map.get(el["team"], "Unknown"),
            "pos": pos_map.get(el["element_type"], "UNK"),
        })

    # Apply transfer if specified
    transfer_note = ""
    if transfer_out:
        out_lower = transfer_out.lower()
        removed = False
        for i, s in enumerate(squad):
            if out_lower in s["full_name"].lower() or out_lower in s["name"].lower():
                transfer_note += f"OUT: {s['name']} ({s['team']}, {s['pos']})\n"
                squad.pop(i)
                removed = True
                break
        if not removed:
            transfer_note += f"⚠️ Could not find '{transfer_out}' in squad to remove.\n"

    if transfer_in:
        # Find the incoming player in bootstrap data
        in_lower = transfer_in.lower()
        in_el = None
        for e in data["elements"]:
            full = (e.get("first_name", "") + " " + e.get("second_name", "")).lower()
            web = e.get("web_name", "").lower()
            if in_lower == web or in_lower == full or in_lower in full or in_lower in web:
                in_el = e
                break
        if in_el:
            in_team = teams_map.get(in_el["team"], "Unknown")
            in_pos = pos_map.get(in_el["element_type"], "UNK")
            squad.append({"name": in_el.get("web_name", ""), "team": in_team, "pos": in_pos})
            transfer_note += f"IN: {in_el.get('web_name', '')} ({in_team}, {in_pos})\n"
        else:
            transfer_note += f"⚠️ Could not find '{transfer_in}' in player database.\n"

    # Count by club
    club_counts = Counter(s["team"] for s in squad)
    # Count by position
    pos_counts = Counter(s["pos"] for s in squad)

    lines = []
    if transfer_note:
        lines.append(f"TRANSFER APPLIED:\n{transfer_note}")
    lines.append("CLUB COUNTS (after transfer):")
    for club, count in sorted(club_counts.items()):
        players_at_club = [s["name"] for s in squad if s["team"] == club]
        flag = " ❌ EXCEEDS LIMIT" if count > 3 else ""
        lines.append(f"  {club}: {count} [{', '.join(players_at_club)}]{flag}")

    violations = [c for c, n in club_counts.items() if n > 3]
    lines.append(f"\nPOSITION COUNTS: {dict(pos_counts)}")
    if violations:
        lines.append(f"\n❌ CLUB LIMIT VIOLATED: {', '.join(violations)}")
    else:
        lines.append("\n✅ All clubs ≤ 3 players.")
    return "\n".join(lines)


@tool
def get_team_stats(
    team_name: Annotated[str, "Team name as shown in FPL (e.g. 'Chelsea', 'Man Utd', 'Nott\\'m Forest')."],
) -> str:
    """Get a team's season-long attacking and defensive stats split by home and away.

    Returns goals scored/conceded, clean sheets, and average per game — home vs away.
    Also shows the last 5 results with scorelines.

    Use this to:
    - Assess whether a team's attackers are worth targeting (high scoring home/away)
    - Assess whether a team's defenders/GKP are worth targeting (low conceding, high CS rate)
    - Understand how dangerous an upcoming OPPONENT is (if they score 2+ away per game,
      your defender playing against them has a low CS ceiling)
    """
    teams_df = pd.DataFrame(data["teams"])
    match = teams_df[teams_df["name"] == team_name]
    if match.empty:
        match = teams_df[teams_df["name"].str.lower().str.contains(team_name.lower(), na=False)]
    if match.empty:
        return f"Team '{team_name}' not found. Available: {', '.join(teams_df['name'].tolist())}"
    team_id = int(match.iloc[0]["id"])

    # Fetch all season fixtures (one cached call)
    all_fix = json.loads(_cached_get(f"{base_url}fixtures/"))

    home_games, away_games = [], []
    for f in all_fix:
        if not f.get("finished"):
            continue
        if f["team_h"] == team_id:
            home_games.append({
                "gw": f.get("event"), "opp": get_team_name_from_id(f["team_a"]),
                "gf": f.get("team_h_score", 0), "ga": f.get("team_a_score", 0),
            })
        elif f["team_a"] == team_id:
            away_games.append({
                "gw": f.get("event"), "opp": get_team_name_from_id(f["team_h"]),
                "gf": f.get("team_a_score", 0), "ga": f.get("team_h_score", 0),
            })

    def _stats(games):
        if not games:
            return None
        n = len(games)
        gf = sum(g["gf"] for g in games)
        ga = sum(g["ga"] for g in games)
        cs = sum(1 for g in games if g["ga"] == 0)
        return {
            "n": n, "gf": gf, "ga": ga, "cs": cs,
            "avg_gf": round(gf / n, 2), "avg_ga": round(ga / n, 2),
            "cs_pct": round(cs / n * 100),
        }

    h = _stats(home_games)
    a = _stats(away_games)

    lines = [f"**{team_name}** — Season stats (finished fixtures)"]
    for label, s in [("HOME", h), ("AWAY", a)]:
        if not s:
            continue
        lines.append(
            f"\n{label} ({s['n']} games): "
            f"GF {s['gf']} (avg {s['avg_gf']}/g) | "
            f"GA {s['ga']} (avg {s['avg_ga']}/g) | "
            f"CS {s['cs']}/{s['n']} ({s['cs_pct']}%)"
        )

    # Last 5 results
    recent = sorted(home_games + away_games, key=lambda x: x.get("gw") or 0)[-5:]
    lines.append("\nLAST 5 RESULTS:")
    for g in recent:
        result = "W" if g["gf"] > g["ga"] else ("D" if g["gf"] == g["ga"] else "L")
        venue = "H" if g in home_games else "A"
        lines.append(f"  GW{g['gw']} vs {g['opp']} ({venue}): {g['gf']}-{g['ga']} {result}")

    # Set-piece & strength context from bootstrap
    row = match.iloc[0]
    lines.append(
        f"\nFPL STRENGTH RATINGS: "
        f"Att H={row.get('strength_attack_home')} A={row.get('strength_attack_away')} | "
        f"Def H={row.get('strength_defence_home')} A={row.get('strength_defence_away')}"
    )
    return "\n".join(lines)


@tool
def get_player_pattern_analysis(
    player_ids: Annotated[list[int], "List of FPL player IDs to analyse (max 15, typically your squad)."],
) -> str:
    """Deep pattern analysis for a list of players.

    For each player computes:
    - form_avg: mean FPL pts over last 5 GWs
    - momentum: avg pts last 3 GWs minus avg pts GWs 4-6 (positive = improving)
    - consistency: std deviation of last 5 GW pts (low = reliable, high = boom-bust)
    - xG_diff: season goals scored minus xG (positive = overperforming, negative = due a correction)
    - home_avg / away_avg: mean FPL pts at home vs away (last 6 GWs)
    - xGI/90: season expected goal involvements per 90 mins

    Returns a markdown table plus a FLAGGED PLAYERS section with automatic alerts.
    """
    elements_map = {e["id"]: e for e in data["elements"]}
    teams_map = {t["id"]: t["name"] for t in data["teams"]}
    pos_map = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}

    rows = []

    for pid in player_ids[:15]:
        el = elements_map.get(pid)
        if not el:
            continue

        name = el.get("web_name", str(pid))
        pos = pos_map.get(el["element_type"], "UNK")
        team = teams_map.get(el["team"], "UNK")
        price = round(el["now_cost"] / 10, 1)

        url = f"https://fantasy.premierleague.com/api/element-summary/{pid}/"
        raw = json.loads(_cached_get(url))
        history = raw.get("history", [])

        # next fixture FDR and H/A from element-summary fixtures array
        future = raw.get("fixtures", [])
        next_fdr = "—"
        next_ha = "—"
        if future:
            nf = future[0]
            next_fdr = nf.get("difficulty", "—")
            next_ha = "H" if nf.get("is_home") else "A"

        if not history:
            rows.append({
                "Player": name, "Pos": pos, "Team": team, "£": f"£{price}m",
                "form_avg": "N/A", "momentum": "N/A", "consistency": "N/A",
                "xG_diff": "N/A", "home_avg": "—", "away_avg": "—",
                "xGI/90": "N/A", "next_FDR": next_fdr, "next_HA": next_ha,
                "flags": "⚠️ No history data",
            })
            continue

        # form_avg: last 5 GWs
        last5 = history[-5:]
        pts5 = [h["total_points"] for h in last5]
        form_avg = round(sum(pts5) / len(pts5), 1) if pts5 else 0.0

        # momentum: recent 3 vs previous 3
        last3 = history[-3:]
        prev3 = history[-6:-3] if len(history) >= 6 else history[:-3]
        recent_avg = round(sum(h["total_points"] for h in last3) / max(len(last3), 1), 1)
        older_avg = round(sum(h["total_points"] for h in prev3) / max(len(prev3), 1), 1)
        momentum = round(recent_avg - older_avg, 1)
        m_icon = "📈" if momentum > 0.5 else ("📉" if momentum < -0.5 else "➡️")

        # consistency: std dev of last 5 pts
        if len(pts5) >= 2:
            mean5 = sum(pts5) / len(pts5)
            std_dev = round((sum((x - mean5) ** 2 for x in pts5) / len(pts5)) ** 0.5, 1)
        else:
            std_dev = 0.0
        consistency_label = "consistent" if std_dev < 2.5 else ("boom-bust" if std_dev > 4 else "moderate")

        # xG over/under-performance (whole season)
        total_goals = sum(h.get("goals_scored", 0) for h in history)
        total_xg = sum(float(h.get("expected_goals", 0) or 0) for h in history)
        xg_diff = round(total_goals - total_xg, 2)
        xg_label = "overperf" if xg_diff > 1.5 else ("underperf" if xg_diff < -1.5 else "on track")

        # home/away split (last 6 GWs)
        last6 = history[-6:]
        home_pts = [h["total_points"] for h in last6 if h.get("was_home")]
        away_pts = [h["total_points"] for h in last6 if not h.get("was_home")]
        home_avg = round(sum(home_pts) / len(home_pts), 1) if home_pts else "—"
        away_avg = round(sum(away_pts) / len(away_pts), 1) if away_pts else "—"

        # season xGI/90 from bootstrap
        season_xgi = round(float(el.get("expected_goal_involvements_per_90", 0) or 0), 2)

        # auto-flags
        flags = []
        if momentum < -1.5:
            flags.append("📉 declining form")
        if momentum > 1.5:
            flags.append("📈 rising form")
        if xg_diff > 2.0:
            flags.append("⚠️ xG overperforming (regression risk)")
        if xg_diff < -2.0:
            flags.append("💡 xG underperforming (correction due)")
        if std_dev > 4.5:
            flags.append("🎲 boom-bust scorer")
        if season_xgi >= 0.5:
            flags.append(f"⚡ elite xGI/90 ({season_xgi:.2f})")
        if form_avg < 2.0 and len(pts5) >= 3:
            flags.append("🔻 very low recent form")

        rows.append({
            "Player": name,
            "Pos": pos,
            "Team": team,
            "£": f"£{price}m",
            "form_avg": form_avg,
            "recent3": recent_avg,
            "prev3": older_avg,
            "momentum": f"{'+' if momentum >= 0 else ''}{momentum}{m_icon}",
            "std_dev": std_dev,
            "consistency": consistency_label,
            "xG_diff": f"{'+' if xg_diff >= 0 else ''}{xg_diff} ({xg_label})",
            "home_avg": home_avg,
            "away_avg": away_avg,
            "xGI/90": season_xgi,
            "next_FDR": next_fdr,
            "next_HA": next_ha,
            "flags": " | ".join(flags) if flags else "—",
        })

    if not rows:
        return "No player data found for the provided IDs."

    df = pd.DataFrame(rows)
    display_cols = ["Player", "Pos", "Team", "£", "form_avg", "momentum",
                    "std_dev", "consistency", "xG_diff", "home_avg", "away_avg", "xGI/90",
                    "next_FDR", "next_HA"]

    flagged = [r for r in rows if r["flags"] != "—"]

    lines = [
        "## PATTERN ANALYSIS REPORT",
        "",
        "### Player Pattern Table",
        df[display_cols].to_markdown(index=False),
        "",
        "### Flagged Players",
    ]
    if flagged:
        for r in flagged:
            lines.append(f"- **{r['Player']}** ({r['Pos']}, {r['Team']}): {r['flags']}")
    else:
        lines.append("- No notable flags detected.")

    return "\n".join(lines)


@tool
def get_gameweek_context() -> str:
    """Get current and next gameweek info: GW numbers, deadline, blank/double teams.
    Use this instead of calling current_gw_status and fpl_gw_info separately.
    No arguments needed."""
    events_df = pd.DataFrame(data["events"])
    cur  = events_df[events_df["is_current"] == True]
    nxt  = events_df[events_df["is_next"] == True]
    prev = events_df[events_df["is_previous"] == True]

    current_gw = int(cur.iloc[0]["id"])  if not cur.empty  else None
    next_gw    = int(nxt.iloc[0]["id"])  if not nxt.empty  else None
    prev_gw    = int(prev.iloc[0]["id"]) if not prev.empty else None

    lines = []
    if current_gw:
        row = cur.iloc[0]
        lines.append(f"Current GW: {current_gw} | Finished: {row['finished']}")
    if next_gw:
        row = nxt.iloc[0]
        lines.append(f"Next GW: {next_gw} | Deadline: {row['deadline_time']}")
    if prev_gw:
        lines.append(f"Previous GW: {prev_gw}")

    # Blank / double GW teams for next GW
    check_gw = next_gw or current_gw
    if check_gw:
        fix_url = f"https://fantasy.premierleague.com/api/fixtures/?event={check_gw}"
        fix_df  = pd.DataFrame(json.loads(_cached_get(fix_url)))
        all_teams = set(pd.DataFrame(data["teams"])["name"])
        if fix_df.empty:
            playing = set()
        else:
            home    = fix_df["team_h"].apply(get_team_name_from_id).tolist()
            away    = fix_df["team_a"].apply(get_team_name_from_id).tolist()
            playing = set(home + away)
            double  = {t for t, c in Counter(home + away).items() if c >= 2}
            blank   = all_teams - playing
            if blank:
                lines.append(f"Blank GW{check_gw} teams: {', '.join(sorted(blank))}")
            if double:
                lines.append(f"Double GW{check_gw} teams: {', '.join(sorted(double))}")
            if not blank and not double:
                lines.append(f"GW{check_gw}: no blanks or doubles")

    return "\n".join(lines) if lines else "Could not determine gameweek context."


@tool
def get_squad_transfer_scores(
    user_id: Annotated[int, "The user's FPL team ID."],
    gw: Annotated[int, "Current or most recent finished gameweek number."],
    num_candidates: Annotated[int, "Top N replacement candidates to return per position being transferred out (default 8)."] = 8,
) -> str:
    """One-shot transfer intelligence tool.

    Performs the full transfer analysis pipeline in a SINGLE call:

    SQUAD SCORING — scores every squad player (0-100) as a weighted average of:
      • form_score      (30%) — recent 5-GW pts average normalised to squad
      • fixture_score   (25%) — avg FDR over next 3 GWs, inverted (low FDR = high score)
      • minutes_score   (15%) — consistency of starts (season avg minutes / 90)
      • xgi_score       (15%) — xGI/90 normalised to position group
      • momentum_score  (10%) — recent 3 GW avg minus prior 3 GW avg
      • penalty_score   ( 5%) — 1st/2nd pen taker bonus

    STRATEGY DETECTION — automatically selects the best strategy lens:
      Fixture Targeting | Form & Stats Chasing | Minutes Certainty | Set-Piece Form

    TRANSFER RECOMMENDATIONS:
      • Flags bottom 1-2 squad players as sell candidates (lowest composite score),
        respecting the hard rule: form_avg ≥ 5.5 = cannot sell.
      • For each sell candidate's position, returns the top N replacement candidates
        from the full PL player pool (same position, budget-estimated, ranked by
        the same composite score). Candidates already in the squad are excluded.

    Returns:
      - STRATEGY SUMMARY section
      - SQUAD SCORES table (all 15 players ranked worst-to-best)
      - SELL CANDIDATES section (bottom players with scores and reasons)
      - REPLACEMENT CANDIDATES section per position (ranked, with scores)
    """
    # ── Load squad ─────────────────────────────────────────────────────────────
    url = f"https://fantasy.premierleague.com/api/entry/{user_id}/event/{gw}/picks/"
    raw = json.loads(_cached_get(url))
    if "picks" not in raw:
        return f"No team data for user_id={user_id}, gw={gw}."

    eh = raw.get("entry_history", {})
    bank  = eh.get("bank", 0) / 10
    value = eh.get("value", 0) / 10
    prev_transfers = eh.get("event_transfers", 1)
    free_transfers = 2 if prev_transfers == 0 else 1
    avg_player_price = round(value / 15, 1)

    elements_map = {e["id"]: e for e in data["elements"]}
    teams_map    = {t["id"]: t["name"] for t in data["teams"]}
    pos_map      = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}

    squad_ids = [p["element"] for p in raw["picks"]]

    # ── Pre-fetch FDR for all teams (next 3 GWs, single cached batch) ──────────
    events_df = pd.DataFrame(data["events"])
    next_rows = events_df[events_df["is_next"] == True]
    cur_rows  = events_df[events_df["is_current"] == True]
    next_gw   = (int(next_rows.iloc[0]["id"]) if not next_rows.empty
                 else int(cur_rows.iloc[0]["id"]) if not cur_rows.empty else None)

    team_fdr: dict[int, float] = {}   # team_id → avg FDR over next 3 GWs
    team_dgw: set[int] = set()        # teams with a double GW next GW
    if next_gw:
        fdr_lists: dict[int, list] = {}
        home_counts: Counter = Counter()
        away_counts: Counter = Counter()
        for gw_offset in range(3):
            fix_url = f"https://fantasy.premierleague.com/api/fixtures/?event={next_gw + gw_offset}"
            for f in json.loads(_cached_get(fix_url)):
                fdr_lists.setdefault(f["team_h"], []).append(f.get("team_h_difficulty", 3))
                fdr_lists.setdefault(f["team_a"], []).append(f.get("team_a_difficulty", 3))
                if gw_offset == 0:
                    home_counts[f["team_h"]] += 1
                    away_counts[f["team_a"]] += 1
        team_fdr = {tid: round(sum(v) / len(v), 2) for tid, v in fdr_lists.items()}
        # teams appearing more than once in GW fixtures = double
        for tid, cnt in (home_counts + away_counts).items():
            if cnt >= 2:
                team_dgw.add(tid)

    def _safe_float(v, default=0.0):
        try: return float(v or 0)
        except: return default

    # ── Score a single player element dict ─────────────────────────────────────
    def _score_player(pid: int, history: list | None = None) -> dict:
        el = elements_map.get(pid, {})
        pos = pos_map.get(el.get("element_type"), "UNK")
        team_id = el.get("team")
        price = round((el.get("now_cost", 0) or 0) / 10, 1)
        status = el.get("status", "a")
        name = (el.get("first_name", "") + " " + el.get("second_name", "")).strip()

        # Form from history (last 5 GWs)
        if history is None:
            hist_url = f"https://fantasy.premierleague.com/api/element-summary/{pid}/"
            hist_raw = json.loads(_cached_get(hist_url))
            history = hist_raw.get("history", [])

        last5 = history[-5:] if history else []
        pts5  = [h["total_points"] for h in last5]
        form_avg = round(sum(pts5) / len(pts5), 2) if pts5 else 0.0

        last3 = history[-3:]
        prev3 = history[-6:-3] if len(history) >= 6 else history[:-3]
        recent_avg = sum(h["total_points"] for h in last3) / max(len(last3), 1)
        older_avg  = sum(h["total_points"] for h in prev3) / max(len(prev3), 1)
        momentum   = round(recent_avg - older_avg, 2)

        # Minutes score: avg minutes per GW
        total_min = _safe_float(el.get("minutes"))
        gws_played = max(_safe_float(el.get("minutes", 90)) / 90, 1)
        avg_min = total_min / gws_played

        # xGI/90
        xgi90 = _safe_float(el.get("expected_goal_involvements_per_90"))

        # Penalty / set-piece bonus
        pen_order = el.get("penalties_order") or 0
        pen_bonus = 1.0 if pen_order == 1 else (0.5 if pen_order == 2 else 0.0)

        # FDR score (invert: low FDR = high score; scale 1-5 → 1.0-0.0)
        fdr = team_fdr.get(team_id, 3.0)
        dgw_bonus = 0.5 if team_id in team_dgw else 0.0
        fixture_raw = max(0.0, (5.0 - fdr) / 4.0) + dgw_bonus  # 0–1.25

        return {
            "player_id": pid,
            "name": name,
            "pos": pos,
            "team": teams_map.get(team_id, "Unknown"),
            "price": price,
            "status": status,
            "form_avg": form_avg,
            "momentum": momentum,
            "avg_min": round(avg_min, 1),
            "xgi90": round(xgi90, 3),
            "pen_bonus": pen_bonus,
            "fdr": round(fdr, 1),
            "fixture_raw": round(fixture_raw, 3),
        }

    # ── Collect squad player stats (fetch history for each squad member) ────────
    squad_stats = []
    for pid in squad_ids:
        hist_url = f"https://fantasy.premierleague.com/api/element-summary/{pid}/"
        hist_raw = json.loads(_cached_get(hist_url))
        squad_stats.append(_score_player(pid, hist_raw.get("history", [])))

    # ── Normalise within squad for composite scoring ────────────────────────────
    def _norm(values: list[float]) -> list[float]:
        mn, mx = min(values), max(values)
        if mx == mn:
            return [0.5] * len(values)
        return [(v - mn) / (mx - mn) for v in values]

    form_norm    = _norm([s["form_avg"]    for s in squad_stats])
    fix_norm     = _norm([s["fixture_raw"] for s in squad_stats])
    min_norm     = _norm([s["avg_min"]     for s in squad_stats])
    xgi_norm     = _norm([s["xgi90"]       for s in squad_stats])
    mom_norm     = _norm([s["momentum"]    for s in squad_stats])
    pen_norm     = _norm([s["pen_bonus"]   for s in squad_stats])

    for i, s in enumerate(squad_stats):
        composite = (
            0.30 * form_norm[i] +
            0.25 * fix_norm[i]  +
            0.15 * min_norm[i]  +
            0.15 * xgi_norm[i]  +
            0.10 * mom_norm[i]  +
            0.05 * pen_norm[i]
        )
        s["composite_score"] = round(composite * 100, 1)

    squad_stats.sort(key=lambda x: x["composite_score"])

    # ── Strategy detection ──────────────────────────────────────────────────────
    avg_squad_fdr = sum(s["fdr"] for s in squad_stats) / len(squad_stats)
    avg_form      = sum(s["form_avg"] for s in squad_stats) / len(squad_stats)
    low_minutes   = sum(1 for s in squad_stats if s["avg_min"] < 60)

    if avg_squad_fdr >= 3.5:
        strategy = "Fixture Targeting"
        strategy_reason = f"Squad avg FDR {avg_squad_fdr:.1f} — prioritise players/replacements entering green fixture runs (FDR ≤ 2.5)"
    elif avg_form < 3.5:
        strategy = "Form & Stats Chasing"
        strategy_reason = f"Squad avg form {avg_form:.1f} pts/GW — prioritise high-form replacements (form_avg ≥ 5.0, xGI/90 ≥ 0.4)"
    elif low_minutes >= 3:
        strategy = "Minutes Certainty"
        strategy_reason = f"{low_minutes} squad players averaging < 60 min/GW — prioritise nailed starters"
    else:
        strategy = "Form & Stats Chasing"
        strategy_reason = "No dominant fixture or rotation issue — target best available form and underlying stats"

    # ── Sell candidates: bottom squad players, with hard blocks ────────────────
    sell_candidates = []
    for s in squad_stats:
        if s["status"] in ("i", "s", "n"):
            sell_candidates.append({**s, "sell_reason": "Injured/suspended/unavailable"})
        elif s["form_avg"] >= 5.5:
            continue  # HARD BLOCK
        elif s["composite_score"] < 35:
            sell_candidates.append({**s, "sell_reason": f"Low composite score {s['composite_score']}/100 (form {s['form_avg']}, FDR {s['fdr']})"})
        if len(sell_candidates) >= 2:
            break

    # ── Pre-compute squad club counts for constraint checking ───────────────
    squad_team_ids = [elements_map.get(pid, {}).get("team") for pid in squad_ids]
    squad_club_counts = Counter(squad_team_ids)
    # Map sell candidates' team_ids so we can "free up" a slot when selling
    sell_team_ids = {}
    for sc in sell_candidates:
        el = elements_map.get(sc["player_id"], {})
        sell_team_ids[sc["pos"]] = el.get("team")

    # ── Replacement candidates per sell candidate ──────────────────────────────
    replacement_sections: list[str] = []
    for sc in sell_candidates:
        pos = sc["pos"]
        sell_price = sc["price"]
        sell_team_id = sell_team_ids.get(pos)
        sell_budget = round(bank + sell_price, 1)

        # Club counts after removing the sold player
        post_sell_counts = Counter(squad_club_counts)
        if sell_team_id and post_sell_counts.get(sell_team_id, 0) > 0:
            post_sell_counts[sell_team_id] -= 1

        # Pull candidates for this position
        df_el = pd.DataFrame(data["elements"])
        pos_type = {"GKP": 1, "DEF": 2, "MID": 3, "FWD": 4}.get(pos, 0)
        df_el = df_el[df_el["element_type"] == pos_type].copy()
        df_el["price"] = df_el["now_cost"] / 10

        # ── Hard filters: assign score=0 equivalent by excluding entirely ─────
        # 1. Already in squad
        df_el = df_el[~df_el["id"].isin(squad_ids)]
        # 2. Over budget
        df_el = df_el[df_el["price"] <= sell_budget]
        # 3. Unavailable / departed
        df_el = df_el[df_el["status"] != "u"]
        # 4. Injured / suspended / not available (status i/s/n) — score 0
        df_el = df_el[~df_el["status"].isin(["i", "s", "n"])]
        # 5. Club limit: adding this player's team would exceed 3-per-club
        def _club_ok(team_id):
            return post_sell_counts.get(team_id, 0) < 3
        df_el = df_el[df_el["team"].apply(_club_ok)]
        # 6. Zero minutes all season — not a real option
        df_el = df_el[pd.to_numeric(df_el["minutes"], errors="coerce").fillna(0) > 0]

        if df_el.empty:
            replacement_sections.append(
                f"\nNo eligible {pos} candidates found (budget ≤ £{sell_budget}m, "
                f"all constraint-filtered)."
            )
            continue

        df_el["form"] = pd.to_numeric(df_el["form"], errors="coerce").fillna(0)
        df_el = df_el.sort_values("form", ascending=False).head(num_candidates * 3)

        cand_stats = []
        for _, row in df_el.iterrows():
            cs = _score_player(int(row["id"]))
            cand_stats.append(cs)

        if not cand_stats:
            continue

        # Score candidates
        c_form_norm = _norm([c["form_avg"]    for c in cand_stats])
        c_fix_norm  = _norm([c["fixture_raw"] for c in cand_stats])
        c_min_norm  = _norm([c["avg_min"]     for c in cand_stats])
        c_xgi_norm  = _norm([c["xgi90"]       for c in cand_stats])
        c_mom_norm  = _norm([c["momentum"]    for c in cand_stats])
        c_pen_norm  = _norm([c["pen_bonus"]   for c in cand_stats])

        for i, c in enumerate(cand_stats):
            c["composite_score"] = round((
                0.30 * c_form_norm[i] +
                0.25 * c_fix_norm[i]  +
                0.15 * c_min_norm[i]  +
                0.15 * c_xgi_norm[i]  +
                0.10 * c_mom_norm[i]  +
                0.05 * c_pen_norm[i]
            ) * 100, 1)

        cand_stats.sort(key=lambda x: x["composite_score"], reverse=True)
        top = cand_stats[:num_candidates]

        # Count how many were filtered out
        total_in_pos = len(pd.DataFrame(data["elements"]).query(
            f"element_type == {pos_type} and status != 'u'"
        ))
        filtered_out = total_in_pos - len(df_el)

        cand_df = pd.DataFrame([{
            "player_id":   c["player_id"],
            "name":        c["name"],
            "team":        c["team"],
            "price":       f"£{c['price']}m",
            "score":       c["composite_score"],
            "form_avg":    c["form_avg"],
            "fdr_3gw":     c["fdr"],
            "xgi/90":      c["xgi90"],
            "momentum":    c["momentum"],
            "pen_order":   ("1st" if c["pen_bonus"]==1.0 else ("2nd" if c["pen_bonus"]==0.5 else "none")),
        } for c in top])
        replacement_sections.append(
            f"\nTOP {pos} REPLACEMENTS for {sc['name']} "
            f"(budget ≤ £{sell_budget}m, {filtered_out} players auto-excluded: "
            f"over budget / in squad / club limit / injured / 0 mins):\n"
            + cand_df.to_markdown(index=False)
        )

    # ── Build output ────────────────────────────────────────────────────────────
    squad_df = pd.DataFrame([{
        "player_id":   s["player_id"],
        "name":        s["name"],
        "pos":         s["pos"],
        "team":        s["team"],
        "price":       f"£{s['price']}m",
        "score":       s["composite_score"],
        "form_avg":    s["form_avg"],
        "fdr_3gw":     s["fdr"],
        "xgi/90":      s["xgi90"],
        "momentum":    s["momentum"],
        "status":      s["status"],
    } for s in squad_stats])

    lines = [
        f"## TRANSFER INTELLIGENCE REPORT",
        f"Budget: ITB £{bank}m | Squad value £{value}m | Free transfers: {free_transfers}",
        f"",
        f"### STRATEGY DETECTED: {strategy}",
        f"Reason: {strategy_reason}",
        f"",
        f"### SQUAD SCORES (worst → best, score 0-100)",
        f"score = weighted avg of form(30%), fixture(25%), minutes(15%), xGI(15%), momentum(10%), set-piece(5%)",
        squad_df.to_markdown(index=False),
        f"",
        f"### SELL CANDIDATES",
    ]

    if sell_candidates:
        for sc in sell_candidates:
            pen_str = ("1st pen taker" if sc["pen_bonus"]==1.0 else
                       ("2nd pen taker" if sc["pen_bonus"]==0.5 else "no pen"))
            lines.append(
                f"  SELL: {sc['name']} ({sc['pos']}, {sc['team']}) | "
                f"Score: {sc['composite_score']}/100 | form_avg: {sc['form_avg']} | "
                f"FDR: {sc['fdr']} | {pen_str}\n"
                f"  Reason: {sc['sell_reason']}"
            )
    else:
        lines.append("  No sell candidates — all squad players score above threshold.")

    lines.append(f"\n### REPLACEMENT CANDIDATES")
    lines.extend(replacement_sections)

    lines.append(
        f"\nNOTE: Composite scores are relative to the candidate pool for each position. "
        f"Always call get_player_summary(player_id) on the top 2-3 candidates for full "
        f"fixture/form detail before making a final recommendation."
    )

    return "\n".join(lines)


# ── FPLState ──────────────────────────────────────────────────────────────────

class FPLState(TypedDict):
    messages:            Annotated[list, add_messages]
    pipeline:            str
    chip_recommendation: str
    transfer_count:      int
    validation_status:   str
    validation_retries:  int
    validation_path:     str

# ── LLM ──────────────────────────────────────────────────────────────────────

llm = ChatOpenAI(
    model="openai/gpt-5.4-mini",
    base_url="https://openrouter.ai/api/v1",
    openai_api_key=os.getenv("OPENAI"),
    temperature=0.9,
    max_tokens=1000,
)

# High-output model for final_reviewer — needs room for full analysis + lineup block
llm_reviewer = ChatOpenAI(
    model="x-ai/grok-4.1-fast",
    base_url="https://openrouter.ai/api/v1",
    openai_api_key=os.getenv("OPENAI"),
    temperature=0.3,
    max_tokens=1500,
)

# Fast model for mechanical agents (validation, routing, pattern analysis).
# IMPORTANT: Do NOT use a :free tier model here — free-tier rate limits add 20-60s
# of queue latency per call, which compounds across 3 sequential fast-agent nodes.
llm_fast = ChatOpenAI(
    model="openai/gpt-5.4-mini",
    base_url="https://openrouter.ai/api/v1",
    openai_api_key=os.getenv("OPENAI"),
    temperature=0.1,
    max_tokens=750,
)

# ── Context compression utilities ─────────────────────────────────────────────

def make_pre_model_hook(keep_last_n: int = 20):
    """
    Trim the message list to the last ~keep_last_n messages, but NEVER split an
    AIMessage-with-tool-calls from its corresponding ToolMessage results.
    Splitting those pairs causes the model to forget its results and retry the
    same tool calls in an infinite loop.
    """
    def _group_turns(msgs):
        """Group messages into complete turns: each turn is either a single
        non-tool message, or an AIMessage-with-tool-calls + ALL its ToolMessages."""
        turns = []
        i = 0
        while i < len(msgs):
            msg = msgs[i]
            if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                tc_ids = {tc["id"] for tc in msg.tool_calls}
                turn = [msg]
                j = i + 1
                while j < len(msgs) and isinstance(msgs[j], ToolMessage) \
                        and msgs[j].tool_call_id in tc_ids:
                    turn.append(msgs[j])
                    j += 1
                turns.append(turn)
                i = j
            else:
                turns.append([msg])
                i += 1
        return turns

    def _hook(state: dict) -> dict:
        messages = state.get("messages", [])
        system_msgs = [m for m in messages if isinstance(m, SystemMessage)]
        non_system  = [m for m in messages if not isinstance(m, SystemMessage)]

        if len(non_system) <= keep_last_n:
            return {"llm_input_messages": system_msgs + non_system}

        turns = _group_turns(non_system)

        # Walk backwards through turns, accumulating until we exceed keep_last_n
        kept_turns = []
        total = 0
        for turn in reversed(turns):
            if total + len(turn) > keep_last_n and kept_turns:
                break
            kept_turns.insert(0, turn)
            total += len(turn)

        recent_msgs = [m for turn in kept_turns for m in turn]

        # Always preserve the first HumanMessage so the agent knows its task
        first_human = next((m for m in non_system if isinstance(m, HumanMessage)), None)
        kept = system_msgs[:]
        if first_human and first_human not in recent_msgs:
            kept.append(first_human)
        kept.extend(recent_msgs)
        return {"llm_input_messages": kept}

    return _hook

def compress_messages(state: FPLState) -> dict:
    to_remove = []
    for msg in state["messages"]:
        msg_id = getattr(msg, "id", None)
        if not msg_id:
            continue
        if isinstance(msg, ToolMessage):
            to_remove.append(RemoveMessage(id=msg_id))
        elif isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            to_remove.append(RemoveMessage(id=msg_id))
    return {"messages": to_remove} if to_remove else {}

def compress_all_ai_messages(state: FPLState) -> dict:
    """Strip ALL AIMessages (tool-call and plain text) plus ToolMessages.
    Use after agents whose text output is NOT needed by downstream agents
    (e.g. researcher — its data is re-fetched by every downstream agent)."""
    to_remove = []
    for msg in state["messages"]:
        msg_id = getattr(msg, "id", None)
        if not msg_id:
            continue
        if isinstance(msg, (AIMessage, ToolMessage)):
            to_remove.append(RemoveMessage(id=msg_id))
    return {"messages": to_remove} if to_remove else {}

def compress_keep_last_output(state: FPLState) -> dict:
    """Strip ALL AI/Tool messages except the most recent non-empty plain-text output.
    Use after outgoing_recommender so incoming_recommender ONLY sees the SELL block —
    prevents large pattern_analyst / transfers_agent tables from burying the SELL line."""
    # Find the last plain AIMessage with non-empty content
    last_plain_id = None
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            content = msg.content if isinstance(msg.content, str) else ""
            if content.strip():
                last_plain_id = getattr(msg, "id", None)
                break

    to_remove = []
    for msg in state["messages"]:
        msg_id = getattr(msg, "id", None)
        if not msg_id or msg_id == last_plain_id:
            continue
        if isinstance(msg, (AIMessage, ToolMessage)):
            to_remove.append(RemoveMessage(id=msg_id))
    return {"messages": to_remove} if to_remove else {}

def compress_and_humanize_last_output(label: str):
    """Return a compression function that strips ALL AI/Tool messages and
    re-injects the last non-empty plain-text AI output as a HumanMessage.

    gpt-5.4-mini ignores AIMessages from other agents (treats them as its own prior
    output). Converting the SELL/BUY blocks to HumanMessages forces the model to
    read them as data they must act on.

    label: used in the HumanMessage header (e.g. 'OUTGOING_RECOMMENDER', 'INCOMING_RECOMMENDER')
    """
    def _compress(state: FPLState) -> dict:
        # Find the last plain AIMessage with non-empty content
        output_content = None
        for msg in reversed(state["messages"]):
            if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
                content = msg.content if isinstance(msg.content, str) else ""
                if content.strip():
                    output_content = content
                    break

        to_remove = []
        for msg in state["messages"]:
            msg_id = getattr(msg, "id", None)
            if not msg_id:
                continue
            if isinstance(msg, (AIMessage, ToolMessage)):
                to_remove.append(RemoveMessage(id=msg_id))

        to_add = []
        if output_content:
            to_add.append(HumanMessage(
                content=f"[{label} OUTPUT]\n{output_content}"
            ))

        return {"messages": to_remove + to_add} if (to_remove or to_add) else {}
    return _compress

# Pre-built instances used in the graph
compress_and_humanize_sell      = compress_and_humanize_last_output("OUTGOING_RECOMMENDER")
compress_and_humanize_buy       = compress_and_humanize_last_output("INCOMING_RECOMMENDER")
compress_and_humanize_transfers = compress_and_humanize_last_output("TRANSFERS_AGENT")

# ── Graph builder ─────────────────────────────────────────────────────────────

def build_graph():
    """Build and compile the FPL LangGraph agent. Returns the compiled model."""

    # ── Agents ────────────────────────────────────────────────────────────────

    with open("prompts/research_prompt.md") as f:
        research_agent = create_react_agent(
            model=llm,
            tools=[team_data, get_user_team, get_player_summary,
                   fixture_info_for_gw, fixture_stats,
                   fpl_scoring_rules, player_types, get_gameweek_context,
                   premier_league_players],
            prompt=f.read(), name="researcher",
            pre_model_hook=make_pre_model_hook(keep_last_n=10),
        )

    with open("prompts/rival_analyst_prompt.md") as f:
        rival_analyst_agent = create_react_agent(
            model=llm,
            tools=[fpl_league_standings, get_user_team, most_valuable_fpl_teams, python_repl_tool],
            prompt=f.read(), name="rival_analyst",
            pre_model_hook=make_pre_model_hook(keep_last_n=15),
        )

    with open("prompts/fixture_analyst_prompt.md") as f:
        fixture_analyst_agent = create_react_agent(
            model=llm,
            tools=[fixture_info_for_gw, team_data, get_team_fixtures],
            prompt=f.read(), name="fixture_analyst",
            pre_model_hook=make_pre_model_hook(keep_last_n=20),
        )

    with open("prompts/chips_strategist_prompt.md") as f:
        chips_strategy_agent = create_react_agent(
            model=llm,
            tools=[get_gameweek_context, get_user_team, fixture_info_for_gw,
                   get_player_summary, get_team_fixtures],
            prompt=f.read(), name="chips_strategist",
            pre_model_hook=make_pre_model_hook(keep_last_n=15),
        )

    with open("prompts/transfers_agents/transfers_prompt.md") as f:
        transfers_agent = create_react_agent(
            model=llm,
            tools=[get_squad_transfer_scores, get_user_team, get_gameweek_context, get_player_summary],
            prompt=f.read(), name="transfers_agent",
            pre_model_hook=make_pre_model_hook(keep_last_n=5),
        )

    with open("prompts/transfers_agents/outgoing_recommender_prompt.md") as f:
        outgoing_recommender = create_react_agent(
            model=llm,
            tools=[get_squad_transfer_scores, get_squad_analysis, get_player_summary,
                   get_user_team, get_team_fixtures, get_team_stats,
                   fpl_scoring_rules, get_gameweek_context],
            prompt=f.read(), name="outgoing_recommender",
            pre_model_hook=make_pre_model_hook(keep_last_n=25),
        )

    with open("prompts/transfers_agents/incoming_recommender_prompt.md") as f:
        incoming_recommender = create_react_agent(
            model=llm,
            tools=[get_squad_transfer_scores, get_player_summary, get_team_stats,
                   team_data, fpl_scoring_rules, player_types,
                   premier_league_players, get_top_form_players, get_user_team,
                   get_team_fixtures, get_squad_club_counts, get_gameweek_context],
            prompt=f.read(), name="incoming_recommender",
            pre_model_hook=make_pre_model_hook(keep_last_n=15),
        )

    # constraint_validator is now a deterministic Python function (no LLM).
    # See validate_constraints() defined below in this function.

    with open("prompts/lineup_selector_prompt.md") as f:
        lineup_selector = create_react_agent(
            model=llm,
            tools=[get_player_summary, get_user_team, get_team_fixtures, get_team_stats, get_gameweek_context],
            prompt=f.read(), name="lineup_selector",
            pre_model_hook=make_pre_model_hook(keep_last_n=20),
        )

    with open("prompts/captaincy_selector_prompt.md") as f:
        captaincy_selector = create_react_agent(
            model=llm,
            tools=[get_player_summary, get_team_fixtures, get_team_stats],
            prompt=f.read(), name="captaincy_selector",
            pre_model_hook=make_pre_model_hook(keep_last_n=5),
        )

    with open("prompts/final_reviewer_prompt.md") as f:
        final_reviewer = create_react_agent(
            model=llm_reviewer,
            tools=[get_user_team, get_gameweek_context, get_player_summary, get_team_fixtures, get_player_pattern_analysis],
            prompt=f.read(), name="final_reviewer",
            pre_model_hook=make_pre_model_hook(keep_last_n=30),
        )

    # Squad builder sub-agents
    with open("prompts/squad_builder/gkp_selector_prompt.md") as f:
        squad_gkp_selector = create_react_agent(
            model=llm,
            tools=[get_player_summary, team_data,
                   fixture_info_for_gw, get_player_name_from_id, get_team_name_from_id,
                   premier_league_players, python_repl_tool],
            prompt=f.read(), name="gkp_selector",
            pre_model_hook=make_pre_model_hook(keep_last_n=5),
        )

    with open("prompts/squad_builder/def_selector_prompt.md") as f:
        squad_def_selector = create_react_agent(
            model=llm,
            tools=[get_player_summary, team_data,
                   fixture_info_for_gw, fpl_scoring_rules, get_player_name_from_id,
                   get_team_name_from_id, premier_league_players, python_repl_tool],
            prompt=f.read(), name="def_selector",
            pre_model_hook=make_pre_model_hook(keep_last_n=5),
        )

    with open("prompts/squad_builder/mid_selector_prompt.md") as f:
        squad_mid_selector = create_react_agent(
            model=llm,
            tools=[get_player_summary, team_data,
                   fixture_info_for_gw, fpl_scoring_rules, get_gameweek_context,
                   premier_league_players, python_repl_tool],
            prompt=f.read(), name="mid_selector",
            pre_model_hook=make_pre_model_hook(keep_last_n=5),
        )

    with open("prompts/squad_builder/fwd_selector_prompt.md") as f:
        squad_fwd_selector = create_react_agent(
            model=llm,
            tools=[get_player_summary, team_data,
                   fixture_info_for_gw, fpl_scoring_rules, premier_league_players, python_repl_tool],
            prompt=f.read(), name="fwd_selector",
            pre_model_hook=make_pre_model_hook(keep_last_n=5),
        )

    with open("prompts/squad_builder/squad_optimizer_prompt.md") as f:
        squad_optimizer = create_react_agent(
            model=llm,
            tools=[fixture_info_for_gw, get_player_summary, fpl_scoring_rules, python_repl_tool],
            prompt=f.read(), name="squad_optimizer",
            pre_model_hook=make_pre_model_hook(keep_last_n=5),
        )

    with open("prompts/squad_builder/squad_builder_supervisor_prompt.md") as f:
        squad_builder_supervisor = create_supervisor(
            model=llm_fast,
            agents=[squad_gkp_selector, squad_def_selector, squad_mid_selector,
                    squad_fwd_selector, squad_optimizer],
            prompt=f.read(),
            add_handoff_back_messages=True,
            output_mode="last_message",
        ).compile()
    squad_builder_supervisor.name = "squad_builder"

    with open("prompts/pattern_analyst_prompt.md") as f:
        pattern_analyst_agent = create_react_agent(
            model=llm_fast,
            tools=[get_user_team, get_player_pattern_analysis, get_gameweek_context],
            prompt=f.read(), name="pattern_analyst",
            pre_model_hook=make_pre_model_hook(keep_last_n=4),
        )

    with open("prompts/primary_supervisor_prompt.md") as f:
        supervisor_agent = create_react_agent(
            model=llm_fast,
            tools=[],  # no tools — supervisor only classifies intent from message text
            prompt=f.read(), name="supervisor",
            pre_model_hook=make_pre_model_hook(keep_last_n=5),
        )

    # ── State updaters ────────────────────────────────────────────────────────

    def _last_ai_text(messages):
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                content = msg.content if isinstance(msg.content, str) else ""
                if content.strip():
                    return content
        return ""

    def _extract_tag(text, tag):
        m = re.search(rf'\[{tag}:\s*([^\]]+)\]', text, re.IGNORECASE)
        return m.group(1).strip() if m else None

    def update_pipeline_state(state):
        tag = _extract_tag(_last_ai_text(state["messages"]), "PIPELINE")
        pipeline = (tag or "full").lower().strip()
        valid = {"full", "transfers", "lineup", "captain", "chip", "rivals", "fixtures", "squad"}
        return {"pipeline": pipeline if pipeline in valid else "full"}

    def update_chip_state(state):
        tag = _extract_tag(_last_ai_text(state["messages"]), "CHIP")
        chip = (tag or "NONE").upper().strip()
        return {"chip_recommendation": chip if chip in {"WC", "FH", "BB", "TC", "NONE"} else "NONE"}

    def set_squad_builder_path(state):
        return {"validation_path": "squad_builder"}

    def update_transfer_state(state):
        content = _last_ai_text(state["messages"])
        tag = _extract_tag(content, "TRANSFERS")
        if tag:
            try:
                return {"transfer_count": int(tag.strip())}
            except ValueError:
                pass
        if re.search(r'\b(roll the ft|0 transfer|zero transfer|rolling)\b', content, re.IGNORECASE):
            return {"transfer_count": 0}
        return {"transfer_count": 1}

    def set_incoming_path(state):
        return {"validation_path": "incoming_recommender"}

    def update_validation_state(state):
        content = _last_ai_text(state["messages"])
        tag = _extract_tag(content, "VALIDATION")
        if tag:
            status = "VALID" if ("VALID" in tag.upper() and "INVALID" not in tag.upper()) else "INVALID"
        elif "VALIDATION PASSED" in content.upper():
            status = "VALID"
        else:
            status = "INVALID"
        retries = state.get("validation_retries", 0)
        if status == "INVALID":
            retries += 1
        return {"validation_status": status, "validation_retries": retries}

    def sync_after_analysis(state):
        # Runs after parallel rival/fixture branches join — do compression here
        # to avoid both branches racing to RemoveMessage the same IDs.
        to_remove = []
        for msg in state["messages"]:
            msg_id = getattr(msg, "id", None)
            if not msg_id:
                continue
            if isinstance(msg, ToolMessage):
                to_remove.append(RemoveMessage(id=msg_id))
            elif isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                to_remove.append(RemoveMessage(id=msg_id))
        return {"messages": to_remove} if to_remove else {}

    # ── Routing ───────────────────────────────────────────────────────────────

    def route_after_research(state):
        return {"full": "rival_analyst", "transfers": "fixture_analyst",
                "lineup": "pattern_analyst", "captain": "pattern_analyst",
                "chip": "fixture_analyst", "rivals": "rival_analyst",
                "fixtures": "fixture_analyst"}.get(state.get("pipeline", "full"), END)

    def route_research_fanout(state):
        if state.get("pipeline", "full") == "full":
            return ["rival_analyst", "fixture_analyst"]
        return [route_after_research(state)]

    def route_after_chips(state):
        chip = state.get("chip_recommendation", "NONE")
        if chip in ("WC", "FH"):
            return "squad_builder"
        if state.get("pipeline") == "chip":
            return END
        return "transfers_agent"

    def route_after_transfers(state):
        if state.get("transfer_count", 1) == 0:
            pipeline = state.get("pipeline", "full")
            if pipeline in ("full", "transfers"):
                return "lineup_selector"
            return END
        # Fan-out: run outgoing and incoming recommenders in parallel.
        # Both read [TRANSFERS_AGENT OUTPUT] for strategy/positions.
        # Incoming estimates budget from squad data; constraint_validator
        # confirms exact affordability once both outputs are available.
        return ["outgoing_recommender", "incoming_recommender"]

    def route_after_validation(state):
        status = state.get("validation_status", "UNKNOWN")
        retries = state.get("validation_retries", 0)
        if status == "VALID":
            pipeline = state.get("pipeline", "full")
            # Always run lineup_selector after a transfer is validated — the
            # final_reviewer needs tool-backed form data to build the STARTING XI
            # table and avoid hallucination.
            if pipeline in ("full", "lineup"):
                return "lineup_selector"
            else:
                return "final_reviewer"
        if retries >= 2:
            return "final_reviewer"
        return state.get("validation_path", "incoming_recommender")

    def route_after_captaincy(state):
        pipeline = state.get("pipeline", "full")
        if pipeline in ("full", "transfers", "captain", "lineup"):
            return "final_reviewer"
        return END

    # ── Deterministic constraint validator (replaces LLM agent) ──────────────

    def validate_constraints(state: FPLState) -> dict:
        """Deterministic transfer/squad validation — zero LLM calls.

        Parses SELL/BUY blocks from conversation messages, does budget arithmetic,
        checks club-count limits via the bootstrap data, and checks position
        composition. Emits a single AIMessage with [VALIDATION: VALID/INVALID].
        """
        messages = state.get("messages", [])

        # ── Detect validation mode ────────────────────────────────────────────
        vpath = state.get("validation_path", "incoming_recommender")
        is_squad_build = vpath == "squad_builder"

        # ── Extract all text from messages ─────────────────────────────────────
        all_text = []
        for msg in messages:
            content = ""
            if isinstance(msg, (AIMessage, HumanMessage)):
                content = msg.content if isinstance(msg.content, str) else ""
            if content.strip():
                all_text.append(content)
        full_text = "\n".join(all_text)

        # ── Find current GW from bootstrap (no HTTP needed) ───────────────────
        events_df = pd.DataFrame(data["events"])
        cur_rows = events_df[events_df["is_current"] == True]
        prev_rows = events_df[events_df["is_previous"] == True]
        if not cur_rows.empty:
            finished_gw = int(cur_rows.iloc[0]["id"])
        elif not prev_rows.empty:
            finished_gw = int(prev_rows.iloc[0]["id"])
        else:
            finished_gw = 1

        # ── Parse SELL blocks ──────────────────────────────────────────────────
        # Same tight-window approach: SELLING PRICE must appear within 5 lines of SELL:
        sell_pattern = re.compile(
            r'SELL:\s*([^\n]+)\n'
            r'(?:[^\n]*\n){0,5}?'
            r'SELLING PRICE:\s*£([\d.]+)m',
        )
        sells = sell_pattern.findall(full_text)
        sell_names = [s[0].strip().split("(")[0].strip() for s in sells]
        sell_prices = [float(s[1]) for s in sells]

        # ── Parse BUY blocks (OPTION 1 RECOMMENDED) ──────────────────────────
        # Match BUY: line followed by PRICE: within the next 5 non-blank lines.
        # Using a non-DOTALL pattern prevents the greedy scan from jumping across
        # sections and grabbing squad_value or table prices instead of the actual
        # recommended player's price.
        buy_pattern = re.compile(
            r'BUY:\s*([^\n]+)\n'                    # BUY: player name on its own line
            r'(?:[^\n]*\n){0,5}?'                   # up to 5 intervening lines
            r'PRICE:\s*£([\d.]+)m',                 # PRICE: £X.Xm
        )
        buys = buy_pattern.findall(full_text)
        # Cap BUY matches to the number of SELL matches to avoid counting OPTION 2
        # alternatives that happen to include a PRICE: line.
        buys = buys[:len(sells)] if sells else buys
        buy_names = [b[0].strip().split("(")[0].strip() for b in buys]
        buy_prices = [float(b[1]) for b in buys]
        log.debug("validate_constraints: parsed sells=%s prices=%s | buys=%s prices=%s | ITB=%.1f",
                  sell_names, sell_prices, buy_names, buy_prices, itb)

        # ── Parse ITB from conversation ────────────────────────────────────────
        itb = 0.0
        itb_match = re.findall(r'ITB[:\s]*£([\d.]+)m', full_text)
        if itb_match:
            itb = float(itb_match[-1])  # take last occurrence

        # ── Squad build mode validation ────────────────────────────────────────
        if is_squad_build:
            # For squad builds, scan for total cost / player list
            # Just do club count check via bootstrap
            issues = []
            # Try to find a total cost
            cost_m = re.findall(r'TOTAL\s+(?:SQUAD\s+)?COST[:\s]*£([\d.]+)m', full_text, re.IGNORECASE)
            if cost_m:
                total_cost = float(cost_m[-1])
                if total_cost > 100.0:
                    issues.append(f"[BUDGET] Total squad cost £{total_cost}m > £100.0m limit")

            if issues:
                result_text = "❌ VALIDATION FAILED\n\nISSUES:\n"
                for i, issue in enumerate(issues, 1):
                    result_text += f"{i}. {issue}\n"
                result_text += "\n[VALIDATION: INVALID]"
            else:
                result_text = "✅ VALIDATION PASSED\n\n[VALIDATION: VALID]"

            return {"messages": [AIMessage(content=result_text)]}

        # ── Transfer mode validation ───────────────────────────────────────────
        issues = []

        # Budget check
        if sell_prices and buy_prices:
            available = itb + sum(sell_prices)
            total_cost = sum(buy_prices)
            remaining = round(available - total_cost, 1)

            sell_str = " + ".join(f"sell £{p}m" for p in sell_prices)
            budget_line = f"Available £{available:.1f}m (ITB £{itb}m + {sell_str}) | Cost £{total_cost:.1f}m | Remaining £{remaining:.1f}m"

            if total_cost > available:
                issues.append(f"[BUDGET] {budget_line} — shortfall £{abs(remaining):.1f}m")
            else:
                budget_line += " ✓"
        elif not sell_prices and not buy_prices:
            budget_line = "No SELL/BUY blocks found — cannot validate budget (ESTIMATED)"
        else:
            budget_line = f"Partial data: {len(sells)} sells, {len(buys)} buys"

        # Club limit & composition check — only when we have complete SELL+BUY data
        uid_match = re.findall(r'user_id[=:]\s*(\d+)', full_text)
        if not uid_match:
            uid_match = re.findall(r'entry/(\d+)/', full_text)
        user_id_val = int(uid_match[-1]) if uid_match else 872062

        elements_map = {e["id"]: e for e in data["elements"]}
        teams_map    = {t["id"]: t["name"] for t in data["teams"]}
        pos_map      = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}

        club_ok = True
        composition_ok = True
        club_line = "Skipped (no complete SELL+BUY data to validate)"
        comp_line = "Skipped (no complete SELL+BUY data to validate)"

        # Only run structural checks if we successfully parsed matching SELL and BUY counts
        if sell_names and buy_names and len(sell_names) == len(buy_names):
            # Load current squad from API cache
            squad_url = f"https://fantasy.premierleague.com/api/entry/{user_id_val}/event/{finished_gw}/picks/"
            squad_raw = json.loads(_cached_get(squad_url))
            squad = []
            if "picks" in squad_raw:
                for p in squad_raw["picks"]:
                    el = elements_map.get(p["element"], {})
                    squad.append({
                        "name": el.get("web_name", str(p["element"])),
                        "full_name": (el.get("first_name", "") + " " + el.get("second_name", "")).strip(),
                        "team": teams_map.get(el.get("team"), "Unknown"),
                        "pos": pos_map.get(el.get("element_type"), "UNK"),
                    })

            # Apply all transfers simultaneously
            removed = []
            for out_name in sell_names:
                out_lower = out_name.lower()
                for i, s in enumerate(squad):
                    if out_lower in s["full_name"].lower() or out_lower in s["name"].lower():
                        removed.append(squad.pop(i))
                        break

            added = []
            for in_name in buy_names:
                in_lower = in_name.lower()
                for e in data["elements"]:
                    full = (e.get("first_name", "") + " " + e.get("second_name", "")).lower()
                    web = e.get("web_name", "").lower()
                    if in_lower == web or in_lower == full or in_lower in full or in_lower in web:
                        player_entry = {
                            "name": e.get("web_name", ""),
                            "team": teams_map.get(e["team"], "Unknown"),
                            "pos": pos_map.get(e["element_type"], "UNK"),
                        }
                        squad.append(player_entry)
                        added.append(player_entry["name"])
                        break

            log.debug(
                "validate_constraints: sells=%s removed=%d | buys=%s added=%d | squad_size=%d",
                sell_names, len(removed), buy_names, len(added), len(squad)
            )

            # Only run club/composition check if squad size is intact (all players matched)
            if len(squad) == 15:
                club_counts = Counter(s["team"] for s in squad)
                pos_counts  = Counter(s["pos"]  for s in squad)
                violations  = [f"{c} ({n} players)" for c, n in club_counts.items() if n > 3]
                club_ok = len(violations) == 0
                club_line = "No club exceeds 3 players ✓" if club_ok else f"VIOLATED: {', '.join(violations)}"

                if not club_ok:
                    issues.append(f"[CLUB LIMIT] Exceeded: {', '.join(violations)}")

                expected = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}
                comp_parts = []
                for pos_code, needed in expected.items():
                    actual = pos_counts.get(pos_code, 0)
                    comp_parts.append(f"{pos_code}:{actual}")
                    if actual != needed:
                        issues.append(f"[COMPOSITION] {pos_code}: {actual} (need {needed})")
                        composition_ok = False
                comp_line = " | ".join(comp_parts) + (" ✓" if composition_ok else " ❌")
            else:
                # Squad size wrong — name matching failed. Don't penalise, just warn.
                log.warning(
                    "validate_constraints: squad size %d after transfers (expected 15) — "
                    "name matching incomplete, skipping structural checks. "
                    "sells=%s removed=%d buys=%s added=%d",
                    len(squad), sell_names, len(removed), buy_names, len(added)
                )
                club_line = f"Skipped — squad size {len(squad)}/15 after name-matching"
                comp_line = f"Skipped — squad size {len(squad)}/15 after name-matching"
        else:
            log.debug(
                "validate_constraints: incomplete parse — sells=%s buys=%s, skipping structural checks",
                sell_names, buy_names
            )

        # ── Build result ───────────────────────────────────────────────────────
        if issues:
            result_text = "❌ VALIDATION FAILED\n\n"
            result_text += f"BUDGET: {budget_line}\n"
            result_text += f"CLUB LIMITS: {club_line}\n"
            result_text += f"COMPOSITION: {comp_line}\n"
            result_text += "\nISSUES:\n"
            for i, issue in enumerate(issues, 1):
                result_text += f"{i}. {issue}\n"
            result_text += "\n[VALIDATION: INVALID]"
        else:
            result_text = "✅ VALIDATION PASSED\n\n"
            result_text += f"BUDGET: {budget_line}\n"
            result_text += f"CLUB LIMITS: {club_line}\n"
            result_text += f"COMPOSITION: {comp_line}\n"
            result_text += "\n[VALIDATION: VALID]"

        return {"messages": [AIMessage(content=result_text)]}

    # ── Build graph ───────────────────────────────────────────────────────────

    g = StateGraph(FPLState)

    g.add_node("supervisor",            supervisor_agent)
    g.add_node("researcher",            research_agent)
    g.add_node("rival_analyst",         rival_analyst_agent)
    g.add_node("fixture_analyst",       fixture_analyst_agent)
    g.add_node("pattern_analyst",       pattern_analyst_agent)
    g.add_node("chips_strategist",      chips_strategy_agent)
    g.add_node("squad_builder",         squad_builder_supervisor)
    g.add_node("transfers_agent",       transfers_agent)
    g.add_node("outgoing_recommender",  outgoing_recommender)
    g.add_node("incoming_recommender",  incoming_recommender)
    g.add_node("constraint_validator",  validate_constraints)
    g.add_node("lineup_selector",       lineup_selector)
    g.add_node("captaincy_selector",    captaincy_selector)
    g.add_node("final_reviewer",        final_reviewer)

    g.add_node("update_pipeline",   update_pipeline_state)
    g.add_node("update_chip",       update_chip_state)
    g.add_node("update_transfers",  update_transfer_state)
    g.add_node("update_validation", update_validation_state)
    g.add_node("set_squad_path",    set_squad_builder_path)
    g.add_node("sync_analysis",     sync_after_analysis)
    # set_incoming_path removed — validation retry defaults to "incoming_recommender"

    # compress_research uses the aggressive variant — strips all AI text from the researcher
    # so its spurious "TRANSFERS RECOMMENDATION" outputs never reach downstream agents.
    g.add_node("compress_research", compress_all_ai_messages)

    for name in ["compress_pattern", "compress_chips", "compress_squad",
                 "compress_validation", "compress_lineup", "compress_captaincy"]:
        g.add_node(name, compress_messages)
    # compress_transfers preserves the transfers_agent strategy output as a HumanMessage
    # labelled [TRANSFERS_AGENT OUTPUT]. Both outgoing and incoming recommenders read this
    # to get the strategic directive and positions to address without calling the agent again.
    g.add_node("compress_transfers", compress_and_humanize_transfers)

    # ── Skip researcher/fixture_analyst/pattern_analyst for focused pipelines ──
    # For "full" pipeline all three pre-analysis agents still run.
    # For targeted queries (transfers, lineup, captain, chip) we jump straight to
    # the relevant starting point — the researcher's output is always wiped by
    # compress_all_ai_messages before downstream agents see it anyway, so running
    # it for focused queries wastes 30-40 seconds for zero benefit.
    def route_after_update_pipeline(state):
        pipeline = state.get("pipeline", "full")
        if pipeline == "full":
            return "researcher"         # full: keep all pre-analysis agents
        if pipeline in ("transfers", "chip"):
            return "chips_strategist"   # skip straight to chip/transfer decision
        if pipeline in ("lineup", "captain"):
            return "pattern_analyst"    # skip researcher but keep pattern analysis
        if pipeline in ("rivals",):
            return "researcher"         # rivals needs league data from researcher
        if pipeline == "fixtures":
            return "fixture_analyst"    # fixtures: only need fixture agent
        return "researcher"             # default fallback

    g.add_edge(START, "supervisor")
    g.add_edge("supervisor", "update_pipeline")
    g.add_conditional_edges("update_pipeline", route_after_update_pipeline,
                            ["researcher", "chips_strategist",
                             "pattern_analyst", "fixture_analyst"])

    g.add_edge("researcher", "compress_research")
    g.add_conditional_edges("compress_research", route_research_fanout,
                            ["rival_analyst", "fixture_analyst",
                             "pattern_analyst", END])

    # Both parallel branches converge directly at sync_analysis, which handles
    # compression in one shot to avoid RemoveMessage collision on the same IDs.
    g.add_edge("rival_analyst",   "sync_analysis")
    
    ##### g.add_edge("fixture_analyst", "sync_analysis")

    def route_after_sync(state):
        """Route to pattern_analyst for actionable pipelines; skip for info-only queries."""
        pipeline = state.get("pipeline", "full")
        if pipeline in ("chip", "fixtures", "rivals"):
            return "chips_strategist"
        return "pattern_analyst"

    def route_after_pattern(state):
        pipeline = state.get("pipeline", "full")
        if pipeline == "transfers":
            return "transfers_agent"
        if pipeline == "captain":
            return "captaincy_selector"
        if pipeline == "lineup":
            return "lineup_selector"
        return "chips_strategist"  # full pipeline

    g.add_conditional_edges("fixture_analyst", route_after_sync,
                            ["chips_strategist", "pattern_analyst"])

    # g.add_edge("pattern_analyst", "compress_pattern")
    # g.add_conditional_edges("compress_pattern", route_after_pattern,
    #                         ["chips_strategist", "transfers_agent",
    #                          "captaincy_selector", "lineup_selector"])

    g.add_conditional_edges("pattern_analyst", route_after_pattern,
                             ["chips_strategist", "transfers_agent",
                              "captaincy_selector", "lineup_selector"])

    g.add_edge("chips_strategist", "update_chip")
    g.add_edge("update_chip",      "compress_chips")
    g.add_conditional_edges("compress_chips", route_after_chips)

    g.add_edge("squad_builder",  "compress_squad")
    g.add_edge("compress_squad", "set_squad_path")
    g.add_edge("set_squad_path", "constraint_validator")

    ## TRANSFERS BRANCH — outgoing + incoming run in PARALLEL ##
    # compress_transfers preserves [TRANSFERS_AGENT OUTPUT] as a HumanMessage so both
    # parallel agents can read the strategy/positions without an extra tool call.
    # They fan-out simultaneously and both converge at constraint_validator.

    g.add_edge("transfers_agent",  "update_transfers")
    g.add_edge("update_transfers", "compress_transfers")
    g.add_conditional_edges("compress_transfers", route_after_transfers,
                            ["outgoing_recommender", "incoming_recommender",
                             "lineup_selector", END])

    # Both parallel agents join at constraint_validator (LangGraph waits for both)
    g.add_edge("outgoing_recommender", "constraint_validator")
    g.add_edge("incoming_recommender", "constraint_validator")

    g.add_edge("constraint_validator", "update_validation")
    g.add_edge("update_validation",    "compress_validation")
    g.add_conditional_edges("compress_validation", route_after_validation)

    g.add_edge("lineup_selector",  "compress_lineup")
    g.add_edge("compress_lineup",  "captaincy_selector")
    g.add_edge("captaincy_selector", "compress_captaincy")
    g.add_conditional_edges("compress_captaincy", route_after_captaincy)

    g.add_edge("final_reviewer", END)

    return g.compile(checkpointer=InMemorySaver())
