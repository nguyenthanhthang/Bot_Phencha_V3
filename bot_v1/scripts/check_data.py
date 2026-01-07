import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT_DIR))

import pandas as pd
from pathlib import Path


def check_file(filepath: str):
    """Check a single data file"""
    try:
        df = pd.read_csv(filepath, parse_dates=["time"])
        rows = len(df)
        time_min = df["time"].min()
        time_max = df["time"].max()
        
        print(f"\nFile: {filepath}")
        print(f"  Rows: {rows:,}")
        print(f"  Time range: {time_min} -> {time_max}")
        print(f"  Duration: {(time_max - time_min).days} days")
        
        return {
            "file": filepath,
            "rows": rows,
            "time_min": time_min,
            "time_max": time_max
        }
    except FileNotFoundError:
        print(f"\nFile not found: {filepath}")
        return None
    except Exception as e:
        print(f"\nError reading {filepath}: {e}")
        return None


def main():
    cache_dir = Path("data_cache")
    
    print("=== CHECKING DATA CACHE FILES ===\n")
    
    # Check M1 files
    print("--- M1 Files ---")
    m1_files = sorted(cache_dir.glob("XAUUSDm_M1_*.csv"))
    if m1_files:
        for f in m1_files:
            check_file(str(f))
    else:
        print("No M1 files found")
    
    # Check M15 files
    print("\n--- M15 Files ---")
    m15_files = sorted(cache_dir.glob("XAUUSDm_M15_*.csv"))
    if m15_files:
        for f in m15_files:
            check_file(str(f))
    else:
        print("No M15 files found")
    
    # Quick check example (as requested)
    print("\n=== QUICK CHECK EXAMPLE ===")
    example_file = "data_cache/XAUUSDm_M15_2021-01-01_2022-01-01.csv"
    result = check_file(example_file)
    
    if result:
        print(f"\nQuick check result:")
        print(f"  len(df) = {result['rows']}")
        print(f"  df['time'].min() = {result['time_min']}")
        print(f"  df['time'].max() = {result['time_max']}")


if __name__ == "__main__":
    main()

