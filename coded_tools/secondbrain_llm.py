from __future__ import annotations

import os

from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI


def _required(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    raise RuntimeError(f"Missing LLM credential. Expected one of: {', '.join(names)}")


class GroqKey1(ChatGroq):
    def __init__(self, **kwargs):
        kwargs["api_key"] = _required("GROQ_API_KEY_1", "GROQ_API_KEY")
        super().__init__(**kwargs)


class GroqKey2(ChatGroq):
    def __init__(self, **kwargs):
        kwargs["api_key"] = _required("GROQ_API_KEY_2")
        super().__init__(**kwargs)



class OpenAIFallback(ChatOpenAI):
    def __init__(self, **kwargs):
        kwargs["api_key"] = _required("OPENAI_API_KEY")
        super().__init__(**kwargs)


class GeminiFallback(ChatGoogleGenerativeAI):
    def __init__(self, **kwargs):
        key = _required("GEMINI_API_KEY", "GOOGLE_API_KEY")
        if "max_tokens" in kwargs:
            kwargs["max_output_tokens"] = kwargs.pop("max_tokens")
        kwargs["google_api_key"] = key
        super().__init__(**kwargs)