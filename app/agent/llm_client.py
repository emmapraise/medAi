import os
from typing import Optional, Tuple
from langchain_openai import ChatOpenAI
from app.config import settings
from langfuse import observe, get_client

class AgentLLMClient:
    def __init__(self):
        self.llm: Optional[ChatOpenAI] = None
        self.fallback_llm: Optional[ChatOpenAI] = None

    def initialize(self):
        gemini_key = settings.GEMINI_API_KEY
        openai_key = settings.OPENAI_API_KEY

        if not gemini_key and not openai_key:
            raise RuntimeError("Neither GEMINI_API_KEY nor OPENAI_API_KEY is configured.")

        if openai_key:
            os.environ["OPENAI_API_KEY"] = openai_key

        if gemini_key:
            self.llm = ChatOpenAI(
                api_key=gemini_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                model=settings.DEFAULT_MODEL
            )
            print(f"[MedicalAgent] Primary LLM: Gemini ({settings.DEFAULT_MODEL}).")
        
        if openai_key:
            self.fallback_llm = ChatOpenAI(
                api_key=openai_key,
                model="gpt-4o-mini"
            )
            print("[MedicalAgent] Fallback LLM: OpenAI (gpt-4o-mini).")
            if not self.llm:
                self.llm = self.fallback_llm

    @observe(as_type="generation", name="llm-generation")
    def invoke(self, prompt: str, max_tokens: Optional[int] = None, temperature: float = 0.7) -> Tuple[str, str, int, int]:
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
                pass

            return content, model_used, p_tokens, c_tokens
        except Exception as e:
            if self.fallback_llm and self.llm != self.fallback_llm:
                print(f"[MedicalAgent] Primary LLM error ({e}). Falling back to OpenAI (gpt-4o-mini)...")
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
                        pass

                    return content, model_used, p_tokens, c_tokens
                except Exception as fe:
                    print(f"[MedicalAgent Error] Fallback LLM also failed: {fe}")
            raise e

llm_client = AgentLLMClient()
