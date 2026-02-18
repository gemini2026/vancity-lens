from __future__ import annotations

import uuid
from typing import Any, cast

from sdk.resources._mixin_base import RequesterMixin
from sdk.types import (
    A2AAgentCardResponse,
    A2AJsonRpcResponse,
)


class A2AMixin(RequesterMixin):
    """SDK mixin for the K2 A2A (Agent-to-Agent) protocol adapter."""

    def a2a_get_agent_card(self, corpus_id: str) -> A2AAgentCardResponse:
        """Fetch the A2A Agent Card for a corpus."""
        data = self._request("GET", f"/a2a/v1/agents/{corpus_id}/.well-known/agent.json")
        return cast("A2AAgentCardResponse", data)

    def a2a_send_message(
        self,
        corpus_id: str,
        *,
        operation: str,
        text: str | None = None,
        data: dict[str, Any] | None = None,
        message_id: str | None = None,
        context_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        configuration: dict[str, Any] | None = None,
    ) -> A2AJsonRpcResponse:
        """Send an A2A message/send request to a corpus agent.

        Args:
            corpus_id: Target corpus ID.
            operation: K2 operation (retrieve, answer, ingest.urls, ingest.text_batch).
            text: Query text (required for retrieve/answer).
            data: Structured data (search config, URLs, documents, etc.).
            message_id: Optional message ID (auto-generated if omitted).
            context_id: Optional context/session ID.
            metadata: Additional metadata merged with operation.
            configuration: Optional A2A configuration passed through to the agent.
        """
        parts: list[dict[str, Any]] = []
        if text is not None:
            parts.append({"kind": "text", "text": text})
        if data is not None:
            parts.append({"kind": "data", "data": data})

        msg_meta: dict[str, Any] = dict(metadata or {})
        # Keep operation authoritative even if metadata contains an `operation` key.
        msg_meta["operation"] = operation

        message: dict[str, Any] = {
            "messageId": message_id or str(uuid.uuid4()),
            "role": "user",
            "parts": parts,
            "metadata": msg_meta,
        }
        if context_id is not None:
            message["contextId"] = context_id

        params: dict[str, Any] = {"message": message}
        if configuration is not None:
            params["configuration"] = configuration

        body = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "message/send",
            "params": params,
        }
        resp = self._request("POST", f"/a2a/v1/agents/{corpus_id}", json=body)
        return cast("A2AJsonRpcResponse", resp)

    def a2a_retrieve(
        self,
        corpus_id: str,
        query: str,
        *,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        hybrid: dict[str, Any] | None = None,
        rerank: dict[str, Any] | None = None,
        return_config: dict[str, Any] | None = None,
    ) -> A2AJsonRpcResponse:
        """Convenience wrapper for the A2A 'retrieve' operation."""
        data: dict[str, Any] = {"top_k": top_k}
        if filters is not None:
            data["filters"] = filters
        if hybrid is not None:
            data["hybrid"] = hybrid
        if rerank is not None:
            data["rerank"] = rerank
        if return_config is not None:
            data["return"] = return_config
        return self.a2a_send_message(corpus_id, operation="retrieve", text=query, data=data)

    def a2a_answer(
        self,
        corpus_id: str,
        query: str,
        *,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        hybrid: dict[str, Any] | None = None,
        rerank: dict[str, Any] | None = None,
        generation: dict[str, Any] | None = None,
    ) -> A2AJsonRpcResponse:
        """Convenience wrapper for the A2A 'answer' operation."""
        data: dict[str, Any] = {"top_k": top_k}
        if filters is not None:
            data["filters"] = filters
        if hybrid is not None:
            data["hybrid"] = hybrid
        if rerank is not None:
            data["rerank"] = rerank
        if generation is not None:
            data["generation"] = generation
        return self.a2a_send_message(corpus_id, operation="answer", text=query, data=data)

    def a2a_ingest_urls(
        self,
        corpus_id: str,
        urls: list[str | dict[str, Any]],
        *,
        auto_index: bool | None = None,
        message_id: str | None = None,
    ) -> A2AJsonRpcResponse:
        """Convenience wrapper for the A2A 'ingest.urls' operation."""
        data: dict[str, Any] = {"urls": urls}
        if auto_index is not None:
            data["auto_index"] = auto_index
        return self.a2a_send_message(
            corpus_id,
            operation="ingest.urls",
            data=data,
            message_id=message_id,
        )

    def a2a_ingest_text_batch(
        self,
        corpus_id: str,
        documents: list[dict[str, Any]],
        *,
        auto_index: bool | None = None,
        message_id: str | None = None,
    ) -> A2AJsonRpcResponse:
        """Convenience wrapper for the A2A 'ingest.text_batch' operation."""
        data: dict[str, Any] = {"documents": documents}
        if auto_index is not None:
            data["auto_index"] = auto_index
        return self.a2a_send_message(
            corpus_id,
            operation="ingest.text_batch",
            data=data,
            message_id=message_id,
        )

    def a2a_get_task(self, corpus_id: str, task_id: str) -> A2AJsonRpcResponse:
        """Get the status of an async A2A task (maps to tasks/get)."""
        body = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tasks/get",
            "params": {"id": task_id},
        }
        resp = self._request("POST", f"/a2a/v1/agents/{corpus_id}", json=body)
        return cast("A2AJsonRpcResponse", resp)

    def a2a_cancel_task(self, corpus_id: str, task_id: str) -> A2AJsonRpcResponse:
        """Cancel an async A2A task (maps to tasks/cancel)."""
        body = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tasks/cancel",
            "params": {"id": task_id},
        }
        resp = self._request("POST", f"/a2a/v1/agents/{corpus_id}", json=body)
        return cast("A2AJsonRpcResponse", resp)
