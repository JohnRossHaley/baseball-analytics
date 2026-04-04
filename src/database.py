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
    # ─────────────────────────────────────────
    # SCHEDULE AND RECORD TABLE
    # One row per game per team
    # ─────────────────────────────────────────
    con.execute("""
            CREATE TABLE IF NOT EXISTS schedule (
                season          INTEGER,
                team            VARCHAR,
                date            VARCHAR,
                home_away       VARCHAR,
                opponent        VARCHAR,
                result          VARCHAR,
                runs_scored     INTEGER,
                runs_allowed    INTEGER,
                innings         INTEGER,
                win_loss_record VARCHAR,
                rank            INTEGER,
                games_back      DOUBLE,
                win             INTEGER,
                loss            INTEGER,
                save_op         VARCHAR,
                time            VARCHAR,
                day_night       VARCHAR,
                attendance      INTEGER,
                streak          VARCHAR,
                PRIMARY KEY (season, team, date, opponent)
            )
        """)

    # ─────────────────────────────────────────
    # STANDINGS TABLE
    # Division standings by season
    # ─────────────────────────────────────────
    con.execute("""
            CREATE TABLE IF NOT EXISTS standings (
                season          INTEGER,
                team            VARCHAR,
                wins            INTEGER,
                losses          INTEGER,
                win_pct         DOUBLE,
                games_back      DOUBLE,
                division        VARCHAR,
                PRIMARY KEY (season, team)
            )
        """)

    # ─────────────────────────────────────────
    # TEAM BATTING TABLE
    # Season level team batting stats
    # ─────────────────────────────────────────
    con.execute("""
            CREATE TABLE IF NOT EXISTS team_batting (
                season          INTEGER,
                team            VARCHAR,
                games           INTEGER,
                pa              INTEGER,
                ab              INTEGER,
                hits            INTEGER,
                doubles         INTEGER,
                triples         INTEGER,
                home_runs       INTEGER,
                rbi             INTEGER,
                walks           INTEGER,
                strikeouts      INTEGER,
                batting_avg     DOUBLE,
                obp             DOUBLE,
                slg             DOUBLE,
                ops             DOUBLE,
                woba            DOUBLE,
                wrc_plus        DOUBLE,
                war             DOUBLE,
                PRIMARY KEY (season, team)
            )
        """)

    # ─────────────────────────────────────────
    # TEAM PITCHING TABLE
    # Season level team pitching stats
    # ─────────────────────────────────────────
    con.execute("""
            CREATE TABLE IF NOT EXISTS team_pitching (
                season          INTEGER,
                team            VARCHAR,
                wins            INTEGER,
                losses          INTEGER,
                era             DOUBLE,
                games           INTEGER,
                saves           INTEGER,
                innings_pitched DOUBLE,
                hits_allowed    INTEGER,
                runs_allowed    INTEGER,
                home_runs       INTEGER,
                walks           INTEGER,
                strikeouts      INTEGER,
                whip            DOUBLE,
                fip             DOUBLE,
                k_per_9         DOUBLE,
                bb_per_9        DOUBLE,
                hr_per_9        DOUBLE,
                war             DOUBLE,
                PRIMARY KEY (season, team)
            )
        """)

    # ─────────────────────────────────────────
    # PITCHING LEADERBOARD TABLE
    # FanGraphs season leaderboard - individual pitchers
    # ─────────────────────────────────────────
    con.execute("""
            CREATE TABLE IF NOT EXISTS pitching_leaderboard (
                season          INTEGER,
                player_id       INTEGER,
                name            VARCHAR,
                team            VARCHAR,
                wins            INTEGER,
                losses          INTEGER,
                era             DOUBLE,
                games           INTEGER,
                gs              INTEGER,
                innings_pitched DOUBLE,
                strikeouts      INTEGER,
                walks           INTEGER,
                home_runs       INTEGER,
                whip            DOUBLE,
                fip             DOUBLE,
                xfip            DOUBLE,
                k_per_9         DOUBLE,
                bb_per_9        DOUBLE,
                k_pct           DOUBLE,
                bb_pct          DOUBLE,
                lob_pct         DOUBLE,
                gb_pct          DOUBLE,
                hr_per_fb       DOUBLE,
                babip           DOUBLE,
                war             DOUBLE,
                PRIMARY KEY (season, player_id)
            )
        """)

    # ─────────────────────────────────────────
    # BATTING LEADERBOARD TABLE
    # FanGraphs season leaderboard - individual batters
    # ─────────────────────────────────────────
    con.execute("""
            CREATE TABLE IF NOT EXISTS batting_leaderboard (
                season          INTEGER,
                player_id       INTEGER,
                name            VARCHAR,
                team            VARCHAR,
                games           INTEGER,
                pa              INTEGER,
                ab              INTEGER,
                hits            INTEGER,
                home_runs       INTEGER,
                rbi             INTEGER,
                stolen_bases    INTEGER,
                batting_avg     DOUBLE,
                obp             DOUBLE,
                slg             DOUBLE,
                ops             DOUBLE,
                woba            DOUBLE,
                wrc_plus        DOUBLE,
                babip           DOUBLE,
                k_pct           DOUBLE,
                bb_pct          DOUBLE,
                hard_hit_pct    DOUBLE,
                avg_exit_velo   DOUBLE,
                barrel_pct      DOUBLE,
                war             DOUBLE,
                PRIMARY KEY (season, player_id)
            )
        """)
    con.close()
    print("Database initialized at:", DB_PATH)
    print("Tables created: pitches, players, games, bullpen_usage")


if __name__ == "__main__":
    initialize_database()