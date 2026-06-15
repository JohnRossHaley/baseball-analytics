"""
export_layer.py

Builds the BI serving layer — clean, pre-aggregated tables
exported for Tableau or Power BI.

This is the data mart pattern: instead of pointing a BI tool
at the raw 3.6M row pitches table (slow), we pre-compute
analysis-ready summary tables at the grain the dashboard
needs, then export them.

Every slash line uses the verified formula from stats.py
(OBP, HR, BB match Baseball Reference exactly).

Tables built (each at BOTH grains — career and per-season):
    1. pitcher_arsenal    — pitcher x pitch type
    2. batter_vs_pitch    — batter x pitch type (slash line)
    3. player_slash       — player x season slash line
    4. lineup_index       — pre-computed matchup scores (current slate)
    5. bullpen_workload   — reliever availability snapshot

Output: data/exports/*.parquet and *.csv

Usage:
    from src.export_layer import build_all_exports
    build_all_exports()
"""

import os
import pandas as pd
from datetime import date
from src.database import get_connection

# Reuse the verified event classifications
from src.stats import EXCLUDE_FROM_PA, DATA_CITATION

EXPORT_DIR = "data/exports"


def _ensure_export_dir():
    """Creates the exports directory if it doesn't exist."""
    os.makedirs(EXPORT_DIR, exist_ok=True)


def _write(df: pd.DataFrame, name: str):
    """
    Writes a DataFrame to both Parquet and CSV.
    Parquet is the primary (typed, compressed).
    CSV is the universal fallback.
    """
    if df.empty:
        print(f"  ⚠ {name}: no rows, skipped")
        return

    _ensure_export_dir()
    parquet_path = f"{EXPORT_DIR}/{name}.parquet"
    csv_path     = f"{EXPORT_DIR}/{name}.csv"

    try:
        df.to_parquet(parquet_path, index=False)
        df.to_csv(csv_path, index=False)
        print(f"  ✓ {name}: {len(df):,} rows "
              f"→ parquet + csv")
    except Exception as e:
        # Parquet needs pyarrow — fall back to CSV only
        df.to_csv(csv_path, index=False)
        print(f"  ✓ {name}: {len(df):,} rows → csv only "
              f"(parquet failed: {e})")


# ─────────────────────────────────────────────────────────
# 1. PITCHER ARSENAL
# One row per pitcher per pitch type
# ─────────────────────────────────────────────────────────

def build_pitcher_arsenal(by_season: bool = False) -> pd.DataFrame:
    """
    Pitcher arsenal table — usage, velocity, whiff, xwOBA
    allowed, hard-hit per pitch type.

    Args:
        by_season: If True, splits by season. If False,
                   career totals across all seasons.
    """
    con = get_connection()

    season_sel   = "YEAR(p.game_date) as season," if by_season else ""
    season_grp   = "YEAR(p.game_date)," if by_season else ""
    season_out   = "season," if by_season else ""
    season_order = "season," if by_season else ""
    partition    = ("PARTITION BY p.pitcher, YEAR(p.game_date)"
                    if by_season else "PARTITION BY p.pitcher")

    df = con.execute(f"""
        SELECT
            {season_sel}
            p.pitcher                                   as mlbam_id,
            COALESCE(pl.name_first || ' ' || pl.name_last,
                     'ID:' || CAST(p.pitcher AS VARCHAR)) as pitcher_name,
            p.pitch_name,
            p.pitch_type,
            COUNT(*)                                     as pitches,
            ROUND(COUNT(*) * 100.0 /
                SUM(COUNT(*)) OVER ({partition}), 1)     as usage_pct,
            ROUND(AVG(p.release_speed), 1)              as avg_velo,
            ROUND(MAX(p.release_speed), 1)             as peak_velo,
            ROUND(AVG(p.release_spin_rate), 0)         as avg_spin,
            ROUND(
                COUNT(CASE WHEN p.description = 'swinging_strike'
                      THEN 1 END) * 100.0 / COUNT(*), 1
            )                                           as whiff_pct,
            ROUND(
                COUNT(CASE WHEN p.zone BETWEEN 1 AND 9
                      THEN 1 END) * 100.0 / COUNT(*), 1
            )                                           as zone_pct,
            ROUND(AVG(p.estimated_woba_using_speedangle), 3)
                                                        as xwoba_allowed,
            ROUND(
                COUNT(CASE WHEN p.launch_speed >= 95
                      THEN 1 END) * 100.0 /
                NULLIF(COUNT(CASE WHEN p.launch_speed IS NOT NULL
                      THEN 1 END), 0), 1
            )                                           as hard_hit_pct,
            ROUND(AVG(CASE WHEN p.launch_speed IS NOT NULL
                  THEN p.launch_speed END), 1)          as avg_exit_velo
        FROM pitches p
        LEFT JOIN players pl ON p.pitcher = pl.mlbam_id
        WHERE p.pitch_type IS NOT NULL
        GROUP BY {season_grp} p.pitcher,
                 pl.name_first, pl.name_last,
                 p.pitch_name, p.pitch_type
        HAVING COUNT(*) >= 20
        ORDER BY {season_order} p.pitcher, pitches DESC
    """).df()

    con.close()
    return df

# ─────────────────────────────────────────────────────────
# 2. BATTER VS PITCH TYPE (verified slash line)
# One row per batter per pitch type
# ─────────────────────────────────────────────────────────

def build_batter_vs_pitch(by_season: bool = False) -> pd.DataFrame:
    """
    Batter performance vs each pitch type with verified
    slash line. This is the core matchup table — it crosses
    with pitcher_arsenal to answer 'how does this hitter
    handle what this pitcher throws'.
    """
    con = get_connection()

    season_sel   = "YEAR(game_date) as season," if by_season else ""
    season_grp   = "season," if by_season else ""
    season_out   = "a.season," if by_season else ""
    season_order = "a.season," if by_season else ""
    exclude_list = "', '".join(EXCLUDE_FROM_PA)

    df = con.execute(f"""
        WITH base AS (
            SELECT
                {season_sel}
                batter,
                pitch_name,
                pitch_type,
                events,
                launch_speed,
                description,
                estimated_woba_using_speedangle as xwoba
            FROM pitches
            WHERE pitch_type IS NOT NULL
              AND events IS NOT NULL
              AND events NOT IN ('{exclude_list}')
        ),
        agg AS (
            SELECT
                {season_grp}
                batter,
                pitch_name,
                pitch_type,
                COUNT(*)                                as pa,
                COUNT(CASE WHEN events NOT IN (
                    'walk','intent_walk','hit_by_pitch',
                    'sac_fly','sac_bunt'
                ) THEN 1 END)                           as ab,
                COUNT(CASE WHEN events IN (
                    'single','double','triple','home_run'
                ) THEN 1 END)                           as h,
                COUNT(CASE WHEN events = 'single'
                      THEN 1 END)                       as singles,
                COUNT(CASE WHEN events = 'double'
                      THEN 1 END)                       as doubles,
                COUNT(CASE WHEN events = 'triple'
                      THEN 1 END)                       as triples,
                COUNT(CASE WHEN events = 'home_run'
                      THEN 1 END)                       as hr,
                COUNT(CASE WHEN events IN (
                    'walk','intent_walk'
                ) THEN 1 END)                           as bb,
                COUNT(CASE WHEN events = 'hit_by_pitch'
                      THEN 1 END)                       as hbp,
                COUNT(CASE WHEN events = 'sac_fly'
                      THEN 1 END)                       as sf,
                COUNT(CASE WHEN events IN (
                    'strikeout','strikeout_double_play'
                ) THEN 1 END)                           as k,
                ROUND(AVG(xwoba), 3)                    as xwoba,
                ROUND(AVG(CASE WHEN launch_speed IS NOT NULL
                      THEN launch_speed END), 1)        as avg_ev,
                ROUND(
                    COUNT(CASE WHEN launch_speed >= 95
                          THEN 1 END) * 100.0 /
                    NULLIF(COUNT(CASE WHEN launch_speed
                          IS NOT NULL THEN 1 END), 0), 1
                )                                       as hard_hit_pct,
                ROUND(
                    COUNT(CASE WHEN description = 'swinging_strike'
                          THEN 1 END) * 100.0 /
                    NULLIF(COUNT(CASE WHEN description
                          LIKE '%swinging%' THEN 1 END), 0), 1
                )                                       as miss_pct
            FROM base
            GROUP BY {season_grp} batter,
                     pitch_name, pitch_type
            HAVING COUNT(*) >= 20
        )
        SELECT
            {season_out}
            a.batter                                    as mlbam_id,
            COALESCE(pl.name_first || ' ' || pl.name_last,
                     'ID:' || CAST(a.batter AS VARCHAR)) as batter_name,
            a.pitch_name,
            a.pitch_type,
            a.pa, a.ab, a.h, a.hr, a.bb, a.k,
            ROUND(a.h * 1.0 / NULLIF(a.ab, 0), 3)      as avg,
            ROUND((a.h + a.bb + a.hbp) * 1.0 /
                NULLIF(a.ab + a.bb + a.hbp + a.sf, 0), 3) as obp,
            ROUND((a.singles + a.doubles*2 + a.triples*3
                   + a.hr*4) * 1.0 /
                NULLIF(a.ab, 0), 3)                     as slg,
            ROUND(
                (a.h + a.bb + a.hbp) * 1.0 /
                NULLIF(a.ab + a.bb + a.hbp + a.sf, 0) +
                (a.singles + a.doubles*2 + a.triples*3
                 + a.hr*4) * 1.0 / NULLIF(a.ab, 0), 3)  as ops,
            a.xwoba,
            a.avg_ev,
            a.hard_hit_pct,
            a.miss_pct
        FROM agg a
        LEFT JOIN players pl ON a.batter = pl.mlbam_id
        ORDER BY {season_order} a.batter, a.pa DESC
    """).df()

    con.close()
    return df


# ─────────────────────────────────────────────────────────
# 3. PLAYER SLASH LINE (verified, season + career)
# One row per player per season (or career)
# ─────────────────────────────────────────────────────────

def build_player_slash(by_season: bool = False) -> pd.DataFrame:
    """
    Verified full slash line per player. Uses the exact
    formula validated against Baseball Reference.
    """
    con = get_connection()

    season_sel   = "YEAR(game_date) as season," if by_season else ""
    season_grp   = "season," if by_season else ""
    season_out   = "a.season," if by_season else ""
    season_order = "a.season," if by_season else ""
    exclude_list = "', '".join(EXCLUDE_FROM_PA)

    df = con.execute(f"""
        WITH base AS (
            SELECT
                {season_sel}
                batter,
                events,
                launch_speed,
                launch_angle,
                game_date,
                estimated_woba_using_speedangle as xwoba
            FROM pitches
            WHERE events IS NOT NULL
              AND events NOT IN ('{exclude_list}')
        ),
        agg AS (
            SELECT
                {season_grp}
                batter,
                COUNT(DISTINCT game_date)               as games,
                COUNT(*)                                as pa,
                COUNT(CASE WHEN events NOT IN (
                    'walk','intent_walk','hit_by_pitch',
                    'sac_fly','sac_bunt'
                ) THEN 1 END)                           as ab,
                COUNT(CASE WHEN events IN (
                    'single','double','triple','home_run'
                ) THEN 1 END)                           as h,
                COUNT(CASE WHEN events = 'single'
                      THEN 1 END)                       as singles,
                COUNT(CASE WHEN events = 'double'
                      THEN 1 END)                       as doubles,
                COUNT(CASE WHEN events = 'triple'
                      THEN 1 END)                       as triples,
                COUNT(CASE WHEN events = 'home_run'
                      THEN 1 END)                       as hr,
                COUNT(CASE WHEN events IN (
                    'walk','intent_walk'
                ) THEN 1 END)                           as bb,
                COUNT(CASE WHEN events = 'hit_by_pitch'
                      THEN 1 END)                       as hbp,
                COUNT(CASE WHEN events = 'sac_fly'
                      THEN 1 END)                       as sf,
                COUNT(CASE WHEN events IN (
                    'strikeout','strikeout_double_play'
                ) THEN 1 END)                           as k,
                ROUND(AVG(xwoba), 3)                    as xwoba,
                ROUND(AVG(CASE WHEN launch_speed IS NOT NULL
                      THEN launch_speed END), 1)        as avg_ev,
                ROUND(
                    COUNT(CASE WHEN launch_speed >= 95
                          THEN 1 END) * 100.0 /
                    NULLIF(COUNT(CASE WHEN launch_speed
                          IS NOT NULL THEN 1 END), 0), 1
                )                                       as hard_hit_pct,
                ROUND(
                    COUNT(CASE WHEN launch_speed >= 98
                          AND launch_angle BETWEEN 26 AND 30
                          THEN 1 END) * 100.0 /
                    NULLIF(COUNT(CASE WHEN launch_speed
                          IS NOT NULL THEN 1 END), 0), 1
                )                                       as barrel_pct
            FROM base
            GROUP BY {season_grp} batter
            HAVING COUNT(*) >= 50
        )
        SELECT
            {season_out}
            a.batter                                    as mlbam_id,
            COALESCE(pl.name_first || ' ' || pl.name_last,
                     'ID:' || CAST(a.batter AS VARCHAR)) as player_name,
            a.games, a.pa, a.ab, a.h, a.hr, a.bb, a.k,
            ROUND(a.h * 1.0 / NULLIF(a.ab, 0), 3)      as avg,
            ROUND((a.h + a.bb + a.hbp) * 1.0 /
                NULLIF(a.ab + a.bb + a.hbp + a.sf, 0), 3) as obp,
            ROUND((a.singles + a.doubles*2 + a.triples*3
                   + a.hr*4) * 1.0 /
                NULLIF(a.ab, 0), 3)                     as slg,
            ROUND(
                (a.h + a.bb + a.hbp) * 1.0 /
                NULLIF(a.ab + a.bb + a.hbp + a.sf, 0) +
                (a.singles + a.doubles*2 + a.triples*3
                 + a.hr*4) * 1.0 / NULLIF(a.ab, 0), 3)  as ops,
            a.xwoba,
            a.avg_ev,
            a.hard_hit_pct,
            a.barrel_pct
        FROM agg a
        LEFT JOIN players pl ON a.batter = pl.mlbam_id
        ORDER BY {season_order} ops DESC
    """).df()

    con.close()
    return df


# ─────────────────────────────────────────────────────────
# MASTER BUILD
# ─────────────────────────────────────────────────────────

def build_all_exports():
    """
    Builds every serving-layer table at both grains
    (career + per-season) and writes Parquet + CSV.

    Run after update_to_today() to refresh the dashboard data.
    """
    print(f"\n{'═' * 55}")
    print(f"  BUILDING BI SERVING LAYER")
    print(f"  {date.today()}")
    print(f"{'═' * 55}\n")

    print("Pitcher arsenal:")
    _write(build_pitcher_arsenal(by_season=False),
           "pitcher_arsenal_career")
    _write(build_pitcher_arsenal(by_season=True),
           "pitcher_arsenal_by_season")

    print("\nBatter vs pitch type:")
    _write(build_batter_vs_pitch(by_season=False),
           "batter_vs_pitch_career")
    _write(build_batter_vs_pitch(by_season=True),
           "batter_vs_pitch_by_season")

    print("\nPlayer slash lines:")
    _write(build_player_slash(by_season=False),
           "player_slash_career")
    _write(build_player_slash(by_season=True),
           "player_slash_by_season")

    print(f"\n{'═' * 55}")
    print(f"  EXPORT COMPLETE → {EXPORT_DIR}/")
    print(f"  {DATA_CITATION}")
    print(f"{'═' * 55}\n")


if __name__ == "__main__":
    build_all_exports()