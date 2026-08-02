"""
Abstract base class for all strategy plugins.

Every strategy plugin must subclass StrategyPlugin and implement all three
methods. The engine dispatches trades to plugins via strategy_type.

May import: models only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from models import PluginResult, Position, Trade


class StrategyPlugin(ABC):
    """
    Interface contract for a trading strategy plugin (§3.0).

    Attributes:
        strategy_type: Unique lowercase string identifier, e.g. "wheel".
                       Must match the value stored in Trade.strategy_type.
        display_name:  Human-readable label shown in the UI.
    """

    strategy_type: str
    display_name: str

    @abstractmethod
    def initial_position_state(self, symbol: str) -> dict:
        """
        Return the blank position state dict for a symbol seen for the first time.

        The dict is the mutable working state passed into and returned from
        process_trade() on every call. It is converted to a Position row only
        after all trades for the symbol have been replayed.

        Args:
            symbol: Uppercase ticker, e.g. "SOFI".

        Returns:
            A dict with all state fields initialised to their zero values.
        """

    @abstractmethod
    def process_trade(self, trade: Trade, state: dict) -> PluginResult:
        """
        Apply one trade to the running position state.

        This is a pure function — it must not access the database or produce
        any side effects. All persistence is handled by the engine after this
        method returns.

        Args:
            trade: The trade to process (chronological order guaranteed).
            state: The current position state dict for trade.symbol.
                   Mutate and return it inside PluginResult.state.

        Returns:
            PluginResult with the updated state and any new assignment /
            lifecycle events to persist.
        """

    @abstractmethod
    def get_available_actions(self, position: Position) -> list[str]:
        """
        Return the action type strings available for the given position status.

        Used by the UI to populate the action dropdown on the Positions page.

        Args:
            position: The current position record for the symbol.

        Returns:
            List of action type strings, e.g. ["CLOSE_CSP", "CSP_EXPIRED_UNASSIGNED"].
        """
