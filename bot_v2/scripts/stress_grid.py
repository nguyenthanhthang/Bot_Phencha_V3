import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT_DIR))

import itertools
import subprocess
import yaml
from pathlib import Path
from utils.logger import setup_logger


def main():
    logger = setup_logger("STRESS_GRID", level="INFO")
    
    BASE_CONFIG = "config/backtest.yaml"
    STRESS_CONFIG = "config/stress.yaml"
    OUT_FILE = "reports/stress_results.txt"
    
    # Load stress scenarios
    with open(STRESS_CONFIG, "r", encoding="utf-8") as f:
        stress = yaml.safe_load(f)["stress"]
    
    spreads = stress["spreads_points"]
    slips = stress["slippages_points"]
    
    logger.info(f"Stress test: {len(spreads)} spreads x {len(slips)} slippages = {len(spreads) * len(slips)} scenarios")
    
    # Backup original config
    backup_path = BASE_CONFIG + ".backup"
    with open(BASE_CONFIG, "r", encoding="utf-8") as f:
        original_config = f.read()
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(original_config)
    logger.info(f"Backed up config to: {backup_path}")
    
    def patch_config(spread, slip):
        """Patch backtest config with spread/slippage"""
        with open(BASE_CONFIG, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        
        cfg.setdefault("fill_model", {})
        cfg["fill_model"]["spread_mode"] = "FIXED"
        cfg["fill_model"]["fixed_spread_points"] = int(spread)
        
        cfg["fill_model"]["slippage_mode"] = "FIXED" if slip > 0 else "OFF"
        cfg["fill_model"]["slippage_points"] = int(slip)
        
        with open(BASE_CONFIG, "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, sort_keys=False, default_flow_style=False)
    
    # Create output directory
    Path(OUT_FILE).parent.mkdir(parents=True, exist_ok=True)
    
    with open(OUT_FILE, "w", encoding="utf-8") as out:
        out.write("=" * 80 + "\n")
        out.write("STRESS TEST RESULTS: Spread & Slippage Grid\n")
        out.write("=" * 80 + "\n\n")
        
        total_scenarios = len(spreads) * len(slips)
        scenario_num = 0
        
        for spread, slip in itertools.product(spreads, slips):
            scenario_num += 1
            logger.info(f"[{scenario_num}/{total_scenarios}] Running spread={spread} slippage={slip} ...")
            
            # Patch config
            patch_config(spread, slip)
            
            # Write header
            out.write("\n" + "=" * 80 + "\n")
            out.write(f"SCENARIO {scenario_num}/{total_scenarios}: spread={spread}pts, slippage={slip}pts\n")
            out.write("=" * 80 + "\n\n")
            out.flush()
            
            # Run backtest
            try:
                result = subprocess.run(
                    ["python", "scripts/backtest_vp_v1.py"],
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 min timeout per scenario
                )
                
                out.write(result.stdout)
                if result.stderr:
                    out.write("\n[STDERR]\n")
                    out.write(result.stderr)
                
                if result.returncode != 0:
                    out.write(f"\n[ERROR] Backtest failed with return code {result.returncode}\n")
                    logger.warning(f"Backtest failed for spread={spread}, slippage={slip}")
                else:
                    logger.info(f"✓ Completed spread={spread}, slippage={slip}")
                
            except subprocess.TimeoutExpired:
                out.write(f"\n[TIMEOUT] Backtest exceeded 5 minutes\n")
                logger.warning(f"Timeout for spread={spread}, slippage={slip}")
            except Exception as e:
                out.write(f"\n[EXCEPTION] {str(e)}\n")
                logger.error(f"Exception for spread={spread}, slippage={slip}: {e}")
            
            out.flush()
    
    # Restore original config
    with open(backup_path, "r", encoding="utf-8") as f:
        original_config = f.read()
    with open(BASE_CONFIG, "w", encoding="utf-8") as f:
        f.write(original_config)
    logger.info(f"Restored original config from backup")
    
    logger.info(f"Stress test completed. Results saved to: {OUT_FILE}")


if __name__ == "__main__":
    main()

