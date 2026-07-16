"""Multilingual prompt-injection signals used for defense-in-depth telemetry."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InjectionSignals:
    detected: bool
    codes: tuple[str, ...]


PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("instruction_override", re.compile(r"\b(ignore|disregard|override)\b.{0,40}\b(instruction|policy|prompt|system|developer)", re.I | re.S)),
    ("prompt_exfiltration", re.compile(r"\b(reveal|show|print|repeat)\b.{0,40}\b(system prompt|hidden prompt|developer message)", re.I | re.S)),
    ("credential_request", re.compile(r"\b(otp|one[- ]time password|pin|password|api key|access token|cvv)\b", re.I)),
    ("identity_override", re.compile(r"\b(another user|other user's|change tenant|act as|impersonate)\b", re.I)),
    ("arabic_instruction_override", re.compile(r"(تجاهل|تخطى|تجاوز).{0,40}(التعليمات|السياسة|النظام)", re.S)),
    ("arabic_credential_request", re.compile(r"(رمز التحقق|كلمة المرور|الرقم السري)", re.S)),
    ("arabic_identity_override", re.compile(r"(مستخدم آخر|حساب شخص آخر|انتحل)", re.S)),
)


def detect_injection_signals(text: str) -> InjectionSignals:
    codes = tuple(code for code, pattern in PATTERNS if pattern.search(text))
    return InjectionSignals(bool(codes), codes)
