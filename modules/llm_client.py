from __future__ import annotations

import importlib.util
import json
import os
import urllib.error
import urllib.request

from modules.llm_config_store import get_active_llm_config, get_llm_config as find_config, public_url


def has_api_key() -> bool:
    config = get_active_llm_config()
    return bool((config and config.api_key) or os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY"))


def get_llm_config() -> dict[str, str | bool]:
    config = get_active_llm_config()
    api_key = config.api_key if config else (os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY", ""))
    base_url = config.base_url if config else (os.getenv("LLM_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    model = config.model if config else (os.getenv("LLM_MODEL") or os.getenv("DEEPSEEK_MODEL", "deepseek-chat"))
    return {
        "has_api_key": bool(api_key),
        "has_openai_package": importlib.util.find_spec("openai") is not None,
        "base_url": public_url(base_url),
        "model": model,
        "active_config_id": config.id if config else "",
        "active_config_name": config.name if config else ".env",
    }


def generate_answer(messages: list[dict[str, str]], temperature: float = 0.2, config_id: str | None = None) -> str:
    config = find_config(config_id) if config_id else get_active_llm_config()
    if config_id and config is None:
        raise ValueError("模型配置不存在")
    api_key = config.api_key if config else (os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY"))
    if not api_key:
        raise RuntimeError("未配置 LLM_API_KEY，请先复制 .env.example 为 .env 并填写 API Key。")

    base_url = config.base_url if config else (os.getenv("LLM_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    model = config.model if config else (os.getenv("LLM_MODEL") or os.getenv("DEEPSEEK_MODEL", "deepseek-chat"))

    try:
        from openai import OpenAI
    except ModuleNotFoundError as exc:
        return _generate_answer_with_urllib(
            api_key=api_key,
            base_url=base_url,
            model=model,
            messages=messages,
            temperature=temperature,
        )

    try:
        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            max_retries=0,
        )
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            timeout=30,
        )
        return response.choices[0].message.content or ""
    except Exception as exc:
        raise RuntimeError("模型连接失败，请检查 API 配置、网络或额度") from exc


def _generate_answer_with_urllib(
    api_key: str,
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
) -> str:
    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    payload = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "rag-qa-system/0.1 OpenAI-Compatible-Client",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"模型接口返回 HTTP {exc.code}，请检查配置或额度") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("模型接口网络连接失败") from exc

    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("模型接口返回格式异常") from exc
