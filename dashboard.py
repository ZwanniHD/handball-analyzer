import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# --- 1. KONFIGURATION ---
st.set_page_config(page_title="Handball Liga-Analyse", layout="wide", page_icon="🤾")

CURRENT_DATE = datetime.now()
DATA_DIR = Path("data/processed")

# --- 2. DATEN LADEN & FILTERN ---
def default_team():
    return {
        "spiele": 0, "tore_erzielt": 0, "tore_kassiert": 0, 
        "siebenmeter_tore": 0, "siebenmeter_versuche": 0, "strafen_2min": 0,
        "zuschauer_gesamt": 0, "heimspiele": 0,
        "unterzahl_tore_erzielt": 0, "unterzahl_tore_kassiert": 0,
        "ueberzahl_tore_erzielt": 0, "ueberzahl_tore_kassiert": 0,
        "start_h1_tore": 0, "start_h1_geg": 0, "ende_h1_tore": 0, "ende_h1_geg": 0,
        "start_h2_tore": 0, "start_h2_geg": 0, "ende_h2_tore": 0, "ende_h2_geg": 0,
        "max_lauf": 0, "crunch_time_tore": 0, "max_comeback": 0,
        "schnelle_mitte_sekunden": [], "torkrisen_max_sekunden": 0,
        "ueberzahl_bilanz": [],
        "siege": 0, "unent": 0, "nieder": 0,
        "heim_punkte": 0, "heim_tore": 0, "heim_gegentore": 0,
        "ausw_punkte": 0, "ausw_tore": 0, "ausw_gegentore": 0,
        "siebenmeter_gegen": 0, "verwarnungen": 0, "disq": 0,
        "ht_fuehrung": 0, "ht_fuehrung_siege": 0, "ht_fuehrung_unent": 0,
        "ht_rueckstand": 0, "ht_rueckstand_siege": 0, "ht_rueckstand_unent": 0, "ht_gleich": 0,
        "tore_h1_erz": 0, "tore_h1_geg": 0, "tore_h2_erz": 0, "tore_h2_geg": 0,
        "sek_fuehrung": 0, "sek_gleich": 0, "sek_rueckstand": 0,
        "knapp_spiele": 0, "knapp_siege": 0, "knapp_unent": 0, "knapp_nieder": 0,
        "auszeiten": 0, "az_tore": 0, "az_geg": 0
    }

def default_player():
    return {
        "team": "", "tore": 0, "7m_tore": 0, "2min": 0,
        "spiele": 0, "max_tore_ein_spiel": 0,
        "tore_h1": 0, "tore_h2": 0, "clutch_tore": 0, "icebreaker": 0,
        "tore_frueh": 0, "tore_spaet": 0,    # NEU: Frühe/Späte Tore
        "strafen_frueh": 0, "strafen_spaet": 0, # NEU: Frühe/Späte Strafen
        "7m_versuche": 0, "verwarnungen": 0, "disq": 0
    }

@st.cache_data(ttl=3600)
def load_and_aggregate_data():
    team_stats = defaultdict(default_team)
    player_stats = defaultdict(default_player)
    referees_count = defaultdict(int)
    timekeepers_count = defaultdict(int)
    matchday_players = defaultdict(list)
    penalty_minutes = defaultdict(int)

    if not DATA_DIR.exists():
        return {}, {}, {}, {}, {}, {}, {}

    spiel_daten = []
    spiele_liste = []
    ref_stats = defaultdict(lambda: defaultdict(int))

    for file in DATA_DIR.glob("match_*.json"):
        with open(file, "r", encoding="utf-8") as f:
            match = json.load(f)
            
        meta = match.get("metadata", {})
        date_str = meta.get("date")
        matchday = meta.get("matchday", 0)
        
        parsed_date = None
        if date_str:
            try:
                match_date = datetime.strptime(date_str, "%d.%m.%Y")
                if match_date > CURRENT_DATE: continue
                parsed_date = match_date
            except ValueError: pass 

        if not meta.get("final_score"):   # noch nicht gespielt / nicht abgeschlossen
            continue
        if parsed_date:
            spiel_daten.append(parsed_date)

        ref_names = []
        for ref in match.get("referees", []) or meta.get("referees", []):
            name = ref.get("name") if isinstance(ref, dict) else ref
            if name:
                referees_count[name.strip()] += 1
                ref_names.append(name.strip())
                
        for off in match.get("match_officials", []):
            rolle = str(off.get("role", "")).lower()
            name = off.get("name")
            if name and any(k in rolle for k in ("zeitnehm", "sekret")):
                timekeepers_count[name.strip()] += 1

        teams = match.get("teams", {})
        if "home" not in teams or "away" not in teams: continue
            
        h_name = teams["home"].get("name", "Unbekannt")
        a_name = teams["away"].get("name", "Unbekannt")
        
        score = meta.get("final_score", "")
        h_goals, a_goals = 0, 0
        if ":" in score:
            try: h_goals, a_goals = map(int, score.split(":"))
            except: pass

        if h_goals > a_goals:
            team_stats[h_name]["siege"] += 1; team_stats[a_name]["nieder"] += 1
        elif a_goals > h_goals:
            team_stats[a_name]["siege"] += 1; team_stats[h_name]["nieder"] += 1
        else:
            team_stats[h_name]["unent"] += 1; team_stats[a_name]["unent"] += 1

        spectators = meta.get("spectators", 0)
        team_stats[h_name]["spiele"] += 1; team_stats[h_name]["heimspiele"] += 1
        team_stats[h_name]["tore_erzielt"] += h_goals; team_stats[h_name]["tore_kassiert"] += a_goals
        team_stats[h_name]["zuschauer_gesamt"] += spectators
        
        team_stats[a_name]["spiele"] += 1
        team_stats[a_name]["tore_erzielt"] += a_goals; team_stats[a_name]["tore_kassiert"] += h_goals

        side_sm = {"home": 0, "away": 0}        # 7m-Versuche je Seite
        strafen_side = {"home": 0, "away": 0}   # Zeitstrafen je Seite

        # Spieler-Grunddaten laden
        for side, t_name in [("home", h_name), ("away", a_name)]:
            for p in teams[side].get("players", []):
                p_name = p.get("name")
                if not p_name: continue
                
                p_id = f"{p_name} ({t_name})"
                p_goals = p.get("goals", 0)
                
                player_stats[p_id]["team"] = t_name
                player_stats[p_id]["spiele"] += 1 
                player_stats[p_id]["tore"] += p_goals
                player_stats[p_id]["2min"] += len(p.get("two_minutes", []))
                team_stats[t_name]["strafen_2min"] += len(p.get("two_minutes", []))
                strafen_side[side] += len(p.get("two_minutes", []))
                n_w, n_d = len(p.get("warnings", [])), len(p.get("disqualifications", []))
                player_stats[p_id]["verwarnungen"] += n_w; player_stats[p_id]["disq"] += n_d
                team_stats[t_name]["verwarnungen"] += n_w; team_stats[t_name]["disq"] += n_d
                
                if p_goals > player_stats[p_id]["max_tore_ein_spiel"]:
                    player_stats[p_id]["max_tore_ein_spiel"] = p_goals
                
                sm_str = p.get("seven_m")
                p_7m = 0
                if sm_str and "/" in sm_str:
                    try:
                        treffer, versuche = map(int, sm_str.split("/"))
                        p_7m = treffer
                        player_stats[p_id]["7m_tore"] += treffer
                        team_stats[t_name]["siebenmeter_tore"] += treffer
                        team_stats[t_name]["siebenmeter_versuche"] += versuche
                        player_stats[p_id]["7m_versuche"] += versuche
                        side_sm[side] += versuche
                    except: pass
                
                if p_goals > 0:
                    matchday_players[matchday].append({
                        "Name": p_name, "Team": t_name, 
                        "Tore": p_goals, "7m": p_7m, "Feldtore": p_goals - p_7m
                    })

        # --- SPIEL-ERGEBNIS-STATISTIKEN ---
        team_stats[h_name]["siebenmeter_gegen"] += side_sm["away"]
        team_stats[a_name]["siebenmeter_gegen"] += side_sm["home"]
        pts_h = 2 if h_goals > a_goals else (1 if h_goals == a_goals else 0)   # Sieg 2:0, Unentschieden 1:1, Niederlage 0:2
        pts_a = 2 - pts_h
        team_stats[h_name]["heim_punkte"] += pts_h; team_stats[h_name]["heim_tore"] += h_goals; team_stats[h_name]["heim_gegentore"] += a_goals
        team_stats[a_name]["ausw_punkte"] += pts_a; team_stats[a_name]["ausw_tore"] += a_goals; team_stats[a_name]["ausw_gegentore"] += h_goals

        if abs(h_goals - a_goals) <= 2:   # knappes Spiel
            for t_name, pts in ((h_name, pts_h), (a_name, pts_a)):
                team_stats[t_name]["knapp_spiele"] += 1
                team_stats[t_name]["knapp_siege" if pts == 2 else ("knapp_unent" if pts == 1 else "knapp_nieder")] += 1

        for rn in ref_names:
            r = ref_stats[rn]
            r["spiele"] += 1
            r["strafen_heim"] += strafen_side["home"]; r["strafen_gast"] += strafen_side["away"]
            r["tore"] += h_goals + a_goals
            r["heimsiege"] += 1 if h_goals > a_goals else 0
            r["heim_diff"] += h_goals - a_goals

        spiele_liste.append({"Spieltag": matchday, "Datum": parsed_date, "Heim": h_name, "Gast": a_name,
                             "Heimtore": h_goals, "Gasttore": a_goals, "Zuschauer": spectators})

        # --- TIMELINE ANALYSE ---
        timeline = match.get("timeline", [])
        current_run_team = None
        current_run_count = 0
        h_score_curr, a_score_curr = 0, 0
        max_deficit_home, max_deficit_away = 0, 0
        last_goal_time_h, last_goal_time_a = 0, 0
        last_scoring_team, last_scoring_time = None, 0
        first_goal_recorded = False
        active_penalties = []
        seen_penalties = set()
        lead_h = lead_a = tie_t = 0          # Sekunden Führung Heim / Führung Gast / Gleichstand
        last_t = 0
        ht_h = ht_a = 0                      # Halbzeitstand
        goals_log, auszeiten = [], []

        for event in timeline:
            ev_type = event.get("event", "").lower()
            ev_team = event.get("team", "").lower()
            p_name = event.get("person_name")
            
            prev_diff = h_score_curr - a_score_curr   # Spielstand VOR diesem Ereignis
            score_str = event.get("score", "0:0")
            if ":" in score_str:
                try:
                    sh, sa = map(int, score_str.split(":"))
                    h_score_curr, a_score_curr = sh, sa
                except: pass
            
            diff = h_score_curr - a_score_curr
            if diff < max_deficit_home: max_deficit_home = diff
            if diff > max_deficit_away: max_deficit_away = diff

            t_str = event.get("time", "00:00").replace("Uhr", "").strip()
            try:
                m, s = map(int, t_str.split(":"))
                sec = m * 60 + s
            except Exception: m, sec = 0, 0

            team_name = h_name if ev_team == "heim" else a_name
            opp_name = a_name if ev_team == "heim" else h_name
            p_id = f"{p_name} ({team_name})" if p_name else None

            if sec >= last_t:
                dt = sec - last_t
                if prev_diff > 0: lead_h += dt
                elif prev_diff < 0: lead_a += dt
                else: tie_t += dt
                last_t = sec

            # Phasen-Klassifizierung für Spieler-Individuelle Leistung (Früh vs. Spät)
            # Früh = Erste 10 Min pro Halbzeit (0-10 / 30-40)
            # Spät = Letzte 10 Min pro Halbzeit (20-30 / 50-60)
            spieler_phase = None
            if sec <= 600 or (1800 <= sec <= 2400):
                spieler_phase = "frueh"
            elif (1200 <= sec <= 1800) or (3000 <= sec <= 3600):
                spieler_phase = "spaet"

            is_penalty = ev_type in ("zwei minuten", "disqualifikation")
            pen_key = (ev_team, sec)
            if is_penalty and pen_key not in seen_penalties:   # "Zwei Minuten" + "Disqualifikation" gleichzeitig nur einmal
                seen_penalties.add(pen_key)
                if ev_type == "zwei minuten":
                    penalty_minutes[m] += 1
                current_diff = diff if ev_team == "heim" else -diff
                active_penalties.append({"team": team_name, "end_time": sec + 120, "start_diff": current_diff})

                # Spieler individuelle Strafen-Phase
                if ev_type == "zwei minuten" and p_id:
                    if spieler_phase == "frueh": player_stats[p_id]["strafen_frueh"] += 1
                    elif spieler_phase == "spaet": player_stats[p_id]["strafen_spaet"] += 1

            for pen in active_penalties[:]:
                if sec >= pen["end_time"]:
                    current_diff = prev_diff if pen["team"] == h_name else -prev_diff   # Stand bei Ablauf der Strafe
                    bilanz = current_diff - pen["start_diff"]
                    team_stats[a_name if pen["team"] == h_name else h_name]["ueberzahl_bilanz"].append(-bilanz)
                    active_penalties.remove(pen)

            if ev_type.startswith("auszeit"):
                auszeiten.append((sec, team_name))

            if ev_type in ("tor", "siebenmeter tor"):
                goals_log.append((sec, team_name))
                if sec <= 1800: ht_h, ht_a = h_score_curr, a_score_curr
                # Über-/Unterzahl: laufende Zeitstrafen beider Teams zum Zeitpunkt des Tores
                own_pen = sum(1 for p in active_penalties if p["team"] == team_name and p["end_time"] > sec)
                opp_pen = sum(1 for p in active_penalties if p["team"] == opp_name and p["end_time"] > sec)
                if opp_pen > own_pen:
                    team_stats[team_name]["ueberzahl_tore_erzielt"] += 1
                    team_stats[opp_name]["unterzahl_tore_kassiert"] += 1
                elif own_pen > opp_pen:
                    team_stats[team_name]["unterzahl_tore_erzielt"] += 1
                    team_stats[opp_name]["ueberzahl_tore_kassiert"] += 1

                if not first_goal_recorded and p_id:
                    player_stats[p_id]["icebreaker"] += 1
                    first_goal_recorded = True

                if p_id:
                    if sec <= 1800: player_stats[p_id]["tore_h1"] += 1
                    else: player_stats[p_id]["tore_h2"] += 1
                    
                    # Spieler individuelle Tor-Phase
                    if spieler_phase == "frueh": player_stats[p_id]["tore_frueh"] += 1
                    elif spieler_phase == "spaet": player_stats[p_id]["tore_spaet"] += 1

                if sec >= 3300 and abs(diff) <= 2:
                    team_stats[team_name]["crunch_time_tore"] += 1
                    if p_id:
                        player_stats[p_id]["clutch_tore"] += 1

                if team_name == current_run_team: current_run_count += 1
                else: current_run_team = team_name; current_run_count = 1
                
                if current_run_count > team_stats[team_name]["max_lauf"]:
                    team_stats[team_name]["max_lauf"] = current_run_count

                if last_scoring_team == opp_name:
                    response_time = sec - last_scoring_time
                    if 0 < response_time <= 45: 
                        team_stats[team_name]["schnelle_mitte_sekunden"].append(response_time)

                last_own_goal_time = last_goal_time_h if team_name == h_name else last_goal_time_a
                drought = sec - last_own_goal_time
                if drought > team_stats[team_name]["torkrisen_max_sekunden"]:
                    team_stats[team_name]["torkrisen_max_sekunden"] = drought

                if team_name == h_name: last_goal_time_h = sec
                else: last_goal_time_a = sec
                last_scoring_team, last_scoring_time = team_name, sec

                # Team 5-Minuten Phasen
                phase_key = None
                if sec <= 300: phase_key = "start_h1"
                elif 1500 <= sec <= 1800: phase_key = "ende_h1"
                elif 1800 < sec <= 2100: phase_key = "start_h2"
                elif 3300 <= sec <= 3600: phase_key = "ende_h2"

                if phase_key:
                    team_stats[team_name][f"{phase_key}_tore"] += 1
                    team_stats[opp_name][f"{phase_key}_geg"] += 1

        final_diff = h_score_curr - a_score_curr
        if timeline:
            dt_end = max(3600, last_t) - last_t
            if final_diff > 0: lead_h += dt_end
            elif final_diff < 0: lead_a += dt_end
            else: tie_t += dt_end
            for t_name, f_sek, r_sek in ((h_name, lead_h, lead_a), (a_name, lead_a, lead_h)):
                ts = team_stats[t_name]
                ts["sek_fuehrung"] += f_sek; ts["sek_rueckstand"] += r_sek; ts["sek_gleich"] += tie_t

            if ht_h <= h_goals and ht_a <= a_goals:   # Plausibilität
                for t_name, ht_own, ht_opp, f_own, f_opp in ((h_name, ht_h, ht_a, h_goals, a_goals),
                                                              (a_name, ht_a, ht_h, a_goals, h_goals)):
                    ts = team_stats[t_name]
                    ts["tore_h1_erz"] += ht_own; ts["tore_h1_geg"] += ht_opp
                    ts["tore_h2_erz"] += f_own - ht_own; ts["tore_h2_geg"] += f_opp - ht_opp
                    key = "ht_fuehrung" if ht_own > ht_opp else ("ht_rueckstand" if ht_own < ht_opp else "ht_gleich")
                    ts[key] += 1
                    if key != "ht_gleich":
                        if f_own > f_opp: ts[key + "_siege"] += 1
                        elif f_own == f_opp: ts[key + "_unent"] += 1

            for az_sec, az_team in auszeiten:   # Tore in den 5 Minuten nach einer Auszeit
                ts = team_stats[az_team]
                ts["auszeiten"] += 1
                for g_sec, g_team in goals_log:
                    if az_sec < g_sec <= az_sec + 300:
                        ts["az_tore" if g_team == az_team else "az_geg"] += 1
        for pen in active_penalties:
            current_diff = final_diff if pen["team"] == h_name else -final_diff
            bilanz = current_diff - pen["start_diff"]
            team_stats[a_name if pen["team"] == h_name else h_name]["ueberzahl_bilanz"].append(-bilanz)

        if h_goals >= a_goals:
            if abs(max_deficit_home) > team_stats[h_name]["max_comeback"]: team_stats[h_name]["max_comeback"] = abs(max_deficit_home)
        if a_goals >= h_goals:
            if max_deficit_away > team_stats[a_name]["max_comeback"]: team_stats[a_name]["max_comeback"] = max_deficit_away

    return dict(team_stats), dict(player_stats), dict(referees_count), dict(timekeepers_count), dict(matchday_players), dict(penalty_minutes), {
        "spiele": len(spiel_daten),
        "letztes_datum": max(spiel_daten) if spiel_daten else None,
        "spiele_liste": spiele_liste,
        "ref_stats": {k: dict(v) for k, v in ref_stats.items()},
    }

team_data, player_data, ref_data, tk_data, matchday_data, penalty_data, data_info = load_and_aggregate_data()

# --- 3. DATEN AUFBEREITEN ---
if not team_data:
    st.warning("Keine Spieldaten gefunden oder alle Spiele liegen in der Zukunft.")
    st.stop()

def _mean(x):
    return sum(x) / len(x) if len(x) else 0

df_teams = pd.DataFrame.from_dict(team_data, orient="index").reset_index()
df_teams.rename(columns={"index": "Team"}, inplace=True)
df_teams["Tore/Spiel"] = df_teams["tore_erzielt"] / df_teams["spiele"]
df_teams["Gegentore/Spiel"] = df_teams["tore_kassiert"] / df_teams["spiele"]
df_teams["2Min/Spiel"] = df_teams["strafen_2min"] / df_teams["spiele"]
df_teams["7m-Quote (%)"] = (df_teams["siebenmeter_tore"] / df_teams["siebenmeter_versuche"] * 100).fillna(0)
df_teams["Ø Zuschauer"] = (df_teams["zuschauer_gesamt"] / df_teams["heimspiele"]).fillna(0)
df_teams["Ø_Schnelle_Mitte_Sek"] = df_teams["schnelle_mitte_sekunden"].apply(_mean)
df_teams["Ø_Ueberzahl_PlusMinus"] = df_teams["ueberzahl_bilanz"].apply(_mean)
df_teams["Torkrise_Max_Min"] = df_teams["torkrisen_max_sekunden"] / 60
df_teams["Tordifferenz"] = df_teams["tore_erzielt"] - df_teams["tore_kassiert"]
df_teams["Punkte"] = 2 * df_teams["siege"] + df_teams["unent"]          # 2 Punkte Sieg, 1 Punkt Unentschieden
df_teams["Ueberzahl_Saldo"] = df_teams["ueberzahl_tore_erzielt"] - df_teams["ueberzahl_tore_kassiert"]
df_teams["Unterzahl_Saldo"] = df_teams["unterzahl_tore_erzielt"] - df_teams["unterzahl_tore_kassiert"]

df_teams["Minuspunkte"] = 2 * df_teams["spiele"] - df_teams["Punkte"]
df_teams["Punkte_Text"] = df_teams["Punkte"].astype(int).astype(str) + ":" + df_teams["Minuspunkte"].astype(int).astype(str)

# Spieleliste (ein Eintrag pro Spiel) und Ergebnisse je Team (zwei Einträge pro Spiel)
df_games = pd.DataFrame(data_info.get("spiele_liste", []),
                        columns=["Spieltag", "Datum", "Heim", "Gast", "Heimtore", "Gasttore", "Zuschauer"])
if not df_games.empty:
    df_games["Tore gesamt"] = df_games["Heimtore"] + df_games["Gasttore"]
    df_games["Differenz"] = df_games["Heimtore"] - df_games["Gasttore"]          # aus Sicht des Heimteams
    df_games["Ergebnis"] = df_games["Heimtore"].astype(str) + ":" + df_games["Gasttore"].astype(str)
    df_games = df_games.sort_values(["Spieltag", "Datum"], kind="stable").reset_index(drop=True)

def _results_long(g):
    cols = ["Team", "Gegner", "Ort", "Tore", "Gegentore", "Spieltag", "Datum"]
    if g.empty:
        return pd.DataFrame(columns=cols + ["Punkte", "Erg"])
    heim = pd.DataFrame({"Team": g["Heim"], "Gegner": g["Gast"], "Ort": "Heim", "Tore": g["Heimtore"],
                         "Gegentore": g["Gasttore"], "Spieltag": g["Spieltag"], "Datum": g["Datum"]})
    ausw = pd.DataFrame({"Team": g["Gast"], "Gegner": g["Heim"], "Ort": "Auswärts", "Tore": g["Gasttore"],
                         "Gegentore": g["Heimtore"], "Spieltag": g["Spieltag"], "Datum": g["Datum"]})
    r = pd.concat([heim, ausw], ignore_index=True)
    r["Punkte"] = (r["Tore"] > r["Gegentore"]).astype(int) * 2 + (r["Tore"] == r["Gegentore"]).astype(int)
    r["Erg"] = r["Punkte"].map({2: "S", 1: "U", 0: "N"})
    return r.sort_values(["Spieltag", "Datum"], kind="stable").reset_index(drop=True)

df_res = _results_long(df_games)

df_players = pd.DataFrame.from_dict(player_data, orient="index").reset_index()
df_players.rename(columns={"index": "Name_Raw"}, inplace=True)   # Name_Raw = "Name (Team)"
df_players["Name"] = df_players["Name_Raw"].apply(lambda x: x.split(" (")[0])
df_players["Feldtore"] = df_players["tore"] - df_players["7m_tore"]


# --- 4. DARSTELLUNG: STYLE & HELFER ---
st.markdown(
    """
    <style>
    .block-container {padding-top: 2.2rem; max-width: 1500px;}
    div[data-testid="stMetric"] {
        background: rgba(128,128,128,0.08);
        border: 1px solid rgba(128,128,128,0.22);
        border-radius: 12px; padding: 12px 16px;
    }
    button[data-baseweb="tab"] {font-weight: 600;}
    h1 {margin-bottom: 0.2rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


def show(fig):
    """Zentrale Stelle für alle Plotly-Charts (bei Streamlit-Updates nur hier anpassen)."""
    st.plotly_chart(fig, width="stretch")


def ranking(df, col, title, color="#3366cc", fmt=".1f", label="Team",
            lower_is_better=False, top=None, color_by=None, hide_if_all_zero=False):
    """Horizontales Ranking: bester Wert immer OBEN, bei Gleichstand alphabetisch.
    Standard: größter Wert oben. Bei lower_is_better: kleinster Wert oben."""
    if df is None or df.empty:
        st.info(f"Noch keine Daten für: {title}")
        return
    cols = [label, col] + ([color_by] if color_by else [])
    d = df[cols].dropna(subset=[col])
    if d.empty or (hide_if_all_zero and (d[col] == 0).all()):
        st.info(f"Noch keine Daten für: {title}")
        return
    d = d.sort_values([col, label], ascending=[lower_is_better, True], kind="stable")
    if top:
        d = d.head(top)
    order = d[label].tolist()

    fig = px.bar(
        d, x=col, y=label, orientation="h", text=col,
        color=color_by, color_discrete_sequence=None if color_by else [color],
    )
    fig.update_traces(texttemplate=f"%{{x:{fmt}}}", textposition="outside", cliponaxis=False)
    # Plotly zeichnet das erste Element der Liste UNTEN -> Liste umdrehen, damit der beste Wert oben steht
    fig.update_yaxes(categoryorder="array", categoryarray=order[::-1], title=None, automargin=True)
    fig.update_xaxes(title=None, showgrid=True, gridcolor="rgba(128,128,128,0.15)", zeroline=True)
    suffix = "  <span style='font-size:12px;opacity:.6'>· niedrigster Wert oben</span>" if lower_is_better else ""
    fig.update_layout(
        title=dict(text=title + suffix, x=0, font=dict(size=16)),
        height=max(260, 32 * len(d) + 100),
        margin=dict(l=0, r=40, t=55, b=10),
        showlegend=False, bargap=0.25,
    )
    show(fig)


def compare_chart(rows, name_col, colors, fmt=".1f"):
    """Vergleich zweier Teams/Spielerinnen: pro Kennzahl eine eigene Skala (kein Mischen von 7m-% und Toren)."""
    fig = px.bar(
        pd.DataFrame(rows), x=name_col, y="Wert", color=name_col, facet_col="Metrik", facet_col_wrap=3,
        text_auto=fmt, color_discrete_sequence=colors,
    )
    fig.update_yaxes(matches=None, showticklabels=False, title=None)
    fig.update_xaxes(showticklabels=False, title=None)
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
    fig.update_layout(legend=dict(title=None, orientation="h", y=1.12, x=0), height=520, margin=dict(t=80, b=10))
    show(fig)


def table(df, rename=None, height=None, column_config=None):
    """Tabelle mit Rang statt anonymem Index, lesbaren Spaltennamen und gerundeten Zahlen."""
    d = df.rename(columns=rename or {}).round(1).reset_index(drop=True)
    d.index = d.index + 1
    d.index.name = "Rang"
    kwargs = {}
    if height:
        kwargs["height"] = height
    if column_config:
        kwargs["column_config"] = column_config
    st.dataframe(d, width="stretch", **kwargs)


def note(text):
    st.caption(text)


def sdiv(a, b):
    """Sichere Division (Serie / Serie): 0 statt NaN/Inf, wenn der Nenner 0 ist."""
    return (a / b.where(b != 0)).fillna(0)


FORM_ICON = {"S": "🟢", "U": "🟡", "N": "🔴"}


def table_history():
    """Tabellenstand nach jedem Spieltag (kumuliert): Platz, Punkte, Tordifferenz."""
    frames = []
    for md in sorted(df_res["Spieltag"].unique()):
        sub = df_res[df_res["Spieltag"] <= md]
        agg = (sub.groupby("Team")
               .agg(Punkte=("Punkte", "sum"), Tore=("Tore", "sum"), Gegentore=("Gegentore", "sum"))
               .reset_index())
        agg["Diff"] = agg["Tore"] - agg["Gegentore"]
        agg = agg.sort_values(["Punkte", "Diff", "Tore", "Team"], ascending=[False, False, False, True])
        agg["Platz"] = range(1, len(agg) + 1)
        agg["Spieltag"] = md
        frames.append(agg)
    return pd.concat(frames, ignore_index=True)


# ==========================================
# BEREICH 1: LIGA
# ==========================================
def tab_liga():
    spiele = int(df_teams["spiele"].sum() // 2)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Teams", len(df_teams))
    k2.metric("Gespielte Spiele", spiele)
    k3.metric("Ø Tore pro Spiel (beide Teams)", f"{df_teams['tore_erzielt'].sum() / max(1, spiele):.1f}")
    k4.metric("Ø Zuschauer (Heimspiele)",
              f"{df_teams['zuschauer_gesamt'].sum() / max(1, df_teams['heimspiele'].sum()):.0f}")
    st.write("")

    t_tab, t_form, t_home, t_off, t_disc, t_games = st.tabs(
        ["📋 Tabelle", "📈 Form & Verlauf", "🏠 Heim & Auswärts", "🔥 Offensive & Defensive",
         "🎯 7m & Disziplin", "🎲 Spiele & Rekorde"])

    # ---- Tabelle: Punkte als Plus:Minus (Sieg 2:0, Unentschieden 1:1, Niederlage 0:2) ----
    with t_tab:
        d = df_teams.sort_values(["Punkte", "Tordifferenz", "tore_erzielt", "Team"],
                                 ascending=[False, False, False, True])
        tab_df = d[["Team", "spiele", "siege", "unent", "nieder", "tore_erzielt", "tore_kassiert",
                    "Tordifferenz", "Punkte_Text"]].copy()
        tab_df["Tore"] = tab_df["tore_erzielt"].astype(int).astype(str) + ":" + tab_df["tore_kassiert"].astype(int).astype(str)
        tab_df = tab_df[["Team", "spiele", "siege", "unent", "nieder", "Tore", "Tordifferenz", "Punkte_Text"]]
        table(tab_df, {"spiele": "Sp", "siege": "S", "unent": "U", "nieder": "N", "Tordifferenz": "Diff",
                       "Punkte_Text": "Punkte"},
              height=min(600, 36 * len(tab_df) + 40))
        note("Punkte als Pluspunkte:Minuspunkte – Sieg 2:0, Unentschieden 1:1, Niederlage 0:2. "
             "Sortierung: Pluspunkte, Tordifferenz, erzielte Tore. Berechnet aus den Spielberichten, nicht offiziell "
             "(Punktabzüge o. Ä. fehlen).")

    # ---- Form & Verlauf ----
    with t_form:
        if df_res.empty:
            st.info("Noch keine Spiele vorhanden.")
        else:
            hist = table_history()
            c1, c2 = st.columns(2)
            with c1:
                fig = px.line(hist, x="Spieltag", y="Platz", color="Team", markers=True)
                fig.update_yaxes(autorange="reversed", dtick=1, title="Tabellenplatz")
                fig.update_xaxes(dtick=1)
                fig.update_layout(title=dict(text="Tabellenplatz nach Spieltag", x=0, font=dict(size=16)),
                                  height=480, margin=dict(l=0, r=10, t=55, b=10), legend=dict(title=None))
                show(fig)
            with c2:
                fig = px.line(hist, x="Spieltag", y="Punkte", color="Team", markers=True)
                fig.update_xaxes(dtick=1)
                fig.update_layout(title=dict(text="Pluspunkte kumuliert", x=0, font=dict(size=16)),
                                  height=480, margin=dict(l=0, r=10, t=55, b=10), legend=dict(title=None))
                show(fig)

            st.subheader("Form – letzte 5 Spiele")
            rows = []
            for team, g in df_res.groupby("Team"):
                last = g.tail(5)
                rows.append({
                    "Team": team,
                    "Form (älteste → neueste)": " ".join(FORM_ICON[e] for e in last["Erg"]),
                    "Pluspunkte": int(last["Punkte"].sum()),
                    "Tordifferenz": int(last["Tore"].sum() - last["Gegentore"].sum()),
                })
            form = pd.DataFrame(rows).sort_values(["Pluspunkte", "Tordifferenz", "Team"],
                                                  ascending=[False, False, True])
            table(form)
            note("🟢 Sieg · 🟡 Unentschieden · 🔴 Niederlage. Sortiert nach Punkten der letzten 5 Spiele.")

    # ---- Heim & Auswärts ----
    with t_home:
        if df_games.empty:
            st.info("Noch keine Spiele vorhanden.")
        else:
            n = len(df_games)
            k1, k2, k3, k4, k5 = st.columns(5)
            k1.metric("Heimsiege", f"{(df_games['Differenz'] > 0).sum() / n * 100:.0f} %")
            k2.metric("Unentschieden", f"{(df_games['Differenz'] == 0).sum() / n * 100:.0f} %")
            k3.metric("Auswärtssiege", f"{(df_games['Differenz'] < 0).sum() / n * 100:.0f} %")
            k4.metric("Ø Tore Heim", f"{df_games['Heimtore'].mean():.1f}")
            k5.metric("Ø Tore Gast", f"{df_games['Gasttore'].mean():.1f}")
            st.write("")

            h = df_teams.copy()
            h["ausw_spiele"] = h["spiele"] - h["heimspiele"]
            h["Heim_Ausbeute"] = sdiv(h["heim_punkte"], 2 * h["heimspiele"]) * 100
            h["Ausw_Ausbeute"] = sdiv(h["ausw_punkte"], 2 * h["ausw_spiele"]) * 100
            h["Heimvorteil"] = h["Heim_Ausbeute"] - h["Ausw_Ausbeute"]

            c1, c2 = st.columns(2)
            with c1:
                ranking(h[h["heimspiele"] > 0], "Heim_Ausbeute", "🏠 Heimstärke – Punkteausbeute (%)", "#1f77b4", fmt=".0f")
            with c2:
                ranking(h[h["ausw_spiele"] > 0], "Ausw_Ausbeute", "🚌 Auswärtsstärke – Punkteausbeute (%)", "#ff7f0e", fmt=".0f")
            ranking(h[(h["heimspiele"] > 0) & (h["ausw_spiele"] > 0)], "Heimvorteil",
                    "Heimvorteil (Heim- minus Auswärts-Ausbeute, Prozentpunkte)", "#2ca02c", fmt="+.0f")

            ht = pd.DataFrame({
                "Team": h["Team"],
                "Heim Sp": h["heimspiele"],
                "Heim Punkte": h["heim_punkte"].astype(int).astype(str) + ":" + (2 * h["heimspiele"] - h["heim_punkte"]).astype(int).astype(str),
                "Heim Ø Tore": sdiv(h["heim_tore"], h["heimspiele"]),
                "Heim Ø Gegentore": sdiv(h["heim_gegentore"], h["heimspiele"]),
                "Ausw Sp": h["ausw_spiele"],
                "Ausw Punkte": h["ausw_punkte"].astype(int).astype(str) + ":" + (2 * h["ausw_spiele"] - h["ausw_punkte"]).astype(int).astype(str),
                "Ausw Ø Tore": sdiv(h["ausw_tore"], h["ausw_spiele"]),
                "Ausw Ø Gegentore": sdiv(h["ausw_gegentore"], h["ausw_spiele"]),
                "_sort": h["heim_punkte"] + h["ausw_punkte"],
            }).sort_values(["_sort", "Team"], ascending=[False, True]).drop(columns="_sort")
            table(ht, height=min(600, 36 * len(ht) + 40))

    # ---- Offensive & Defensive ----
    with t_off:
        c1, c2 = st.columns(2)
        with c1:
            ranking(df_teams, "Tore/Spiel", "🔥 Beste Offensive – Tore pro Spiel", "#3366cc")
        with c2:
            ranking(df_teams, "Gegentore/Spiel", "🧱 Beste Defensive – Gegentore pro Spiel", "#109618",
                    lower_is_better=True)
        ranking(df_teams, "Tordifferenz", "⚖️ Tordifferenz gesamt", "#17becf", fmt="+.0f")

    # ---- 7m & Disziplin ----
    with t_disc:
        c1, c2 = st.columns(2)
        with c1:
            ranking(df_teams[df_teams["siebenmeter_versuche"] > 5], "7m-Quote (%)",
                    "🎯 7-Meter-Quote (ab 6 Versuchen)", "#ff9900", fmt=".0f")
        with c2:
            ranking(df_teams, "2Min/Spiel", "⚠️ Meiste Zeitstrafen pro Spiel", "#dc3912",
                    hide_if_all_zero=True)

        st.subheader("7-Meter-Detail")
        sm = df_teams.copy()
        sm7 = pd.DataFrame({
            "Team": sm["Team"],
            "7m geworfen": sm["siebenmeter_versuche"],
            "Tore": sm["siebenmeter_tore"],
            "Fehlwürfe": sm["siebenmeter_versuche"] - sm["siebenmeter_tore"],
            "Quote (%)": sm["7m-Quote (%)"],
            "Fehlwurfquote (%)": (100 - sm["7m-Quote (%)"]).where(sm["siebenmeter_versuche"] > 0, 0),
            "7m zugesprochen / Spiel": sdiv(sm["siebenmeter_versuche"], sm["spiele"]),
            "7m gegen uns / Spiel": sdiv(sm["siebenmeter_gegen"], sm["spiele"]),
        }).sort_values(["7m zugesprochen / Spiel", "Team"], ascending=[False, True])
        table(sm7, height=min(600, 36 * len(sm7) + 40))
        note("„zugesprochen“ = eigene 7-Meter pro Spiel, „gegen uns“ = 7-Meter des Gegners. Sortiert nach zugesprochenen 7m.")

        st.subheader("Fairness-Tabelle")
        fair = pd.DataFrame({
            "Team": df_teams["Team"],
            "Zeitstrafen": df_teams["strafen_2min"],
            "Zeitstrafen / Spiel": df_teams["2Min/Spiel"],
            "Verwarnungen": df_teams["verwarnungen"],
            "Disqualifikationen": df_teams["disq"],
        }).sort_values(["Zeitstrafen / Spiel", "Verwarnungen", "Team"], ascending=[False, False, True])
        table(fair, height=min(600, 36 * len(fair) + 40))
        note("Sortiert nach Zeitstrafen pro Spiel – oben stehen die „unfairsten“ Teams.")

    # ---- Spiele & Rekorde ----
    with t_games:
        if df_games.empty:
            st.info("Noch keine Spiele vorhanden.")
        else:
            cols = ["Spieltag", "Heim", "Gast", "Ergebnis"]
            c1, c2, c3 = st.columns(3)
            with c1:
                st.subheader("Torreichste Spiele")
                x = df_games.sort_values(["Tore gesamt", "Spieltag"], ascending=[False, True]).head(5)
                table(x[cols + ["Tore gesamt"]])
            with c2:
                st.subheader("Torärmste Spiele")
                x = df_games.sort_values(["Tore gesamt", "Spieltag"], ascending=[True, True]).head(5)
                table(x[cols + ["Tore gesamt"]])
            with c3:
                st.subheader("Höchste Siege")
                x = df_games.assign(Abstand=df_games["Differenz"].abs()).sort_values(
                    ["Abstand", "Spieltag"], ascending=[False, True]).head(5)
                table(x[cols + ["Abstand"]])

            st.subheader("Knappe Spiele (höchstens 2 Tore Unterschied)")
            kn = df_teams.assign(Knapp_Punkte=2 * df_teams["knapp_siege"] + df_teams["knapp_unent"])
            kn["Knapp_Siegquote"] = sdiv(kn["knapp_siege"], kn["knapp_spiele"]) * 100
            c1, c2 = st.columns([3, 2])
            with c1:
                table(kn.sort_values(["Knapp_Punkte", "knapp_spiele", "Team"], ascending=[False, False, True])
                      [["Team", "knapp_spiele", "knapp_siege", "knapp_unent", "knapp_nieder", "Knapp_Punkte"]],
                      {"knapp_spiele": "Knappe Spiele", "knapp_siege": "S", "knapp_unent": "U",
                       "knapp_nieder": "N", "Knapp_Punkte": "Pluspunkte"},
                      height=min(600, 36 * len(kn) + 40))
            with c2:
                ranking(kn[kn["knapp_spiele"] >= 3], "Knapp_Siegquote",
                        "Siegquote in knappen Spielen (ab 3 Spielen)", "#9467bd", fmt=".0f")


# ==========================================
# BEREICH 2: TEAMS
# ==========================================
def kader_df():
    """Torverteilung je Team: Abhängigkeit von der Topscorerin und Kadertiefe."""
    rows = []
    for team, g in df_players.groupby("team"):
        total = g["tore"].sum()
        if total == 0:
            continue
        g = g.sort_values(["tore", "Name"], ascending=[False, True])
        rows.append({
            "Team": team,
            "Top-Torschützin": g.iloc[0]["Name"],
            "Top1_Anteil": g.iloc[0]["tore"] / total * 100,
            "Top3_Anteil": g["tore"].head(3).sum() / total * 100,
            "Kadertiefe": int((g["tore"] / total >= 0.10).sum()),
            "Torschützinnen": int((g["tore"] > 0).sum()),
            "Tore": int(total),
        })
    return pd.DataFrame(rows)


def tab_teams():
    t_detail, t_kader, t_h2h = st.tabs(["🔍 Team-Analyse", "👥 Kader & Abhängigkeit", "⚔️ Team-Vergleich (H2H)"])

    with t_detail:
        team = st.selectbox("Team wählen:", sorted(df_teams["Team"].tolist()), key="team_detail")
        row = df_teams[df_teams["Team"] == team].iloc[0]

        k1, k2, k3, k4, k5, k6 = st.columns(6)
        k1.metric("Spiele", int(row["spiele"]))
        k2.metric("Punkte", row["Punkte_Text"])
        k3.metric("Bilanz (S-U-N)", f"{int(row['siege'])}-{int(row['unent'])}-{int(row['nieder'])}")
        k4.metric("Ø Tore erzielt", f"{row['Tore/Spiel']:.1f}")
        k5.metric("Ø Gegentore", f"{row['Gegentore/Spiel']:.1f}")
        k6.metric("7m-Quote", f"{row['7m-Quote (%)']:.0f} %")
        st.write("")

        tp = df_players[df_players["team"] == team]
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Top-Torschützinnen")
            table(tp.sort_values(["tore", "spiele", "Name"], ascending=[False, True, True]).head(15)
                  [["Name", "spiele", "tore", "7m_tore"]],
                  {"spiele": "Spiele", "tore": "Tore", "7m_tore": "davon 7m"})
        with c2:
            st.subheader("Zeitstrafen")
            strafen = tp[tp["2min"] > 0].sort_values(["2min", "Name"], ascending=[False, True])[["Name", "2min"]]
            if strafen.empty:
                st.info("Keine Zeitstrafen.")
            else:
                table(strafen, {"2min": "2-Minuten"})

        st.subheader("Spiele der Saison")
        sp = df_res[df_res["Team"] == team]
        if sp.empty:
            st.info("Noch keine Spiele.")
        else:
            sp = sp.assign(Ergebnis=sp["Tore"].astype(str) + ":" + sp["Gegentore"].astype(str),
                           Form=sp["Erg"].map(FORM_ICON))
            table(sp[["Spieltag", "Ort", "Gegner", "Ergebnis", "Form", "Punkte"]].rename(columns={"Punkte": "Pluspunkte"}))

    with t_kader:
        kd = kader_df()
        if kd.empty:
            st.info("Noch keine Torschützinnen-Daten.")
        else:
            c1, c2 = st.columns(2)
            with c1:
                ranking(kd, "Top1_Anteil", "Abhängigkeit von der Topscorerin (% der Teamtore)", "#d62728", fmt=".0f")
            with c2:
                ranking(kd, "Kadertiefe", "Kadertiefe – Spielerinnen mit ≥ 10 % der Teamtore", "#2ca02c", fmt=".0f")
            table(kd.sort_values(["Top1_Anteil", "Team"], ascending=[False, True])
                  [["Team", "Top-Torschützin", "Top1_Anteil", "Top3_Anteil", "Kadertiefe", "Torschützinnen", "Tore"]],
                  {"Top1_Anteil": "Top 1 (%)", "Top3_Anteil": "Top 3 (%)", "Torschützinnen": "Spielerinnen mit Tor",
                   "Tore": "Tore (Kader)"},
                  height=min(600, 36 * len(kd) + 40))
            note("Hoher Top-1-Anteil = Team hängt stark an einer Spielerin. Kadertiefe zählt Spielerinnen, "
                 "die mindestens 10 % der Teamtore erzielt haben. Basis: Torschützinnen der Spielberichte.")

    with t_h2h:
        teams = sorted(df_teams["Team"].tolist())
        c1, c2 = st.columns(2)
        team_a = c1.selectbox("Team A", teams, index=0, key="h2h_a")
        team_b = c2.selectbox("Team B", teams, index=1 if len(teams) > 1 else 0, key="h2h_b")
        if team_a == team_b:
            st.info("Bitte zwei verschiedene Teams wählen.")
        else:
            a = df_teams[df_teams["Team"] == team_a].iloc[0]
            b = df_teams[df_teams["Team"] == team_b].iloc[0]
            kpis = {"Tore/Spiel": "Tore/Spiel", "Gegentore/Spiel": "Gegentore/Spiel", "2Min/Spiel": "2Min/Spiel",
                    "7m-Quote (%)": "7m-Quote (%)", "Punkte": "Pluspunkte", "Tordifferenz": "Tordifferenz"}
            rows = []
            for kpi, name in kpis.items():
                rows.append({"Metrik": name, "Team": team_a, "Wert": a[kpi]})
                rows.append({"Metrik": name, "Team": team_b, "Wert": b[kpi]})
            compare_chart(rows, "Team", ["#3366cc", "#ff9900"])

            direkt = df_games[((df_games["Heim"] == team_a) & (df_games["Gast"] == team_b)) |
                              ((df_games["Heim"] == team_b) & (df_games["Gast"] == team_a))] if not df_games.empty else df_games
            if len(direkt):
                st.subheader("Direkte Duelle")
                table(direkt[["Spieltag", "Heim", "Gast", "Ergebnis"]])


# ==========================================
# BEREICH 4: SPIELVERLAUF
# ==========================================
def tab_flow():
    t_ph, t_run, t_crunch, t_react, t_cond, t_half, t_az = st.tabs(
        ["⏱️ 5-Minuten-Phasen", "🔗 Torserien", "🧊 Crunch-Time & Comebacks",
         "⚡ Reaktion & Krisen", "🏃‍♀️ Kondition (H1 vs. H2)", "🕐 Halbzeiten & Führung", "⏸️ Auszeiten"])

    with t_ph:
        phasen = {
            "Start 1. Halbzeit (0–5 Min)": ("start_h1_tore", "start_h1_geg"),
            "Ende 1. Halbzeit (25–30 Min)": ("ende_h1_tore", "ende_h1_geg"),
            "Start 2. Halbzeit (30–35 Min)": ("start_h2_tore", "start_h2_geg"),
            "Ende 2. Halbzeit (55–60 Min)": ("ende_h2_tore", "ende_h2_geg"),
        }
        phase = st.radio("Phase:", list(phasen), horizontal=True, key="phase_wahl")
        c_tore, c_geg = phasen[phase]
        d = df_teams.assign(Phasen_Diff=df_teams[c_tore] - df_teams[c_geg])
        c1, c2 = st.columns(2)
        with c1:
            ranking(d, c_tore, f"Geworfene Tore – {phase}", "#1f77b4", fmt=".0f")
        with c2:
            ranking(d, "Phasen_Diff", f"Tordifferenz (+/−) – {phase}", "#ff7f0e", fmt="+.0f")

    with t_run:
        ranking(df_teams, "max_lauf", "Längste Torserie (Tore am Stück)", "#2ca02c", fmt=".0f")

    with t_crunch:
        note("Crunch-Time: Tore ab Minute 55 bei höchstens 2 Toren Differenz.")
        c1, c2 = st.columns(2)
        with c1:
            ranking(df_teams, "crunch_time_tore", "Nervenstärke – Tore in der Crunch-Time", "#d62728",
                    fmt=".0f", hide_if_all_zero=True)
        with c2:
            ranking(df_teams, "max_comeback", "Größter aufgeholter Rückstand", "#9467bd", fmt=".0f")

    with t_react:
        c1, c2 = st.columns(2)
        with c1:
            ranking(df_teams[df_teams["Ø_Schnelle_Mitte_Sek"] > 0], "Ø_Schnelle_Mitte_Sek",
                    "Ø Reaktionszeit nach Gegentor (Sek.)", "#e377c2", lower_is_better=True)
        with c2:
            ranking(df_teams, "Torkrise_Max_Min", "Längste Torflaute (Minuten)", "#7f7f7f", lower_is_better=True)

    with t_cond:
        note("Positiver Wert = Spielerin trifft in der 2. Halbzeit häufiger. Nur Spielerinnen mit > 5 Toren in einer Halbzeit.")
        cond = df_players[(df_players["tore_h1"] > 5) | (df_players["tore_h2"] > 5)].copy()
        if cond.empty:
            st.info("Noch keine Spielerinnen mit mehr als 5 Toren in einer Halbzeit.")
        else:
            cond["H2_Dominanz"] = cond["tore_h2"] - cond["tore_h1"]
            table(cond.sort_values(["H2_Dominanz", "Name"], ascending=[False, True])
                  [["Name", "team", "tore_h1", "tore_h2", "H2_Dominanz"]],
                  {"team": "Team", "tore_h1": "Tore H1", "tore_h2": "Tore H2", "H2_Dominanz": "H2-Dominanz"})

    # ---- Halbzeiten & Führung ----
    with t_half:
        d = df_teams.copy()
        d["H1_Diff"] = d["tore_h1_erz"] - d["tore_h1_geg"]
        d["H2_Diff"] = d["tore_h2_erz"] - d["tore_h2_geg"]
        c1, c2 = st.columns(2)
        with c1:
            ranking(d, "H1_Diff", "Tordifferenz 1. Halbzeit", "#1f77b4", fmt="+.0f")
        with c2:
            ranking(d, "H2_Diff", "Tordifferenz 2. Halbzeit", "#ff7f0e", fmt="+.0f")

        st.subheader("Pausenstand & Endergebnis")
        hz = pd.DataFrame({
            "Team": d["Team"],
            "Pause führend": d["ht_fuehrung"],
            "→ Sieg": d["ht_fuehrung_siege"],
            "→ nicht gewonnen": d["ht_fuehrung"] - d["ht_fuehrung_siege"],
            "Pause Rückstand": d["ht_rueckstand"],
            "→ Comeback-Sieg": d["ht_rueckstand_siege"],
            "→ Unentschieden": d["ht_rueckstand_unent"],
            "Comeback-Quote (%)": sdiv(d["ht_rueckstand_siege"], d["ht_rueckstand"]) * 100,
        }).sort_values(["→ Comeback-Sieg", "Pause führend", "Team"], ascending=[False, False, True])
        table(hz, height=min(600, 36 * len(hz) + 40))
        note("Comeback-Quote = Anteil der Spiele mit Pausenrückstand, die noch gewonnen wurden. "
             "„nicht gewonnen“ = Pausenführung nicht zum Sieg gebracht. Sortiert nach Comeback-Siegen.")

        st.subheader("Führungsanteil")
        f = pd.DataFrame({
            "Team": d["Team"],
            "In Führung": sdiv(d["sek_fuehrung"] / 60, d["spiele"]),
            "Gleichstand": sdiv(d["sek_gleich"] / 60, d["spiele"]),
            "Im Rückstand": sdiv(d["sek_rueckstand"] / 60, d["spiele"]),
        }).sort_values(["In Führung", "Team"], ascending=[False, True])
        if f[["In Führung", "Gleichstand", "Im Rückstand"]].sum().sum() == 0:
            st.info("Noch keine Daten für den Führungsanteil.")
        else:
            order = f["Team"].tolist()
            long = f.melt(id_vars="Team", var_name="Situation", value_name="Minuten")
            fig = px.bar(long, x="Minuten", y="Team", color="Situation", orientation="h", barmode="stack",
                         color_discrete_map={"In Führung": "#2ca02c", "Gleichstand": "#9e9e9e", "Im Rückstand": "#d62728"})
            fig.update_yaxes(categoryorder="array", categoryarray=order[::-1], title=None, automargin=True)
            fig.update_xaxes(title="Ø Minuten pro Spiel")
            fig.update_layout(title=dict(text="Ø Spielzeit in Führung / Gleichstand / Rückstand", x=0, font=dict(size=16)),
                              height=max(300, 34 * len(f) + 120), margin=dict(l=0, r=10, t=55, b=10),
                              legend=dict(title=None, orientation="h", y=-0.12))
            show(fig)

    # ---- Auszeiten ----
    with t_az:
        a = df_teams.copy()
        a["AZ_Diff"] = sdiv(a["az_tore"] - a["az_geg"], a["auszeiten"])
        a["AZ_pro_Spiel"] = sdiv(a["auszeiten"], a["spiele"])
        if a["auszeiten"].sum() == 0:
            st.info("Noch keine Auszeiten erfasst.")
        else:
            ranking(a[a["auszeiten"] >= 3], "AZ_Diff", "Ø Tordifferenz in den 5 Min. nach einer eigenen Auszeit (ab 3 Auszeiten)",
                    "#17becf", fmt="+.2f")
            table(a.sort_values(["AZ_Diff", "auszeiten", "Team"], ascending=[False, False, True])
                  [["Team", "auszeiten", "AZ_pro_Spiel", "az_tore", "az_geg", "AZ_Diff"]],
                  {"auszeiten": "Auszeiten", "AZ_pro_Spiel": "Auszeiten / Spiel", "az_tore": "Tore danach",
                   "az_geg": "Gegentore danach", "AZ_Diff": "Ø Diff pro Auszeit"},
                  height=min(600, 36 * len(a) + 40))
            note("Gezählt werden Tore und Gegentore in den 5 Minuten nach einer Auszeit des jeweiligen Teams.")


# ==========================================
# BEREICH 6: UMFELD
# ==========================================
def tab_environment():
    t_fans, t_ref = st.tabs(["📢 Zuschauer", "👨‍⚖️ Schiedsrichter & Zeitnehmer"])

    with t_fans:
        ranking(df_teams[df_teams["heimspiele"] > 0], "Ø Zuschauer", "Ø Zuschauer pro Heimspiel", "#9c27b0", fmt=".0f")

        st.subheader("Zuschauer & Heimergebnis")
        g = df_games[df_games["Zuschauer"] > 0].copy() if not df_games.empty else df_games
        if len(g) < 6:
            st.info("Zu wenige Spiele mit Zuschauerangaben (mindestens 6 nötig).")
        else:
            g["Heimsieg"] = (g["Differenz"] > 0).astype(float) * 100
            rang = g["Zuschauer"].rank(method="first")
            g["Gruppe"] = pd.qcut(rang, 3, labels=["Wenig Zuschauer", "Mittel", "Viele Zuschauer"])
            grp = (g.groupby("Gruppe", observed=True)
                   .agg(Spiele=("Zuschauer", "size"), Von=("Zuschauer", "min"), Bis=("Zuschauer", "max"),
                        Heimsiegquote=("Heimsieg", "mean"), Heim_Tordiff=("Differenz", "mean"))
                   .reset_index())
            c1, c2 = st.columns([2, 3])
            with c1:
                corr = g["Zuschauer"].corr(g["Differenz"])
                st.metric("Korrelation Zuschauer ↔ Heim-Tordifferenz", f"{corr:+.2f}" if pd.notna(corr) else "–")
                table(grp.rename(columns={"Von": "Zuschauer von", "Bis": "bis", "Heimsiegquote": "Heimsiege (%)",
                                          "Heim_Tordiff": "Ø Heim-Tordiff"}))
            with c2:
                fig = px.bar(grp, x="Gruppe", y="Heimsiegquote", text_auto=".0f", color_discrete_sequence=["#9c27b0"])
                fig.update_xaxes(title=None)
                fig.update_yaxes(title="Heimsiege (%)", range=[0, 100])
                fig.update_layout(title=dict(text="Heimsiegquote nach Zuschauergruppe", x=0, font=dict(size=16)),
                                  height=340, margin=dict(l=0, r=10, t=55, b=10))
                show(fig)
            note("Die Spiele werden nach Zuschauerzahl in drei gleich große Gruppen geteilt. Korrelation ≠ Ursache: "
                 "starke Teams ziehen oft auch mehr Zuschauer an.")

    with t_ref:
        st.subheader("Schiedsrichter")
        rs = data_info.get("ref_stats", {})
        if rs:
            rows = []
            for name, r in rs.items():
                n = max(1, r.get("spiele", 0))
                rows.append({
                    "Name": name, "Spiele": r.get("spiele", 0),
                    "Ø Zeitstrafen": (r.get("strafen_heim", 0) + r.get("strafen_gast", 0)) / n,
                    "Ø Strafen Heim": r.get("strafen_heim", 0) / n,
                    "Ø Strafen Gast": r.get("strafen_gast", 0) / n,
                    "Ø Tore": r.get("tore", 0) / n,
                    "Heimsiege (%)": r.get("heimsiege", 0) / n * 100,
                    "Ø Heim-Tordiff": r.get("heim_diff", 0) / n,
                })
            rdf = pd.DataFrame(rows).sort_values(["Spiele", "Ø Zeitstrafen", "Name"], ascending=[False, False, True])
            table(rdf, height=min(600, 36 * len(rdf) + 40))
            note("Strafen Heim/Gast = Zeitstrafen gegen das Heim- bzw. Gastteam pro Spiel. "
                 "Bei wenigen Spielen sind die Werte nur Tendenzen.")
        else:
            st.info("Keine Schiedsrichterdaten erfasst.")

        st.subheader("Zeitnehmer / Sekretariat")
        if tk_data:
            table(pd.DataFrame(list(tk_data.items()), columns=["Name", "Einsätze"])
                  .sort_values(["Einsätze", "Name"], ascending=[False, True]), height=420)
        else:
            st.info("Keine Daten vorhanden.")


# ==========================================
# BEREICH 3: SPIELERINNEN
# ==========================================
TOP_KATEGORIEN = {
    "Meiste Tore (Gesamt)": "tore",
    "Meiste Feldtore": "Feldtore",
    "Meiste 7m-Tore": "7m_tore",
    "Meiste 2-Minuten-Strafen": "2min",
    "Meiste Verwarnungen": "verwarnungen",
    "Meiste Disqualifikationen": "disq",
}


def tab_players():
    t_top, t_7m, t_prof, t_vgl, t_rec, t_week, t_clutch = st.tabs(
        ["⭐ Top-Listen", "🎯 7-Meter", "👤 Profil", "🆚 Vergleich", "🏅 Rekorde", "📅 Team der Woche",
         "🧊 Clutch & Icebreaker"])
    alle = sorted(df_players["Name_Raw"].tolist())

    with t_top:
        kat = st.radio("Kategorie:", list(TOP_KATEGORIEN), horizontal=True, key="top_kat")
        col = TOP_KATEGORIEN[kat]
        top = (df_players[df_players[col] > 0]
               .sort_values([col, "spiele", "Name"], ascending=[False, True, True])   # Gleichstand: weniger Spiele vorne
               .head(25))
        if top.empty:
            st.info("Noch keine Daten.")
        else:
            c1, c2 = st.columns([3, 2])
            with c1:
                ranking(top, col, f"Top 10 – {kat}", fmt=".0f", label="Name_Raw", top=10, color_by="team")
            with c2:
                st.subheader("Top 25")
                table(top[["Name", "team", col]], {"team": "Team", col: kat.replace("Meiste ", "")}, height=600)

    with t_7m:
        min_v = st.slider("Mindestanzahl geworfener 7-Meter", 1, 20, 6, key="min_7m")
        sm = df_players[df_players["7m_versuche"] >= min_v].copy()
        if sm.empty:
            st.info("Keine Spielerin mit so vielen 7-Metern.")
        else:
            sm["Quote"] = sm["7m_tore"] / sm["7m_versuche"] * 100
            sm["Fehlwürfe"] = sm["7m_versuche"] - sm["7m_tore"]
            sm = sm.sort_values(["Quote", "7m_versuche", "Name"], ascending=[False, False, True])
            c1, c2 = st.columns([3, 2])
            with c1:
                ranking(sm, "Quote", f"Sicherste 7m-Schützinnen (ab {min_v} Würfen)", "#ff9900",
                        fmt=".0f", label="Name_Raw", top=10, color_by="team")
            with c2:
                table(sm[["Name", "team", "7m_versuche", "7m_tore", "Fehlwürfe", "Quote"]],
                      {"team": "Team", "7m_versuche": "Würfe", "7m_tore": "Tore", "Quote": "Quote (%)"}, height=520)
            note("Sortiert nach Quote, bei Gleichstand nach Anzahl der Würfe.")

    with t_prof:
        wahl = st.selectbox("Spielerin wählen:", alle, key="prof_wahl")
        sp = df_players[df_players["Name_Raw"] == wahl].iloc[0]
        st.markdown(f"### {sp['Name']} · {sp['team']}")

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Einsätze", int(sp["spiele"]))
        k2.metric("Tore", int(sp["tore"]))
        k3.metric("Tore pro Spiel", f"{sp['tore'] / max(1, sp['spiele']):.1f}")
        k4.metric("Bestwert in 1 Spiel", f"{int(sp['max_tore_ein_spiel'])} Tore")
        st.write("")

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Torgefahr")
            note("Früh = erste 10 Min. jeder Halbzeit · Spät = letzte 10 Min. jeder Halbzeit")
            m1, m2 = st.columns(2)
            m1.metric("Tore früh", int(sp["tore_frueh"]))
            m2.metric("Tore spät", int(sp["tore_spaet"]))
            labels = ["Tore H1", "Tore H2", "Tore früh", "Tore spät", "Clutch-Tore"]
            vals = [sp["tore_h1"], sp["tore_h2"], sp["tore_frueh"], sp["tore_spaet"], sp["clutch_tore"]]
            fig = go.Figure(go.Scatterpolar(r=vals + vals[:1], theta=labels + labels[:1],
                                            fill="toself", line_color="#1f77b4"))
            fig.update_layout(showlegend=False, height=340, margin=dict(t=30, b=30, l=40, r=40),
                              polar=dict(radialaxis=dict(visible=True, rangemode="tozero")))
            show(fig)
        with c2:
            st.subheader("Disziplin")
            note("Zeitstrafen bei hoher Frische (früh) vs. bei Ermüdung (spät)")
            m1, m2 = st.columns(2)
            m1.metric("Strafen früh", int(sp["strafen_frueh"]))
            m2.metric("Strafen spät", int(sp["strafen_spaet"]))
            if sp["tore"] > 0:
                pie = px.pie(pd.DataFrame({"Kategorie": ["Feldtore", "7-Meter-Tore"],
                                           "Anzahl": [sp["Feldtore"], sp["7m_tore"]]}),
                             values="Anzahl", names="Kategorie", hole=0.5,
                             color_discrete_sequence=["#2ca02c", "#ff7f0e"])
                pie.update_layout(height=340, margin=dict(t=30, b=10, l=10, r=10),
                                  legend=dict(orientation="h", y=-0.05))
                show(pie)

    with t_vgl:
        c1, c2 = st.columns(2)
        wahl_a = c1.selectbox("Spielerin A", alle, index=0, key="vgl_a")
        wahl_b = c2.selectbox("Spielerin B", alle, index=1 if len(alle) > 1 else 0, key="vgl_b")
        if wahl_a == wahl_b:
            st.info("Bitte zwei verschiedene Spielerinnen wählen.")
        else:
            a = df_players[df_players["Name_Raw"] == wahl_a].iloc[0]
            b = df_players[df_players["Name_Raw"] == wahl_b].iloc[0]
            kpis = {"tore": "Tore", "Feldtore": "Feldtore", "7m_tore": "7m-Tore",
                    "2min": "2-Minuten", "tore_frueh": "Tore früh", "tore_spaet": "Tore spät"}
            rows = []
            for key, name in kpis.items():
                rows.append({"Metrik": name, "Spielerin": wahl_a, "Wert": a[key]})
                rows.append({"Metrik": name, "Spielerin": wahl_b, "Wert": b[key]})
            compare_chart(rows, "Spielerin", ["#9467bd", "#8c564b"], fmt=".0f")

    with t_rec:
        ranking(df_players[df_players["max_tore_ein_spiel"] > 0], "max_tore_ein_spiel",
                "🏆 Die meisten Tore in einem Spiel", fmt=".0f", label="Name_Raw", top=15, color_by="team")

    with t_week:
        tage = sorted(m for m in matchday_data.keys() if m != 0)
        if not tage:
            st.info("Noch keine Spieltagsdaten.")
        else:
            tag = st.selectbox("Spieltag:", tage, index=len(tage) - 1, key="woche_tag")
            df = pd.DataFrame(matchday_data[tag])
            if not df.empty:
                df = df.sort_values(["Tore", "Feldtore", "Name"], ascending=[False, False, True]).head(7).copy()
                df["Label"] = df["Name"] + " (" + df["Team"] + ")"
                c1, c2 = st.columns([2, 3])
                with c1:
                    table(df[["Name", "Team", "Tore", "7m", "Feldtore"]])
                with c2:
                    ranking(df, "Tore", f"Top-Performer Spieltag {tag}", fmt=".0f", label="Label", color_by="Team")

    with t_clutch:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Clutch-Tore")
            note("Tore ab Minute 55 bei maximal 2 Toren Differenz")
            d = df_players[df_players["clutch_tore"] > 0].sort_values(["clutch_tore", "Name"], ascending=[False, True])
            if d.empty:
                st.info("Noch keine Clutch-Tore.")
            else:
                table(d.head(10)[["Name", "team", "clutch_tore"]], {"team": "Team", "clutch_tore": "Clutch-Tore"})
        with c2:
            st.subheader("Icebreaker")
            note("Erstes Tor des Spiels")
            d = df_players[df_players["icebreaker"] > 0].sort_values(["icebreaker", "Name"], ascending=[False, True])
            if d.empty:
                st.info("Noch keine Icebreaker.")
            else:
                table(d.head(10)[["Name", "team", "icebreaker"]], {"team": "Team", "icebreaker": "Icebreaker"})


# ==========================================
# BEREICH 5: ÜBER-/UNTERZAHL & STRAFEN
# ==========================================
def tab_powerplay():
    t_sum, t_ueber, t_unter, t_pen = st.tabs(
        ["📋 Gesamtbilanz", "⬆️ Überzahl", "⬇️ Unterzahl", "⏱️ Strafen nach Minute"])

    with t_sum:
        d = df_teams.assign(Gesamtsaldo=df_teams["Ueberzahl_Saldo"] + df_teams["Unterzahl_Saldo"])
        d = d.sort_values(["Gesamtsaldo", "Ueberzahl_Saldo", "Team"], ascending=[False, False, True])
        table(d[["Team", "ueberzahl_tore_erzielt", "ueberzahl_tore_kassiert", "Ueberzahl_Saldo",
                 "unterzahl_tore_erzielt", "unterzahl_tore_kassiert", "Unterzahl_Saldo", "Gesamtsaldo"]],
              {"ueberzahl_tore_erzielt": "Tore in Überzahl", "ueberzahl_tore_kassiert": "Gegentore in Überzahl",
               "Ueberzahl_Saldo": "Saldo Überzahl", "unterzahl_tore_erzielt": "Tore in Unterzahl",
               "unterzahl_tore_kassiert": "Gegentore in Unterzahl", "Unterzahl_Saldo": "Saldo Unterzahl",
               "Gesamtsaldo": "Gesamtsaldo"},
              height=min(600, 36 * len(d) + 40))
        note("Saldo = erzielte Tore − Gegentore in der jeweiligen Situation. Sortiert nach Gesamtsaldo.")

    with t_ueber:
        c1, c2 = st.columns(2)
        with c1:
            ranking(df_teams, "ueberzahl_tore_erzielt", "Tore in Überzahl", "#2ca02c", fmt=".0f",
                    hide_if_all_zero=True)
        with c2:
            ranking(df_teams, "ueberzahl_tore_kassiert", "Gegentore in eigener Überzahl", "#ff9800", fmt=".0f",
                    lower_is_better=True, hide_if_all_zero=True)
        ranking(df_teams, "Ø_Ueberzahl_PlusMinus", "Ø Tordifferenz in Überzahl (pro gegnerischer Zeitstrafe)",
                "#17becf", fmt="+.2f", hide_if_all_zero=True)

    with t_unter:
        c1, c2 = st.columns(2)
        with c1:
            ranking(df_teams, "unterzahl_tore_erzielt", "Tore in Unterzahl", "#17becf", fmt=".0f",
                    hide_if_all_zero=True)
        with c2:
            ranking(df_teams, "unterzahl_tore_kassiert", "Gegentore in Unterzahl", "#e91e63", fmt=".0f",
                    lower_is_better=True, hide_if_all_zero=True)

    with t_pen:
        if penalty_data and sum(penalty_data.values()) > 0:
            letzte = max(60, max(penalty_data) + 1)
            df_pen = pd.DataFrame({"Minute": range(letzte)})
            df_pen["Anzahl"] = df_pen["Minute"].map(penalty_data).fillna(0).astype(int)
            fig = px.bar(df_pen, x="Minute", y="Anzahl", color_discrete_sequence=["#d62728"])
            fig.add_vline(x=29.5, line_dash="dot", line_color="gray", annotation_text="Halbzeit")
            fig.update_layout(title=dict(text="Ligaweite Zeitstrafen nach Spielminute", x=0, font=dict(size=16)),
                              height=380, margin=dict(l=0, r=10, t=55, b=10), bargap=0.15)
            fig.update_xaxes(dtick=5)
            show(fig)
        else:
            st.info("Noch keine Zeitstrafen erfasst.")


# --- 5. SEITENLEISTE & HAUPT-TABS ---
with st.sidebar:
    st.title("📊 Analyse-Zentrale")
    st.caption("3. Liga Frauen Nord · Saison 2026/27")
    st.metric("Ausgewertete Spiele", data_info.get("spiele", 0))
    if data_info.get("letztes_datum"):
        st.caption(f"Letztes Spiel: {data_info['letztes_datum'].strftime('%d.%m.%Y')}")
    if st.button("🔄 Daten neu laden"):
        st.cache_data.clear()
        st.rerun()

st.title("🤾 Handball Liga-Analyse")

main_tabs = st.tabs(["🏆 Liga", "🛡️ Teams", "⭐ Spielerinnen", "⏱️ Spielverlauf",
                     "⚖️ Über-/Unterzahl", "🏟️ Umfeld"])
for tab, render in zip(main_tabs, [tab_liga, tab_teams, tab_players, tab_flow, tab_powerplay, tab_environment]):
    with tab:
        render()