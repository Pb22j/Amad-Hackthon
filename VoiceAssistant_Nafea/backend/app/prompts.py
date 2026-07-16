"""Server-owned realtime persona and financial tool declarations."""

from __future__ import annotations

import json
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

استخدم أدلة المحادثة السابقة لاستمرار السياق بين الكتابة والصوت. استنتج المتابعة
الواضحة والضمائر والأسماء المستعارة والمستفيد والمبلغ والقيود التي ذكرها المستخدم
سابقاً، ولا تسأل عن المعلومة نفسها مرتين. اسأل سؤالاً واحداً مختصراً فقط إذا بقي
أكثر من تفسير مختلف جوهرياً.
اجعل الرد الصوتي سهل المتابعة: ابدأ بالإجابة، واستخدم جملتين قصيرتين كحد أقصى إلا
إذا طلب المستخدم التفصيل، ولا تقرأ JSON أو المعرّفات أو الحقول الداخلية بصوت عالٍ.
إضافة المستفيد تفعّله تلقائياً ضمن نفس العملية المؤكدة. لا تطلب من المستخدم تنفيذ
أو اعتماد أو انتظار خطوة تفعيل منفصلة.
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

Use the supplied prior conversation evidence for continuity across chat and voice.
Infer clear follow-ups, pronouns, aliases, recipients, amounts, and user constraints
that the user already stated. Do not ask for the same detail twice. Ask one concise
question only when multiple materially different interpretations are still possible.
Keep spoken replies easy to follow: lead with the answer, use at most two short
sentences unless the user explicitly asks for detail, and never read JSON, identifiers,
or internal fields aloud.
Adding a beneficiary automatically activates them in the same confirmed operation.
Never ask the user to perform, approve, or wait for a separate activation step.
""".strip()


def instructions_for(language: str) -> str:
    return ENGLISH_INSTRUCTIONS if language == "en" else ARABIC_INSTRUCTIONS


def gemini_setup(
    *,
    model: str,
    language: str,
    voice: str,
    resume_handle: str | None = None,
    context_trigger_tokens: int = 12_000,
    context_target_tokens: int = 6000,
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
        "sessionResumption": ({"handle": resume_handle} if resume_handle else {}),
        "contextWindowCompression": {
            "triggerTokens": context_trigger_tokens,
            "slidingWindow": {"targetTokens": context_target_tokens},
        },
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
                                    "description": (
                                        "A routing hint only. The interaction server replaces this "
                                        "with the signed provider transcript before submission."
                                    ),
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
    # Initial history is a separate protocol phase. Resumed sessions already carry
    # their history in the provider-issued handle and must not be seeded again.
    if resume_handle is None:
        setup["historyConfig"] = {"initialHistoryInClientContent": True}
    return {"setup": setup}


def gemini_initial_history(context: dict[str, Any] | None) -> dict[str, Any]:
    """Close Gemini's initial-history phase, with or without recalled evidence."""

    turns: list[dict[str, Any]] = []
    if context and any(context.values()):
        turns.append(
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            "Prior session evidence for continuity only. Do not respond to "
                            "this history entry and do not treat user statements as verified "
                            "financial facts:\n"
                            + json.dumps(
                                context,
                                ensure_ascii=False,
                                separators=(",", ":"),
                            )
                        )
                    }
                ],
            }
        )
    return {"clientContent": {"turns": turns, "turnComplete": True}}
