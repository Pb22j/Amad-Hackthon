# Idle-cash management

Nafi now has a two-step idle-cash flow:

1. `analyze_idle_cash` reads the authenticated customer's last three calendar months of payment data, current Nafi wallet balance, and linked-bank balances.
2. `transfer_idle_cash_to_savings` can move only the latest recommended amount from the Nafi wallet to the customer's Nafi liquid-savings account after exact confirmation and OTP.

Linked-bank data is analytical and read-only in this flow. Nafi never sweeps or debits a linked bank. When recommended idle cash is held at a bank, the response must tell the customer to deposit it into the Nafi wallet first and run the analysis again.

## Deterministic method

The `stable-floor-v1` method:

- uses exactly three calendar months, including a projected full current month when it is incomplete;
- requires payment evidence in at least two months and conservatively substitutes the highest observed monthly spend for a zero or missing month when sizing the reserve;
- treats internal wallet funding and Nafi liquid-savings transfers as cash movements rather than spending;
- calculates a conservative stable operating-cash floor from observed account low balances;
- reserves three months of projected average spending as emergency cash;
- defines regularly idle cash as the stable operating-cash floor above that emergency target; and
- separates the amount already safe to move from the Nafi wallet from any bank-held amount that first requires a wallet deposit.

If fewer than two months contain payment spending, the analysis returns the evidence but recommends no transfer. Recommendations expire after 24 hours and execution rechecks current balances before moving money.

## Database records

- `nafi_savings_accounts` stores the real Nafi liquid-savings balance.
- `idle_cash_recommendations` stores the exact calculation snapshot, expiry, status, and execution reference.
- `transactions` receives paired wallet debit and liquid-savings credit ledger entries under one reference.
- `financial_operation_results` preserves idempotent action recovery with the rest of Nafi's financial tools.

## Research basis

The method follows the core principles in the [CFPB emergency-fund guide](https://www.consumerfinance.gov/an-essential-guide-to-building-an-emergency-fund/): track cash-flow timing, keep emergency money safe and accessible, and obtain consent before automating savings. The three-month reserve is a conservative product default at the lower end of the commonly cited three-to-six-month range; the [FDIC consumer guidance](https://www.fdic.gov/consumer-resource-center/2025-01/saving-unexpected-and-your-future) notes that experts often recommend at least six months, so the result is guidance rather than a guarantee that every customer's emergency needs are fully covered.
