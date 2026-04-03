"""
matchup_queries.py
Core pitcher/batter matchup and tendency analysis queries.
"""

import pandas as pd
from src.database import get_connection


def pitcher_vs_batter(pitcher_id: int, batter_id: int) -> pd.DataFrame:
    """
    Full matchup breakdown between a specific pitcher and batter.
    Shows pitch mix, velocity, whiff rate, and outcome tendencies.

    Example:
        pitcher_vs_batter(594798, 592450)
    """
    con = get_connection()
    result = con.execute(f"""
        SELECT
            pitch_name,
            pitch_type,
            COUNT(*)                                        as pitches,
            ROUND(AVG(release_speed), 1)                   as avg_velo,
            ROUND(MIN(release_speed), 1)                   as min_velo,
            ROUND(MAX(release_speed), 1)                   as max_velo,
            ROUND(
                COUNT(CASE WHEN description = 'swinging_strike'
                      THEN 1 END) * 100.0 / COUNT(*), 1
            )                                               as whiff_pct,
            ROUND(
                COUNT(CASE WHEN zone BETWEEN 1 AND 9
                      THEN 1 END) * 100.0 / COUNT(*), 1
            )                                               as zone_pct,
            ROUND(
                COUNT(CASE WHEN launch_speed >= 95
                      THEN 1 END) * 100.0 /
                NULLIF(COUNT(CASE WHEN launch_speed IS NOT NULL
                      THEN 1 END), 0), 1
            )                                               as hard_hit_pct,
            ROUND(AVG(estimated_woba_using_speedangle), 3)  as xwoba

        FROM pitches
        WHERE pitcher = {pitcher_id}
          AND batter  = {batter_id}
          AND pitch_type IS NOT NULL
        GROUP BY pitch_name, pitch_type
        ORDER BY pitches DESC
    """).df()
    con.close()
    return result


def pitcher_tendencies(pitcher_id: int) -> pd.DataFrame:
    """
    Full pitch tendency profile for a pitcher.
    Breaks down pitch mix, location, and outcomes by count.

    Example:
        pitcher_tendencies(594798)
    """
    con = get_connection()
    result = con.execute(f"""
        SELECT
            balls,
            strikes,
            pitch_name,
            COUNT(*)                                        as pitches,
            ROUND(
                COUNT(*) * 100.0 /
                SUM(COUNT(*)) OVER (PARTITION BY balls, strikes), 1
            )                                               as pct_in_count,
            ROUND(AVG(release_speed), 1)                   as avg_velo,
            ROUND(AVG(release_spin_rate), 0)               as avg_spin,
            ROUND(
                COUNT(CASE WHEN description = 'swinging_strike'
                      THEN 1 END) * 100.0 / COUNT(*), 1
            )                                               as whiff_pct,
            ROUND(AVG(plate_x), 2)                         as avg_plate_x,
            ROUND(AVG(plate_z), 2)                         as avg_plate_z

        FROM pitches
        WHERE pitcher = {pitcher_id}
          AND pitch_type IS NOT NULL
        GROUP BY balls, strikes, pitch_name
        ORDER BY balls, strikes, pitches DESC
    """).df()
    con.close()
    return result


def batter_tendencies(batter_id: int) -> pd.DataFrame:
    """
    Full batting tendency profile.
    Shows performance against each pitch type.

    Example:
        batter_tendencies(592450)
    """
    con = get_connection()
    result = con.execute(f"""
        SELECT
            pitch_name,
            COUNT(*)                                        as pitches_seen,
            ROUND(
                COUNT(CASE WHEN description LIKE '%swinging%'
                      THEN 1 END) * 100.0 / COUNT(*), 1
            )                                               as swing_pct,
            ROUND(
                COUNT(CASE WHEN description = 'swinging_strike'
                      THEN 1 END) * 100.0 /
                NULLIF(COUNT(CASE WHEN description LIKE '%swinging%'
                      THEN 1 END), 0), 1
            )                                               as miss_pct,
            ROUND(AVG(CASE WHEN launch_speed IS NOT NULL
                  THEN launch_speed END), 1)                as avg_exit_velo,
            ROUND(AVG(CASE WHEN launch_angle IS NOT NULL
                  THEN launch_angle END), 1)                as avg_launch_angle,
            ROUND(
                COUNT(CASE WHEN launch_speed >= 95
                      THEN 1 END) * 100.0 /
                NULLIF(COUNT(CASE WHEN launch_speed IS NOT NULL
                      THEN 1 END), 0), 1
            )                                               as hard_hit_pct,
            ROUND(AVG(estimated_woba_using_speedangle), 3)  as xwoba,
            ROUND(AVG(estimated_ba_using_speedangle), 3)    as xba

        FROM pitches
        WHERE batter = {batter_id}
          AND pitch_type IS NOT NULL
        GROUP BY pitch_name
        ORDER BY pitches_seen DESC
    """).df()
    con.close()
    return result


def pitch_mix_by_count(pitcher_id: int) -> pd.DataFrame:
    """
    Shows how a pitcher's pitch selection changes by count.
    Critical for understanding sequencing strategy.

    Example:
        pitch_mix_by_count(594798)
    """
    con = get_connection()
    result = con.execute(f"""
        SELECT
            CONCAT(balls, '-', strikes)                     as count,
            pitch_name,
            COUNT(*)                                        as pitches,
            ROUND(
                COUNT(*) * 100.0 /
                SUM(COUNT(*)) OVER (
                    PARTITION BY balls, strikes
                ), 1
            )                                               as usage_pct,
            ROUND(AVG(release_speed), 1)                   as avg_velo,
            ROUND(
                COUNT(CASE WHEN description = 'swinging_strike'
                      THEN 1 END) * 100.0 / COUNT(*), 1
            )                                               as whiff_pct

        FROM pitches
        WHERE pitcher = {pitcher_id}
          AND pitch_type IS NOT NULL
        GROUP BY balls, strikes, pitch_name
        ORDER BY balls, strikes, pitches DESC
    """).df()
    con.close()
    return result


def platoon_splits(pitcher_id: int) -> pd.DataFrame:
    """
    Left vs right handedness splits for a pitcher.
    Shows which pitch types are most effective against each side.

    Example:
        platoon_splits(594798)
    """
    con = get_connection()
    result = con.execute(f"""
        SELECT
            pitch_name,
            COUNT(*)                                        as pitches,
            ROUND(AVG(release_speed), 1)                   as avg_velo,
            ROUND(
                COUNT(CASE WHEN description = 'swinging_strike'
                      THEN 1 END) * 100.0 / COUNT(*), 1
            )                                               as whiff_pct,
            ROUND(AVG(estimated_woba_using_speedangle), 3)  as xwoba

        FROM pitches
        WHERE pitcher = {pitcher_id}
          AND pitch_type IS NOT NULL
        GROUP BY pitch_name
        ORDER BY pitches DESC
    """).df()
    con.close()
    return result


if __name__ == "__main__":
    print("Matchup query module ready")
    print("Available functions:")
    print("  pitcher_vs_batter(pitcher_id, batter_id)")
    print("  pitcher_tendencies(pitcher_id)")
    print("  batter_tendencies(batter_id)")
    print("  pitch_mix_by_count(pitcher_id)")
    print("  platoon_splits(pitcher_id)")
