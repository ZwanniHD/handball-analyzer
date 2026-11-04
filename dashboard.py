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
        "ueberzahl_bilanz": []
    }

def default_player():
    return {
        "team": "", "tore": 0, "7m_tore": 0, "2min": 0,
        "spiele": 0, "max_tore_ein_spiel": 0,
        "tore_h1": 0, "tore_h2": 0, "clutch_tore": 0, "icebreaker": 0,
        "tore_frueh": 0, "tore_spaet": 0,    # NEU: Frühe/Späte Tore
        "strafen_frueh": 0, "strafen_spaet": 0 # NEU: Frühe/Späte Strafen
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
        return {}, {}, {}, {}, {}, {}

    for file in DATA_DIR.glob("match_*.json"):
        with open(file, "r", encoding="utf-8") as f:
            match = json.load(f)
            
        meta = match.get("metadata", {})
        date_str = meta.get("date")
        matchday = meta.get("matchday", 0)
        
        if date_str:
            try:
                match_date = datetime.strptime(date_str, "%d.%m.%Y")
                if match_date > CURRENT_DATE: continue
            except ValueError: pass 

        for ref in match.get("referees", []) or meta.get("referees", []):
            name = ref.get("name") if isinstance(ref, dict) else ref
            if name: referees_count[name.strip()] += 1
                
        tk = meta.get("timekeeper", "") or meta.get("sekretaer", "")
        if tk and isinstance(tk, str): timekeepers_count[tk.strip()] += 1

        teams = match.get("teams", {})
        if "home" not in teams or "away" not in teams: continue
            
        h_name = teams["home"].get("name", "Unbekannt")
        a_name = teams["away"].get("name", "Unbekannt")
        
        score = meta.get("final_score", "")
        h_goals, a_goals = 0, 0
        if ":" in score:
            try: h_goals, a_goals = map(int, score.split(":"))
            except: pass

        spectators = meta.get("spectators", 0)
        team_stats[h_name]["spiele"] += 1; team_stats[h_name]["heimspiele"] += 1
        team_stats[h_name]["tore_erzielt"] += h_goals; team_stats[h_name]["tore_kassiert"] += a_goals
        team_stats[h_name]["zuschauer_gesamt"] += spectators
        
        team_stats[a_name]["spiele"] += 1
        team_stats[a_name]["tore_erzielt"] += a_goals; team_stats[a_name]["tore_kassiert"] += h_goals

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
                    except: pass
                
                if p_goals > 0:
                    matchday_players[matchday].append({
                        "Name": p_name, "Team": t_name, 
                        "Tore": p_goals, "7m": p_7m, "Feldtore": p_goals - p_7m
                    })

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

            # Phasen-Klassifizierung für Spieler-Individuelle Leistung (Früh vs. Spät)
            # Früh = Erste 10 Min pro Halbzeit (0-10 / 30-40)
            # Spät = Letzte 10 Min pro Halbzeit (20-30 / 50-60)
            spieler_phase = None
            if sec <= 600 or (1800 <= sec <= 2400):
                spieler_phase = "frueh"
            elif (1200 <= sec <= 1800) or (3000 <= sec <= 3600):
                spieler_phase = "spaet"

            if "2-minuten" in ev_type:
                penalty_minutes[m] += 1
                current_diff = diff if ev_team == "heim" else -diff
                active_penalties.append({"team": team_name, "end_time": sec + 120, "start_diff": current_diff})
                
                # Spieler individuelle Strafen-Phase
                if p_id:
                    if spieler_phase == "frueh": player_stats[p_id]["strafen_frueh"] += 1
                    elif spieler_phase == "spaet": player_stats[p_id]["strafen_spaet"] += 1

            for pen in active_penalties[:]:
                if sec >= pen["end_time"]:
                    current_diff = prev_diff if pen["team"] == h_name else -prev_diff   # Stand bei Ablauf der Strafe
                    bilanz = current_diff - pen["start_diff"]
                    team_stats[a_name if pen["team"] == h_name else h_name]["ueberzahl_bilanz"].append(-bilanz)
                    active_penalties.remove(pen)

            if "tor" in ev_type:
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

                if sec >= 3300 and abs(diff) <= 2 and p_id:
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

        if h_goals >= a_goals:
            if abs(max_deficit_home) > team_stats[h_name]["max_comeback"]: team_stats[h_name]["max_comeback"] = abs(max_deficit_home)
        if a_goals >= h_goals:
            if max_deficit_away > team_stats[a_name]["max_comeback"]: team_stats[a_name]["max_comeback"] = max_deficit_away

    return dict(team_stats), dict(player_stats), dict(referees_count), dict(timekeepers_count), dict(matchday_players), dict(penalty_minutes)

team_data, player_data, ref_data, tk_data, matchday_data, penalty_data = load_and_aggregate_data()

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

df_players = pd.DataFrame.from_dict(player_data, orient="index").reset_index()
df_players.rename(columns={"index": "Name_Raw"}, inplace=True)   # Name_Raw = "Name (Team)"
df_players["Name"] = df_players["Name_Raw"].apply(lambda x: x.split(" (")[0])
df_players["Feldtore"] = df_players["tore"] - df_players["7m_tore"]


# --- 4. HELFER (einheitliche Darstellung & Sortierung) ---
def show(fig):
    """Zentrale Stelle für alle Plotly-Charts (bei Streamlit-Updates nur hier anpassen)."""
    st.plotly_chart(fig, width="stretch")


def ranking(df, col, title, color="#3366cc", fmt=".1f", label="Team",
            lower_is_better=False, top=None, color_by=None):
    """Horizontales Ranking: bester Wert immer OBEN.
    Standard: größter Wert oben (absteigend). Bei lower_is_better: kleinster Wert oben."""
    if df is None or df.empty:
        st.info(f"Noch keine Daten für: {title}")
        return
    cols = [label, col] + ([color_by] if color_by else [])
    d = df[cols].dropna(subset=[col]).sort_values(col, ascending=lower_is_better, kind="stable")
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


def table(df, rename=None, height=None):
    """Tabelle mit Rang statt anonymem Index, lesbaren Spaltennamen und gerundeten Zahlen."""
    d = df.rename(columns=rename or {}).round(1).reset_index(drop=True)
    d.index = d.index + 1
    d.index.name = "Rang"
    kwargs = {"height": height} if height else {}   # height=None ist ungültig -> dann weglassen
    st.dataframe(d, width="stretch", **kwargs)


# ==========================================
# ANSICHTEN
# ==========================================
def view_liga():
    st.title("🏆 Liga-Vergleich")
    spiele = int(df_teams["spiele"].sum() // 2)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Teams", len(df_teams))
    k2.metric("Gespielte Spiele", spiele)
    k3.metric("Ø Tore pro Spiel (beide Teams)", f"{df_teams['tore_erzielt'].sum() / max(1, spiele):.1f}")
    k4.metric("Ø Zuschauer (Heimspiele)", f"{df_teams['zuschauer_gesamt'].sum() / max(1, df_teams['heimspiele'].sum()):.0f}")
    st.divider()

    c1, c2 = st.columns(2)
    with c1:
        ranking(df_teams, "Tore/Spiel", "🔥 Beste Offensive – Tore pro Spiel", "#3366cc")
        ranking(df_teams, "2Min/Spiel", "⚠️ Meiste Zeitstrafen pro Spiel", "#dc3912")
    with c2:
        ranking(df_teams, "Gegentore/Spiel", "🧱 Beste Defensive – Gegentore pro Spiel", "#109618", lower_is_better=True)
        ranking(df_teams[df_teams["siebenmeter_versuche"] > 5], "7m-Quote (%)",
                "🎯 7-Meter-Quote (ab 6 Versuchen)", "#ff9900", fmt=".0f")


def view_team_detail():
    st.title("🔍 Einzel-Team-Analyse")
    team = st.selectbox("Team wählen:", sorted(df_teams["Team"].tolist()))
    row = df_teams[df_teams["Team"] == team].iloc[0]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Absolvierte Spiele", int(row["spiele"]))
    k2.metric("Ø Tore erzielt", f"{row['Tore/Spiel']:.1f}")
    k3.metric("Ø Gegentore", f"{row['Gegentore/Spiel']:.1f}")
    k4.metric("7m-Trefferquote", f"{row['7m-Quote (%)']:.1f} %")
    st.divider()

    tp = df_players[df_players["team"] == team]
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Top-Torschützinnen")
        table(tp.sort_values(["tore", "spiele"], ascending=[False, True]).head(15)[["Name", "tore", "7m_tore"]],
              {"tore": "Tore", "7m_tore": "davon 7m"})
    with c2:
        st.subheader("Zeitstrafen")
        strafen = tp[tp["2min"] > 0].sort_values("2min", ascending=False)[["Name", "2min"]]
        if strafen.empty:
            st.info("Keine Zeitstrafen.")
        else:
            table(strafen, {"2min": "2-Minuten"})


def view_team_h2h():
    st.title("⚔️ Direkter Team-Vergleich")
    teams = sorted(df_teams["Team"].tolist())
    c1, c2 = st.columns(2)
    team_a = c1.selectbox("Team A", teams, index=0)
    team_b = c2.selectbox("Team B", teams, index=1 if len(teams) > 1 else 0)
    if team_a == team_b:
        st.info("Bitte zwei verschiedene Teams wählen.")
        return
    a = df_teams[df_teams["Team"] == team_a].iloc[0]
    b = df_teams[df_teams["Team"] == team_b].iloc[0]
    rows = []
    for kpi in ["Tore/Spiel", "Gegentore/Spiel", "2Min/Spiel", "7m-Quote (%)"]:
        rows.append({"Metrik": kpi, "Team": team_a, "Wert": a[kpi]})
        rows.append({"Metrik": kpi, "Team": team_b, "Wert": b[kpi]})
    compare_chart(rows, "Team", ["#3366cc", "#ff9900"])


TOP_KATEGORIEN = {
    "Meiste Tore (Gesamt)": "tore",
    "Meiste Feldtore": "Feldtore",
    "Meiste 7m-Tore": "7m_tore",
    "Meiste 2-Minuten-Strafen": "2min",
}

def view_top_lists():
    st.title("⭐ Ligaweite Top-Listen")
    kat = st.radio("Kategorie:", list(TOP_KATEGORIEN), horizontal=True)
    col = TOP_KATEGORIEN[kat]
    top = (df_players[df_players[col] > 0]
           .sort_values([col, "spiele"], ascending=[False, True])   # bei Gleichstand: weniger Spiele vorne
           .head(25))
    c1, c2 = st.columns([3, 2])
    with c1:
        ranking(top, col, f"Top 10 – {kat}", fmt=".0f", label="Name_Raw", top=10, color_by="team")
    with c2:
        st.subheader("Top 25")
        table(top[["Name", "team", col]], {"team": "Team", col: kat.replace("Meiste ", "")}, height=600)


def view_players():
    st.title("👤 Individuelle Spieler-Analyse")
    tab1, tab2, tab3 = st.tabs(["Profil & KPIs", "Spieler-Vergleich", "Saison-Rekorde"])
    alle = sorted(df_players["Name_Raw"].tolist())

    with tab1:
        wahl = st.selectbox("Spielerin wählen:", alle)
        sp = df_players[df_players["Name_Raw"] == wahl].iloc[0]
        st.markdown(f"### {sp['Name']} · {sp['team']}")

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Einsätze", int(sp["spiele"]))
        k2.metric("Tore", int(sp["tore"]))
        k3.metric("Tore pro Spiel", f"{sp['tore'] / max(1, sp['spiele']):.1f}")
        k4.metric("Bestwert in 1 Spiel", f"{int(sp['max_tore_ein_spiel'])} Tore")
        st.divider()

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Torgefahr")
            st.caption("Früh = erste 10 Min. jeder Halbzeit · Spät = letzte 10 Min. jeder Halbzeit")
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
            st.caption("Zeitstrafen bei hoher Frische (früh) vs. bei Ermüdung (spät)")
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

    with tab2:
        c1, c2 = st.columns(2)
        wahl_a = c1.selectbox("Spielerin A", alle, index=0)
        wahl_b = c2.selectbox("Spielerin B", alle, index=1 if len(alle) > 1 else 0)
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

    with tab3:
        st.subheader("🏆 Die meisten Tore in einem Spiel")
        ranking(df_players[df_players["max_tore_ein_spiel"] > 0], "max_tore_ein_spiel", "",
                fmt=".0f", label="Name_Raw", top=15, color_by="team")


def view_matchday():
    st.title("⭐ Team der Woche")
    tage = sorted(m for m in matchday_data.keys() if m != 0)
    if not tage:
        st.info("Noch keine Spieltagsdaten.")
        return
    tag = st.selectbox("Spieltag:", tage, index=len(tage) - 1)
    df = pd.DataFrame(matchday_data[tag])
    if df.empty:
        return
    df = df.sort_values(["Tore", "Feldtore"], ascending=[False, False]).head(7).copy()
    df["Label"] = df["Name"] + " (" + df["Team"] + ")"
    c1, c2 = st.columns([2, 3])
    with c1:
        table(df[["Name", "Team", "Tore", "7m", "Feldtore"]])
    with c2:
        ranking(df, "Tore", f"Top-Performer Spieltag {tag}", fmt=".0f", label="Label", color_by="Team")


def view_phases():
    st.title("⏱️ Spielphasen & Momentum")
    tab1, tab2, tab3 = st.tabs(["5-Minuten-Phasen", "Torserien", "Crunch-Time & Comebacks"])

    with tab1:
        phasen = {
            "Start 1. Halbzeit (0–5 Min)": ("start_h1_tore", "start_h1_geg"),
            "Ende 1. Halbzeit (25–30 Min)": ("ende_h1_tore", "ende_h1_geg"),
            "Start 2. Halbzeit (30–35 Min)": ("start_h2_tore", "start_h2_geg"),
            "Ende 2. Halbzeit (55–60 Min)": ("ende_h2_tore", "ende_h2_geg"),
        }
        phase = st.radio("Phase:", list(phasen), horizontal=True)
        c_tore, c_geg = phasen[phase]
        d = df_teams.assign(Phasen_Diff=df_teams[c_tore] - df_teams[c_geg])
        c1, c2 = st.columns(2)
        with c1:
            ranking(d, c_tore, f"Geworfene Tore – {phase}", "#1f77b4", fmt=".0f")
        with c2:
            ranking(d, "Phasen_Diff", f"Tordifferenz (+/−) – {phase}", "#ff7f0e", fmt="+.0f")
    with tab2:
        ranking(df_teams, "max_lauf", "Längste Torserie (Tore am Stück)", "#2ca02c", fmt=".0f")
    with tab3:
        c1, c2 = st.columns(2)
        with c1:
            ranking(df_teams, "crunch_time_tore", "Nervenstärke – Tore in der Crunch-Time", "#d62728", fmt=".0f")
        with c2:
            ranking(df_teams, "max_comeback", "Größter aufgeholter Rückstand", "#9467bd", fmt=".0f")


def view_deep_dive():
    st.title("🧠 Deep-Dive Analytics")
    t1, t2, t3, t4, t5 = st.tabs(["⚡ Reaktion & Krisen", "⚖️ Überzahl", "🧊 Clutch & Icebreaker",
                                  "🏃‍♀️ Kondition (H1 vs. H2)", "⏱️ Strafen nach Minute"])
    with t1:
        c1, c2 = st.columns(2)
        with c1:
            ranking(df_teams[df_teams["Ø_Schnelle_Mitte_Sek"] > 0], "Ø_Schnelle_Mitte_Sek",
                    "Ø Reaktionszeit nach Gegentor (Sek.)", "#e377c2", lower_is_better=True)
        with c2:
            ranking(df_teams, "Torkrise_Max_Min", "Längste Torflaute (Minuten)", "#7f7f7f", lower_is_better=True)
    with t2:
        ranking(df_teams, "Ø_Ueberzahl_PlusMinus", "Ø Tordifferenz in Überzahl (pro Zeitstrafe)", "#17becf", fmt="+.2f")
    with t3:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Clutch-Tore")
            st.caption("Tore ab Minute 55 bei maximal 2 Toren Differenz")
            table(df_players[df_players["clutch_tore"] > 0].sort_values("clutch_tore", ascending=False)
                  .head(10)[["Name", "team", "clutch_tore"]], {"team": "Team", "clutch_tore": "Clutch-Tore"})
        with c2:
            st.subheader("Icebreaker")
            st.caption("Erstes Tor des Spiels")
            table(df_players[df_players["icebreaker"] > 0].sort_values("icebreaker", ascending=False)
                  .head(10)[["Name", "team", "icebreaker"]], {"team": "Team", "icebreaker": "Icebreaker"})
    with t4:
        st.caption("Positiver Wert = Spielerin trifft in der 2. Halbzeit häufiger. Nur Spielerinnen mit > 5 Toren in einer Halbzeit.")
        cond = df_players[(df_players["tore_h1"] > 5) | (df_players["tore_h2"] > 5)].copy()
        cond["H2_Dominanz"] = cond["tore_h2"] - cond["tore_h1"]
        table(cond.sort_values("H2_Dominanz", ascending=False)[["Name", "team", "tore_h1", "tore_h2", "H2_Dominanz"]],
              {"team": "Team", "tore_h1": "Tore H1", "tore_h2": "Tore H2", "H2_Dominanz": "H2-Dominanz"})
    with t5:
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


def view_crowd_and_powerplay():
    st.title("🏟️ Zuschauer & Über-/Unterzahl")
    tab1, tab2 = st.tabs(["Zuschauer", "Über-/Unterzahl"])
    with tab1:
        ranking(df_teams[df_teams["heimspiele"] > 0], "Ø Zuschauer", "Ø Zuschauer pro Heimspiel", "#9c27b0", fmt=".0f")
    with tab2:
        c1, c2 = st.columns(2)
        with c1:
            ranking(df_teams, "ueberzahl_tore_erzielt", "Tore in Überzahl", "#2ca02c", fmt=".0f")
            ranking(df_teams, "unterzahl_tore_erzielt", "Tore in Unterzahl", "#17becf", fmt=".0f")
        with c2:
            ranking(df_teams, "unterzahl_tore_kassiert", "Gegentore in Unterzahl", "#e91e63", fmt=".0f")
            ranking(df_teams, "ueberzahl_tore_kassiert", "Gegentore in gegnerischer Unterzahl", "#ff9800", fmt=".0f")


def view_officials():
    st.title("👨‍⚖️ Schiedsrichter & Zeitnehmer")
    c1, c2 = st.columns(2)
    for col, title, data in [(c1, "Schiedsrichter", ref_data), (c2, "Zeitnehmer / Sekretariat", tk_data)]:
        with col:
            st.subheader(title)
            if data:
                table(pd.DataFrame(list(data.items()), columns=["Name", "Einsätze"])
                      .sort_values("Einsätze", ascending=False))
            else:
                st.info("Keine Daten vorhanden.")


# --- 5. NAVIGATION ---
VIEWS = {
    "Liga-Vergleich (Teams)": view_liga,
    "Detail-Analyse (Pro Team)": view_team_detail,
    "Team-Vergleich (H2H)": view_team_h2h,
    "Top-Listen (Spielerinnen)": view_top_lists,
    "👤 Spieler-Profile & Vergleich": view_players,
    "⭐ Team der Woche": view_matchday,
    "⏱️ Spielphasen & Momentum": view_phases,
    "🧠 Deep-Dive Analytics": view_deep_dive,
    "🏟️ Zuschauer & Unterzahl": view_crowd_and_powerplay,
    "👨‍⚖️ Schiedsrichter & Offizielle": view_officials,
}

st.sidebar.title("📊 Analyse-Zentrale")
ansicht = st.sidebar.radio("Bereich wählen:", list(VIEWS))
VIEWS[ansicht]()