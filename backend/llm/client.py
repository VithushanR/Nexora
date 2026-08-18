"""
Gemini LLM client wrapper.

Responsibility:
- Instantiate a langchain-google-genai ChatGoogleGenerativeAI client using
  GEMINI_API_KEY from config.
- Provide a structured-output helper (pydantic schema -> parsed response)
  used by all four agents.
"""

from functools import lru_cache

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel

from config import get_settings


@lru_cache
def get_llm_client() -> ChatGoogleGenerativeAI:
    # TODO: pull model name + generation params from settings
    settings = get_settings()
    raise NotImplementedError


async def structured_completion(prompt: str, schema: type[BaseModel]) -> BaseModel:
    # TODO: call the LLM with structured output / function-calling bound to `schema`
    raise NotImplementedError
