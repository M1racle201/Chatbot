"""运行时 API 配置的读取、校验和持久化。"""

import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_SETTINGS = {
    "base_url": "https://api.deepseek.com",
    "api_key": "",
    "model": "deepseek-chat",
}
SETTING_KEYS = tuple(DEFAULT_SETTINGS)


def _settings_path(project_root, data_dir=None) -> Path:
    return Path(data_dir) / "settings.json" if data_dir else Path(project_root) / "data" / "settings.json"


def _normalize(settings: dict) -> dict:
    return {
        "base_url": str(settings.get("base_url", "")).strip().rstrip("/"),
        "api_key": str(settings.get("api_key", "")).strip(),
        "model": str(settings.get("model", "")).strip(),
    }


def load_settings(project_root, env=None, data_dir=None) -> dict:
    """按默认值、环境变量、settings.json 的顺序加载配置。"""
    env = os.environ if env is None else env
    settings = {
        "base_url": str(env.get("BASE_URL", DEFAULT_SETTINGS["base_url"])).strip()
        or DEFAULT_SETTINGS["base_url"],
        "api_key": str(env.get("DEEPSEEK_API", DEFAULT_SETTINGS["api_key"])).strip(),
        "model": str(env.get("MODEL_DEFAULT", DEFAULT_SETTINGS["model"])).strip()
        or DEFAULT_SETTINGS["model"],
    }
    path = _settings_path(project_root, data_dir=data_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for key in SETTING_KEYS:
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    settings[key] = value.strip()
    except (OSError, UnicodeError, json.JSONDecodeError):
        pass
    return _normalize(settings)


def validate_settings(settings: dict) -> dict:
    """校验并规范化用户提交的运行时配置。"""
    if not isinstance(settings, dict):
        raise ValueError("配置必须是对象")
    normalized = _normalize(settings)
    parsed = urlparse(normalized["base_url"])
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("API URL 必须是有效的 http 或 https 地址")
    if not normalized["api_key"]:
        raise ValueError("API Key 不能为空")
    if not normalized["model"]:
        raise ValueError("模型名称不能为空")
    return normalized


def save_settings(project_root, settings: dict, data_dir=None) -> dict:
    """校验后以 UTF-8 原子写入 data/settings.json。"""
    normalized = validate_settings(settings)
    path = _settings_path(project_root, data_dir=data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="settings-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as file:
            json.dump(normalized, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return normalized
