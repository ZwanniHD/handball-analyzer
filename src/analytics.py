import json
from pathlib import Path
import re
import pandas as pd

def clean_player_name(name: str) -> str:
    """Bereinigt den Namen von Trennzeichen und führenden Trikotnummern."""
    if not name or not isinstance(name, str):
        return ""
    clean = re.sub(r'^\d+\s*', '', name)
    clean = re.sub(r'\s*-\s*-', '', clean).strip()
    return clean

def load_all_games(processed_dir: str = "data/processed") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Lädt Spiele und Kader-Statistiken aller geparsten JSON-Dateien."""
    path = Path(processed_dir)
    games_list = []
    player_stats_list = []

    for json_file in path.glob("match_*.json"):
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        meta = data.get("metadata", {})
        match_id = json_file.stem.replace("match_", "")

        games_list.append({
            "match_id": match_id,
            "game_number": meta.get("game_number", ""),
            "date": meta.get("date", ""),
            "home_team": meta.get("home_team", ""),
            "away_team": meta.get("away_team", ""),
            "final_score": meta.get("final_score", ""),
            "spectators": meta.get("spectators", 0)
        })

        # Kader von Heim- und Gastmannschaft auslesen
        teams_data = data.get("teams", {})
        for team_key in ["home", "away"]:
            team = teams_data.get(team_key, {})
            team_name = team.get("name", meta.get(f"{team_key}_team", ""))
            
            for player in team.get("players", []):
                name = clean_player_name(player.get("name", ""))
                nr = player.get("number", "")
                
                if not name:
                    continue

                tore = player.get("goals", 0)
                seven_m_str = player.get("seven_m") or ""
                
                seven_m_goals = 0
                if "/" in str(seven_m_str):
                    try:
                        seven_m_goals = int(str(seven_m_str).split("/")[0])
                    except ValueError:
                        seven_m_goals = 0

                player_stats_list.append({
                    "match_id": match_id,
                    "team": team_name,
                    "nr": nr,
                    "person": name,
                    "tore": tore,
                    "7m_tore": seven_m_goals
                })

    games_df = pd.DataFrame(games_list)
    player_stats_df = pd.DataFrame(player_stats_list)

    return games_df, player_stats_df    