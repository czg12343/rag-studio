from __future__ import annotations

import json
import uuid
from urllib.parse import urlsplit, urlunsplit
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from modules.settings import DATA_DIR, STATE_LOCK, atomic_json


CONFIG_PATH = DATA_DIR / "llm_configs.json"


@dataclass(frozen=True)
class LlmConfig:
    id: str
    name: str
    api_key: str
    base_url: str
    model: str
    active: bool = False


def list_llm_configs(mask_keys: bool = True) -> list[dict[str, Any]]:
    data = _read_data()
    configs = data.get("configs", [])
    if not isinstance(configs, list):
        configs = []

    result = []
    for config in configs:
        item = dict(config)
        if mask_keys:
            item["api_key"] = _mask_key(str(item.get("api_key", "")))
            item["base_url"] = public_url(str(item.get("base_url", "")))
        result.append(item)
    return result


def get_active_llm_config() -> LlmConfig | None:
    data = _read_data()
    configs = data.get("configs", [])
    if not isinstance(configs, list):
        return None
    for config in configs:
        if config.get("active"):
            return _to_config(config)
    return None


def get_llm_config(config_id: str) -> LlmConfig | None:
    data = _read_data()
    configs = data.get("configs", [])
    if not isinstance(configs, list):
        return None
    for config in configs:
        if str(config.get("id")) == config_id:
            return _to_config(config)
    return None


def save_llm_config(name: str, api_key: str, base_url: str, model: str, active: bool = False) -> dict[str, Any]:
    data = _read_data()
    configs = data.setdefault("configs", [])
    if not isinstance(configs, list):
        configs = []
        data["configs"] = configs

    config = {
        "id": uuid.uuid4().hex,
        "name": name.strip(),
        "api_key": api_key.strip(),
        "base_url": base_url.strip().rstrip("/"),
        "model": model.strip(),
        "active": bool(active) or not configs,
    }
    if config["active"]:
        for item in configs:
            item["active"] = False
    configs.append(config)
    _write_data(data)

    safe = dict(config)
    safe["api_key"] = _mask_key(config["api_key"])
    return safe


def activate_llm_config(config_id: str) -> dict[str, Any]:
    data = _read_data()
    configs = data.get("configs", [])
    if not isinstance(configs, list):
        raise ValueError("LLM 配置数据格式错误。")

    selected: dict[str, Any] | None = None
    for config in configs:
        is_selected = str(config.get("id")) == config_id
        config["active"] = is_selected
        if is_selected:
            selected = config

    if not selected:
        raise ValueError("未找到指定的模型配置。")

    _write_data(data)
    safe = dict(selected)
    safe["api_key"] = _mask_key(str(safe.get("api_key", "")))
    return safe


def delete_llm_config(config_id: str) -> int:
    data = _read_data()
    configs = data.get("configs", [])
    if not isinstance(configs, list):
        return 0

    deleted_active = any(str(config.get("id")) == config_id and config.get("active") for config in configs)
    kept = [config for config in configs if str(config.get("id")) != config_id]
    deleted = len(configs) - len(kept)
    if deleted and deleted_active and kept:
        kept[0]["active"] = True
    data["configs"] = kept
    _write_data(data)
    return deleted


def _read_data() -> dict[str, Any]:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        return {"configs": []}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("模型配置文件损坏，请先备份并修复，系统不会覆盖原文件") from exc


def _write_data(data: dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with STATE_LOCK:
        atomic_json(CONFIG_PATH, data)


def _to_config(data: dict[str, Any]) -> LlmConfig:
    return LlmConfig(
        id=str(data.get("id", "")),
        name=str(data.get("name", "")),
        api_key=str(data.get("api_key", "")),
        base_url=str(data.get("base_url", "")),
        model=str(data.get("model", "")),
        active=bool(data.get("active")),
    )


def _mask_key(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 12:
        return "********"
    return f"********{api_key[-4:]}"


def public_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        if ":" in host:
            host = f"[{host}]"
        if parsed.port:
            host += f":{parsed.port}"
        return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
    except ValueError:
        return "[无效地址]"
