"""Banking provider selection and startup/readiness reporting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import httpx

from .config import AgenticSettings
from .live_adapters import SaudiOpenBankingAdapter, SaudiOpenBankingProfile


class ProviderSelectionError(ValueError):
    """Raised when the configured runtime/provider pair is unsupported."""


@dataclass(frozen=True, slots=True)
class BankingProviderRuntime:
    """Selected provider boundary.

    Mock mode intentionally has no live profile or client, guaranteeing that a
    zero-key demo cannot accidentally call an external bank.  Live mode builds
    and validates the selected client at startup using environment values only.
    """

    mode: str
    provider_name: str
    live_adapter: SaudiOpenBankingAdapter | None = None

    @classmethod
    def from_settings(
        cls,
        settings: AgenticSettings,
        *,
        environment: Mapping[str, str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> "BankingProviderRuntime":
        if settings.provider_mode == "mock":
            if settings.banking_provider != "mock":
                raise ProviderSelectionError("Mock mode requires the mock banking provider")
            return cls(mode="mock", provider_name="mock")
        if settings.provider_mode != "live":
            raise ProviderSelectionError(f"Unsupported banking mode: {settings.provider_mode}")
        if settings.banking_provider != "saudi_open_banking":
            raise ProviderSelectionError(f"Unsupported live banking provider: {settings.banking_provider}")
        profile = SaudiOpenBankingProfile.from_env(environment)
        adapter = SaudiOpenBankingAdapter(profile, transport=transport)
        return cls(mode="live", provider_name="saudi_open_banking", live_adapter=adapter)

    @property
    def configured(self) -> bool:
        return self.mode == "mock" or self.live_adapter is not None

    def readiness(self) -> dict[str, Any]:
        if self.mode == "mock":
            return {
                "status": "ready",
                "mode": "mock",
                "provider": "mock",
                "configured": True,
                "network_checked": False,
            }
        assert self.live_adapter is not None
        provider = self.live_adapter.readiness()
        return {
            "status": "ready" if provider["configured"] else "not_ready",
            "mode": "live",
            "provider": self.provider_name,
            "configured": bool(provider["configured"]),
            "network_checked": False,
            "provider_profile": provider,
        }

    def capabilities(self) -> dict[str, bool]:
        if self.mode == "mock":
            return {
                "account_information": True,
                "payment_initiation": True,
                "beneficiary_write": False,
            }
        assert self.live_adapter is not None
        profile = self.live_adapter.profile
        return {
            "account_information": profile.account_information_enabled,
            "payment_initiation": profile.payment_initiation_enabled,
            "beneficiary_write": profile.beneficiary_write_enabled,
        }
