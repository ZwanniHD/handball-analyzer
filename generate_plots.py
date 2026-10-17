import json
import matplotlib.pyplot as plt
import pandas as pd
from src.analytics import load_all_games


def plot_top_scorers_timeline():
  games_df, player_stats_df = load_all_games()

  if player_stats_df.empty:
    print('Keine Spielerdaten gefunden.')
    return

  # Spieltag-Mapping aus data/all_match_ids.json laden
  match_to_day = {}
  try:
    with open('data/all_match_ids.json', 'r', encoding='utf-8') as f:
      all_ids = json.load(f)
      match_to_day = {item['match_id']: item['matchday'] for item in all_ids}
  except Exception:
    pass

  player_stats_df['spieltag'] = player_stats_df['match_id'].map(match_to_day)
  player_stats_df = player_stats_df.dropna(subset=['spieltag'])
  player_stats_df['spieltag'] = player_stats_df['spieltag'].astype(int)

  # 1. Gesamttore pro Spielerin berechnen
  total_scores = (
      player_stats_df.groupby('person')['tore']
      .sum()
      .sort_values(ascending=False)
  )

  # Top 5 Torschützinnen der Liga
  top_5_names = total_scores.head(5).index.tolist()

  print('=== TOP 5 TORSCHÜTZINNEN DER LIGA ===')
  for rank, name in enumerate(top_5_names, start=1):
    print(f'{rank}. {name}: {total_scores[name]} Tore')

  # Filter auf Top 5
  top_df = player_stats_df[player_stats_df['person'].isin(top_5_names)]

  # 2. Pivot-Tabelle erstellen & kumulierte Tore berechnen
  pivot_df = top_df.pivot_table(
      index='spieltag', columns='person', values='tore', aggfunc='sum'
  ).fillna(0)

  # Lücken für spielfreie Tage mit den bisherigen Toren auffüllen
  max_day = int(player_stats_df['spieltag'].max())
  full_index = pd.Index(range(1, max_day + 1), name='spieltag')
  pivot_df = pivot_df.reindex(full_index, fill_value=0)

  cum_goals = pivot_df.cumsum()

  # 3. Plot zeichnen
  plt.figure(figsize=(11, 6))

  for player in top_5_names:
    if player in cum_goals.columns:
      plt.plot(
          cum_goals.index,
          cum_goals[player],
          marker='o',
          label=f'{player} ({int(cum_goals[player].iloc[-1])} Tore)',
          linewidth=2.5,
      )

  plt.title(
      'Kumulierte Tore der Top-5-Torschützinnen (3. Liga Frauen Nord)',
      fontsize=13,
      pad=15,
  )
  plt.xlabel('Spieltag', fontsize=11)
  plt.ylabel('Tore Gesamt', fontsize=11)

  plt.xticks(range(1, max_day + 1))
  plt.legend(title='Spielerin', bbox_to_anchor=(1.02, 1), loc='upper left')
  plt.grid(True, linestyle='--', alpha=0.6)
  plt.tight_layout()
  plt.savefig('top_scorers_correct.png', dpi=300)
  plt.show()


if __name__ == '__main__':
  plot_top_scorers_timeline()