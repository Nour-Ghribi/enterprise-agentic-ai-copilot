"""Provider transport: real calls unless a test explicitly injects an HTTP transport."""

import os
import time
import json
import uuid
from urllib.parse import urlparse

import httpx


class ChatProvider:
    def __init__(self):
        self.kind = os.getenv("LLM_PROVIDER", "openai")
        self.mode = os.getenv("LLM_MODE", "offline")
        self.model = (
            os.getenv("AZURE_OPENAI_DEPLOYMENT", "")
            if self.kind == "azure"
            else os.getenv("LLM_MODEL", "gpt-4o-mini")
        )
        self.key = (
            os.getenv("AZURE_OPENAI_API_KEY", "") if self.kind == "azure" else os.getenv("LLM_API_KEY", "")
        )
        self.base = (
            os.getenv("AZURE_OPENAI_ENDPOINT", "").rstrip("/") + "/openai/v1"
            if self.kind == "azure"
            else os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        )
        self.timeout = max(1, min(float(os.getenv("LLM_TIMEOUT_SECONDS", "20")), 60))
        self.max_tokens = max(256, min(int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "2500")), 8000))
        self.transport = None  # Injectable MockTransport in tests; never inferred from response content.
        self.execution_label = "real_provider"
        self.ollama_base = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        self._ollama_status = None
        if self.kind == "ollama":
            self.base = self.ollama_base + "/v1"
            self.model = os.getenv("OLLAMA_MODEL", "qwen3:1.7b")
            self.key = ""
            self.timeout = max(1, min(float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "300")), 600))
        elif self.kind == "foundry":
            self.base = os.getenv("AZURE_FOUNDRY_ENDPOINT", "").rstrip("/")
            self.model = os.getenv("AZURE_FOUNDRY_MODEL", "")
            self.key = os.getenv("AZURE_FOUNDRY_API_KEY", "")

    @property
    def is_ollama(self):
        return self.kind == "ollama" and self.mode == "ollama"

    @property
    def configured(self):
        if self.is_ollama:
            return bool(self.model and self.ollama_base)
        if self.kind == "foundry" and os.getenv("AZURE_FOUNDRY_MODE", "mock") != "real":
            return False
        return self.mode in {"openai", "azure", "foundry"} and bool(self.key and self.model and self.base)

    def ollama_status(self, refresh=False):
        """Local discovery is not an inference success or proof of tool-use quality."""
        if not self.is_ollama:
            return {"status": "not_selected", "inference_verified": False}
        if self._ollama_status and not refresh and time.monotonic() - self._ollama_status[0] < 5:
            return self._ollama_status[1]
        result = {"status": "unconfigured", "model": self.model, "inference_verified": False}
        try:
            parsed = urlparse(self.ollama_base)
            if parsed.hostname not in {"localhost", "127.0.0.1", "::1"} or parsed.username or parsed.password:
                raise ValueError("Ollama must use a local loopback server, never a cloud endpoint")
            if "cloud" in self.model.casefold() or self.model.startswith(("http:", "https:")):
                raise ValueError("Cloud-backed model tags are not permitted")
            with httpx.Client(timeout=2, transport=self.transport, trust_env=False) as client:
                tags = client.get(self.ollama_base + "/api/tags")
                tags.raise_for_status()
                names = {m.get("name", m.get("model")) for m in tags.json().get("models", [])}
                if self.model not in names and self.model + ":latest" not in names:
                    result["status"] = "model_missing"
                else:
                    response = client.post(self.ollama_base + "/api/show", json={"model": self.model})
                    response.raise_for_status()
                    capabilities = response.json().get("capabilities", [])
                    if response.json().get("remote_model") or response.json().get("remote_host"):
                        raise ValueError("Remote Ollama model is not local inference")
                    result.update(
                        status="ready" if "tools" in capabilities else "tools_not_advertised",
                        capabilities=capabilities,
                    )
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            result.update(
                status="server_unreachable" if isinstance(exc, httpx.RequestError) else "unavailable",
                error_type=type(exc).__name__,
            )
        self._ollama_status = time.monotonic(), result
        return result

    def ollama_complete(self, messages, tools=None, timeout=None, response_schema=None):
        parsed = urlparse(self.ollama_base)
        if parsed.hostname not in {"localhost", "127.0.0.1", "::1"} or parsed.username or parsed.password:
            raise ValueError("Only local Ollama is permitted")
        if "cloud" in self.model.casefold() or self.model.startswith(("http:", "https:")):
            raise ValueError("Cloud-backed Ollama tags are not permitted")
        replay, names = [], {}
        for message in messages:
            entry = {"role": message["role"], "content": message.get("content") or ""}
            if message.get("tool_calls"):
                normalized = []
                for call in message["tool_calls"]:
                    fn = call["function"]
                    names[call["id"]] = fn["name"]
                    normalized.append(
                        {
                            "type": "function",
                            "function": {
                                "name": fn["name"],
                                "arguments": json.loads(fn["arguments"])
                                if isinstance(fn["arguments"], str)
                                else fn["arguments"],
                            },
                        }
                    )
                entry["tool_calls"] = normalized
            if message["role"] == "tool":
                entry["tool_name"] = names.get(message.get("tool_call_id"), "")
            replay.append(entry)
        body = {
            "model": self.model,
            "messages": replay,
            "stream": False,
            "think": False,
            "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "5m"),
            "options": {
                "temperature": 0,
                "num_ctx": max(2048, min(int(os.getenv("OLLAMA_NUM_CTX", "8192")), 32768)),
                "num_predict": self.max_tokens,
            },
        }
        if tools:
            body["tools"] = tools
        if response_schema is not None:
            body["format"] = response_schema
        started = time.perf_counter()
        with httpx.Client(
            timeout=max(0.1, min(self.timeout, timeout) if timeout is not None else self.timeout),
            transport=self.transport,
            trust_env=False,
        ) as client:
            response = client.post(self.ollama_base + "/api/chat", json=body)
            response.raise_for_status()
            data = response.json()
        message = data["message"]
        if message.get("role") != "assistant":
            raise ValueError("Invalid Ollama assistant message")
        normalized = {"role": "assistant", "content": message.get("content") or ""}
        if message.get("tool_calls"):
            normalized["tool_calls"] = [
                {
                    "id": call.get("id") or "ollama-" + uuid.uuid4().hex,
                    "type": "function",
                    "function": {
                        "name": call["function"]["name"],
                        "arguments": json.dumps(call["function"]["arguments"])
                        if not isinstance(call["function"]["arguments"], str)
                        else call["function"]["arguments"],
                    },
                }
                for call in message["tool_calls"]
            ]
        usage = {
            "prompt_tokens": data.get("prompt_eval_count", 0),
            "completion_tokens": data.get("eval_count", 0),
        }
        usage["total_tokens"] = sum(usage.values())
        return normalized, {
            "provider": "ollama",
            "model": data.get("model", self.model),
            "requested_model": self.model,
            "execution": "simulated_provider" if self.transport is not None else "local_ollama",
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "usage": usage,
            "estimated_cost_usd": None,
            "commercial_api_used": False,
            "total_duration_ns": data.get("total_duration"),
            "done_reason": data.get("done_reason"),
            "structured_output": response_schema is not None,
        }

    def complete(self, messages, tools=None, timeout=None, response_schema=None):
        if self.is_ollama:
            return self.ollama_complete(messages, tools, timeout, response_schema)
        if not self.configured:
            raise RuntimeError("No provider credentials configured")
        parsed = urlparse(self.base)
        if parsed.scheme != "https" and parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise ValueError("Use HTTPS for a remote provider")
        body = {"model": self.model, "messages": messages, "max_completion_tokens": self.max_tokens}
        if tools:
            body.update(tools=tools, tool_choice="auto", parallel_tool_calls=True)
        start = time.perf_counter()
        deadline = min(self.timeout, timeout) if timeout is not None else self.timeout
        with httpx.Client(
            timeout=httpx.Timeout(max(0.1, deadline), connect=min(5, max(0.1, deadline))),
            transport=self.transport,
        ) as client:
            response = client.post(
                self.base + "/chat/completions", headers={"Authorization": f"Bearer {self.key}"}, json=body
            )
            response.raise_for_status()
            data = response.json()
        message = data["choices"][0]["message"]
        if message.get("role") != "assistant":
            raise ValueError("Invalid provider role")
        usage = data.get("usage") or {}
        metadata = {
            "provider": self.kind,
            "model": data.get("model", self.model),
            "requested_model": self.model,
            "response_id": data.get("id"),
            "latency_ms": round((time.perf_counter() - start) * 1000, 2),
            "usage": usage,
            "execution": "simulated_provider" if self.transport is not None else self.execution_label,
        }
        # Cost is unknown unless the operator explicitly supplies model-specific rates.
        if os.getenv("LLM_INPUT_USD_PER_MILLION") and os.getenv("LLM_OUTPUT_USD_PER_MILLION"):
            metadata["estimated_cost_usd"] = (
                usage.get("prompt_tokens", 0) * float(os.environ["LLM_INPUT_USD_PER_MILLION"])
                + usage.get("completion_tokens", 0) * float(os.environ["LLM_OUTPUT_USD_PER_MILLION"])
            ) / 1e6
        else:
            metadata["estimated_cost_usd"] = None
        return message, metadata
