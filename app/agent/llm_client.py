import logging
import os

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langfuse import get_client, observe

from app.config import settings

logger = logging.getLogger(__name__)

class AgentLLMClient:
    def __init__(self):
        self.llm = None
        self.fallback_llm = None

    def initialize(self):
        gemini_key = settings.GEMINI_API_KEY
        openai_key = settings.OPENAI_API_KEY

        if not gemini_key and not openai_key:
            raise RuntimeError("Neither GEMINI_API_KEY nor OPENAI_API_KEY is configured.")

        if openai_key:
            os.environ["OPENAI_API_KEY"] = openai_key
            self.fallback_llm = ChatOpenAI(
                api_key=openai_key,
                model="gpt-4o-mini"
            )
            logger.warning("[MedicalAgent] Fallback LLM: OpenAI (gpt-4o-mini).")

        if gemini_key:
            try:
                self.llm = ChatGoogleGenerativeAI(
                    google_api_key=gemini_key,
                    model=settings.DEFAULT_MODEL
                )
                logger.info(f"[MedicalAgent] Primary LLM: Gemini ({settings.DEFAULT_MODEL}).")
            except Exception as ge:
                logger.warning(f"[MedicalAgent Warning] Gemini init error: {ge}")

        if not self.llm and self.fallback_llm:
            self.llm = self.fallback_llm

    @observe(as_type="generation", name="llm-generation")
    def invoke(self, prompt: str, max_tokens: int | None = None, temperature: float = 0.7) -> tuple[str, str, int, int]:
        model_used = settings.DEFAULT_MODEL
        try:
            kwargs = {}
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens
            if temperature is not None:
                kwargs["temperature"] = temperature

            res = self.llm.invoke(prompt, **kwargs)
            content = str(res.content).strip()
            
            p_tokens = len(prompt) // 4
            c_tokens = len(content) // 4
            if hasattr(res, "response_metadata") and isinstance(res.response_metadata, dict):
                token_usage = res.response_metadata.get("token_usage") or res.response_metadata.get("usage", {})
                if token_usage:
                    p_tokens = token_usage.get("prompt_tokens", p_tokens)
                    c_tokens = token_usage.get("completion_tokens", c_tokens)

            try:
                lf = get_client()
                lf.update_current_generation(
                    model=model_used,
                    model_parameters={"temperature": temperature, "max_tokens": max_tokens},
                    usage_details={"input": p_tokens, "output": c_tokens, "total": p_tokens + c_tokens}
                )
            except Exception:
                logger.debug("Langfuse generation update failed", exc_info=True)

            return content, model_used, p_tokens, c_tokens
        except Exception as e:
            if self.fallback_llm and self.llm != self.fallback_llm:
                logger.warning(f"[MedicalAgent] Primary LLM error ({e}). Falling back to OpenAI (gpt-4o-mini)...")
                try:
                    model_used = "gpt-4o-mini"
                    res = self.fallback_llm.invoke(prompt, **kwargs)
                    content = str(res.content).strip()
                    p_tokens = len(prompt) // 4
                    c_tokens = len(content) // 4
                    if hasattr(res, "response_metadata") and isinstance(res.response_metadata, dict):
                        token_usage = res.response_metadata.get("token_usage") or res.response_metadata.get("usage", {})
                        if token_usage:
                            p_tokens = token_usage.get("prompt_tokens", p_tokens)
                            c_tokens = token_usage.get("completion_tokens", c_tokens)

                    try:
                        lf = get_client()
                        lf.update_current_generation(
                            model=model_used,
                            model_parameters={"temperature": temperature, "max_tokens": max_tokens},
                            usage_details={"input": p_tokens, "output": c_tokens, "total": p_tokens + c_tokens}
                        )
                    except Exception:
                        logger.debug("Langfuse generation update failed", exc_info=True)

                    return content, model_used, p_tokens, c_tokens
                except Exception as fe:
                    logger.warning(f"[MedicalAgent Error] Fallback LLM also failed: {fe}")
            raise e

llm_client = AgentLLMClient()
