import json
from pathlib import Path
import pandas as pd
from src.analytics import load_all_games

def print_all_scorers(output_csv: str = "data/processed/torschuetzenliste.csv"):
    """Liest alle verarbeiteten JSON-Dateien ein und gibt die komplette Torschützenliste aus."""
    
    # 1. Daten über analytics.py laden
    games_df, player_stats_df = load_all_games()

    if player_stats_df.empty:
        print("Keine Spielerdaten im Ordner 'data/processed/' gefunden.")
        print("Bitte stelle sicher, dass 'python src/batch_processor.py' zuvor ausgeführt wurde.")
        return

    # 2. Aggregation: Tore, 7m-Tore und absolvierte Spiele pro Spielerin berechnen
    scorers = player_stats_df.groupby(["person", "team"]).agg(
        Gesamttore=("tore", "sum"),
        Siebenmeter=("7m_tore", "sum"),
        Spiele=("match_id", "nunique")
    ).reset_index()

    # Nur Spielerinnen mit mindestens einem Tor filtern
    scorers = scorers[scorers["Gesamttore"] > 0]

    # 3. Nach Gesamttoren absteigend sortieren
    scorers = scorers.sort_values(by=["Gesamttore", "Siebenmeter"], ascending=[False, False])
    scorers["Tore_pro_Spiel"] = (scorers["Gesamttore"] / scorers["Spiele"]).round(2)

    # Platzierung (Rang) hinzufügen
    scorers.insert(0, "Rang", range(1, len(scorers) + 1))

    # 4. Ausgabe im Terminal
    print("\n" + "=" * 80)
    print(f"VOLLSTÄNDIGE TORSCHÜTZENLISTE ({len(scorers)} Spielerinnen mit Toren)")
    print("=" * 80)
    
    # Formatierte Konsolenausgabe
    print(f"{'Rang':<5} | {'Spielerin':<30} | {'Team':<25} | {'Tore':<5} | {'7m':<4} | {'Spiele':<6} | {'Ø/Spiel':<6}")
    print("-" * 90)
    
    for _, row in scorers.iterrows():
        print(f"{row['Rang']:<5} | {row['person']:<30} | {row['team']:<25} | {row['Gesamttore']:<5} | {row['Siebenmeter']:<4} | {row['Spiele']:<6} | {row['Tore_pro_Spiel']:<6}")

    # 5. Optional als CSV-Datei speichern
    if output_csv:
        csv_path = Path(output_csv)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        scorers.to_csv(csv_path, index=False, encoding="utf-8-sig")
        print("=" * 80)
        print(f"Torschützenliste wurde erfolgreich gespeichert unter: {csv_path}")
        print("=" * 80)

if __name__ == "__main__":
    print_all_scorers()