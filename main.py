"""
main.py
Entry point for the baseball analytics system.
"""

from src.database import initialize_database
from src.data_pull import (
    pull_statcast_range,
    pull_player_lookup,
    build_bullpen_usage
)
from src.matchup_queries import (
    pitcher_vs_batter,
    pitcher_tendencies,
    batter_tendencies
)
from src.bullpen_monitor import bullpen_availability
from src.player_lookup import get_player_id, populate_all_players
from src.metrics import calculate_fip, calculate_whip


def pull_current_seasons():
    """
    Pulls 2025 full season and 2026 season to date.
    Run this after initial setup is complete.
    """
    print("=" * 50)
    print("PULLING CURRENT SEASON DATA")
    print("=" * 50)

    # Pull full 2025 season
    print("\n[1/3] Pulling 2025 full season...")
    print("This will take 10-15 minutes - ~700,000 pitches")
    pull_statcast_range("2025-03-27", "2025-10-01")

    # Pull 2026 season to date
    print("\n[2/3] Pulling 2026 season to date...")
    pull_statcast_range("2026-03-27", "2026-04-03")

    # Rebuild bullpen usage with all new data
    print("\n[3/3] Rebuilding bullpen usage table...")
    build_bullpen_usage()

    print("\n" + "=" * 50)
    print("SEASON DATA PULL COMPLETE")
    print("=" * 50)


def sample_analysis():
    """
    Sample analysis to verify everything is working.
    """
    print("=" * 50)
    print("RUNNING SAMPLE ANALYSIS")
    print("=" * 50)

    # Look up player IDs
    print("\nLooking up player IDs...")
    cole_id = get_player_id("cole", "gerrit")
    judge_id = get_player_id("judge", "aaron")
    degrom_id = get_player_id("degrom", "jacob")

    # Aaron Judge batting tendencies
    if judge_id:
        print(f"\nAaron Judge batting tendencies:")
        judge_tendencies = batter_tendencies(judge_id)
        if judge_tendencies.empty:
            print("No data found for Judge in current date range")
        else:
            print(judge_tendencies.to_string(index=False))

    # Gerrit Cole pitch tendencies
    if cole_id:
        print(f"\nGerrit Cole pitch tendencies:")
        cole_tendencies = pitcher_tendencies(cole_id)
        if cole_tendencies.empty:
            print("No data found for Cole in current date range")
        else:
            print(cole_tendencies.head(15).to_string(index=False))

    # deGrom pitch tendencies
    if degrom_id:
        print(f"\nJacob deGrom pitch tendencies:")
        degrom_tendencies = pitcher_tendencies(degrom_id)
        if degrom_tendencies.empty:
            print("No data for deGrom - likely injured during this period")
        else:
            print(degrom_tendencies.head(15).to_string(index=False))

    # Cole vs Judge matchup
    if cole_id and judge_id:
        print(f"\nCole vs Judge matchup breakdown:")
        matchup = pitcher_vs_batter(cole_id, judge_id)
        if matchup.empty:
            print("No head to head data in current date range")
        else:
            print(matchup.to_string(index=False))

    # Cole FIP and WHIP
    if cole_id:
        print(f"\nGerrit Cole FIP by game:")
        fip = calculate_fip(cole_id)
        if fip.empty:
            print("No FIP data available")
        else:
            print(fip.to_string(index=False))

        print(f"\nGerrit Cole WHIP by game:")
        whip = calculate_whip(cole_id)
        if whip.empty:
            print("No WHIP data available")
        else:
            print(whip.to_string(index=False))

    # Yankees bullpen availability
    print("\nYankees bullpen availability:")
    availability = bullpen_availability("NYY")
    if availability.empty:
        print("No bullpen data available")
    else:
        print(availability.head(15).to_string(index=False))

    print("\n" + "=" * 50)
    print("ANALYSIS COMPLETE")
    print("=" * 50)


if __name__ == "__main__":
    # Step 1 - Pull current season data
    # Comment this out after first run
    # pull_current_seasons()
    # populate_all_players()
    # Step 2 - Run analysis
    sample_analysis()