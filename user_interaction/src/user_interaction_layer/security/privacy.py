"""Financial privacy checks before agentic dispatch."""

from __future__ import annotations

from dataclasses import dataclass

from user_interaction_layer.agentic_client.schemas import Language


@dataclass(frozen=True)
class PrivacyAssessment:
    allowed: bool
    reason: str = ""
    user_message: str = ""


SECRET_TERMS = (
    "password",
    "passcode",
    "api key",
    "secret",
    "token",
    "otp",
    "pin",
    "private key",
    "كلمة المرور",
    "رمز التحقق",
    "الرمز السري",
    "المفتاح السري",
)

EXFILTRATION_TERMS = (
    "show me",
    "give me",
    "reveal",
    "export",
    "download",
    "list all",
    "send me",
    "اعرض",
    "اكشف",
    "صدر",
    "نزّل",
    "ارسل",
)

OTHER_USER_TERMS = (
    "another customer",
    "someone else's",
    "other user's",
    "all customers",
    "all users",
    "customer list",
    "عميل آخر",
    "مستخدم آخر",
    "كل العملاء",
    "جميع العملاء",
    "قائمة العملاء",
)


def assess_financial_privacy(text: str, language: Language) -> PrivacyAssessment:
    normalized = " ".join(text.lower().split())

    if _contains_any(normalized, SECRET_TERMS) and _contains_any(normalized, EXFILTRATION_TERMS):
        return PrivacyAssessment(
            allowed=False,
            reason="secret_exfiltration",
            user_message=_secret_message(language),
        )

    if _contains_any(normalized, OTHER_USER_TERMS) and _contains_any(normalized, EXFILTRATION_TERMS):
        return PrivacyAssessment(
            allowed=False,
            reason="other_user_financial_data",
            user_message=_privacy_message(language),
        )

    return PrivacyAssessment(allowed=True)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _secret_message(language: Language) -> str:
    if language == Language.ARABIC:
        return "لا أستطيع كشف كلمات المرور أو الرموز أو المفاتيح السرية. يمكنني مساعدتك بخطوات آمنة لاستعادة الوصول."
    return "I cannot reveal passwords, codes, tokens, or secret keys. I can help you with a safe recovery flow."


def _privacy_message(language: Language) -> str:
    if language == Language.ARABIC:
        return "لا أستطيع عرض بيانات مالية خاصة بمستخدمين آخرين. يمكنني مساعدتك في طلب يخص حسابك أو مسار مصرح به."
    return "I cannot show private financial data for other users. I can help with your own account or an authorized workflow."

