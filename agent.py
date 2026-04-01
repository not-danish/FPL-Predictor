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

    keep = ["player_id" if "player_id" in df.columns else "id",
            "player_name", "team_name", "price", "form",
            "pts_per_game", "total_points", "minutes",
            "goals_scored", "assists", "clean_sheets", "selected_by_percent"]
    # id column is named "id" in bootstrap
    df = df.rename(columns={"id": "player_id"})
    keep = [c for c in ["player_id", "player_name", "team_name", "price", "form",
                        "pts_per_game", "total_points", "minutes",
                        "goals_scored", "assists", "clean_sheets",
                        "selected_by_percent"] if c in df.columns]
    result = df[keep].reset_index(drop=True)
    lines = [
        f"Top {len(result)} {position} players by FPL form (≤ £{max_price}m, avg ≥ {min_minutes_per_gw} min/GW):",
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
    """Get a player's recent form AND upcoming fixtures in one call.
    Returns last 6 GW stats + next 5 fixtures. Use this instead of calling
    player_stats_by_fixture and player_upcoming_fixtures separately."""
    url = f"{base_url}element-summary/{player_id}/"
    raw = json.loads(_cached_get(url))

    player_name = get_player_name_from_id(player_id)
    player_team = get_player_team(player_id)
    lines = [f"**{player_name}** (ID: {player_id}) | Team: {player_team}"]

    # ── Recent form: last 6 GWs only, key columns only ────────────────────────
    history = raw.get("history", [])
    if history:
        df = pd.DataFrame(history[-6:])  # last 6 fixtures
        df = df.rename(columns={"round": "gw", "total_points": "pts"})
        df["opp"] = df["opponent_team"].apply(get_team_name_from_id)
        df["h/a"] = df["was_home"].map({True: "H", False: "A"})
        keep = ["gw", "opp", "h/a", "minutes", "goals_scored", "assists",
                "clean_sheets", "goals_conceded", "pts"]
        df = df[[c for c in keep if c in df.columns]]
        lines.append("\nRECENT FORM (last 6 GW):")
        lines.append(df.to_markdown(index=False))
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

    # Include player_id so downstream agents can call get_player_summary
    keep = ["slot", "player_id", "pos", "name", "team", "cap_mult"]
    if "next_gw" in df.columns:
        keep.append("next_gw")
    lines.append("\n**Squad:**")
    lines.append(df[keep].to_markdown(index=False))
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
    model="gpt-4o-mini",
    base_url="https://openrouter.ai/api/v1",
    openai_api_key=os.getenv("OPENAI"),
    temperature=0.9,
    max_tokens=1500,
)

# Faster, cheaper model for mechanical agents (validation, routing, lineup ordering)
llm_fast = ChatOpenAI(
    model="gpt-4o-mini",
    base_url="https://openrouter.ai/api/v1",
    openai_api_key=os.getenv("OPENAI"),
    temperature=0.1,
    max_tokens=800,
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
            tools=[get_user_team, get_gameweek_context, get_player_summary],
            prompt=f.read(), name="transfers_agent",
            pre_model_hook=make_pre_model_hook(keep_last_n=10),
        )

    with open("prompts/transfers_agents/outgoing_recommender_prompt.md") as f:
        outgoing_recommender = create_react_agent(
            model=llm,
            tools=[get_player_summary, get_user_team,
                   get_team_fixtures, fpl_scoring_rules],
            prompt=f.read(), name="outgoing_recommender",
            pre_model_hook=make_pre_model_hook(keep_last_n=40),
        )

    with open("prompts/transfers_agents/incoming_recommender_prompt.md") as f:
        incoming_recommender = create_react_agent(
            model=llm,
            tools=[get_player_summary, team_data,
                   fpl_scoring_rules, player_types,
                   premier_league_players, get_top_form_players, get_user_team,
                   get_team_fixtures, get_squad_club_counts],
            prompt=f.read(), name="incoming_recommender",
            pre_model_hook=make_pre_model_hook(keep_last_n=20),
        )

    with open("prompts/constraint_validator_prompt.md") as f:
        constraint_validator = create_react_agent(
            model=llm_fast,
            tools=[get_user_team, get_gameweek_context, get_squad_club_counts],
            prompt=f.read(), name="constraint_validator",
            pre_model_hook=make_pre_model_hook(keep_last_n=15),
        )

    with open("prompts/lineup_selector_prompt.md") as f:
        lineup_selector = create_react_agent(
            model=llm_fast,
            tools=[get_player_summary, get_user_team, get_team_fixtures],
            prompt=f.read(), name="lineup_selector",
            pre_model_hook=make_pre_model_hook(keep_last_n=20),
        )

    with open("prompts/captaincy_selector_prompt.md") as f:
        captaincy_selector = create_react_agent(
            model=llm,
            tools=[get_player_summary, get_team_fixtures],
            prompt=f.read(), name="captaincy_selector",
            pre_model_hook=make_pre_model_hook(keep_last_n=15),
        )

    with open("prompts/final_reviewer_prompt.md") as f:
        final_reviewer = create_react_agent(
            model=llm,
            tools=[get_user_team, get_gameweek_context, get_player_summary, get_team_fixtures],
            prompt=f.read(), name="final_reviewer",
            pre_model_hook=make_pre_model_hook(keep_last_n=50),
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
            model=llm,
            agents=[squad_gkp_selector, squad_def_selector, squad_mid_selector,
                    squad_fwd_selector, squad_optimizer],
            prompt=f.read(),
            add_handoff_back_messages=True,
            output_mode="last_message",
        ).compile()
    squad_builder_supervisor.name = "squad_builder"

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
                "lineup": "lineup_selector", "captain": "captaincy_selector",
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
            return "lineup_selector" if state.get("pipeline") == "full" else END
        return "outgoing_recommender"

    def route_after_validation(state):
        status = state.get("validation_status", "UNKNOWN")
        retries = state.get("validation_retries", 0)
        if status == "VALID":
            pipeline = state.get("pipeline", "full")
            if pipeline == "full":
                return "lineup_selector"
            elif pipeline == "transfers":
                return "final_reviewer"
            else:
                return END
        if retries >= 2:
            return "final_reviewer"
        return state.get("validation_path", "incoming_recommender")

    def route_after_captaincy(state):
        return "final_reviewer" if state.get("pipeline") == "full" else END

    # ── Build graph ───────────────────────────────────────────────────────────

    g = StateGraph(FPLState)

    g.add_node("supervisor",            supervisor_agent)
    g.add_node("researcher",            research_agent)
    g.add_node("rival_analyst",         rival_analyst_agent)
    g.add_node("fixture_analyst",       fixture_analyst_agent)
    g.add_node("chips_strategist",      chips_strategy_agent)
    g.add_node("squad_builder",         squad_builder_supervisor)
    g.add_node("transfers_agent",       transfers_agent)
    g.add_node("outgoing_recommender",  outgoing_recommender)
    g.add_node("incoming_recommender",  incoming_recommender)
    g.add_node("constraint_validator",  constraint_validator)
    g.add_node("lineup_selector",       lineup_selector)
    g.add_node("captaincy_selector",    captaincy_selector)
    g.add_node("final_reviewer",        final_reviewer)

    g.add_node("update_pipeline",   update_pipeline_state)
    g.add_node("update_chip",       update_chip_state)
    g.add_node("update_transfers",  update_transfer_state)
    g.add_node("update_validation", update_validation_state)
    g.add_node("set_squad_path",    set_squad_builder_path)
    g.add_node("set_incoming_path", set_incoming_path)
    g.add_node("sync_analysis",     sync_after_analysis)

    for name in ["compress_research",
                 "compress_chips", "compress_squad",
                 "compress_transfers", "compress_outgoing", "compress_incoming",
                 "compress_validation", "compress_lineup", "compress_captaincy"]:
        g.add_node(name, compress_messages)

    g.add_edge(START, "supervisor")
    g.add_edge("supervisor", "update_pipeline")
    g.add_edge("update_pipeline", "researcher")

    g.add_edge("researcher", "compress_research")
    g.add_conditional_edges("compress_research", route_research_fanout,
                            ["rival_analyst", "fixture_analyst",
                             "lineup_selector", "captaincy_selector", END])

    # Both parallel branches converge directly at sync_analysis, which handles
    # compression in one shot to avoid RemoveMessage collision on the same IDs.
    g.add_edge("rival_analyst",   "sync_analysis")
    g.add_edge("fixture_analyst", "sync_analysis")
    g.add_edge("sync_analysis",     "chips_strategist")

    g.add_edge("chips_strategist", "update_chip")
    g.add_edge("update_chip",      "compress_chips")
    g.add_conditional_edges("compress_chips", route_after_chips)

    g.add_edge("squad_builder",  "compress_squad")
    g.add_edge("compress_squad", "set_squad_path")
    g.add_edge("set_squad_path", "constraint_validator")

    g.add_edge("transfers_agent",  "update_transfers")
    g.add_edge("update_transfers", "compress_transfers")
    g.add_conditional_edges("compress_transfers", route_after_transfers)

    g.add_edge("outgoing_recommender", "compress_outgoing")
    g.add_edge("compress_outgoing",    "incoming_recommender")
    g.add_edge("incoming_recommender", "set_incoming_path")
    g.add_edge("set_incoming_path",    "compress_incoming")
    g.add_edge("compress_incoming",    "constraint_validator")

    g.add_edge("constraint_validator", "update_validation")
    g.add_edge("update_validation",    "compress_validation")
    g.add_conditional_edges("compress_validation", route_after_validation)

    g.add_edge("lineup_selector",  "compress_lineup")
    g.add_edge("compress_lineup",  "captaincy_selector")
    g.add_edge("captaincy_selector", "compress_captaincy")
    g.add_conditional_edges("compress_captaincy", route_after_captaincy)

    g.add_edge("final_reviewer", END)

    return g.compile(checkpointer=InMemorySaver())
