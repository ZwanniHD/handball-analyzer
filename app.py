import plotly.express as px
import streamlit as st
from src.analytics import load_all_games

st.title("🤾 Handball 3. Liga Frauen Nord - Analytics")

games_df, events_df = load_all_games()

st.sidebar.header("Filter")
selected_match = st.sidebar.selectbox(
    "Wähle ein Spiel:",
    games_df["match_id"].tolist(),
    format_func=lambda x: f"Match {x}: {games_df[games_df['match_id']==x]['home_team'].values[0]} vs {games_df[games_df['match_id']==x]['away_team'].values[0]}",
)

# Filter auf ausgewähltes Spiel
match_events = events_df[events_df["match_id"] == selected_match]

st.subheader("Spielverlauf")
goals = match_events[match_events["Stand"].str.contains(":", na=False)].copy()

if not goals.empty:
    fig = px.line(
        goals,
        x="Minute",
        y="Stand",
        hover_data=["Person", "Team", "Ereignis"],
        title="Torverlauf",
    )
    st.plotly_chart(fig, use_container_width=True)