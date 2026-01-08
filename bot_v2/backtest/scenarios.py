"""
Backtest Scenarios Module
Runs multiple backtest scenarios with different parameters
"""

from typing import Dict, List, Optional
import itertools
from ..backtest.engine import BacktestEngine


class ScenarioRunner:
    """Run multiple backtest scenarios"""
    
    def __init__(self, engine: BacktestEngine):
        """
        Initialize scenario runner
        
        Args:
            engine: Backtest engine instance
        """
        self.engine = engine
        self.scenarios = []
        self.results = []
    
    def add_scenario(self, name: str, parameters: Dict) -> None:
        """
        Add a scenario to test
        
        Args:
            name: Scenario name
            parameters: Parameter dictionary
        """
        self.scenarios.append({
            'name': name,
            'parameters': parameters
        })
    
    def generate_grid_search(self, param_grid: Dict[str, List]) -> List[Dict]:
        """
        Generate scenarios from parameter grid
        
        Args:
            param_grid: Dictionary of {parameter_name: [values]}
            
        Returns:
            List of parameter combinations
        """
        keys = param_grid.keys()
        values = param_grid.values()
        
        combinations = []
        for combination in itertools.product(*values):
            combinations.append(dict(zip(keys, combination)))
        
        return combinations
    
    def run_all(self) -> List[Dict]:
        """
        Run all scenarios
        
        Returns:
            List of results for each scenario
        """
        self.results = []
        
        for scenario in self.scenarios:
            # Apply parameters to strategy
            # This is a placeholder - implement based on your strategy structure
            result = self.engine.run(
                symbol=scenario['parameters'].get('symbol', 'EURUSD'),
                pip_value=scenario['parameters'].get('pip_value', 0.0001)
            )
            
            result['scenario_name'] = scenario['name']
            result['parameters'] = scenario['parameters']
            self.results.append(result)
            
            # Reset engine for next scenario
            self.engine.reset()
        
        return self.results
    
    def get_best_scenario(self, metric: str = 'return_pct') -> Optional[Dict]:
        """
        Get best performing scenario
        
        Args:
            metric: Metric to optimize
            
        Returns:
            Best scenario result
        """
        if not self.results:
            return None
        
        return max(self.results, key=lambda x: x.get(metric, 0))
    
    def compare_scenarios(self) -> Dict:
        """Compare all scenarios"""
        if not self.results:
            return {}
        
        comparison = {
            'scenarios': [r['scenario_name'] for r in self.results],
            'total_trades': [r.get('total_trades', 0) for r in self.results],
            'win_rate': [r.get('win_rate', 0) for r in self.results],
            'return_pct': [r.get('return_pct', 0) for r in self.results],
            'sharpe_ratio': [r.get('sharpe_ratio', 0) for r in self.results],
        }
        
        return comparison


