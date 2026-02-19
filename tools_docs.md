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


6. **fixture_stats**:
Inputs: fixture_id, stat
look-up specific stats for a specific fixture in the English Premier League (EPL).

stats is one of:
goals_scored, assists, own_goals, penalties_saved, penalties_missed, yellow_cards, red_cards, saves, bonus, bps, defensive_contribution

## Outputs: 
player_id, stat_name

6. **current_gw_status**: Look-up the current gw number and live status of the gw.





7. **fpl_gw_info**: Look-up latest info about a specific gw in the EPL.




8. **fpl_league_standings**: Look-up the current standings of a specific FPL League.





9. **most_valuable_fpl_teams**: Look-up the most valuable FPL teams right now (current season).





10. **my_fpl_team_players**: Look-up the players in a user's FPL team.






11. **python_repl_tool**: Create and execute python code