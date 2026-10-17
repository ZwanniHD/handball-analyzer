from pathlib import Path
import json
import time
import requests
from parser import parse_match_pdf, save_as_json

# Exakte URL für den PDF-Download von Handball360 / iSquad
PDF_URL_PATTERN = "https://handball360.isquad.de/dhb_acta_completa_pdf.php?id_partido={match_id}"


def download_pdf(match_id: str, output_path: Path) -> bool:
    """Lädt das Spielberichts-PDF für eine Match-ID von handball360 herunter.

    Gibt True zurück, wenn eine gültige PDF empfangen wurde.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/pdf,application/json,*/*",
        "Referer": "https://www.handball.net/",
    }
    url = PDF_URL_PATTERN.format(match_id=match_id)

    try:
        response = requests.get(url, headers=headers, timeout=10)
        # Eine gültige PDF beginnt immer mit den Magic Bytes %PDF und ist größer als 3 KB
        if response.status_code == 200 and response.content.startswith(b"%PDF"):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(response.content)
            return True
        else:
            return False
    except Exception:
        return False


def run_batch_processing():
    ids_file = Path("data/all_match_ids.json")
    if not ids_file.exists():
        print("Datei 'data/all_match_ids.json' nicht gefunden!")
        return

    with open(ids_file, "r", encoding="utf-8") as f:
        matches = json.load(f)

    print(f"Starte Verarbeitung von insgesamt {len(matches)} Spielen...\n")

    successful_count = 0
    skipped_count = 0
    failed_count = 0

    for idx, match in enumerate(matches, start=1):
        match_id = match["match_id"]
        matchday = match.get("matchday", "?")

        pdf_path = Path(f"data/raw_pdfs/match_{match_id}.pdf")
        json_path = Path(f"data/processed/match_{match_id}.json")

        # Überspringen, falls die JSON schon verarbeitet ist
        if json_path.exists():
            skipped_count += 1
            continue

        print(f"[{idx:3d}/{len(matches)}] Spieltag {matchday:2d} | Match-ID {match_id} ... ", end="")

        # 1. PDF herunterladen (falls noch nicht lokal vorhanden)
        if not pdf_path.exists():
            download_success = download_pdf(match_id, pdf_path)
            if not download_success:
                print("Keine PDF verfügbar (Spiel nicht stattgefunden / noch ausstehend)")
                failed_count += 1
                continue
            time.sleep(0.3)  # Sanfte Pause für den Server

        # 2. PDF parsen & als JSON exportieren
        try:
            parsed_data = parse_match_pdf(pdf_path)
            save_as_json(parsed_data, json_path)
            successful_count += 1
            print("OK")
        except Exception as e:
            print(f"FEHLER beim Parsen: {e}")
            failed_count += 1

    print("\n" + "=" * 40)
    print("BATCH-VERARBEITUNG ABGESCHLOSSEN")
    print(f"Neu verarbeitet: {successful_count}")
    print(f"Übersprungen (bereits vorhanden): {skipped_count}")
    print(f"Keine PDFs / Zukünftige Spiele: {failed_count}")
    print("=" * 40)


if __name__ == "__main__":
    run_batch_processing()