# FPL Agent Tools Reference

## Helper Functions (internal, not exposed as tools)

| Function | Description |
|---|---|
| `get_player_name_from_id(player_id)` | Resolve player ID → name from bootstrap data |
| `get_team_name_from_id(team_id)` | Resolve team ID → name from bootstrap data |
| `get_player_team(player_id)` | Resolve player ID → their team name |
| `_parse_transfers_from_output(text)` | **app.py** — Parse `OUT: X (£Xm) → IN: Y (£Xm)` lines from final reviewer output into `[(out_name, in_name)]` swap pairs |
| `_find_element_by_name(name, elements)` | **app.py** — Fuzzy-match a player name against FPL bootstrap elements dict |
| `_squad_pitch_html(user_id, transfers)` | **app.py** — Render pitch graphic; optional `transfers` list applies proposed swaps before rendering |

---

## Consolidated Tools (preferred — use these first)

These tools replace combinations that used to require two separate calls.

---

### 1. `get_player_summary(player_id)`

**Use instead of:** `player_stats_by_fixture` + `player_upcoming_fixtures`

Get a player's recent form AND upcoming fixtures in a single call.

**Inputs:**
- `player_id` (int) — FPL/EPL player ID

**Outputs:**
- Player name and ID
- `RECENT FORM (last 6 GW)` table: `gw, opp, h/a, minutes, goals_scored, assists, clean_sheets, goals_conceded, pts`
- `UPCOMING FIXTURES (next 5 GW)` table: `gw, opponent, h/a, fdr, type` (type = NORMAL / DGW / BLANK)

**Used by:** `outgoing_recommender`, `incoming_recommender`, `captaincy_selector`, `lineup_selector`, `final_reviewer`, squad builder agents

---

### 2. `get_user_team(user_id, gw)`

**Use instead of:** `fpl_team_players` + `fpl_team_budget`

Get the user's full squad, captain/VC info, and bank balance (ITB) in one call.

**Inputs:**
- `user_id` (int) — FPL team ID
- `gw` (int) — current or most recent gameweek number

**Outputs:**
- `Budget` line: `ITB: £X.Xm | Squad value: £X.Xm`
- `Squad` table: `slot, pos, name, team, cap_mult, next_gw`
  - `cap_mult`: 2 = captain, 3 = triple captain, 1 = normal, 0 = bench
  - `next_gw`: BLANK(GWN), DGW(N), or OK

**Used by:** `researcher`, `chips_strategist`, `outgoing_recommender`, `incoming_recommender`, `constraint_validator`, `lineup_selector`, `final_reviewer`

---

### 3. `get_gameweek_context()`

**Use instead of:** `current_gw_status` + `fpl_gw_info`

Get current GW, next GW, deadline, and blank/double GW team information. No arguments needed.

**Outputs:**
- `Current GW: N | Finished: True/False`
- `Next GW: N | Deadline: ISO8601 timestamp`
- `Previous GW: N`
- Blank teams and double gameweek teams for the next GW

**Used by:** `researcher`, `chips_strategist`, `constraint_validator`

---

## Core Data Tools

---

### 4. `fixture_info_for_gw(gw)`

Look up all fixtures for a specific FPL gameweek.

**Inputs:**
- `gw` (int) — FPL gameweek number (1–38)

**Outputs table:** `event, finished, fixture_id, kickoff_time, minutes, started, team_a, team_a_score, team_h, team_h_score, team_h_difficulty, team_a_difficulty`

**Used by:** `researcher`, `fixture_analyst`, `chips_strategist`, `lineup_selector`, `captaincy_selector`, incoming/outgoing recommenders

---

### 5. `team_data(team_id)`

Get team-level strength ratings for a Premier League team. Use `team_id = -1` to get all teams.

**Inputs:**
- `team_id` (int) — EPL team ID, or -1 for all teams

**Outputs:** `name, position, short_name, strength_overall_home, strength_overall_away, strength_attack_home, strength_attack_away, strength_defence_home, strength_defence_away, pulse_id`

**Used by:** `fixture_analyst`, `incoming_recommender`, squad builder agents

---

### 6. `premier_league_players(position, max_price)`

List EPL players filtered by position and/or price. Always pass both filters to avoid oversized results.

**Inputs:**
- `position` (str) — `GKP`, `DEF`, `MID`, `FWD`, or `ALL` (default: `ALL`)
- `max_price` (float) — max price in millions, e.g. `8.5`. Use `0` to disable.

**Outputs table:** `player_id, player_name, team_name, position, price`

**Used by:** `incoming_recommender`, squad builder agents

**Important:** Never call with `position="ALL"` and `max_price=0` — will return all ~600 players.

---

### 7. `fpl_scoring_rules(pos)`

Look up FPL scoring rules for a player position.

**Inputs:**
- `pos` (str) — `GKP`, `DEF`, `MID`, or `FWD`

**Outputs:** `long_play, short_play, goals_conceded, goals_scored, assists, clean_sheets, penalties_saved, penalties_missed, yellow_cards, red_cards, own_goals, defensive_contribution`

**Used by:** `outgoing_recommender`, `incoming_recommender`, squad builder agents

---

### 8. `player_types()`

Look up FPL squad composition rules (position limits, min/max players per position, etc.).

**Outputs:** `position_code, squad_select, squad_min_select, squad_max_select, squad_min_play, squad_max_play, sub_positions_locked, element_count`

**Used by:** `incoming_recommender`, squad builder agents

---

## League & User Tools

---

### 9. `fpl_league_standings(league_id)`

Look up the current standings of a specific FPL mini-league.

**Inputs:**
- `league_id` (int) — FPL league ID

**Outputs:** `gw_points, fpl_manager_name, current_rank, last_rank, fpl_total_points, fpl_team_id, fpl_team_name, movement`

**Used by:** `rival_analyst`

---

### 10. `most_valuable_fpl_teams()`

Look up the most valuable FPL teams in the current season. No arguments.

**Outputs:** `fpl_team_id, fpl_team_name, fpl_manager_name, value_with_bank, total_transfers`

**Used by:** `rival_analyst`

---

## Utility Tools

---

### 11. `python_repl_tool(code)`

Execute Python code in a sandboxed REPL. Use `print()` to see output.

**Inputs:**
- `code` (str) — Python code to run

**Outputs:** The code block + stdout output.

**Used by:** `outgoing_recommender`, `incoming_recommender`, `lineup_selector`, `captaincy_selector`, squad builder agents

**Not available in:** `constraint_validator` (removed — it caused wrong budget arithmetic)

---

## Legacy Tools (still defined, but superseded by consolidated versions)

These tools still work but agents should prefer the consolidated alternatives above.

| Tool | Superseded by |
|---|---|
| `fpl_team_players(user_id, gw)` | `get_user_team(user_id, gw)` |
| `fpl_team_budget(user_id, gw)` | `get_user_team(user_id, gw)` |
| `player_stats_by_fixture(player_id)` | `get_player_summary(player_id)` |
| `player_upcoming_fixtures(player_id)` | `get_player_summary(player_id)` |
| `current_gw_status()` | `get_gameweek_context()` |
| `fpl_gw_info(gw)` | `get_gameweek_context()` |
| `fixture_stats(fixture_id, stat)` | Direct fixture analysis via `fixture_info_for_gw` |

---

## Tool Assignment by Agent

| Agent | Tools available |
|---|---|
| `researcher` | `get_user_team`, `get_gameweek_context`, `fixture_info_for_gw`, `get_player_summary`, `player_types`, `premier_league_players` |
| `fixture_analyst` | `fixture_info_for_gw`, `team_data` |
| `rival_analyst` | `fpl_league_standings`, `most_valuable_fpl_teams`, `get_user_team`, `get_gameweek_context` |
| `chips_strategist` | `get_user_team`, `get_gameweek_context`, `fixture_info_for_gw` |
| `transfers_agent` | `get_user_team`, `get_gameweek_context` |
| `outgoing_recommender` | `get_player_summary`, `get_user_team`, `fixture_info_for_gw`, `fpl_scoring_rules`, `python_repl_tool` |
| `incoming_recommender` | `get_player_summary`, `team_data`, `fpl_scoring_rules`, `player_types`, `fixture_info_for_gw`, `premier_league_players`, `get_user_team`, `python_repl_tool` |
| `constraint_validator` | `get_user_team`, `get_gameweek_context` |
| `lineup_selector` | `fixture_info_for_gw`, `get_player_summary`, `get_user_team`, `python_repl_tool` |
| `captaincy_selector` | `fixture_info_for_gw`, `get_player_summary`, `python_repl_tool` |
| `final_reviewer` | `get_user_team`, `get_gameweek_context`, `python_repl_tool` |
| Squad builder agents | `get_player_summary`, `team_data`, `fixture_info_for_gw`, `fpl_scoring_rules`, `player_types`, `premier_league_players`, `python_repl_tool` |
