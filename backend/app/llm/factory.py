"""Capa multi-proveedor LLM (T-301, RF-206, RNF-009, RF-601).

Expone `get_chat_model`/`get_chat_model_from_settings` para instanciar el
chat model segun `LLM_PROVIDER`/`LLM_MODEL`, `get_structured_chat_model` como
envoltura uniforme sobre `with_structured_output` (el enrutador del grafo,
T-303, no necesita ramas por proveedor), y utilidades para normalizar
tokens/costo hacia las columnas de `agent_runs` (data-model.md):
`llm_provider`, `llm_model`, `input_tokens`, `output_tokens`,
`estimated_cost_usd`.

Decision de diseno (unificacion de tokens): `langchain-google-genai` y
`langchain-anthropic` exponen el uso crudo en formatos distintos
(`usage_metadata.prompt_token_count`/`candidates_token_count` en la API de
Google vs `usage.input_tokens`/`output_tokens` en la API de Anthropic), pero
ambos SDKs pueblan `AIMessage.usage_metadata` con el mismo esquema
normalizado de LangChain (`langchain_core.messages.ai.UsageMetadata`:
`input_tokens`/`output_tokens`/`total_tokens`; verificado leyendo
`chat_models.py` de cada paquete, no asumido). Por eso este modulo lee
siempre `AIMessage.usage_metadata` -- nunca `response_metadata` crudo -- y no
necesita ramas por proveedor para contar tokens.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable

from app.config import Settings


class LLMConfigurationError(Exception):
    """Proveedor LLM desconocido o sin API key configurada (falla temprana, RF-206)."""


class LLMProviderError(Exception):
    """Error definitivo del proveedor LLM al invocar el modelo.

    El grafo del agente (T-303/T-304) traduce esta excepcion a
    `LLM_PROVIDER_ERROR` (contracts/api-rest.md §6).
    """


class LLMPricingError(LookupError):
    """No hay tarifa configurada para el modelo indicado.

    Agregar una entrada a `_PRICING_USD_PER_MILLION_TOKENS` en este modulo
    (T-602 la necesita para comparar costos entre configuraciones).
    """


# Precios en USD por 1.000.000 de tokens (tarifa API estandar: sin cache,
# sin Batch API, tramo <=200k tokens de contexto). Vigentes al 2026-07-09,
# segun https://ai.google.dev/gemini-api/docs/pricing y
# https://platform.claude.com/docs/en/about-claude/pricing. Los precios
# cambian: revisar esta fecha antes de confiar en RNF-009. Extender esta
# tabla (T-602) no requiere tocar el resto del modulo.
_PRICING_USD_PER_MILLION_TOKENS: dict[str, tuple[float, float]] = {
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-pro": (1.25, 10.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-opus-4-8": (5.00, 25.00),
}


@dataclass(frozen=True)
class LLMUsage:
    """Uso normalizado, compatible con las columnas de `agent_runs` (data-model.md)."""

    llm_provider: str
    llm_model: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float


def get_chat_model(
    llm_provider: str,
    llm_model: str,
    *,
    google_api_key: str | None = None,
    anthropic_api_key: str | None = None,
    **kwargs: Any,
) -> BaseChatModel:
    """Instancia el chat model segun `llm_provider`/`llm_model` (RF-206).

    Falla temprano -- antes de cualquier llamada de red -- si el proveedor es
    desconocido o si falta la API key correspondiente; nunca deja el fallo
    para el primer uso del modelo.
    """
    if llm_provider == "google":
        if not google_api_key:
            raise LLMConfigurationError(
                "LLM_PROVIDER=google requiere GOOGLE_API_KEY configurada"
            )
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=llm_model, google_api_key=google_api_key, **kwargs)
    if llm_provider == "anthropic":
        if not anthropic_api_key:
            raise LLMConfigurationError(
                "LLM_PROVIDER=anthropic requiere ANTHROPIC_API_KEY configurada"
            )
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=llm_model, api_key=anthropic_api_key, **kwargs)
    raise LLMConfigurationError(f"LLM_PROVIDER desconocido: {llm_provider!r}")


def get_chat_model_from_settings(settings: Settings, **kwargs: Any) -> BaseChatModel:
    """Conveniencia sobre `get_chat_model` que lee `Settings` (config.py, T-102)."""

    return get_chat_model(
        settings.llm_provider,
        settings.llm_model,
        google_api_key=(
            settings.google_api_key.get_secret_value() if settings.google_api_key else None
        ),
        anthropic_api_key=(
            settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
        ),
        **kwargs,
    )


def get_structured_chat_model(
    llm_provider: str,
    llm_model: str,
    schema: Any,
    *,
    google_api_key: str | None = None,
    anthropic_api_key: str | None = None,
    **kwargs: Any,
) -> Runnable:
    """Envoltura uniforme sobre `with_structured_output` (RF-206).

    `with_structured_output` es un metodo estandar de `BaseChatModel`
    implementado por ambos proveedores; el codigo que consume esta funcion
    (el enrutador del grafo, T-303) no necesita ramas especificas de
    proveedor para obtener decisiones estructuradas.
    """
    model = get_chat_model(
        llm_provider,
        llm_model,
        google_api_key=google_api_key,
        anthropic_api_key=anthropic_api_key,
        **kwargs,
    )
    return model.with_structured_output(schema)


def usage_from_message(provider: str, model: str, message: AIMessage) -> LLMUsage:
    """Normaliza `AIMessage.usage_metadata` a `LLMUsage` (tokens + costo)."""

    usage_metadata = message.usage_metadata
    if usage_metadata is None:
        raise LLMProviderError(f"La respuesta de {provider}/{model} no incluyo usage_metadata")
    input_tokens = usage_metadata.get("input_tokens", 0)
    output_tokens = usage_metadata.get("output_tokens", 0)
    return LLMUsage(
        llm_provider=provider,
        llm_model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=estimate_cost_usd(model, input_tokens, output_tokens),
    )


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calcula el costo estimado segun `_PRICING_USD_PER_MILLION_TOKENS`."""

    try:
        input_price, output_price = _PRICING_USD_PER_MILLION_TOKENS[model]
    except KeyError as exc:
        raise LLMPricingError(
            f"Sin tarifa configurada para el modelo {model!r}; agregala a "
            "_PRICING_USD_PER_MILLION_TOKENS en app/llm/factory.py"
        ) from exc
    cost = (input_tokens * input_price + output_tokens * output_price) / 1_000_000
    return round(cost, 6)


def sum_usage(usages: Iterable[LLMUsage]) -> LLMUsage:
    """Agrega tokens y costo de varios pasos de una misma corrida (pruebas.md §2.1).

    `agent_runs` guarda un unico `llm_provider`/`llm_model` por corrida
    (data-model.md); mezclar proveedores o modelos distintos es un error del
    llamador, no un caso a tolerar silenciosamente.
    """
    usage_list = list(usages)
    if not usage_list:
        raise ValueError("sum_usage requiere al menos un LLMUsage")
    provider = usage_list[0].llm_provider
    model = usage_list[0].llm_model
    if any(u.llm_provider != provider or u.llm_model != model for u in usage_list):
        raise ValueError("sum_usage no admite mezclar llm_provider/llm_model distintos")
    return LLMUsage(
        llm_provider=provider,
        llm_model=model,
        input_tokens=sum(u.input_tokens for u in usage_list),
        output_tokens=sum(u.output_tokens for u in usage_list),
        estimated_cost_usd=round(sum(u.estimated_cost_usd for u in usage_list), 6),
    )


_PROVIDER_ERROR_TYPES: tuple[type[Exception], ...] | None = None


def _provider_error_types() -> tuple[type[Exception], ...]:
    global _PROVIDER_ERROR_TYPES
    if _PROVIDER_ERROR_TYPES is None:
        from anthropic import APIError
        from google.api_core.exceptions import GoogleAPICallError

        _PROVIDER_ERROR_TYPES = (GoogleAPICallError, APIError)
    return _PROVIDER_ERROR_TYPES


async def ainvoke_chat_model(model: BaseChatModel, input: Any, **kwargs: Any) -> AIMessage:
    """Invoca el modelo traduciendo errores definitivos del proveedor.

    Cuota agotada, autenticacion invalida o modelo inexistente llegan aqui
    como excepciones especificas del SDK subyacente (`google.api_core` o
    `anthropic`); se relanzan como `LLMProviderError` para que el grafo
    (T-303/T-304) las mapee de forma uniforme a `LLM_PROVIDER_ERROR`. La
    politica de reintento ante fallos transitorios de red es responsabilidad
    del grafo, no de esta capa.
    """
    try:
        result = await model.ainvoke(input, **kwargs)
    except _provider_error_types() as exc:
        raise LLMProviderError(f"Error definitivo del proveedor LLM: {exc}") from exc
    return result
