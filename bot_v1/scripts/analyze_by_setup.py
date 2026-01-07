import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT_DIR))

import pandas as pd

PATH = "reports/trades_vp_v1_2025.csv"

# Parse setup từ reason column
# Format: VP_ASIA_HVN_VAL_REACTION_BUY -> A
#        VP_ASIA_SECOND_ENTRY_BUY -> B
#        VP_ASIA_VA_REENTRY_TRAP_SELL -> D
#        VP_LONDON_LVN_GAP_SELL -> E

def extract_setup(reason: str) -> str:
    """Extract setup letter from reason string"""
    if pd.isna(reason):
        return "UNKNOWN"
    
    reason = str(reason).upper()
    
    if "REACTION" in reason or "HVN_VAL" in reason:
        return "A"  # HVN/VAL Reaction
    elif "SECOND_ENTRY" in reason or "SECOND" in reason:
        return "B"  # Second Entry
    elif "VA_REENTRY" in reason or "REENTRY_TRAP" in reason or "VA_TRAP" in reason:
        return "D"  # VA Re-entry Trap
    elif "GAP" in reason or "LVN_GAP" in reason:
        return "E"  # LVN Gap continuation
    else:
        return "UNKNOWN"

def main():
    try:
        df = pd.read_csv(PATH)
    except FileNotFoundError:
        print(f"File not found: {PATH}")
        print("Please run backtest first to generate trades file.")
        return

    # Extract setup
    if "setup" not in df.columns:
        if "reason" not in df.columns:
            print("Error: No 'reason' or 'setup' column found in CSV!")
            return
        df["setup"] = df["reason"].apply(extract_setup)

    # Filter out trades without valid setup
    df = df[df["setup"] != "UNKNOWN"].copy()

    if len(df) == 0:
        print("No trades found or no valid setup information!")
        return

    summary = (
        df.groupby("setup")
          .agg(
              trades=("pnl_usd", "count"),
              wins=("pnl_usd", lambda x: (x > 0).sum()),
              losses=("pnl_usd", lambda x: (x <= 0).sum()),
              total_pnl=("pnl_usd", "sum"),
              avg_pnl=("pnl_usd", "mean"),
              max_win=("pnl_usd", "max"),
              max_loss=("pnl_usd", "min"),
          )
    )

    summary["winrate_pct"] = summary["wins"] / summary["trades"] * 100

    # Calculate profit factor per setup
    profit_factors = {}
    for setup in summary.index:
        setup_trades = df[df["setup"] == setup]
        wins = setup_trades[setup_trades["pnl_usd"] > 0]["pnl_usd"].sum()
        losses = abs(setup_trades[setup_trades["pnl_usd"] < 0]["pnl_usd"].sum())
        if losses > 0:
            profit_factors[setup] = wins / losses
        else:
            profit_factors[setup] = float("inf") if wins > 0 else 0.0

    summary["profit_factor"] = summary.index.map(profit_factors)

    summary = summary.sort_values("total_pnl", ascending=False)

    print("\n=== PERFORMANCE BY SETUP ===\n")
    print(summary.round(2))

    print("\n=== SHARE OF TOTAL PNL ===\n")
    total = df["pnl_usd"].sum()
    if total != 0:
        share = (summary["total_pnl"] / total * 100).round(2)
        print(share)
    else:
        print("Total PnL is zero, cannot calculate share")

    print("\n=== SETUP NAMES ===\n")
    setup_names = {
        "A": "HVN/VAL Reaction",
        "B": "Second Entry",
        "D": "VA Re-entry Trap",
        "E": "LVN Gap continuation"
    }
    for setup, name in setup_names.items():
        if setup in summary.index:
            print(f"{setup}: {name}")

    print(f"\n=== TOTAL TRADES: {len(df)} ===\n")


if __name__ == "__main__":
    main()

