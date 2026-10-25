"""
Pipeline: Spielplan -> Spielbericht-PDFs -> strukturierte JSONs

Aufruf:
    python pipeline.py                 # neue/unvollständige Spiele laden und parsen
    python pipeline.py --reparse       # ALLE vorhandenen PDFs neu parsen (JSONs überschreiben)
    python pipeline.py --offline       # kein Netzwerk: nur lokale PDFs + gespeicherte Match-IDs
    python pipeline.py --debug 392526  # Rohtext + Rohtabellen einer PDF ausgeben

Ergebnis pro Spiel: data/processed/match_<id>.json mit
    metadata, teams (home/away: name, players, officials), timeline, parse_info
"""
import argparse
import json
import re
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import pdfplumber
import requests

# ----------------------------------------------------------------------------
# Konfiguration
# ----------------------------------------------------------------------------
API_MATCHES_URL = "https://www.handball.net/api/new/matches"
PDF_URL_PATTERN = "https://handball360.isquad.de/dhb_acta_completa_pdf.php?id_partido={match_id}"
PHASE_ID = "14057"
MATCHDAYS = range(1, 27)

RAW_DIR = Path("data/raw_pdfs")
OUT_DIR = Path("data/processed")
IDS_FILE = Path("data/all_match_ids.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.handball.net/",
}

TIME_RE = re.compile(r"^\d{2,3}:\d{2}(?:\s*Uhr)?$")
SCORE_RE = re.compile(r"^\d+:\d+$")
SIDE_CELLS = {"": None, "heim": "home", "gast": "away"}  # Inhalt der Team-Spalte
GOAL_EVENTS = {"tor", "siebenmeter tor"}
OFFICIAL_KEYS = {"A", "B", "C", "D", "E"}
LETTERS_RE = re.compile(r"[A-Za-zÄÖÜäöüß]")


# ----------------------------------------------------------------------------
# 1. Match-IDs
# ----------------------------------------------------------------------------
def fetch_all_season_matches(offline: bool = False) -> list[dict]:
    if not offline:
        matches = []
        print("Starte Abfrage aller Spieltage über die Handball.net API...\n")
        for matchday in MATCHDAYS:
            params = {"phase_id": PHASE_ID, "round": str(matchday), "per_page": "20", "page": "1"}
            try:
                res = requests.get(API_MATCHES_URL, params=params, headers=HEADERS, timeout=10)
                res.raise_for_status()
                data = res.json()
                items = data.get("data", data) if isinstance(data, dict) else data
                count = 0
                for item in items:
                    m_id = item.get("id") or item.get("matchId")
                    if not m_id:
                        continue
                    home_t = item.get("homeTeam") or {}
                    away_t = item.get("guestTeam") or {}
                    matches.append({
                        "match_id": str(m_id),
                        "matchday": matchday,
                        "home_team": item.get("homeTeamName") or home_t.get("name", ""),
                        "away_team": item.get("guestTeamName") or away_t.get("name", ""),
                    })
                    count += 1
                print(f"Spieltag {matchday:2d}: {count} Spiele gefunden.")
            except Exception as e:
                print(f"Fehler bei Spieltag {matchday}: {e}")

        if matches:
            IDS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(IDS_FILE, "w", encoding="utf-8") as f:
                json.dump(matches, f, ensure_ascii=False, indent=2)
            return matches
        print("API lieferte nichts – verwende gespeicherte Match-IDs.")

    if IDS_FILE.exists():
        with open(IDS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


# ----------------------------------------------------------------------------
# 2. PDF-Download
# ----------------------------------------------------------------------------
def download_pdf(match_id: str, output_path: Path) -> bool:
    url = PDF_URL_PATTERN.format(match_id=match_id)
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code == 200 and response.content.startswith(b"%PDF"):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(response.content)
            return True
    except Exception:
        pass
    return False


# ----------------------------------------------------------------------------
# 3. PDF-Parsing
# ----------------------------------------------------------------------------
def to_seconds(t: str):
    try:
        t_clean = str(t).replace("Uhr", "").strip()
        m, s = t_clean.split(":")
        return int(m) * 60 + int(s)
    except ValueError:
        return None

def clean_cell(c) -> str:
    """Zelltext ohne Zeilenumbrüche/Mehrfach-Leerzeichen (None -> '')."""
    return " ".join((c or "").split())


# ---- 3a. Metadaten -----------------------------------------------------------
_STOP = (
    r"(?=\s*(?:Spielnummer|Spielklasse|Datum|Spielbeginn|Spielort|Heimmannschaft|"
    r"Gastmannschaft|Endstand|Zuschauer|Schiedsrichter)\b|\s*[\n|]|\s*$)"
)


def header_field(text: str, label: str, value: str, stop: bool = False) -> str:
    pattern = rf"{label}\s*[:|]?\s*\|?\s*({value})" + (_STOP if stop else "")
    m = re.search(pattern, text)
    return m.group(1).strip() if m else ""


def parse_metadata(pdf, match_id: str, api_match: dict | None) -> dict:
    page = pdf.pages[0]
    # Text + Tabellenzellen der ersten Seite (Header kann in beidem stecken)
    table_text = "\n".join(
        " | ".join(clean_cell(c).replace("\n", " ") for c in row)
        for table in page.extract_tables() for row in table if row
    )
    text = (page.extract_text() or "") + "\n" + table_text

    meta = {
        "game_number": header_field(text, "Spielnummer", r"[A-Z0-9]{10,}"),
        "date": header_field(text, "Datum", r"\d{2}\.\d{2}\.\d{4}"),
        "time": header_field(text, "Spielbeginn", r"\d{1,2}:\d{2}"),
        "home_team": header_field(text, "Heimmannschaft", r"[^\n|]+?", stop=True),
        "away_team": header_field(text, "Gastmannschaft", r"[^\n|]+?", stop=True),
        "venue": header_field(text, "Spielort", r"[^\n|]+?", stop=True),
        "league": header_field(text, "Spielklasse", r"[^\n|]+?", stop=True),
        "matchday": None,
        "winner": header_field(text, "Sieger", r"[^\n|]+?", stop=True),
        "final_score": "",
        "halftime_score": "",
        "spectators": 0,
        "match_id": match_id,
    }

    m = re.search(
        r"Endstand\s*[:|]?\s*\|?\s*(\d+)\s*:\s*(\d+)(?:\s*\(\s*(\d+)\s*[-:]\s*(\d+)\s*\))?", text
    )
    if m:
        meta["final_score"] = f"{m.group(1)}:{m.group(2)}"
        if m.group(3):
            meta["halftime_score"] = f"{m.group(3)}-{m.group(4)}"

    md = re.search(r"SPIELTAG\s+(\d+)", text)
    meta["matchday"] = int(md.group(1)) if md else None

    spec = header_field(text, "Zuschauer", r"\d+")
    meta["spectators"] = int(spec) if spec else 0

    # Fallback: Teamnamen aus dem Spielplan
    if api_match:
        meta["home_team"] = meta["home_team"] or api_match.get("home_team", "")
        meta["away_team"] = meta["away_team"] or api_match.get("away_team", "")
    return meta


# ---- 3b. Kader ----------------------------------------------------------------
def parse_player(number: int, text: str):
    text = re.sub(r"\s+", " ", text).strip()

    seven_m = re.search(r"\b(\d+/\d+)\b", text)
    if seven_m:
        text = text.replace(seven_m.group(1), " ")

    penalties = re.findall(r"\b\d{2}:\d{2}\b", text)
    text = re.sub(r"\b\d{2}:\d{2}\b", " ", text)

    # --- NEUE ZEILE HIER EINFÜGEN ---
    text = text.replace("Uhr", "").strip() 
    # -------------------------------

    text = re.sub(r"(?:\s+[-–])+\s*$", "", text.strip())  # Platzhalter-Striche "- -"
    goals = 0
    m = re.search(r"(\d+)\s*$", text)
    if m:
        goals = int(m.group(1))
        text = text[:m.start()]
    name = re.sub(r"(?:\s+[-–])+\s*$", "", text.strip()).strip()

    if len(name) < 2 or not LETTERS_RE.search(name):
        return None
    return {
        "number": number,
        "name": name,
        "goals": goals,
        "seven_m": seven_m.group(1) if seven_m else None,
        "penalties": penalties,
    }


def parse_official(letter: str, text: str):
    text = re.sub(r"\s+", " ", text).strip()
    penalties = re.findall(r"\b\d{2}:\d{2}\b", text)
    name = re.sub(r"\b\d{2}:\d{2}\b", " ", text)
    name = re.sub(r"(?:\s+[-–])+\s*$", "", name.strip()).strip()
    if len(name) < 2 or not LETTERS_RE.search(name):
        return None
    return {"role": letter, "name": name, "penalties": penalties}


def _add(bucket: dict, side: str, key: str, text: str):
    if key.isdigit():
        item = parse_player(int(key), text)
        target = bucket[side]["players"]
    elif key in OFFICIAL_KEYS:
        item = parse_official(key, text)
        target = bucket[side]["officials"]
    else:
        return
    if item and item not in target:
        target.append(item)


def _empty_roster() -> dict:
    return {s: {"players": [], "officials": []} for s in ("home", "away")}


def roster_from_tables(pdf) -> dict:
    """Kader aus den Tabellen. Der Abschnitt (Heim/Gast) bleibt über Tabellen UND
    Seiten hinweg erhalten, damit Fortsetzungen auf Seite 2 nicht verloren gehen."""
    roster = _empty_roster()
    section = None
    for page in pdf.pages:
        for table in page.extract_tables():
            for row in table:
                cells = [clean_cell(c).replace("\n", " ") for c in (row or [])]
                if not any(cells):
                    continue
                joined = " ".join(cells)
                if "Heim:" in joined:
                    section = "home"
                    continue
                if "Gast:" in joined:
                    section = "away"
                    continue
                if section and cells[0]:
                    _add(roster, section, cells[0], " ".join(cells[1:]))
    return roster


def roster_from_text(pdf) -> dict:
    """Fallback, falls die Tabellenerkennung für den Kader nichts liefert."""
    roster = _empty_roster()
    section = None
    for page in pdf.pages:
        for line in (page.extract_text() or "").split("\n"):
            line = line.strip()
            if "Heim:" in line:
                section = "home"
                continue
            if "Gast:" in line:
                section = "away"
                continue
            m = re.match(r"^(\d{1,2}|[A-E])\s+(\D.*)$", line)
            if section and m:
                _add(roster, section, m.group(1), m.group(2))
    return roster


def parse_roster(pdf) -> dict:
    roster = roster_from_tables(pdf)
    if not roster["home"]["players"] or not roster["away"]["players"]:
        fallback = roster_from_text(pdf)
        for side in ("home", "away"):
            if not roster[side]["players"]:
                roster[side] = fallback[side]
    return roster


# ---- 3c. Spielverlauf ------------------------------------------------------------
def _person_parts(person: str):
    """'33 Josefine Jakobsen' -> (33, 'Josefine Jakobsen')"""
    m = re.match(r"^(\d+)\s+(.+)$", person)
    if m:
        return int(m.group(1)), m.group(2)
    return None, person


def _timeline_rows(source, page_idx: int, block: int, raw: list) -> int:
    """Liest Verlaufszeilen aus allen Tabellen von `source` (Seite oder Seitenausschnitt).

    Erwartet je Zeile: Team | Zeit | Stand | Ereignis | Person. Die Zeitzelle dient als
    Anker, die Zellen davor/danach werden relativ dazu gelesen.
    """
    found = 0
    for table_idx, table in enumerate(source.extract_tables()):
        for row_idx, row in enumerate(table):
            cells = [clean_cell(c) for c in (row or [])]
            for i in range(1, len(cells)):
                team, tstr = cells[i - 1], cells[i]
                if not TIME_RE.match(tstr) or team.lower() not in SIDE_CELLS:
                    continue
                score = cells[i + 1] if i + 1 < len(cells) else ""
                event = cells[i + 2] if i + 2 < len(cells) else ""
                person = cells[i + 3] if i + 3 < len(cells) else ""
                if not event or (score and not SCORE_RE.match(score)):
                    continue  # keine Verlaufszeile (z. B. Strafzeit im Kader)
                number, name = _person_parts(person)
                raw.append(((to_seconds(tstr), page_idx, block, table_idx, row_idx), {
                    "team": team,
                    "time": tstr,
                    "score": score,
                    "event": event,
                    "person": person,
                    "person_number": number,
                    "person_name": name,
                }))
                found += 1
    return found


def _half_boxes(page):
    """Ausschnitte (linke/rechte Tabelle) einer Verlaufsseite.

    Die Box reicht von der Kopfzeile ("Team") bis knapp unter die letzte Zeitangabe.
    Ein Ausschnitt bis zum Seitenende würde Fußzeile/Barcode mit einbeziehen, und dann
    erkennt pdfplumber die rechte Tabelle nicht mehr.
    """
    words = page.extract_words()
    heads = [w["top"] for w in words if w["text"] == "Team"]
    if not heads:
        return []
    top = min(heads) - 3
    mid = page.width / 2
    boxes = []
    for block, (x0, x1) in enumerate(((0, mid), (mid, page.width))):
        tw = [w for w in words if TIME_RE.match(w["text"]) and x0 <= w["x0"] < x1 and w["top"] > top]
        if tw:
            bottom = min(page.height, max(w["bottom"] for w in tw) + 14)
            boxes.append((block, (x0, top, x1, bottom)))
    return boxes


def parse_timeline(pdf) -> list[dict]:
    """Liest den kompletten Spielverlauf.

    Auf jeder Verlaufsseite stehen ZWEI getrennte Tabellen nebeneinander. pdfplumber
    erkennt auf der Gesamtseite nur die linke (und schneidet dabei die Spalte "Person"
    ab). Deshalb wird jede Seite in eine linke und rechte Hälfte geschnitten und jede
    Hälfte einzeln ausgelesen.
    """
    raw = []
    for page_idx, page in enumerate(pdf.pages):
        found = 0
        for block, bbox in _half_boxes(page):
            found += _timeline_rows(page.crop(bbox), page_idx, block, raw)
        if not found:  # Fallback: Gesamtseite (falls das Layout einmal abweicht)
            _timeline_rows(page, page_idx, 0, raw)

    raw.sort(key=lambda x: x[0])  # chronologisch, bei gleicher Sekunde Lesereihenfolge

    timeline, seen = [], set()
    for _, ev in raw:
        if ev["score"]:  # Tore können nicht doppelt vorkommen -> Duplikate entfernen
            key = (ev["team"], ev["time"], ev["score"], ev["event"], ev["person"])
            if key in seen:
                continue
            seen.add(key)
        timeline.append(ev)
    return timeline


# ---- 3d. Schiedsrichter & Spieloffizielle (Seite 1) -------------------------------------
def _group_lines(words, tol: float = 3):
    lines = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(lines[-1]["top"] - w["top"]) <= tol:
            lines[-1]["words"].append(w)
        else:
            lines.append({"top": w["top"], "words": [w]})
    for line in lines:
        line["words"].sort(key=lambda w: w["x0"])
    return lines


def parse_match_officials(page):
    """Schiedsrichter und Spieloffizielle anhand der Wortpositionen (Spalten)."""
    referees, officials = [], []
    try:
        lines = _group_lines(page.extract_words())
        texts = [" ".join(w["text"] for w in l["words"]) for l in lines]
        i_ref = next(i for i, t in enumerate(texts) if t.startswith("Schiedsrichter"))
        i_off = next(i for i, t in enumerate(texts) if t.startswith("Spieloffizielle"))
        i_end = next(i for i, t in enumerate(texts) if t.startswith("Heim:"))

        # Schiedsrichter: Spalte SR B beginnt beim zweiten "SR" der Kopfzeile
        srs = [w for w in lines[i_ref + 1]["words"] if w["text"] == "SR"]
        if len(srs) >= 2:
            x_b = srs[1]["x0"] - 2
            people = [{"role": "SR A"}, {"role": "SR B"}]
            for l in lines[i_ref + 2:i_off]:
                label = l["words"][0]["text"]
                field = {"Name": "name", "Verein": "club"}.get(label)
                if not field:
                    continue
                rest = l["words"][1:]
                people[0][field] = " ".join(w["text"] for w in rest if w["x0"] < x_b)
                people[1][field] = " ".join(w["text"] for w in rest if w["x0"] >= x_b)
            referees = [p for p in people if p.get("name")]

        # Spieloffizielle: Spalten Rolle | Name | Verein
        head = {w["text"]: w["x0"] for w in lines[i_off + 1]["words"]}
        x_name, x_club = head["Name"] - 2, head["Verein"] - 2
        for l in lines[i_off + 2:i_end]:
            ws = l["words"]
            officials.append({
                "role": " ".join(w["text"] for w in ws if w["x0"] < x_name),
                "name": " ".join(w["text"] for w in ws if x_name <= w["x0"] < x_club),
                "club": " ".join(w["text"] for w in ws if w["x0"] >= x_club),
            })
    except Exception:
        pass
    return referees, officials


# ---- 3e. Verknüpfung Kader <-> Spielverlauf ------------------------------------------------
def enrich_players(teams: dict, timeline: list[dict]):
    """Ordnet die Strafzeiten im Kader über den Spielverlauf zu.
    Nutzt den Spielverlauf als primäre Quelle, um Lücken in der Tabellenerkennung auszugleichen."""
    lookup = defaultdict(list)
    for e in timeline:
        side = SIDE_CELLS.get(e["team"].lower())
        if side and e["person_number"] is not None:
            lookup[(side, e["time"], e["person_number"])].append(e["event"].lower())

    for side in ("home", "away"):
        for p in teams[side]["players"]:
            p["warnings"], p["two_minutes"], p["disqualifications"] = [], [], []
            
            # 1. Alle Strafen aus dem zuverlässigen Spielverlauf übernehmen
            for (l_side, l_time, l_num), events_list in lookup.items():
                if l_side == side and l_num == p["number"]:
                    events_str = " ".join(events_list)
                    if "verwarnung" in events_str and l_time not in p["warnings"]:
                        p["warnings"].append(l_time)
                    if "zwei minuten" in events_str and l_time not in p["two_minutes"]:
                        p["two_minutes"].append(l_time)
                    if "disqualifikation" in events_str and l_time not in p["disqualifications"]:
                        p["disqualifications"].append(l_time)

            # 2. Fallback: Strafen, die nur in der Kader-Tabelle standen (und im Verlauf fehlen)
            for t in p["penalties"]:
                if t not in p["warnings"] and t not in p["two_minutes"] and t not in p["disqualifications"]:
                    events = " ".join(lookup.get((side, t, p["number"]), []))
                    if "verwarnung" in events:
                        p["warnings"].append(t)
                    elif "zwei minuten" in events:
                        p["two_minutes"].append(t)
                    elif "disqualifikation" in events:
                        p["disqualifications"].append(t)
            
            # 3. Sammelliste "penalties" synchronisieren und chronologisch sortieren
            all_penalties = set(p["warnings"] + p["two_minutes"] + p["disqualifications"] + p["penalties"])
            p["penalties"] = sorted(list(all_penalties), key=lambda x: to_seconds(x) or 0)
            p["warnings"] = sorted(p["warnings"], key=lambda x: to_seconds(x) or 0)
            p["two_minutes"] = sorted(p["two_minutes"], key=lambda x: to_seconds(x) or 0)
            p["disqualifications"] = sorted(p["disqualifications"], key=lambda x: to_seconds(x) or 0)

# ---- 3f. Plausibilitätsprüfung --------------------------------------------------------
def run_checks(meta: dict, teams: dict, timeline: list[dict]) -> dict:
    timeline_warnings, roster_warnings, notes = [], [], []

    if not timeline:
        timeline_warnings.append("Spielverlauf leer")

    h = a = 0
    goals_by_player = Counter()
    for e in timeline:
        side = SIDE_CELLS.get(e["team"].lower())
        if e["event"].lower() in GOAL_EVENTS and side:
            if side == "home":
                h += 1
            else:
                a += 1
            if e["person_number"] is not None:
                goals_by_player[(side, e["person_number"])] += 1
            if SCORE_RE.match(e["score"]):
                sh, sa = map(int, e["score"].split(":"))
                if (sh, sa) != (h, a):
                    timeline_warnings.append(
                        f"Spielverlauf: Lücke bei {e['time']} (Stand {sh}:{sa}, gezählt {h}:{a})"
                    )
                    h, a = sh, sa

    final = meta.get("final_score", "")
    if not final:
        timeline_warnings.append("Kein Endstand im Spielbericht (Spiel evtl. nicht abgeschlossen)")
    else:
        fh, fa = map(int, final.split(":"))
        if (h, a) != (fh, fa):
            timeline_warnings.append(f"Spielverlauf endet bei {h}:{a}, Endstand ist {final}")
        for side, expected in (("home", fh), ("away", fa)):
            total = sum(p["goals"] for p in teams[side]["players"])
            if total != expected:
                roster_warnings.append(
                    f"Kader {side}: Torsumme {total} statt {expected} "
                    f"({len(teams[side]['players'])} Spielerinnen erkannt)"
                )

    # Hinweis (beeinflusst "complete" nicht): Torschützen Kader vs. Verlauf
    for side in ("home", "away"):
        for p in teams[side]["players"]:
            n = goals_by_player.get((side, p["number"]), 0)
            if n != p["goals"]:
                notes.append(f"{side} #{p['number']} {p['name']}: Kader {p['goals']} Tore, Verlauf {n}")

    warnings = timeline_warnings + roster_warnings
    return {
        "complete": not warnings,
        "timeline_ok": not timeline_warnings,
        "roster_ok": not roster_warnings,
        "warnings": warnings,
        "notes": notes,
    }


# ---- 3g. Gesamt-Parser ------------------------------------------------------------------
def parse_match_pdf(pdf_path: Path, match_id: str, api_match: dict | None = None) -> dict:
    with pdfplumber.open(pdf_path) as pdf:
        meta = parse_metadata(pdf, match_id, api_match)
        referees, match_officials = parse_match_officials(pdf.pages[0])
        roster = parse_roster(pdf)
        timeline = parse_timeline(pdf)
        n_pages = len(pdf.pages)

    teams = {
        "home": {"name": meta["home_team"], **roster["home"]},
        "away": {"name": meta["away_team"], **roster["away"]},
    }
    enrich_players(teams, timeline)
    parse_info = run_checks(meta, teams, timeline)
    parse_info.update({
        "pages": n_pages,
        "events": len(timeline),
        "parsed_at": datetime.now().isoformat(timespec="seconds"),
    })
    return {
        "metadata": meta,
        "referees": referees,
        "match_officials": match_officials,
        "teams": teams,
        "timeline": timeline,
        "parse_info": parse_info,
    }


# ----------------------------------------------------------------------------
# 4. Hilfen & Batch-Verarbeitung
# ----------------------------------------------------------------------------
def json_state(path: Path) -> str:
    """missing | legacy (alter Parser) | incomplete | complete"""
    if not path.exists():
        return "missing"
    try:
        with open(path, "r", encoding="utf-8") as f:
            info = json.load(f).get("parse_info")
    except (json.JSONDecodeError, OSError):
        return "legacy"
    if not info:
        return "legacy"
    return "complete" if info.get("complete") else "incomplete"


def debug_pdf(match_id: str):
    pdf_path = RAW_DIR / f"match_{match_id}.pdf"
    if not pdf_path.exists():
        print(f"PDF nicht gefunden: {pdf_path}")
        return
    with pdfplumber.open(pdf_path) as pdf:
        for n, page in enumerate(pdf.pages, start=1):
            print(f"\n{'=' * 20} SEITE {n}: TEXT {'=' * 20}")
            print(page.extract_text())
            for t_idx, table in enumerate(page.extract_tables(), start=1):
                print(f"\n--- Seite {n}, Tabelle {t_idx} ({len(table)} Zeilen) ---")
                for row in table:
                    print(row)


def run_pipeline(args):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    matches = fetch_all_season_matches(offline=args.offline)
    if not matches:
        print("Keine Spiele gefunden.")
        return

    print(f"\nStarte Verarbeitung von {len(matches)} Spielen...")
    counts = {"complete": 0, "partial": 0, "skipped": 0, "no_pdf": 0, "error": 0}
    partial = []

    for idx, match in enumerate(matches, start=1):
        match_id = str(match["match_id"])
        pdf_path = RAW_DIR / f"match_{match_id}.pdf"
        json_path = OUT_DIR / f"match_{match_id}.json"
        state = json_state(json_path)

        if state == "complete" and not args.reparse:
            counts["skipped"] += 1
            continue

        print(f"[{idx:3d}/{len(matches)}] Match-ID {match_id} ... ", end="", flush=True)

        # PDF laden: fehlt sie, oder war das Spiel beim letzten Lauf noch unvollständig
        # (Spielbericht könnte inzwischen ergänzt worden sein)
        need_download = not args.offline and (
            not pdf_path.exists() or (state == "incomplete" and not args.reparse)
        )
        if need_download:
            download_pdf(match_id, pdf_path)
            time.sleep(0.3)
        if not pdf_path.exists():
            print("Keine PDF (Spiel noch nicht gespielt?)")
            counts["no_pdf"] += 1
            continue

        try:
            data = parse_match_pdf(pdf_path, match_id, match)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"FEHLER beim Parsen: {e}")
            counts["error"] += 1
            continue

        info = data["parse_info"]
        if info["complete"]:
            counts["complete"] += 1
            print(f"OK ({info['events']} Ereignisse)")
        else:
            counts["partial"] += 1
            partial.append((match_id, info["warnings"]))
            print(f"OK mit {len(info['warnings'])} Warnung(en): {info['warnings'][0]}")

    print("\n" + "=" * 50)
    print("FERTIG")
    print(f"Vollständig geparst:        {counts['complete']}")
    print(f"Mit Warnungen:              {counts['partial']}")
    print(f"Übersprungen (schon fertig): {counts['skipped']}")
    print(f"Keine PDF:                  {counts['no_pdf']}")
    print(f"Fehler:                     {counts['error']}")
    print("=" * 50)
    if partial:
        print("\nSpiele mit Warnungen (Details in parse_info.warnings der JSON):")
        for mid, warns in partial[:20]:
            print(f"  {mid}: {warns[0]}" + (f"  (+{len(warns) - 1} weitere)" if len(warns) > 1 else ""))
        print("\nTipp: python pipeline.py --debug <MATCH_ID> zeigt Rohtext und Rohtabellen der PDF.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Handball-Spielberichte laden und parsen")
    ap.add_argument("--reparse", action="store_true", help="vorhandene PDFs neu parsen, JSONs überschreiben")
    ap.add_argument("--offline", action="store_true", help="kein Netzwerkzugriff")
    ap.add_argument("--debug", metavar="MATCH_ID", help="Rohtext/Rohtabellen einer PDF ausgeben")
    args, _ = ap.parse_known_args()  # tolerant, falls im Notebook gestartet

    if args.debug:
        debug_pdf(args.debug)
    else:
        run_pipeline(args)