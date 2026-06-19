from __future__ import annotations

import json
import os
import random
import time

from locust import HttpUser, between, events, task

DEFAULT_MODEL = "qwen3-coder-30b-a3b-instruct"

_resolved_model: str | None = (
    os.environ.get("LOCUST_MODEL", "").strip() or None
)


def _auth_headers() -> dict[str, str]:
    return {
        "X-API-Key": "09e8dc3cd20614088cde847ee2e1550ccf60b28be6b89bae3461e1a58b9946db",
        "Content-Type": "application/json",
    }


@events.test_start.add_listener
def _resolve_model(environment, **kwargs):
    global _resolved_model

    if _resolved_model:
        print(f"[locust] using model from env: {_resolved_model}")
        return

    host = environment.host or "http://127.0.0.1:8001"

    import urllib.request

    req = urllib.request.Request(
        f"{host.rstrip('/')}/v1/models",
        headers=_auth_headers(),
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode())

        models = payload.get("data", [])

        if models:
            _resolved_model = models[0]["id"]
        else:
            _resolved_model = DEFAULT_MODEL

    except Exception as exc:
        print(
            f"[locust] model discovery failed: {exc}"
        )
        _resolved_model = DEFAULT_MODEL

    print(f"[locust] using model: {_resolved_model}")


class OpenAIClient(HttpUser):

    wait_time = between(2, 6)

    def on_start(self):
        self.model = _resolved_model or DEFAULT_MODEL
        self.headers = _auth_headers()

    def _payload(self, stream: bool):

        topics = [
            "python",
            "docker",
            "linux",
            "redis",
            "postgresql",
            "networking",
            "kubernetes",
            "gpu inference",
        ]

        return {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a concise assistant."
                },
                {
                    "role": "user",
                    "content": (
                        f"Give one short fact about "
                        f"{random.choice(topics)}."
                    )
                },
            ],
            "temperature": 0.7,
            "max_tokens": 80,
            "stream": stream,
        }

    # --------------------------------------------------
    # NON STREAM
    # --------------------------------------------------

    @task(8)
    def chat_completion_non_stream(self):

        with self.client.post(
            "/v1/chat/completions",
            json=self._payload(stream=False),
            headers=self.headers,
            catch_response=True,
            timeout=180,
            name="chat_non_stream",
        ) as response:

            if response.status_code != 200:
                response.failure(
                    f"HTTP {response.status_code}"
                )
                return

            try:
                payload = response.json()

                if "choices" not in payload:
                    response.failure(
                        "missing choices"
                    )

            except Exception as exc:
                response.failure(
                    f"json parse error: {exc}"
                )

    # --------------------------------------------------
    # STREAM
    # --------------------------------------------------

    @task(4)
    def chat_completion_stream(self):

        start_time = time.time()
        first_token_received = False

        with self.client.post(
            "/v1/chat/completions",
            json=self._payload(stream=True),
            headers=self.headers,
            stream=True,
            catch_response=True,
            timeout=300,
            name="chat_stream",
        ) as response:

            if response.status_code != 200:
                response.failure(
                    f"HTTP {response.status_code}"
                )
                return

            try:

                for raw_line in response.iter_lines():

                    if not raw_line:
                        continue

                    line = raw_line.decode(
                        "utf-8",
                        errors="ignore"
                    )

                    if not line.startswith("data:"):
                        continue

                    chunk = line[5:].strip()

                    if chunk == "[DONE]":
                        break

                    if not first_token_received:
                        ttfb = (
                            time.time() - start_time
                        )

                        print(
                            f"[stream] first token "
                            f"{ttfb:.3f}s"
                        )

                        first_token_received = True

                if not first_token_received:
                    response.failure(
                        "stream ended without tokens"
                    )

            except Exception as exc:
                response.failure(
                    f"stream error: {exc}"
                )

    # --------------------------------------------------
    # MODELS
    # --------------------------------------------------

    @task(1)
    def list_models(self):

        with self.client.get(
            "/v1/models",
            headers=self.headers,
            catch_response=True,
            timeout=30,
            name="list_models",
        ) as response:

            if response.status_code != 200:
                response.failure(
                    f"HTTP {response.status_code}"
                )