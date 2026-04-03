"""
bullpen_monitor.py
Daily bullpen workload tracking and availability analysis.
"""

import pandas as pd
from src.database import get_connection


def bullpen_availability(team: str, as_of_date: str = None) -> pd.DataFrame:
    """
    Shows bullpen availability for a team based on recent workload.
    Flags pitchers who may be unavailable due to recent usage.

    Args:
        team:        Team abbreviation e.g. 'NYY', 'CHC', 'LAD'
        as_of_date:  Date string 'YYYY-MM-DD', defaults to
                     most recent date in database

    Example:
        bullpen_availability('NYY', '2024-04-15')
    """
    con = get_connection()

    date_filter = (
        f"= '{as_of_date}'"
        if as_of_date
        else "= (SELECT MAX(game_date) FROM pitches)"
    )

    result = con.execute(f"""
        WITH recent_usage AS (
            SELECT
                pitcher,
                game_date,
                COUNT(*)    as pitches,
                1           as appearance
            FROM pitches
            WHERE home_team = '{team}'
               OR away_team = '{team}'
            GROUP BY pitcher, game_date
        ),
        workload_summary AS (
            SELECT
                pitcher,
                MAX(game_date)                              as last_used,
                SUM(appearance)                             as appearances_7d,
                SUM(pitches)                                as pitches_7d,
                SUM(CASE
                    WHEN game_date >= (
                        SELECT MAX(game_date) FROM pitches
                    ) - INTERVAL '2 days'
                    THEN appearance ELSE 0
                END)                                        as apps_last_3d,
                SUM(CASE
                    WHEN game_date >= (
                        SELECT MAX(game_date) FROM pitches
                    ) - INTERVAL '2 days'
                    THEN pitches ELSE 0
                END)                                        as pitches_last_3d
            FROM recent_usage
            GROUP BY pitcher
        )
        SELECT
            w.pitcher,
            w.last_used,
            w.appearances_7d,
            w.pitches_7d,
            w.apps_last_3d,
            w.pitches_last_3d,
            CASE
                WHEN w.apps_last_3d >= 3
                    THEN 'UNAVAILABLE - 3 straight days'
                WHEN w.pitches_last_3d >= 60
                    THEN 'UNAVAILABLE - High pitch load'
                WHEN w.apps_last_3d = 2
                    THEN 'LIMITED - Use with caution'
                WHEN w.last_used = (
                    SELECT MAX(game_date) FROM pitches
                )   THEN 'USED YESTERDAY - Monitor'
                ELSE 'AVAILABLE'
            END                                             as availability_status
        FROM workload_summary w
        ORDER BY w.apps_last_3d DESC, w.pitches_7d DESC
    """).df()

    con.close()
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
    return result


if __name__ == "__main__":
    print("Bullpen monitor module ready")
    print("Available functions:")
    print("  bullpen_availability(team, as_of_date)")
    print("  velocity_trend(pitcher_id)")
    print("  inning_by_inning_velo(pitcher_id, game_pk)")
    print("  consecutive_days_used(team)")