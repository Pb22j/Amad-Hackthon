"""Configurable, fail-closed Saudi Open Banking HTTP boundary.

There is no universal Saudi bank endpoint or authentication profile.  This
module therefore owns only a small canonical transport contract and makes the
provider-specific pieces (paths, headers, auth mode, versions, and mTLS) env
configuration.  Mock mode never imports credentials or makes network calls.
"""

from __future__ import annotations

import asyncio
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import quote, urlparse

import httpx


class LiveProviderConfigurationError(RuntimeError):
    """Raised before a live request when provider onboarding is incomplete."""


class LiveProviderRequestError(RuntimeError):
    """Safe provider failure that never contains response bodies or secrets."""

    def __init__(
        self,
        operation: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        ambiguous: bool = False,
    ) -> None:
        self.operation = operation
        self.status_code = status_code
        self.retryable = retryable
        self.ambiguous = ambiguous
        suffix = f" (HTTP {status_code})" if status_code is not None else ""
        super().__init__(f"Saudi Open Banking {operation} failed{suffix}")


_AUTH_MODES = {
    "api_key",
    "bearer_token",
    "api_key_bearer_token",
    "oauth_client_credentials",
    "api_key_oauth_client_credentials",
}
_OAUTH_MODES = {"oauth_client_credentials", "api_key_oauth_client_credentials"}
_API_KEY_MODES = {"api_key", "api_key_bearer_token", "api_key_oauth_client_credentials"}
_BEARER_MODES = {"bearer_token", "api_key_bearer_token"}
_HEADER_NAME = re.compile(r"^[A-Za-z0-9-]+$")


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _value(environment: Mapping[str, str], *names: str, default: str = "") -> str:
    for name in names:
        value = environment.get(name)
        if value is not None:
            return str(value).strip()
    return default


@dataclass(frozen=True, slots=True)
class SaudiOpenBankingProfile:
    """Environment-backed provider profile with conditional auth requirements.

    ``api_key`` is the easiest aggregator/sandbox integration.  OAuth client
    credentials is supported for application tokens.  A customer-bound token
    obtained by a future consent/SCA flow can always be passed explicitly to a
    request and takes precedence over the configured application token.
    """

    provider_id: str = "saudi_open_banking"
    base_url: str = ""
    auth_mode: str = "api_key"
    client_id: str = ""
    client_secret: str = field(default="", repr=False)
    api_key: str = field(default="", repr=False)
    api_key_header: str = "X-API-Key"
    access_token: str = field(default="", repr=False)
    customer_context_id: str = field(default="", repr=False)
    customer_context_header: str = "X-Customer-Context-ID"
    token_url: str = ""
    token_scope: str = ""
    token_audience: str = ""
    token_client_auth_method: str = "client_secret_basic"
    mtls_required: bool = False
    mtls_cert_path: str = ""
    mtls_key_path: str = ""
    verify_ssl: bool = True
    allow_insecure_http: bool = False
    timeout_seconds: float = 20.0
    api_version: str = ""
    api_version_header: str = "X-API-Version"
    idempotency_header: str = "X-Idempotency-Key"
    interaction_header: str = "X-FAPI-Interaction-ID"
    account_information_enabled: bool = True
    payment_initiation_enabled: bool = True
    beneficiary_write_enabled: bool = False
    accounts_path: str = "/accounts"
    balances_path: str = "/accounts/{account_id}/balances"
    transactions_path: str = "/accounts/{account_id}/transactions"
    payment_path: str = "/payments"
    payment_status_path: str = "/payments/{payment_id}"
    beneficiaries_path: str = "/beneficiaries"
    beneficiary_path: str = "/beneficiaries/{beneficiary_id}"

    @classmethod
    def from_env(cls, environment: Mapping[str, str] | None = None) -> "SaudiOpenBankingProfile":
        import os

        env = os.environ if environment is None else environment
        timeout_raw = _value(env, "SAUDI_OPEN_BANKING_TIMEOUT_SECONDS", "SAUDI_OB_TIMEOUT_SECONDS", default="20")
        try:
            timeout = float(timeout_raw)
        except ValueError as exc:
            raise LiveProviderConfigurationError("SAUDI_OPEN_BANKING_TIMEOUT_SECONDS must be numeric") from exc
        return cls(
            provider_id=_value(env, "SAUDI_OPEN_BANKING_PROVIDER_ID", "SAUDI_OB_PROFILE", default="saudi_open_banking"),
            base_url=_value(env, "SAUDI_OPEN_BANKING_BASE_URL", "SAUDI_OB_BASE_URL").rstrip("/"),
            auth_mode=_value(env, "SAUDI_OPEN_BANKING_AUTH_MODE", "SAUDI_OB_AUTH_MODE", default="api_key").lower(),
            client_id=_value(env, "SAUDI_OPEN_BANKING_CLIENT_ID", "SAUDI_OB_CLIENT_ID"),
            client_secret=_value(env, "SAUDI_OPEN_BANKING_CLIENT_SECRET", "SAUDI_OB_CLIENT_SECRET"),
            api_key=_value(env, "SAUDI_OPEN_BANKING_API_KEY", "SAUDI_OB_API_KEY"),
            api_key_header=_value(env, "SAUDI_OPEN_BANKING_API_KEY_HEADER", "SAUDI_OB_API_KEY_HEADER", default="X-API-Key"),
            access_token=_value(env, "SAUDI_OPEN_BANKING_ACCESS_TOKEN", "SAUDI_OB_ACCESS_TOKEN"),
            customer_context_id=_value(
                env, "SAUDI_OPEN_BANKING_CUSTOMER_CONTEXT_ID", "SAUDI_OB_CUSTOMER_CONTEXT_ID"
            ),
            customer_context_header=_value(
                env,
                "SAUDI_OPEN_BANKING_CUSTOMER_CONTEXT_HEADER",
                "SAUDI_OB_CUSTOMER_CONTEXT_HEADER",
                default="X-Customer-Context-ID",
            ),
            token_url=_value(env, "SAUDI_OPEN_BANKING_TOKEN_URL", "SAUDI_OB_TOKEN_URL"),
            token_scope=_value(env, "SAUDI_OPEN_BANKING_SCOPES", "SAUDI_OB_SCOPES"),
            token_audience=_value(env, "SAUDI_OPEN_BANKING_AUDIENCE", "SAUDI_OB_AUDIENCE"),
            token_client_auth_method=_value(
                env,
                "SAUDI_OPEN_BANKING_TOKEN_CLIENT_AUTH_METHOD",
                "SAUDI_OB_TOKEN_CLIENT_AUTH_METHOD",
                default="client_secret_basic",
            ).lower(),
            mtls_required=_bool(_value(env, "SAUDI_OPEN_BANKING_MTLS_REQUIRED", "SAUDI_OB_MTLS_REQUIRED"), False),
            mtls_cert_path=_value(env, "SAUDI_OPEN_BANKING_MTLS_CERT_PATH", "SAUDI_OB_MTLS_CERT_PATH"),
            mtls_key_path=_value(env, "SAUDI_OPEN_BANKING_MTLS_KEY_PATH", "SAUDI_OB_MTLS_KEY_PATH"),
            verify_ssl=_bool(_value(env, "SAUDI_OPEN_BANKING_VERIFY_SSL", "SAUDI_OB_VERIFY_SSL"), True),
            allow_insecure_http=_bool(
                _value(env, "SAUDI_OPEN_BANKING_ALLOW_INSECURE_HTTP", "SAUDI_OB_ALLOW_INSECURE_HTTP"), False
            ),
            timeout_seconds=timeout,
            api_version=_value(env, "SAUDI_OPEN_BANKING_API_VERSION", "SAUDI_OB_API_VERSION"),
            api_version_header=_value(
                env, "SAUDI_OPEN_BANKING_API_VERSION_HEADER", "SAUDI_OB_API_VERSION_HEADER", default="X-API-Version"
            ),
            idempotency_header=_value(
                env, "SAUDI_OPEN_BANKING_IDEMPOTENCY_HEADER", "SAUDI_OB_IDEMPOTENCY_HEADER", default="X-Idempotency-Key"
            ),
            interaction_header=_value(
                env, "SAUDI_OPEN_BANKING_INTERACTION_HEADER", "SAUDI_OB_INTERACTION_HEADER", default="X-FAPI-Interaction-ID"
            ),
            account_information_enabled=_bool(
                _value(env, "SAUDI_OPEN_BANKING_AIS_ENABLED", "SAUDI_OB_AIS_ENABLED"), True
            ),
            payment_initiation_enabled=_bool(
                _value(env, "SAUDI_OPEN_BANKING_PIS_ENABLED", "SAUDI_OB_PIS_ENABLED"), True
            ),
            beneficiary_write_enabled=_bool(
                _value(env, "SAUDI_OPEN_BANKING_BENEFICIARY_WRITE_ENABLED", "SAUDI_OB_BENEFICIARY_WRITE_ENABLED"),
                False,
            ),
            accounts_path=_value(env, "SAUDI_OPEN_BANKING_ACCOUNTS_PATH", "SAUDI_OB_ACCOUNTS_PATH", default="/accounts"),
            balances_path=_value(
                env,
                "SAUDI_OPEN_BANKING_BALANCES_PATH",
                "SAUDI_OB_BALANCES_PATH",
                default="/accounts/{account_id}/balances",
            ),
            transactions_path=_value(
                env,
                "SAUDI_OPEN_BANKING_TRANSACTIONS_PATH",
                "SAUDI_OB_TRANSACTIONS_PATH",
                default="/accounts/{account_id}/transactions",
            ),
            payment_path=_value(env, "SAUDI_OPEN_BANKING_PAYMENT_PATH", "SAUDI_OB_PAYMENT_PATH", default="/payments"),
            payment_status_path=_value(
                env,
                "SAUDI_OPEN_BANKING_PAYMENT_STATUS_PATH",
                "SAUDI_OB_PAYMENT_STATUS_PATH",
                default="/payments/{payment_id}",
            ),
            beneficiaries_path=_value(
                env, "SAUDI_OPEN_BANKING_BENEFICIARIES_PATH", "SAUDI_OB_BENEFICIARIES_PATH", default="/beneficiaries"
            ),
            beneficiary_path=_value(
                env,
                "SAUDI_OPEN_BANKING_BENEFICIARY_PATH",
                "SAUDI_OB_BENEFICIARY_PATH",
                default="/beneficiaries/{beneficiary_id}",
            ),
        )

    @property
    def uses_api_key(self) -> bool:
        return self.auth_mode in _API_KEY_MODES

    @property
    def uses_oauth(self) -> bool:
        return self.auth_mode in _OAUTH_MODES

    @property
    def uses_static_bearer(self) -> bool:
        return self.auth_mode in _BEARER_MODES

    @property
    def has_customer_authorization(self) -> bool:
        """Whether a single-user sandbox consent context is configured."""
        return bool((self.uses_static_bearer and self.access_token) or self.customer_context_id)

    def missing_requirements(self, *, check_files: bool = True) -> list[str]:
        missing: list[str] = []
        if not self.base_url:
            missing.append("SAUDI_OPEN_BANKING_BASE_URL")
        if self.uses_api_key and not self.api_key:
            missing.append("SAUDI_OPEN_BANKING_API_KEY")
        if self.uses_static_bearer and not self.access_token:
            missing.append("SAUDI_OPEN_BANKING_ACCESS_TOKEN")
        if self.uses_oauth:
            required = {
                "SAUDI_OPEN_BANKING_TOKEN_URL": self.token_url,
                "SAUDI_OPEN_BANKING_CLIENT_ID": self.client_id,
                "SAUDI_OPEN_BANKING_CLIENT_SECRET": self.client_secret,
            }
            missing.extend(name for name, value in required.items() if not value)
        if self.mtls_required:
            required_paths = {
                "SAUDI_OPEN_BANKING_MTLS_CERT_PATH": self.mtls_cert_path,
                "SAUDI_OPEN_BANKING_MTLS_KEY_PATH": self.mtls_key_path,
            }
            missing.extend(name for name, value in required_paths.items() if not value)
            if check_files:
                missing.extend(
                    f"{name} (file not found)"
                    for name, value in required_paths.items()
                    if value and not Path(value).expanduser().is_file()
                )
        return missing

    def _validation_errors(self) -> list[str]:
        errors: list[str] = []
        if self.auth_mode not in _AUTH_MODES:
            errors.append("SAUDI_OPEN_BANKING_AUTH_MODE is unsupported")
        if self.token_client_auth_method not in {"client_secret_basic", "client_secret_post"}:
            errors.append("SAUDI_OPEN_BANKING_TOKEN_CLIENT_AUTH_METHOD is unsupported")
        if self.timeout_seconds <= 0:
            errors.append("SAUDI_OPEN_BANKING_TIMEOUT_SECONDS must be positive")
        for label, url in (("base URL", self.base_url), ("token URL", self.token_url)):
            if not url:
                continue
            parsed = urlparse(url)
            if label == "token URL" and not parsed.scheme:
                continue
            if parsed.scheme not in {"https", "http"} or not parsed.netloc:
                errors.append(f"Saudi Open Banking {label} is invalid")
            elif parsed.scheme != "https" and not self.allow_insecure_http:
                errors.append(f"Saudi Open Banking {label} must use HTTPS")
        for name, value in {
            "API key header": self.api_key_header,
            "customer context header": self.customer_context_header,
            "API version header": self.api_version_header,
            "idempotency header": self.idempotency_header,
            "interaction header": self.interaction_header,
        }.items():
            if not _HEADER_NAME.fullmatch(value):
                errors.append(f"Saudi Open Banking {name} is invalid")
        for name, path in {
            "accounts path": self.accounts_path,
            "balances path": self.balances_path,
            "transactions path": self.transactions_path,
            "payment path": self.payment_path,
            "payment status path": self.payment_status_path,
            "beneficiaries path": self.beneficiaries_path,
            "beneficiary path": self.beneficiary_path,
        }.items():
            if not path.startswith("/") or path.startswith("//") or "://" in path:
                errors.append(f"Saudi Open Banking {name} must be a relative absolute path")
        return errors

    def ensure_usable(self, *, check_files: bool = True) -> None:
        problems = self.missing_requirements(check_files=check_files) + self._validation_errors()
        if problems:
            raise LiveProviderConfigurationError(
                "Live Saudi Open Banking is not configured: " + ", ".join(problems)
            )

    def readiness(self) -> dict[str, Any]:
        problems = self.missing_requirements() + self._validation_errors()
        return {
            "provider": self.provider_id,
            "configured": not problems,
            "auth_mode": self.auth_mode,
            "mtls_enabled": self.mtls_required,
            "api_version": self.api_version or None,
            "network_checked": False,
            "missing": problems,
            "customer_authorization_configured": self.has_customer_authorization,
            "capabilities": {
                "account_information": self.account_information_enabled,
                "payment_initiation": self.payment_initiation_enabled,
                "beneficiary_write": self.beneficiary_write_enabled,
            },
        }


class SaudiOpenBankingAdapter:
    """Async canonical client for AIS/PIS and optional payee endpoints.

    The injected ``transport`` is used by contract tests and provider sandbox
    fixtures, so the complete auth and request mapping can be verified without
    external network access.
    """

    def __init__(
        self,
        profile: SaudiOpenBankingProfile,
        *,
        timeout_seconds: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        profile.ensure_usable(check_files=transport is None)
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise LiveProviderConfigurationError("Saudi Open Banking timeout must be positive")
        self.profile = profile
        self.timeout_seconds = timeout_seconds or profile.timeout_seconds
        self._transport = transport
        self._clock = clock
        self._token: str = ""
        self._token_expires_at = 0.0
        self._token_lock = threading.Lock()

    def readiness(self) -> dict[str, Any]:
        return self.profile.readiness()

    def _client(self) -> httpx.AsyncClient:
        options: dict[str, Any] = {
            # A trailing slash plus relative endpoint paths preserves provider
            # base prefixes such as ``https://host/open-banking/v1``.
            "base_url": f"{self.profile.base_url.rstrip('/')}/",
            "timeout": self.timeout_seconds,
            "verify": self.profile.verify_ssl,
            "follow_redirects": False,
        }
        if self._transport is not None:
            options["transport"] = self._transport
        if self.profile.mtls_required:
            options["cert"] = (self.profile.mtls_cert_path, self.profile.mtls_key_path)
        return httpx.AsyncClient(**options)

    async def _application_token(self) -> str:
        if self.profile.uses_static_bearer:
            return self.profile.access_token
        if not self.profile.uses_oauth:
            return ""
        if self._token and self._clock() < self._token_expires_at:
            return self._token
        # The service can invoke the same adapter from several worker event
        # loops. Acquire the cross-loop lock off-loop to avoid blocking ASGI.
        await asyncio.to_thread(self._token_lock.acquire)
        try:
            if self._token and self._clock() < self._token_expires_at:
                return self._token
            form = {"grant_type": "client_credentials"}
            if self.profile.token_scope:
                form["scope"] = self.profile.token_scope
            if self.profile.token_audience:
                form["audience"] = self.profile.token_audience
            auth: tuple[str, str] | None = None
            if self.profile.token_client_auth_method == "client_secret_basic":
                auth = (self.profile.client_id, self.profile.client_secret)
            else:
                form["client_id"] = self.profile.client_id
                form["client_secret"] = self.profile.client_secret
            headers = {"Accept": "application/json"}
            if self.profile.uses_api_key:
                headers[self.profile.api_key_header] = self.profile.api_key
            try:
                async with self._client() as client:
                    token_target = self.profile.token_url if urlparse(self.profile.token_url).scheme else self.profile.token_url.lstrip("/")
                    response = await client.post(token_target, data=form, headers=headers, auth=auth)
                    response.raise_for_status()
                    payload = response.json()
            except httpx.HTTPStatusError as exc:
                raise LiveProviderRequestError(
                    "token request", status_code=exc.response.status_code, retryable=exc.response.status_code >= 500
                ) from exc
            except (httpx.HTTPError, ValueError) as exc:
                raise LiveProviderRequestError("token request", retryable=True) from exc
            if not isinstance(payload, dict) or not isinstance(payload.get("access_token"), str) or not payload["access_token"]:
                raise LiveProviderRequestError("token response validation")
            try:
                lifetime = max(1, int(payload.get("expires_in", 300)))
            except (TypeError, ValueError) as exc:
                raise LiveProviderRequestError("token response validation") from exc
            self._token = payload["access_token"]
            self._token_expires_at = self._clock() + max(1, lifetime - min(30, lifetime // 10))
            return self._token
        finally:
            self._token_lock.release()

    async def _headers(
        self,
        *,
        access_token: str | None,
        idempotency_key: str = "",
        interaction_id: str = "",
    ) -> dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": "Nafi-Agentic/1.0"}
        if self.profile.uses_api_key:
            headers[self.profile.api_key_header] = self.profile.api_key
        if self.profile.customer_context_id:
            headers[self.profile.customer_context_header] = self.profile.customer_context_id
        token = access_token or await self._application_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if self.profile.api_version:
            headers[self.profile.api_version_header] = self.profile.api_version
        if idempotency_key:
            headers[self.profile.idempotency_header] = idempotency_key
        if interaction_id:
            headers[self.profile.interaction_header] = interaction_id
        return headers

    @staticmethod
    def _path(template: str, **values: str) -> str:
        encoded = {name: quote(str(value), safe="") for name, value in values.items()}
        try:
            return template.format(**encoded)
        except (KeyError, ValueError) as exc:
            raise LiveProviderConfigurationError("A Saudi Open Banking endpoint path template is invalid") from exc

    async def list_accounts(self, access_token: str | None = None) -> Mapping[str, Any]:
        if not self.profile.account_information_enabled:
            raise LiveProviderConfigurationError("The selected provider profile does not enable account information")
        return await self._request("GET", self.profile.accounts_path, access_token=access_token)

    async def list_transactions(
        self, account_id: str, access_token: str | None = None
    ) -> Mapping[str, Any]:
        if not self.profile.account_information_enabled:
            raise LiveProviderConfigurationError("The selected provider profile does not enable account information")
        path = self._path(self.profile.transactions_path, account_id=account_id)
        return await self._request("GET", path, access_token=access_token)

    async def get_balances(
        self, account_id: str, access_token: str | None = None
    ) -> Mapping[str, Any]:
        if not self.profile.account_information_enabled:
            raise LiveProviderConfigurationError("The selected provider profile does not enable account information")
        path = self._path(self.profile.balances_path, account_id=account_id)
        return await self._request("GET", path, access_token=access_token)

    async def initiate_payment(
        self,
        payment: Mapping[str, Any],
        *,
        access_token: str | None = None,
        idempotency_key: str,
        interaction_id: str,
    ) -> Mapping[str, Any]:
        if not self.profile.payment_initiation_enabled:
            raise LiveProviderConfigurationError("The selected provider profile does not enable payment initiation")
        if not idempotency_key or not interaction_id:
            raise LiveProviderConfigurationError(
                "Live payment requests require idempotency and FAPI interaction identifiers"
            )
        return await self._request(
            "POST",
            self.profile.payment_path,
            json_body=dict(payment),
            access_token=access_token,
            idempotency_key=idempotency_key,
            interaction_id=interaction_id,
        )

    async def get_payment_status(
        self, payment_id: str, *, access_token: str | None = None, interaction_id: str = ""
    ) -> Mapping[str, Any]:
        if not self.profile.payment_initiation_enabled:
            raise LiveProviderConfigurationError("The selected provider profile does not enable payment initiation")
        path = self._path(self.profile.payment_status_path, payment_id=payment_id)
        return await self._request("GET", path, access_token=access_token, interaction_id=interaction_id)

    async def add_beneficiary(
        self,
        beneficiary: Mapping[str, Any],
        *,
        access_token: str | None = None,
        idempotency_key: str,
        interaction_id: str,
    ) -> Mapping[str, Any]:
        if not self.profile.beneficiary_write_enabled:
            raise LiveProviderConfigurationError("The selected provider profile does not enable beneficiary writes")
        if not idempotency_key or not interaction_id:
            raise LiveProviderConfigurationError(
                "Live beneficiary mutations require idempotency and FAPI interaction identifiers"
            )
        return await self._request(
            "POST",
            self.profile.beneficiaries_path,
            json_body=dict(beneficiary),
            access_token=access_token,
            idempotency_key=idempotency_key,
            interaction_id=interaction_id,
        )

    async def delete_beneficiary(
        self,
        beneficiary_id: str,
        *,
        access_token: str | None = None,
        idempotency_key: str,
        interaction_id: str,
    ) -> Mapping[str, Any]:
        if not self.profile.beneficiary_write_enabled:
            raise LiveProviderConfigurationError("The selected provider profile does not enable beneficiary writes")
        if not idempotency_key or not interaction_id:
            raise LiveProviderConfigurationError(
                "Live beneficiary mutations require idempotency and FAPI interaction identifiers"
            )
        path = self._path(self.profile.beneficiary_path, beneficiary_id=beneficiary_id)
        return await self._request(
            "DELETE",
            path,
            access_token=access_token,
            idempotency_key=idempotency_key,
            interaction_id=interaction_id,
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        access_token: str | None,
        json_body: Mapping[str, Any] | None = None,
        idempotency_key: str = "",
        interaction_id: str = "",
    ) -> Mapping[str, Any]:
        headers = await self._headers(
            access_token=access_token,
            idempotency_key=idempotency_key,
            interaction_id=interaction_id,
        )
        try:
            async with self._client() as client:
                response = await client.request(method, path.lstrip("/"), headers=headers, json=json_body)
                response.raise_for_status()
                data = {} if response.status_code == 204 or not response.content else response.json()
        except httpx.TimeoutException as exc:
            raise LiveProviderRequestError(
                "request", retryable=method.upper() in {"GET", "HEAD"}, ambiguous=method.upper() not in {"GET", "HEAD"}
            ) from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            raise LiveProviderRequestError(
                "request",
                status_code=status_code,
                retryable=method.upper() in {"GET", "HEAD"} and (status_code == 429 or status_code >= 500),
                ambiguous=False,
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise LiveProviderRequestError(
                "request", retryable=method.upper() in {"GET", "HEAD"}, ambiguous=method.upper() not in {"GET", "HEAD"}
            ) from exc
        if not isinstance(data, dict):
            raise LiveProviderRequestError("response validation")
        return data
