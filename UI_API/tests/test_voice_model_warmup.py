import ai_services


class _Response:
    def raise_for_status(self):
        return None


class _Session:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _Response()


def test_voice_model_warmup_loads_without_generation_and_keeps_model_alive(monkeypatch):
    session = _Session()
    monkeypatch.setattr(ai_services, "_get_ollama_session", lambda: session)
    monkeypatch.setattr(
        ai_services.config,
        "get",
        lambda key, default=None: {
            "OLLAMA_KEEP_ALIVE": "30m",
            "OLLAMA_TIMEOUT": 120,
        }.get(key, default),
    )

    result = ai_services.warm_ollama_model("qwen3.5:4b")

    assert result["status"] == "ready"
    assert len(session.calls) == 1
    payload = session.calls[0][1]["json"]
    assert payload == {
        "model": "qwen3.5:4b",
        "prompt": "",
        "stream": False,
        "keep_alive": "30m",
        "options": {"num_predict": 0},
    }
