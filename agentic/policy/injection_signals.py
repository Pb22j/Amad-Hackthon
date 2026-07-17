"""Multilingual, normalization-aware request screening signals.

The detector is deliberately deterministic: it is used before the model and must remain
cheap, explainable, and available when a model provider is not.  Signals describe the
*meaningful relationship* between an action and a protected target, rather than rejecting
requests merely because they mention words such as ``password`` or ``act as``.
"""

from __future__ import annotations

import base64
import binascii
import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InjectionSignals:
    detected: bool
    codes: tuple[str, ...]


_FLAGS = re.I | re.S
_ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]")
_SEPARATED_WORD = re.compile(
    r"(?<!\w)(?:(?:[a-z0-9][\W_]+){3,}[a-z0-9]|(?:[\u0600-\u06ff][\W_]+){3,}[\u0600-\u06ff])(?!\w)",
    re.I,
)
_BASE64_TOKEN = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{16,}={0,2}(?![A-Za-z0-9+/=])")
_LEET_TRANSLATION = str.maketrans(
    {"0": "o", "1": "i", "3": "e", "5": "s", "7": "t", "ı": "i", "Ι": "i", "ι": "i"}
)

_OVERRIDE_VERB = (
    r"(?:ignore|disregard|override|skip|bypass|discard|forget|disable"
    r"|تجاهل|تخط(?:ي)?|تجاوز|اهمل|انس|عطل|تعطيل)"
)
_PROTECTED_INSTRUCTION = (
    r"(?:instructions?|policy|rules?|prompt|system|developer|restrictions?"
    r"|confirmation(?:\s+(?:policy|step|requirement))?"
    r"|تعليمات|التعليمات|السياسه|النظام|القيود|قيود|قواعد\s+النظام"
    r"|موجه\s+النظام|رساله\s+المطور|(?:خطوه|متطلب)\s+التاكيد)"
)
_DISCLOSURE_VERB = (
    r"(?:reveal|show|print|repeat|disclose|expose|quote|return"
    r"|اكشف|اظهر|اعرض|اطبع|كرر|اقتبس|اعد)"
)
_PROMPT_TARGET = (
    r"(?:system\s+prompt|(?:hidden|confidential|secret)\s+(?:prompt|instructions?)"
    r"|developer\s+(?:message|instructions?)|initiali[sz]ation\s+prompt"
    r"|prompt\s+you\s+were\s+given|تعليمات\s+(?:مخفيه|سريه)"
    r"|التعليمات\s+(?:المخفيه|السريه)|رساله\s+المطور"
    r"|موجه\s+(?:النظام|التهيئه|التهييه))"
)
_CREDENTIAL = (
    r"(?:otp|one[- ]time\s+password|pin|password|api\s+(?:key|credential)"
    r"|access\s+token|bearer\s+token|cvv|verification\s+code|card\s+security\s+code"
    r"|login\s+secret|secret.{0,30}sign\s+in|authentication\s+code"
    r"|card\s+verification\s+(?:number|code)|private\s+api\s+credential"
    r"|رمز\s+(?:التحقق|المصادقه|امان\s+البطاقه)|رقم\s+التحقق\s+من\s+البطاقه"
    r"|كلمه\s+المرور|الرقم\s+السري|السر\s+المستخدم\s+للدخول"
    r"|سر\s+(?:ال)?دخول|مفتاح\s+جلسه|بيانات\s+الاعتماد\s+السريه)"
)
_CREDENTIAL_REQUEST = (
    r"(?:tell\s+me|give\s+me|read(?:\s+back)?|what(?:\s+is|'s)|send\s+me|share"
    r"|disclose|display|show|reveal|copy|retrieve|requires?"
    r"|commands?.{0,20}(?:disclose|show|send)"
    r"|اعطني|اخبرني|ارسل\s+لي|اعرض|اكشف|اقرا|انسخ|استخرج"
    r"|(?:فريق\s+الامان|مسؤول\s+الامتثال|الجهه\s+الرقابيه).{0,30}(?:يطلب|تطلب)"
    r"|يامرك.{0,20}(?:بكشف|بعرض|بارسال))"
)
_NEGATED_CREDENTIAL_ACTION = re.compile(
    r"(?:never|do\s+not|don't|without).{0,20}(?:share|show|display|request|reveal)"
    r"|(?:الا|لا|دون).{0,20}(?:اشارك|اعرض|اطلب|اكشف)",
    _FLAGS,
)


PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "instruction_override",
        re.compile(
            rf"(?:{_OVERRIDE_VERB}.{{0,80}}{_PROTECTED_INSTRUCTION}"
            rf"|(?:higher\s+priority|اعلي\s+اولويه).{{0,50}}{_PROTECTED_INSTRUCTION})",
            _FLAGS,
        ),
    ),
    (
        "prompt_exfiltration",
        re.compile(rf"{_DISCLOSURE_VERB}.{{0,80}}{_PROMPT_TARGET}", _FLAGS),
    ),
    (
        "credential_request",
        re.compile(
            rf"(?:{_CREDENTIAL_REQUEST}.{{0,60}}{_CREDENTIAL}"
            rf"|(?:^|\s)ما(?:\s+(?:هي|هو))?\s+{_CREDENTIAL})",
            _FLAGS,
        ),
    ),
    (
        "identity_override",
        re.compile(
            r"(?:change\s+tenant|impersonat\w*"
            r"|act\s+as.{0,30}(?:user|admin|administrator|account\s+owner)"
            r"|i\s+am\s+now\s+(?:the\s+)?user\b|set\s+my\s+identity\s+to"
            r"|(?:switch|move|pretend).{0,40}(?:identity|session|user\s+id|tenant)"
            r"|use.{0,35}(?:profile|identity).{0,25}instead\s+of\s+mine"
            r"|access.{0,30}account\s+belonging\s+to"
            r"|(?:show|open|fetch|list|access|need).{0,50}(?:another|other)\s+user's.{0,30}"
            r"(?:account|balance|transactions?|portfolio|statements?)"
            r"|(?:account_owner_id|authenticated_user|tenant_id|user_id|owner_id|principal_id)"
            r"\s*(?:[:=]|\s+)\s*['\"]?[a-z0-9_-]+"
            r"|(?:tenant|user)\s*[:=]\s*['\"]?[a-z0-9_-]+"
            r"|انتحل|انا\s+الان\s+المستخدم\b|غير\s+المستاجر"
            r"|(?:بدل|انقل|اعتبر|استبدل).{0,45}(?:هويتي|الهويه|الجلسه|معرف\s+المستخدم|مستاجر)"
            r"|استخدم.{0,30}ملف.{0,30}بدلا\s+من\s+ملفي"
            r"|ادخل.{0,25}حساب\s+الشخص"
            r"|معرف\s+مستخدم\s+اخر"
            r"|(?:اعرض|افتح|اجلب).{0,40}(?:حساب|عمليات|محفظه).{0,30}(?:مستخدم\s+اخر|شخص\s+اخر))",
            _FLAGS,
        ),
    ),
    (
        "bulk_data_exfiltration",
        re.compile(
            r"(?:"
            r"(?:list|show|return|download|enumerate|export|extract|query|create).{0,80}"
            r"(?:every|all|complete|entire).{0,45}"
            r"(?:users?|customers?|accounts?|tenants?|wallets?|beneficiar(?:y|ies)|database|table)"
            r"|dump.{0,30}(?:database|table|transactions?)"
            r"|(?:اعرض|اعد|نزل|اسرد|انش(?:ئ|ي)|استعلم).{0,80}"
            r"(?:جميع|كل|كاملا|كامله).{0,45}"
            r"(?:المستخدمين|العملاء|الحسابات|المستاجرين|المحافظ|المستفيدين|قاعده|جدول)"
            r"|(?:انش(?:ئ|ي)|استعلم).{0,60}"
            r"(?:المحافظ|الحسابات|المستخدمين|العملاء|قاعده).{0,35}(?:جميع|كل|كاملا|كامله)"
            r")",
            _FLAGS,
        ),
    ),
)


def _normalize(text: str) -> str:
    """Normalize harmless Unicode variation without erasing language boundaries."""

    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = "".join(char for char in normalized if unicodedata.category(char) != "Cf")
    normalized = _ARABIC_DIACRITICS.sub("", normalized)
    # Arabic spelling variants that are immaterial to these security phrases.
    normalized = normalized.replace("ـ", "")
    normalized = normalized.translate(str.maketrans("أإآةىؤئ", "اااهيوي"))
    return " ".join(normalized.split())


def _deobfuscate(text: str) -> str:
    leet_normalized = text.translate(_LEET_TRANSLATION)
    return _SEPARATED_WORD.sub(
        lambda match: re.sub(r"[\W_]+", "", match.group(0)), leet_normalized
    )


def _decoded_payloads(text: str) -> tuple[str, ...]:
    """Return bounded, printable UTF-8 payloads from standalone Base64 tokens."""

    decoded: list[str] = []
    for match in _BASE64_TOKEN.finditer(text):
        token = match.group(0)
        if len(token) > 4096 or len(token) % 4:
            continue
        try:
            raw = base64.b64decode(token, validate=True)
            value = raw.decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            continue
        if value and len(value) <= 3072 and sum(char.isprintable() for char in value) / len(value) >= 0.9:
            decoded.append(value)
    return tuple(decoded)


def _screening_views(text: str) -> tuple[str, ...]:
    normalized = _normalize(text)
    candidates = [normalized, _deobfuscate(normalized)]
    # Base64 is case-sensitive, so extraction must happen before case-folding.
    for payload in _decoded_payloads(text):
        decoded = _normalize(payload)
        candidates.extend((decoded, _deobfuscate(decoded)))
    return tuple(dict.fromkeys(candidates))


def detect_injection_signals(text: str) -> InjectionSignals:
    views = _screening_views(text)
    codes: list[str] = []
    for code, pattern in PATTERNS:
        detected = False
        for view in views:
            matches = tuple(pattern.finditer(view))
            if code != "credential_request":
                detected = bool(matches)
            else:
                negated = tuple(_NEGATED_CREDENTIAL_ACTION.finditer(view))
                detected = any(
                    not any(
                        safe.start() < match.end() and match.start() < safe.end()
                        for safe in negated
                    )
                    for match in matches
                )
            if detected:
                break
        if detected:
            codes.append(code)
    return InjectionSignals(bool(codes), tuple(codes))
