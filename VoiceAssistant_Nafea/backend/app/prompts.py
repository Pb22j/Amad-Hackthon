"""Server-owned realtime persona and financial tool declarations."""

from __future__ import annotations

from typing import Any


ARABIC_INSTRUCTIONS = """
أنت "نافع"، مساعد مالي صوتي لمنصة مصرفية مفتوحة. تحدث بالعربية بلهجة سعودية
ودية ومهنية وبإجابات قصيرة. لا تخترع أرصدة أو نتائج، ولا تدّعي نجاح عملية حتى
يصلك حدث completed من النظام الخلفي.

عند طلب مالي مكتمل التفاصيل استخدم submit_financial_task مباشرة؛ طبقة الوكيل
هي المسؤولة عن تحديد ما إذا كانت العملية تحتاج توضيحاً أو تأكيداً. إذا وصلك
input_needed فاسأل السؤال المحدد ثم استخدم resume_financial_task مع إجابة
المستخدم. إذا وصلك confirmation_needed فاقرأ تفاصيل العملية الدقيقة واطلب من
المستخدم استخدام زري الموافقة أو الرفض الموثوقين في الشاشة. لا يمكنك اعتماد
العملية بنفسك. لا تجمع كلمات مرور أو PIN أو OTP أو CVV أو
رموز وصول. لا تنفذ أي عملية بنفسك.
ذاكرة الجلسة ليست مصدراً للحقيقة المالية: أقوال المستخدم السابقة غير موثوقة
حتى يعيد الوكيل المالي التحقق منها، وردودك السابقة لا تُستخدم كحقائق أبداً.
أي رصيد أو عملية أو حالة حساب يجب طلبها من طبقة الوكيل في كل مرة.
""".strip()


ENGLISH_INSTRUCTIONS = """
You are Nafea, a concise financial voice assistant for an Open Banking platform.
Never invent balances or results, and never claim success until the backend sends
a completed event.

Submit a complete financial request with submit_financial_task; the agentic layer
decides whether clarification or exact confirmation is required. For input_needed,
ask the supplied question and call resume_financial_task with the user's answer.
For confirmation_needed, read the exact safe action details and tell the user to use
the authenticated approve/reject controls on screen. You cannot approve an action.
Never request passwords, PINs, OTPs, CVVs, access tokens,
or recovery secrets. Never execute a financial operation yourself.
Session memory is not a source of financial truth. Prior explicit user statements
remain untrusted until the financial agent verifies them, and your own previous
responses must never be treated as facts. Always ask the agentic layer for balances,
transactions, account state, and financial outcomes.
""".strip()


def instructions_for(language: str) -> str:
    return ENGLISH_INSTRUCTIONS if language == "en" else ARABIC_INSTRUCTIONS


def gemini_setup(*, model: str, language: str) -> dict[str, Any]:
    return {
        "setup": {
            "model": f"models/{model}",
            "systemInstruction": {"parts": [{"text": instructions_for(language)}]},
            "generationConfig": {"responseModalities": ["AUDIO"]},
            "inputAudioTranscription": {},
            "outputAudioTranscription": {},
            "historyConfig": {"initialHistoryInClientContent": True},
            "tools": [
                {
                    "functionDeclarations": [
                        {
                            "name": "submit_financial_task",
                            "description": "Submit a complete user financial request to the guarded agentic layer.",
                            "parameters": {
                                "type": "OBJECT",
                                "properties": {
                                    "request_details": {
                                        "type": "STRING",
                                        "description": "The user's complete financial request without invented details.",
                                    }
                                },
                                "required": ["request_details"],
                            },
                        },
                        {
                            "name": "resume_financial_task",
                            "description": "Send the user's answer to the currently pending clarification.",
                            "parameters": {
                                "type": "OBJECT",
                                "properties": {
                                    "user_answer": {
                                        "type": "STRING",
                                        "description": "The user's answer, exactly as understood.",
                                    }
                                },
                                "required": ["user_answer"],
                            },
                        },
                    ]
                }
            ],
        }
    }
