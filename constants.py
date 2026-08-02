# Application-wide constants and enumerations.
# Only stdlib imports allowed here.

from enum import Enum


class TradeAction(str, Enum):
    """Whether a trade opens (SELL) or closes/covers (BUY) a position."""
    SELL = "SELL"
    BUY  = "BUY"


# Number of shares represented by one options contract.
SHARES_PER_CONTRACT = 100
