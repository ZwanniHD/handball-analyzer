from flask import Flask, jsonify
import json
from pathlib import Path
from collections import defaultdict

app = Flask(__name__)
@app.route('/', methods=['GET'])
def home():
    """Zeigt eine Übersicht der verfügbaren Endpunkte auf der Startseite."""
    return jsonify({
        "status": "online",
        "message": "Handball-Analyse API läuft!",
        "endpoints": [
            "http://127.0.0.1:5000/api/overview",
            "http://127.0.0.1:5000/api/topscorers",
            "http://127.0.0.1:5000/api/match/<match_id>"
        ]
    })
# Pfad zu den von der Pipeline generierten JSON-Dateien
DATA_DIR = Path("data/processed")

def load_all_matches():
    """Lädt alle verfügbaren Spielberichte aus dem processed-Ordner."""
    matches = []
    if not DATA_DIR.exists():
        return matches
    
    # Sucht nach allen Dateien mit dem Muster match_<id>.json
    for file in DATA_DIR.glob("match_*.json"):
        try:
            with open(file, "r", encoding="utf-8") as f:
                matches.append(json.load(f))
        except Exception as e:
            print(f"Fehler beim Laden von {file}: {e}")
            
    return matches

@app.route('/api/overview', methods=['GET'])
def get_overview():
    """Gibt eine grobe Übersicht aller Spiele (Metadaten) zurück."""
    matches = load_all_matches()
    overview = []
    
    for match in matches:
        meta = match.get("metadata", {})
        # Nutzt die aus der PDF extrahierten Metadaten
        overview.append({
            "match_id": meta.get("match_id"),
            "matchday": meta.get("matchday"),
            "date": meta.get("date"),
            "time": meta.get("time"),
            "home_team": meta.get("home_team"),
            "away_team": meta.get("away_team"),
            "final_score": meta.get("final_score"),
            "spectators": meta.get("spectators")
        })
        
    # Sortieren nach Spieltag (falls vorhanden)
    overview.sort(key=lambda x: x["matchday"] or 0)
    return jsonify({"total_matches": len(overview), "matches": overview})

@app.route('/api/topscorers', methods=['GET'])
def get_topscorers():
    """Aggregiert die Tore aller Spieler aus allen geladenen Spielen."""
    matches = load_all_matches()
    player_stats = defaultdict(lambda: {"team": "", "goals": 0, "7m": 0})
    
    for match in matches:
        teams = match.get("teams", {})
        
        # Iteriert über Heim- und Auswärtsteam
        for side in ["home", "away"]:
            if side not in teams:
                continue
                
            team_name = teams[side].get("name", "Unbekannt")
            players = teams[side].get("players", [])
            
            for p in players:
                # Spieler-ID aus Name generieren
                name = p.get("name")
                if not name:
                    continue
                    
                player_id = f"{name} ({team_name})"
                player_stats[player_id]["team"] = team_name
                player_stats[player_id]["goals"] += p.get("goals", 0)
                
                # 7-Meter auswerten (Format ist oft "Tore/Versuche")
                seven_m = p.get("seven_m")
                if seven_m and "/" in seven_m:
                    try:
                        made = int(seven_m.split("/")[0])
                        player_stats[player_id]["7m"] += made
                    except ValueError:
                        pass

    # In Liste umwandeln und nach Toren absteigend sortieren
    sorted_players = sorted(
        [{"name": k.split(" (")[0], **v} for k, v in player_stats.items()],
        key=lambda x: x["goals"],
        reverse=True
    )
    
    return jsonify({"topscorers": sorted_players[:50]})  # Top 50

@app.route('/api/match/<match_id>', methods=['GET'])
def get_match_details(match_id):
    """Gibt alle Details (inkl. Timeline und Kader) für ein spezifisches Spiel zurück."""
    file_path = DATA_DIR / f"match_{match_id}.json"
    
    if not file_path.exists():
        return jsonify({"error": "Spiel nicht gefunden"}), 404
        
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    return jsonify(data)

if __name__ == '__main__':
    # Flask-Server starten (Port 5000 ist Standard)
    print("Starte Handball-Analyse Backend...")
    app.run(debug=True, host='0.0.0.0', port=5000)