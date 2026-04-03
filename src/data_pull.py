"""
data_pull.py
Handles all pybaseball data ingestion into DuckDB.
"""

import pybaseball as pb
import pandas as pd
from src.database import get_connection

pb.cache.enable()


def pull_statcast_range(start_date: str, end_date: str, save_raw: bool = True):
    """
    Pulls Statcast pitch-level data for a date range
    and loads it into the pitches table in DuckDB.

    Args:
        start_date: Format 'YYYY-MM-DD'
        end_date:   Format 'YYYY-MM-DD'
        save_raw:   Whether to save a CSV backup to data/raw/

    Example:
        pull_statcast_range('2024-04-01', '2024-04-30')
    """
    print(f"Pulling Statcast data: {start_date} to {end_date}")
    print("First run may take several minutes...")

    df = pb.statcast(start_dt=start_date, end_dt=end_date)

    print(f"Pulled {len(df):,} pitches successfully")

    if save_raw:
        filename = f"data/raw/statcast_{start_date}_{end_date}.csv"
        df.to_csv(filename, index=False)
        print(f"Raw data saved to {filename}")

    con = get_connection()

    core_columns = [
        'game_pk', 'game_date', 'pitcher', 'batter',
        'home_team', 'away_team', 'inning', 'inning_topbot',
        'outs_when_up', 'balls', 'strikes',
        'on_1b', 'on_2b', 'on_3b',
        'pitch_type', 'pitch_name', 'release_speed',
        'release_spin_rate', 'pfx_x', 'pfx_z',
        'plate_x', 'plate_z', 'zone',
        'description', 'type', 'bb_type',
        'launch_speed', 'launch_angle', 'hit_distance_sc',
        'hc_x', 'hc_y',
        'estimated_ba_using_speedangle',
        'estimated_woba_using_speedangle',
        'woba_value', 'woba_denom',
        'events', 'des',
        'effective_speed', 'release_extension',
        'release_pos_x', 'release_pos_z'
    ]

    available_columns = [c for c in core_columns if c in df.columns]
    df_clean = df[available_columns].copy()
    df_clean['game_date'] = pd.to_datetime(df_clean['game_date']).dt.date

    con.execute("""
        INSERT INTO pitches
        SELECT * FROM df_clean
        WHERE game_pk NOT IN (
            SELECT DISTINCT game_pk FROM pitches
        )
    """)

    row_count = con.execute("SELECT COUNT(*) FROM pitches").fetchone()[0]
    con.close()

    print(f"Data loaded into DuckDB successfully")
    print(f"Total pitches in database: {row_count:,}")

    return df_clean


def pull_player_lookup(last_name: str, first_name: str):
    """
    Looks up a player and saves them to the players table.

    Example:
        pull_player_lookup('degrom', 'jacob')
    """
    player = pb.playerid_lookup(last_name, first_name)

    if player.empty:
        print(f"No player found for {first_name} {last_name}")
        return None

    con = get_connection()

    for _, row in player.iterrows():
        con.execute("""
            INSERT OR REPLACE INTO players VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            row.get('key_mlbam'),
            row.get('name_last'),
            row.get('name_first'),
            row.get('key_bbref'),
            row.get('key_fangraphs'),
            row.get('mlb_played_first'),
            row.get('mlb_played_last')
        ])

    con.close()
    print(f"Player saved: {player[['name_first', 'name_last', 'key_mlbam']].to_string()}")
    return player


def build_bullpen_usage():
    """
    Aggregates pitch level data into the bullpen_usage table.
    Run after each Statcast pull to keep workload tracking current.
    """
    con = get_connection()
# Edit to show true innings pitched
    con.execute("""
        INSERT OR REPLACE INTO bullpen_usage
        SELECT
            pitcher,
            game_date,
            CASE
                WHEN home_team IS NOT NULL THEN home_team
                ELSE away_team
            END as team,
            COUNT(*) as pitches_thrown,
            COUNT(DISTINCT batter) as batters_faced,
            ROUND(COUNT(DISTINCT
                CONCAT(inning, inning_topbot)) / 3.0, 1) as innings_pitched,
            ROUND(AVG(release_speed), 1) as avg_velocity,
            game_pk
        FROM pitches
        GROUP BY pitcher, game_date, home_team, away_team, game_pk
    """)

    con.close()
    print("Bullpen usage table updated successfully")


if __name__ == "__main__":
    from src.database import initialize_database
    initialize_database()
    pull_statcast_range("2024-04-01", "2024-04-30")
    build_bullpen_usage()