## List of Tools in the System

1. **team_data**:  Latest football team-level performance data for teams in the English Premier League (EPL).

### Outputs:
name, position, short_name, strength_overall_home, stength_overall_away, strength_attack_home, strength_sttack_away, strength_defence_home, strength_defence_away, pulse_id

-------------------------------

2. **get_player_name_from_id**: Look-up the name of a player in the EPL given player ID

-------------------------------

3. **fpl_scoring_rules**: Look-up the latest scoring rules for FPL given their position (GKP, DEF, MID, TWD)

## Outputs:
long_play, short_play, goals_conceded, goals_scored, assists, clean_sheets, penalties_saved, penalties_missed, yellow_cards, red_cards, own_goals, defensive_contribution

-------------------------------

4. **player_types**: Look-up the different player types/positions in FPL.

## Outputs:
position_code, squad_select, squad_min_select, squad_max_select, squad_min_play, squad_max_play, sub_positions_locked, element_count

-------------------------------

5. **fixture_info_for_gw**: Look-up the latest match information for a specific gameweek in the EPL.

## Outputs:
event, finished, fixture_id, kickoff_time, minutes, started, team_a, team_a_score, team_h, team_h_score, team_h_difficulty, team_a_difficulty


6. **fixture_stats**:
Inputs: fixture_id, stat
look-up specific stats for a specific fixture in the English Premier League (EPL).

stats is one of:
goals_scored, assists, own_goals, penalties_saved, penalties_missed, yellow_cards, red_cards, saves, bonus, bps, defensive_contribution

## Outputs: 
player_id, stat_name


-------------------------------

7. **current_gw_status**: Look-up the current gw number and live status of the gw.

## Outputs:
bonus_added: if bonus points have been applied for that gw
date: dates within the current gw for which there are fixtures
event: the current gw number
points

-------------------------------


8. **fpl_gw_info**: Look-up latest info about a specific gw in the EPL.

## Outputs: 
gameweek: The ID of the gameweek (e.g., 1, 2, 3, etc.).
gameweek_name: The name of the gameweek (e.g., "Gameweek 1", "Gameweek 2").
deadline_time: The deadline for making transfers, setting your team, or using chips for the gameweek. This is in ISO 8601 format (e.g., 2026-02-15T12:30:00Z).
release_time: The time when the gameweek data (e.g., fixtures, stats) is released. This is also in ISO 8601 format.
average_entry_score: The average score of all FPL managers for that gameweek.
finished: A boolean indicating whether the gameweek has concluded.
data_checked: A boolean indicating whether all the data for the gameweek (e.g., points, stats) has been finalized and verified.
highest_scoring_entry: The entry ID (team ID) of the FPL manager who scored the highest points in that gameweek.
highest_score: The highest score achieved by any FPL manager in that gameweek.
is_previous: A boolean (true or false) indicating whether this gameweek is the one that just finished (i.e., the most recent completed gameweek).
is_current: A boolean (true or false) indicating whether this is the current active gameweek.
is_next: A boolean (true or false) indicating whether this is the next upcoming gameweek.
released: A boolean (true or false) indicating whether the gameweek has been officially released (e.g., fixtures and data are available).
ranked_count: The number of FPL managers who have been ranked in the gameweek (i.e., those who have scored points).
most_selected: The player ID of the most selected player in FPL squads for that gameweek.
most_transferred_in: The player ID of the most transferred-in player for that gameweek.
highest_scoring_player_id: The player ID of the highest-scoring player in that gameweek.
highest_scoring_player_points: The total points scored by the highest-scoring player in that gameweek.
transfers_made: The total number of transfers made by all FPL managers during that gameweek.
most_captained_player_id: The player ID of the most captained player in FPL squads for that gameweek.
most_vice_captained_player_id: The player ID of the most vice-captained player in FPL squads for that gameweek.

-------------------------------


9. **fpl_league_standings**: Look-up the current standings of a specific FPL League.

## Outputs:
- gw_points: Total points scored by the team in the current gameweek
- fpl_manager_name: Name of the FPL team manager
- current_rank: Current rank of the team in the league
- last_rank: The team's rank in the previous gameweek
- fpl_total_points: Total points scored by the team in all gameweeks so far
- fpl_team_id: Unique identifier for the FPL team
- fpl_team_name: Name of the team
- movement: Change in rank from the previous gameweek (positive means moved up, negative means moved down)

-------------------------------

10. **most_valuable_fpl_teams**: Look-up the most valuable FPL teams right now (current season).

## Outputs:
    - fpl_team_id: Unique identifier for the team
    - fpl_team_name: Name of the team
    - fpl_manager_name: Name of the team manager
    - value_with_bank: Current value of the team. Includes the bank value of the team as well. The value is in millions (e.g., a value of 1050 means the team is worth 105 million).
    - total_transfers: Total number of transfers made by the team in the season so far

-------------------------------


11. **my_fpl_team_players**: Look-up the players in a user's FPL team.






12. **python_repl_tool**: Create and execute python code