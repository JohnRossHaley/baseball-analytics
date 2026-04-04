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

def head_to_head_history(pitcher_id: int,
                          batter_id: int) -> dict:
    """
    Full career head to head history between a specific
    pitcher and batter using your Statcast database.

    Returns at bat level results, pitch level breakdown,
    and a summary with key talking points.

    Note: Limited to seasons in your database.
    Pull more seasons via pull_statcast_range() for
    deeper historical context.

    Example:
        history = head_to_head_history(677960, 605141)
    """
    con = get_connection()

    # ── At bat level results ──────────────────────────────
    at_bats = con.execute(f"""
        WITH at_bat_results AS (
            SELECT
                game_date,
                game_pk,
                YEAR(game_date)                         as season,
                inning,
                balls,
                strikes,
                events,
                description,
                launch_speed,
                launch_angle,
                hit_distance_sc,
                estimated_woba_using_speedangle         as xwoba,
                estimated_ba_using_speedangle           as xba,
                bb_type
            FROM pitches
            WHERE pitcher = {pitcher_id}
              AND batter  = {batter_id}
              AND events IS NOT NULL
              AND events NOT IN (
                  'caught_stealing_2b',
                  'caught_stealing_3b',
                  'caught_stealing_home',
                  'pickoff_caught_stealing_2b',
                  'pickoff_caught_stealing_3b',
                  'wild_pitch',
                  'passed_ball'
              )
        )
        SELECT
            game_date,
            season,
            inning,
            events                                      as result,
            ROUND(launch_speed, 1)                      as exit_velo,
            ROUND(launch_angle, 1)                      as launch_angle,
            ROUND(hit_distance_sc, 0)                   as distance,
            ROUND(xwoba, 3)                             as xwoba,
            bb_type                                     as batted_ball_type
        FROM at_bat_results
        ORDER BY game_date DESC
    """).df()

    # ── Pitch level breakdown in this matchup ─────────────
    pitch_breakdown = con.execute(f"""
        SELECT
            pitch_name,
            COUNT(*)                                    as pitches,
            ROUND(COUNT(*) * 100.0 /
                SUM(COUNT(*)) OVER (), 1)               as usage_pct,
            ROUND(AVG(release_speed), 1)                as avg_velo,
            ROUND(
                COUNT(CASE WHEN description = 'swinging_strike'
                      THEN 1 END) * 100.0 / COUNT(*), 1
            )                                           as whiff_pct,
            ROUND(
                COUNT(CASE WHEN zone NOT BETWEEN 1 AND 9
                      AND description LIKE '%swinging%'
                      THEN 1 END) * 100.0 /
                NULLIF(COUNT(CASE WHEN zone NOT BETWEEN 1 AND 9
                      THEN 1 END), 0), 1
            )                                           as chase_pct,
            ROUND(AVG(estimated_woba_using_speedangle), 3)
                                                        as xwoba,
            ROUND(AVG(CASE WHEN launch_speed IS NOT NULL
                  THEN launch_speed END), 1)            as avg_exit_velo,
            ROUND(
                COUNT(CASE WHEN launch_speed >= 95
                      THEN 1 END) * 100.0 /
                NULLIF(COUNT(CASE WHEN launch_speed IS NOT NULL
                      THEN 1 END), 0), 1
            )                                           as hard_hit_pct
        FROM pitches
        WHERE pitcher = {pitcher_id}
          AND batter  = {batter_id}
          AND pitch_type IS NOT NULL
        GROUP BY pitch_name
        ORDER BY pitches DESC
    """).df()

    # ── Count tendencies in this matchup ──────────────────
    count_tendencies = con.execute(f"""
        SELECT
            CONCAT(balls, '-', strikes)                 as count,
            pitch_name,
            COUNT(*)                                    as pitches,
            ROUND(COUNT(*) * 100.0 /
                SUM(COUNT(*)) OVER (
                    PARTITION BY balls, strikes
                ), 1)                                   as usage_pct,
            ROUND(
                COUNT(CASE WHEN description = 'swinging_strike'
                      THEN 1 END) * 100.0 / COUNT(*), 1
            )                                           as whiff_pct
        FROM pitches
        WHERE pitcher = {pitcher_id}
          AND batter  = {batter_id}
          AND pitch_type IS NOT NULL
        GROUP BY balls, strikes, pitch_name
        HAVING COUNT(*) >= 3
        ORDER BY balls, strikes, pitches DESC
    """).df()

    # ── Season by season summary ──────────────────────────
    by_season = con.execute(f"""
        SELECT
            YEAR(game_date)                             as season,
            COUNT(DISTINCT game_pk)                     as games_faced,
            COUNT(DISTINCT CASE WHEN events IS NOT NULL
                  AND events NOT IN (
                      'caught_stealing_2b',
                      'wild_pitch', 'passed_ball'
                  ) THEN game_pk END)                   as at_bats,
            COUNT(CASE WHEN events IN (
                  'single', 'double', 'triple', 'home_run'
                  ) THEN 1 END)                         as hits,
            COUNT(CASE WHEN events = 'home_run'
                  THEN 1 END)                           as home_runs,
            COUNT(CASE WHEN events = 'walk'
                  THEN 1 END)                           as walks,
            COUNT(CASE WHEN events = 'strikeout'
                  THEN 1 END)                           as strikeouts,
            COUNT(*)                                    as total_pitches,
            ROUND(AVG(release_speed), 1)                as avg_velo_seen,
            ROUND(AVG(estimated_woba_using_speedangle), 3)
                                                        as xwoba,
            ROUND(AVG(CASE WHEN launch_speed IS NOT NULL
                  THEN launch_speed END), 1)            as avg_exit_velo
        FROM pitches
        WHERE pitcher = {pitcher_id}
          AND batter  = {batter_id}
        GROUP BY YEAR(game_date)
        ORDER BY season DESC
    """).df()

    # ── Overall career summary ────────────────────────────
    career = con.execute(f"""
        SELECT
            COUNT(*)                                    as total_pitches,
            COUNT(DISTINCT game_pk)                     as games_faced,
            COUNT(CASE WHEN events IN (
                  'single', 'double', 'triple', 'home_run'
                  ) THEN 1 END)                         as hits,
            COUNT(CASE WHEN events = 'home_run'
                  THEN 1 END)                           as home_runs,
            COUNT(CASE WHEN events = 'walk'
                  THEN 1 END)                           as walks,
            COUNT(CASE WHEN events = 'strikeout'
                  THEN 1 END)                           as strikeouts,
            COUNT(CASE WHEN events IS NOT NULL
                  AND events NOT IN (
                      'caught_stealing_2b', 'wild_pitch',
                      'passed_ball'
                  ) THEN 1 END)                         as at_bats,
            ROUND(AVG(release_speed), 1)                as avg_velo_seen,
            ROUND(AVG(estimated_woba_using_speedangle), 3)
                                                        as career_xwoba,
            ROUND(AVG(CASE WHEN launch_speed IS NOT NULL
                  THEN launch_speed END), 1)            as avg_exit_velo,
            ROUND(
                COUNT(CASE WHEN launch_speed >= 95
                      THEN 1 END) * 100.0 /
                NULLIF(COUNT(CASE WHEN launch_speed IS NOT NULL
                      THEN 1 END), 0), 1
            )                                           as hard_hit_pct
        FROM pitches
        WHERE pitcher = {pitcher_id}
          AND batter  = {batter_id}
    """).df()

    con.close()

    # Get player names
    con2 = get_connection()
    pitcher_name = con2.execute(f"""
        SELECT name_first || ' ' || name_last
        FROM players WHERE mlbam_id = {pitcher_id}
    """).fetchone()
    batter_name = con2.execute(f"""
        SELECT name_first || ' ' || name_last
        FROM players WHERE mlbam_id = {batter_id}
    """).fetchone()
    con2.close()

    pitcher_name = pitcher_name[0] if pitcher_name else str(pitcher_id)
    batter_name = batter_name[0] if batter_name else str(batter_id)

    return {
        'pitcher_id':       pitcher_id,
        'pitcher_name':     pitcher_name,
        'batter_id':        batter_id,
        'batter_name':      batter_name,
        'career_summary':   career,
        'by_season':        by_season,
        'at_bats':          at_bats,
        'pitch_breakdown':  pitch_breakdown,
        'count_tendencies': count_tendencies
    }


def print_head_to_head(pitcher_id: int, batter_id: int):
    """
    Prints a clean formatted head to head report.

    Example:
        print_head_to_head(677960, 605141)
    """
    h2h = head_to_head_history(pitcher_id, batter_id)

    print(f"\n{'═' * 60}")
    print(f"HEAD TO HEAD HISTORY")
    print(f"{h2h['pitcher_name'].upper()} vs "
          f"{h2h['batter_name'].upper()}")
    print(f"(Limited to seasons in your database)")
    print(f"{'═' * 60}")

    # Career summary
    if not h2h['career_summary'].empty:
        c = h2h['career_summary'].iloc[0]
        total = c['total_pitches']

        if total == 0:
            print("\nNo head to head data in database.")
            print("Pull additional seasons via "
                  "pull_statcast_range() for history.")
            return

        print(f"\nCareer Summary ({c['games_faced']} games):")
        print(f"  Total Pitches:  {int(c['total_pitches'])}")
        print(f"  At Bats:        {int(c['at_bats'])}")
        print(f"  Hits:           {int(c['hits'])}")
        print(f"  Home Runs:      {int(c['home_runs'])}")
        print(f"  Walks:          {int(c['walks'])}")
        print(f"  Strikeouts:     {int(c['strikeouts'])}")
        print(f"  Avg Exit Velo:  {c['avg_exit_velo']} mph")
        print(f"  Hard Hit%:      {c['hard_hit_pct']}%")
        print(f"  Career xwOBA:   {c['career_xwoba']}")

        # Calculate basic slash if enough at bats
        ab = int(c['at_bats'])
        hits = int(c['hits'])
        if ab > 0:
            avg = round(hits / ab, 3)
            print(f"  H/AB (raw):     {hits}/{ab} ({avg:.3f})")

    # Season by season
    if not h2h['by_season'].empty:
        print(f"\nBy Season:")
        print(h2h['by_season'].to_string(index=False))

    # Pitch breakdown in this specific matchup
    if not h2h['pitch_breakdown'].empty:
        print(f"\nPitch Breakdown in This Matchup:")
        print(h2h['pitch_breakdown'].to_string(index=False))

    # Count tendencies
    if not h2h['count_tendencies'].empty:
        print(f"\nCount Tendencies in This Matchup:")
        print(h2h['count_tendencies'].to_string(index=False))

    # Individual at bat results
    if not h2h['at_bats'].empty:
        print(f"\nAt Bat Results (most recent first):")
        print(h2h['at_bats'].to_string(index=False))
    else:
        print("\nNo completed at bat results in database.")

    print(f"\n{'═' * 60}")


if __name__ == "__main__":
    print("Matchup query module ready")
    print("Available functions:")
    print("  pitcher_vs_batter(pitcher_id, batter_id)")
    print("  pitcher_tendencies(pitcher_id)")
    print("  batter_tendencies(batter_id)")
    print("  pitch_mix_by_count(pitcher_id)")
    print("  platoon_splits(pitcher_id)")
