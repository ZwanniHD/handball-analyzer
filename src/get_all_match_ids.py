from pathlib import Path
import json
import requests

API_URL = "https://www.handball.net/api/new/matches"


def fetch_all_season_matches() -> list[dict]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.handball.net/",
    }

    all_matches = []

    print("Starte Abfrage aller Spieltage über die Handball.net API...\n")

    # Schleife über alle 26 Spieltage
    for matchday in range(1, 27):
        params = {
            "phase_id": "14057",
            "round": str(matchday),
            "per_page": "20",
            "page": "1",
        }

        try:
            res = requests.get(API_URL, params=params, headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json()

                # Die API liefert die Spiele unter 'data' oder direkt als Liste
                items = data.get("data", data) if isinstance(data, dict) else data

                count_added = 0
                for item in items:
                    m_id = item.get("id") or item.get("matchId")
                    if m_id:
                        # Teams sicher auslesen
                        home = (
                            item.get("homeTeamName")
                            or item.get("homeTeam", {}).get("name")
                            or item.get("homeTeam", {}).get("shortName", "")
                        )
                        away = (
                            item.get("guestTeamName")
                            or item.get("guestTeam", {}).get("name")
                            or item.get("guestTeam", {}).get("shortName", "")
                        )

                        all_matches.append({
                            "match_id": str(m_id),
                            "matchday": matchday,
                            "home_team": home,
                            "away_team": away,
                        })
                        count_added += 1

                print(f"Spieltag {matchday:2d}: {count_added} Spiele gefunden.")
            else:
                print(f"Spieltag {matchday:2d}: Status Code {res.status_code}")

        except Exception as e:
            print(f"Fehler bei Spieltag {matchday}: {e}")

    return all_matches


if __name__ == "__main__":
    matches = fetch_all_season_matches()

    if matches:
        print(f"\nErfolgreich {len(matches)} Spiele der Saison geladen!")

        output_path = Path("data/all_match_ids.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(matches, f, ensure_ascii=False, indent=2)

        print(f"Gespeichert unter: {output_path}")
    else:
        print("\nKeine Spiele gefunden. Bitte überprüfe die Internetverbindung.")