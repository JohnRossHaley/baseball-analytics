"""
matchup_report.py

Generates comprehensive matchup analysis reports for any
pitcher vs batter or team vs team matchup.

Designed to be customizable so you can inject professional
baseball logic, personal weights, and betting relevant
thresholds on top of raw Statcast analytics.

Architecture:
    1. get_pitcher_profile()  - builds full pitcher data dict
    2. get_batter_profile()   - builds full batter data dict
    3. head_to_head_history() - career H2H between two players
    4. analyze_matchup()      - compares profiles, finds edges
    5. generate_matchup_report() - master function, runs all above
    6. quick_matchup()        - name based convenience wrapper
"""

import pandas as pd
from datetime import date, timedelta
from src.database import get_connection
from src.matchup_queries import head_to_head_history


# ─────────────────────────────────────────────────────────────
# CUSTOMIZABLE THRESHOLDS
# Adjust these based on your professional baseball experience
# These drive all edge classifications and talking points
# ─────────────────────────────────────────────────────────────

THRESHOLDS = {

    # Whiff rate
    'whiff_elite':              30.0,
    'whiff_good':               22.0,
    'whiff_concern':            10.0,

    # xwOBA allowed by pitcher
    'xwoba_elite':              0.280,
    'xwoba_average':            0.320,
    'xwoba_concern':            0.370,
    'xwoba_danger':             0.420,

    # Batter xwOBA vs pitch type
    'batter_xwoba_danger':      0.420,
    'batter_xwoba_neutral':     0.340,

    # Hard hit rate
    'hard_hit_elite':           50.0,
    'hard_hit_concern':         38.0,

    # Exit velocity
    'exit_velo_elite':          92.0,
    'exit_velo_concern':        88.0,

    # Chase rate - batter chasing out of zone
    'chase_high':               35.0,
    'chase_elite':              42.0,

    # Velocity drop flags
    'velo_drop_watch':          1.5,
    'velo_drop_concern':        3.0,

    # Sample size thresholds
    'min_pitches_reliable':     100,
    'min_pitches_usable':       50,
    'min_pitches_small':        20,

    # Hot/cold batter thresholds
    # Recent xwOBA vs season xwOBA delta
    'hot_batter_delta':         0.060,
    'cold_batter_delta':        -0.060,

    # Recent form window in days
    'recent_form_days':         14,
}


# ─────────────────────────────────────────────────────────────
# PITCHER PROFILE
# ─────────────────────────────────────────────────────────────

def get_pitcher_profile(pitcher_id: int,
                        season: int = None,
                        recent_days: int = None) -> dict:
    """
    Builds a complete pitcher profile including season
    pitch mix, recent form, velocity trend, and count
    leverage tendencies.

    Args:
        pitcher_id:  MLBAM pitcher ID
        season:      Filter to specific season (None = all)
        recent_days: Days for recent form window

    Returns:
        Dictionary with full pitcher profile
    """
    con = get_connection()

    season_filter = (
        f"AND YEAR(game_date) = {season}" if season else ""
    )
    days = recent_days or THRESHOLDS['recent_form_days']

    # ── Player name ───────────────────────────────────────
    name_row = con.execute(f"""
        SELECT name_first || ' ' || name_last
        FROM players WHERE mlbam_id = {pitcher_id}
    """).fetchone()
    name = name_row[0] if name_row else f"Pitcher {pitcher_id}"

    # ── Season summary ────────────────────────────────────
    summary = con.execute(f"""
        SELECT
            COUNT(DISTINCT game_date)           as appearances,
            COUNT(*)                            as total_pitches,
            ROUND(AVG(release_speed), 1)        as season_avg_velo,
            ROUND(MAX(release_speed), 1)        as season_peak_velo,
            ROUND(
                COUNT(CASE WHEN description = 'swinging_strike'
                      THEN 1 END) * 100.0 / COUNT(*), 1
            )                                   as overall_whiff_pct,
            ROUND(AVG(estimated_woba_using_speedangle), 3)
                                                as overall_xwoba,
            ROUND(
                COUNT(CASE WHEN launch_speed >= 95
                      THEN 1 END) * 100.0 /
                NULLIF(COUNT(CASE WHEN launch_speed IS NOT NULL
                      THEN 1 END), 0), 1
            )                                   as overall_hard_hit_pct,
            ROUND(
                COUNT(CASE WHEN zone BETWEEN 1 AND 9
                      THEN 1 END) * 100.0 / COUNT(*), 1
            )                                   as zone_pct,
            ROUND(
                COUNT(CASE WHEN type = 'S'
                      THEN 1 END) * 100.0 / COUNT(*), 1
            )                                   as strike_pct
        FROM pitches
        WHERE pitcher = {pitcher_id}
          AND pitch_type IS NOT NULL
          {season_filter}
    """).df()

    # ── Full pitch mix ────────────────────────────────────
    pitch_mix = con.execute(f"""
        SELECT
            pitch_name,
            pitch_type,
            COUNT(*)                                    as pitches,
            ROUND(COUNT(*) * 100.0 /
                SUM(COUNT(*)) OVER (), 1)               as usage_pct,
            ROUND(AVG(release_speed), 1)                as avg_velo,
            ROUND(MAX(release_speed), 1)                as peak_velo,
            ROUND(AVG(release_spin_rate), 0)            as avg_spin,
            ROUND(AVG(pfx_x), 2)                        as h_break,
            ROUND(AVG(pfx_z), 2)                        as v_break,
            ROUND(
                COUNT(CASE WHEN description = 'swinging_strike'
                      THEN 1 END) * 100.0 / COUNT(*), 1
            )                                           as whiff_pct,
            ROUND(
                COUNT(CASE WHEN zone BETWEEN 1 AND 9
                      THEN 1 END) * 100.0 / COUNT(*), 1
            )                                           as zone_pct,
            ROUND(
                COUNT(CASE WHEN zone NOT BETWEEN 1 AND 9
                      AND description LIKE '%swinging%'
                      THEN 1 END) * 100.0 /
                NULLIF(COUNT(CASE WHEN zone NOT BETWEEN 1 AND 9
                      THEN 1 END), 0), 1
            )                                           as induced_chase_pct,
            ROUND(AVG(estimated_woba_using_speedangle), 3)
                                                        as xwoba_allowed,
            ROUND(
                COUNT(CASE WHEN launch_speed >= 95
                      THEN 1 END) * 100.0 /
                NULLIF(COUNT(CASE WHEN launch_speed IS NOT NULL
                      THEN 1 END), 0), 1
            )                                           as hard_hit_pct,
            ROUND(AVG(CASE WHEN launch_speed IS NOT NULL
                  THEN launch_speed END), 1)            as avg_exit_velo
        FROM pitches
        WHERE pitcher = {pitcher_id}
          AND pitch_type IS NOT NULL
          {season_filter}
        GROUP BY pitch_name, pitch_type
        ORDER BY pitches DESC
    """).df()

    # ── Recent form ───────────────────────────────────────
    recent_mix = con.execute(f"""
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
            ROUND(AVG(estimated_woba_using_speedangle), 3)
                                                        as xwoba_allowed
        FROM pitches
        WHERE pitcher = {pitcher_id}
          AND pitch_type IS NOT NULL
          AND game_date >= CURRENT_DATE - INTERVAL '{days} days'
        GROUP BY pitch_name
        ORDER BY pitches DESC
    """).df()

    # ── Velocity trend last 10 outings ────────────────────
    velo_trend = con.execute(f"""
        SELECT
            game_date,
            ROUND(AVG(release_speed), 1)    as avg_velo,
            ROUND(MAX(release_speed), 1)    as peak_velo,
            COUNT(*)                        as pitches
        FROM pitches
        WHERE pitcher = {pitcher_id}
          AND release_speed IS NOT NULL
          AND pitch_type IS NOT NULL
        GROUP BY game_date
        ORDER BY game_date DESC
        LIMIT 10
    """).df()

    # ── Count leverage ────────────────────────────────────
    count_profile = con.execute(f"""
        SELECT
            CONCAT(balls, '-', strikes)     as count,
            pitch_name,
            COUNT(*)                        as pitches,
            ROUND(COUNT(*) * 100.0 /
                SUM(COUNT(*)) OVER (
                    PARTITION BY balls, strikes
                ), 1)                       as usage_pct,
            ROUND(AVG(release_speed), 1)    as avg_velo,
            ROUND(
                COUNT(CASE WHEN description = 'swinging_strike'
                      THEN 1 END) * 100.0 / COUNT(*), 1
            )                               as whiff_pct,
            ROUND(AVG(estimated_woba_using_speedangle), 3)
                                            as xwoba_allowed
        FROM pitches
        WHERE pitcher = {pitcher_id}
          AND pitch_type IS NOT NULL
          {season_filter}
          AND CONCAT(balls, '-', strikes) IN (
              '0-0', '0-2', '1-2', '2-2', '3-2', '3-1'
          )
        GROUP BY balls, strikes, pitch_name
        HAVING COUNT(*) >= 10
        ORDER BY balls, strikes, pitches DESC
    """).df()

    con.close()

    # ── Velocity signal ───────────────────────────────────
    velo_signal = 'STABLE: Velocity on track'
    velo_flag = False

    if len(velo_trend) >= 3 and not summary.empty:
        recent_velo = velo_trend['avg_velo'].head(3).mean()
        season_velo = summary['season_avg_velo'].iloc[0]
        if season_velo:
            drop = round(season_velo - recent_velo, 1)
            if drop >= THRESHOLDS['velo_drop_concern']:
                velo_signal = (f"⚠ CONCERN: Velocity down "
                               f"{drop} mph vs season avg")
                velo_flag = True
            elif drop >= THRESHOLDS['velo_drop_watch']:
                velo_signal = (f"👀 WATCH: Velocity down "
                               f"{drop} mph recently")
                velo_flag = True

    return {
        'pitcher_id':    pitcher_id,
        'name':          name,
        'summary':       summary,
        'pitch_mix':     pitch_mix,
        'recent_mix':    recent_mix,
        'velo_trend':    velo_trend,
        'velo_signal':   velo_signal,
        'velo_flag':     velo_flag,
        'count_profile': count_profile,
        'season_filter': season_filter
    }


# ─────────────────────────────────────────────────────────────
# BATTER PROFILE
# ─────────────────────────────────────────────────────────────

def get_batter_profile(batter_id: int,
                       season: int = None) -> dict:
    """
    Builds a complete batter profile including performance
    vs each pitch type, zone tendencies, recent form,
    and hot/cold status.

    Args:
        batter_id: MLBAM batter ID
        season:    Filter to specific season

    Returns:
        Dictionary with full batter profile
    """
    con = get_connection()

    season_filter = (
        f"AND YEAR(game_date) = {season}" if season else ""
    )

    # ── Player name ───────────────────────────────────────
    name_row = con.execute(f"""
        SELECT name_first || ' ' || name_last
        FROM players WHERE mlbam_id = {batter_id}
    """).fetchone()
    name = name_row[0] if name_row else f"Batter {batter_id}"

    # ── Season summary ────────────────────────────────────
    summary = con.execute(f"""
        SELECT
            COUNT(DISTINCT game_date)                   as games,
            COUNT(*)                                    as total_pitches,
            ROUND(AVG(CASE WHEN launch_speed IS NOT NULL
                  THEN launch_speed END), 1)            as avg_exit_velo,
            ROUND(MAX(launch_speed), 1)                 as max_exit_velo,
            ROUND(AVG(CASE WHEN launch_angle IS NOT NULL
                  THEN launch_angle END), 1)            as avg_launch_angle,
            ROUND(
                COUNT(CASE WHEN launch_speed >= 95
                      THEN 1 END) * 100.0 /
                NULLIF(COUNT(CASE WHEN launch_speed IS NOT NULL
                      THEN 1 END), 0), 1
            )                                           as hard_hit_pct,
            ROUND(
                COUNT(CASE WHEN launch_speed >= 98
                      AND launch_angle BETWEEN 26 AND 30
                      THEN 1 END) * 100.0 /
                NULLIF(COUNT(CASE WHEN launch_speed IS NOT NULL
                      THEN 1 END), 0), 1
            )                                           as barrel_pct,
            ROUND(AVG(estimated_woba_using_speedangle), 3)
                                                        as xwoba,
            ROUND(AVG(estimated_ba_using_speedangle), 3)
                                                        as xba,
            ROUND(
                COUNT(CASE WHEN description LIKE '%swinging%'
                      THEN 1 END) * 100.0 / COUNT(*), 1
            )                                           as swing_pct,
            ROUND(
                COUNT(CASE WHEN description = 'swinging_strike'
                      THEN 1 END) * 100.0 /
                NULLIF(COUNT(CASE WHEN description LIKE '%swinging%'
                      THEN 1 END), 0), 1
            )                                           as miss_pct,
            ROUND(
                COUNT(CASE WHEN zone NOT BETWEEN 1 AND 9
                      AND description LIKE '%swinging%'
                      THEN 1 END) * 100.0 /
                NULLIF(COUNT(CASE WHEN zone NOT BETWEEN 1 AND 9
                      THEN 1 END), 0), 1
            )                                           as chase_pct
        FROM pitches
        WHERE batter = {batter_id}
          AND pitch_type IS NOT NULL
          {season_filter}
    """).df()

    # ── Performance vs each pitch type ───────────────────
    vs_pitch_types = con.execute(f"""
        SELECT
            pitch_name,
            pitch_type,
            COUNT(*)                                    as pitches_seen,
            ROUND(COUNT(*) * 100.0 /
                SUM(COUNT(*)) OVER (), 1)               as pct_of_pitches,
            ROUND(
                COUNT(CASE WHEN description LIKE '%swinging%'
                      THEN 1 END) * 100.0 / COUNT(*), 1
            )                                           as swing_pct,
            ROUND(
                COUNT(CASE WHEN description = 'swinging_strike'
                      THEN 1 END) * 100.0 /
                NULLIF(COUNT(CASE WHEN description LIKE '%swinging%'
                      THEN 1 END), 0), 1
            )                                           as miss_pct,
            ROUND(
                COUNT(CASE WHEN zone NOT BETWEEN 1 AND 9
                      AND description LIKE '%swinging%'
                      THEN 1 END) * 100.0 /
                NULLIF(COUNT(CASE WHEN zone NOT BETWEEN 1 AND 9
                      THEN 1 END), 0), 1
            )                                           as chase_pct,
            ROUND(AVG(CASE WHEN launch_speed IS NOT NULL
                  THEN launch_speed END), 1)            as avg_exit_velo,
            ROUND(AVG(CASE WHEN launch_angle IS NOT NULL
                  THEN launch_angle END), 1)            as avg_launch_angle,
            ROUND(
                COUNT(CASE WHEN launch_speed >= 95
                      THEN 1 END) * 100.0 /
                NULLIF(COUNT(CASE WHEN launch_speed IS NOT NULL
                      THEN 1 END), 0), 1
            )                                           as hard_hit_pct,
            ROUND(AVG(estimated_woba_using_speedangle), 3)
                                                        as xwoba,
            ROUND(AVG(estimated_ba_using_speedangle), 3)
                                                        as xba
        FROM pitches
        WHERE batter = {batter_id}
          AND pitch_type IS NOT NULL
          {season_filter}
        GROUP BY pitch_name, pitch_type
        HAVING COUNT(*) >= {THRESHOLDS['min_pitches_small']}
        ORDER BY pitches_seen DESC
    """).df()

    # ── Recent form last 14 days ──────────────────────────
    recent_form = con.execute(f"""
        SELECT
            COUNT(DISTINCT game_date)                   as games,
            COUNT(*)                                    as pitches,
            ROUND(AVG(CASE WHEN launch_speed IS NOT NULL
                  THEN launch_speed END), 1)            as avg_exit_velo,
            ROUND(
                COUNT(CASE WHEN launch_speed >= 95
                      THEN 1 END) * 100.0 /
                NULLIF(COUNT(CASE WHEN launch_speed IS NOT NULL
                      THEN 1 END), 0), 1
            )                                           as hard_hit_pct,
            ROUND(AVG(estimated_woba_using_speedangle), 3)
                                                        as xwoba,
            ROUND(
                COUNT(CASE WHEN description = 'swinging_strike'
                      THEN 1 END) * 100.0 /
                NULLIF(COUNT(CASE WHEN description LIKE '%swinging%'
                      THEN 1 END), 0), 1
            )                                           as miss_pct,
            ROUND(
                COUNT(CASE WHEN zone NOT BETWEEN 1 AND 9
                      AND description LIKE '%swinging%'
                      THEN 1 END) * 100.0 /
                NULLIF(COUNT(CASE WHEN zone NOT BETWEEN 1 AND 9
                      THEN 1 END), 0), 1
            )                                           as chase_pct
        FROM pitches
        WHERE batter = {batter_id}
          AND pitch_type IS NOT NULL
          AND game_date >= CURRENT_DATE - INTERVAL '14 days'
    """).df()

    # ── Zone performance ──────────────────────────────────
    zone_performance = con.execute(f"""
        SELECT
            zone,
            COUNT(*)                                    as pitches,
            ROUND(
                COUNT(CASE WHEN description LIKE '%swinging%'
                      THEN 1 END) * 100.0 / COUNT(*), 1
            )                                           as swing_pct,
            ROUND(AVG(estimated_woba_using_speedangle), 3)
                                                        as xwoba,
            ROUND(AVG(CASE WHEN launch_speed IS NOT NULL
                  THEN launch_speed END), 1)            as avg_exit_velo
        FROM pitches
        WHERE batter = {batter_id}
          AND zone IS NOT NULL
          AND zone BETWEEN 1 AND 14
          {season_filter}
        GROUP BY zone
        ORDER BY zone
    """).df()

    con.close()

    # ── Hot cold status ───────────────────────────────────
    hot_cold = 'NEUTRAL'
    hot_cold_detail = ''

    if (not summary.empty and not recent_form.empty and
            recent_form.iloc[0]['games'] and
            recent_form.iloc[0]['games'] >= 3):

        season_xwoba = summary.iloc[0]['xwoba']
        recent_xwoba = recent_form.iloc[0]['xwoba']

        if season_xwoba and recent_xwoba:
            delta = round(recent_xwoba - season_xwoba, 3)

            if delta >= THRESHOLDS['hot_batter_delta']:
                hot_cold = '🔥 HOT'
                hot_cold_detail = (
                    f"xwOBA last 14d: {recent_xwoba} "
                    f"vs season: {season_xwoba} "
                    f"(+{delta})"
                )
            elif delta <= THRESHOLDS['cold_batter_delta']:
                hot_cold = '🧊 COLD'
                hot_cold_detail = (
                    f"xwOBA last 14d: {recent_xwoba} "
                    f"vs season: {season_xwoba} "
                    f"({delta})"
                )
            else:
                hot_cold_detail = (
                    f"xwOBA last 14d: {recent_xwoba} "
                    f"vs season: {season_xwoba}"
                )

    return {
        'batter_id':        batter_id,
        'name':             name,
        'summary':          summary,
        'vs_pitch_types':   vs_pitch_types,
        'recent_form':      recent_form,
        'zone_performance': zone_performance,
        'hot_cold':         hot_cold,
        'hot_cold_detail':  hot_cold_detail
    }


# ─────────────────────────────────────────────────────────────
# MATCHUP ANALYSIS ENGINE
# ─────────────────────────────────────────────────────────────

def analyze_matchup(pitcher_profile: dict,
                    batter_profile: dict,
                    h2h: dict = None,
                    custom_notes: str = None) -> dict:
    """
    Core matchup analysis engine.
    Compares pitcher and batter profiles pitch by pitch,
    identifies edges, and generates talking points.

    Your professional notes are injected via custom_notes.
    Adjust THRESHOLDS at top of file to tune logic.

    Args:
        pitcher_profile: From get_pitcher_profile()
        batter_profile:  From get_batter_profile()
        h2h:             From head_to_head_history()
        custom_notes:    Your professional observations

    Returns:
        Dictionary with full matchup analysis
    """
    pitcher_name = pitcher_profile['name']
    batter_name = batter_profile['name']

    pitch_mix = pitcher_profile['pitch_mix']
    vs_pitches = batter_profile['vs_pitch_types']

    advantages = []
    vulnerabilities = []
    talking_points = []
    sample_warnings = []
    pitch_analysis = []

    # ── Head to head historical edge ─────────────────────
    h2h_edge = None
    if h2h and not h2h['career_summary'].empty:
        c = h2h['career_summary'].iloc[0]
        total = int(c['total_pitches']) if c['total_pitches'] else 0
        if total >= THRESHOLDS['min_pitches_small']:
            career_xwoba = c['career_xwoba']
            if career_xwoba:
                if career_xwoba >= THRESHOLDS['xwoba_danger']:
                    h2h_edge = 'BATTER'
                    advantages.append(
                        f"Historical edge: {batter_name} career "
                        f"xwOBA of {career_xwoba} vs "
                        f"{pitcher_name} ({total} pitches)"
                    )
                elif career_xwoba <= THRESHOLDS['xwoba_elite']:
                    h2h_edge = 'PITCHER'
                    advantages.append(
                        f"Historical edge: {pitcher_name} holding "
                        f"{batter_name} to {career_xwoba} xwOBA "
                        f"career ({total} pitches)"
                    )

    # ── Pitch by pitch analysis ───────────────────────────
    for _, pitch in pitch_mix.iterrows():
        pitch_name = pitch['pitch_name']
        pitcher_whiff = pitch['whiff_pct']
        pitcher_xwoba = pitch['xwoba_allowed']
        pitcher_velo = pitch['avg_velo']
        pitcher_usage = pitch['usage_pct']
        pitcher_chase = pitch.get('induced_chase_pct')

        batter_vs = vs_pitches[
            vs_pitches['pitch_name'] == pitch_name
        ]

        if batter_vs.empty:
            pitch_analysis.append({
                'pitch':            pitch_name,
                'pitcher_usage':    pitcher_usage,
                'pitcher_velo':     pitcher_velo,
                'pitcher_whiff':    pitcher_whiff,
                'pitcher_xwoba':    pitcher_xwoba,
                'batter_xwoba':     None,
                'batter_miss':      None,
                'batter_chase':     None,
                'batter_hard_hit':  None,
                'batter_exit_velo': None,
                'sample':           0,
                'edge':             'NO DATA'
            })
            sample_warnings.append(
                f"No data: {batter_name} vs {pitch_name}"
            )
            continue

        row = batter_vs.iloc[0]
        batter_xwoba = row['xwoba']
        batter_miss = row['miss_pct']
        batter_hard_hit = row['hard_hit_pct']
        batter_chase = row.get('chase_pct')
        batter_exit_velo = row.get('avg_exit_velo')
        sample = row['pitches_seen']

        if sample < THRESHOLDS['min_pitches_reliable']:
            sample_warnings.append(
                f"Small sample ({sample}px): "
                f"{batter_name} vs {pitch_name}"
            )

        # ── Edge scoring ──────────────────────────────────
        edge_score = 0

        # Pitcher advantages
        if (pitcher_whiff >= THRESHOLDS['whiff_good'] and
                batter_miss and batter_miss >= 25):
            edge_score += 2

        if (pitcher_xwoba and
                pitcher_xwoba <= THRESHOLDS['xwoba_elite']):
            edge_score += 2
        elif (pitcher_xwoba and
              pitcher_xwoba <= THRESHOLDS['xwoba_average']):
            edge_score += 1

        if (batter_chase and
                batter_chase >= THRESHOLDS['chase_high']):
            edge_score += 1

        # Batter advantages
        if (batter_xwoba and
                batter_xwoba >= THRESHOLDS['xwoba_danger']):
            edge_score -= 2

        if (batter_hard_hit and
                batter_hard_hit >= THRESHOLDS['hard_hit_elite']):
            edge_score -= 2
        elif (batter_hard_hit and
              batter_hard_hit >= THRESHOLDS['hard_hit_concern']):
            edge_score -= 1

        # Classify edge
        if edge_score >= 3:
            edge = '✅ PITCHER DOMINANT'
        elif edge_score == 2:
            edge = '+ PITCHER ADVANTAGE'
        elif edge_score == 1:
            edge = '~ SLIGHT PITCHER EDGE'
        elif edge_score == 0:
            edge = '= NEUTRAL'
        elif edge_score == -1:
            edge = '~ SLIGHT BATTER EDGE'
        elif edge_score == -2:
            edge = '- BATTER ADVANTAGE'
        else:
            edge = '❌ BATTER DOMINANT'

        pitch_analysis.append({
            'pitch':            pitch_name,
            'pitcher_usage':    pitcher_usage,
            'pitcher_velo':     pitcher_velo,
            'pitcher_whiff':    pitcher_whiff,
            'pitcher_xwoba':    pitcher_xwoba,
            'batter_xwoba':     batter_xwoba,
            'batter_miss':      batter_miss,
            'batter_chase':     batter_chase,
            'batter_hard_hit':  batter_hard_hit,
            'batter_exit_velo': batter_exit_velo,
            'sample':           sample,
            'edge':             edge
        })

        # ── Talking points ────────────────────────────────

        # High usage pitch with clear edge
        if pitcher_usage >= 15:

            if (batter_chase and
                    batter_chase >= THRESHOLDS['chase_elite']):
                talking_points.append(
                    f"{batter_name} chases {pitch_name} at "
                    f"{batter_chase}% out-of-zone rate — "
                    f"expand the zone late in counts"
                )

            if (batter_miss and batter_miss >= 30 and
                    pitcher_whiff >= THRESHOLDS['whiff_good']):
                talking_points.append(
                    f"High K potential: {pitcher_name} "
                    f"{pitch_name} ({pitcher_whiff}% whiff) "
                    f"vs {batter_name} "
                    f"({batter_miss}% miss rate on swings)"
                )

            if (batter_xwoba and
                    batter_xwoba >= THRESHOLDS['xwoba_danger']):
                talking_points.append(
                    f"Avoid {pitch_name} to {batter_name} — "
                    f"{batter_xwoba} xwOBA against this pitch "
                    f"type is a significant liability"
                )

        # Vulnerabilities
        if (batter_xwoba and
                batter_xwoba >= THRESHOLDS['xwoba_danger']):
            vulnerabilities.append(
                f"{batter_name} vs {pitch_name}: "
                f"{batter_xwoba} xwOBA | "
                f"{batter_hard_hit}% hard hit"
            )

        # Pitcher advantages
        if (pitcher_xwoba and
                pitcher_xwoba <= THRESHOLDS['xwoba_average'] and
                pitcher_whiff >= THRESHOLDS['whiff_good']):
            advantages.append(
                f"{pitcher_name} {pitch_name}: "
                f"{pitcher_xwoba} xwOBA allowed | "
                f"{pitcher_whiff}% whiff"
            )

    # ── Velocity alert ────────────────────────────────────
    if pitcher_profile.get('velo_flag'):
        talking_points.insert(
            0, f"VELOCITY ALERT: {pitcher_profile['velo_signal']}"
        )

    # ── Hot cold batter flag ──────────────────────────────
    if batter_profile['hot_cold'] != 'NEUTRAL':
        talking_points.append(
            f"{batter_name} is {batter_profile['hot_cold']} — "
            f"{batter_profile['hot_cold_detail']}"
        )

    return {
        'pitcher':          pitcher_name,
        'batter':           batter_name,
        'pitch_analysis':   pd.DataFrame(pitch_analysis),
        'advantages':       advantages,
        'vulnerabilities':  vulnerabilities,
        'talking_points':   talking_points,
        'sample_warnings':  sample_warnings,
        'h2h_edge':         h2h_edge,
        'custom_notes':     custom_notes
    }


# ─────────────────────────────────────────────────────────────
# REPORT PRINTER
# ─────────────────────────────────────────────────────────────

def _print_pitcher_section(pitcher: dict):
    """Prints the pitcher section of the report."""

    print(f"\n{'═' * 65}")
    print(f"  PITCHER: {pitcher['name'].upper()}")
    print(f"{'═' * 65}")

    if not pitcher['summary'].empty:
        s = pitcher['summary'].iloc[0]
        print(f"\n  Season Summary:")
        print(f"  Appearances: {int(s['appearances'])} | "
              f"Pitches: {int(s['total_pitches']):,}")
        print(f"  Avg Velo:    {s['season_avg_velo']} mph | "
              f"Peak: {s['season_peak_velo']} mph")
        print(f"  Whiff%:      {s['overall_whiff_pct']}% | "
              f"Zone%: {s['zone_pct']}% | "
              f"Strike%: {s['strike_pct']}%")
        print(f"  xwOBA:       {s['overall_xwoba']} | "
              f"Hard Hit%: {s['overall_hard_hit_pct']}%")

    if pitcher['velo_flag']:
        print(f"\n  {pitcher['velo_signal']}")

    if not pitcher['pitch_mix'].empty:
        print(f"\n  Pitch Arsenal:")
        print(f"  {'Pitch':<18} {'Use%':>5} {'Velo':>5} "
              f"{'Spin':>6} {'Whiff%':>7} {'Zone%':>6} "
              f"{'xwOBA':>6} {'HH%':>5}")
        print(f"  {'─' * 60}")
        for _, p in pitcher['pitch_mix'].iterrows():
            print(f"  {p['pitch_name']:<18} "
                  f"{p['usage_pct']:>5} "
                  f"{p['avg_velo']:>5} "
                  f"{int(p['avg_spin']) if p['avg_spin'] else 0:>6} "
                  f"{p['whiff_pct']:>7} "
                  f"{p['zone_pct']:>6} "
                  f"{p['xwoba_allowed']:>6} "
                  f"{str(p['hard_hit_pct']) + '%':>5}")

    if not pitcher['recent_mix'].empty:
        print(f"\n  Recent Form (Last 14 Days):")
        print(f"  {'Pitch':<18} {'Px':>4} {'Use%':>5} "
              f"{'Velo':>5} {'Whiff%':>7} {'xwOBA':>6}")
        print(f"  {'─' * 48}")
        for _, p in pitcher['recent_mix'].iterrows():
            print(f"  {p['pitch_name']:<18} "
                  f"{int(p['pitches']):>4} "
                  f"{p['usage_pct']:>5} "
                  f"{p['avg_velo']:>5} "
                  f"{p['whiff_pct']:>7} "
                  f"{p['xwoba_allowed']:>6}")

    if not pitcher['count_profile'].empty:
        print(f"\n  Key Count Tendencies:")
        current_count = None
        for _, row in pitcher['count_profile'].iterrows():
            if row['count'] != current_count:
                current_count = row['count']
                print(f"\n  [{current_count}]")
            print(f"    {row['pitch_name']:<18} "
                  f"{row['usage_pct']:>5}% | "
                  f"Velo: {row['avg_velo']} | "
                  f"Whiff: {row['whiff_pct']}% | "
                  f"xwOBA: {row['xwoba_allowed']}")


def _print_matchup_section(matchup: dict,
                           batter_profile: dict,
                           h2h: dict):
    """Prints one batter matchup section."""

    hot_cold = batter_profile['hot_cold']
    hot_cold_str = f" {hot_cold}" if hot_cold != 'NEUTRAL' else ''

    print(f"\n{'─' * 65}")
    print(f"  vs {batter_profile['name'].upper()}{hot_cold_str}")
    print(f"{'─' * 65}")

    # Batter summary
    if not batter_profile['summary'].empty:
        s = batter_profile['summary'].iloc[0]
        print(f"\n  Season: {int(s['games'])}G | "
              f"Exit Velo: {s['avg_exit_velo']} | "
              f"Hard Hit: {s['hard_hit_pct']}% | "
              f"Barrel: {s['barrel_pct']}% | "
              f"xwOBA: {s['xwoba']}")
        print(f"  Swing%: {s['swing_pct']}% | "
              f"Miss%: {s['miss_pct']}% | "
              f"Chase%: {s['chase_pct']}%")

    if batter_profile['hot_cold_detail']:
        print(f"  Form:   {batter_profile['hot_cold_detail']}")

    # Head to head history
    if h2h and not h2h['career_summary'].empty:
        c = h2h['career_summary'].iloc[0]
        total = int(c['total_pitches']) if c['total_pitches'] else 0

        print(f"\n  Head to Head History:")

        if total == 0:
            print(f"  No career data in database "
                  f"— pull additional seasons for history")
        else:
            ab = int(c['at_bats']) if c['at_bats'] else 0
            hits = int(c['hits']) if c['hits'] else 0
            hrs = int(c['home_runs']) if c['home_runs'] else 0
            ks = int(c['strikeouts']) if c['strikeouts'] else 0
            bbs = int(c['walks']) if c['walks'] else 0
            avg = round(hits/ab, 3) if ab > 0 else 0.000

            print(f"  Career: {int(c['games_faced'])}G | "
                  f"{total}px | "
                  f"{hits}H {hrs}HR {ks}K {bbs}BB "
                  f"in {ab}AB | "
                  f"AVG: {avg:.3f} | "
                  f"xwOBA: {c['career_xwoba']}")

            if not h2h['by_season'].empty:
                for _, row in h2h['by_season'].iterrows():
                    print(f"    {int(row['season'])}: "
                          f"{int(row['hits'])}H "
                          f"{int(row['home_runs'])}HR "
                          f"{int(row['strikeouts'])}K "
                          f"in {int(row['at_bats'])}AB | "
                          f"xwOBA: {row['xwoba']} | "
                          f"Exit Velo: {row['avg_exit_velo']}")

            if not h2h['pitch_breakdown'].empty:
                print(f"\n  Pitch Mix vs This Batter Specifically:")
                for _, row in h2h['pitch_breakdown'].iterrows():
                    if int(row['pitches']) >= 5:
                        print(f"    {row['pitch_name']:<18} "
                              f"{int(row['pitches'])}px "
                              f"({row['usage_pct']}%) | "
                              f"Velo: {row['avg_velo']} | "
                              f"Whiff: {row['whiff_pct']}% | "
                              f"Chase: {row['chase_pct']}% | "
                              f"xwOBA: {row['xwoba']}")

    # Pitch matchup breakdown
    pa = matchup['pitch_analysis']
    if not pa.empty:
        print(f"\n  Pitch Matchup Breakdown "
              f"(league-wide vs pitch type):")
        print(f"  {'Pitch':<18} {'Use%':>5} {'P-Whiff':>8} "
              f"{'B-xwOBA':>8} {'B-Miss':>7} "
              f"{'B-HH%':>6} {'Px':>5}  {'Edge'}")
        print(f"  {'─' * 70}")
        for _, row in pa.iterrows():
            bxw = f"{row['batter_xwoba']:.3f}" if pd.notna(
                row.get('batter_xwoba')) else '  N/A'
            bmiss = f"{row['batter_miss']:.1f}%" if pd.notna(
                row.get('batter_miss')) else '  N/A'
            bhh = f"{row['batter_hard_hit']:.1f}%" if pd.notna(
                row.get('batter_hard_hit')) else '  N/A'
            sample = int(row['sample']) if row['sample'] else 0

            print(f"  {row['pitch']:<18} "
                  f"{row['pitcher_usage']:>5} "
                  f"{row['pitcher_whiff']:>7}% "
                  f"{bxw:>8} "
                  f"{bmiss:>7} "
                  f"{bhh:>6} "
                  f"{sample:>5}  "
                  f"{row['edge']}")

    # Advantages
    if matchup['advantages']:
        print(f"\n  ✅ Pitcher Advantages:")
        for a in matchup['advantages']:
            print(f"     + {a}")

    # Vulnerabilities
    if matchup['vulnerabilities']:
        print(f"\n  ❌ Batter Advantages:")
        for v in matchup['vulnerabilities']:
            print(f"     - {v}")

    # Talking points
    if matchup['talking_points']:
        print(f"\n  → Key Talking Points:")
        for t in matchup['talking_points']:
            print(f"     • {t}")

    # Professional notes
    if matchup['custom_notes']:
        print(f"\n  ★ Professional Notes:")
        print(f"     {matchup['custom_notes']}")

    # Sample warnings
    if matchup['sample_warnings']:
        print(f"\n  ⚠ Sample Warnings:")
        for w in matchup['sample_warnings']:
            print(f"     {w}")


# ─────────────────────────────────────────────────────────────
# MASTER REPORT FUNCTION
# ─────────────────────────────────────────────────────────────

def generate_matchup_report(pitcher_id: int,
                             batter_ids: list,
                             game_date: str = None,
                             season: int = None,
                             custom_notes: dict = None,
                             print_report: bool = True,
                             min_pitches_filter: int = 0
                             ) -> dict:
    """
    Master function that generates a complete matchup report
    for one pitcher against a list of batters.

    Includes:
    - Full pitcher profile with arsenal and recent form
    - Per batter head to head career history
    - Pitch type matchup breakdown
    - Hot cold status
    - Edge classification per pitch
    - Talking points and professional notes

    Args:
        pitcher_id:         MLBAM ID of the starting pitcher
        batter_ids:         List of MLBAM IDs for batters
        game_date:          Date string 'YYYY-MM-DD'
        season:             Season to filter historical data
        custom_notes:       Dict {batter_id: 'your note'}
        print_report:       Print to terminal
        min_pitches_filter: Skip batters with fewer pitches
                            in database than this threshold

    Example:
        report = generate_matchup_report(
            pitcher_id=677960,
            batter_ids=[605141, 592450],
            season=2025,
            custom_notes={
                605141: 'Betts laying off sliders recently'
            }
        )
    """
    notes = custom_notes or {}

    # ── Header ────────────────────────────────────────────
    print(f"\n{'═' * 65}")
    print(f"  MATCHUP REPORT")
    if game_date:
        print(f"  Game Date: {game_date}")
    if season:
        print(f"  Data Filter: {season} season")
    print(f"{'═' * 65}")

    # ── Build pitcher profile ─────────────────────────────
    pitcher = get_pitcher_profile(pitcher_id, season=season)

    if print_report:
        _print_pitcher_section(pitcher)

    # ── Process each batter ───────────────────────────────
    all_matchups = []

    for batter_id in batter_ids:
        batter = get_batter_profile(batter_id, season=season)

        # Skip batters with very little data
        if (min_pitches_filter > 0 and
                not batter['summary'].empty):
            total = batter['summary'].iloc[0]['total_pitches']
            if total and total < min_pitches_filter:
                continue

        # Get head to head history
        h2h = head_to_head_history(pitcher_id, batter_id)

        # Analyze matchup
        matchup = analyze_matchup(
            pitcher,
            batter,
            h2h=h2h,
            custom_notes=notes.get(batter_id)
        )

        all_matchups.append({
            'batter':  batter,
            'matchup': matchup,
            'h2h':     h2h
        })

        if print_report:
            _print_matchup_section(matchup, batter, h2h)

    # ── Footer ────────────────────────────────────────────
    if print_report:
        print(f"\n{'═' * 65}")
        print(f"  END OF MATCHUP REPORT")
        print(f"{'═' * 65}\n")

    return {
        'pitcher':   pitcher,
        'matchups':  all_matchups,
        'game_date': game_date,
        'season':    season
    }


# ─────────────────────────────────────────────────────────────
# CONVENIENCE WRAPPER
# ─────────────────────────────────────────────────────────────

def quick_matchup(pitcher_last: str,
                  pitcher_first: str,
                  batter_last_first_pairs: list,
                  season: int = None,
                  game_date: str = None,
                  custom_notes: dict = None,
                  min_pitches_filter: int = 0) -> dict:
    """
    Name based convenience wrapper for generate_matchup_report.
    Looks up MLBAM IDs automatically from player names.

    Args:
        pitcher_last:            Pitcher last name
        pitcher_first:           Pitcher first name
        batter_last_first_pairs: List of (last, first) tuples
        season:                  Season filter
        game_date:               Game date string
        custom_notes:            Dict {batter_name: note}
        min_pitches_filter:      Skip batters below threshold

    Example:
        quick_matchup(
            pitcher_last='degrom',
            pitcher_first='jacob',
            batter_last_first_pairs=[
                ('judge', 'aaron'),
                ('ohtani', 'shohei')
            ],
            season=2025,
            game_date='2026-04-05',
            custom_notes={
                'aaron judge': 'Pulling off on breaking balls'
            }
        )
    """
    from src.player_lookup import get_player_id

    pitcher_id = get_player_id(pitcher_last, pitcher_first)
    if not pitcher_id:
        print(f"Pitcher not found: {pitcher_first} {pitcher_last}")
        return {}

    batter_ids = []
    name_to_id = {}

    for last, first in batter_last_first_pairs:
        bid = get_player_id(last, first)
        if bid:
            batter_ids.append(bid)
            full_name = f"{first} {last}".lower()
            name_to_id[full_name] = bid

    if not batter_ids:
        print("No batters found")
        return {}

    # Convert name keyed notes to ID keyed
    id_notes = {}
    if custom_notes:
        for name, note in custom_notes.items():
            if name.lower() in name_to_id:
                id_notes[name_to_id[name.lower()]] = note

    return generate_matchup_report(
        pitcher_id=pitcher_id,
        batter_ids=batter_ids,
        game_date=game_date,
        season=season,
        custom_notes=id_notes,
        print_report=True,
        min_pitches_filter=min_pitches_filter
    )


if __name__ == "__main__":
    print("Matchup report module ready")
    print()
    print("Quick start:")
    print("  quick_matchup(")
    print("      pitcher_last='degrom',")
    print("      pitcher_first='jacob',")
    print("      batter_last_first_pairs=[")
    print("          ('judge', 'aaron'),")
    print("          ('ohtani', 'shohei')")
    print("      ],")
    print("      season=2025,")
    print("      game_date='2026-04-05'")
    print("  )")