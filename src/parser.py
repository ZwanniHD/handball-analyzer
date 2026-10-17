from pathlib import Path
import json
import re
import pandas as pd
import pdfplumber


def parse_match_pdf(pdf_path: Path) -> dict:
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"Datei nicht gefunden: {pdf_path}")

    metadata = {
        "game_number": "",
        "date": "",
        "venue": "",
        "home_team": "",
        "away_team": "",
        "final_score": "",
        "spectators": 0,
    }
    home_players = []
    away_players = []
    events = []

    with pdfplumber.open(pdf_path) as pdf:
        # -------------------------------------------------------------
        # 1. METADATEN EXTRAHIEREN (Aus Seite 1 Reinetext)
        # -------------------------------------------------------------
        p1_text = pdf.pages[0].extract_text() or ""

        # Spielnummer
        g_num = re.search(r"Spielnummer\s+([A-Z0-9]+)", p1_text)
        metadata["game_number"] = g_num.group(1).strip() if g_num else ""

        # Datum
        date_m = re.search(r"Datum\s+(.*?,\s*Spielbeginn\s*\d{2}:\d{2})", p1_text)
        metadata["date"] = date_m.group(1).strip() if date_m else ""

        # Spielort
        venue_m = re.search(r"Spielort\s+(.*?)\s+Gastmannschaft", p1_text)
        metadata["venue"] = venue_m.group(1).strip() if venue_m else ""

        # Heimmannschaft
        home_m = re.search(r"Heimmannschaft\s+(.*?)(?=\n|Spielort)", p1_text)
        metadata["home_team"] = home_m.group(1).strip() if home_m else ""

        # Gastmannschaft
        away_m = re.search(r"Gastmannschaft\s+(.*?)(?=\n|Endstand)", p1_text)
        metadata["away_team"] = away_m.group(1).strip() if away_m else ""

        # Endstand
        score_m = re.search(r"Endstand\s+(.*?)\s+Zuschauer", p1_text)
        metadata["final_score"] = score_m.group(1).strip() if score_m else ""

        # Zuschauer
        specs_m = re.search(r"Zuschauer\s+(\d+)", p1_text)
        metadata["spectators"] = int(specs_m.group(1)) if specs_m else 0

        # -------------------------------------------------------------
        # 2. KADER EXTRAHIEREN (Aus Reinetext S. 1 & S. 2)
        # -------------------------------------------------------------
        current_target = home_players

        # RegEx für Kaderzeilen: Nr/Kürzel + Name + optionale Tore/7m/Zeitstrafen
        player_regex = re.compile(
            r"^([0-9]{1,2}|[A-DH])\s+([A-Za-zÄÖÜäöüß\s\-]+?)(?:\s+(\d+))?(?:\s+(\d+/\d+))?(?:\s+(\d{2}:\d{2}))?$"
        )

        for page_idx in [0, 1]:
            lines = (pdf.pages[page_idx].extract_text() or "").split("\n")

            for line in lines:
                line = line.strip()

                if "Gast:" in line:
                    current_target = away_players
                    continue

                m = player_regex.match(line)
                if m:
                    nr, name, tore, seven_m, strafe = m.groups()
                    clean_name = name.strip()

                    # Überschriften/Trenner herausfiltern
                    if clean_name in ["Name", "Verein", "Rolle", "SR A SR B"]:
                        continue

                    current_target.append({
                        "Nr": nr,
                        "Name": clean_name,
                        "Tore": tore if tore else "",
                        "7m_Tore": seven_m if seven_m else "",
                        "Verwarnung": "",
                        "Hinausstellungen": strafe if strafe else "",
                    })

        # -------------------------------------------------------------
        # 3. SPIELVERLAUF EXTRAHIEREN (Seite 3 & 4 durch Spaltenschnitt)
        # -------------------------------------------------------------
        event_pattern = re.compile(
            r"(Heim|Gast)?\s*(\d{2}:\d{2})\s*(\d+:\d+)?\s*(Tor|Siebenmeter Tor|Zwei Minuten|Verwarnung|Auszeit|Teilende|Spielende)?\s*(.*)"
        )

        forbidden_words = [
            "Halbzeit", "Spielort", "SPORTHALLE", "REIFERBAHN",
            "DHB", "Spielklasse", "Zuschauer", "Endstand", "Startseite",
            "Teil", "GENERAL", "NORD", "SPIELTAG", "3. LIGA", "FRAUEN"
        ]

        for page_idx in range(2, len(pdf.pages)):
            page = pdf.pages[page_idx]
            w, h = page.width, page.height

            for bbox in [(0, 0, w / 2, h), (w / 2, 0, w, h)]:
                crop = page.crop(bbox)
                text = crop.extract_text() or ""
                lines = [l.strip() for l in text.split("\n") if l.strip()]

                for i, line in enumerate(lines):
                    if any(
                        kw in line
                        for kw in [
                            "Spielklasse", "Heimmannschaft", "Gastmannschaft",
                            "Endstand", "Zuschauer", "Spielverlauf", "DHB",
                            "Seite", "HANDBALL"
                        ]
                    ):
                        continue

                    match = event_pattern.search(line)
                    if match:
                        team, time_val, score_val, event_type, person = match.groups()

                        if time_val:
                            # Falls Name in Folgezeile steht
                            if not person and i + 1 < len(lines):
                                next_line = lines[i + 1]
                                if not re.search(r"\d{2}:\d{2}", next_line) and not any(
                                    kw in next_line for kw in ["Heim", "Gast"]
                                ):
                                    person = next_line

                            clean_person = person.strip() if person else ""

                            if any(fp in clean_person for fp in forbidden_words):
                                clean_person = ""

                            if (
                                not team
                                and not score_val
                                and not event_type
                                and not clean_person
                            ):
                                continue

                            events.append({
                                "Zeit": time_val,
                                "Team": team or "",
                                "Stand": score_val or "",
                                "Ereignis": event_type or "",
                                "Person": clean_person,
                            })

    df_events = pd.DataFrame(events)
    if not df_events.empty and "Zeit" in df_events.columns:
        df_events = df_events.sort_values(by="Zeit").reset_index(drop=True)

    return {
        "metadata": metadata,
        "home_kader": pd.DataFrame(home_players),
        "away_kader": pd.DataFrame(away_players),
        "events": df_events,
    }


def save_as_json(data: dict, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    export_data = {
        "metadata": data["metadata"],
        "home_kader": data["home_kader"].to_dict(orient="records"),
        "away_kader": data["away_kader"].to_dict(orient="records"),
        "events": data["events"].to_dict(orient="records"),
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)
    print(f"\nErfolgreich als JSON gespeichert unter: {output_path}")


if __name__ == "__main__":
    sample_pdf = Path("data/raw_pdfs/match_392542.pdf")

    if sample_pdf.exists():
        result = parse_match_pdf(sample_pdf)
        print("=== METADATEN ===")
        for k, v in result["metadata"].items():
            print(f"{k}: {v}")

        save_as_json(result, Path("data/processed/match_392542.json"))
    else:
        print(f"PDF nicht gefunden unter: {sample_pdf}")