"""
database.py
Handles all DuckDB connection and table creation logic.
"""

import duckdb
import os

DB_PATH = "data/baseball.db"


def get_connection():
    """Returns a DuckDB connection to the baseball database"""
    return duckdb.connect(DB_PATH)


def initialize_database():
    con = get_connection()

    con.execute("""
        CREATE TABLE IF NOT EXISTS pitches (
            game_pk             BIGINT,
            game_date           DATE,
            pitcher             INTEGER,
            batter              INTEGER,
            home_team           VARCHAR,
            away_team           VARCHAR,
            inning              INTEGER,
            inning_topbot       VARCHAR,
            outs_when_up        INTEGER,
            balls               INTEGER,
            strikes             INTEGER,
            on_1b               DOUBLE,
            on_2b               DOUBLE,
            on_3b               DOUBLE,
            pitch_type          VARCHAR,
            pitch_name          VARCHAR,
            release_speed       DOUBLE,
            release_spin_rate   DOUBLE,
            pfx_x               DOUBLE,
            pfx_z               DOUBLE,
            plate_x             DOUBLE,
            plate_z             DOUBLE,
            zone                DOUBLE,
            description         VARCHAR,
            type                VARCHAR,
            bb_type             VARCHAR,
            launch_speed        DOUBLE,
            launch_angle        DOUBLE,
            hit_distance_sc     DOUBLE,
            hc_x                DOUBLE,
            hc_y                DOUBLE,
            estimated_ba_using_speedangle   DOUBLE,
            estimated_woba_using_speedangle DOUBLE,
            woba_value          DOUBLE,
            woba_denom          DOUBLE,
            events              VARCHAR,
            des                 VARCHAR,
            effective_speed     DOUBLE,
            release_extension   DOUBLE,
            release_pos_x       DOUBLE,
            release_pos_z       DOUBLE
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS players (
            mlbam_id        INTEGER PRIMARY KEY,
            name_last       VARCHAR,
            name_first      VARCHAR,
            key_bbref       VARCHAR,
            key_fangraphs   INTEGER,
            mlb_played_first INTEGER,
            mlb_played_last  INTEGER
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS games (
            game_pk         BIGINT PRIMARY KEY,
            game_date       DATE,
            home_team       VARCHAR,
            away_team       VARCHAR,
            home_score      INTEGER,
            away_score      INTEGER,
            venue_name      VARCHAR,
            game_type       VARCHAR
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS bullpen_usage (
            pitcher         INTEGER,
            game_date       DATE,
            team            VARCHAR,
            pitches_thrown  INTEGER,
            batters_faced   INTEGER,
            innings_pitched DOUBLE,
            avg_velocity    DOUBLE,
            game_pk         BIGINT,
            PRIMARY KEY (pitcher, game_date)
        )
    """)

    con.close()
    print("Database initialized at:", DB_PATH)
    print("Tables created: pitches, players, games, bullpen_usage")


if __name__ == "__main__":
    initialize_database()