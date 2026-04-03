"""
metrics.py
SABR and Statcast metric calculations.
These functions calculate advanced stats from raw pitch data.
"""

import pandas as pd
from src.database import get_connection


def calculate_fip(pitcher_id: int) -> pd.DataFrame:
    """
    Calculates FIP - Fielding Independent Pitching.
    FIP measures what a pitcher's ERA should look like
    based only on outcomes they control directly:
    strikeouts, walks, hit batters, and home runs.

    FIP Formula: ((13*HR) + (3*(BB+HBP)) - (2*K)) / IP + FIP_constant
    FIP constant is typically around 3.10 and normalizes FIP to ERA scale.

    Lower FIP = better pitcher performance independent of defense.

    Example:
        calculate_fip(594798)
    """
    con = get_connection()
    result = con.execute(f"""
        SELECT
            pitcher,
            game_date,

            -- Counting stats needed for FIP
            COUNT(CASE WHEN events = 'strikeout'
                  THEN 1 END)                           as strikeouts,
            COUNT(CASE WHEN events IN ('walk')
                  THEN 1 END)                           as walks,
            COUNT(CASE WHEN events = 'hit_by_pitch'
                  THEN 1 END)                           as hbp,
            COUNT(CASE WHEN events = 'home_run'
                  THEN 1 END)                           as home_runs,

            -- Estimated innings pitched via outs
            ROUND(
                COUNT(CASE WHEN events IN (
                    'strikeout', 'field_out', 'force_out',
                    'grounded_into_double_play', 'sac_fly',
                    'sac_bunt', 'fielders_choice_out'
                ) THEN 1 END) / 3.0, 1
            )                                           as innings_pitched,

            -- FIP calculation with 3.10 constant
            ROUND(
                (
                    (13 * COUNT(CASE WHEN events = 'home_run' THEN 1 END)) +
                    (3  * COUNT(CASE WHEN events IN ('walk', 'hit_by_pitch') THEN 1 END)) -
                    (2  * COUNT(CASE WHEN events = 'strikeout' THEN 1 END))
                ) /
                NULLIF(
                    COUNT(CASE WHEN events IN (
                        'strikeout', 'field_out', 'force_out',
                        'grounded_into_double_play', 'sac_fly',
                        'sac_bunt', 'fielders_choice_out'
                    ) THEN 1 END) / 3.0
                , 0)
                + 3.10
            , 2)                                        as fip

        FROM pitches
        WHERE pitcher = {pitcher_id}
        GROUP BY pitcher, game_date
        ORDER BY game_date ASC
    """).df()
    con.close()
    return result


def calculate_whip(pitcher_id: int) -> pd.DataFrame:
    """
    Calculates WHIP - Walks plus Hits per Inning Pitched.
    One of the most commonly used pitching efficiency metrics.
    Lower WHIP = fewer baserunners allowed per inning.

    Example:
        calculate_whip(594798)
    """
    con = get_connection()
    result = con.execute(f"""
        SELECT
            pitcher,
            game_date,
            COUNT(CASE WHEN events IN ('single', 'double',
                  'triple', 'home_run')
                  THEN 1 END)                           as hits,
            COUNT(CASE WHEN events = 'walk'
                  THEN 1 END)                           as walks,
            ROUND(
                COUNT(CASE WHEN events IN (
                    'strikeout', 'field_out', 'force_out',
                    'grounded_into_double_play', 'sac_fly',
                    'sac_bunt', 'fielders_choice_out'
                ) THEN 1 END) / 3.0, 1
            )                                           as innings_pitched,
            ROUND(
                (
                    COUNT(CASE WHEN events IN ('single', 'double',
                          'triple', 'home_run') THEN 1 END) +
                    COUNT(CASE WHEN events = 'walk' THEN 1 END)
                ) /
                NULLIF(
                    COUNT(CASE WHEN events IN (
                        'strikeout', 'field_out', 'force_out',
                        'grounded_into_double_play', 'sac_fly',
                        'sac_bunt', 'fielders_choice_out'
                    ) THEN 1 END) / 3.0
                , 0)
            , 3)                                        as whip

        FROM pitches
        WHERE pitcher = {pitcher_id}
        GROUP BY pitcher, game_date
        ORDER BY game_date ASC
    """).df()
    con.close()
    return result


def calculate_k_bb(pitcher_id: int) -> pd.DataFrame:
    """
    Calculates K/BB ratio - Strikeouts to Walks ratio.
    Measures a pitcher's command and dominance together.
    Higher K/BB = better command and swing and miss stuff.
    Elite starters typically have K/BB above 3.0.

    Example:
        calculate_k_bb(594798)
    """
    con = get_connection()
    result = con.execute(f"""
        SELECT
            pitcher,
            COUNT(CASE WHEN events = 'strikeout'
                  THEN 1 END)                           as strikeouts,
            COUNT(CASE WHEN events = 'walk'
                  THEN 1 END)                           as walks,
            ROUND(
                COUNT(CASE WHEN events = 'strikeout' THEN 1 END) * 1.0 /
                NULLIF(COUNT(CASE WHEN events = 'walk' THEN 1 END), 0)
            , 2)                                        as k_bb_ratio,
            ROUND(
                COUNT(CASE WHEN events = 'strikeout' THEN 1 END) * 9.0 /
                NULLIF(
                    COUNT(CASE WHEN events IN (
                        'strikeout', 'field_out', 'force_out',
                        'grounded_into_double_play'
                    ) THEN 1 END) / 3.0
                , 0)
            , 1)                                        as k_per_9,
            ROUND(
                COUNT(CASE WHEN events = 'walk' THEN 1 END) * 9.0 /
                NULLIF(
                    COUNT(CASE WHEN events IN (
                        'strikeout', 'field_out', 'force_out',
                        'grounded_into_double_play'
                    ) THEN 1 END) / 3.0
                , 0)
            , 1)                                        as bb_per_9

        FROM pitches
        WHERE pitcher = {pitcher_id}
    """).df()
    con.close()
    return result


def calculate_xwoba_by_pitch(pitcher_id: int) -> pd.DataFrame:
    """
    Calculates xwOBA allowed by pitch type.
    xwOBA (expected Weighted On Base Average) measures
    quality of contact allowed on each pitch type.
    Lower xwOBA = better pitch effectiveness.
    League average xwOBA is typically around .320.

    Example:
        calculate_xwoba_by_pitch(594798)
    """
    con = get_connection()
    result = con.execute(f"""
        SELECT
            pitch_name,
            pitch_type,
            COUNT(*)                                        as pitches,
            ROUND(AVG(release_speed), 1)                   as avg_velo,
            ROUND(
                COUNT(CASE WHEN description = 'swinging_strike'
                      THEN 1 END) * 100.0 / COUNT(*), 1
            )                                               as whiff_pct,
            ROUND(AVG(estimated_woba_using_speedangle), 3)  as xwoba_allowed,
            ROUND(AVG(estimated_ba_using_speedangle), 3)    as xba_allowed,
            ROUND(AVG(launch_speed), 1)                     as avg_exit_velo,
            ROUND(AVG(launch_angle), 1)                     as avg_launch_angle

        FROM pitches
        WHERE pitcher = {pitcher_id}
          AND pitch_type IS NOT NULL
        GROUP BY pitch_name, pitch_type
        ORDER BY pitches DESC
    """).df()
    con.close()
    return result


def babip(pitcher_id: int) -> pd.DataFrame:
    """
    Calculates BABIP - Batting Average on Balls In Play.
    Measures how often batted balls become hits excluding
    home runs and strikeouts.

    League average BABIP is around .300.
    Pitchers significantly above .300 may be getting unlucky.
    Pitchers significantly below .300 may be getting lucky.
    BABIP regresses toward .300 over time for most pitchers.

    Example:
        babip(594798)
    """
    con = get_connection()
    result = con.execute(f"""
        SELECT
            pitcher,
            COUNT(CASE WHEN events IN ('single', 'double', 'triple')
                  THEN 1 END)                           as hits_in_play,
            COUNT(CASE WHEN events IN (
                  'single', 'double', 'triple',
                  'field_out', 'force_out',
                  'grounded_into_double_play',
                  'fielders_choice_out', 'sac_fly')
                  THEN 1 END)                           as balls_in_play,
            COUNT(CASE WHEN events = 'strikeout'
                  THEN 1 END)                           as strikeouts,
            COUNT(CASE WHEN events = 'home_run'
                  THEN 1 END)                           as home_runs,
            ROUND(
                COUNT(CASE WHEN events IN (
                    'single', 'double', 'triple'
                ) THEN 1 END) * 1.0 /
                NULLIF(COUNT(CASE WHEN events IN (
                    'single', 'double', 'triple',
                    'field_out', 'force_out',
                    'grounded_into_double_play',
                    'fielders_choice_out', 'sac_fly'
                ) THEN 1 END), 0)
            , 3)                                        as babip

        FROM pitches
        WHERE pitcher = {pitcher_id}
    """).df()
    con.close()
    return result


if __name__ == "__main__":
    print("Metrics module ready")
    print("Available functions:")
    print("  calculate_fip(pitcher_id)")
    print("  calculate_whip(pitcher_id)")
    print("  calculate_k_bb(pitcher_id)")
    print("  calculate_xwoba_by_pitch(pitcher_id)")
    print("  babip(pitcher_id)")
    print()
    print("All functions take an MLBAM pitcher ID as input")
    print("Use player_lookup.py to find player IDs")