"""
app.py — FCHL Season Predictor (Streamlit)

Simulates remaining NHL games and projects fantasy points for 6 FCHL teams.

Scoring: G=1pt, A=1pt, W=2pts, SO=3pts
Lineup:  12F, 6D, 2G per team
"""

from pathlib import Path

import pandas as pd
import streamlit as st

from data_loader import (
    DEFAULT_FCHL_POINTS,
    FCHL_TEAMS,
    build_player_lookup,
    load_fchl_roster,
    load_goalie_stats,
    load_schedule,
    load_skater_stats,
)
from projections import compute_standings, project_all_players

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent
FCHL_CSV = str(BASE_DIR / "data" / "FCHL Players - Sheet1.csv")
SCHEDULE_CSV = str(BASE_DIR / "data" / "nhl-202526-asplayed.csv")
SKATERS_CSV = str(BASE_DIR / "data" / "skaters.csv")
GOALIES_CSV = str(BASE_DIR / "data" / "goalies.csv")

# ---------------------------------------------------------------------------
# Cached data loaders
# ---------------------------------------------------------------------------

@st.cache_data
def get_skater_stats():
    return load_skater_stats(SKATERS_CSV)

@st.cache_data
def get_goalie_stats():
    return load_goalie_stats(GOALIES_CSV)

@st.cache_data
def get_schedule():
    return load_schedule(SCHEDULE_CSV)

@st.cache_data
def get_original_roster():
    return load_fchl_roster(FCHL_CSV)

# ---------------------------------------------------------------------------
# App config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="FCHL Season Predictor",
    page_icon="🏒",
    layout="wide",
)

st.title("🏒 FCHL Season Predictor")
st.caption(
    "Projects remaining 2025-26 NHL season fantasy points for each FCHL team. "
    "Scoring: G=1, A=1, W=2, SO=3"
)

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

skater_stats = get_skater_stats()
goalie_stats = get_goalie_stats()
schedule_data = get_schedule()

# ---------------------------------------------------------------------------
# Session state — mutable roster & lookup
# ---------------------------------------------------------------------------

if "roster" not in st.session_state:
    st.session_state.roster = list(get_original_roster())  # mutable copy

if "player_lookup" not in st.session_state:
    with st.spinner("Building player name index…"):
        st.session_state.player_lookup = build_player_lookup(
            st.session_state.roster, skater_stats, goalie_stats
        )

# ---------------------------------------------------------------------------
# Sidebar — editable current points
# ---------------------------------------------------------------------------

st.sidebar.header("Current FCHL Points")
st.sidebar.caption("Update these to reflect your league's current standings.")

current_pts: dict[str, int] = {}
for team in sorted(FCHL_TEAMS):
    current_pts[team] = st.sidebar.number_input(
        label=team,
        value=DEFAULT_FCHL_POINTS.get(team, 0),
        step=1,
        min_value=0,
        key=f"sidebar_pts_{team}",
    )

st.sidebar.divider()
remaining_games = schedule_data["team_remaining"]
total_remaining = sum(remaining_games.values()) // 2  # each game counted twice
st.sidebar.metric("Remaining NHL Games", total_remaining)

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab1, tab2, tab3 = st.tabs(["📊 Standings", "👤 Player Projections", "🔧 Roster Builder"])

# ---------------------------------------------------------------------------
# Tab 1 — Standings
# ---------------------------------------------------------------------------

with tab1:
    projections = project_all_players(
        st.session_state.roster,
        st.session_state.player_lookup,
        skater_stats,
        goalie_stats,
        schedule_data,
    )
    standings = compute_standings(projections, current_pts)

    st.subheader("Projected Final Standings")
    st.caption("Current points + projected remaining fantasy points for each team.")

    rows = []
    for i, s in enumerate(standings):
        rows.append({
            "Rank": i + 1,
            "Team": s["fchl_team"],
            "Current Pts": s["current_pts"],
            "Proj Remaining": round(s["proj_remaining"], 1),
            "Proj Total": round(s["proj_total"], 1),
        })

    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        use_container_width=True,
        column_config={
            "Rank": st.column_config.NumberColumn(width="small"),
            "Proj Total": st.column_config.NumberColumn(
                help="Current Pts + Projected Remaining"
            ),
        },
    )

    # Per-team breakdown
    st.subheader("Team Breakdown")
    selected_team = st.selectbox(
        "Select team to inspect", sorted(FCHL_TEAMS), key="standings_team_select"
    )
    team_projs = [p for p in projections if p["fchl_team"] == selected_team]

    if team_projs:
        df_team = pd.DataFrame(team_projs)
        skater_df = df_team[df_team["position"] != "G"][
            ["name", "position", "nhl_team", "proj_goals", "proj_assists", "proj_pts", "found_in_stats"]
        ].copy()
        goalie_df = df_team[df_team["position"] == "G"][
            ["name", "nhl_team", "proj_wins", "proj_shutouts", "proj_pts", "found_in_stats"]
        ].copy()

        for col in ["proj_goals", "proj_assists", "proj_pts"]:
            skater_df[col] = skater_df[col].round(1)
        for col in ["proj_wins", "proj_shutouts", "proj_pts"]:
            goalie_df[col] = goalie_df[col].round(1)

        skater_df = skater_df.rename(columns={
            "name": "Player", "position": "Pos", "nhl_team": "NHL Team",
            "proj_goals": "Proj G", "proj_assists": "Proj A",
            "proj_pts": "Proj Pts", "found_in_stats": "Found",
        })
        goalie_df = goalie_df.rename(columns={
            "name": "Player", "nhl_team": "NHL Team",
            "proj_wins": "Proj W", "proj_shutouts": "Proj SO",
            "proj_pts": "Proj Pts", "found_in_stats": "Found",
        })

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Skaters**")
            st.dataframe(
                skater_df.sort_values("Proj Pts", ascending=False),
                hide_index=True, use_container_width=True,
            )
        with col2:
            st.markdown("**Goalies**")
            st.dataframe(
                goalie_df.sort_values("Proj Pts", ascending=False),
                hide_index=True, use_container_width=True,
            )

# ---------------------------------------------------------------------------
# Tab 2 — Player Projections
# ---------------------------------------------------------------------------

with tab2:
    projections2 = project_all_players(
        st.session_state.roster,
        st.session_state.player_lookup,
        skater_stats,
        goalie_stats,
        schedule_data,
    )

    st.subheader("All Player Projections")

    # Filters
    fcol1, fcol2 = st.columns(2)
    with fcol1:
        team_filter = st.selectbox(
            "Filter by FCHL Team", ["All"] + sorted(FCHL_TEAMS), key="proj_team_filter"
        )
    with fcol2:
        pos_filter = st.selectbox(
            "Filter by Position", ["All", "F", "D", "G"], key="proj_pos_filter"
        )

    df_all = pd.DataFrame(projections2)

    if team_filter != "All":
        df_all = df_all[df_all["fchl_team"] == team_filter]
    if pos_filter != "All":
        df_all = df_all[df_all["position"] == pos_filter]

    # Round and rename
    for col in ["proj_goals", "proj_assists", "proj_wins", "proj_shutouts", "proj_pts"]:
        df_all[col] = df_all[col].round(1)

    display = df_all[[
        "name", "position", "fchl_team", "nhl_team",
        "proj_goals", "proj_assists", "proj_wins", "proj_shutouts", "proj_pts",
        "found_in_stats",
    ]].rename(columns={
        "name": "Player",
        "position": "Pos",
        "fchl_team": "FCHL Team",
        "nhl_team": "NHL Team",
        "proj_goals": "Proj G",
        "proj_assists": "Proj A",
        "proj_wins": "Proj W",
        "proj_shutouts": "Proj SO",
        "proj_pts": "Proj Pts",
        "found_in_stats": "Found",
    })

    st.dataframe(
        display.sort_values("Proj Pts", ascending=False),
        hide_index=True,
        use_container_width=True,
        column_config={
            "Found": st.column_config.CheckboxColumn(help="Player found in stats CSV"),
            "Proj Pts": st.column_config.NumberColumn(help="Projected remaining fantasy points"),
        },
    )

    # Warn about unmatched players
    unmatched = [p for p in projections2 if not p["found_in_stats"]]
    if unmatched:
        names = ", ".join(p["name"] for p in unmatched)
        st.warning(f"⚠️ {len(unmatched)} player(s) not found in stats (will project 0 pts): {names}")

    # Remaining games reference
    with st.expander("Remaining games per NHL team"):
        rg = schedule_data["team_remaining"]
        rg_df = pd.DataFrame(
            sorted(rg.items(), key=lambda x: -x[1]),
            columns=["NHL Team", "Remaining Games"],
        )
        st.dataframe(rg_df, hide_index=True, use_container_width=True)

# ---------------------------------------------------------------------------
# Tab 3 — Roster Builder
# ---------------------------------------------------------------------------

with tab3:
    st.subheader("Roster Builder")
    st.caption(
        "Modify rosters to simulate trade scenarios or lineup changes. "
        "Changes here update the Standings and Player Projections tabs."
    )

    # --- Add a player ---
    with st.expander("➕ Add a player to a roster", expanded=False):
        all_stat_players = sorted(
            set(list(skater_stats.keys()) + list(goalie_stats.keys()))
        )
        current_names = {p["name"] for p in st.session_state.roster}
        # Also include fuzzy-matched names so we don't show already-rostered players
        matched_names = set(v for v in st.session_state.player_lookup.values() if v)
        available = sorted(set(all_stat_players) - matched_names)

        acol1, acol2, acol3 = st.columns(3)
        with acol1:
            add_name = st.selectbox("Player", available, key="add_player_name")
        with acol2:
            add_pos = st.selectbox("Position", ["F", "D", "G"], key="add_player_pos")
        with acol3:
            add_team = st.selectbox("FCHL Team", sorted(FCHL_TEAMS), key="add_player_team")

        if st.button("Add Player", key="btn_add_player"):
            new_player = {
                "raw": f"{add_pos} {add_name} (added)",
                "name": add_name,
                "position": add_pos,
                "fchl_team": add_team,
            }
            st.session_state.roster.append(new_player)
            # Add to lookup — exact match since name came from the stats dict
            st.session_state.player_lookup[add_name] = add_name
            st.rerun()

    # --- Edit existing team ---
    st.markdown("#### Edit Team Roster")

    edit_team = st.selectbox(
        "Select team to edit", sorted(FCHL_TEAMS), key="edit_team_select"
    )

    team_players = [p for p in st.session_state.roster if p["fchl_team"] == edit_team]

    if not team_players:
        st.info("No players on this team.")
    else:
        # Group by position for display
        for pos_label, pos_code in [("Forwards", "F"), ("Defensemen", "D"), ("Goalies", "G")]:
            pos_players = [p for p in team_players if p["position"] == pos_code]
            if not pos_players:
                continue
            st.markdown(f"**{pos_label}**")
            for player in pos_players:
                col1, col2, col3 = st.columns([3, 2, 1])
                with col1:
                    st.write(player["name"])
                with col2:
                    team_opts = sorted(FCHL_TEAMS)
                    cur_idx = team_opts.index(player["fchl_team"])
                    new_team = st.selectbox(
                        "Move to",
                        team_opts,
                        index=cur_idx,
                        key=f"move_{player['name']}_{player['fchl_team']}",
                        label_visibility="collapsed",
                    )
                    if new_team != player["fchl_team"]:
                        for p in st.session_state.roster:
                            if p["name"] == player["name"] and p["fchl_team"] == player["fchl_team"]:
                                p["fchl_team"] = new_team
                                break
                        st.rerun()
                with col3:
                    if st.button("Remove", key=f"remove_{player['name']}_{player['fchl_team']}"):
                        st.session_state.roster = [
                            p for p in st.session_state.roster
                            if not (p["name"] == player["name"] and p["fchl_team"] == player["fchl_team"])
                        ]
                        st.rerun()

    st.divider()

    # --- Projected standings with current (possibly modified) roster ---
    st.markdown("#### Projected Standings with Current Rosters")
    proj3 = project_all_players(
        st.session_state.roster,
        st.session_state.player_lookup,
        skater_stats,
        goalie_stats,
        schedule_data,
    )
    standings3 = compute_standings(proj3, current_pts)
    rows3 = []
    for i, s in enumerate(standings3):
        rows3.append({
            "Rank": i + 1,
            "Team": s["fchl_team"],
            "Current Pts": s["current_pts"],
            "Proj Remaining": round(s["proj_remaining"], 1),
            "Proj Total": round(s["proj_total"], 1),
        })
    st.dataframe(pd.DataFrame(rows3), hide_index=True, use_container_width=True)

    st.divider()
    if st.button("🔄 Reset All Rosters to Original"):
        del st.session_state.roster
        del st.session_state.player_lookup
        st.rerun()
