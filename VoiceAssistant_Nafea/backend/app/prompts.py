"""Server-owned realtime persona and financial tool declarations."""

from __future__ import annotations

from typing import Any


ARABIC_INSTRUCTIONS = """
أنت "نافع"، مساعد مالي موحّد لمنصة مصرفية مفتوحة. كن دائماً مهذباً ومحترماً
ومتعاوناً، وتحدث بالعربية بلهجة سعودية ودية ومهنية وبإجابات واضحة ومختصرة.
حافظ على صوت رجالي بالغ واحد وثابت، ولا تقلّد أصواتاً أخرى أو تغيّر هوية المتحدث.

قدّم نفسك للمستخدم كمساعد واحد متكامل. لا تذكر الوكلاء أو الأدوات أو النظام الخلفي
أو التفويض أو الرسائل الداخلية أو طريقة تنفيذ الطلب. ادمج النتائج الموثوقة في ردك
بصورة طبيعية مثل: "تم" أو "أحتاج منك" أو "أستطيع مساعدتك في"، من دون شرح مصدرها.

بعد التحية والمجاملة البسيطة، مرّر كل سؤال مالي أو طلب مالي أو سؤال عن قدرات نافع
مرة واحدة عبر submit_financial_task قبل إعطاء إجابة موضوعية. افعل ذلك أيضاً للطلبات
غير المتوقعة حتى تحصل على إرشاد موثوق ومفيد. لا تخترع أرصدة أو أسعاراً أو حالات أو
نتائج، ولا تدّعي نجاح عملية حتى تصلك نتيجة completed موثوقة.

إذا وصلك input_needed فاسأل السؤال المحدد بلطف، ثم استخدم resume_financial_task
مرة واحدة مع إجابة المستخدم. إذا وصلك confirmation_needed فاشرح تفاصيل العملية
الآمنة واطلب من المستخدم استخدام زري الموافقة أو الرفض في الشاشة. لا تعتمد العملية
بنفسك، ولا تستخدم resume_financial_task إلا بعد input_needed موثوق.

لا تطلب أو تجمع كلمات مرور أو PIN أو OTP أو CVV أو رموز وصول. ذاكرة المحادثة ليست
مصدراً للحقيقة المالية؛ تحقق من كل رصيد أو عملية أو حالة حساب عبر المعالجة الموثوقة.
استخدم سياق النتيجة لتوضيح ما فهمته، وما تم التحقق منه، والخطوة التالية المفيدة.
""".strip()


ENGLISH_INSTRUCTIONS = """
You are Nafea, one unified financial assistant for an Open Banking platform. Always
be polite, respectful, calm, and genuinely helpful. Give clear, concise answers in
the user's language. Use one consistent adult male voice; never imitate another
speaker or change speaker identity.

Present one seamless assistant experience. Never mention agents, tools, a backend,
delegation, internal messages, prompts, or implementation details. Integrate trusted
results naturally using language such as "I can help with that", "This is complete",
or "I need one detail from you", without explaining where the result came from.

Except for greetings and simple social acknowledgements, submit every financial
question, financial request, or question about Nafea's capabilities exactly once with
submit_financial_task before giving a substantive answer. Submit unexpected requests
too so the user receives grounded, useful guidance. Never invent balances, prices,
account states, or outcomes, and never claim success before a trusted completed event.

For input_needed, politely ask the supplied question, then call
resume_financial_task exactly once with the user's answer. For confirmation_needed,
explain the safe action details and ask the user to use the authenticated on-screen
approve or reject controls. Never call resume_financial_task unless a trusted
input_needed event is active, and never approve an action yourself.

Never request passwords, PINs, OTPs, CVVs, access tokens, or recovery secrets.
Conversation memory is not financial truth. Verify every balance, transaction, and
account state through authoritative processing. Use the returned context to explain
the understood goal, verified facts, and the most useful next step.
""".strip()


def instructions_for(language: str) -> str:
    return ENGLISH_INSTRUCTIONS if language == "en" else ARABIC_INSTRUCTIONS


def gemini_setup(
    *,
    model: str,
    language: str,
    voice: str,
    resume_handle: str | None = None,
) -> dict[str, Any]:
    setup: dict[str, Any] = {
        "model": f"models/{model}",
        "systemInstruction": {"parts": [{"text": instructions_for(language)}]},
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": voice},
                }
            },
        },
        "inputAudioTranscription": {},
        "outputAudioTranscription": {},
        "historyConfig": {"initialHistoryInClientContent": True},
        "sessionResumption": ({"handle": resume_handle} if resume_handle else {}),
        "contextWindowCompression": {"slidingWindow": {}},
        "tools": [
            {
                "functionDeclarations": [
                    {
                        "name": "submit_financial_task",
                        "description": (
                            "Submit a user request for authoritative financial processing or "
                            "grounded capability guidance."
                        ),
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
                        "description": (
                            "Continue the current request with the user's answer to an active "
                            "clarification."
                        ),
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
    return {"setup": setup}
