import base64
import time
import ssl
import os
from typing import Dict, Tuple
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, WebSocket, WebSocketDisconnect
import hmac
import hashlib
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import settings
from app.utils.logger import logger, log_duration
from app.utils.cache import audio_cache
from app.services.stt_service import get_stt_service, STTException
from app.services.llm_service import get_llm_service, LLMException
from app.services.tts_service import get_tts_service, TTSException
import httpx

# Global SSL verification bypass if configured
if not settings.SSL_VERIFY:
    logger.warning("SSL verification is globally disabled.")
    ssl._create_default_https_context = ssl._create_unverified_context
    os.environ["PYTHONHTTPSVERIFY"] = "0"

app = FastAPI(
    title="Voice AI Agent Proxy Backend",
    description="Secure proxy for transcribing, LLM reasoning, and speaking",
    version="1.0.0"
)

# CORS Configuration
# Allow local React/Vite development server to access the backend APIs
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual frontend origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom Rate Limiter (Token Bucket)
class TokenBucketLimiter:
    def __init__(self, rate_limit: int = settings.RATE_LIMIT_PER_MIN):
        self.rate_limit = rate_limit
        # Stores: (tokens, last_update_time) per IP
        self.buckets: Dict[str, Tuple[float, float]] = {}

    def _cleanup_stale_buckets(self, now: float):
        # Remove entries inactive for more than 10 minutes (600 seconds)
        stale_ips = [ip for ip, (_, last_update) in self.buckets.items() if now - last_update > 600]
        for ip in stale_ips:
            del self.buckets[ip]
        if stale_ips:
            logger.info(f"RateLimiter cleaned up {len(stale_ips)} stale IP entries.")

    def is_allowed(self, ip: str) -> bool:
        if self.rate_limit <= 0:
            return True
            
        now = time.time()
        
        # Periodic cleanup if registry grows too large
        if len(self.buckets) > 1000:
            self._cleanup_stale_buckets(now)
            
        if ip not in self.buckets:
            self.buckets[ip] = (float(self.rate_limit), now)
            return True

        tokens, last_update = self.buckets[ip]
        # Calculate replenished tokens: 1 minute = 60 seconds
        elapsed = now - last_update
        replenished = elapsed * (self.rate_limit / 60.0)
        new_tokens = min(float(self.rate_limit), tokens + replenished)

        if new_tokens >= 1.0:
            self.buckets[ip] = (new_tokens - 1.0, now)
            return True
        
        self.buckets[ip] = (new_tokens, now)
        return False

limiter = TokenBucketLimiter()

# Response Models
class ConfigResponse(BaseModel):
    stt_provider: str
    llm_provider: str
    tts_provider: str
    openai_configured: bool
    gemini_configured: bool
    elevenlabs_configured: bool
    deepgram_configured: bool

class VoiceChatResponse(BaseModel):
    user_transcript: str
    agent_text: str
    audio_base64: str
    audio_mime_type: str
    processing_time_sec: float

@app.middleware("http")
async def rate_limiting_middleware(request: Request, call_next):
    # Check rate limit for API endpoints
    if request.url.path.startswith("/api/voice-chat"):
        client_ip = request.client.host if request.client else "unknown"
        if not limiter.is_allowed(client_ip):
            logger.warning(f"Rate limit exceeded for IP: {client_ip}")
            raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")
            
    response = await call_next(request)
    return response

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "timestamp": time.time()}

@app.get("/api/config", response_model=ConfigResponse)
async def get_config():
    return ConfigResponse(
        stt_provider=settings.STT_PROVIDER,
        llm_provider=settings.LLM_PROVIDER,
        tts_provider=settings.TTS_PROVIDER,
        openai_configured=bool(settings.OPENAI_API_KEY),
        gemini_configured=bool(settings.GEMINI_API_KEY),
        elevenlabs_configured=bool(settings.ELEVENLABS_API_KEY),
        deepgram_configured=bool(settings.DEEPGRAM_API_KEY)
    )

from pydantic import BaseModel
from pydantic import BaseModel
class TokenRequest(BaseModel):
    custom_system_prompt: str | None = None
    language: str | None = "ar"

@app.post("/api/realtime-token")
async def get_realtime_token(req: TokenRequest = None):
    if not settings.OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="OpenAI API Key is not configured on the backend.")
    
    url = "https://api.openai.com/v1/realtime/client_secrets"
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    custom_prompt = req.custom_system_prompt if req and req.custom_system_prompt else ""
    language = req.language if req and req.language else "ar"
    
    default_instructions = """أنت "نافع"، المساعد المالي الصوتي الذكي. أنت تعمل في منصة مصرفية مفتوحة (Open Banking) وتساعد المستخدمين في أمورهم المالية.

## هويتك:
- اسمك "نافع" وأنت مساعد مالي صوتي ذكي.
- إذا سألك أحد "من أنت؟" أو "ما اسمك؟"، قل: "أنا نافع، مساعدك المالي الصوتي. أقدر أساعدك في تحويل الأموال، والاستعلام عن رصيدك، وغيرها من العمليات المالية."
- تحدث دائماً باللغة العربية بلهجة سعودية ودية ومهنية.
- ردودك يجب أن تكون قصيرة ومباشرة لأنك مساعد صوتي.

## ماذا تستطيع أن تفعل:
- تحويل أموال بين الحسابات أو للمستفيدين.
- الاستعلام عن الرصيد.
- عرض آخر العمليات المالية.
- المساعدة في إدارة المستفيدين.
- أي عملية مالية أخرى يطلبها المستخدم.

## كيف تعمل:
1. عندما يطلب منك المستخدم أي عملية مالية (مثل: "حول 200 ريال"، "كم رصيدي"، "وش آخر العمليات")، يجب عليك التأكد من تفاصيل الطلب بالكامل.
2. قبل استخدام أداة submit_financial_task، **يجب** عليك أن تسأل المستخدم وتطلب منه تأكيد العملية بوضوح (مثلاً: "تحويل 1000 ريال من حساب الراجحي إلى الأهلي، متأكد يا مستخدم؟"). لا تستخدم الأداة أبداً حتى يؤكد المستخدم بـ "نعم" أو ما يثبت موافقته.
3. لا تحاول تنفيذ أي عملية مالية بنفسك أبداً. أنت فقط تستقبل الطلب، تتأكد منه، وتأخذ موافقة المستخدم، ثم ترسله عبر الأداة.
4. إذا كان الطلب ناقص معلومات (مثلاً قال "حول فلوس" بدون ما يحدد المبلغ)، اسأله عن التفاصيل الناقصة قبل أن تطلب التأكيد النهائي.
5. إذا وصلك سؤال من النظام الخلفي، اقرأه للمستخدم بأسلوب طبيعي واسأله. ولما يرد، استخدم أداة resume_financial_task لإرسال إجابته.
6. بعد ما ترسل الطلب باستخدام الأداة، قل للمستخدم "تم إرسال طلبك، ثواني بس" وانتظر الرد.

## أمثلة على المحادثات:
- المستخدم: "حول 200 ريال" ← أنت: "حاضر! لمين تبي تحول الـ 200 ريال ومن أي حساب؟"
- المستخدم: "من الراجحي للأهلي" ← أنت: "ممتاز، يعني أعتمد تحويل 200 ريال من الراجحي للأهلي؟"
- المستخدم: "إيه توكل على الله" ← أنت: تستخدم أداة submit_financial_task وتقول "تم إرسال طلب التحويل، ثواني بس."
- المستخدم: "كم رصيدي بالراجحي؟" ← أنت: "تبي أشيك لك على رصيدك في الراجحي، متأكد؟"
- المستخدم: "نعم" ← أنت: تستخدم أداة submit_financial_task وتقول "جاري الاستعلام عن رصيدك."

## تنبيهات مهمة:
- لا تخترع أرقام أو أرصدة من عندك أبداً.
- لا تقل للمستخدم أن العملية تمت إلا إذا وصلك تأكيد من النظام الخلفي.
- كن ودوداً ومهنياً دائماً."""

    english_instructions = """You are "Nafea", an intelligent financial voice assistant. You work in an Open Banking platform and help users with their finances.

## Your Identity:
- Your name is "Nafea" and you are a smart financial voice assistant.
- If anyone asks "Who are you?" or "What is your name?", say: "I am Nafea, your financial voice assistant. I can help you transfer money, check your balance, and perform other financial operations."
- ALWAYS speak in English in a friendly, professional tone.
- Your responses MUST be short and direct because you are a voice assistant.

## What you can do:
- Transfer money between accounts or to beneficiaries.
- Check account balances.
- Show recent financial transactions.
- Help manage beneficiaries.
- Any other financial operation requested by the user.

## How you work:
1. When the user requests a financial operation (e.g., "transfer $200", "what's my balance", "show recent transactions"), you must ensure you have all the request details.
2. Before using the submit_financial_task tool, you **MUST** explicitly ask the user for confirmation (e.g., "Are you sure you want to transfer $200 to John?"). DO NOT use the tool until the user replies with "Yes" or otherwise confirms.
3. Never attempt to execute any financial operation yourself. You only receive the request, confirm it, and send it via the tool.
4. If the request is missing information (e.g., "transfer money" without specifying an amount), ask for the missing details before asking for final confirmation.
5. If you receive a clarifying question from the backend, read it naturally to the user and ask them. When they reply, use the resume_financial_task tool to send their answer.
6. After you send the request using the tool, tell the user "Your request has been submitted, please wait a moment" and wait for the backend's response.

## Conversation Examples:
- User: "Transfer $200" -> You: "Sure! Who would you like to transfer the $200 to, and from which account?"
- User: "To my savings account" -> You: "Great, so I should confirm transferring $200 to your savings account?"
- User: "Yes, go ahead" -> You: use the submit_financial_task tool and say "Your transfer request has been submitted, just a moment."

## Important Warnings:
- Never invent numbers or balances.
- Do not tell the user that the operation is complete unless you receive confirmation from the backend.
- Always be friendly and professional."""

    if custom_prompt.strip():
        instructions = custom_prompt
    elif language == "en":
        instructions = english_instructions
    else:
        instructions = default_instructions

    # If the model is a Gemini model, return the Gemini connection details directly.
    if "gemini" in settings.REALTIME_MODEL.lower():
        if not settings.GEMINI_API_KEY:
            raise HTTPException(status_code=500, detail="Gemini API Key is not configured on the backend.")
        return {
            "provider": "gemini",
            "api_key": settings.GEMINI_API_KEY,
            "model": settings.REALTIME_MODEL,
            "instructions": instructions
        }

    # Otherwise, generate OpenAI ephemeral token
    payload = {
        "session": {
            "model": settings.REALTIME_MODEL,
            "type": "realtime",
            "instructions": instructions,
            "tools": [
                {
                    "type": "function",
                    "name": "submit_financial_task",
                    "description": "أرسل طلب مالي جديد من المستخدم إلى النظام الخلفي للتنفيذ. استخدم هذه الأداة عندما يطلب المستخدم أي عملية مالية مثل: تحويل أموال، استعلام عن رصيد، عرض عمليات، إضافة مستفيد، أو أي طلب مصرفي آخر. يجب أن تتضمن التفاصيل كل المعلومات التي ذكرها المستخدم.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "request_details": { "type": "string", "description": "تفاصيل طلب المستخدم كاملة باللغة العربية. مثال: تحويل 200 ريال إلى حساب التوفير" }
                        },
                        "required": ["request_details"]
                    }
                },
                {
                    "type": "function",
                    "name": "resume_financial_task",
                    "description": "أرسل إجابة المستخدم على سؤال توضيحي طرحه النظام الخلفي. استخدم هذه الأداة فقط عندما يجيب المستخدم على سؤال كان النظام قد طلبه سابقاً.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "user_answer": { "type": "string", "description": "إجابة المستخدم على السؤال التوضيحي" }
                        },
                        "required": ["user_answer"]
                    }
                }
            ],
            "tool_choice": "auto"
        }
    }

    try:
        async with httpx.AsyncClient(verify=settings.SSL_VERIFY) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            return {
                "client_secret": data.get("value"),
                "model": settings.REALTIME_MODEL
            }
    except Exception as e:
        logger.error(f"Failed to fetch realtime token: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate OpenAI Realtime token: {str(e)}")

@app.post("/api/voice-chat", response_model=VoiceChatResponse)
async def voice_chat(
    file: UploadFile = File(...),
    custom_system_prompt: str = Form(None)
):
    """
    Main endpoint for real-time conversational Voice AI Agent.
    Receives voice recording, runs transcription -> LLM -> TTS,
    caches responses, and returns base64 speech.
    """
    start_time = time.perf_counter()
    mime_type = file.content_type or "audio/webm"
    
    # 1. Read incoming audio file
    try:
        audio_bytes = await file.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Empty audio file provided.")
    except Exception as e:
        logger.error(f"Error reading audio file payload: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to read audio data: {str(e)}")

    # 2. STT: Transcribe speech to text
    try:
        stt_service = get_stt_service()
        user_transcript = await stt_service.transcribe(audio_bytes, mime_type=mime_type)
        logger.info(f"User transcription: '{user_transcript}'")
    except STTException as e:
        logger.error(f"STT pipeline failed: {e}")
        raise HTTPException(status_code=502, detail=f"Speech-to-Text failed: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected STT error: {e}")
        raise HTTPException(status_code=500, detail="Internal Speech-to-Text error.")

    # Edge case: If user transcript is empty or whitespace
    if not user_transcript.strip():
        return VoiceChatResponse(
            user_transcript="",
            agent_text="I couldn't hear you clearly. Please try speaking again.",
            audio_base64="",
            audio_mime_type="audio/mp3",
            processing_time_sec=time.perf_counter() - start_time
        )

    # 3. LLM: Process user transcript to get text response
    try:
        llm_service = get_llm_service()
        system_prompt = custom_system_prompt or settings.LLM_SYSTEM_PROMPT
        agent_text = await llm_service.generate_response(
            prompt=user_transcript,
            system_prompt=system_prompt
        )
        logger.info(f"Agent text response: '{agent_text}'")
    except LLMException as e:
        logger.error(f"LLM pipeline failed: {e}")
        raise HTTPException(status_code=502, detail=f"Language Model reasoning failed: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected LLM error: {e}")
        raise HTTPException(status_code=500, detail="Internal Language Model error.")

    # 4. TTS: Synthesize agent text response into voice audio
    audio_mime_type = "audio/mp3"
    try:
        tts_service = get_tts_service()
        
        # Check cache first
        cached_audio = audio_cache.get(
            provider=settings.TTS_PROVIDER,
            voice_id=settings.TTS_VOICE_ID,
            text=agent_text
        )
        
        if cached_audio is not None:
            audio_bytes_response = cached_audio
        else:
            # Hit external API
            audio_bytes_response = await tts_service.synthesize(
                text=agent_text,
                voice_id=settings.TTS_VOICE_ID
            )
            # Write back to cache
            audio_cache.set(
                provider=settings.TTS_PROVIDER,
                voice_id=settings.TTS_VOICE_ID,
                text=agent_text,
                audio_bytes=audio_bytes_response
            )
            
    except TTSException as e:
        logger.error(f"TTS pipeline failed: {e}")
        raise HTTPException(status_code=502, detail=f"Text-to-Speech synthesis failed: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected TTS error: {e}")
        raise HTTPException(status_code=500, detail="Internal Text-to-Speech error.")

    # Encode response to Base64
    try:
        audio_base64 = base64.b64encode(audio_bytes_response).decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to encode synthesized audio to base64: {e}")
        raise HTTPException(status_code=500, detail="Audio serialization error.")

    processing_time = time.perf_counter() - start_time
    logger.info(f"Total pipeline voice roundtrip completed in: {processing_time:.3f}s")

    return VoiceChatResponse(
        user_transcript=user_transcript,
        agent_text=agent_text,
        audio_base64=audio_base64,
        audio_mime_type=audio_mime_type,
        processing_time_sec=round(processing_time, 3)
    )

# ==========================================
# MULTI-AGENT INTEGRATION (INTERACTION LAYER)
# ==========================================
import json
import uuid

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()

@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

def verify_agentic_signature(timestamp: str, body: bytes, signature: str) -> bool:
    if not settings.INTERACTION_SHARED_SECRET:
        return True # For local testing if not set
    expected_msg = f"{timestamp}.".encode('utf-8') + body
    expected_sig = hmac.new(
        settings.INTERACTION_SHARED_SECRET.encode('utf-8'),
        expected_msg,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_sig, signature)

def sign_agentic_request(body: bytes) -> tuple[str, str]:
    timestamp = str(int(time.time()))
    if not settings.INTERACTION_SHARED_SECRET:
        return timestamp, "dummy_sig"
    msg = f"{timestamp}.".encode('utf-8') + body
    sig = hmac.new(
        settings.INTERACTION_SHARED_SECRET.encode('utf-8'),
        msg,
        hashlib.sha256
    ).hexdigest()
    return timestamp, sig

@app.post("/api/webhook")
async def handle_agentic_webhook(request: Request):
    timestamp = request.headers.get("X-Agentic-Timestamp", "")
    signature = request.headers.get("X-Agentic-Signature", "")
    body = await request.body()
    
    if not verify_agentic_signature(timestamp, body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    try:
        event = json.loads(body)
        logger.info(f"Received Agentic Webhook: {event.get('event_type')}")
        # Broadcast to frontend via WebSocket so Voice Agent can speak it
        await manager.broadcast(event)
        return {"status": "received"}
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid JSON")

class SubmitTaskRequest(BaseModel):
    natural_language_request: str

@app.post("/api/submit-task")
async def submit_task(req: SubmitTaskRequest):
    # Construct the payload according to the contract
    payload = {
        "request_id": str(uuid.uuid4()),
        "session_id": str(uuid.uuid4()),
        "user_id": "user-demo",
        "tenant_id": "tenant-demo",
        "language": "ar",
        "natural_language_request": req.natural_language_request,
        "original_user_message": req.natural_language_request,
        "authorization": {
            "scopes": ["financial:read", "financial:write"],
            "authenticated_at": "2026-07-13T12:00:00Z",
            "assurance_level": "high"
        },
        "metadata": {
            "source_provider": "voice-assistant"
        }
    }
    
    body_bytes = json.dumps(payload).encode('utf-8')
    timestamp, signature = sign_agentic_request(body_bytes)
    
    headers = {
        "Content-Type": "application/json",
        "X-Interaction-Timestamp": timestamp,
        "X-Interaction-Signature": signature
    }
    
    url = f"{settings.AGENTIC_BASE_URL.rstrip('/')}/agentic/request"
    
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(url, headers=headers, content=body_bytes)
            if r.status_code == 202:
                return r.json()
            else:
                logger.error(f"Agentic submit failed: {r.status_code} {r.text}")
                # Return dummy success if the dummy server isn't up
                return {"status": "dummy_accepted", "task_id": "dummy-task"}
    except Exception as e:
        logger.error(f"Agentic submit exception: {e}")
        # Return a dummy response so the UI doesn't crash during local dev without the backend
        return {"status": "dummy_accepted", "task_id": "dummy-task"}

class ResumeTaskRequest(BaseModel):
    task_id: str
    user_answer: str

@app.post("/api/resume-task")
async def resume_task(req: ResumeTaskRequest):
    payload = {
        "answer": req.user_answer,
        "session_id": "dummy-session"
    }
    
    body_bytes = json.dumps(payload).encode('utf-8')
    timestamp, signature = sign_agentic_request(body_bytes)
    
    headers = {
        "Content-Type": "application/json",
        "X-Interaction-Timestamp": timestamp,
        "X-Interaction-Signature": signature
    }
    
    url = f"{settings.AGENTIC_BASE_URL.rstrip('/')}/agentic/tasks/{req.task_id}/resume"
    
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(url, headers=headers, content=body_bytes)
            return {"status": "resumed"}
    except Exception as e:
        logger.error(f"Agentic resume exception: {e}")
        return {"status": "dummy_resumed"}
