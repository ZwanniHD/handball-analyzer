import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import plotly.express as px

# --- 1. KONFIGURATION ---
st.set_page_config(page_title="Handball Liga-Analyse", layout="wide", page_icon="🤾")

CURRENT_DATE = datetime(2026, 10, 20)
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
        "schnelle_mitte_sekunden": [], "torkrisen_max_sekunden": 0
    }

def default_player():
    return {
        "team": "", "tore": 0, "7m_tore": 0, "2min": 0,
        "tore_h1": 0, "tore_h2": 0, "clutch_tore": 0, "icebreaker": 0
    }

@st.cache_data
def load_and_aggregate_data():
    team_stats = defaultdict(default_team)
    player_stats = defaultdict(default_player)
    referees_count = defaultdict(int)
    timekeepers_count = defaultdict(int)
    matchday_players = defaultdict(list)
    
    # Strafenermüdung initialisieren
    penalty_minutes = {i: 0 for i in range(61)} 

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
                if match_date > CURRENT_DATE:
                    continue
            except ValueError:
                pass 

        for ref in match.get("referees", []) or meta.get("referees", []):
            name = ref.get("name") if isinstance(ref, dict) else ref
            if name: referees_count[name.strip()] += 1
                
        for off in match.get("match_officials", []):
            role = off.get("role", "").lower()
            name = off.get("name")
            if name and ("zeitnehmer" in role or "sekretär" in role or "zeit" in role):
                timekeepers_count[name.strip()] += 1
                
        tk = meta.get("timekeeper", "") or meta.get("sekretaer", "")
        if tk and isinstance(tk, str):
            timekeepers_count[tk.strip()] += 1

        teams = match.get("teams", {})
        if "home" not in teams or "away" not in teams:
            continue
            
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

        for side, t_name in [("home", h_name), ("away", a_name)]:
            for p in teams[side].get("players", []):
                p_name = p.get("name")
                if not p_name: continue
                
                p_id = f"{p_name} ({t_name})"
                player_stats[p_id]["team"] = t_name
                p_goals = p.get("goals", 0)
                player_stats[p_id]["tore"] += p_goals
                player_stats[p_id]["2min"] += len(p.get("two_minutes", []))
                team_stats[t_name]["strafen_2min"] += len(p.get("two_minutes", []))
                
                sm_str = p.get("seven_m")
                p_7m_tore = 0
                if sm_str and "/" in sm_str:
                    try:
                        treffer, versuche = map(int, sm_str.split("/"))
                        p_7m_tore = treffer
                        player_stats[p_id]["7m_tore"] += treffer
                        team_stats[t_name]["siebenmeter_tore"] += treffer
                        team_stats[t_name]["siebenmeter_versuche"] += versuche
                    except: pass
                
                if p_goals > 0:
                    matchday_players[matchday].append({
                        "Name": p_name, "Team": t_name, 
                        "Tore": p_goals, "7m": p_7m_tore, "Feldtore": p_goals - p_7m_tore
                    })

        timeline = match.get("timeline", [])
        
        current_run_team = None
        current_run_count = 0
        h_score_curr, a_score_curr = 0, 0
        max_deficit_home, max_deficit_away = 0, 0
        last_goal_time_h, last_goal_time_a = 0, 0
        last_scoring_team = None
        last_scoring_time = 0
        first_goal_recorded = False
        
        active_penalties_h = []
        active_penalties_a = []

        for event in timeline:
            ev_type = event.get("event", "").lower()
            ev_team = event.get("team", "").lower()
            p_name = event.get("person_name") or event.get("player", "")
            
            t_str = event.get("time", "00:00").replace("Uhr", "").strip()
            try:
                m, s = map(int, t_str.split(":"))
                sec = m * 60 + s
            except: 
                sec = 0
                m = 0

            score_str = event.get("score", "0:0")
            if ":" in score_str:
                try: h_score_curr, a_score_curr = map(int, score_str.split(":"))
                except: pass
            
            diff = h_score_curr - a_score_curr
            if diff < max_deficit_home: max_deficit_home = diff
            if diff > max_deficit_away: max_deficit_away = diff

            team_name = h_name if ev_team in ["heim", "home"] else a_name
            opp_name = a_name if team_name == h_name else h_name
            p_id = f"{p_name} ({team_name})" if p_name else None

            active_penalties_h = [end_time for end_time in active_penalties_h if end_time > sec]
            active_penalties_a = [end_time for end_time in active_penalties_a if end_time > sec]

            # KORREKTUR: Sucht nun zusätzlich nach dem ausgeschriebenen String "zwei minuten"
            if "zwei minuten" in ev_type or ("2" in ev_type and "min" in ev_type):
                if m <= 60:
                    penalty_minutes[m] += 1
                if ev_team in ["heim", "home"]:
                    active_penalties_h.append(sec + 120)
                else:
                    active_penalties_a.append(sec + 120)

            if "tor" in ev_type:
                scoring_team_name = h_name if ev_team in ["heim", "home"] else a_name
                conceding_team_name = a_name if ev_team in ["heim", "home"] else h_name

                if scoring_team_name == h_name:
                    if len(active_penalties_h) < len(active_penalties_a): 
                        team_stats[h_name]["ueberzahl_tore_erzielt"] += 1
                        team_stats[a_name]["unterzahl_tore_kassiert"] += 1
                    elif len(active_penalties_h) > len(active_penalties_a): 
                        team_stats[h_name]["unterzahl_tore_erzielt"] += 1
                        team_stats[a_name]["ueberzahl_tore_kassiert"] += 1
                else:
                    if len(active_penalties_a) < len(active_penalties_h): 
                        team_stats[a_name]["ueberzahl_tore_erzielt"] += 1
                        team_stats[h_name]["unterzahl_tore_kassiert"] += 1
                    elif len(active_penalties_a) > len(active_penalties_h): 
                        team_stats[a_name]["unterzahl_tore_erzielt"] += 1
                        team_stats[h_name]["ueberzahl_tore_kassiert"] += 1

                if scoring_team_name == current_run_team:
                    current_run_count += 1
                else:
                    current_run_team = scoring_team_name
                    current_run_count = 1
                
                if current_run_count > team_stats[scoring_team_name]["max_lauf"]:
                    team_stats[scoring_team_name]["max_lauf"] = current_run_count

                phase_key = None
                if sec <= 300: phase_key = "start_h1"
                elif 1500 <= sec <= 1800: phase_key = "ende_h1"
                elif 1800 < sec <= 2100: phase_key = "start_h2"
                elif 3300 <= sec <= 3600: phase_key = "ende_h2"

                if phase_key:
                    team_stats[scoring_team_name][f"{phase_key}_tore"] += 1
                    team_stats[conceding_team_name][f"{phase_key}_geg"] += 1

                if sec >= 3300 and abs(diff) <= 2:
                    team_stats[scoring_team_name]["crunch_time_tore"] += 1
                    if p_id: player_stats[p_id]["clutch_tore"] += 1

                if not first_goal_recorded and p_id:
                    player_stats[p_id]["icebreaker"] += 1
                    first_goal_recorded = True

                if p_id:
                    if sec <= 1800: player_stats[p_id]["tore_h1"] += 1
                    else: player_stats[p_id]["tore_h2"] += 1

                if last_scoring_team == conceding_team_name:
                    response_time = sec - last_scoring_time
                    if 0 < response_time <= 45:
                        team_stats[scoring_team_name]["schnelle_mitte_sekunden"].append(response_time)

                last_own_goal_time = last_goal_time_h if scoring_team_name == h_name else last_goal_time_a
                drought = sec - last_own_goal_time
                if drought > team_stats[scoring_team_name]["torkrisen_max_sekunden"]:
                    team_stats[scoring_team_name]["torkrisen_max_sekunden"] = drought

                if scoring_team_name == h_name: last_goal_time_h = sec
                else: last_goal_time_a = sec
                
                last_scoring_team = scoring_team_name
                last_scoring_time = sec

        if h_goals >= a_goals:
            if abs(max_deficit_home) > team_stats[h_name]["max_comeback"]:
                team_stats[h_name]["max_comeback"] = abs(max_deficit_home)
        if a_goals >= h_goals:
            if max_deficit_away > team_stats[a_name]["max_comeback"]:
                team_stats[a_name]["max_comeback"] = max_deficit_away

    return dict(team_stats), dict(player_stats), dict(referees_count), dict(timekeepers_count), dict(matchday_players), penalty_minutes

team_data, player_data, ref_data, tk_data, matchday_data, penalty_data = load_and_aggregate_data()

if not team_data:
    st.warning("Keine Spieldaten gefunden oder alle Spiele liegen in der Zukunft.")
    st.stop()

df_teams = pd.DataFrame.from_dict(team_data, orient='index').reset_index()
df_teams.rename(columns={"index": "Team"}, inplace=True)
df_teams['Tore/Spiel'] = df_teams['tore_erzielt'] / df_teams['spiele']
df_teams['Gegentore/Spiel'] = df_teams['tore_kassiert'] / df_teams['spiele']
df_teams['2Min/Spiel'] = df_teams['strafen_2min'] / df_teams['spiele']
df_teams['7m-Quote (%)'] = (df_teams['siebenmeter_tore'] / df_teams['siebenmeter_versuche'] * 100).fillna(0)
df_teams['Ø Zuschauer'] = (df_teams['zuschauer_gesamt'] / df_teams['heimspiele']).fillna(0)

df_teams['Ø_Schnelle_Mitte_Sek'] = df_teams['schnelle_mitte_sekunden'].apply(lambda x: sum(x)/len(x) if len(x)>0 else 0)
df_teams['Überzahl_Bilanz'] = df_teams['ueberzahl_tore_erzielt'] - df_teams['ueberzahl_tore_kassiert']
df_teams['Ø_Ueberzahl_PlusMinus'] = df_teams['Überzahl_Bilanz'] / df_teams['spiele']
df_teams['Torkrise_Max_Min'] = df_teams['torkrisen_max_sekunden'] / 60

df_players = pd.DataFrame.from_dict(player_data, orient='index').reset_index()
df_players.rename(columns={"index": "Name_Raw"}, inplace=True)
df_players['Name'] = df_players['Name_Raw'].apply(lambda x: x.split(" (")[0])
df_players['Feldtore'] = df_players['tore'] - df_players['7m_tore']

st.sidebar.title("📊 Analyse-Zentrale")
ansicht = st.sidebar.radio("Bereich wählen:", [
    "Liga-Vergleich (Teams)", 
    "Detail-Analyse (Pro Team)",
    "Team-Vergleich (H2H)",
    "Top-Listen (Spielerinnen)",
    "⭐ Team der Woche",
    "⏱️ Spielphasen & Momentum",
    "🧠 Deep-Dive Analytics",
    "🏟️ Zuschauer & Unterzahl",
    "👨‍⚖️ Schiedsrichter & Offizielle"
])

def create_chart(df, x_col, title, color_theme, text_format='.1f', ascending=True):
    df_sorted = df.sort_values(x_col, ascending=ascending)
    fig = px.bar(
        df_sorted, x=x_col, y="Team", orientation='h',
        text_auto=text_format, title=title,
        color_discrete_sequence=[color_theme],
        hover_data={"Team": True, x_col: text_format, "spiele": True}
    )
    fig.update_layout(yaxis_title=None, xaxis_title=None, yaxis=dict(tickmode='linear'), margin=dict(l=200, r=20, t=40, b=20))
    return fig

if ansicht == "Liga-Vergleich (Teams)":
    st.title("🏆 Liga-Vergleich (Alle Teams)")
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(create_chart(df_teams, 'Tore/Spiel', "🔥 Beste Offensive (Tore pro Spiel)", "#3366cc"), use_container_width=True)
        st.plotly_chart(create_chart(df_teams, '2Min/Spiel', "⚠️ Unfairste Teams (2-Minuten pro Spiel)", "#dc3912"), use_container_width=True)
    with col2:
        st.plotly_chart(create_chart(df_teams, 'Gegentore/Spiel', "🧱 Beste Defensive (Gegentore pro Spiel)", "#109618", ascending=False), use_container_width=True)
        df_7m = df_teams[df_teams['siebenmeter_versuche'] > 5]
        st.plotly_chart(create_chart(df_7m, '7m-Quote (%)', "🎯 Sicherste 7-Meter-Teams (%)", "#ff9900"), use_container_width=True)

elif ansicht == "Detail-Analyse (Pro Team)":
    st.title("🔍 Einzel-Team-Analyse")
    gewaehltes_team = st.selectbox("Wähle ein Team aus:", sorted(df_teams['Team'].tolist()))
    if gewaehltes_team:
        team_stats = df_teams[df_teams['Team'] == gewaehltes_team].iloc[0]
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("Absolvierte Spiele", int(team_stats['spiele']))
        kpi2.metric("Ø Tore erzielt", f"{team_stats['Tore/Spiel']:.1f}")
        kpi3.metric("Ø Gegentore", f"{team_stats['Gegentore/Spiel']:.1f}")
        kpi4.metric("7m-Trefferquote", f"{team_stats['7m-Quote (%)']:.1f} %")
        st.divider()
        team_players = df_players[df_players['team'] == gewaehltes_team].copy()
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Top-Torschützinnen")
            st.dataframe(team_players[['Name', 'tore', '7m_tore']].sort_values(by='tore', ascending=False).head(15).rename(columns={'tore': 'Gesamttore', '7m_tore': 'davon 7m'}), hide_index=True, use_container_width=True)
        with c2:
            st.subheader("Interne Strafen-Übersicht")
            st.dataframe(team_players[team_players['2min'] > 0][['Name', '2min']].sort_values(by='2min', ascending=False).rename(columns={'2min': 'Anzahl 2-Minuten'}), hide_index=True, use_container_width=True)

elif ansicht == "Team-Vergleich (H2H)":
    st.title("⚔️ Direkter Team-Vergleich")
    alle_teams = sorted(df_teams['Team'].tolist())
    c1, c2 = st.columns(2)
    team_a = c1.selectbox("Team A", alle_teams, index=0)
    team_b = c2.selectbox("Team B", alle_teams, index=1 if len(alle_teams) > 1 else 0)
    if team_a and team_b and team_a != team_b:
        stats_a = df_teams[df_teams['Team'] == team_a].iloc[0]
        stats_b = df_teams[df_teams['Team'] == team_b].iloc[0]
        comp_data = []
        for kpi in ['Tore/Spiel', 'Gegentore/Spiel', '2Min/Spiel', '7m-Quote (%)']:
            comp_data.append({"Kategorie": kpi, "Team": team_a, "Wert": stats_a[kpi]})
            comp_data.append({"Kategorie": kpi, "Team": team_b, "Wert": stats_b[kpi]})
        fig = px.bar(pd.DataFrame(comp_data), x="Kategorie", y="Wert", color="Team", barmode="group", text_auto='.1f', color_discrete_sequence=["#3366cc", "#ff9900"])
        st.plotly_chart(fig, use_container_width=True)

elif ansicht == "Top-Listen (Spielerinnen)":
    st.title("⭐ Ligaweite Top-Listen")
    kat = st.radio("Kategorie wählen:", ["Meiste Tore (Gesamt)", "Meiste Feldtore", "Sicherste 7m-Schützinnen", "Meiste 2-Minuten-Strafen"], horizontal=True)
    sort_col = "tore" if kat == "Meiste Tore (Gesamt)" else ("Feldtore" if kat == "Meiste Feldtore" else ("7m_tore" if kat == "Sicherste 7m-Schützinnen" else "2min"))
    top_p = df_players[df_players[sort_col] > 0].sort_values(by=sort_col, ascending=False).head(25)
    top_p['Label'] = top_p['Name'] + " (" + top_p['team'] + ")"
    c1, c2 = st.columns([2, 1])
    with c1:
        fig = px.bar(top_p.head(10).sort_values(by=sort_col, ascending=True), x=sort_col, y="Label", orientation='h', text_auto=True, color="team")
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.dataframe(top_p[['Name', 'team', sort_col]].rename(columns={'team': 'Team'}), use_container_width=True, hide_index=True)

elif ansicht == "⭐ Team der Woche":
    st.title("⭐ Team der Woche (Nach Spieltag)")
    verfuegbare_spieltage = sorted([m for m in matchday_data.keys() if m != 0])
    
    if verfuegbare_spieltage:
        auswahl_st = st.selectbox("Spieltag auswählen:", verfuegbare_spieltage, index=len(verfuegbare_spieltage)-1)
        df_md = pd.DataFrame(matchday_data[auswahl_st])
        if not df_md.empty:
            df_md = df_md.sort_values(by=["Tore", "Feldtore"], ascending=[False, False]).head(7)
            df_md.index = range(1, len(df_md) + 1)
            
            st.subheader(f"Die 7 besten Spielerinnen am {auswahl_st}. Spieltag")
            st.dataframe(df_md, use_container_width=True)
            
            fig_md = px.bar(df_md, x="Name", y="Tore", color="Team", text="Tore", title=f"Top-Performer Spieltag {auswahl_st}")
            st.plotly_chart(fig_md, use_container_width=True)
        else:
            st.info("Keine Daten für diesen Spieltag.")
    else:
        st.info("Noch keine Spieltage mit auswertbaren Toren erfasst.")

elif ansicht == "⏱️ Spielphasen & Momentum":
    st.title("⏱️ Spielphasen, Momentum & Nervenstärke")
    tab1, tab2, tab3 = st.tabs(["Die 5-Minuten-Phasen", "Torserien (Längste Läufe)", "Crunch-Time & Comebacks"])
    
    with tab1:
        st.subheader("Performance in kritischen Spielphasen")
        st.write("Wie viele Tore wirft (und kassiert) ein Team direkt nach Anpfiff oder kurz vor der Halbzeitsirene?")
        phase = st.selectbox("Phase wählen:", [
            "Start 1. Halbzeit (0-5 Min)", "Ende 1. Halbzeit (25-30 Min)",
            "Start 2. Halbzeit (30-35 Min)", "Ende 2. Halbzeit (55-60 Min)"
        ])
        col_tore = "start_h1_tore"
        col_geg = "start_h1_geg"
        if "Ende 1." in phase: col_tore, col_geg = "ende_h1_tore", "ende_h1_geg"
        elif "Start 2." in phase: col_tore, col_geg = "start_h2_tore", "start_h2_geg"
        elif "Ende 2." in phase: col_tore, col_geg = "ende_h2_tore", "ende_h2_geg"
        
        df_teams['Phasen_Diff'] = df_teams[col_tore] - df_teams[col_geg]
        
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(create_chart(df_teams, col_tore, f"Geworfene Tore: {phase}", "#1f77b4", text_format='.0f'), use_container_width=True)
        with c2:
            st.plotly_chart(create_chart(df_teams, 'Phasen_Diff', f"Tordifferenz (+/-) in: {phase}", "#ff7f0e", text_format='.0f'), use_container_width=True)

    with tab2:
        st.subheader("🔥 Momentum: Die längsten Torserien (Läufe)")
        st.plotly_chart(create_chart(df_teams, 'max_lauf', "Längste Torserie (Tore am Stück)", "#2ca02c", text_format='.0f'), use_container_width=True)

    with tab3:
        st.subheader("🧊 Crunch-Time-Qualitäten & Comebacks")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Crunch-Time-Tore**")
            st.plotly_chart(create_chart(df_teams, 'crunch_time_tore', "Nervenstärke (Crunch-Time Tore)", "#d62728", text_format='.0f'), use_container_width=True)
        with c2:
            st.markdown("**Die Comeback-Könige**")
            st.plotly_chart(create_chart(df_teams, 'max_comeback', "Größter aufgeholter Rückstand", "#9467bd", text_format='.0f'), use_container_width=True)

elif ansicht == "🧠 Deep-Dive Analytics":
    st.title("🧠 Deep-Dive Analytics")
    
    t1, t2, t3, t4, t5 = st.tabs(["⚡ Schnelle Mitte & Krisen", "⚖️ 2-Minuten Effizienz", "🧊 Clutch Players & Icebreaker", "🏃‍♀️ Kondition (H1 vs H2)", "⏱️ Strafen-Ermüdung"])
    
    with t1:
        st.subheader("Umschaltspiel & Offensiv-Blackouts")
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(create_chart(df_teams[df_teams['Ø_Schnelle_Mitte_Sek'] > 0], 'Ø_Schnelle_Mitte_Sek', "Ø Reaktionszeit nach Gegentor (Sek)", "#e377c2", ascending=False), use_container_width=True)
        with c2:
            st.plotly_chart(create_chart(df_teams, 'Torkrise_Max_Min', "Längste Torflaute (Minuten ohne Tor)", "#7f7f7f", ascending=False), use_container_width=True)
            
    with t2:
        st.subheader("Die wahre Überzahl-Bilanz")
        st.write("Tordifferenz (Plus/Minus), die ein Team **im Durchschnitt pro Spiel während der eigenen Überzahl** erzielt.")
        st.plotly_chart(create_chart(df_teams, 'Ø_Ueberzahl_PlusMinus', "Ø Tordifferenz in Überzahl (Pro Spiel)", "#17becf"), use_container_width=True)
        
    with t3:
        st.subheader("Nervenstärke & Game-Opener")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**🧊 Clutch Players (Tore in letzten 5 Min bei +/- 2)**")
            st.dataframe(df_players[df_players['clutch_tore']>0][['Name', 'team', 'clutch_tore']].sort_values(by='clutch_tore', ascending=False).head(10), hide_index=True)
        with c2:
            st.markdown("**🔨 Icebreaker (Erstes Tor des Spiels)**")
            st.dataframe(df_players[df_players['icebreaker']>0][['Name', 'team', 'icebreaker']].sort_values(by='icebreaker', ascending=False).head(10), hide_index=True)

    with t4:
        st.subheader("🏃‍♀️ Spielerinnen-Kondition (Halbzeit-Vergleich)")
        st.write("Wer wirft die Tore in der 1. Halbzeit, wer dreht in der 2. Halbzeit auf?")
        cond_df = df_players[(df_players['tore_h1'] > 5) | (df_players['tore_h2'] > 5)].copy()
        cond_df['H2_Dominanz'] = cond_df['tore_h2'] - cond_df['tore_h1']
        st.dataframe(cond_df[['Name', 'team', 'tore_h1', 'tore_h2', 'H2_Dominanz']].sort_values(by='H2_Dominanz', ascending=False), hide_index=True, use_container_width=True)

    with t5:
        st.subheader("⏱️ Strafen-Ermüdung (Wann fallen die Strafen?)")
        if penalty_data and sum(penalty_data.values()) > 0:
            df_pen = pd.DataFrame(list(penalty_data.items()), columns=['Minute', 'Anzahl']).sort_values('Minute')
            fig = px.bar(df_pen, x='Minute', y='Anzahl', title="Ligaweite Zeitstrafen nach Spielminute", color_discrete_sequence=["#d62728"])
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Keine Strafen im Zeitverlauf gefunden.")

elif ansicht == "🏟️ Zuschauer & Unterzahl":
    st.title("🏟️ Zuschauer & Unterzahl-Analyse")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📢 Zuschauer-Ranking (Ø pro Heimspiel)")
        df_zuschauer = df_teams[df_teams['heimspiele'] > 0].sort_values('Ø Zuschauer', ascending=True)
        fig_z = px.bar(df_zuschauer, x='Ø Zuschauer', y='Team', orientation='h', text_auto='.0f', color_discrete_sequence=["#9c27b0"])
        st.plotly_chart(fig_z, use_container_width=True)
    with col2:
        st.subheader("🛡️ Kassierte Tore während Unterzahl")
        df_uz = df_teams.sort_values('unterzahl_tore_kassiert', ascending=False)
        fig_uz = px.bar(df_uz, x='unterzahl_tore_kassiert', y='Team', orientation='h', text_auto=True, color_discrete_sequence=["#e91e63"])
        st.plotly_chart(fig_uz, use_container_width=True)

elif ansicht == "👨‍⚖️ Schiedsrichter & Offizielle":
    st.title("👨‍⚖️ Schiedsrichter & Zeitnehmer Einsätze")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Schiedsrichter-Einsätze")
        if ref_data:
            df_ref = pd.DataFrame(list(ref_data.items()), columns=['Name', 'Einsätze']).sort_values('Einsätze', ascending=False)
            st.dataframe(df_ref, hide_index=True, use_container_width=True)
        else:
            st.info("Keine Schiedsrichterdaten erfasst.")
    with col2:
        st.subheader("Zeitnehmer / Sekretäre")
        if tk_data:
            df_tk = pd.DataFrame(list(tk_data.items()), columns=['Name', 'Einsätze']).sort_values('Einsätze', ascending=False)
            st.dataframe(df_tk, hide_index=True, use_container_width=True)
        else:
            st.info("Keine Zeitnehmerdaten erfasst.")