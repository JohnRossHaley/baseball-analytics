"""
stats.py
Verified batting stat calculations from Statcast pitch data.

Accuracy vs Baseball Reference (verified Aaron Judge 2025):
  HR:  exact match (53)
  BB:  exact match (124)
  OBP: exact match (.457)
  AVG: within .002
  SLG: within .003
  PA:  within ~1% (Statcast scoring edge cases on
       certain force outs and unusual plays)

This module is the single source of truth for slash-line
math across the whole system. Other modules import from
here rather than redefining the formula.
"""

import pandas as pd
from src.database import get_connection


# ─────────────────────────────────────────────────────────────
# VERIFIED EVENT CLASSIFICATIONS
# Do not modify — these match official scoring rules
# verified against Baseball Reference
# ─────────────────────────────────────────────────────────────

# Events excluded from PA entirely
# (baserunning, pitching, umpire events — not a batting result)
EXCLUDE_FROM_PA = {
    'caught_stealing_2b', 'caught_stealing_3b',
    'caught_stealing_home',
    'pickoff_caught_stealing_2b',
    'pickoff_caught_stealing_3b',
    'pickoff_1b', 'pickoff_2b', 'pickoff_3b',
    'stolen_base_2b', 'stolen_base_3b',
    'stolen_base_home', 'wild_pitch', 'passed_ball',
    'balk', 'defensive_indiff', 'run_scoring_play'
}

# Events excluded from official AB (but still count as PA)
NOT_AB = {
    'walk', 'intent_walk', 'hit_by_pitch',
    'sac_fly', 'sac_bunt'
}

# Events that count as hits
HIT_EVENTS = {'single', 'double', 'triple', 'home_run'}


def batter_slash_line(batter_id: int,
                      season: int = None,
                      last_n_days: int = None,
                      vs_pitch_type: str = None) -> dict:
    """
    Verified batting slash line for any batter.
    Formula validated against Baseball Reference.

    Args:
        batter_id:     MLBAM batter ID
        season:        Filter to one season (None = all)
        last_n_days:   Rolling window in days (None = all)
        vs_pitch_type: Filter to one pitch type e.g. 'FF'

    Returns:
        Dict with pa, ab, h, hr, bb, k, avg, obp, slg,
        ops, xwoba, avg_ev, hard_hit_pct, barrel_pct

    Example:
        line = batter_slash_line(592450, season=2025)
        # Judge 2025: .333/.457/.685
    """
    con = get_connection()

    filters = []
    if season:
        filters.append(f"AND YEAR(game_date) = {season}")
    if last_n_days:
        filters.append(
            f"AND game_date >= CURRENT_DATE "
            f"- INTERVAL '{last_n_days} days'"
        )
    if vs_pitch_type:
        filters.append(f"AND pitch_type = '{vs_pitch_type}'")
    filter_str = ' '.join(filters)

    exclude_list = "', '".join(EXCLUDE_FROM_PA)

    result = con.execute(f"""
        WITH at_bats AS (
            SELECT
                events,
                estimated_woba_using_speedangle as xwoba,
                launch_speed,
                launch_angle
            FROM pitches
            WHERE batter = {batter_id}
              AND events IS NOT NULL
              AND events NOT IN ('{exclude_list}')
              {filter_str}
        ),
        counts AS (
            SELECT
                COUNT(*) as pa,
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
            FROM at_bats
        )
        SELECT
            pa, ab, h, singles, doubles, triples,
            hr, bb, hbp, sf, k,
            xwoba, avg_ev, hard_hit_pct, barrel_pct,
            ROUND(h * 1.0 / NULLIF(ab, 0), 3)          as avg,
            ROUND((h + bb + hbp) * 1.0 /
                NULLIF(ab + bb + hbp + sf, 0), 3)       as obp,
            ROUND((singles + doubles*2 + triples*3 + hr*4)
                * 1.0 / NULLIF(ab, 0), 3)               as slg,
            ROUND(
                (h + bb + hbp) * 1.0 /
                NULLIF(ab + bb + hbp + sf, 0) +
                (singles + doubles*2 + triples*3 + hr*4)
                * 1.0 / NULLIF(ab, 0), 3)               as ops
        FROM counts
    """).df()

    con.close()

    if result.empty or not result.iloc[0]['pa']:
        return {}

    r = result.iloc[0]

    def _i(v): return int(v) if pd.notna(v) else 0
    def _f(v): return float(v) if pd.notna(v) else 0.0

    return {
        'pa':           _i(r['pa']),
        'ab':           _i(r['ab']),
        'h':            _i(r['h']),
        'singles':      _i(r['singles']),
        'doubles':      _i(r['doubles']),
        'triples':      _i(r['triples']),
        'hr':           _i(r['hr']),
        'bb':           _i(r['bb']),
        'hbp':          _i(r['hbp']),
        'sf':           _i(r['sf']),
        'k':            _i(r['k']),
        'avg':          _f(r['avg']),
        'obp':          _f(r['obp']),
        'slg':          _f(r['slg']),
        'ops':          _f(r['ops']),
        'xwoba':        _f(r['xwoba']),
        'avg_ev':       _f(r['avg_ev']),
        'hard_hit_pct': _f(r['hard_hit_pct']),
        'barrel_pct':   _f(r['barrel_pct']),
    }


def batter_slash_vs_pitcher(batter_id: int,
                             pitcher_id: int) -> dict:
    """
    Head-to-head slash line for a specific batter vs a
    specific pitcher. Same verified formula.

    Example:
        batter_slash_vs_pitcher(592450, 543037)
    """
    con = get_connection()
    exclude_list = "', '".join(EXCLUDE_FROM_PA)

    result = con.execute(f"""
        WITH at_bats AS (
            SELECT
                events, game_date,
                estimated_woba_using_speedangle as xwoba,
                launch_speed
            FROM pitches
            WHERE batter  = {batter_id}
              AND pitcher = {pitcher_id}
              AND events IS NOT NULL
              AND events NOT IN ('{exclude_list}')
        ),
        counts AS (
            SELECT
                COUNT(*)                                as pa,
                COUNT(DISTINCT game_date)               as games,
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
                      THEN launch_speed END), 1)        as avg_ev
            FROM at_bats
        )
        SELECT
            pa, games, ab, h, singles, doubles, triples,
            hr, bb, hbp, sf, k, xwoba, avg_ev,
            ROUND(h * 1.0 / NULLIF(ab, 0), 3)          as avg,
            ROUND((h + bb + hbp) * 1.0 /
                NULLIF(ab + bb + hbp + sf, 0), 3)       as obp,
            ROUND((singles + doubles*2 + triples*3 + hr*4)
                * 1.0 / NULLIF(ab, 0), 3)               as slg,
            ROUND(
                (h + bb + hbp) * 1.0 /
                NULLIF(ab + bb + hbp + sf, 0) +
                (singles + doubles*2 + triples*3 + hr*4)
                * 1.0 / NULLIF(ab, 0), 3)               as ops
        FROM counts
    """).df()

    con.close()

    if result.empty or not result.iloc[0]['pa']:
        return {}

    r = result.iloc[0]

    def _i(v): return int(v) if pd.notna(v) else 0
    def _f(v): return float(v) if pd.notna(v) else 0.0

    return {
        'pa':     _i(r['pa']),  'games': _i(r['games']),
        'ab':     _i(r['ab']),  'h':     _i(r['h']),
        'hr':     _i(r['hr']),  'bb':    _i(r['bb']),
        'k':      _i(r['k']),
        'avg':    _f(r['avg']), 'obp':   _f(r['obp']),
        'slg':    _f(r['slg']), 'ops':   _f(r['ops']),
        'xwoba':  _f(r['xwoba']),
        'avg_ev': _f(r['avg_ev']),
    }


def format_slash_line(stats: dict,
                      include_counting: bool = True) -> str:
    """
    Formats a slash-line dict into a readable string.

    Example:
        format_slash_line(line)
        # '.333/.457/.685 | 53 HR | 124 BB | 162 K | 687 PA'
    """
    if not stats:
        return 'No data'

    def _pct(v):
        return f".{int(round(v * 1000)):03d}"

    slash = f"{_pct(stats['avg'])}/{_pct(stats['obp'])}/{_pct(stats['slg'])}"

    if include_counting:
        parts = [slash]
        if stats.get('hr'):  parts.append(f"{stats['hr']} HR")
        if stats.get('bb'):  parts.append(f"{stats['bb']} BB")
        if stats.get('k'):   parts.append(f"{stats['k']} K")
        if stats.get('pa'):  parts.append(f"{stats['pa']} PA")
        return ' | '.join(parts)

    return slash


def format_slash_short(stats: dict) -> str:
    """
    Compact slash line for SMS and summary output.

    Example:
        format_slash_short(line)  # '.333/.457/.685'
    """
    if not stats:
        return 'N/A'

    def _pct(v):
        return f".{int(round(v * 1000)):03d}"

    return (f"{_pct(stats.get('avg', 0))}/"
            f"{_pct(stats.get('obp', 0))}/"
            f"{_pct(stats.get('slg', 0))}")


# ─────────────────────────────────────────────────────────────
# DATA CITATION
# Include at the bottom of every report and export
# ─────────────────────────────────────────────────────────────

DATA_CITATION = (
    "Sources: Statcast · FanGraphs · MLB API · OpenWeatherMap"
)

METHODOLOGY_NOTE = (
    "Stats from Statcast pitch data (2021-2026). "
    "PA may differ from official totals by ~1% due to "
    "Statcast scoring edge cases. Rate stats (AVG/OBP/SLG) "
    "accurate within .003 vs Baseball Reference."
)


if __name__ == "__main__":
    # Verification — Judge 2025 should be ~.333/.457/.685
    print("Verification — Aaron Judge 2025:")
    line = batter_slash_line(592450, season=2025)
    print(f"  {format_slash_line(line)}")
    print()
    print("  BB-Ref target: .331/.457/.688 | 53 HR | 124 BB | 160 K")
    print()
    print(f"  OBP exact match: {line.get('obp') == 0.457}")
    print(f"  HR exact match:  {line.get('hr')  == 53}")
    print(f"  BB exact match:  {line.get('bb')  == 124}")
    print()
    print(f"  {DATA_CITATION}")