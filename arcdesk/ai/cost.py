"""Cost guard — makes "no payment, no subscription" a rule the code enforces.

Three classes, checked before any request leaves the machine:

    local   runs on this PC. no account, no key, no limit, no cost. forever.
    free    a cloud free tier (Groq, Gemini). no money, but needs a key and has
            rate limits. Allowed by default because it costs ₹0.
    paid    bills per token (OpenAI, or any custom endpoint that is not localhost).
            BLOCKED by default. It takes a deliberate settings change to allow it.

The guard runs in `LLMClient.from_config` and in the agent before a request, so a
stale settings.json, a copied config or an AI tool cannot quietly spend your money.
"""
from __future__ import annotations

LOCAL_PROVIDERS = {
    "lite", "ollama", "llamacpp", "localai", "vllm", "jan",
    "gpt4all", "koboldcpp", "textgen", "lmstudio",
    "sglang", "aphrodite", "llamafile",
}
FREE_TIER_PROVIDERS = {"groq", "gemini"}

CLASS_LOCAL, CLASS_FREE, CLASS_PAID = "local", "free", "paid"
ORDER = {CLASS_LOCAL: 0, CLASS_FREE: 1, CLASS_PAID: 2}

MAX_DEFAULT = CLASS_FREE          # free tiers fine, paid blocked

LABELS = {
    CLASS_LOCAL: "FREE · LOCAL",
    CLASS_FREE: "FREE TIER · CLOUD",
    CLASS_PAID: "PAID · BLOCKED",
}


def _is_localhost(url: str) -> bool:
    u = (url or "").lower()
    return ("127.0.0.1" in u or "localhost" in u or "0.0.0.0" in u
            or "[::1]" in u or u.startswith("http://host.docker.internal"))


def classify(provider: str, base_url: str = "") -> str:
    """Which cost class does this brain belong to?"""
    p = (provider or "").strip().lower()
    if p in LOCAL_PROVIDERS:
        return CLASS_LOCAL
    if p in FREE_TIER_PROVIDERS:
        return CLASS_FREE
    if p == "custom":
        # a custom endpoint pointed at localhost is still local and still free
        return CLASS_LOCAL if _is_localhost(base_url) else CLASS_PAID
    if _is_localhost(base_url):
        return CLASS_LOCAL
    return CLASS_PAID


def allowed(requested: str, max_class: str) -> bool:
    return ORDER.get(requested, 2) <= ORDER.get(max_class or MAX_DEFAULT, 1)


def describe(provider: str, base_url: str = "") -> str:
    return LABELS[classify(provider, base_url)]


def explain_refusal(provider: str, max_class: str) -> str:
    cls = classify(provider, "")
    return (f"{provider} is a {cls} brain and your limit is '{max_class}' "
            f"(Settings · Local AI & tools · Allowed brain cost). "
            f"Nothing was sent and nothing was charged. Use a local engine "
            f"(Ollama / llama.cpp) or JARVIS Lite instead — both are free forever.")


def free_summary() -> list[tuple[str, str, str]]:
    """Rows for the UI and the docs: (what, cost, note)."""
    return [
        ("JARVIS Lite brain", "₹0 / forever", "no model, no key, no network"),
        (f"{len(LOCAL_PROVIDERS) - 1} local engines", "₹0 / forever",
         "your laptop does the work"),
        ("Voice in + out", "₹0 / forever", "Windows SAPI, offline"),
        ("Wake word", "₹0 / forever", "Vosk, offline"),
        ("All 25 automation tools", "₹0 / forever", "local app functions"),
        ("Magic mode + charms + HUD", "₹0 / forever", "our own code"),
        ("MCP tool servers", "₹0 / forever", "open-source, local processes"),
        ("Groq / Gemini free tier", "₹0 / rate limited", "optional, needs a key"),
        ("OpenAI / paid APIs", "💰 blocked by default", "opt-in only, never automatic"),
    ]
