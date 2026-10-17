import json
from pathlib import Path
import re
import pandas as pd


def clean_player_name(name: str) -> str:
  if not name or not isinstance(name, str):
    return ''
  clean = re.sub(r'\s*-\s*-', '', name).strip()
  return clean


def load_all_games(
    processed_dir: str = 'data/processed',
) -> tuple[pd.DataFrame, pd.DataFrame]:
  path = Path(processed_dir)
  games_list = []
  player_stats_list = []

  for json_file in path.glob('match_*.json'):
    with open(json_file, 'r', encoding='utf-8') as f:
      data = json.load(f)

    meta = data.get('metadata', {})
    match_id = json_file.stem.replace('match_', '')

    games_list.append({
        'match_id': match_id,
        'game_number': meta.get('game_number', ''),
        'date': meta.get('date', ''),
        'home_team': meta.get('home_team', ''),
        'away_team': meta.get('away_team', ''),
        'final_score': meta.get('final_score', ''),
        'spectators': meta.get('spectators', 0),
    })

    # Beide Kader (Heim und Gast) vollständig verarbeiten
    for team_type, kader_key in [
        ('Heim', 'home_kader'),
        ('Gast', 'away_kader'),
    ]:
      kader = data.get(kader_key, [])
      team_name = meta.get(
          'home_team' if team_type == 'Heim' else 'away_team', ''
      )

      for p in kader:
        raw_name = p.get('Name', '')
        name = clean_player_name(raw_name)

        nr = str(p.get('Nr', '')).strip()
        if not name or nr in ['A', 'B', 'C', 'D', 'H']:
          continue

        # Tore auslesen
        tore_str = str(p.get('Tore', '')).strip()
        tore = int(tore_str) if tore_str.isdigit() else 0

        # 7m Tore auslesen
        seven_m_str = str(p.get('7m_Tore', '')).strip()
        seven_m_goals = 0
        if '/' in seven_m_str:
          try:
            seven_m_goals = int(seven_m_str.split('/')[0])
          except ValueError:
            seven_m_goals = 0

        player_stats_list.append({
            'match_id': match_id,
            'team': team_name,
            'nr': nr,
            'person': name,
            'tore': tore,
            '7m_tore': seven_m_goals,
        })

  games_df = pd.DataFrame(games_list)
  player_stats_df = pd.DataFrame(player_stats_list)

  return games_df, player_stats_df