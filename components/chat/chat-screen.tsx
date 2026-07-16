"use client";

import * as React from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Check,
  CircleHelp,
  Loader2,
  Mic,
  MicOff,
  ReceiptText,
  Send,
  ShieldCheck,
  SquarePen,
  StopCircle,
  X,
} from "lucide-react";

import { cn } from "@/lib/utils";
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
import { BrandLogo } from "@/components/nafi/brand-logo";
import { LanguageToggle } from "@/components/i18n/language-toggle";

type AgentEventType =
  | "accepted"
  | "progress"
  | "input_needed"
  | "confirmation_needed"
  | "completed"
  | "rejected"
  | "failed";

type AgentEvent = {
  task_id: string;
  request_id: string;
  session_id: string;
  event_type: AgentEventType;
  user_safe_summary: string;
  details: Record<string, unknown>;
  created_at: string;
};

type AcceptedTask = {
  request_id: string;
  task_id: string;
  status: "accepted" | "rejected";
  user_safe_message?: string;
};

type ActiveTaskResponse = {
  active_task: {
    task_id: string;
    request_id: string;
    status: string;
    pending_event: unknown;
  } | null;
};

type RealtimeConnection = {
  provider: "gemini";
  model: string;
  websocket_url: string;
};

type RealtimeFunctionCall = {
  id?: string;
  name?: string;
  args?: Record<string, unknown>;
};

type RealtimeMessage = {
  serverContent?: {
    inputTranscription?: { text?: string };
    outputTranscription?: { text?: string };
    modelTurn?: {
      parts?: Array<{
        text?: string;
        inlineData?: { data?: string };
      }>;
    };
    interrupted?: boolean;
    generationComplete?: boolean;
    turnComplete?: boolean;
  };
  toolCall?: { functionCalls?: RealtimeFunctionCall[] };
};

type Msg = {
  id: string;
  role: "nafi" | "user";
  text: string;
  taskId?: string;
  event?: AgentEvent;
  pending?: boolean;
};

type SessionStatus = "connecting" | "online" | "offline";
type VoiceStatus = "idle" | "connecting" | "active";
type Translate = (key: string, vars?: Record<string, string>) => string;

type ClarificationSchema = {
  type: "string" | "number" | "integer" | "boolean";
  field: string;
  label: string;
  description?: string;
  choices: Array<string | number | boolean>;
  minimum?: number;
  maximum?: number;
};

const TERMINAL_EVENTS = new Set<AgentEventType>(["completed", "rejected", "failed"]);
const VOICE_RELAY_EVENTS = new Set<AgentEventType>([
  "input_needed",
  "confirmation_needed",
  "completed",
  "rejected",
  "failed",
]);
const AGENT_EVENTS = new Set<AgentEventType>([
  "accepted",
  "progress",
  "input_needed",
  "confirmation_needed",
  "completed",
  "rejected",
  "failed",
]);
const SENSITIVE_QUESTION =
  /password|passcode|\bpin\b|\botp\b|\bcvv\b|access token|recovery secret|كلمة المرور|الرقم السري|رمز التحقق|رمز الدخول/i;
const SENSITIVE_ARGUMENT = /password|passcode|pin|otp|cvv|token|secret/i;
const EQ_BARS = [0.4, 0.8, 1, 0.6, 0.85];
const MAX_VOICE_RELAY_CHARACTERS = 4_000;

function isAgentEvent(value: unknown): value is AgentEvent {
  if (!value || typeof value !== "object") return false;
  const event = value as Partial<AgentEvent>;
  return (
    typeof event.task_id === "string" &&
    typeof event.request_id === "string" &&
    typeof event.session_id === "string" &&
    typeof event.event_type === "string" &&
    AGENT_EVENTS.has(event.event_type as AgentEventType) &&
    typeof event.user_safe_summary === "string" &&
    Boolean(event.details) &&
    typeof event.details === "object"
  );
}

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function newRequestKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
}

function normalizeDecimalDigits(value: string): string {
  return value.replace(/[٠-٩۰-۹]/g, (digit) => {
    const code = digit.charCodeAt(0);
    return String(code >= 0x06f0 ? code - 0x06f0 : code - 0x0660);
  });
}

function eventText(event: AgentEvent): string {
  if (event.event_type === "input_needed") {
    const question = event.details.question;
    return typeof question === "string" ? question : event.user_safe_summary;
  }
  if (event.event_type === "completed") {
    const report = record(event.details.report);
    const summary = typeof report?.summary === "string" ? report.summary : event.user_safe_summary;
    const result = record(report?.result);
    const beneficiaries = Array.isArray(result?.beneficiaries)
      ? result.beneficiaries.map(record).filter((item): item is Record<string, unknown> => Boolean(item))
      : [];
    if (beneficiaries.length === 0) return summary;
    const lines = beneficiaries.map((beneficiary) => {
      const fullName = beneficiary.full_name ?? beneficiary["الاسم الكامل"];
      const shortName = beneficiary.short_name ?? beneficiary["الاسم المختصر"];
      const bankName = beneficiary.bank_name ?? beneficiary["اسم البنك"];
      const names = [shortName, fullName]
        .filter((value): value is string => typeof value === "string" && Boolean(value.trim()))
        .filter((value, index, values) => values.indexOf(value) === index)
        .join(" — ");
      return `• ${names}${typeof bankName === "string" ? ` (${bankName})` : ""}`;
    });
    return `${summary}\n${lines.join("\n")}`;
  }
  return event.user_safe_summary;
}

function clarificationSchema(event: AgentEvent, t: Translate): ClarificationSchema {
  const schema = record(event.details.expected_answer);
  const rawType = schema?.type;
  const type =
    rawType === "number" || rawType === "integer" || rawType === "boolean"
      ? rawType
      : "string";
  const rawField = typeof schema?.field === "string" ? schema.field : "answer";
  const label =
    knownArgumentLabel(rawField, t) ??
    (typeof schema?.label === "string"
      ? schema.label
      : rawField.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()));
  const choices = Array.isArray(schema?.enum)
    ? schema.enum.filter(
        (value): value is string | number | boolean =>
          typeof value === "string" || typeof value === "number" || typeof value === "boolean"
      )
    : [];
  return {
    type,
    field: rawField,
    label,
    description: typeof schema?.description === "string" ? schema.description : undefined,
    choices,
    minimum: typeof schema?.minimum === "number" ? schema.minimum : undefined,
    maximum: typeof schema?.maximum === "number" ? schema.maximum : undefined,
  };
}

function eventLabel(event: AgentEvent, t: Translate): string {
  const labels: Record<AgentEventType, string> = {
    accepted: t("accepted"),
    progress: t("processing"),
    input_needed: t("needsInput"),
    confirmation_needed: t("needsConfirmation"),
    completed: t("completed"),
    rejected: t("rejected"),
    failed: t("failed"),
  };
  return labels[event.event_type];
}

function eventTone(event: AgentEvent): string {
  if (event.event_type === "completed") return "bg-positive/15 text-positive";
  if (event.event_type === "failed" || event.event_type === "rejected") {
    return "bg-negative/15 text-negative";
  }
  if (event.event_type === "confirmation_needed") return "bg-orange/15 text-orange";
  return "bg-primary/15 text-primary";
}

function safeArguments(details: Record<string, unknown>): Array<[string, string]> {
  const args = record(details.arguments);
  if (!args) return [];
  return Object.entries(args)
    .filter(([key]) => !SENSITIVE_ARGUMENT.test(key))
    .map(([key, value]) => {
      const rendered =
        typeof value === "string" || typeof value === "number" || typeof value === "boolean"
          ? String(value)
          : JSON.stringify(value);
      return [key, rendered ?? ""];
    });
}

function knownArgumentLabel(key: string, t: Translate): string | undefined {
  const labels: Record<string, string> = {
    account_reference: t("accountReference"),
    biller: t("biller"),
    benefit_account_number: t("beneficiaryAccountNumber"),
    beneficiary_short_name: t("shortName"),
    full_name_of_benefit_account: t("beneficiaryFullName"),
    symbol: t("investmentSymbol"),
    quantity: t("quantity"),
    amount: t("amount"),
    destination: t("destination"),
    destination_account: t("destinationAccount"),
    gift_message: t("giftMessage"),
    last_four_digits: t("lastFourDigits"),
    name: t("name"),
    participants: t("participants"),
    qatta_name: t("qattaName"),
    recipient: t("recipient"),
    short_name: t("shortName"),
    total_amount: t("totalAmount"),
  };
  return labels[key];
}

function argumentLabel(key: string, t: Translate): string {
  return knownArgumentLabel(key, t) ?? key.replaceAll("_", " ");
}

function reportMetadata(event: AgentEvent): { warnings: string[]; receipts: string[] } {
  const report = record(event.details.report);
  const warnings = Array.isArray(report?.warnings)
    ? report.warnings.filter((item): item is string => typeof item === "string")
    : [];
  const receipts = Array.isArray(report?.receipt_ids)
    ? report.receipt_ids.filter((item): item is string => typeof item === "string")
    : [];
  return { warnings, receipts };
}

function resamplePcm(
  input: Float32Array,
  sourceRate: number,
  targetRate: number
): Float32Array {
  if (sourceRate === targetRate) return input;
  const ratio = sourceRate / targetRate;
  const length = Math.max(1, Math.round(input.length / ratio));
  const output = new Float32Array(length);
  for (let index = 0; index < length; index += 1) {
    const position = index * ratio;
    const left = Math.min(input.length - 1, Math.floor(position));
    const right = Math.min(input.length - 1, left + 1);
    const weight = position - left;
    output[index] = input[left] * (1 - weight) + input[right] * weight;
  }
  return output;
}

function boundedVoiceJson(value: Record<string, unknown>, fallback: string): string {
  const serialized = JSON.stringify(value);
  return serialized.length <= MAX_VOICE_RELAY_CHARACTERS
    ? serialized
    : JSON.stringify({ summary: fallback.slice(0, 1_000), detail_omitted: true });
}

function float32ToBase64Pcm(input: Float32Array): string {
  const bytes = new Uint8Array(input.length * 2);
  const view = new DataView(bytes.buffer);
  for (let index = 0; index < input.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, input[index]));
    view.setInt16(index * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
  }
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return window.btoa(binary);
}

function base64PcmToFloat32(base64: string): Float32Array {
  const binary = window.atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  const view = new DataView(bytes.buffer);
  const output = new Float32Array(Math.floor(bytes.length / 2));
  for (let index = 0; index < output.length; index += 1) {
    const sample = view.getInt16(index * 2, true);
    output[index] = sample / (sample >= 0 ? 32767 : 32768);
  }
  return output;
}

/** Secure chat and realtime voice client for the Nafea interaction backend. */
export function ChatScreen() {
  const { t, lang, dir } = useLang();
  const [messages, setMessages] = React.useState<Msg[]>([]);
  const [input, setInput] = React.useState("");
  const [sessionStatus, setSessionStatus] = React.useState<SessionStatus>("connecting");
  const [voiceStatus, setVoiceStatus] = React.useState<VoiceStatus>("idle");
  const [liveTranscript, setLiveTranscript] = React.useState("");
  const [activeTaskId, setActiveTaskId] = React.useState<string | null>(null);
  const [pendingEvent, setPendingEvent] = React.useState<AgentEvent | null>(null);
  const [clarificationValue, setClarificationValue] = React.useState("");
  const [confirmationOtp, setConfirmationOtp] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [cancelling, setCancelling] = React.useState(false);
  const [startingNewChat, setStartingNewChat] = React.useState(false);
  const [sessionGeneration, setSessionGeneration] = React.useState(0);
  const [taskElapsed, setTaskElapsed] = React.useState(0);
  const [errorMessage, setErrorMessage] = React.useState("");

  const messageIdRef = React.useRef(0);
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const sessionIdRef = React.useRef<string | null>(null);
  const eventSocketRef = React.useRef<WebSocket | null>(null);
  const realtimeSocketRef = React.useRef<WebSocket | null>(null);
  const knownTasksRef = React.useRef(new Map<string, string>());
  const queuedEventsRef = React.useRef<AgentEvent[]>([]);
  const ignoredTaskIdsRef = React.useRef(new Set<string>());
  const currentTaskIdRef = React.useRef<string | null>(null);
  const pendingEventRef = React.useRef<AgentEvent | null>(null);
  const processEventRef = React.useRef<((event: AgentEvent) => void) | null>(null);
  const realtimeToolCallsRef = React.useRef(
    new Map<string, Promise<Record<string, unknown>>>()
  );
  const relayedVoiceEventsRef = React.useRef(new Set<string>());
  const realtimeFinancialActionRef = React.useRef(false);

  const mediaStreamRef = React.useRef<MediaStream | null>(null);
  const inputContextRef = React.useRef<AudioContext | null>(null);
  const outputContextRef = React.useRef<AudioContext | null>(null);
  const micSourceRef = React.useRef<MediaStreamAudioSourceNode | null>(null);
  const processorRef = React.useRef<AudioWorkletNode | null>(null);
  const mutedGainRef = React.useRef<GainNode | null>(null);
  const playerRef = React.useRef<AudioWorkletNode | null>(null);
  const voicePlaybackActiveRef = React.useRef(false);
  const suppressMicUntilRef = React.useRef(0);
  const voiceInputRef = React.useRef("");
  const voiceOutputRef = React.useRef("");

  function nextMessageId(): string {
    messageIdRef.current += 1;
    return `message-${messageIdRef.current}`;
  }

  function setPending(event: AgentEvent | null) {
    const previousClarification = pendingEventRef.current?.details.clarification_id;
    pendingEventRef.current = event;
    setPendingEvent(event);
    if (!event || event.event_type !== "confirmation_needed") setConfirmationOtp("");
    if (
      !event ||
      event.event_type !== "input_needed" ||
      event.details.clarification_id !== previousClarification
    ) {
      setClarificationValue("");
    }
  }

  function clearPendingIfCurrent(expected: AgentEvent) {
    const current = pendingEventRef.current;
    const expectedClarificationId = expected.details.clarification_id;
    const currentClarificationId = current?.details.clarification_id;
    if (
      current?.task_id === expected.task_id &&
      current.event_type === expected.event_type &&
      currentClarificationId === expectedClarificationId
    ) {
      setPending(null);
    }
  }

  const stopVoice = React.useCallback(() => {
    const socket = realtimeSocketRef.current;
    realtimeSocketRef.current = null;
    if (socket && socket.readyState < WebSocket.CLOSING) socket.close();

    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
    micSourceRef.current?.disconnect();
    processorRef.current?.disconnect();
    mutedGainRef.current?.disconnect();
    playerRef.current?.disconnect();
    micSourceRef.current = null;
    processorRef.current = null;
    mutedGainRef.current = null;
    playerRef.current = null;
    voicePlaybackActiveRef.current = false;
    suppressMicUntilRef.current = 0;
    if (inputContextRef.current) void inputContextRef.current.close();
    if (outputContextRef.current) void outputContextRef.current.close();
    inputContextRef.current = null;
    outputContextRef.current = null;
    voiceInputRef.current = "";
    voiceOutputRef.current = "";
    setLiveTranscript("");
    setVoiceStatus("idle");
  }, []);

  function relayTrustedEventToVoice(event: AgentEvent) {
    if (!VOICE_RELAY_EVENTS.has(event.event_type)) return;
    const socket = realtimeSocketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    const relayKey = `${event.task_id}:${event.event_type}:${event.created_at}`;
    if (relayedVoiceEventsRef.current.has(relayKey)) return;

    let text: string;
    if (event.event_type === "input_needed") {
      const question = eventText(event);
      if (SENSITIVE_QUESTION.test(question)) return;
      text =
        "Authoritative clarification. Ask the user this question politely as Nafea, " +
        `without mentioning internal processing: ${question}`;
    } else if (event.event_type === "confirmation_needed") {
      const args = Object.fromEntries(safeArguments(event.details));
      text =
        "Authoritative confirmation. Naturally ask the user to review and use the authenticated " +
        `on-screen controls. Exact safe action: ${boundedVoiceJson(args, event.user_safe_summary)}`;
    } else {
      const report = record(event.details.report);
      const interactionContext = record(report?.interaction_context);
      text =
        "Authoritative result. Present it naturally as Nafea, the user's single assistant. " +
        "Do not mention agents, tools, delegation, or internal processing. " +
        boundedVoiceJson(
          {
            status: event.event_type,
            summary: eventText(event),
            interaction_context: interactionContext,
          },
          eventText(event)
        );
    }

    socket.send(
      JSON.stringify({
        realtimeInput: { text },
      })
    );
    if (relayedVoiceEventsRef.current.size >= 100) {
      const oldest = relayedVoiceEventsRef.current.values().next().value;
      if (oldest) relayedVoiceEventsRef.current.delete(oldest);
    }
    relayedVoiceEventsRef.current.add(relayKey);
  }

  function processAgentEvent(event: AgentEvent) {
    if (ignoredTaskIdsRef.current.has(event.task_id)) return;
    if (event.session_id !== sessionIdRef.current) return;

    const blockedClarification =
      event.event_type === "input_needed" && SENSITIVE_QUESTION.test(eventText(event));
    const workingEvent = event.event_type === "accepted" || event.event_type === "progress";
    const displayText = blockedClarification
      ? t("unsafeClarification")
      : workingEvent
        ? t("chatThinking")
        : event.event_type === "confirmation_needed"
          ? t("reviewAction")
          : eventText(event);

    setMessages((current) => {
      const index = current.findIndex((message) => message.taskId === event.task_id);
      const nextMessage: Msg = {
        id: index >= 0 ? current[index].id : nextMessageId(),
        role: "nafi",
        text: displayText,
        taskId: event.task_id,
        event,
        pending: workingEvent,
      };
      if (index < 0) return [...current, nextMessage];
      return current.map((message, messageIndex) =>
        messageIndex === index ? nextMessage : message
      );
    });

    if (TERMINAL_EVENTS.has(event.event_type)) {
      if (currentTaskIdRef.current === event.task_id) {
        currentTaskIdRef.current = null;
        setActiveTaskId(null);
      }
      if (pendingEventRef.current?.task_id === event.task_id) setPending(null);
    } else {
      currentTaskIdRef.current = event.task_id;
      setActiveTaskId(event.task_id);
      if (event.event_type === "input_needed" && !blockedClarification) setPending(event);
      if (event.event_type === "confirmation_needed") setPending(event);
    }

    if (!blockedClarification && VOICE_RELAY_EVENTS.has(event.event_type)) {
      relayTrustedEventToVoice(event);
    }
  }
  processEventRef.current = processAgentEvent;

  function registerAcceptedTask(accepted: AcceptedTask, optimisticMessageId?: string) {
    knownTasksRef.current.set(accepted.task_id, accepted.request_id);
    if (accepted.status === "accepted") {
      currentTaskIdRef.current = accepted.task_id;
      setActiveTaskId(accepted.task_id);
    }

    setMessages((current) => {
      if (current.some((message) => message.taskId === accepted.task_id)) return current;
      if (optimisticMessageId) {
        return current.map((message) =>
          message.id === optimisticMessageId
            ? {
                ...message,
                text: t("chatThinking"),
                taskId: accepted.task_id,
                pending: true,
              }
            : message
        );
      }
      return [
        ...current,
        {
          id: nextMessageId(),
          role: "nafi",
          text: t("chatThinking"),
          taskId: accepted.task_id,
          pending: true,
        },
      ];
    });

    const queued = queuedEventsRef.current;
    queuedEventsRef.current = [];
    for (const event of queued) {
      const requestId = knownTasksRef.current.get(event.task_id);
      if (requestId === event.request_id) processEventRef.current?.(event);
      else queuedEventsRef.current.push(event);
    }
    void pollTaskUntilActionable(accepted);
  }

  async function pollTaskUntilActionable(accepted: AcceptedTask) {
    // WebSockets provide the fast path. Durable polling closes the race where
    // a reconnect or language switch misses the terminal frame and would
    // otherwise leave the composer disabled forever.
    for (let attempt = 0; attempt < 30; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 1_500));
      if (currentTaskIdRef.current !== accepted.task_id) return;
      try {
        const replay = await nafeaRequest<{ event: unknown }>(
          `/api/tasks/${encodeURIComponent(accepted.task_id)}/latest-event`
        );
        if (!isAgentEvent(replay.event) || replay.event.request_id !== accepted.request_id) {
          continue;
        }
        processEventRef.current?.(replay.event);
        if (
          TERMINAL_EVENTS.has(replay.event.event_type) ||
          replay.event.event_type === "input_needed" ||
          replay.event.event_type === "confirmation_needed"
        ) {
          return;
        }
      } catch {
        // The socket can still complete the task; retry within the bounded window.
      }
    }
  }

  function restoreActiveTask(task: NonNullable<ActiveTaskResponse["active_task"]>) {
    knownTasksRef.current.set(task.task_id, task.request_id);
    currentTaskIdRef.current = task.task_id;
    setActiveTaskId(task.task_id);
    if (isAgentEvent(task.pending_event)) {
      processEventRef.current?.(task.pending_event);
      return;
    }
    setMessages((current) =>
      current.some((message) => message.taskId === task.task_id)
        ? current
        : [
            ...current,
            {
              id: nextMessageId(),
              role: "nafi",
              text: t("chatThinking"),
              taskId: task.task_id,
              pending: true,
            },
          ]
    );
  }

  async function submitFinancialTask(
    request: string,
    idempotencyKey: string,
    optimisticMessageId?: string,
    source: "chat" | "voice" = "chat"
  ): Promise<AcceptedTask> {
    const accepted = await nafeaPost<AcceptedTask>("/api/submit-task", {
      natural_language_request: request,
      idempotency_key: idempotencyKey,
      source,
    });
    registerAcceptedTask(accepted, optimisticMessageId);
    return accepted;
  }

  async function executeRealtimeFunctionCall(
    call: RealtimeFunctionCall
  ): Promise<Record<string, unknown>> {
    const name = call.name ?? "unknown";
    if (name !== "submit_financial_task" && name !== "resume_financial_task") {
      return { error: "Unsupported tool call" };
    }
    if (realtimeFinancialActionRef.current) {
      return { status: "busy", message: "A financial action is already being processed." };
    }

    realtimeFinancialActionRef.current = true;
    try {
      if (name === "submit_financial_task") {
        const request = call.args?.request_details;
        if (typeof request !== "string" || !request.trim()) throw new Error("invalid request");
        if (currentTaskIdRef.current) {
          return {
            status: "already_processing",
            task_id: currentTaskIdRef.current,
          };
        }
        const accepted = await submitFinancialTask(
          request,
          call.id || newRequestKey(),
          undefined,
          "voice"
        );
        return { ...accepted };
      }

      const answer = call.args?.user_answer;
      const pending = pendingEventRef.current;
      if (
        pending?.event_type !== "input_needed" ||
        typeof answer !== "string" ||
        !answer.trim()
      ) {
        return {
          status: "not_waiting_for_clarification",
          message: "Wait for a trusted clarification request before answering.",
        };
      }
      const response = await nafeaPost<Record<string, unknown>>("/api/resume-task", {
          task_id: pending.task_id,
          user_answer: answer.trim(),
        });
      clearPendingIfCurrent(pending);
      return response;
    } catch (error) {
      if (error instanceof NafeaApiError && error.status === 504) {
        return {
          status: "timed_out",
          action_cancelled: true,
          message: error.message,
        };
      }
      return { error: "The secure financial service could not complete this tool call." };
    } finally {
      realtimeFinancialActionRef.current = false;
    }
  }

  async function handleRealtimeFunctionCall(call: RealtimeFunctionCall, socket: WebSocket) {
    const name = call.name ?? "unknown";
    const callKey = call.id ? `${name}:${call.id}` : null;
    let operation = callKey ? realtimeToolCallsRef.current.get(callKey) : undefined;
    if (!operation) {
      operation = executeRealtimeFunctionCall(call);
      if (callKey) {
        if (realtimeToolCallsRef.current.size >= 100) {
          const oldest = realtimeToolCallsRef.current.keys().next().value;
          if (oldest) realtimeToolCallsRef.current.delete(oldest);
        }
        realtimeToolCallsRef.current.set(callKey, operation);
      }
    }
    const response = await operation;

    if (socket.readyState === WebSocket.OPEN) {
      socket.send(
        JSON.stringify({
          toolResponse: {
            functionResponses: [{ id: call.id, name, response }],
          },
        })
      );
    }
  }

  async function handleRealtimeMessage(event: MessageEvent, socket: WebSocket) {
    try {
      const raw = event.data instanceof Blob ? await event.data.text() : String(event.data);
      const message = JSON.parse(raw) as RealtimeMessage;
      const content = message.serverContent;
      const inputChunk = content?.inputTranscription?.text ?? "";
      const outputChunk = content?.outputTranscription?.text ?? "";

      if (inputChunk) {
        voiceInputRef.current += inputChunk;
        setLiveTranscript(voiceInputRef.current);
      }
      if (outputChunk) voiceOutputRef.current += outputChunk;

      for (const part of content?.modelTurn?.parts ?? []) {
        if (part.inlineData?.data) {
          const decoded = base64PcmToFloat32(part.inlineData.data);
          const outputRate = outputContextRef.current?.sampleRate ?? 24_000;
          playerRef.current?.port.postMessage(resamplePcm(decoded, 24_000, outputRate));
        }
        if (part.text && !outputChunk) voiceOutputRef.current += part.text;
      }

      if (content?.interrupted) {
        playerRef.current?.port.postMessage({ action: "clear" });
        voicePlaybackActiveRef.current = false;
        suppressMicUntilRef.current = performance.now() + 200;
        voiceOutputRef.current = "";
      }
      if (content?.generationComplete) {
        playerRef.current?.port.postMessage({ action: "flush" });
      }

      for (const call of message.toolCall?.functionCalls ?? []) {
        void handleRealtimeFunctionCall(call, socket);
      }

      if (content?.turnComplete) {
        const userText = voiceInputRef.current.trim();
        const assistantText = voiceOutputRef.current.trim();
        setMessages((current) => [
          ...current,
          ...(userText
            ? [{ id: nextMessageId(), role: "user" as const, text: userText }]
            : []),
          ...(assistantText
            ? [{ id: nextMessageId(), role: "nafi" as const, text: assistantText }]
            : []),
        ]);
        voiceInputRef.current = "";
        voiceOutputRef.current = "";
        setLiveTranscript("");
      }
    } catch {
      setErrorMessage(t("voiceError"));
    }
  }

  async function startVoice() {
    if (sessionStatus !== "online") return;
    if (!navigator.mediaDevices?.getUserMedia || !window.AudioWorkletNode) {
      setErrorMessage(t("voiceUnavailable"));
      return;
    }

    setErrorMessage("");
    setVoiceStatus("connecting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          autoGainControl: true,
          noiseSuppression: true,
        },
      });
      mediaStreamRef.current = stream;

      const connection = await nafeaPost<RealtimeConnection>("/api/realtime-token", {
        language: lang,
      });
      const socket = new WebSocket(nafeaWebSocketUrl(connection.websocket_url));
      realtimeSocketRef.current = socket;

      socket.onmessage = (message) => void handleRealtimeMessage(message, socket);
      socket.onerror = () => {
        if (realtimeSocketRef.current === socket) setErrorMessage(t("voiceError"));
      };
      socket.onclose = () => {
        if (realtimeSocketRef.current === socket) stopVoice();
      };
      socket.onopen = async () => {
        try {
          const inputContext = new AudioContext({ sampleRate: 16_000 });
          const outputContext = new AudioContext({ sampleRate: 24_000 });
          inputContextRef.current = inputContext;
          outputContextRef.current = outputContext;
          await Promise.all([
            inputContext.audioWorklet.addModule("/pcm-processor.js"),
            outputContext.audioWorklet.addModule("/pcm-player.js"),
          ]);

          const source = inputContext.createMediaStreamSource(stream);
          const processor = new AudioWorkletNode(inputContext, "pcm-processor");
          const mutedGain = inputContext.createGain();
          mutedGain.gain.value = 0;
          source.connect(processor);
          processor.connect(mutedGain);
          mutedGain.connect(inputContext.destination);
          processor.port.onmessage = (audioEvent: MessageEvent<Float32Array>) => {
            if (socket.readyState !== WebSocket.OPEN) return;
            if (performance.now() < suppressMicUntilRef.current) {
              return;
            }
            const pcm = resamplePcm(audioEvent.data, inputContext.sampleRate, 16_000);
            socket.send(
              JSON.stringify({
                realtimeInput: {
                  audio: {
                    mimeType: "audio/pcm;rate=16000",
                    data: float32ToBase64Pcm(pcm),
                  },
                },
              })
            );
          };

          const player = new AudioWorkletNode(outputContext, "pcm-player");
          player.port.onmessage = (playbackEvent: MessageEvent) => {
            const playback = playbackEvent.data as { type?: string; active?: boolean };
            if (playback.type === "playback-error") {
              setErrorMessage(t("voiceError"));
              return;
            }
            if (playback.type !== "playback-state") return;
            voicePlaybackActiveRef.current = Boolean(playback.active);
            if (!playback.active) suppressMicUntilRef.current = performance.now() + 200;
          };
          player.connect(outputContext.destination);
          micSourceRef.current = source;
          processorRef.current = processor;
          mutedGainRef.current = mutedGain;
          playerRef.current = player;
          await Promise.all([inputContext.resume(), outputContext.resume()]);
          if (realtimeSocketRef.current === socket) setVoiceStatus("active");
        } catch {
          setErrorMessage(t("voiceError"));
          stopVoice();
        }
      };
    } catch {
      setErrorMessage(t("voiceError"));
      stopVoice();
    }
  }

  React.useEffect(() => {
    let disposed = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    stopVoice();
    eventSocketRef.current?.close();
    eventSocketRef.current = null;
    sessionIdRef.current = null;
    knownTasksRef.current.clear();
    queuedEventsRef.current = [];
    ignoredTaskIdsRef.current.clear();
    currentTaskIdRef.current = null;
    realtimeToolCallsRef.current.clear();
    relayedVoiceEventsRef.current.clear();
    realtimeFinancialActionRef.current = false;
    setActiveTaskId(null);
    setPending(null);
    setErrorMessage("");
    setSessionStatus("connecting");
    setMessages((current) =>
      current.length > 0
        ? current
        : [{ id: nextMessageId(), role: "nafi", text: t("chatGreeting") }]
    );

    function connectEvents() {
      if (disposed || !sessionIdRef.current) return;
      setSessionStatus("connecting");
      const socket = new WebSocket(nafeaWebSocketUrl("/api/ws"));
      eventSocketRef.current = socket;
      socket.onopen = () => {
        if (!disposed) setSessionStatus("online");
      };
      socket.onmessage = (message) => {
        try {
          const event = JSON.parse(String(message.data)) as unknown;
          if (!isAgentEvent(event) || event.session_id !== sessionIdRef.current) return;
          if (ignoredTaskIdsRef.current.has(event.task_id)) return;
          const requestId = knownTasksRef.current.get(event.task_id);
          if (!requestId) {
            queuedEventsRef.current.push(event);
            return;
          }
          if (requestId === event.request_id) processEventRef.current?.(event);
        } catch {
          // Malformed event frames are ignored; the backend will replay durable events.
        }
      };
      socket.onclose = () => {
        if (disposed) return;
        setSessionStatus("offline");
        reconnectTimer = setTimeout(connectEvents, 1_500);
      };
      socket.onerror = () => socket.close();
    }

    function connectSession() {
      void ensureNafeaSession(lang)
        .then(async (session) => {
          if (disposed) return;
          sessionIdRef.current = session.session_id;
          const recovered = await nafeaRequest<ActiveTaskResponse>("/api/active-task");
          if (disposed) return;
          if (recovered.active_task) restoreActiveTask(recovered.active_task);
          setErrorMessage("");
          connectEvents();
        })
        .catch((error) => {
          if (disposed) return;
          if (error instanceof NafeaApiError && error.status === 401) {
            invalidateNafeaSession();
          }
          setSessionStatus("offline");
          setErrorMessage(t("sessionError"));
          reconnectTimer = setTimeout(connectSession, 1_500);
        });
    }

    connectSession();

    return () => {
      disposed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      eventSocketRef.current?.close();
      eventSocketRef.current = null;
      stopVoice();
    };
  }, [lang, sessionGeneration, stopVoice, t]);

  React.useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, pendingEvent, liveTranscript]);

  React.useEffect(() => {
    if (!activeTaskId) {
      setTaskElapsed(0);
      return;
    }
    const startedAt = Date.now();
    setTaskElapsed(0);
    const interval = window.setInterval(() => {
      setTaskElapsed(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(interval);
  }, [activeTaskId]);

  async function cancelActiveTask(forNewChat = false): Promise<boolean> {
    const taskId = currentTaskIdRef.current;
    if (!taskId) return true;
    setCancelling(true);
    setErrorMessage("");
    try {
      await nafeaPost("/api/cancel-task", { task_id: taskId });
      currentTaskIdRef.current = null;
      setActiveTaskId(null);
      setPending(null);
      if (!forNewChat) {
        setMessages((current) =>
          current.map((message) =>
            message.taskId === taskId
              ? {
                  ...message,
                  text: t("requestCancelled"),
                  event: undefined,
                  pending: false,
                }
              : message
          )
        );
      }
      return true;
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : t("requestError"));
      return false;
    } finally {
      setCancelling(false);
    }
  }

  async function startNewChat() {
    if (startingNewChat || submitting) return;
    setStartingNewChat(true);
    setErrorMessage("");
    const previousTaskId = currentTaskIdRef.current;
    if (previousTaskId) ignoredTaskIdsRef.current.add(previousTaskId);
    try {
      if (!(await cancelActiveTask(true))) {
        if (previousTaskId) ignoredTaskIdsRef.current.delete(previousTaskId);
        return;
      }
      const session = await startNewNafeaChat();
      stopVoice();
      eventSocketRef.current?.close();
      eventSocketRef.current = null;
      sessionIdRef.current = session.session_id;
      knownTasksRef.current.clear();
      queuedEventsRef.current = [];
      realtimeToolCallsRef.current.clear();
      relayedVoiceEventsRef.current.clear();
      setInput("");
      setPending(null);
      setSessionStatus("connecting");
      setMessages([{ id: nextMessageId(), role: "nafi", text: t("chatGreeting") }]);
      setSessionGeneration((current) => current + 1);
    } catch {
      if (previousTaskId) ignoredTaskIdsRef.current.delete(previousTaskId);
      setErrorMessage(t("newChatError"));
    } finally {
      setStartingNewChat(false);
    }
  }

  async function send(text: string) {
    const body = text.trim();
    if (!body || submitting || sessionStatus !== "online") return;
    setErrorMessage("");
    setInput("");
    const optimisticMessageId = nextMessageId();
    setMessages((current) => [
      ...current,
      { id: nextMessageId(), role: "user", text: body },
      {
        id: optimisticMessageId,
        role: "nafi",
        text: t("chatThinking"),
        pending: true,
      },
    ]);
    setSubmitting(true);

    const pending = pendingEventRef.current;
    try {
      if (pending?.event_type === "input_needed") throw new Error(t("provideInCard"));
      if (currentTaskIdRef.current) throw new Error(t("activeTask"));
      await submitFinancialTask(body, newRequestKey(), optimisticMessageId);
    } catch (error) {
      if (pending) setPending(pending);
      setMessages((current) =>
        current.filter((message) => message.id !== optimisticMessageId)
      );
      setErrorMessage(
        error instanceof NafeaApiError && error.status >= 500
          ? t("requestError")
          : error instanceof Error
            ? error.message
            : t("requestError")
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function submitClarification(answer: string | number | boolean) {
    const clarification = pendingEventRef.current;
    if (clarification?.event_type !== "input_needed" || submitting) return;
    const displayAnswer = typeof answer === "boolean" ? (answer ? t("yes") : t("no")) : String(answer);
    const answerMessageId = nextMessageId();
    setSubmitting(true);
    setErrorMessage("");
    clearPendingIfCurrent(clarification);
    setMessages((current) => [
      ...current.map((message) =>
        message.taskId === clarification.task_id &&
        message.event?.details.clarification_id === clarification.details.clarification_id
          ? { ...message, taskId: undefined }
          : message
      ),
      { id: answerMessageId, role: "user", text: displayAnswer },
    ]);
    try {
      await nafeaPost("/api/resume-task", {
        task_id: clarification.task_id,
        user_answer: answer,
      });
    } catch (error) {
      setMessages((current) =>
        current
          .filter((message) => message.id !== answerMessageId)
          .map((message) =>
            !message.taskId &&
            message.event?.details.clarification_id === clarification.details.clarification_id
              ? { ...message, taskId: clarification.task_id }
              : message
          )
      );
      setPending(clarification);
      setErrorMessage(
        error instanceof NafeaApiError && error.status >= 500
          ? t("requestError")
          : error instanceof Error
            ? error.message
            : t("requestError")
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function confirmFinancialTask(approved: boolean) {
    const confirmation = pendingEventRef.current;
    if (confirmation?.event_type !== "confirmation_needed" || submitting) return;
    setSubmitting(true);
    setErrorMessage("");
    try {
      await nafeaPost("/api/confirm-task", {
        task_id: confirmation.task_id,
        approved,
        ...(approved ? { otp_code: confirmationOtp } : {}),
      });
      clearPendingIfCurrent(confirmation);
      setMessages((current) =>
        current.map((message) =>
          message.taskId === confirmation.task_id &&
          message.event?.event_type === "confirmation_needed"
            ? { ...message, text: t("decisionRecorded"), event: undefined, pending: false }
            : message
        )
      );
    } catch (error) {
      setErrorMessage(
        error instanceof NafeaApiError && error.status === 403
          ? t("invalidOtp")
          : error instanceof NafeaApiError
            ? t("requestError")
            : error instanceof Error
            ? error.message
            : t("requestError")
      );
    } finally {
      setSubmitting(false);
    }
  }

  const suggestions = [t("sugNetWorth"), t("sugSpend"), t("sugTransfer")];
  const hasUserMessage = messages.some((message) => message.role === "user");
  const composerDisabled =
    sessionStatus !== "online" ||
    submitting ||
    Boolean(activeTaskId);
  const statusText =
    sessionStatus === "online"
      ? t("online")
      : sessionStatus === "connecting"
        ? t("connecting")
        : t("offline");

  return (
    <div className="mx-auto flex h-dvh w-full max-w-2xl flex-col">
      <header className="flex items-center justify-between gap-3 border-b border-white/[0.06] px-4 py-3 sm:px-5">
        <div className="flex items-center gap-3">
          <span className="relative grid size-10 place-items-center rounded-full bg-gradient-to-br from-primary to-purple">
            <BrandLogo className="h-4 w-6 text-white" />
            <span
              className={cn(
                "absolute -bottom-0.5 -end-0.5 size-3 rounded-full border-2 border-background",
                sessionStatus === "online"
                  ? "bg-positive"
                  : sessionStatus === "connecting"
                    ? "bg-orange"
                    : "bg-negative"
              )}
            />
          </span>
          <div className="leading-tight">
            <p className="text-sm font-semibold">{lang === "ar" ? "نافع" : "Nafi"}</p>
            <p className="text-[11px] text-muted-foreground">{statusText}</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void startNewChat()}
            disabled={startingNewChat || submitting}
            aria-label={activeTaskId ? t("cancelAndNewChat") : t("newChat")}
            title={activeTaskId ? t("cancelAndNewChat") : t("newChat")}
            className="grid size-9 place-items-center rounded-full border border-white/10 bg-white/[0.03] text-muted-foreground transition-colors hover:text-foreground disabled:opacity-40"
          >
            {startingNewChat ? (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            ) : (
              <SquarePen className="size-4" aria-hidden />
            )}
          </button>
          <LanguageToggle disabled={Boolean(activeTaskId) || submitting} />
          <Link
            href="/dashboard"
            aria-label={t("backToDashboard")}
            title={t("backToDashboard")}
            className="grid size-9 place-items-center rounded-full border border-white/10 bg-white/[0.03] text-muted-foreground transition-colors hover:text-foreground"
          >
            <X className="size-4" aria-hidden />
          </Link>
        </div>
      </header>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-5 sm:px-5">
        {messages.map((message) => {
          const metadata = message.event ? reportMetadata(message.event) : null;
          const confirmation =
            pendingEvent?.event_type === "confirmation_needed" &&
            message.taskId === pendingEvent.task_id
              ? pendingEvent
              : null;
          const clarification =
            pendingEvent?.event_type === "input_needed" &&
            message.taskId === pendingEvent.task_id
              ? pendingEvent
              : null;
          const answerSchema = clarification ? clarificationSchema(clarification, t) : null;
          return (
            <div
              key={message.id}
              className={cn(
                "flex items-end gap-2",
                message.role === "user" ? "justify-end" : "justify-start"
              )}
            >
              {message.role === "nafi" && (
                <span className="mb-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-gradient-to-br from-primary to-purple text-white shadow-lg shadow-primary/10">
                  <BrandLogo className="h-2.5 w-4" />
                </span>
              )}
              <div
                className={cn(
                  "max-w-[88%] rounded-2xl px-3.5 py-2.5 text-[13px] leading-relaxed",
                  message.role === "user"
                    ? "bg-gradient-to-br from-primary to-purple text-white"
                    : "border border-white/[0.06] bg-card-2 text-foreground"
                )}
              >
                {message.event &&
                  !["accepted", "progress", "completed"].includes(message.event.event_type) && (
                  <span
                    className={cn(
                      "mb-2 inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold",
                      eventTone(message.event)
                    )}
                  >
                    {eventLabel(message.event, t)}
                  </span>
                )}
                {message.pending ? (
                  <div role="status" aria-live="polite">
                    <div className="flex items-center gap-2">
                      <Loader2 className="size-3.5 animate-spin text-primary" aria-hidden />
                      <p>{message.text}</p>
                    </div>
                    <p className="mt-1.5 text-[10px] text-muted-foreground">
                      {taskElapsed >= 5 ? t("chatStillWorking") : t("chatWorkingHint")}
                    </p>
                  </div>
                ) : (
                  <p className="whitespace-pre-line">{message.text}</p>
                )}

                {metadata && metadata.warnings.length > 0 && (
                  <div className="mt-2 border-t border-white/[0.06] pt-2 text-[11px] text-orange">
                    <span className="font-semibold">{t("warnings")}:</span>{" "}
                    {metadata.warnings.join(" · ")}
                  </div>
                )}
                {metadata && metadata.receipts.length > 0 && (
                  <div className="mt-2 flex items-start gap-1.5 border-t border-white/[0.06] pt-2 text-[11px] text-muted-foreground">
                    <ReceiptText className="mt-0.5 size-3 shrink-0" aria-hidden />
                    <span>
                      <strong className="text-foreground">{t("receipts")}:</strong>{" "}
                      {metadata.receipts.join(", ")}
                    </span>
                  </div>
                )}

                {clarification && answerSchema && (
                  <form
                    onSubmit={(event) => {
                      event.preventDefault();
                      if (clarificationValue.trim()) void submitClarification(clarificationValue);
                    }}
                    className="mt-3 space-y-3 border-t border-primary/30 pt-3"
                  >
                    <div className="flex items-center gap-2 font-semibold text-primary">
                      <CircleHelp className="size-4" aria-hidden />
                      <span>{t("missingInformationTitle")}</span>
                    </div>
                    <div>
                      <label
                        className="block text-[11px] font-medium"
                        htmlFor={`clarification-${clarification.task_id}`}
                      >
                        {answerSchema.label}
                      </label>
                      {answerSchema.description && (
                        <p className="mt-1 text-[11px] text-muted-foreground">
                          {answerSchema.description}
                        </p>
                      )}
                    </div>
                    {answerSchema.type === "boolean" ? (
                      <div className="flex gap-2">
                        <button
                          type="button"
                          disabled={submitting}
                          onClick={() => void submitClarification(true)}
                          className="rounded-full bg-primary px-4 py-1.5 text-[11px] font-semibold text-white disabled:opacity-40"
                        >
                          {t("yes")}
                        </button>
                        <button
                          type="button"
                          disabled={submitting}
                          onClick={() => void submitClarification(false)}
                          className="rounded-full border border-white/10 px-4 py-1.5 text-[11px] font-semibold disabled:opacity-40"
                        >
                          {t("no")}
                        </button>
                      </div>
                    ) : answerSchema.choices.length > 0 ? (
                      <div className="flex flex-wrap gap-2">
                        {answerSchema.choices.map((choice) => (
                          <button
                            key={String(choice)}
                            type="button"
                            disabled={submitting}
                            onClick={() => void submitClarification(choice)}
                            className="rounded-full border border-primary/30 bg-primary/10 px-3 py-1.5 text-[11px] font-semibold text-primary disabled:opacity-40"
                          >
                            {String(choice)}
                          </button>
                        ))}
                      </div>
                    ) : (
                      <div className="flex gap-2">
                        <input
                          id={`clarification-${clarification.task_id}`}
                          type={answerSchema.type === "string" ? "text" : "number"}
                          step={answerSchema.type === "integer" ? 1 : "any"}
                          min={answerSchema.minimum}
                          max={answerSchema.maximum}
                          required
                          autoFocus
                          value={clarificationValue}
                          onChange={(event) => setClarificationValue(event.target.value)}
                          className="min-w-0 flex-1 rounded-xl border border-white/10 bg-black/20 px-3 py-2 outline-none focus:border-primary/50"
                        />
                        <button
                          type="submit"
                          disabled={!clarificationValue.trim() || submitting}
                          className="rounded-xl bg-primary px-3 py-2 text-[11px] font-semibold text-white disabled:opacity-40"
                        >
                          {t("submitInformation")}
                        </button>
                      </div>
                    )}
                    <p className="text-[10px] text-muted-foreground">{t("missingInformationHint")}</p>
                  </form>
                )}

                {confirmation && (
                  <div
                    role="alertdialog"
                    aria-label={t("confirmationTitle")}
                    className="mt-3 space-y-3 border-t border-orange/30 pt-3"
                  >
                    <div className="flex items-center gap-2 font-semibold text-orange">
                      <ShieldCheck className="size-4" aria-hidden />
                      <span>{t("confirmationTitle")}</span>
                    </div>
                    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 rounded-xl bg-black/15 p-3 text-[11px]">
                      {safeArguments(confirmation.details).map(([key, value]) => (
                        <React.Fragment key={key}>
                          <dt className="text-muted-foreground">{argumentLabel(key, t)}</dt>
                          <dd className="text-end font-mono text-foreground">{value}</dd>
                        </React.Fragment>
                      ))}
                    </dl>
                    <p className="text-[11px] text-muted-foreground">{t("confirmationHint")}</p>
                    <label className="block text-[11px] font-medium" htmlFor="confirmation-otp">
                      {t("demoOtp")}
                    </label>
                    <input
                      id="confirmation-otp"
                      type="password"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      maxLength={4}
                      value={confirmationOtp}
                      onChange={(event) =>
                        setConfirmationOtp(
                          normalizeDecimalDigits(event.target.value).replace(/\D/g, "").slice(0, 4)
                        )
                      }
                      className="w-full rounded-xl border border-white/10 bg-black/20 px-3 py-2 font-mono outline-none focus:border-primary/50"
                    />
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        disabled={confirmationOtp.length !== 4 || submitting}
                        onClick={() => void confirmFinancialTask(true)}
                        className="inline-flex items-center gap-1.5 rounded-full bg-positive px-3 py-1.5 text-[11px] font-semibold text-background disabled:opacity-40"
                      >
                        <Check className="size-3" aria-hidden />
                        {t("approve")}
                      </button>
                      <button
                        type="button"
                        disabled={submitting}
                        onClick={() => void confirmFinancialTask(false)}
                        className="rounded-full bg-negative/20 px-3 py-1.5 text-[11px] font-semibold text-negative disabled:opacity-40"
                      >
                        {t("reject")}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {(voiceStatus === "active" || voiceStatus === "connecting") && (
          <div className="flex justify-end">
            <div className="flex max-w-[82%] items-center gap-3 rounded-2xl border border-primary/30 bg-primary/10 px-4 py-3">
              {voiceStatus === "connecting" ? (
                <Loader2 className="size-4 animate-spin text-primary" aria-hidden />
              ) : (
                <span className="flex h-5 items-end gap-[3px]" aria-hidden>
                  {EQ_BARS.map((height, index) => (
                    <span
                      key={index}
                      className="w-[3px] origin-bottom animate-eq rounded-full bg-primary"
                      style={{ height: `${height * 100}%`, animationDelay: `${index * 90}ms` }}
                    />
                  ))}
                </span>
              )}
              <span className="text-[12px] font-medium text-primary">
                {liveTranscript ||
                  (voiceStatus === "connecting" ? t("connecting") : t("listening"))}
              </span>
            </div>
          </div>
        )}
      </div>

      {!hasUserMessage && !activeTaskId && (
        <div className="flex flex-wrap gap-2 px-4 pb-2 sm:px-5">
          {suggestions.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              disabled={sessionStatus !== "online"}
              onClick={() => void send(suggestion)}
              className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-[12px] text-muted-foreground transition-colors hover:text-foreground disabled:opacity-40"
            >
              {suggestion}
            </button>
          ))}
        </div>
      )}

      {errorMessage && (
        <div className="mx-4 mb-2 flex items-start gap-2 rounded-xl border border-negative/30 bg-negative/10 px-3 py-2 text-[12px] text-negative sm:mx-5">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          <span>{errorMessage}</span>
        </div>
      )}

      {activeTaskId && (
        <div className="mx-4 mb-2 flex items-center justify-between gap-3 rounded-xl border border-primary/20 bg-primary/[0.07] px-3 py-2 sm:mx-5">
          <div className="min-w-0">
            <p className="text-[11px] font-medium text-foreground">
              {taskElapsed >= 5 ? t("chatStillWorking") : t("chatWorkingHint")}
            </p>
            <p className="mt-0.5 text-[10px] tabular-nums text-muted-foreground">
              {taskElapsed}s
            </p>
          </div>
          <button
            type="button"
            onClick={() => void cancelActiveTask()}
            disabled={cancelling}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-negative/30 bg-negative/10 px-3 py-1.5 text-[11px] font-semibold text-negative transition-colors hover:bg-negative/20 disabled:opacity-50"
          >
            {cancelling ? (
              <Loader2 className="size-3 animate-spin" aria-hidden />
            ) : (
              <StopCircle className="size-3" aria-hidden />
            )}
            {cancelling ? t("cancellingRequest") : t("cancelRequest")}
          </button>
        </div>
      )}

      <form
        onSubmit={(event) => {
          event.preventDefault();
          void send(input);
        }}
        className="flex items-center gap-2 border-t border-white/[0.06] px-4 py-3 sm:px-5"
      >
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          disabled={composerDisabled}
          placeholder={
            pendingEvent?.event_type === "input_needed"
              ? t("provideInCard")
              : activeTaskId
                ? t("chatWorkingPlaceholder")
                : t("chatPlaceholder")
          }
          className="min-w-0 flex-1 rounded-full border border-white/[0.06] bg-card-2 px-4 py-2.5 text-sm outline-none placeholder:text-faint focus:border-primary/50 disabled:opacity-50"
        />
        <button
          type="button"
          onClick={() => (voiceStatus === "idle" ? void startVoice() : stopVoice())}
          disabled={sessionStatus !== "online" || voiceStatus === "connecting"}
          aria-pressed={voiceStatus === "active"}
          aria-label={voiceStatus === "active" ? t("stopListening") : t("askNafi")}
          className={cn(
            "grid size-11 shrink-0 place-items-center rounded-full transition-colors disabled:opacity-40",
            voiceStatus === "active"
              ? "bg-primary text-white"
              : "border border-white/10 bg-white/[0.03] text-muted-foreground hover:text-foreground"
          )}
        >
          {voiceStatus === "connecting" ? (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          ) : voiceStatus === "active" ? (
            <MicOff className="size-4" aria-hidden />
          ) : (
            <Mic className="size-4" aria-hidden />
          )}
        </button>
        <button
          type="submit"
          disabled={!input.trim() || composerDisabled}
          aria-label={t("send")}
          className="grid size-11 shrink-0 place-items-center rounded-full bg-gradient-to-br from-primary to-purple text-white transition-opacity disabled:opacity-40"
        >
          {submitting ? (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          ) : (
            <Send className={cn("size-4", dir === "rtl" && "-scale-x-100")} aria-hidden />
          )}
        </button>
      </form>
    </div>
  );
}
