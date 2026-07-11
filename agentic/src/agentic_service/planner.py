"""Deterministic English/Arabic request planning.

This module intentionally has no model or provider dependency.  It turns the
small, well-defined demo language into a *proposal*; account resolution,
authorisation, pricing, and execution remain server-side responsibilities.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
import json
import re
from typing import Any

try:  # The domain package is supplied by the service foundation.
    from agentic_service.domain import ActionPlan, ActionType
except ImportError:  # Allows this module to be exercised in isolation.
    class ActionType(str, Enum):
        OWN_ACCOUNT_TRANSFER = "own_account_transfer"
        USER_TRANSFER = "user_transfer"
        ADD_BENEFICIARY = "add_beneficiary"
        DELETE_BENEFICIARY = "delete_beneficiary"
        INVEST = "invest"
        CREATE_QATTA = "create_qatta"
        PAY_QATTA_SHARE = "pay_qatta_share"
        MONTHLY_REPORT = "monthly_report"
        OPEN_SAVINGS = "open_savings"
        GIFT_TRANSFER = "gift_transfer"
        FINANCIAL_ANALYSIS = "financial_analysis"
        LIST_STORE_ITEMS = "list_store_items"
        STORE_PURCHASE = "store_purchase"
        NEED_INPUT = "need_input"

    @dataclass(frozen=True)
    class ActionPlan:
        action: ActionType
        parameters: dict[str, Any]
        missing_fields: tuple[str, ...] = ()
        confidence: float = 1.0
        user_message: str = ""


_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")
_IBAN_RE = re.compile(r"(?<![A-Z0-9])SA\d{2}(?:\s*[A-Z0-9]){20}(?![A-Z0-9])", re.IGNORECASE)
_AMOUNT_RE = re.compile(
    r"(?<![A-Z0-9@])(?P<amount>\d{1,3}(?:[,.]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*"
    r"(?P<currency>SAR|SR|ر\.?س\.?|ريال(?:\s+سعودي)?)?\b",
    re.IGNORECASE,
)
_HANDLE_RE = re.compile(r"(?<!\w)@([\w.-]+)", re.UNICODE)
_SKU_RE = re.compile(r"\b(?:sku|item)\s*[-:#]?\s*([A-Z0-9][A-Z0-9_-]{1,})\b", re.IGNORECASE)
_QATTA_ID_RE = re.compile(r"\b(?:qatta|قطة)\s*[-#]?\s*([A-Z0-9_-]+)\b", re.IGNORECASE)

_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3,
    "mar": 3, "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6,
    "july": 7, "jul": 7, "august": 8, "aug": 8, "september": 9,
    "sep": 9, "sept": 9, "october": 10, "oct": 10, "november": 11,
    "nov": 11, "december": 12, "dec": 12,
    "يناير": 1, "فبراير": 2, "مارس": 3, "ابريل": 4, "أبريل": 4,
    "مايو": 5, "يونيو": 6, "يوليو": 7, "اغسطس": 8, "أغسطس": 8,
    "سبتمبر": 9, "اكتوبر": 10, "أكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12,
}

_ACTION_ENUM_NAMES = {
    "own_account_transfer": ("OWN_ACCOUNT_TRANSFER",),
    "user_transfer": ("USER_TRANSFER",),
    "add_beneficiary": ("ADD_BENEFICIARY",),
    "delete_beneficiary": ("DELETE_BENEFICIARY",),
    "invest": ("INVEST", "INVESTMENT_ORDER"),
    "create_qatta": ("CREATE_QATTA",),
    "pay_qatta_share": ("PAY_QATTA_SHARE",),
    "monthly_report": ("MONTHLY_REPORT",),
    "open_savings": ("OPEN_SAVINGS", "OPEN_SAVINGS_AND_FUND"),
    "gift_transfer": ("GIFT_TRANSFER",),
    "financial_analysis": ("FINANCIAL_ANALYSIS",),
    "list_store_items": ("LIST_STORE_ITEMS",),
    "store_purchase": ("STORE_PURCHASE",),
    "need_input": ("NEED_INPUT",),
}


def plan_request(text: str, language: str = "en") -> ActionPlan:
    """Return one closed action proposal for a human request.

    ``language`` is a hint only: Arabic and English markers are both accepted
    in every request so bilingual code-switching behaves predictably.
    """
    original = text or ""
    structured = _structured_request_plan(original, language)
    if structured is not None:
        return structured
    normalized = _normalise(original)
    lowered = normalized.lower()
    language = "ar" if language.lower().startswith("ar") or _contains_arabic(original) else "en"
    common = _common_fields(normalized)

    # Specific actions must precede the generic send/transfer language.
    if _has(lowered, "gift", "هدية", "كهدية", "ك هدية"):
        return _proposal("gift_transfer", common, ("amount", "recipient"), language)
    if _has(lowered, "add beneficiary", "new beneficiary", "اضف مستفيد", "أضف مستفيد", "إضافة مستفيد"):
        return _proposal("add_beneficiary", common, ("iban",), language)
    if _has(lowered, "delete beneficiary", "remove beneficiary", "حذف مستفيد", "احذف مستفيد", "إزالة مستفيد"):
        reference = _extract_beneficiary_reference(normalized)
        if reference:
            common["beneficiary"] = reference
        return _proposal("delete_beneficiary", common, ("beneficiary",), language)
    if _has(lowered, "pay my qatta", "pay qatta", "pay my share", "ادفع حصتي", "سدد حصتي", "دفع حصتي"):
        return _proposal("pay_qatta_share", common, ("qatta_id",), language)
    if _has(lowered, "qatta", "split", "قسّم", "قسم", "تقسيم فاتورة", "قطة"):
        return _proposal("create_qatta", common, ("amount", "participants"), language)
    if _has(lowered, "financial analysis", "analyze my finances", "analyse my finances", "تحليل مالي", "حلل وضعي المالي", "حلل وضعي"):
        return _proposal("financial_analysis", common, (), language)
    if _has(lowered, "monthly report", "financial report", "monthly summary", "تقرير شهري", "تقرير مالي", "ملخص شهري"):
        return _proposal("monthly_report", common, (), language)
    if _has(lowered, "savings account", "open savings", "saving account", "حساب ادخار", "افتح ادخار", "فتح ادخار"):
        return _proposal("open_savings", common, ("amount",), language)
    if _has(lowered, "portfolio", "invest", "investment", "buy stock", "sell stock", "اشتري سهم", "بيع سهم", "استثمر", "استثمار") or re.search(r"\b(?:buy|sell)\s+\d+\s+shares?\b", lowered):
        return _proposal("invest", common, ("symbol", "amount_or_quantity"), language)
    if _has(lowered, "store", "catalog", "shop", "المتجر", "المنتجات", "عرض المنتجات"):
        action = "list_store_items" if _has(lowered, "list", "show", "browse", "catalog", "عرض", "اظهر", "أظهر") and not _has(lowered, "buy", "purchase", "order", "اشتري", "شراء", "اطلب") else "store_purchase"
        return _proposal(action, common, (() if action == "list_store_items" else ("item",)), language)
    if _has(lowered, "transfer", "send", "pay", "حوّل", "حول", "ارسِل", "أرسل", "ادفع"):
        # "my account" / حسابي makes the ownership intent explicit.  A handle
        # or named recipient is always treated as an app-user transfer.
        own = bool(re.search(r"\b(?:my|own)\s+\w.*\b(?:to|into)\s+(?:my|own)\b", lowered)) or "من حساب" in normalized and ("إلى حساب" in normalized or "الى حساب" in normalized)
        action = "own_account_transfer" if own and not common.get("recipient") else "user_transfer"
        required = ("amount", "source_account", "destination_account") if action == "own_account_transfer" else ("amount", "recipient")
        return _proposal(action, common, required, language)

    return _need_input(language, "action")


_MODEL_INTENT_ACTIONS: dict[str, tuple[str, tuple[str, ...]]] = {
    "transfer_between_accounts": ("own_account_transfer", ("amount", "source_account", "destination_account")),
    "transfer_between_users": ("user_transfer", ("amount", "recipient")),
    "add_beneficiary": ("add_beneficiary", ("iban",)),
    "delete_beneficiary": ("delete_beneficiary", ("beneficiary",)),
    "invest_saudi_market": ("invest", ("symbol", "amount_or_quantity")),
    "create_qatta": ("create_qatta", ("amount", "participants")),
    "monthly_report": ("monthly_report", ()),
    "create_savings_account": ("open_savings", ("amount",)),
    "send_gift": ("gift_transfer", ("amount", "recipient")),
    "financial_analysis": ("financial_analysis", ()),
    "browse_store": ("list_store_items", ()),
    "purchase_store_item": ("store_purchase", ("item",)),
}


def _structured_request_plan(text: str, language_hint: str) -> ActionPlan | None:
    """Convert the validated model-router envelope into the closed action plan.

    Only the server-generated schema is accepted. Unknown keys never become
    executor parameters, and an unknown intent becomes a clarification rather
    than falling through to a mutation heuristic.
    """
    if not text.lstrip().startswith("{"):
        return None
    try:
        raw = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("intent"), str):
        return None
    language = "ar" if raw.get("language") == "ar" or language_hint.lower().startswith("ar") else "en"
    intent = str(raw["intent"])
    if intent in {"needs_clarification", "unsupported"}:
        question = str(raw.get("clarification_question") or "").strip()
        if not question:
            question = _missing_message("details", language)
        return _make_plan("need_input", {}, ("details",), 0.99, question)
    mapping = _MODEL_INTENT_ACTIONS.get(intent)
    if mapping is None:
        return _make_plan("need_input", {}, ("action",), 0.0, _missing_message("action", language))

    fields: dict[str, Any] = {}
    for key in ("recipient", "source_account", "destination_account", "iban", "symbol", "sku", "note", "period"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            fields[key] = value.strip()
    for key in ("amount", "quantity"):
        value = raw.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            fields[key] = str(value) if key == "amount" else int(value)
    participants = raw.get("participants")
    if isinstance(participants, list):
        fields["participants"] = [str(item).strip() for item in participants if isinstance(item, str) and item.strip()]

    if fields.get("amount"):
        fields["currency"] = "SAR"
        fields["amount_or_quantity"] = "amount"
    if fields.get("quantity"):
        fields["amount_or_quantity"] = "quantity"
    if fields.get("iban"):
        fields["beneficiary"] = fields["iban"]
    if fields.get("sku"):
        fields["item"] = fields["sku"]
    if fields.get("period"):
        fields["month"] = fields["period"]
    if intent == "send_gift" and fields.get("note"):
        fields["gift_message"] = fields["note"]
    if intent == "add_beneficiary" and fields.get("recipient"):
        fields["display_name"] = fields["recipient"]

    action, required = mapping
    return _proposal(action, fields, required, language)


def _common_fields(text: str) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    amount, currency = _extract_amount(text)
    if amount is not None:
        fields["amount"] = amount
    if currency:
        fields["currency"] = currency
    iban = _extract_iban(text)
    if iban:
        fields["iban"] = iban
        fields.setdefault("beneficiary", iban)
    source, destination = _extract_accounts(text)
    if source:
        fields["source_account"] = source
    if destination:
        fields["destination_account"] = destination
    recipient = _extract_recipient(text)
    if recipient:
        fields["recipient"] = recipient
    participants = _extract_participants(text)
    if participants:
        fields["participants"] = participants
    symbol = _extract_symbol(text)
    if symbol:
        fields["symbol"] = symbol
    month = _extract_month(text)
    if month:
        fields["month"] = month
    sku, item = _extract_item(text)
    if sku:
        fields["sku"] = sku
    if item:
        fields["item"] = item
    qatta_id = _extract_qatta_id(text)
    if qatta_id:
        fields["qatta_id"] = qatta_id
    quantity = _extract_quantity(text)
    if quantity is not None:
        fields["quantity"] = quantity
    if quantity is not None or amount is not None:
        fields["amount_or_quantity"] = "quantity" if quantity is not None else "amount"
    if _has(text.lower(), "sell", "بيع", "بع"):
        fields["side"] = "sell"
    elif _has(text.lower(), "buy", "اشتري", "اشتر", "استثمر", "invest"):
        fields["side"] = "buy"
    return fields


def _proposal(action: str, fields: dict[str, Any], required: tuple[str, ...], language: str) -> ActionPlan:
    parameters = dict(fields)
    if action == "add_beneficiary":
        name = _extract_beneficiary_name(parameters, "")
        if name:
            parameters["display_name"] = name
    if action == "gift_transfer":
        parameters["transfer_kind"] = "gift"
        message = _quoted_text(parameters.pop("_text", ""))
        if message:
            parameters["gift_message"] = message
    if action == "create_qatta":
        parameters.setdefault("currency", "SAR")
    if action == "invest":
        parameters.setdefault("order_type", "market")
    missing = tuple(
        field for field in required
        if not parameters.get(field)
        and not (action == "store_purchase" and field == "item" and parameters.get("sku"))
    )
    if missing:
        return _make_plan("need_input", parameters, missing, 0.72, _missing_message(missing[0], language))
    return _make_plan(action, parameters, (), 0.95, "")


def _need_input(language: str, *missing: str) -> ActionPlan:
    return _make_plan("need_input", {}, tuple(missing), 0.0, _missing_message(missing[0], language))


def _make_plan(action_name: str, parameters: dict[str, Any], missing: tuple[str, ...], confidence: float, user_message: str) -> ActionPlan:
    action = _resolve_action(action_name)
    # Root's public contract uses action/parameters.  The alternate form keeps
    # compatibility with the internal foundation's action_type/fields model.
    try:
        return ActionPlan(action=action, parameters=parameters, missing_fields=missing, confidence=confidence, user_message=user_message)
    except TypeError:
        return ActionPlan(action_type=action, fields=parameters, missing_fields=missing, confidence=confidence, evidence=())


def _resolve_action(name: str) -> ActionType:
    for member_name in _ACTION_ENUM_NAMES[name]:
        member = getattr(ActionType, member_name, None)
        if member is not None:
            return member
    try:
        return ActionType(name)
    except ValueError as exc:  # programmer error, never a user controlled path
        raise RuntimeError(f"Domain ActionType does not support {name!r}") from exc


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(_ARABIC_DIGITS)).strip()


def _contains_arabic(value: str) -> bool:
    return bool(re.search(r"[\u0600-\u06ff]", value))


def _has(text: str, *phrases: str) -> bool:
    return any(phrase in text for phrase in phrases)


def _extract_amount(text: str) -> tuple[str | None, str | None]:
    for match in _AMOUNT_RE.finditer(text):
        # 2222 (a Tadawul ticker) and SKU numbers are not money without a
        # currency marker or a clear payment phrase around them.
        raw, currency = match.group("amount"), match.group("currency")
        before = text[max(0, match.start() - 18):match.start()].lower()
        if not currency and not re.search(r"(?:transfer|send|pay|gift|invest|buy|split|حو|ارس|أرس|ادفع|اشتري|قسم|قسّم)\s*$", before):
            continue
        value = raw.replace(",", "") if raw.count(",") > 1 or "." in raw else raw.replace(",", ".")
        try:
            decimal = Decimal(value)
        except InvalidOperation:
            continue
        if decimal <= 0:
            continue
        return format(decimal.quantize(Decimal("0.01")), "f"), "SAR"
    return None, None


def _extract_iban(text: str) -> str | None:
    match = _IBAN_RE.search(text.upper())
    return re.sub(r"\s+", "", match.group(0)) if match else None


def _clean_alias(value: str) -> str:
    value = re.sub(r"\b(?:account|bank|bank account)\b", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\b(?:for|with|as|to|into)\b.*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+(?:من|إلى|الى|لحساب|لـ).*$", "", value)
    return value.strip(" .,:;!?-–")


def _extract_accounts(text: str) -> tuple[str | None, str | None]:
    source = destination = None
    english_source = re.search(r"\bfrom\s+(?:my\s+)?(.+?)(?=\s+(?:to|into)\s+|$)", text, re.IGNORECASE)
    english_destination = re.search(r"\b(?:to|into)\s+(?:my\s+)?(.+?)(?=\s+(?:for|with|as)\s+|$)", text, re.IGNORECASE)
    arabic_source = re.search(r"(?:من\s+(?:حسابي|حساب)?\s*)(.+?)(?=\s+(?:إلى|الى)\s+|$)", text)
    arabic_destination = re.search(r"(?:إلى|الى)\s+(?:حسابي|حساب)?\s*(.+?)(?=\s+(?:لـ|لحساب|ل)\s+|$)", text)
    if english_source:
        source = _clean_alias(english_source.group(1))
    elif arabic_source:
        source = _clean_alias(arabic_source.group(1))
    if english_destination:
        destination = _clean_alias(english_destination.group(1))
    elif arabic_destination:
        destination = _clean_alias(arabic_destination.group(1))
    return source or None, destination or None


def _extract_recipient(text: str) -> str | None:
    handles = _HANDLE_RE.findall(text)
    if handles:
        return "@" + handles[-1]
    match = re.search(r"\b(?:to|for)\s+(?:user\s+)?([A-Za-z][\w.-]{1,})\b", text, re.IGNORECASE)
    if match and match.group(1).lower() not in {"my", "the", "a", "an"}:
        return match.group(1)
    match = re.search(r"(?:إلى|الى|لـ)\s*([\u0621-\u064a][\u0621-\u064a\s]{1,30}?)(?=\s+(?:بمبلغ|مبلغ|ريال|من|$)|$)", text)
    if not match:
        return None
    candidate = match.group(1).strip()
    # ``إلى حسابي`` identifies a destination account, not an app payee.
    return None if candidate.startswith("حساب") else candidate


def _extract_participants(text: str) -> list[str]:
    handles = ["@" + value for value in _HANDLE_RE.findall(text)]
    if len(handles) >= 2:
        return list(dict.fromkeys(handles))
    match = re.search(r"\b(?:between|with|among)\s+(.+?)(?=\s+(?:for|amount|worth)\b|$)", text, re.IGNORECASE)
    if match:
        values = re.split(r"\s*(?:,|and|&)\s*", match.group(1))
        values = [value.strip(" .") for value in values if value.strip(" .")]
        if len(values) >= 2:
            return values
    match = re.search(r"بين\s+(.+?)(?=\s+(?:بمبلغ|مبلغ|ريال|لـ|لغرض|$)|$)", text)
    if match:
        values = re.split(r"\s*(?:،|,|و)\s*", match.group(1))
        values = [value.strip(" .") for value in values if value.strip(" .")]
        if len(values) >= 2:
            return values
    return handles


def _extract_symbol(text: str) -> str | None:
    match = re.search(r"\b(?:stock|shares?|symbol|ticker|سهم)\s+(?:of\s+)?\$?([A-Za-z]{2,8}|\d{4})(?:\.SA)?\b", text, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    match = re.search(r"\$([A-Za-z]{2,8})\b", text)
    return match.group(1).upper() if match else None


def _extract_month(text: str) -> str | None:
    numeric = re.search(r"\b(20\d{2})[-/](0[1-9]|1[0-2])\b", text)
    if numeric:
        return f"{numeric.group(1)}-{numeric.group(2)}"
    lowered = text.lower()
    for name, number in _MONTHS.items():
        if name.lower() in lowered:
            year = re.search(r"\b(20\d{2})\b", text)
            return f"{year.group(1)}-{number:02d}" if year else f"--{number:02d}"
    if _has(lowered, "last month", "الشهر الماضي"):
        return "previous_month"
    if _has(lowered, "this month", "الشهر الحالي", "هذا الشهر"):
        return "current_month"
    return None


def _extract_item(text: str) -> tuple[str | None, str | None]:
    sku = _SKU_RE.search(text)
    if sku:
        return sku.group(1).upper(), None
    match = re.search(r"\b(?:buy|purchase|order)\s+(?:the\s+|a\s+)?(.+?)(?=\s+(?:from|for)\s+|$)", text, re.IGNORECASE)
    if match:
        return None, match.group(1).strip(" .")
    match = re.search(r"(?:اشتري|شراء|اطلب)\s+(.+?)(?=\s+(?:من|بمبلغ|$)|$)", text)
    return (None, match.group(1).strip()) if match else (None, None)


def _extract_qatta_id(text: str) -> str | None:
    match = _QATTA_ID_RE.search(text)
    if match and match.group(1).lower() != "share":
        return match.group(1)
    return None


def _extract_beneficiary_reference(text: str) -> str | None:
    """Extract a local UUID/reference following a beneficiary delete command."""
    match = re.search(
        r"(?:delete|remove)\s+beneficiary\s+([A-Za-z0-9_-]{6,})",
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)
    match = re.search(r"(?:حذف|احذف|إزالة)\s+مستفيد\s+([A-Za-z0-9_-]{6,})", text)
    return match.group(1) if match else None


def _extract_quantity(text: str) -> int | None:
    match = re.search(r"\b(\d+)\s+(?:shares?|stocks?|أسهم)\b", text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _quoted_text(text: str) -> str | None:
    match = re.search(r"[\"“](.+?)[\"”]", text)
    return match.group(1).strip() if match else None


def _extract_beneficiary_name(parameters: dict[str, Any], text: str) -> str | None:
    # Kept as a hook for callers that enrich the proposal with a display name.
    return None


def _missing_message(field: str, language: str) -> str:
    english = {
        "action": "What would you like to do?",
        "amount": "What amount in SAR should I use?",
        "recipient": "Who should receive it?",
        "source_account": "Which account should fund this?",
        "destination_account": "Which of your accounts should receive it?",
        "iban": "Please provide the beneficiary's Saudi IBAN.",
        "beneficiary": "Which beneficiary or IBAN should I remove?",
        "symbol": "Which Saudi-market symbol should I use?",
        "amount_or_quantity": "What amount or number of shares should I use?",
        "participants": "Who should participate in the Qatta?",
        "qatta_id": "Which Qatta should I pay?",
        "item": "Which store item would you like to buy?",
    }
    arabic = {
        "action": "ما العملية التي تريد تنفيذها؟",
        "amount": "ما المبلغ بالريال السعودي؟",
        "recipient": "لمن تريد التحويل؟",
        "source_account": "من أي حساب تريد الدفع؟",
        "destination_account": "إلى أي حساب من حساباتك تريد التحويل؟",
        "iban": "يرجى إدخال آيبان المستفيد السعودي.",
        "beneficiary": "أي مستفيد أو آيبان تريد حذفه؟",
        "symbol": "ما رمز السهم السعودي؟",
        "amount_or_quantity": "ما المبلغ أو عدد الأسهم؟",
        "participants": "من هم المشاركون في القطة؟",
        "qatta_id": "أي قطة تريد سدادها؟",
        "item": "ما المنتج الذي تريد شراءه؟",
    }
    return (arabic if language == "ar" else english).get(field, "Please provide the missing information." if language == "en" else "يرجى توفير المعلومات الناقصة.")


class HeuristicPlanner:
    """Small adapter matching the planner service's synchronous MVP boundary."""

    def plan(self, text: str, language: str = "en") -> ActionPlan:
        return plan_request(text, language)
