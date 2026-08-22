"""运行时 API 设置服务测试。"""

import json
import tempfile
import unittest
from pathlib import Path

from vibechatbot.settings import (
    DEFAULT_SETTINGS,
    load_settings,
    save_settings,
    validate_settings,
)


class TestSettings(unittest.TestCase):
    def test_settings_file_overrides_env_and_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings_path = root / "data" / "settings.json"
            settings_path.parent.mkdir()
            settings_path.write_text(
                json.dumps(
                    {
                        "base_url": "https://settings.example/v1/",
                        "api_key": "file-key",
                        "model": "file-model",
                    }
                ),
                encoding="utf-8",
            )
            result = load_settings(
                root,
                env={
                    "BASE_URL": "https://env.example",
                    "DEEPSEEK_API": "env-key",
                    "MODEL_DEFAULT": "env-model",
                },
            )
        self.assertEqual(result["base_url"], "https://settings.example/v1")
        self.assertEqual(result["api_key"], "file-key")
        self.assertEqual(result["model"], "file-model")

    def test_invalid_json_falls_back_without_exposing_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings_path = root / "data" / "settings.json"
            settings_path.parent.mkdir()
            settings_path.write_text("not-json", encoding="utf-8")
            result = load_settings(
                root,
                env={"BASE_URL": "https://env.example", "DEEPSEEK_API": "env-key"},
            )
        self.assertEqual(result["base_url"], "https://env.example")
        self.assertEqual(result["api_key"], "env-key")
        self.assertEqual(result["model"], DEFAULT_SETTINGS["model"])

    def test_validate_rejects_non_http_url_and_empty_required_fields(self):
        with self.assertRaises(ValueError):
            validate_settings({"base_url": "ftp://example.com", "api_key": "x", "model": "m"})
        with self.assertRaises(ValueError):
            validate_settings({"base_url": "https://example.com", "api_key": "", "model": "m"})
        with self.assertRaises(ValueError):
            validate_settings({"base_url": "https://example.com", "api_key": "x", "model": ""})

    def test_save_uses_utf8_and_writes_expected_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = save_settings(
                root,
                {
                    "base_url": "https://api.example/v1/",
                    "api_key": "secret-key",
                    "model": "模型-1",
                },
            )
            saved = json.loads(
                (root / "data" / "settings.json").read_text(encoding="utf-8")
            )
        self.assertEqual(result["base_url"], "https://api.example/v1")
        self.assertEqual(saved["model"], "模型-1")
        self.assertEqual(saved["api_key"], "secret-key")


if __name__ == "__main__":
    unittest.main()
