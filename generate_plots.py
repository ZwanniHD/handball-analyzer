import json
import re
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


def generate_corrected_top_scorers(json_path="raw_pdf_dumps.json"):
    # Load JSON raw PDF dumps
    with open(json_path, "r", encoding="utf-8") as f:
        dumps = json.load(f)

    player_data = {}

    for match in dumps:
        full_text = "\n".join([p["raw_text"] for p in match["pages"]])

        # Check if the match was actually played (must have valid goal results)
        has_score = bool(re.search(r"\b\d{1,2}\s*:\s*\d{1,2}\b", full_text))
        if not has_score:
            continue  # Skip unplayed / future fixtures

        # Extract team names
        heim_team, gast_team = "", ""
        heim_m = re.search(
            r"Heimmannschaft\s+(.*?)\s+(?:Spielort|Gastmannschaft)", full_text
        )
        if heim_m:
            heim_team = heim_m.group(1).strip()
        gast_m = re.search(
            r"Gastmannschaft\s+(.*?)\s+(?:Endstand|\d+:\d+|\n)", full_text
        )
        if gast_m:
            gast_team = gast_m.group(1).strip()

        # Parse squad list table from pages 1 and 2
        for page in match["pages"][:2]:
            lines = page["raw_text"].split("\n")
            current_team = ""
            for line in lines:
                if "Heim:" in line:
                    current_team = line.replace("Heim:", "").strip()
                elif "Gast:" in line:
                    current_team = line.replace("Gast:", "").strip()

                # Regex pattern matching player rows: Nr Name Goals (7m_goals/7m_attempts)
                m = re.match(
                    r"^\s*(\d+)\s+([A-Za-zÄÖÜäöüß–\-\s]+?)\s+(\d+)(?:\s+(\d+)/(\d+))?(?:\s+.*)?$",
                    line,
                )
                if m:
                    pname = m.group(2).strip()

                    # Exclude non-players / officials
                    if pname in [
                        "Name",
                        "Rolle",
                        "SR A",
                        "SR B",
                        "TECHNISCHE DELEGIERTE",
                        "ZEITNEHMER/SEKRETÄR",
                    ]:
                        continue
                    if any(char.isdigit() for char in pname):
                        continue

                    goals = int(m.group(3))
                    seven_m = int(m.group(4)) if m.group(4) else 0

                    team_name = (
                        current_team
                        if current_team
                        else (
                            heim_team if "Heim" in line else gast_team
                        )
                    )

                    key = (pname, team_name)
                    if key not in player_data:
                        player_data[key] = {
                            "goals": 0,
                            "7m": 0,
                            "games_played": 0,
                        }

                    player_data[key]["goals"] += goals
                    player_data[key]["7m"] += seven_m
                    player_data[key]["games_played"] += 1

    # Format into DataFrame
    rows = []
    for (pname, team), stats in player_data.items():
        games = stats["games_played"]
        goals = stats["goals"]
        avg = round(goals / games, 2) if games > 0 else 0.0
        rows.append(
            {
                "person": pname,
                "team": team,
                "Gesamttore": goals,
                "Siebenmeter": stats["7m"],
                "Spiele": games,
                "Tore_pro_Spiel": avg,
            }
        )

    df = pd.DataFrame(rows).sort_values(
        by=["Gesamttore", "Tore_pro_Spiel"], ascending=[False, False]
    )
    df["Rang"] = range(1, len(df) + 1)
    df = df[
        [
            "Rang",
            "person",
            "team",
            "Gesamttore",
            "Siebenmeter",
            "Spiele",
            "Tore_pro_Spiel",
        ]
    ]

    # Save to CSV
    df.to_csv("torschuetzenliste.csv", index=False)
    return df


def plot_top_scorers(df, top_n=10):
    # Filter Top N scorers
    df_top = df.head(top_n).copy()

    # Calculate Field Goals vs 7m Goals
    df_top["Feldtore"] = df_top["Gesamttore"] - df_top["Siebenmeter"]

    # Plot styling
    sns.set_theme(style="whitegrid")
    fig, ax1 = plt.subplots(figsize=(12, 6))

    # Stacked bar chart for Goals (Field Goals + 7m Goals)
    bar1 = ax1.bar(
        df_top["person"],
        df_top["Feldtore"],
        label="Feldtore",
        color="#1f77b4",
        alpha=0.85,
    )
    bar2 = ax1.bar(
        df_top["person"],
        df_top["Siebenmeter"],
        bottom=df_top["Feldtore"],
        label="7m-Tore",
        color="#ff7f0e",
        alpha=0.85,
    )

    ax1.set_ylabel("Gesamttore", fontsize=12, fontweight="bold")
    ax1.set_xlabel("Spielerin", fontsize=12, fontweight="bold")
    ax1.set_title(
        f"Top {top_n} Torschützinnen (Bereinigt)", fontsize=14, fontweight="bold"
    )
    plt.xticks(rotation=30, ha="right")

    # Secondary Y-Axis for Average Goals per Game (Line plot)
    ax2 = ax1.twinx()
    line = ax2.plot(
        df_top["person"],
        df_top["Tore_pro_Spiel"],
        color="#2ca02c",
        marker="o",
        linewidth=2.5,
        label="Tore pro Spiel",
    )
    ax2.set_ylabel(
        "Tore pro Spiel", fontsize=12, fontweight="bold", color="#2ca02c"
    )
    ax2.grid(False)

    # Annotate total goals on top of bars
    for idx, row in df_top.iterrows():
        ax1.text(
            row["person"],
            row["Gesamttore"] + 0.8,
            f"{int(row['Gesamttore'])} ({row['Spiele']} Sp.)",
            ha="center",
            va="bottom",
            fontsize=9,
            fontweight="bold",
        )

    # Combined Legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right")

    plt.tight_layout()
    plt.savefig("top_torschuetzen_plot.png", dpi=300)
    plt.show()


# Run pipeline
df = generate_corrected_top_scorers("raw_pdf_dumps.json")
plot_top_scorers(df, top_n=10)