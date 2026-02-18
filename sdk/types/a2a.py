from __future__ import annotations

from typing import Any, Literal, TypedDict


class A2ATextPart(TypedDict):
    kind: Literal["text"]
    text: str


class A2ADataPart(TypedDict):
    kind: Literal["data"]
    data: dict[str, Any]


class A2AArtifact(TypedDict, total=False):
    artifactId: str
    name: str
    parts: list[A2ATextPart | A2ADataPart]
    metadata: dict[str, Any]


class A2ATaskStatus(TypedDict, total=False):
    state: str
    timestamp: str
    message: dict[str, Any]


class A2ATaskResponse(TypedDict, total=False):
    id: str
    contextId: str
    status: A2ATaskStatus
    artifacts: list[A2AArtifact]
    history: list[dict[str, Any]]
    metadata: dict[str, Any]
    kind: Literal["task"]


class A2AJsonRpcError(TypedDict, total=False):
    code: int
    message: str
    data: dict[str, Any]


class A2AJsonRpcResponse(TypedDict, total=False):
    jsonrpc: str
    id: str | int
    result: A2ATaskResponse
    error: A2AJsonRpcError


class A2AAgentSkill(TypedDict, total=False):
    id: str
    name: str
    description: str
    tags: list[str]
    examples: list[str]
    inputModes: list[str]
    outputModes: list[str]


class A2AAgentCapabilities(TypedDict, total=False):
    streaming: bool
    pushNotifications: bool
    stateTransitionHistory: bool


class A2AAgentProvider(TypedDict, total=False):
    organization: str
    url: str


class A2AAgentAuthentication(TypedDict, total=False):
    schemes: list[str]
    credentials: str


class A2AAgentCardResponse(TypedDict, total=False):
    name: str
    description: str
    url: str
    provider: A2AAgentProvider
    version: str
    capabilities: A2AAgentCapabilities
    authentication: A2AAgentAuthentication
    defaultInputModes: list[str]
    defaultOutputModes: list[str]
    skills: list[A2AAgentSkill]
