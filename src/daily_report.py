"""
daily_report.py

Generates a complete daily baseball intelligence report
combining the full slate, weather for every game,
and matchup analysis for any specified team.

Designed to run each morning before games start.
Output is clean, digestible, and actionable.

Usage:
    from src.daily_report import run_daily_report
    run_daily_report(focus_team='NYY', season=2025)
"""

import pandas as pd
from datetime import date
from src.daily_slate import (
    get_todays_slate,
    print_slate,
    get_probable_pitchers,
    build_game_matchup_inputs,
    get_team_id,
    get_lineup_batters,
    MLB_TEAM_MAP
)
from src.matchup_report import (
    get_pitcher_profile,
    get_batter_profile,
    analyze_matchup,
    _print_pitcher_section,
    _print_matchup_section
)
from src.matchup_queries import head_to_head_history
from src.weather import get_weather, print_weather_report
from src.database import get_connection


# ─────────────────────────────────────────────────────────
# HOT/COLD THRESHOLDS
# Research backed — see weather.py for citations
# ─────────────────────────────────────────────────────────
HOT_COLD_CONFIG = {

    # Minimum games in window before flagging
    'min_games_window':     5,

    # Window in days
    'window_days':          21,

    # xwOBA delta thresholds
    'hot_xwoba_delta':      0.080,
    'cold_xwoba_delta':    -0.080,

    # Exit velocity delta thresholds (mph)
    # Must ALSO meet this to confirm hot/cold
    'hot_ev_delta':         1.5,
    'cold_ev_delta':       -1.5,

    # Strikeout rate change confirmation (percentage points)
    'cold_k_rate_increase': 5.0,
}


def get_hot_cold_status(batter_id: int,
                        season: int = None) -> dict:
    """
    Research-backed hot/cold determination using
    multi-metric confirmation approach.

    Requires BOTH xwOBA delta AND exit velocity delta
    to confirm hot/cold status — reduces false positives
    from pure variance in small samples.

    Args:
        batter_id: MLBAM batter ID
        season:    Season filter

    Returns:
        Dict with status, detail, and supporting metrics
    """
    con = get_connection()

    season_filter = (
        f"AND YEAR(game_date) = {season}" if season else ""
    )
    days = HOT_COLD_CONFIG['window_days']
    min_games = HOT_COLD_CONFIG['min_games_window']

    # Season baseline
    baseline = con.execute(f"""
        SELECT
            COUNT(DISTINCT game_date)               as games,
            ROUND(AVG(estimated_woba_using_speedangle), 3)
                                                    as xwoba,
            ROUND(AVG(CASE WHEN launch_speed IS NOT NULL
                  THEN launch_speed END), 1)        as avg_ev,
            ROUND(
                COUNT(CASE WHEN events = 'strikeout'
                      THEN 1 END) * 100.0 /
                NULLIF(COUNT(CASE WHEN events IS NOT NULL
                      AND events NOT IN (
                          'caught_stealing_2b', 'wild_pitch'
                      ) THEN 1 END), 0), 1
            )                                       as k_rate
        FROM pitches
        WHERE batter = {batter_id}
          AND pitch_type IS NOT NULL
          {season_filter}
    """).df()

    # Recent form
    recent = con.execute(f"""
        SELECT
            COUNT(DISTINCT game_date)               as games,
            ROUND(AVG(estimated_woba_using_speedangle), 3)
                                                    as xwoba,
            ROUND(AVG(CASE WHEN launch_speed IS NOT NULL
                  THEN launch_speed END), 1)        as avg_ev,
            ROUND(
                COUNT(CASE WHEN events = 'strikeout'
                      THEN 1 END) * 100.0 /
                NULLIF(COUNT(CASE WHEN events IS NOT NULL
                      AND events NOT IN (
                          'caught_stealing_2b', 'wild_pitch'
                      ) THEN 1 END), 0), 1
            )                                       as k_rate
        FROM pitches
        WHERE batter = {batter_id}
          AND pitch_type IS NOT NULL
          AND game_date >= CURRENT_DATE - INTERVAL '{days} days'
    """).df()

    con.close()

    # Default response
    result = {
        'status':       'NEUTRAL',
        'emoji':        '',
        'detail':       '',
        'xwoba_delta':  None,
        'ev_delta':     None,
        'k_rate_delta': None,
        'games_recent': 0,
        'confirmed':    False
    }

    if baseline.empty or recent.empty:
        return result

    b = baseline.iloc[0]
    r = recent.iloc[0]

    games_recent = int(r['games']) if r['games'] else 0
    result['games_recent'] = games_recent

    # Not enough recent games to determine
    if games_recent < min_games:
        result['detail'] = (
            f"Only {games_recent} games in last {days} days "
            f"— insufficient sample for hot/cold designation"
        )
        return result

    # Calculate deltas
    xwoba_delta = None
    ev_delta = None
    k_rate_delta = None

    if r['xwoba'] and b['xwoba']:
        xwoba_delta = round(r['xwoba'] - b['xwoba'], 3)
        result['xwoba_delta'] = xwoba_delta

    if r['avg_ev'] and b['avg_ev']:
        ev_delta = round(r['avg_ev'] - b['avg_ev'], 1)
        result['ev_delta'] = ev_delta

    if r['k_rate'] and b['k_rate']:
        k_rate_delta = round(r['k_rate'] - b['k_rate'], 1)
        result['k_rate_delta'] = k_rate_delta

    # ── HOT determination ─────────────────────────────────
    # Requires BOTH xwOBA and exit velocity above threshold
    if (xwoba_delta and
            xwoba_delta >= HOT_COLD_CONFIG['hot_xwoba_delta'] and
            ev_delta and
            ev_delta >= HOT_COLD_CONFIG['hot_ev_delta']):

        result['status'] = 'HOT'
        result['emoji'] = '🔥'
        result['confirmed'] = True
        result['detail'] = (
            f"xwOBA: {r['xwoba']} vs season {b['xwoba']} "
            f"(+{xwoba_delta}) | "
            f"Exit Velo: {r['avg_ev']} vs {b['avg_ev']} "
            f"(+{ev_delta} mph) — "
            f"both metrics confirm hot streak over "
            f"{games_recent} games"
        )

    # xwOBA only hot — flag but note unconfirmed
    elif (xwoba_delta and
          xwoba_delta >= HOT_COLD_CONFIG['hot_xwoba_delta']):
        result['status'] = 'WARM'
        result['emoji'] = '📈'
        result['confirmed'] = False
        result['detail'] = (
            f"xwOBA trending up: {r['xwoba']} vs "
            f"season {b['xwoba']} (+{xwoba_delta}) | "
            f"Exit velo not confirming — "
            f"may be batted ball luck rather than "
            f"genuine improvement"
        )

    # ── COLD determination ────────────────────────────────
    # Requires BOTH xwOBA and exit velocity below threshold
    elif (xwoba_delta and
          xwoba_delta <= HOT_COLD_CONFIG['cold_xwoba_delta'] and
          ev_delta and
          ev_delta <= HOT_COLD_CONFIG['cold_ev_delta']):

        result['status'] = 'COLD'
        result['emoji'] = '🧊'
        result['confirmed'] = True

        # Check if K rate also elevated — mechanical issue signal
        k_note = ''
        if (k_rate_delta and
                k_rate_delta >= HOT_COLD_CONFIG[
                    'cold_k_rate_increase']):
            k_note = (
                f" | K rate up {k_rate_delta}pp — "
                f"possible mechanical issue"
            )

        result['detail'] = (
            f"xwOBA: {r['xwoba']} vs season {b['xwoba']} "
            f"({xwoba_delta}) | "
            f"Exit Velo: {r['avg_ev']} vs {b['avg_ev']} "
            f"({ev_delta} mph) — "
            f"both metrics confirm cold over "
            f"{games_recent} games{k_note}"
        )

    # xwOBA only cold
    elif (xwoba_delta and
          xwoba_delta <= HOT_COLD_CONFIG['cold_xwoba_delta']):
        result['status'] = 'COOLING'
        result['emoji'] = '📉'
        result['confirmed'] = False
        result['detail'] = (
            f"xwOBA trending down: {r['xwoba']} vs "
            f"season {b['xwoba']} ({xwoba_delta}) | "
            f"Exit velo not confirming — "
            f"monitoring but not confirmed cold"
        )

    else:
        result['detail'] = (
            f"xwOBA last {days}d: {r['xwoba']} vs "
            f"season: {b['xwoba']} | "
            f"Exit Velo: {r['avg_ev']} vs {b['avg_ev']}"
        )

    return result


def build_lineup_danger_ranking(pitcher_id: int,
                                 batter_ids: list,
                                 season: int = None) -> pd.DataFrame:
    """
    Ranks opposing batters from most to least dangerous
    against a specific pitcher using a composite score.

    Composite score weights:
    - xwOBA vs pitcher's primary pitch types (40%)
    - Hard hit rate vs pitcher's pitch types (25%)
    - Hot/cold status adjustment (20%)
    - Career head to head xwOBA (15%)

    Args:
        pitcher_id: MLBAM pitcher ID
        batter_ids: List of MLBAM batter IDs
        season:     Season filter

    Returns:
        DataFrame sorted by danger score descending
    """
    con = get_connection()

    season_filter = (
        f"AND YEAR(game_date) = {season}" if season else ""
    )

    # Get pitcher's top 3 pitch types by usage
    top_pitches = con.execute(f"""
        SELECT pitch_name
        FROM pitches
        WHERE pitcher = {pitcher_id}
          AND pitch_type IS NOT NULL
          {season_filter}
        GROUP BY pitch_name
        ORDER BY COUNT(*) DESC
        LIMIT 3
    """).df()

    if top_pitches.empty:
        con.close()
        return pd.DataFrame()

    pitch_list = "', '".join(top_pitches['pitch_name'].tolist())

    rows = []
    for batter_id in batter_ids:

        # Get batter name
        name_row = con.execute(f"""
            SELECT name_first || ' ' || name_last
            FROM players WHERE mlbam_id = {batter_id}
        """).fetchone()
        name = name_row[0] if name_row else str(batter_id)

        # Performance vs pitcher's top pitches
        vs_pitches = con.execute(f"""
            SELECT
                ROUND(AVG(estimated_woba_using_speedangle), 3)
                                                as xwoba,
                ROUND(
                    COUNT(CASE WHEN launch_speed >= 95
                          THEN 1 END) * 100.0 /
                    NULLIF(COUNT(CASE WHEN launch_speed IS NOT NULL
                          THEN 1 END), 0), 1
                )                               as hard_hit_pct,
                COUNT(*)                        as pitches
            FROM pitches
            WHERE batter = {batter_id}
              AND pitch_name IN ('{pitch_list}')
              AND pitch_type IS NOT NULL
              {season_filter}
        """).df()

        # Head to head career xwOBA
        h2h = con.execute(f"""
            SELECT
                ROUND(AVG(estimated_woba_using_speedangle), 3)
                                                as h2h_xwoba,
                COUNT(*)                        as h2h_pitches
            FROM pitches
            WHERE pitcher = {pitcher_id}
              AND batter  = {batter_id}
        """).df()

        # Hot cold
        hot_cold = get_hot_cold_status(batter_id, season)

        # Season xwOBA
        season_xwoba = con.execute(f"""
            SELECT ROUND(AVG(estimated_woba_using_speedangle), 3)
            FROM pitches
            WHERE batter = {batter_id}
              AND pitch_type IS NOT NULL
              {season_filter}
        """).fetchone()

        xwoba = (vs_pitches.iloc[0]['xwoba']
                 if not vs_pitches.empty else None)
        hard_hit = (vs_pitches.iloc[0]['hard_hit_pct']
                    if not vs_pitches.empty else None)
        pitches = (int(vs_pitches.iloc[0]['pitches'])
                   if not vs_pitches.empty else 0)
        h2h_xwoba = (h2h.iloc[0]['h2h_xwoba']
                     if not h2h.empty else None)
        h2h_pitches = (int(h2h.iloc[0]['h2h_pitches'])
                       if not h2h.empty else 0)
        s_xwoba = season_xwoba[0] if season_xwoba else None

        # ── Composite danger score ────────────────────────
        score = 0.0

        # xwOBA vs pitcher pitch types (40%)
        if xwoba:
            score += xwoba * 0.40

        # Hard hit rate (25%)
        if hard_hit:
            score += (hard_hit / 100) * 0.25

        # Hot cold adjustment (20%)
        hc_adj = 0.0
        hc_status = hot_cold['status']
        if hc_status == 'HOT' and hot_cold['confirmed']:
            hc_adj = 0.020
        elif hc_status == 'WARM':
            hc_adj = 0.010
        elif hc_status == 'COLD' and hot_cold['confirmed']:
            hc_adj = -0.020
        elif hc_status == 'COOLING':
            hc_adj = -0.010
        score += hc_adj * 0.20

        # Career H2H xwOBA (15%)
        if h2h_xwoba and h2h_pitches >= 20:
            score += h2h_xwoba * 0.15
        elif s_xwoba:
            # Fall back to season if no H2H
            score += s_xwoba * 0.15

        rows.append({
            'batter_id':    batter_id,
            'name':         name,
            'danger_score': round(score, 3),
            'xwoba_vs_sp':  xwoba,
            'hard_hit_pct': hard_hit,
            'h2h_xwoba':    h2h_xwoba,
            'h2h_pitches':  h2h_pitches,
            'season_xwoba': s_xwoba,
            'hot_cold':     hc_status,
            'hot_cold_emoji': hot_cold['emoji'],
            'sample':       pitches
        })

    con.close()

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values('danger_score', ascending=False)
        df = df.reset_index(drop=True)
        df.index = df.index + 1  # Start ranking at 1

    return df


def run_daily_report(focus_team: str = None,
                     game_date: str = None,
                     season: int = None,
                     include_weather: bool = True,
                     include_matchup: bool = True,
                     min_batter_pitches: int = 50):
    """
    Master daily report function.
    Runs the full slate, weather, and matchup analysis.

    Args:
        focus_team:          Team to run full matchup for
                             e.g. 'NYY'. If None shows
                             slate and weather only.
        game_date:           Date string, defaults to today
        season:              Historical data season filter
        include_weather:     Include weather for all games
        include_matchup:     Include full matchup report
        min_batter_pitches:  Skip batters below threshold

    Example:
        run_daily_report(
            focus_team='NYY',
            season=2025
        )
    """
    target_date = game_date or str(date.today())

    print(f"\n{'█' * 65}")
    print(f"  MLB DAILY INTELLIGENCE REPORT")
    print(f"  {target_date}")
    print(f"{'█' * 65}")

    # ── Full slate ────────────────────────────────────────
    games = get_todays_slate(target_date)
    if not games:
        print("No games found for today")
        return

    print_slate(games)

    # ── Weather for all outdoor games ─────────────────────
    if include_weather:
        print(f"\n{'═' * 65}")
        print(f"  WEATHER CONDITIONS")
        print(f"{'═' * 65}")

        for game in games:
            if game['game_state'] == 'Final':
                continue

            home = game['home_abbr']
            is_dome = game.get('is_dome', False)

            matchup_str = (
                f"{game['away_abbr']} @ {game['home_abbr']} "
                f"({game['game_time']})"
            )
            print(f"\n  {matchup_str}")

            if is_dome:
                print(f"  Fixed/Retractable dome — "
                      f"weather conditions irrelevant")
                continue

            weather = get_weather(home)
            print_weather_report(weather)

    # ── Focus team matchup ────────────────────────────────
    if focus_team and include_matchup:

        print(f"\n{'═' * 65}")
        print(f"  FULL MATCHUP ANALYSIS — {focus_team.upper()}")
        print(f"{'═' * 65}")

        inputs = build_game_matchup_inputs(
            focus_team, target_date
        )

        if not inputs:
            print(f"No game found for {focus_team} "
                  f"on {target_date}")
            return

        game = inputs['game']
        our_pitcher_id = inputs['our_pitcher_id']
        opp_batter_ids = inputs['opp_batter_ids']
        opp_team = inputs['opp_team']

        if not our_pitcher_id:
            print(f"No probable pitcher listed for {focus_team}")
            return

        # ── Lineup danger ranking first ───────────────────
        print(f"\n  LINEUP DANGER RANKING")
        print(f"  {focus_team} SP vs {opp_team} lineup")
        print(f"  {'─' * 60}")

        ranking = build_lineup_danger_ranking(
            our_pitcher_id,
            opp_batter_ids,
            season=season
        )

        if not ranking.empty:
            print(f"\n  {'#':<3} {'Batter':<22} {'Score':>6} "
                  f"{'xwOBA-SP':>9} {'HH%':>5} "
                  f"{'H2H':>6} {'Form':>6}  Status")
            print(f"  {'─' * 65}")
            for idx, row in ranking.iterrows():
                h2h_str = (
                    f"{row['h2h_xwoba']:.3f}"
                    if row['h2h_xwoba'] and
                    row['h2h_pitches'] >= 20
                    else '  N/A'
                )
                xwoba_str = (
                    f"{row['xwoba_vs_sp']:.3f}"
                    if row['xwoba_vs_sp'] else '  N/A'
                )
                hh_str = (
                    f"{row['hard_hit_pct']:.1f}%"
                    if row['hard_hit_pct'] else '  N/A'
                )
                emoji = row.get('hot_cold_emoji', '')

                print(f"  {idx:<3} "
                      f"{row['name']:<22} "
                      f"{row['danger_score']:>6.3f} "
                      f"{xwoba_str:>9} "
                      f"{hh_str:>6} "
                      f"{h2h_str:>6}  "
                      f"{emoji} {row['hot_cold']}")

        # ── Full pitcher profile ──────────────────────────
        pitcher = get_pitcher_profile(
            our_pitcher_id, season=season
        )
        _print_pitcher_section(pitcher)

        # ── Per batter matchup in danger order ────────────
        if not ranking.empty:
            ordered_ids = ranking['batter_id'].tolist()
        else:
            ordered_ids = opp_batter_ids

        print(f"\n{'═' * 65}")
        print(f"  BATTER BY BATTER MATCHUPS")
        print(f"  (Ordered by danger score)")
        print(f"{'═' * 65}")

        for batter_id in ordered_ids:
            batter = get_batter_profile(
                batter_id, season=season
            )

            if not batter['summary'].empty:
                total = batter['summary'].iloc[0]['total_pitches']
                if total and total < min_batter_pitches:
                    continue

            # Replace batter hot_cold with research-backed version
            hc = get_hot_cold_status(batter_id, season)
            batter['hot_cold'] = hc['status']
            batter['hot_cold_detail'] = hc['detail']

            h2h = head_to_head_history(
                our_pitcher_id, batter_id
            )

            matchup = analyze_matchup(
                pitcher, batter, h2h=h2h
            )

            _print_matchup_section(matchup, batter, h2h)

        # ── Opposing pitcher profile ──────────────────────
        opp_pitcher_id = inputs.get('opp_pitcher_id')
        if opp_pitcher_id:

            print(f"\n{'═' * 65}")
            print(f"  OPPOSING PITCHER")
            print(f"{'═' * 65}")

            opp_pitcher = get_pitcher_profile(
                opp_pitcher_id, season=season
            )
            _print_pitcher_section(opp_pitcher)

            # Yankees lineup vs opposing pitcher
            our_team_id = (
                [k for k, v in MLB_TEAM_MAP.items()
                 if v == focus_team.upper()]
            )

            if our_team_id:
                print(f"\n  {focus_team} lineup vs "
                      f"{inputs['opp_pitcher']}:")

                our_batters = get_lineup_batters(our_team_id[0])
                our_batter_ids = [
                    p['mlbam_id'] for p in our_batters
                    if p['mlbam_id']
                ]

                opp_ranking = build_lineup_danger_ranking(
                    opp_pitcher_id,
                    our_batter_ids,
                    season=season
                )

                if not opp_ranking.empty:
                    print(f"\n  {'#':<3} {'Batter':<22} "
                          f"{'Score':>6} {'xwOBA-SP':>9} "
                          f"{'HH%':>5} {'Form':>6}  Status")
                    print(f"  {'─' * 60}")
                    for idx, row in opp_ranking.iterrows():
                        xwoba_str = (
                            f"{row['xwoba_vs_sp']:.3f}"
                            if row['xwoba_vs_sp'] else '  N/A'
                        )
                        hh_str = (
                            f"{row['hard_hit_pct']:.1f}%"
                            if row['hard_hit_pct'] else '  N/A'
                        )
                        emoji = row.get('hot_cold_emoji', '')
                        print(f"  {idx:<3} "
                              f"{row['name']:<22} "
                              f"{row['danger_score']:>6.3f} "
                              f"{xwoba_str:>9} "
                              f"{hh_str:>6}  "
                              f"{emoji} {row['hot_cold']}")

    print(f"\n{'█' * 65}")
    print(f"  END OF DAILY REPORT — {target_date}")
    print(f"{'█' * 65}\n")


if __name__ == "__main__":
    print("Daily report module ready")
    print()
    print("Usage:")
    print("  run_daily_report(focus_team='NYY', season=2025)")