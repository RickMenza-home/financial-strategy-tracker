"""
Chart builder functions for premium visualisations.

All functions return a Plotly Figure object ready to be rendered
by Streamlit via st.plotly_chart().

May import: plotly, pandas.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from calculations import total_premium
from models import Position, Trade

# ---------------------------------------------------------------------------
# Premium by week (§6.2)
# ---------------------------------------------------------------------------

def premium_by_week_chart(trades: list[Trade]) -> go.Figure:
    """
    Bar chart of total premium collected grouped by week.

    X-axis: week label (YYYY-W##)
    Y-axis: sum of total_premium for trades in that week

    Returns an empty figure with a helpful annotation when no trades exist.
    """
    if not trades:
        fig = go.Figure()
        fig.update_layout(
            title="Weekly Premium",
            xaxis_title="Week",
            yaxis_title="Premium ($)",
            annotations=[{
                "text": "No trades yet",
                "xref": "paper", "yref": "paper",
                "x": 0.5, "y": 0.5, "showarrow": False,
                "font": {"size": 16, "color": "gray"},
            }],
        )
        return fig

    rows = []
    for t in trades:
        week_label = t.trade_date.strftime("%Y-W%U")
        rows.append({
            "week": week_label,
            "total_premium": total_premium(t.premium, t.contracts),
        })

    df = pd.DataFrame(rows)
    df = df.groupby("week", as_index=False)["total_premium"].sum()
    df = df.sort_values("week")

    fig = px.bar(
        df,
        x="week",
        y="total_premium",
        labels={"week": "Week", "total_premium": "Premium ($)"},
        title="Weekly Premium",
    )
    fig.update_layout(showlegend=False)
    return fig


# ---------------------------------------------------------------------------
# Premium by symbol (§10.5)
# ---------------------------------------------------------------------------

def premium_by_symbol_chart(positions: list[Position]) -> go.Figure:
    """
    Bar chart of premium_collected per symbol.

    X-axis: symbol
    Y-axis: premium_collected (net, fee-adjusted)

    Returns an empty figure with a helpful annotation when no positions exist.
    """
    if not positions:
        fig = go.Figure()
        fig.update_layout(
            title="Premium by Symbol",
            xaxis_title="Symbol",
            yaxis_title="Net Premium ($)",
            annotations=[{
                "text": "No positions yet",
                "xref": "paper", "yref": "paper",
                "x": 0.5, "y": 0.5, "showarrow": False,
                "font": {"size": 16, "color": "gray"},
            }],
        )
        return fig

    rows = [
        {"symbol": p.symbol, "premium_collected": p.premium_collected}
        for p in positions
    ]
    df = pd.DataFrame(rows)
    df = df.sort_values("premium_collected", ascending=False)

    fig = px.bar(
        df,
        x="symbol",
        y="premium_collected",
        labels={"symbol": "Symbol", "premium_collected": "Net Premium ($)"},
        title="Premium by Symbol",
    )
    fig.update_layout(showlegend=False)
    return fig
