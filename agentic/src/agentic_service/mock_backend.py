"""Stateful no-key financial providers used by the runnable MVP.

The mock is intentionally server-authoritative: prices, balances, inventory,
and payment results are calculated here rather than accepted from a planner.
It implements the same conceptual boundaries a future Saudi banking, product,
and broker adapter will expose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, ROUND_DOWN
from threading import RLock
from typing import Any
from uuid import uuid4

from .domain import Money


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _saudi_iban(serial: int) -> str:
    """Generate a valid deterministic Saudi IBAN for mock data."""
    bban = f"8000000000{serial:010d}"
    remainder = 0
    for character in bban + "SA00":
        digits = str(ord(character) - 55) if character.isalpha() else character
        for digit in digits:
            remainder = (remainder * 10 + int(digit)) % 97
    return f"SA{98 - remainder:02d}{bban}"


@dataclass(slots=True)
class MockAccount:
    account_id: str
    user_id: str
    bank: str
    name: str
    iban: str
    balance: Decimal
    account_type: str = "current"

    def public(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "bank": self.bank,
            "name": self.name,
            "iban_masked": f"{self.iban[:4]}{'*' * 16}{self.iban[-4:]}",
            "balance": Money(self.balance).to_dict(),
            "account_type": self.account_type,
        }


@dataclass(slots=True)
class MockFinancialBackend:
    """Thread-safe mock bank, product provider, broker, and user directory."""

    accounts: dict[str, MockAccount] = field(default_factory=dict)
    aliases: dict[str, dict[str, str]] = field(default_factory=dict)
    transactions: list[dict[str, Any]] = field(default_factory=list)
    holdings: dict[str, dict[str, Decimal]] = field(default_factory=dict)
    market_prices: dict[str, Decimal] = field(
        default_factory=lambda: {"2222": Decimal("30.00"), "2010": Decimal("34.50"), "1120": Decimal("31.20")}
    )
    user_aliases: dict[str, str] = field(default_factory=lambda: {
        "user-1": "user-1", "me": "user-1", "user-2": "user-2", "@sara": "user-2", "sara": "user-2",
        "سارة": "user-2", "user-3": "user-3", "@ali": "user-3", "ali": "user-3", "علي": "user-3",
        "@noura": "user-3", "noura": "user-3", "نورة": "user-3",
    })
    _lock: RLock = field(default_factory=RLock, repr=False)

    def __post_init__(self) -> None:
        if self.accounts:
            return
        self._seed()

    def _seed(self) -> None:
        self._add_account("alrajhi-main", "user-1", "Al Rajhi", "Al Rajhi Main", Decimal("100000.00"), 1)
        self._add_account("alrajhi-wallet", "user-1", "Al Rajhi", "Al Rajhi Wallet", Decimal("5000.00"), 6)
        self._add_account("snb-secondary", "user-1", "SNB", "SNB Secondary", Decimal("25000.00"), 2)
        self._add_account("user-2-main", "user-2", "Riyad Bank", "Sara Main", Decimal("42000.00"), 3)
        self._add_account("user-3-main", "user-3", "Alinma", "Ali Main", Decimal("18000.00"), 4)
        self._add_account("store-merchant", "merchant-store", "Mock Merchant", "Nafi Store", Decimal("0.00"), 5)
        self.aliases = {
            "user-1": {"alrajhi": "alrajhi-main", "al rajhi": "alrajhi-main", "alrajhi-main": "alrajhi-main", "al rajhi main": "alrajhi-main", "main": "alrajhi-main", "alrajhi-wallet": "alrajhi-wallet", "al rajhi wallet": "alrajhi-wallet", "wallet": "alrajhi-wallet", "snb": "snb-secondary", "snb-secondary": "snb-secondary", "secondary": "snb-secondary"},
            "user-2": {"main": "user-2-main", "riyad": "user-2-main", "sara": "user-2-main"},
            "user-3": {"main": "user-3-main", "alinma": "user-3-main", "ali": "user-3-main"},
        }
        # Seed transactions make reports and analysis immediately useful.
        self._record("user-1", "alrajhi-main", Decimal("12500.00"), "income", "Salary", "2026-06-01T09:00:00+00:00")
        self._record("user-1", "alrajhi-main", Decimal("-2300.00"), "housing", "Rent", "2026-06-03T09:00:00+00:00")
        self._record("user-1", "alrajhi-main", Decimal("-850.00"), "food", "Groceries", "2026-06-12T09:00:00+00:00")
        self._record("user-1", "snb-secondary", Decimal("-120.00"), "transport", "Ride", "2026-06-17T09:00:00+00:00")

    def _add_account(self, account_id: str, user_id: str, bank: str, name: str, balance: Decimal, serial: int, account_type: str = "current") -> MockAccount:
        account = MockAccount(account_id, user_id, bank, name, _saudi_iban(serial), balance, account_type)
        self.accounts[account_id] = account
        return account

    def _record(self, user_id: str, account_id: str, amount: Decimal, category: str, description: str, occurred_at: str | None = None, metadata: dict[str, Any] | None = None) -> str:
        reference = str(uuid4())
        self.transactions.append({"transaction_id": reference, "user_id": user_id, "account_id": account_id, "amount": format(amount, "f"), "currency": "SAR", "category": category, "description": description, "occurred_at": occurred_at or _now(), "metadata": metadata or {}})
        return reference

    def list_accounts(self, user_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [account.public() for account in self.accounts.values() if account.user_id == user_id]

    def resolve_account(self, user_id: str, alias: str | None, *, include_savings: bool = True) -> MockAccount:
        if not alias:
            raise ValueError("source account is required")
        key = " ".join(str(alias).lower().replace("account", "").split())
        with self._lock:
            if key in self.aliases.get(user_id, {}):
                return self.accounts[self.aliases[user_id][key]]
            for account in self.accounts.values():
                if account.user_id != user_id or (not include_savings and account.account_type == "savings"):
                    continue
                haystack = f"{account.account_id} {account.bank} {account.name}".lower()
                if key and key in haystack:
                    return account
        raise ValueError(f"No linked account matches '{alias}'")

    def default_account(self, user_id: str) -> MockAccount:
        with self._lock:
            for account in self.accounts.values():
                if account.user_id == user_id and account.account_type == "current":
                    return account
        raise ValueError("User has no current account")

    def resolve_user(self, alias: str) -> str:
        key = str(alias).strip().lower()
        with self._lock:
            if key in self.user_aliases:
                return self.user_aliases[key]
        raise ValueError(f"Unknown app user '{alias}'")

    def transfer(self, user_id: str, source_alias: str | None, destination: str, amount: Money, *, description: str, category: str = "transfer", recipient_user_id: str | None = None) -> dict[str, Any]:
        if amount.currency != "SAR":
            raise ValueError("The mock provider currently supports SAR only")
        with self._lock:
            source = self.resolve_account(user_id, source_alias or self.default_account(user_id).account_id)
            if recipient_user_id:
                target = self.default_account(recipient_user_id)
            else:
                try:
                    target = self.resolve_account(user_id, destination)
                except ValueError:
                    target = self.accounts.get(destination) or next(
                        (account for account in self.accounts.values() if account.iban == destination), None
                    )
                    if target is None:
                        raise ValueError("Destination account or verified payee was not found")
            if source.account_id == target.account_id:
                raise ValueError("Source and destination accounts must be different")
            if source.balance < amount.amount:
                raise ValueError("Insufficient funds")
            source.balance -= amount.amount
            target.balance += amount.amount
            reference = self._record(user_id, source.account_id, -amount.amount, category, description, metadata={"counterparty": target.account_id})
            self._record(target.user_id, target.account_id, amount.amount, category, description, metadata={"counterparty": source.account_id, "payment_reference": reference})
            return {"payment_reference": reference, "status": "settled", "source": source.public(), "destination": target.public(), "amount": amount.to_dict()}

    def create_savings_account(self, user_id: str, name: str = "Savings") -> MockAccount:
        with self._lock:
            index = len(self.accounts) + 100
            account_id = f"savings-{user_id}-{index}"
            account = self._add_account(account_id, user_id, "Mock Savings Bank", name, Decimal("0.00"), index, "savings")
            self.aliases.setdefault(user_id, {})["savings"] = account_id
            self.aliases[user_id][account_id] = account_id
            return account

    def place_order(self, user_id: str, source_alias: str | None, symbol: str, *, amount: Money | None, quantity: int | None, side: str) -> dict[str, Any]:
        symbol = symbol.upper()
        if symbol not in self.market_prices:
            raise ValueError(f"Unsupported mock Tadawul symbol '{symbol}'")
        price = self.market_prices[symbol]
        with self._lock:
            holding = self.holdings.setdefault(user_id, {})
            if side == "sell":
                if not quantity or quantity <= 0 or holding.get(symbol, Decimal("0")) < quantity:
                    raise ValueError("Insufficient holding quantity")
                value = (price * quantity).quantize(Decimal("0.01"))
                target = self.resolve_account(user_id, source_alias or self.default_account(user_id).account_id)
                holding[symbol] -= Decimal(quantity)
                target.balance += value
                reference = self._record(user_id, target.account_id, value, "investment", f"Sold {quantity} {symbol}")
                return {"order_reference": reference, "status": "filled", "symbol": symbol, "side": "sell", "quantity": quantity, "price": format(price, "f"), "amount": Money(value).to_dict()}
            if quantity is None:
                if amount is None:
                    raise ValueError("Investment amount or quantity is required")
                quantity = int((amount.amount / price).to_integral_value(rounding=ROUND_DOWN))
            if quantity <= 0:
                raise ValueError("Investment amount is below one share")
            value = (price * quantity).quantize(Decimal("0.01"))
            source = self.resolve_account(user_id, source_alias or self.default_account(user_id).account_id)
            if source.balance < value:
                raise ValueError("Insufficient funds")
            source.balance -= value
            holding[symbol] = holding.get(symbol, Decimal("0")) + Decimal(quantity)
            reference = self._record(user_id, source.account_id, -value, "investment", f"Bought {quantity} {symbol}")
            return {"order_reference": reference, "status": "filled", "symbol": symbol, "side": "buy", "quantity": quantity, "price": format(price, "f"), "amount": Money(value).to_dict()}

    def portfolio(self, user_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [{"symbol": symbol, "quantity": format(quantity, "f"), "price": format(self.market_prices[symbol], "f"), "market_value": Money((quantity * self.market_prices[symbol]).quantize(Decimal("0.01"))).to_dict()} for symbol, quantity in sorted(self.holdings.get(user_id, {}).items()) if quantity > 0]

    def transactions_for_month(self, user_id: str, month: str | None) -> list[dict[str, Any]]:
        with self._lock:
            records = [dict(item) for item in self.transactions if item["user_id"] == user_id]
        if month and month not in {"current_month", "previous_month"} and month.startswith("20"):
            return [item for item in records if item["occurred_at"].startswith(month)]
        return records
