"""Agent-based stock-market simulation focused on market efficiency under the
growth of large passive index funds."""
from .config import SimulationConfig, PERIODS_PER_YEAR
from .engine import run_simulation, SimulationResult, TYPES
from .metrics import summary, performance_table

__all__ = [
    "SimulationConfig",
    "PERIODS_PER_YEAR",
    "run_simulation",
    "SimulationResult",
    "TYPES",
    "summary",
    "performance_table",
]
