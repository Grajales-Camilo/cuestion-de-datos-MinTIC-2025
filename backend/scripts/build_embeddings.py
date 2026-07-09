"""CLI para generar embeddings del catalogo (T-203, RF-301/RF-304).

Uso (desde backend/, ver quickstart.md §3):
    python scripts/build_embeddings.py [--batch-size N] [--limit N] [--only-missing]
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.catalog.embeddings import build_catalog_embeddings
from app.config import get_settings
from app.db.engine import create_app_async_engine


async def _run(
    *,
    batch_size: int,
    max_retries: int,
    limit: int | None,
    only_missing: bool,
    replace_existing_model: bool,
) -> None:
    settings = get_settings()
    if settings.google_api_key is None or not settings.google_api_key.get_secret_value():
        raise RuntimeError("GOOGLE_API_KEY es obligatoria para generar embeddings con Google.")
    if settings.embedding_model is None:
        raise RuntimeError("EMBEDDING_MODEL es obligatoria desde T-203.")

    embedding_client = GoogleGenerativeAIEmbeddings(
        model=settings.embedding_model,
        google_api_key=settings.google_api_key,
    )

    engine = create_app_async_engine(settings.sqlalchemy_database_url, pool_pre_ping=True)
    try:
        summary = await build_catalog_embeddings(
            engine,
            embedding_client=embedding_client,
            model=settings.embedding_model,
            batch_size=batch_size,
            max_retries=max_retries,
            limit=limit,
            only_missing=only_missing,
            replace_existing_model=replace_existing_model,
        )
    finally:
        await engine.dispose()

    print(
        f"Embeddings upserted: {summary.embeddings_upserted} | "
        f"selected: {summary.selected_datasets} | active_datasets: {summary.active_datasets} | "
        f"model: {summary.model} | dimension: {summary.dimension}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genera embeddings del catalogo activo y los upsertea en catalog_embeddings."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Tamano de lote para la API de embeddings de Google (1-100, default: 50).",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Reintentos por lote ante errores transitorios del proveedor (default: 3).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limita la cantidad de datasets activos procesados (muestra de desarrollo).",
    )
    parser.add_argument(
        "--only-missing",
        action="store_true",
        help="Procesa solo datasets activos sin fila en catalog_embeddings.",
    )
    parser.add_argument(
        "--replace-existing-model",
        action="store_true",
        help="Si la tabla contiene otro modelo, borra catalog_embeddings antes de regenerar.",
    )
    args = parser.parse_args()

    if sys.platform == "win32":
        asyncio.run(
            _run(
                batch_size=args.batch_size,
                max_retries=args.max_retries,
                limit=args.limit,
                only_missing=args.only_missing,
                replace_existing_model=args.replace_existing_model,
            ),
            loop_factory=asyncio.SelectorEventLoop,
        )
    else:
        asyncio.run(
            _run(
                batch_size=args.batch_size,
                max_retries=args.max_retries,
                limit=args.limit,
                only_missing=args.only_missing,
                replace_existing_model=args.replace_existing_model,
            )
        )


if __name__ == "__main__":
    main()
