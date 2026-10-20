import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import plotly.express as px
import plotly.graph_objects as go

# --- 1. KONFIGURATION ---
st.set_page_config(page_title="Handball Liga-Analyse", layout="wide", page_icon="🤾")

CURRENT_DATE = datetime(2026, 10, 20)
DATA_DIR = Path("data/processed")

# --- 2. DATEN LADEN & FILTERN ---
def default_team():
    return {"spiele": 0, "tore_erzielt": 0, "tore_kassiert": 0, 
            "siebenmeter_tore": 0, "siebenmeter_versuche": 0, "strafen_2min": 0}

def default_player():
    return {"team": "", "tore": 0, "7m_tore": 0, "2min": 0}

@st.cache_data
def load_and_aggregate_data():
    team_stats = defaultdict(default_team)
    player_stats = defaultdict(default_player)

    if not DATA_DIR.exists():
        return {}, {}

    for file in DATA_DIR.glob("match_*.json"):
        with open(file, "r", encoding="utf-8") as f:
            match = json.load(f)
            
        meta = match.get("metadata", {})
        date_str = meta.get("date")
        
        if date_str:
            try:
                match_date = datetime.strptime(date_str, "%d.%m.%Y")
                if match_date > CURRENT_DATE:
                    continue
            except ValueError:
                pass 
        
        teams = match.get("teams", {})
        if "home" in teams and "away" in teams:
            h_name = teams["home"].get("name", "Unbekannt")
            a_name = teams["away"].get("name", "Unbekannt")
            
            score = meta.get("final_score", "")
            h_goals, a_goals = 0, 0
            if ":" in score:
                try:
                    h_goals, a_goals = map(int, score.split(":"))
                except ValueError:
                    pass

            team_stats[h_name]["spiele"] += 1
            team_stats[h_name]["tore_erzielt"] += h_goals
            team_stats[h_name]["tore_kassiert"] += a_goals
            
            team_stats[a_name]["spiele"] += 1
            team_stats[a_name]["tore_erzielt"] += a_goals
            team_stats[a_name]["tore_kassiert"] += h_goals

            for side, t_name in [("home", h_name), ("away", a_name)]:
                for p in teams[side].get("players", []):
                    p_name = p.get("name")
                    if not p_name: continue
                    
                    p_id = f"{p_name} ({t_name})"
                    player_stats[p_id]["team"] = t_name
                    player_stats[p_id]["tore"] += p.get("goals", 0)
                    player_stats[p_id]["2min"] += len(p.get("two_minutes", []))
                    team_stats[t_name]["strafen_2min"] += len(p.get("two_minutes", []))
                    
                    sm_str = p.get("seven_m")
                    if sm_str and "/" in sm_str:
                        try:
                            treffer, versuche = map(int, sm_str.split("/"))
                            player_stats[p_id]["7m_tore"] += treffer
                            team_stats[t_name]["siebenmeter_tore"] += treffer
                            team_stats[t_name]["siebenmeter_versuche"] += versuche
                        except ValueError:
                            pass

    return dict(team_stats), dict(player_stats)

team_data, player_data = load_and_aggregate_data()

# --- 3. DATEN AUFBEREITEN ---
if team_data:
    df_teams = pd.DataFrame.from_dict(team_data, orient='index').reset_index()
    df_teams.rename(columns={"index": "Team"}, inplace=True)
    
    df_teams['Tore/Spiel'] = df_teams['tore_erzielt'] / df_teams['spiele']
    df_teams['Gegentore/Spiel'] = df_teams['tore_kassiert'] / df_teams['spiele']
    df_teams['2Min/Spiel'] = df_teams['strafen_2min'] / df_teams['spiele']
    df_teams['7m-Quote (%)'] = (df_teams['siebenmeter_tore'] / df_teams['siebenmeter_versuche'] * 100).fillna(0)
    
    df_players = pd.DataFrame.from_dict(player_data, orient='index').reset_index()
    df_players.rename(columns={"index": "Name_Raw"}, inplace=True)
    df_players['Name'] = df_players['Name_Raw'].apply(lambda x: x.split(" (")[0])
    df_players['Feldtore'] = df_players['tore'] - df_players['7m_tore']
else:
    st.warning("Keine Spieldaten gefunden oder alle Spiele liegen in der Zukunft.")
    st.stop()

# --- 4. LAYOUT & NAVIGATION ---
st.sidebar.title("📊 Analyse-Zentrale")
ansicht = st.sidebar.radio("Bereich wählen:", [
    "Liga-Vergleich (Teams)", 
    "Detail-Analyse (Pro Team)",
    "Team-Vergleich (H2H)",
    "Top-Listen (Spielerinnen)"
])

# Hilfsfunktion für einheitliche Plotly-Charts
def create_chart(df, x_col, title, color_theme):
    df_sorted = df.sort_values(x_col, ascending=True)
    fig = px.bar(
        df_sorted, x=x_col, y="Team", orientation='h',
        text_auto='.1f', title=title,
        color_discrete_sequence=[color_theme],
        hover_data={"Team": True, x_col: ':.1f', "spiele": True}
    )
    fig.update_layout(
        yaxis_title=None, xaxis_title=None, 
        yaxis=dict(tickmode='linear'), 
        margin=dict(l=200, r=20, t=40, b=20) 
    )
    return fig

# ==========================================
# ANSICHT 1: LIGA-VERGLEICH
# ==========================================
if ansicht == "Liga-Vergleich (Teams)":
    st.title("🏆 Liga-Vergleich (Alle Teams)")
    
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(create_chart(df_teams, 'Tore/Spiel', "🔥 Beste Offensive (Tore pro Spiel)", "#3366cc"), use_container_width=True)
        st.plotly_chart(create_chart(df_teams, '2Min/Spiel', "⚠️ Unfairste Teams (2-Minuten pro Spiel)", "#dc3912"), use_container_width=True)
        
    with col2:
        df_def = df_teams.sort_values('Gegentore/Spiel', ascending=False)
        fig_def = px.bar(
            df_def, x='Gegentore/Spiel', y="Team", orientation='h',
            text_auto='.1f', title="🧱 Beste Defensive (Gegentore pro Spiel)",
            color_discrete_sequence=["#109618"],
            hover_data={"Team": True, 'Gegentore/Spiel': ':.1f', "spiele": True}
        )
        fig_def.update_layout(yaxis_title=None, xaxis_title=None, yaxis=dict(tickmode='linear'), margin=dict(l=200, r=20, t=40, b=20))
        st.plotly_chart(fig_def, use_container_width=True)
        
        df_7m = df_teams[df_teams['siebenmeter_versuche'] > 5]
        st.plotly_chart(create_chart(df_7m, '7m-Quote (%)', "🎯 Sicherste 7-Meter-Teams (%)", "#ff9900"), use_container_width=True)

# ==========================================
# ANSICHT 2: TEAM-DETAILS
# ==========================================
elif ansicht == "Detail-Analyse (Pro Team)":
    st.title("🔍 Einzel-Team-Analyse")
    
    alle_teams = sorted(df_teams['Team'].tolist())
    gewaehltes_team = st.selectbox("Wähle ein Team aus:", alle_teams)
    
    if gewaehltes_team:
        team_stats = df_teams[df_teams['Team'] == gewaehltes_team].iloc[0]
        
        st.markdown(f"### Saison-Statistiken: {gewaehltes_team}")
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("Absolvierte Spiele", int(team_stats['spiele']))
        kpi2.metric("Ø Tore erzielt", f"{team_stats['Tore/Spiel']:.1f}")
        kpi3.metric("Ø Gegentore", f"{team_stats['Gegentore/Spiel']:.1f}")
        kpi4.metric("7m-Trefferquote", f"{team_stats['7m-Quote (%)']:.1f} %")
        
        st.divider()
        team_players = df_players[df_players['team'] == gewaehltes_team].copy()
        
        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Top-Torschützinnen")
            top_scorer = team_players[['Name', 'tore', '7m_tore']].sort_values(by='tore', ascending=False).head(15)
            top_scorer.columns = ['Spielerin', 'Gesamttore', 'davon 7m']
            st.dataframe(top_scorer, hide_index=True, use_container_width=True)
            
        with col_b:
            st.subheader("Interne Strafen-Übersicht")
            bad_girls = team_players[team_players['2min'] > 0][['Name', '2min']].sort_values(by='2min', ascending=False)
            bad_girls.columns = ['Spielerin', 'Anzahl 2-Minuten']
            st.dataframe(bad_girls, hide_index=True, use_container_width=True)

# ==========================================
# ANSICHT 3: TEAM-VERGLEICH (Head-to-Head)
# ==========================================
elif ansicht == "Team-Vergleich (H2H)":
    st.title("⚔️ Direkter Team-Vergleich")
    
    alle_teams = sorted(df_teams['Team'].tolist())
    col1, col2 = st.columns(2)
    
    with col1:
        team_a = st.selectbox("Team A", alle_teams, index=0)
    with col2:
        # Standardmäßig ein anderes Team als Team B auswählen
        default_idx = 1 if len(alle_teams) > 1 else 0
        team_b = st.selectbox("Team B", alle_teams, index=default_idx)
        
    if team_a and team_b:
        if team_a == team_b:
            st.warning("Bitte wähle zwei unterschiedliche Teams aus.")
        else:
            # Daten für das Chart vorbereiten
            stats_a = df_teams[df_teams['Team'] == team_a].iloc[0]
            stats_b = df_teams[df_teams['Team'] == team_b].iloc[0]
            
            # Ein DataFrame für Plotly formatieren (Melt)
            kpis = ['Tore/Spiel', 'Gegentore/Spiel', '2Min/Spiel', '7m-Quote (%)']
            comp_data = []
            
            for kpi in kpis:
                comp_data.append({"Kategorie": kpi, "Team": team_a, "Wert": stats_a[kpi]})
                comp_data.append({"Kategorie": kpi, "Team": team_b, "Wert": stats_b[kpi]})
                
            df_comp = pd.DataFrame(comp_data)
            
            # Gruppiertes Balkendiagramm erstellen
            fig = px.bar(
                df_comp, x="Kategorie", y="Wert", color="Team", barmode="group",
                text_auto='.1f', title=f"{team_a} vs. {team_b} (Durchschnittswerte)",
                color_discrete_sequence=["#3366cc", "#ff9900"]
            )
            fig.update_layout(yaxis_title="Wert", xaxis_title=None)
            st.plotly_chart(fig, use_container_width=True)
            
            # Top Scorer Head-to-Head
            st.markdown("### Top-Scorer im Vergleich")
            c1, c2 = st.columns(2)
            for col, team_name in zip((c1, c2), (team_a, team_b)):
                with col:
                    st.write(f"**{team_name}**")
                    t_players = df_players[df_players['team'] == team_name].sort_values(by='tore', ascending=False).head(5)
                    st.dataframe(t_players[['Name', 'tore', 'Feldtore', '7m_tore']].rename(
                        columns={'tore': 'Gesamt', '7m_tore': '7m'}), hide_index=True, use_container_width=True)

# ==========================================
# ANSICHT 4: TOP-LISTEN (LIGAWEIT)
# ==========================================
elif ansicht == "Top-Listen (Spielerinnen)":
    st.title("⭐ Ligaweite Top-Listen")
    
    # Kategorie-Auswahl
    kategorie = st.radio("Was möchtest du sehen?", [
        "Meiste Tore (Feld + 7m)", 
        "Meiste Feldtore", 
        "Sicherste 7-Meter-Schützinnen", 
        "Meiste 2-Minuten-Strafen"
    ], horizontal=True)
    
    st.divider()
    
    # Entsprechende Spalte für die Sortierung setzen
    sort_col = "tore"
    if kategorie == "Meiste Feldtore":
        sort_col = "Feldtore"
    elif kategorie == "Sicherste 7-Meter-Schützinnen":
        sort_col = "7m_tore"
    elif kategorie == "Meiste 2-Minuten-Strafen":
        sort_col = "2min"
        
    # Top Spielerinnen ligaweit ermitteln (z.B. Top 25)
    top_players = df_players[df_players[sort_col] > 0].sort_values(by=sort_col, ascending=False).head(25)
    
    # Beschriftung für den Graphen erstellen
    top_players['Label'] = top_players['Name'] + " (" + top_players['team'] + ")"
    
    col_chart, col_table = st.columns([2, 1])
    
    with col_chart:
        # Graphen von unten nach oben aufbauen (damit der 1. Platz ganz oben ist)
        chart_data = top_players.head(10).sort_values(by=sort_col, ascending=True)
        fig = px.bar(
            chart_data, x=sort_col, y="Label", orientation='h',
            text_auto=True, title=f"Top 10: {kategorie}",
            color="team", hover_data={"Label": False, "Name": True, "team": True, sort_col: True}
        )
        fig.update_layout(yaxis_title=None, xaxis_title="Anzahl", showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
        
    with col_table:
        # Reine Daten-Tabelle anzeigen
        anzeige_df = top_players[['Name', 'team', sort_col]].rename(columns={'team': 'Team'})
        anzeige_df.index = range(1, len(anzeige_df) + 1)  # Index von 1 bis X für die Platzierung
        st.write(f"**Top 25 Tabelle**")
        st.dataframe(anzeige_df, use_container_width=True)
import json
from pathlib import Path
from collections import Counter, defaultdict
import pandas as pd
import streamlit as st  # Falls du Streamlit als Dashboard-Framework nutzt

# 1. Daten laden (Beispiel-Funktion aus deinem Projekt)
from src.analytics import load_all_games
games_df, player_stats_df = load_all_games()

# 2. Zusätzliche Offiziellen-Daten direkt aus den JSONs laden
def load_officials_stats(processed_dir="data/processed"):
    path = Path(processed_dir)
    referees_list = []
    timekeepers_list = []

    for json_file in path.glob("match_*.json"):
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        meta = data.get("metadata", {})
        match_id = json_file.stem.replace("match_", "")
        
        # Schiedsrichter auslesen (kann unter 'referees' direkt oder im Meta-Bereich liegen)
        refs = data.get("referees", []) or meta.get("referees", [])
        for ref in refs:
            # Unterscheidung ob Dict oder String
            name = ref.get("name") if isinstance(ref, dict) else ref
            if name:
                referees_list.append({"match_id": match_id, "official": name.strip()})
                
        # Zeitnehmer / Sekretär auslesen
        tk = meta.get("timekeeper", "") or meta.get("sekretaer", "")
        if tk and isinstance(tk, str):
            timekeepers_list.append({"match_id": match_id, "official": tk.strip()})

    ref_df = pd.DataFrame(referees_list)
    tk_df = pd.DataFrame(timekeepers_list)

    ref_stats = ref_df.groupby("official")["match_id"].count().reset_index(name="Anzahl_Einsätze").sort_values(by="Anzahl_Einsätze", ascending=False) if not ref_df.empty else pd.DataFrame()
    tk_stats = tk_df.groupby("official")["match_id"].count().reset_index(name="Anzahl_Einsätze").sort_values(by="Anzahl_Einsätze", ascending=False) if not tk_df.empty else pd.DataFrame()

    return ref_stats, tk_stats

ref_ranking, tk_ranking = load_officials_stats()

# ==============================================================================
# DASHBOARD STRUKTUR (MIT TABS)
# ==============================================================================
st.title("Handball Saison-Dashboard")

tab_overview, tab_spectators, tab_special_teams, tab_officials = st.tabs([
    "Übersicht", 
    "Zuschauerstatistik", 
    "Über- / Unterzahl", 
    "Schiedsrichter & Zeitnehmer"
])

with tab_overview:
    st.subheader("Allgemeine Saisonübersicht")
    st.dataframe(games_df.head())

with tab_spectators:
    st.subheader("Zuschauerstatistik nach Heim-Teams")
    valid_games = games_df[games_df["spectators"] > 0].copy()
    if not valid_games.empty:
        spectator_stats = valid_games.groupby("home_team").agg(
            Heimspiele=("spectators", "count"),
            Zuschauer_Gesamt=("spectators", "sum"),
            Zuschauer_Schnitt=("spectators", "mean")
        ).reset_index()

        spectator_stats = spectator_stats.sort_values(by="Zuschauer_Schnitt", ascending=False)
        spectator_stats["Zuschauer_Schnitt"] = spectator_stats["Zuschauer_Schnitt"].round(1)
        
        st.dataframe(spectator_stats, use_container_width=True)
    else:
        st.info("Keine Zuschauerdaten verfügbar.")

with tab_special_teams:
    st.subheader("Leistungsdaten in Über- und Unterzahl")
    st.write("Hier fließen die Zeitstrafen-Analysen aus der Timeline des Parsers ein.")
    # Beispielhaftes Einbinden der Unterzahl/Überzahl-Auswertung aus deinem Projekt
    if "two_minutes" in player_stats_df.columns:
        st.dataframe(player_stats_df[["name", "team", "two_minutes", "goals"]].sort_values(by="two_minutes", ascending=False))
    else:
        st.info("Unter-/Überzahl-Metriken werden über die Timeline-Objekte berechnet.")

with tab_officials:
    st.subheader("Offiziellen-Statistik (Einsätze)")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### Schiedsrichter-Ranking")
        if not ref_ranking.empty:
            st.dataframe(ref_ranking, use_container_width=True)
        else:
            st.warning("Keine Schiedsrichter-Daten gefunden.")
            
    with col2:
        st.markdown("### Zeitnehmer / Sekretäre")
        if not tk_ranking.empty:
            st.dataframe(tk_ranking, use_container_width=True)
        else:
            st.warning("Keine Zeitnehmer-Daten gefunden.")