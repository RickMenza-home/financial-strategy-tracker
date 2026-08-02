"""
Wheel-strategy-specific calculation functions.

All functions are pure (no side effects, no DB access).
Implements §2.5, §2.6, and §2.7 of the requirements.

May import: stdlib, constants.
"""

from __future__ import annotations

from constants import AssignmentType, SHARES_PER_CONTRACT


# ---------------------------------------------------------------------------
# §2.5 / §2.6  Net stock basis on assignment
# ---------------------------------------------------------------------------

def net_stock_basis(strike: float, contracts: int, net_premium: float,
                    assignment_type: AssignmentType) -> float:
    """
    Net stock basis for an assignment event (§2.5 for PUT, §2.6 for CALL).

    PUT assignment — cost of acquiring shares:

        shares          = contracts × SHARES_PER_CONTRACT
        stock_value     = strike × shares
        net_stock_basis = stock_value − net_premium

    Because net_premium < gross premium (fee reduces income), the result is
    higher than without fees — reflecting the true acquisition cost.

    CALL assignment — net proceeds from shares called away:

        shares          = contracts × SHARES_PER_CONTRACT
        stock_value     = strike × shares
        net_stock_basis = stock_value + net_premium

    net_premium is positive (SELL), so it increases the net proceeds.

    Args:
        strike:          Strike price of the assigned option.
        contracts:       Number of contracts assigned.
        net_premium:     net_premium_value of the original trade (positive).
        assignment_type: AssignmentType.PUT or AssignmentType.CALL.

    Returns:
        Net stock basis in dollars (total, not per-share).
    """
    shares      = contracts * SHARES_PER_CONTRACT
    stock_value = strike * shares
    
    return stock_value - net_premium if assignment_type == AssignmentType.PUT else stock_value + net_premium


# ---------------------------------------------------------------------------
# §2.7  Cost basis adjustment from a covered call
# ---------------------------------------------------------------------------

def cost_basis_reduction_per_share(net_premium: float, contracts: int) -> float:
    """
    Per-share cost basis reduction applied each time a CC trade is processed
    (status OPEN, CLOSED, or EXPIRED) (§2.7).

        reduction = net_premium / (contracts × SHARES_PER_CONTRACT)

    Args:
        net_premium: net_premium_value of the CC trade (positive for SELL,
                     negative for BUY).
        contracts:   Number of contracts in the CC trade.

    Returns:
        Dollar reduction per share (positive = cost basis decreases).
    """
    return net_premium / (contracts * SHARES_PER_CONTRACT)
