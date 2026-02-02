from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import OpenAI

from .paths import papers_root, db_path
from .storage import record_paper


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _openai_client_from_config(config: dict[str, Any]) -> OpenAI | None:
    providers = config.get("providers", {})
    default_openai = providers.get("default", {}).get("openai", {})
    api_key = default_openai.get("api_key") or None
    base_url = default_openai.get("base_url") or None
    organization = default_openai.get("organization") or None
    project = default_openai.get("project") or None
    if not api_key and not base_url and not organization and not project:
        # Allow default OpenAI client behavior (environment variables).
        if os.getenv("OPENAI_API_KEY"):
            return OpenAI()
        return None
    return OpenAI(
        api_key=api_key,
        base_url=base_url,
        organization=organization,
        project=project,
    )


def _attach_to_vector_store(
    client: OpenAI, vector_store_id: str, file_id: str
) -> str | None:
    vs_files = client.vector_stores.files
    if hasattr(vs_files, "create_and_poll"):
        result = vs_files.create_and_poll(vector_store_id=vector_store_id, file_id=file_id)
    else:
        result = vs_files.create(vector_store_id=vector_store_id, file_id=file_id)
    return getattr(result, "id", None)


def ingest_docs(
    run_id: str,
    doc_paths: list[str],
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    papers_root().mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    vector_store_id = ""
    client: OpenAI | None = None
    if config:
        vector_store_id = config.get("vector_store_id") or ""
        if vector_store_id:
            client = _openai_client_from_config(config)
            if client is None:
                raise ValueError(
                    "vector_store_id is set but OpenAI credentials are missing. "
                    "Set OPENAI_API_KEY or configure providers.default.openai.api_key."
                )
    for doc_path in doc_paths:
        src = Path(doc_path).expanduser().resolve()
        if not src.exists():
            raise FileNotFoundError(f"Doc not found: {src}")
        data = src.read_bytes()
        sha = _sha256_bytes(data)
        stored_name = f"{sha[:8]}_{src.name}"
        dest = papers_root() / stored_name
        dest.write_bytes(data)
        paper_id = sha[:16]
        added_at = _now_iso()
        openai_file_id = None
        vector_store_file_id = None
        if client and vector_store_id:
            with src.open("rb") as file_obj:
                file_result = client.files.create(file=file_obj, purpose="assistants")
            openai_file_id = getattr(file_result, "id", None)
            if openai_file_id:
                vector_store_file_id = _attach_to_vector_store(
                    client, vector_store_id, openai_file_id
                )
        record_paper(
            db_path=db_path(),
            paper_id=paper_id,
            run_id=run_id,
            source_path=str(src),
            stored_path=str(dest),
            sha256=sha,
            added_at=added_at,
            openai_file_id=openai_file_id,
            vector_store_id=vector_store_id or None,
            vector_store_file_id=vector_store_file_id,
        )
        results.append(
            {
                "id": paper_id,
                "source_path": str(src),
                "stored_path": str(dest),
                "sha256": sha,
                "added_at": added_at,
                "openai_file_id": openai_file_id,
                "vector_store_id": vector_store_id or None,
                "vector_store_file_id": vector_store_file_id,
            }
        )
    return results
