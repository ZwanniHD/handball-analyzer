import re
import requests


def fetch_match_ids_from_url(url: str) -> list[str]:
  headers = {
      'User-Agent': (
          'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      )
  }
  response = requests.get(url, headers=headers)
  response.raise_for_status()

  # Suche nach allen ID-Mustern, die z. B. in Links zu 'id_partido=' vorkommen
  ids = re.findall(r'id_partido=(\d+)', response.text)

  # Falls Handball.net IDs in Daten-Attributen versteckt (z.B. "matchId": 392542)
  if not ids:
    ids = re.findall(r'["\'](?:matchId|id_partido|gameId)["\']\s*:\s*(\d+)', response.text)

  # Duplikate entfernen
  unique_ids = sorted(list(set(ids)))
  return unique_ids


if __name__ == '__main__':
  # Füge hier die URL der Spielplan-Webseite der 3. Liga Frauen Nord ein:
  spielplan_url = 'https://www.handball.net/ligen/6596?season_id=2627&fed_id=1&phaseId=14057'

  try:
    match_ids = fetch_match_ids_from_url(spielplan_url)
    print(f'Gefundene Match-IDs ({len(match_ids)}): {match_ids}')
  except Exception as e:
    print(f'Fehler beim Abrufen: {e}')