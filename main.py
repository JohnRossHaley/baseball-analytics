"""
main.py
Entry point for the baseball analytics system.
Run this file to initialize the database and pull your first dataset.
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
from src.player_lookup import get_player_id
from src.metrics import calculate_fip, calculate_whip


def setup():
    """
    Full setup sequence.
    Run this once to initialize the database
    and pull your first month of Statcast data.
    """
    print("=" * 50)
    print("BASEBALL ANALYTICS SYSTEM")
    print("=" * 50)

    # Step 1 - Initialize database tables
    print("\n[1/4] Initializing database...")
    initialize_database()

    # Step 2 - Pull one month of Statcast data to start
    print("\n[2/4] Pulling Statcast data...")
    pull_statcast_range("2024-04-01", "2024-04-30")

    # Step 3 - Build bullpen usage from pitch data
    print("\n[3/4] Building bullpen usage table...")
    build_bullpen_usage()

    # Step 4 - Sample player lookups
    print("\n[4/4] Running sample player lookups...")
    pull_player_lookup("judge", "aaron")
    pull_player_lookup("degrom", "jacob")
    pull_player_lookup("cole", "gerrit")

    print("\n" + "=" * 50)
    print("SETUP COMPLETE")
    print("=" * 50)
    print("\nDatabase ready at: data/baseball.db")
    print("Run sample_analysis() to see your first results")


def sample_analysis():
    """
    Sample analysis to verify everything is working.
    Run this after setup() completes successfully.
    """
    print("=" * 50)
    print("RUNNING SAMPLE ANALYSIS")
    print("=" * 50)

    # Look up player IDs
    print("\nLooking up player IDs...")
    cole_id = get_player_id("cole", "gerrit")
    judge_id = get_player_id("judge", "aaron")

    if cole_id and judge_id:

        # Pitcher tendencies
        print(f"\nGerrit Cole pitch tendencies:")
        tendencies = pitcher_tendencies(cole_id)
        print(tendencies.head(10).to_string(index=False))

        # Batter tendencies
        print(f"\nAaron Judge batting tendencies:")
        judge_tendencies = batter_tendencies(judge_id)
        print(judge_tendencies.to_string(index=False))

        # Cole vs Judge matchup
        print(f"\nCole vs Judge matchup breakdown:")
        matchup = pitcher_vs_batter(cole_id, judge_id)
        if matchup.empty:
            print("No head to head data in current date range")
            print("Pull more data or try a different matchup")
        else:
            print(matchup.to_string(index=False))

        # FIP for Cole
        print(f"\nGerrit Cole FIP by game:")
        fip = calculate_fip(cole_id)
        print(fip.to_string(index=False))

        # WHIP for Cole
        print(f"\nGerrit Cole WHIP by game:")
        whip = calculate_whip(cole_id)
        print(whip.to_string(index=False))

    # Yankees bullpen availability
    print("\nYankees bullpen availability:")
    availability = bullpen_availability("NYY")
    print(availability.to_string(index=False))

    print("\n" + "=" * 50)
    print("ANALYSIS COMPLETE")
    print("=" * 50)


if __name__ == "__main__":
    # Run setup first time only
    setup()

    # Uncomment after setup completes successfully
    # sample_analysis()