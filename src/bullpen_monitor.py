"""
bullpen_monitor.py
Daily bullpen workload tracking and availability analysis.
"""

import pandas as pd
from src.database import get_connection
from src.player_lookup import enrich_with_names

def bullpen_availability(team: str, as_of_date: str = None) -> pd.DataFrame:
    """
    Shows bullpen availability for a team based on recent workload.
    Correctly filters to only pitchers who threw for that team
    and calculates rolling 7 day and 3 day windows properly.

    Args:
        team:        Team abbreviation e.g. 'NYY', 'CHC', 'LAD'
        as_of_date:  Date string 'YYYY-MM-DD', defaults to
                     most recent date in database

    Example:
        bullpen_availability('NYY', '2026-04-03')
    """
    con = get_connection()

    result = con.execute(f"""
        WITH

        -- Step 1: Find the most recent date in the database
        max_date AS (
            SELECT MAX(game_date) as latest
            FROM pitches
        ),

        -- Step 2: Get the reference date
        -- Uses as_of_date if provided, otherwise latest in DB
        ref_date AS (
            SELECT
                CASE
                    WHEN '{as_of_date}' = 'None'
                    THEN (SELECT latest FROM max_date)
                    ELSE CAST('{as_of_date}' AS DATE)
                END as ref
        ),

        -- Step 3: Identify which team each pitcher threw FOR
        -- A pitcher throws for the HOME team when pitching in
        -- the top half of the inning (facing away team batters)
        -- A pitcher throws for the AWAY team when pitching in
        -- the bottom half (facing home team batters)
        pitcher_team AS (
            SELECT DISTINCT
                pitcher,
                game_date,
                game_pk,
                CASE
                    WHEN inning_topbot = 'Top'
                    THEN home_team
                    ELSE away_team
                END as pitching_team,
                COUNT(*) as pitches_in_game
            FROM pitches
            GROUP BY
                pitcher,
                game_date,
                game_pk,
                CASE
                    WHEN inning_topbot = 'Top'
                    THEN home_team
                    ELSE away_team
                END
        ),

        -- Step 4: Filter to only pitchers who threw FOR our team
        team_pitchers AS (
            SELECT
                pitcher,
                game_date,
                game_pk,
                pitches_in_game
            FROM pitcher_team
            WHERE pitching_team = '{team}'
        ),

        -- Step 5: Calculate 7 day rolling window stats
        rolling_7d AS (
            SELECT
                pitcher,
                COUNT(DISTINCT game_date)   as appearances_7d,
                SUM(pitches_in_game)        as pitches_7d
            FROM team_pitchers
            WHERE game_date >= (
                SELECT ref - INTERVAL '6 days' FROM ref_date
            )
            AND game_date <= (SELECT ref FROM ref_date)
            GROUP BY pitcher
        ),

        -- Step 6: Calculate 3 day rolling window stats
        rolling_3d AS (
            SELECT
                pitcher,
                COUNT(DISTINCT game_date)   as apps_last_3d,
                SUM(pitches_in_game)        as pitches_last_3d
            FROM team_pitchers
            WHERE game_date >= (
                SELECT ref - INTERVAL '2 days' FROM ref_date
            )
            AND game_date <= (SELECT ref FROM ref_date)
            GROUP BY pitcher
        ),

        -- Step 7: Get last appearance date for each pitcher
        last_used AS (
            SELECT
                pitcher,
                MAX(game_date) as last_appearance
            FROM team_pitchers
            GROUP BY pitcher
        )

        -- Step 8: Combine everything and apply availability logic
        SELECT
            r7.pitcher,
            r7.appearances_7d,
            r7.pitches_7d,
            COALESCE(r3.apps_last_3d, 0)        as apps_last_3d,
            COALESCE(r3.pitches_last_3d, 0)     as pitches_last_3d,
            lu.last_appearance,
            (SELECT ref FROM ref_date)           as as_of_date,

            -- Availability logic
            CASE
                WHEN COALESCE(r3.apps_last_3d, 0) >= 3
                    THEN 'UNAVAILABLE - 3 consecutive days'
                WHEN COALESCE(r3.pitches_last_3d, 0) >= 60
                    THEN 'UNAVAILABLE - High recent pitch load'
                WHEN COALESCE(r3.apps_last_3d, 0) = 2
                    THEN 'LIMITED - Used 2 of last 3 days'
                WHEN lu.last_appearance = (SELECT ref FROM ref_date)
                    THEN 'USED TODAY - Monitor'
                WHEN lu.last_appearance = (SELECT ref FROM ref_date) - 1
                    THEN 'USED YESTERDAY - Monitor'
                ELSE 'AVAILABLE'
            END                                  as availability_status

        FROM rolling_7d r7
        LEFT JOIN rolling_3d r3
            ON r7.pitcher = r3.pitcher
        LEFT JOIN last_used lu
            ON r7.pitcher = lu.pitcher
        ORDER BY
            apps_last_3d DESC,
            pitches_last_3d DESC

    """).df()

    con.close()

    # Add player names
    result = enrich_with_names(result, pitcher_col='pitcher')
    return result


def velocity_trend(pitcher_id: int) -> pd.DataFrame:
    """
    Tracks a pitcher's velocity across outings.
    Velocity drops can signal fatigue or injury.

    Example:
        velocity_trend(594798)
    """
    con = get_connection()
    result = con.execute(f"""
        SELECT
            game_date,
            pitch_name,
            COUNT(*)                        as pitches,
            ROUND(AVG(release_speed), 1)    as avg_velo,
            ROUND(MAX(release_speed), 1)    as peak_velo,
            ROUND(MIN(release_speed), 1)    as min_velo,
            ROUND(AVG(release_spin_rate))   as avg_spin

        FROM pitches
        WHERE pitcher = {pitcher_id}
          AND pitch_type IS NOT NULL
          AND release_speed IS NOT NULL
        GROUP BY game_date, pitch_name
        ORDER BY game_date ASC, pitches DESC
    """).df()
    con.close()
    result = enrich_with_names(result, pitcher_col='pitcher')
    return result


def inning_by_inning_velo(pitcher_id: int, game_pk: int) -> pd.DataFrame:
    """
    Tracks velocity inning by inning within a single start.
    Shows how stuff changes as pitch count climbs.

    Example:
        inning_by_inning_velo(594798, 745528)
    """
    con = get_connection()
    result = con.execute(f"""
        SELECT
            inning,
            pitch_name,
            COUNT(*)                        as pitches,
            ROUND(AVG(release_speed), 1)    as avg_velo,
            ROUND(AVG(release_spin_rate))   as avg_spin,
            ROUND(
                COUNT(CASE WHEN description = 'swinging_strike'
                      THEN 1 END) * 100.0 / COUNT(*), 1
            )                               as whiff_pct

        FROM pitches
        WHERE pitcher = {pitcher_id}
          AND game_pk  = {game_pk}
          AND pitch_type IS NOT NULL
        GROUP BY inning, pitch_name
        ORDER BY inning ASC, pitches DESC
    """).df()
    con.close()
    result = enrich_with_names(result, pitcher_col='pitcher')
    return result


def consecutive_days_used(team: str) -> pd.DataFrame:
    """
    Shows how many consecutive days each pitcher has been used.
    Key metric for bullpen management decisions.

    Example:
        consecutive_days_used('NYY')
    """
    con = get_connection()
    result = con.execute(f"""
        WITH pitcher_dates AS (
            SELECT DISTINCT
                pitcher,
                game_date
            FROM pitches
            WHERE home_team = '{team}'
               OR away_team = '{team}'
            ORDER BY pitcher, game_date
        )
        SELECT
            pitcher,
            COUNT(DISTINCT game_date)       as total_appearances,
            MAX(game_date)                  as last_appearance,
            MIN(game_date)                  as first_appearance
        FROM pitcher_dates
        GROUP BY pitcher
        ORDER BY total_appearances DESC
    """).df()
    con.close()
    result = enrich_with_names(result, pitcher_col='pitcher')
    return result


if __name__ == "__main__":
    print("Bullpen monitor module ready")
    print("Available functions:")
    print("  bullpen_availability(team, as_of_date)")
    print("  velocity_trend(pitcher_id)")
    print("  inning_by_inning_velo(pitcher_id, game_pk)")
    print("  consecutive_days_used(team)")