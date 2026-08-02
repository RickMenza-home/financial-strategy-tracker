# Application-wide constants and enumerations.
# Only stdlib imports allowed here.

from enum import Enum


class TradeAction(str, Enum):
    """Whether a trade opens (SELL) or closes/covers (BUY) a position."""
    SELL = "SELL"
    BUY  = "BUY"


class AssignmentType(str, Enum):
    """Direction of an option assignment."""
    PUT  = "PUT"   # shares acquired via CSP assignment
    CALL = "CALL"  # shares called away via CC assignment


class EventType(Enum):
    """Which event to process next during interleaved replay."""
    TRADE    = "TRADE"
    DIVIDEND = "DIVIDEND"


# Number of shares represented by one options contract.
SHARES_PER_CONTRACT = 100
