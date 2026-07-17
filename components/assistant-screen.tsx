"use client";

import * as React from "react";
import {
  AlertCircle,
  ArrowRight,
  Bot,
  Check,
  CircleStop,
  Clock3,
  LoaderCircle,
  Mic,
  MicOff,
  Plus,
  ReceiptText,
  Send,
  ShieldCheck,
  Sparkles,
  UserRound,
  X,
} from "lucide-react";
import { useLang } from "@/lib/i18n";
import {
  ensureNafeaSession,
  invalidateNafeaSession,
  NafeaApiError,
  nafeaPost,
  nafeaRequest,
  nafeaWebSocketUrl,
  startNewNafeaChat,
} from "@/lib/nafea-api";

type AgentEventType = "accepted" | "progress" | "input_needed" | "confirmation_needed" | "completed" | "rejected" | "failed";
type AgentEvent = {
  task_id: string;
  request_id: string;
  session_id: string;
  event_type: AgentEventType;
  user_safe_summary: string;
  details: Record<string, unknown>;
  created_at: string;
};
type AcceptedTask = { request_id: string; task_id: string; status: "accepted" | "rejected"; user_safe_message?: string };
type ActiveTaskResponse = { active_task: { task_id: string; request_id: string; status: string; pending_event: unknown } | null };
type Message = { id: string; role: "user" | "nafi"; text: string; taskId?: string; event?: AgentEvent; pending?: boolean };
type RealtimeFunctionCall = { id?: string; name?: string; args?: Record<string, unknown> };
type RealtimeMessage = {
  serverContent?: {
    inputTranscription?: { text?: string };
    outputTranscription?: { text?: string };
    modelTurn?: { parts?: Array<{ text?: string; inlineData?: { data?: string } }> };
    interrupted?: boolean;
    generationComplete?: boolean;
    turnComplete?: boolean;
  };
  toolCall?: { functionCalls?: RealtimeFunctionCall[] };
};

const TERMINAL = new Set<AgentEventType>(["completed", "rejected", "failed"]);
const VALID_EVENTS = new Set<AgentEventType>(["accepted", "progress", "input_needed", "confirmation_needed", "completed", "rejected", "failed"]);
const VOICE_EVENTS = new Set<AgentEventType>(["input_needed", "confirmation_needed", "completed", "rejected", "failed"]);
const SENSITIVE_QUESTION = /password|passcode|\bpin\b|\botp\b|\bcvv\b|access token|secret|كلمة المرور|الرقم السري|رمز التحقق|رمز الدخول/i;
const SENSITIVE_ARGUMENT = /password|passcode|pin|otp|cvv|token|secret/i;
const VOICE_OUTCOME_SUMMARY_LIMIT = 160;

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function isAgentEvent(value: unknown): value is AgentEvent {
  const event = asRecord(value);
  return Boolean(event && typeof event.task_id === "string" && typeof event.request_id === "string" &&
    typeof event.session_id === "string" && typeof event.event_type === "string" &&
    VALID_EVENTS.has(event.event_type as AgentEventType) && typeof event.user_safe_summary === "string" && asRecord(event.details));
}

function eventText(event: AgentEvent): string {
  if (event.event_type === "input_needed" && typeof event.details.question === "string") return event.details.question;
  if (event.event_type === "completed") {
    const report = asRecord(event.details.report);
    return typeof report?.summary === "string" ? report.summary : event.user_safe_summary;
  }
  return event.user_safe_summary;
}

function voiceOutcomeSummary(event: AgentEvent): string {
  const voiceContext = asRecord(event.details.voice_context);
  if (typeof voiceContext?.summary === "string" && voiceContext.summary.trim()) {
    return voiceContext.summary.trim();
  }
  const report = asRecord(event.details.report);
  const source = event.event_type === "completed" && typeof report?.summary === "string"
    ? report.summary
    : event.user_safe_summary;
  const normalized = source.replace(/\s+/g, " ").trim();
  if (normalized.length <= VOICE_OUTCOME_SUMMARY_LIMIT) return normalized;
  const sentence = normalized.match(/^.*?[.!?؟](?:\s|$)/)?.[0]?.trim();
  if (sentence && sentence.length <= VOICE_OUTCOME_SUMMARY_LIMIT) return sentence;
  const prefix = normalized.slice(0, VOICE_OUTCOME_SUMMARY_LIMIT - 1).trimEnd();
  const boundary = prefix.lastIndexOf(" ");
  return `${boundary >= VOICE_OUTCOME_SUMMARY_LIMIT / 2 ? prefix.slice(0, boundary).trimEnd() : prefix}…`;
}

function randomKey() {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
}

function resamplePcm(input: Float32Array, sourceRate: number, targetRate: number): Float32Array {
  if (sourceRate === targetRate) return input;
  const ratio = sourceRate / targetRate;
  const output = new Float32Array(Math.max(1, Math.round(input.length / ratio)));
  for (let index = 0; index < output.length; index += 1) {
    const position = index * ratio;
    const left = Math.min(input.length - 1, Math.floor(position));
    const right = Math.min(input.length - 1, left + 1);
    output[index] = input[left] * (1 - (position - left)) + input[right] * (position - left);
  }
  return output;
}

function float32ToBase64Pcm(input: Float32Array): string {
  const bytes = new Uint8Array(input.length * 2);
  const view = new DataView(bytes.buffer);
  input.forEach((sample, index) => {
    const bounded = Math.max(-1, Math.min(1, sample));
    view.setInt16(index * 2, bounded < 0 ? bounded * 0x8000 : bounded * 0x7fff, true);
  });
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return window.btoa(binary);
}

function base64PcmToFloat32(base64: string): Float32Array {
  const binary = window.atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  const view = new DataView(bytes.buffer);
  const output = new Float32Array(Math.floor(bytes.length / 2));
  for (let index = 0; index < output.length; index += 1) {
    const sample = view.getInt16(index * 2, true);
    output[index] = sample / (sample >= 0 ? 32767 : 32768);
  }
  return output;
}

export function AssistantScreen({ initialPrompt = "" }: { initialPrompt?: string }) {
  const { t, lang, dir } = useLang();
  const [messages, setMessages] = React.useState<Message[]>([]);
  const [input, setInput] = React.useState(initialPrompt);
  const [sessionStatus, setSessionStatus] = React.useState<"connecting" | "online" | "offline">("connecting");
  const [voiceStatus, setVoiceStatus] = React.useState<"idle" | "connecting" | "active">("idle");
  const [liveTranscript, setLiveTranscript] = React.useState("");
  const [activeTaskId, setActiveTaskId] = React.useState<string | null>(null);
  const [pending, setPendingState] = React.useState<AgentEvent | null>(null);
  const [answer, setAnswer] = React.useState("");
  const [otp, setOtp] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [cancelling, setCancelling] = React.useState(false);
  const [newChatLoading, setNewChatLoading] = React.useState(false);
  const [error, setError] = React.useState("");
  const [taskSeconds, setTaskSeconds] = React.useState(0);
  const [generation, setGeneration] = React.useState(0);

  const idRef = React.useRef(0);
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const sessionIdRef = React.useRef<string | null>(null);
  const eventSocketRef = React.useRef<WebSocket | null>(null);
  const realtimeSocketRef = React.useRef<WebSocket | null>(null);
  const knownTasksRef = React.useRef(new Map<string, string>());
  const queuedEventsRef = React.useRef<AgentEvent[]>([]);
  const ignoredTasksRef = React.useRef(new Set<string>());
  const currentTaskRef = React.useRef<string | null>(null);
  const pendingRef = React.useRef<AgentEvent | null>(null);
  const processEventRef = React.useRef<(event: AgentEvent) => void>(() => undefined);
  const voiceToolCallsRef = React.useRef(new Map<string, Promise<Record<string, unknown>>>());
  const relayedEventsRef = React.useRef(new Set<string>());
  const voiceActionRef = React.useRef(false);
  const sentInitialPromptRef = React.useRef(false);

  const streamRef = React.useRef<MediaStream | null>(null);
  const inputContextRef = React.useRef<AudioContext | null>(null);
  const outputContextRef = React.useRef<AudioContext | null>(null);
  const sourceRef = React.useRef<MediaStreamAudioSourceNode | null>(null);
  const processorRef = React.useRef<AudioWorkletNode | null>(null);
  const gainRef = React.useRef<GainNode | null>(null);
  const playerRef = React.useRef<AudioWorkletNode | null>(null);
  const playbackRef = React.useRef(false);
  const suppressMicRef = React.useRef(0);
  const voiceInputRef = React.useRef("");
  const voiceOutputRef = React.useRef("");

  function nextId() { idRef.current += 1; return `message-${idRef.current}`; }
  function setPending(event: AgentEvent | null) {
    pendingRef.current = event;
    setPendingState(event);
    setAnswer("");
    setOtp("");
  }

  const stopVoice = React.useCallback(() => {
    const socket = realtimeSocketRef.current;
    realtimeSocketRef.current = null;
    if (socket && socket.readyState < WebSocket.CLOSING) socket.close();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    sourceRef.current?.disconnect(); processorRef.current?.disconnect(); gainRef.current?.disconnect(); playerRef.current?.disconnect();
    sourceRef.current = null; processorRef.current = null; gainRef.current = null; playerRef.current = null;
    if (inputContextRef.current) void inputContextRef.current.close();
    if (outputContextRef.current) void outputContextRef.current.close();
    inputContextRef.current = null; outputContextRef.current = null;
    playbackRef.current = false; suppressMicRef.current = 0;
    voiceInputRef.current = ""; voiceOutputRef.current = "";
    setLiveTranscript(""); setVoiceStatus("idle");
  }, []);

  function relayEventToVoice(event: AgentEvent) {
    const socket = realtimeSocketRef.current;
    if (!VOICE_EVENTS.has(event.event_type) || !socket || socket.readyState !== WebSocket.OPEN) return;
    const key = `${event.task_id}:${event.event_type}:${event.created_at}`;
    if (relayedEventsRef.current.has(key)) return;
    let text = "";
    if (event.event_type === "input_needed") {
      const question = eventText(event);
      if (SENSITIVE_QUESTION.test(question)) return;
      text = `Authoritative clarification. Ask this politely without mentioning internal processing: ${question}`;
    } else if (event.event_type === "confirmation_needed") {
      const safe = Object.fromEntries(Object.entries(asRecord(event.details.arguments) ?? {}).filter(([key]) => !SENSITIVE_ARGUMENT.test(key)));
      text = `Authoritative confirmation. Ask the user to review and use the authenticated on-screen controls. Safe details: ${JSON.stringify(safe).slice(0, 3000)}`;
    } else {
      const summary = voiceOutcomeSummary(event);
      text = `Authoritative task outcome. Speak this safe summary naturally and lead with the result: ${JSON.stringify(summary)}. Do not invent or infer anything beyond it. Then mention that the full report is available in chat.`;
    }
    socket.send(JSON.stringify({ realtimeInput: { text } }));
    relayedEventsRef.current.add(key);
  }

  function processAgentEvent(event: AgentEvent) {
    if (ignoredTasksRef.current.has(event.task_id) || event.session_id !== sessionIdRef.current) return;
    const blocked = event.event_type === "input_needed" && SENSITIVE_QUESTION.test(eventText(event));
    const working = event.event_type === "accepted" || event.event_type === "progress";
    const text = blocked ? t("requestError") : working ? t("thinking") : event.event_type === "confirmation_needed" ? t("confirmationHint") : eventText(event);
    setMessages((current) => {
      const index = current.findIndex((message) => message.taskId === event.task_id);
      const next: Message = { id: index >= 0 ? current[index].id : nextId(), role: "nafi", text, taskId: event.task_id, event, pending: working };
      return index < 0 ? [...current, next] : current.map((message, messageIndex) => messageIndex === index ? next : message);
    });
    if (TERMINAL.has(event.event_type)) {
      if (event.event_type === "completed") window.dispatchEvent(new Event("nafea:financial-action"));
      if (currentTaskRef.current === event.task_id) { currentTaskRef.current = null; setActiveTaskId(null); }
      if (pendingRef.current?.task_id === event.task_id) setPending(null);
    } else {
      currentTaskRef.current = event.task_id; setActiveTaskId(event.task_id);
      if (!blocked && (event.event_type === "input_needed" || event.event_type === "confirmation_needed")) setPending(event);
    }
    if (!blocked) relayEventToVoice(event);
  }
  processEventRef.current = processAgentEvent;

  async function pollTask(accepted: AcceptedTask) {
    for (let attempt = 0; attempt < 30; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 1500));
      if (currentTaskRef.current !== accepted.task_id) return;
      try {
        const replay = await nafeaRequest<{ event: unknown }>(`/api/tasks/${encodeURIComponent(accepted.task_id)}/latest-event`);
        if (!isAgentEvent(replay.event) || replay.event.request_id !== accepted.request_id) continue;
        processEventRef.current(replay.event);
        if (TERMINAL.has(replay.event.event_type) || replay.event.event_type === "input_needed" || replay.event.event_type === "confirmation_needed") return;
      } catch { /* WebSocket remains the fast path. */ }
    }
  }

  function registerTask(accepted: AcceptedTask, optimisticId?: string) {
    knownTasksRef.current.set(accepted.task_id, accepted.request_id);
    currentTaskRef.current = accepted.task_id; setActiveTaskId(accepted.task_id);
    setMessages((current) => optimisticId ? current.map((message) => message.id === optimisticId ? { ...message, taskId: accepted.task_id } : message) : current);
    const queued = queuedEventsRef.current; queuedEventsRef.current = [];
    queued.forEach((event) => knownTasksRef.current.get(event.task_id) === event.request_id ? processEventRef.current(event) : queuedEventsRef.current.push(event));
    void pollTask(accepted);
  }

  async function submitTask(request: string, key: string, optimisticId?: string, source: "chat" | "voice" = "chat", evidence?: string) {
    const accepted = await nafeaPost<AcceptedTask>("/api/submit-task", {
      natural_language_request: request, idempotency_key: key, source,
      ...(evidence ? { voice_evidence: evidence } : {}),
    });
    registerTask(accepted, optimisticId);
    return accepted;
  }

  async function executeVoiceFunction(call: RealtimeFunctionCall): Promise<Record<string, unknown>> {
    if (voiceActionRef.current) return { status: "busy" };
    voiceActionRef.current = true;
    try {
      if (call.name === "submit_financial_task") {
        const request = call.args?.voice_transcript;
        const evidence = call.args?.voice_evidence;
        if (typeof request !== "string" || !request.trim() || typeof evidence !== "string") return { error: "Invalid signed voice transcript" };
        if (currentTaskRef.current) return { status: "already_processing", task_id: currentTaskRef.current };
        return await submitTask(request, call.id || randomKey(), undefined, "voice", evidence);
      }
      if (call.name === "resume_financial_task") {
        const event = pendingRef.current;
        const userAnswer = call.args?.user_answer;
        if (event?.event_type !== "input_needed" || typeof userAnswer !== "string" || !userAnswer.trim()) return { status: "not_waiting" };
        const response = await nafeaPost<Record<string, unknown>>("/api/resume-task", { task_id: event.task_id, user_answer: userAnswer.trim() });
        setPending(null); return response;
      }
      return { error: "Unsupported voice action" };
    } catch { return { error: "The secure financial service could not complete this voice action." }; }
    finally { voiceActionRef.current = false; }
  }

  async function handleVoiceCall(call: RealtimeFunctionCall, socket: WebSocket) {
    const key = call.id ? `${call.name}:${call.id}` : randomKey();
    let operation = voiceToolCallsRef.current.get(key);
    if (!operation) { operation = executeVoiceFunction(call); voiceToolCallsRef.current.set(key, operation); }
    const response = await operation;
    if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ toolResponse: { functionResponses: [{ id: call.id, name: call.name, response }] } }));
  }

  async function handleVoiceMessage(event: MessageEvent, socket: WebSocket) {
    try {
      const raw = event.data instanceof Blob ? await event.data.text() : String(event.data);
      const message = JSON.parse(raw) as RealtimeMessage;
      const content = message.serverContent;
      const inputChunk = content?.inputTranscription?.text ?? "";
      const outputChunk = content?.outputTranscription?.text ?? "";
      if (inputChunk) { voiceInputRef.current += inputChunk; setLiveTranscript(voiceInputRef.current); }
      if (outputChunk) voiceOutputRef.current += outputChunk;
      for (const part of content?.modelTurn?.parts ?? []) {
        if (part.inlineData?.data) {
          const outputRate = outputContextRef.current?.sampleRate ?? 24000;
          playerRef.current?.port.postMessage(resamplePcm(base64PcmToFloat32(part.inlineData.data), 24000, outputRate));
        }
        if (part.text && !outputChunk) voiceOutputRef.current += part.text;
      }
      if (content?.interrupted) { playerRef.current?.port.postMessage({ action: "clear" }); playbackRef.current = false; suppressMicRef.current = performance.now() + 200; voiceOutputRef.current = ""; }
      if (content?.generationComplete) playerRef.current?.port.postMessage({ action: "flush" });
      for (const call of message.toolCall?.functionCalls ?? []) void handleVoiceCall(call, socket);
      if (content?.turnComplete) {
        const userText = voiceInputRef.current.trim(); const assistantText = voiceOutputRef.current.trim();
        setMessages((current) => [...current,
          ...(userText ? [{ id: nextId(), role: "user" as const, text: userText }] : []),
          ...(assistantText ? [{ id: nextId(), role: "nafi" as const, text: assistantText }] : []),
        ]);
        voiceInputRef.current = ""; voiceOutputRef.current = ""; setLiveTranscript("");
      }
    } catch { setError(t("voiceError")); }
  }

  async function startVoice() {
    if (sessionStatus !== "online") return;
    if (!navigator.mediaDevices?.getUserMedia || !window.AudioWorkletNode) { setError(t("voiceUnavailable")); return; }
    setVoiceStatus("connecting"); setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, autoGainControl: true, noiseSuppression: true } });
      streamRef.current = stream;
      const connection = await nafeaPost<{ websocket_url: string }>("/api/realtime-token", { language: lang });
      const socket = new WebSocket(nafeaWebSocketUrl(connection.websocket_url)); realtimeSocketRef.current = socket;
      socket.onmessage = (message) => void handleVoiceMessage(message, socket);
      socket.onerror = () => setError(t("voiceError"));
      socket.onclose = () => { if (realtimeSocketRef.current === socket) stopVoice(); };
      socket.onopen = async () => {
        try {
          const inputContext = new AudioContext({ sampleRate: 16000 }); const outputContext = new AudioContext({ sampleRate: 24000 });
          inputContextRef.current = inputContext; outputContextRef.current = outputContext;
          await Promise.all([inputContext.audioWorklet.addModule("/pcm-processor.js"), outputContext.audioWorklet.addModule("/pcm-player.js")]);
          const source = inputContext.createMediaStreamSource(stream); const processor = new AudioWorkletNode(inputContext, "pcm-processor"); const gain = inputContext.createGain(); gain.gain.value = 0;
          source.connect(processor); processor.connect(gain); gain.connect(inputContext.destination);
          processor.port.onmessage = (audio: MessageEvent<Float32Array>) => {
            if (socket.readyState !== WebSocket.OPEN || playbackRef.current || performance.now() < suppressMicRef.current) return;
            const pcm = resamplePcm(audio.data, inputContext.sampleRate, 16000);
            socket.send(JSON.stringify({ realtimeInput: { audio: { mimeType: "audio/pcm;rate=16000", data: float32ToBase64Pcm(pcm) } } }));
          };
          const player = new AudioWorkletNode(outputContext, "pcm-player");
          player.port.onmessage = (playback: MessageEvent<{ type?: string; active?: boolean }>) => {
            if (playback.data.type === "playback-error") setError(t("voiceError"));
            if (playback.data.type === "playback-state") { playbackRef.current = Boolean(playback.data.active); if (!playback.data.active) suppressMicRef.current = performance.now() + 200; }
          };
          player.connect(outputContext.destination);
          sourceRef.current = source; processorRef.current = processor; gainRef.current = gain; playerRef.current = player;
          await Promise.all([inputContext.resume(), outputContext.resume()]); setVoiceStatus("active");
        } catch { setError(t("voiceError")); stopVoice(); }
      };
    } catch { setError(t("voiceError")); stopVoice(); }
  }

  React.useEffect(() => {
    let disposed = false; let timer: ReturnType<typeof setTimeout> | null = null;
    stopVoice(); eventSocketRef.current?.close(); knownTasksRef.current.clear(); queuedEventsRef.current = [];
    currentTaskRef.current = null; setActiveTaskId(null); setPending(null); setSessionStatus("connecting"); setError("");
    setMessages([{ id: nextId(), role: "nafi", text: t("greeting") }]);
    function connectEvents() {
      if (disposed || !sessionIdRef.current) return;
      const socket = new WebSocket(nafeaWebSocketUrl("/api/ws")); eventSocketRef.current = socket;
      socket.onopen = () => !disposed && setSessionStatus("online");
      socket.onmessage = (message) => { try {
        const event = JSON.parse(String(message.data));
        if (!isAgentEvent(event) || event.session_id !== sessionIdRef.current || ignoredTasksRef.current.has(event.task_id)) return;
        const requestId = knownTasksRef.current.get(event.task_id);
        if (!requestId) queuedEventsRef.current.push(event); else if (requestId === event.request_id) processEventRef.current(event);
      } catch { /* Durable polling covers malformed or missed frames. */ } };
      socket.onclose = () => { if (!disposed) { setSessionStatus("offline"); timer = setTimeout(connectEvents, 1500); } };
      socket.onerror = () => socket.close();
    }
    void ensureNafeaSession(lang).then(async (session) => {
      if (disposed) return; sessionIdRef.current = session.session_id;
      const recovered = await nafeaRequest<ActiveTaskResponse>("/api/active-task");
      if (recovered.active_task) {
        knownTasksRef.current.set(recovered.active_task.task_id, recovered.active_task.request_id);
        currentTaskRef.current = recovered.active_task.task_id; setActiveTaskId(recovered.active_task.task_id);
        if (isAgentEvent(recovered.active_task.pending_event)) processEventRef.current(recovered.active_task.pending_event);
      }
      connectEvents();
    }).catch((requestError) => {
      if (requestError instanceof NafeaApiError && requestError.status === 401) invalidateNafeaSession();
      if (!disposed) { setSessionStatus("offline"); setError(t("sessionError")); }
    });
    return () => { disposed = true; if (timer) clearTimeout(timer); eventSocketRef.current?.close(); stopVoice(); };
  }, [generation, lang, stopVoice, t]);

  React.useEffect(() => { scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" }); }, [messages, pending, liveTranscript]);
  React.useEffect(() => { if (!activeTaskId) { setTaskSeconds(0); return; } const started = Date.now(); const timer = window.setInterval(() => setTaskSeconds(Math.floor((Date.now() - started) / 1000)), 1000); return () => clearInterval(timer); }, [activeTaskId]);

  async function sendMessage(text: string) {
    const body = text.trim(); if (!body || submitting || sessionStatus !== "online") return;
    if (pendingRef.current?.event_type === "input_needed") { setError(t("inputHint")); return; }
    if (currentTaskRef.current) { setError(t("activeTask")); return; }
    setInput(""); setError(""); setSubmitting(true);
    const optimisticId = nextId();
    setMessages((current) => [...current, { id: nextId(), role: "user", text: body }, { id: optimisticId, role: "nafi", text: t("thinking"), pending: true }]);
    try { await submitTask(body, randomKey(), optimisticId); }
    catch (requestError) { setMessages((current) => current.filter((message) => message.id !== optimisticId)); setError(requestError instanceof NafeaApiError && requestError.status < 500 ? requestError.message : t("requestError")); }
    finally { setSubmitting(false); }
  }

  React.useEffect(() => {
    if (initialPrompt && sessionStatus === "online" && !sentInitialPromptRef.current && !activeTaskId) {
      sentInitialPromptRef.current = true; void sendMessage(initialPrompt);
    }
  }, [activeTaskId, initialPrompt, sessionStatus]);

  async function cancelTask(silent = false) {
    const taskId = currentTaskRef.current; if (!taskId) return true;
    setCancelling(true); setError("");
    try { await nafeaPost("/api/cancel-task", { task_id: taskId }); currentTaskRef.current = null; setActiveTaskId(null); setPending(null);
      if (!silent) setMessages((current) => current.map((message) => message.taskId === taskId ? { ...message, text: t("cancelled"), event: undefined, pending: false } : message)); return true;
    } catch { setError(t("requestError")); return false; } finally { setCancelling(false); }
  }

  async function newChat() {
    if (newChatLoading) return; setNewChatLoading(true); setError("");
    const previousTask = currentTaskRef.current; if (previousTask) ignoredTasksRef.current.add(previousTask);
    try { if (!(await cancelTask(true))) return; await startNewNafeaChat(); stopVoice(); eventSocketRef.current?.close(); knownTasksRef.current.clear(); queuedEventsRef.current = []; setInput(""); setMessages([]); setGeneration((value) => value + 1); }
    catch { if (previousTask) ignoredTasksRef.current.delete(previousTask); setError(t("newChatError")); }
    finally { setNewChatLoading(false); }
  }

  async function submitClarification(value: string | number | boolean) {
    const event = pendingRef.current; if (event?.event_type !== "input_needed" || submitting) return;
    setSubmitting(true); setError("");
    try { await nafeaPost("/api/resume-task", { task_id: event.task_id, user_answer: value }); setPending(null); setMessages((current) => [...current, { id: nextId(), role: "user", text: typeof value === "boolean" ? String(value) : String(value) }]); }
    catch (requestError) { setError(requestError instanceof NafeaApiError ? requestError.message : t("requestError")); }
    finally { setSubmitting(false); }
  }

  async function confirmTask(approved: boolean) {
    const event = pendingRef.current; if (event?.event_type !== "confirmation_needed" || submitting) return;
    setSubmitting(true); setError("");
    try { await nafeaPost("/api/confirm-task", { task_id: event.task_id, approved, ...(approved ? { otp_code: otp } : {}) }); setPending(null); }
    catch (requestError) { setError(requestError instanceof NafeaApiError ? requestError.message : t("requestError")); }
    finally { setSubmitting(false); }
  }

  const suggestions = lang === "ar" ? ["كم رصيد محفظتي؟", "حلل مصروفاتي هذا الشهر", "اعرض فواتيري غير المسددة"] : ["What’s my wallet balance?", "Analyze this month’s spending", "Show my unpaid bills"];
  const composerDisabled = sessionStatus !== "online" || submitting || Boolean(activeTaskId);

  return <div className="assistant-layout">
    <section className="assistant-conversation">
      <header className="assistant-header">
        <div><span className="assistant-avatar"><Sparkles size={20} /></span><div><h1>{t("assistantTitle")}</h1><p><i className={`status-dot ${sessionStatus}`} />{t(sessionStatus)}</p></div></div>
        <button type="button" className="secondary-button compact" onClick={() => void newChat()} disabled={newChatLoading || submitting}>
          {newChatLoading ? <LoaderCircle className="spin" size={16} /> : <Plus size={17} />}{t("newChat")}
        </button>
      </header>
      <div className="message-scroll" ref={scrollRef}>
        <div className="assistant-intro"><span><Bot size={24} /></span><h2>{t("assistantTitle")}</h2><p>{t("assistantSubtitle")}</p></div>
        <div className="messages">
          {messages.map((message) => <MessageBubble key={message.id} message={message} />)}
          {liveTranscript ? <div className="message-row user"><span className="message-person"><UserRound size={15} /></span><div className="message-bubble live"><span className="listening-dot" />{liveTranscript}</div></div> : null}
        </div>
        {messages.filter((message) => message.role === "user").length === 0 ? <div className="suggestion-grid">
          {suggestions.map((suggestion) => <button type="button" key={suggestion} onClick={() => void sendMessage(suggestion)}><Sparkles size={15} /><span>{suggestion}</span><ArrowRight size={15} className={dir === "rtl" ? "flip" : ""} /></button>)}
        </div> : null}
      </div>
      {pending?.event_type === "input_needed" ? <ClarificationCard event={pending} value={answer} setValue={setAnswer} submit={submitClarification} loading={submitting} /> : null}
      {pending?.event_type === "confirmation_needed" ? <ConfirmationCard event={pending} otp={otp} setOtp={setOtp} submit={confirmTask} loading={submitting} /> : null}
      {error ? <div className="assistant-error" role="alert"><AlertCircle size={17} /><span>{error}</span><button type="button" onClick={() => setError("")}><X size={16} /></button></div> : null}
      {activeTaskId && !pending ? <div className="task-progress"><div><Clock3 size={17} /><span>{taskSeconds > 5 ? t("workingLong") : t("working")} <small>{taskSeconds}s</small></span></div><button type="button" onClick={() => void cancelTask()} disabled={cancelling}><CircleStop size={16} />{t("cancel")}</button></div> : null}
      <form className="assistant-composer" onSubmit={(event) => { event.preventDefault(); void sendMessage(input); }}>
        <button type="button" className={`voice-button ${voiceStatus === "active" ? "active" : ""}`} onClick={() => voiceStatus === "idle" ? void startVoice() : stopVoice()} disabled={sessionStatus !== "online" || voiceStatus === "connecting"} aria-label={voiceStatus === "active" ? t("stopVoice") : t("startVoice")}>
          {voiceStatus === "connecting" ? <LoaderCircle className="spin" size={19} /> : voiceStatus === "active" ? <MicOff size={20} /> : <Mic size={20} />}
        </button>
        <input value={input} onChange={(event) => setInput(event.target.value)} placeholder={activeTaskId ? t("working") : t("placeholder")} disabled={composerDisabled} />
        <button type="submit" className="send-button" disabled={!input.trim() || composerDisabled} aria-label={t("send")}>
          {submitting ? <LoaderCircle className="spin" size={18} /> : <Send size={18} />}
        </button>
      </form>
    </section>
    <aside className={`voice-panel ${voiceStatus === "active" ? "active" : ""}`}>
      <div className="voice-visual"><i /><i /><i /><i /><i /><i /><i /></div>
      <span className="voice-panel-icon">{voiceStatus === "active" ? <Mic size={25} /> : <Sparkles size={25} />}</span>
      <h2>{voiceStatus === "active" ? t("listening") : t("startVoice")}</h2>
      <p>{voiceStatus === "active" ? liveTranscript || t("assistantSubtitle") : t("assistantSubtitle")}</p>
      <button type="button" className={voiceStatus === "active" ? "danger-button" : "primary-button"} onClick={() => voiceStatus === "idle" ? void startVoice() : stopVoice()} disabled={sessionStatus !== "online" || voiceStatus === "connecting"}>
        {voiceStatus === "active" ? <MicOff size={18} /> : <Mic size={18} />}{voiceStatus === "active" ? t("stopVoice") : t("startVoice")}
      </button>
      <div className="voice-security"><ShieldCheck size={16} /><span>{t("securityCopy")}</span></div>
    </aside>
  </div>;
}

function MessageBubble({ message }: { message: Message }) {
  const { t } = useLang();
  const report = message.event ? asRecord(message.event.details.report) : null;
  return <div className={`message-row ${message.role}${report ? " with-report" : ""}`}>
    <span className="message-person">{message.role === "nafi" ? <Sparkles size={15} /> : <UserRound size={15} />}</span>
    <div className={`message-bubble ${message.pending ? "pending" : ""}`}>
      {message.pending ? <LoaderCircle className="spin" size={15} /> : null}<p>{message.text}</p>
      {message.event && TERMINAL.has(message.event.event_type) ? <span className={`event-badge ${message.event.event_type}`}>
        {message.event.event_type === "completed" ? <Check size={13} /> : <AlertCircle size={13} />}{t(message.event.event_type)}
      </span> : null}
      {report ? <FullReport report={report} /> : null}
    </div>
  </div>;
}

const REPORT_LABELS: Record<string, string> = {
  status: "reportStatus",
  summary: "reportSummary",
  actions: "reportActions",
  result: "reportResults",
  warnings: "warnings",
  receipt_ids: "receipts",
  needs_follow_up: "reportFollowUp",
  interaction_context: "reportContext",
  response_kind: "reportResponseType",
  user_goal: "reportUserGoal",
  key_facts: "reportKeyFacts",
  suggested_next_steps: "reportNextSteps",
};

function FullReport({ report }: { report: Record<string, unknown> }) {
  const { t } = useLang();
  return <section className="full-report" aria-label={t("fullReport")}>
    <strong className="full-report-title"><ReceiptText size={15} />{t("fullReport")}</strong>
    <dl className="report-fields">
      {Object.entries(report).map(([key, value]) => <div className="report-field" key={key}>
        <dt>{t(REPORT_LABELS[key] ?? key.replaceAll("_", " "))}</dt>
        <dd><ReportValue value={value} /></dd>
      </div>)}
    </dl>
  </section>;
}

function ReportValue({ value }: { value: unknown }) {
  const { t } = useLang();
  if (value === null || value === undefined || value === "") return <span className="report-empty">{t("reportNone")}</span>;
  if (typeof value === "boolean") return <span>{t(value ? "yes" : "no")}</span>;
  if (typeof value !== "object") return <span>{String(value)}</span>;
  if (Array.isArray(value)) {
    if (!value.length) return <span className="report-empty">{t("reportNone")}</span>;
    return <ul>{value.map((item, index) => <li key={index}><ReportValue value={item} /></li>)}</ul>;
  }
  if (!Object.keys(value as Record<string, unknown>).length) return <span className="report-empty">{t("reportNone")}</span>;
  return <dl className="report-nested">
    {Object.entries(value as Record<string, unknown>).map(([key, nestedValue]) => <div key={key}>
      <dt>{t(REPORT_LABELS[key] ?? key.replaceAll("_", " "))}</dt>
      <dd><ReportValue value={nestedValue} /></dd>
    </div>)}
  </dl>;
}

function ClarificationCard({ event, value, setValue, submit, loading }: { event: AgentEvent; value: string; setValue: (value: string) => void; submit: (value: string | number | boolean) => void; loading: boolean }) {
  const { t } = useLang(); const schema = asRecord(event.details.expected_answer); const type = schema?.type; const choices = Array.isArray(schema?.enum) ? schema.enum.filter((item): item is string | number | boolean => ["string", "number", "boolean"].includes(typeof item)) : [];
  return <div className="action-card clarification-card"><div className="action-card-title"><span><Sparkles size={18} /></span><div><strong>{t("inputNeeded")}</strong><p>{String(event.details.question ?? event.user_safe_summary)}</p></div></div>
    {choices.length ? <div className="choice-grid">{choices.map((choice) => <button type="button" key={String(choice)} disabled={loading} onClick={() => void submit(choice)}>{typeof choice === "boolean" ? t(choice ? "yes" : "no") : String(choice)}</button>)}</div> : type === "boolean" ? <div className="choice-grid"><button type="button" onClick={() => submit(true)}>{t("yes")}</button><button type="button" onClick={() => submit(false)}>{t("no")}</button></div> : <form onSubmit={(formEvent) => { formEvent.preventDefault(); if (value.trim()) submit(type === "number" || type === "integer" ? Number(value) : value.trim()); }}><input value={value} onChange={(inputEvent) => setValue(inputEvent.target.value)} type={type === "number" || type === "integer" ? "number" : "text"} min={typeof schema?.minimum === "number" ? schema.minimum : undefined} max={typeof schema?.maximum === "number" ? schema.maximum : undefined} autoFocus /><button className="primary-button" disabled={!value.trim() || loading}>{loading ? <LoaderCircle className="spin" size={16} /> : null}{t("submitAnswer")}</button></form>}
    <small><ShieldCheck size={13} /> {t("inputHint")}</small></div>;
}

function ConfirmationCard({ event, otp, setOtp, submit, loading }: { event: AgentEvent; otp: string; setOtp: (value: string) => void; submit: (approved: boolean) => void; loading: boolean }) {
  const { t } = useLang(); const args = Object.entries(asRecord(event.details.arguments) ?? {}).filter(([key]) => !SENSITIVE_ARGUMENT.test(key));
  return <div className="action-card confirmation-card"><div className="action-card-title"><span><ShieldCheck size={19} /></span><div><strong>{t("confirmation")}</strong><p>{event.user_safe_summary}</p></div></div>
    {args.length ? <dl>{args.map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{typeof value === "object" ? JSON.stringify(value) : String(value)}</dd></div>)}</dl> : null}
    <div className="confirmation-actions"><label><span>{t("demoOtp")}</span><input className="otp-input small" type="text" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]*" maxLength={4} placeholder="1111" value={otp} onChange={(inputEvent) => setOtp(inputEvent.target.value.replace(/\D/g, "").slice(0, 4))} /></label><button type="button" className="primary-button" disabled={otp.length !== 4 || loading} onClick={() => submit(true)}>{loading ? <LoaderCircle className="spin" size={16} /> : <ShieldCheck size={16} />}{t("approve")}</button><button type="button" className="text-button negative-text" disabled={loading} onClick={() => submit(false)}>{t("reject")}</button></div>
    <small><ShieldCheck size={13} /> {t("otpHint")}</small></div>;
}
