from typing import Any

import httpx
import pytest
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel

from app.config import Settings
from app.llm.factory import (
    LLMConfigurationError,
    LLMPricingError,
    LLMProviderError,
    LLMUsage,
    ainvoke_structured_chat_model,
    estimate_cost_usd,
    get_chat_model,
    get_chat_model_from_settings,
    get_structured_chat_model,
    sum_usage,
    usage_from_message,
)


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "DATABASE_URL": "postgresql://usuario:clave@localhost:5432/cuestion_de_datos",
        "SOCRATA_APP_TOKEN": "token-local",
        "RETENTION_HASH_SALT": "replace-with-local-development-salt-32-bytes",
    }
    values.update(overrides)
    return Settings(**values)


class DecisionEsquema(BaseModel):
    herramienta: str
    argumentos: dict[str, Any]


# --- Instanciacion por proveedor (RF-206) -----------------------------------


def test_get_chat_model_google_instancia_chat_google_generative_ai() -> None:
    model = get_chat_model("google", "gemini-2.5-flash", google_api_key="fake-google-key")

    assert isinstance(model, ChatGoogleGenerativeAI)
    assert model.model.endswith("gemini-2.5-flash")


def test_get_chat_model_anthropic_instancia_chat_anthropic() -> None:
    model = get_chat_model("anthropic", "claude-sonnet-5", anthropic_api_key="fake-anthropic-key")

    assert isinstance(model, ChatAnthropic)
    assert model.model == "claude-sonnet-5"


def test_get_chat_model_proveedor_desconocido_falla_claro() -> None:
    with pytest.raises(LLMConfigurationError, match="desconocido"):
        get_chat_model("openai", "gpt-4o", google_api_key="irrelevante")


@pytest.mark.parametrize(
    "llm_provider,kwargs",
    [
        ("google", {}),
        ("google", {"google_api_key": ""}),
        ("anthropic", {}),
        ("anthropic", {"anthropic_api_key": ""}),
    ],
)
def test_get_chat_model_sin_api_key_falla_temprano(
    llm_provider: str, kwargs: dict[str, str]
) -> None:
    with pytest.raises(LLMConfigurationError, match="API_KEY"):
        get_chat_model(llm_provider, "modelo-cualquiera", **kwargs)


def test_get_chat_model_from_settings_usa_config_google() -> None:
    loaded = settings(
        LLM_PROVIDER="google", LLM_MODEL="gemini-2.5-flash", GOOGLE_API_KEY="fake-google-key"
    )

    model = get_chat_model_from_settings(loaded)

    assert isinstance(model, ChatGoogleGenerativeAI)


def test_get_chat_model_from_settings_sin_key_falla_claro() -> None:
    loaded = settings(LLM_PROVIDER="anthropic", LLM_MODEL="claude-sonnet-5")

    with pytest.raises(LLMConfigurationError):
        get_chat_model_from_settings(loaded)


# --- Structured output uniforme (sin ramas por proveedor) -------------------


@pytest.mark.parametrize(
    "llm_provider,llm_model,key_kwargs",
    [
        ("google", "gemini-2.5-flash", {"google_api_key": "fake-google-key"}),
        ("anthropic", "claude-sonnet-5", {"anthropic_api_key": "fake-anthropic-key"}),
    ],
)
def test_get_structured_chat_model_es_uniforme_entre_proveedores(
    llm_provider: str, llm_model: str, key_kwargs: dict[str, str]
) -> None:
    structured = get_structured_chat_model(llm_provider, llm_model, DecisionEsquema, **key_kwargs)

    assert hasattr(structured, "invoke")


class TimeoutRunnable:
    async def ainvoke(self, _input, **_kwargs):
        raise httpx.ReadTimeout("proveedor sin respuesta")


@pytest.mark.asyncio
async def test_structured_model_timeout_maps_to_llm_provider_error() -> None:
    with pytest.raises(LLMProviderError, match="Timeout"):
        await ainvoke_structured_chat_model(TimeoutRunnable(), [])


# --- Conteo de tokens y costo unificado (RNF-009) ---------------------------


def test_usage_from_message_normaliza_tokens_y_calcula_costo() -> None:
    mensaje = AIMessage(
        content="respuesta",
        usage_metadata={"input_tokens": 1000, "output_tokens": 500, "total_tokens": 1500},
    )

    usage = usage_from_message("google", "gemini-2.5-flash", mensaje)

    assert usage == LLMUsage(
        llm_provider="google",
        llm_model="gemini-2.5-flash",
        input_tokens=1000,
        output_tokens=500,
        estimated_cost_usd=round(1000 * 0.30 / 1_000_000 + 500 * 2.50 / 1_000_000, 6),
    )


def test_usage_from_message_sin_usage_metadata_lanza_llm_provider_error() -> None:
    mensaje = AIMessage(content="respuesta")

    with pytest.raises(LLMProviderError):
        usage_from_message("anthropic", "claude-sonnet-5", mensaje)


def test_estimate_cost_usd_modelo_sin_tarifa_lanza_llm_pricing_error() -> None:
    with pytest.raises(LLMPricingError):
        estimate_cost_usd("modelo-no-catalogado", input_tokens=100, output_tokens=100)


def test_sum_usage_agrega_tokens_y_costo_de_varios_pasos() -> None:
    paso_1 = LLMUsage("anthropic", "claude-sonnet-5", 100, 20, 0.0006)
    paso_2 = LLMUsage("anthropic", "claude-sonnet-5", 200, 30, 0.0011)

    total = sum_usage([paso_1, paso_2])

    assert total.input_tokens == 300
    assert total.output_tokens == 50
    assert total.estimated_cost_usd == round(0.0006 + 0.0011, 6)


def test_sum_usage_no_admite_mezclar_proveedores() -> None:
    paso_google = LLMUsage("google", "gemini-2.5-flash", 100, 20, 0.001)
    paso_anthropic = LLMUsage("anthropic", "claude-sonnet-5", 100, 20, 0.001)

    with pytest.raises(ValueError):
        sum_usage([paso_google, paso_anthropic])


def test_sum_usage_lista_vacia_lanza_value_error() -> None:
    with pytest.raises(ValueError):
        sum_usage([])
