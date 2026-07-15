"""Financial tool integration package.

Teammate-owned functionality is exposed through ``TOOLS``. The agent discovers
this list at startup and applies the guarded boundary to every item. The bank
tools operate on the shared PostgreSQL bank database (:mod:`agentic.tools.bank_db`).
The in-memory ``DUMMY_TOOLS`` sandbox remains available through the
``AGENTIC_TOOL_PROVIDER=agentic.tools.dummy:DUMMY_TOOLS`` override.
"""

from agentic.tools.add_benefit import LIST_TOOL as LIST_BENEFICIARIES_TOOL
from agentic.tools.add_benefit import TOOL as ADD_BENEFIT_TOOL
from agentic.tools.accounts import GET_BALANCE_TOOL, SEARCH_TRANSACTIONS_TOOL
from agentic.tools.analyze_finances import TOOL as ANALYZE_FINANCES_TOOL
from agentic.tools.dummy import DUMMY_TOOLS
from agentic.tools.fatoorah import LIST_FATOORAHS_TOOL, PAY_FATOORAH_TOOL
from agentic.tools.gift import TOOL as SEND_GIFT_TOOL
from agentic.tools.guard import AgentRuntimeContext, GuardedToolFactory
from agentic.tools.metadata import ToolMetadata, ToolResult
from agentic.tools.monthly_report import TOOL as MONTHLY_REPORT_TOOL
from agentic.tools.investments import (
    BUY_INVESTMENT_TOOL,
    GET_PORTFOLIO_TOOL,
    SELL_INVESTMENT_TOOL,
)
from agentic.tools.qatta import (
    CANCEL_QATTA_TOOL,
    CREATE_QATTA_TOOL,
    LIST_QATTA_BILLS_TOOL,
    PAY_QATTA_BILL_TOOL,
)
from agentic.tools.transfer_between_accounts import TOOL as TRANSFER_BETWEEN_ACCOUNTS_TOOL

BANK_TOOLS = (
    GET_BALANCE_TOOL,
    SEARCH_TRANSACTIONS_TOOL,
    ADD_BENEFIT_TOOL,
    LIST_BENEFICIARIES_TOOL,
    TRANSFER_BETWEEN_ACCOUNTS_TOOL,
    MONTHLY_REPORT_TOOL,
    CREATE_QATTA_TOOL,
    PAY_QATTA_BILL_TOOL,
    CANCEL_QATTA_TOOL,
    LIST_QATTA_BILLS_TOOL,
    SEND_GIFT_TOOL,
    PAY_FATOORAH_TOOL,
    LIST_FATOORAHS_TOOL,
    ANALYZE_FINANCES_TOOL,
    GET_PORTFOLIO_TOOL,
    BUY_INVESTMENT_TOOL,
    SELL_INVESTMENT_TOOL,
)

TOOLS = BANK_TOOLS

__all__ = [
    "TOOLS",
    "BANK_TOOLS",
    "DUMMY_TOOLS",
    "AgentRuntimeContext",
    "GuardedToolFactory",
    "ToolMetadata",
    "ToolResult",
]
