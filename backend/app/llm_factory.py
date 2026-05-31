"""
llm_factory.py — Free LLM provider factory.

Priority:
  1. Groq  (llama-3.3-70b-versatile  — free tier, fast)
  2. Google Gemini  (gemini-1.5-flash — free tier)
  3. Offline template fallback (no API key needed)

Set ONE of these in your .env:
  GROQ_API_KEY=gsk_...
  GOOGLE_API_KEY=AIza...
"""
import os
import logging

logger = logging.getLogger(__name__)


def get_llm(temperature: float = 0.3):
    """
    Return the best available free LLM.

    Tries Groq first, then Gemini, then returns None (offline mode).
    """
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    google_key = os.getenv("GOOGLE_API_KEY", "").strip()

    if groq_key:
        try:
            from langchain_groq import ChatGroq
            llm = ChatGroq(
                model="llama-3.3-70b-versatile",
                api_key=groq_key,
                temperature=temperature,
                max_tokens=1024,
            )
            logger.info("[LLM] Using Groq — llama-3.3-70b-versatile (free tier)")
            return llm
        except ImportError:
            logger.warning("[LLM] langchain-groq not installed.")
        except Exception as e:
            logger.warning(f"[LLM] Groq init failed: {e}")

    if google_key:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            llm = ChatGoogleGenerativeAI(
                model="gemini-1.5-flash",
                google_api_key=google_key,
                temperature=temperature,
                max_output_tokens=1024,
            )
            logger.info("[LLM] Using Google Gemini — gemini-1.5-flash (free tier)")
            return llm
        except ImportError:
            logger.warning("[LLM] langchain-google-genai not installed.")
        except Exception as e:
            logger.warning(f"[LLM] Gemini init failed: {e}")

    logger.warning("[LLM] No API key found — running in OFFLINE/template mode.")
    return None


def llm_invoke(prompt: str, temperature: float = 0.3) -> str:
    """
    Invoke the best available LLM with a prompt string.
    Returns the response text, or None if no LLM is available.
    """
    llm = get_llm(temperature)
    if llm is None:
        return None
    try:
        response = llm.invoke(prompt)
        return response.content if hasattr(response, "content") else str(response)
    except Exception as e:
        logger.error(f"[LLM] invoke failed: {e}")
        return None
