from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "user_interaction" / "src"))
sys.path.insert(0, str(REPO_ROOT))

import main as nafi_main
from user_interaction_layer.config.env import EnvFileError, load_env_file, load_project_env
from user_interaction_layer.config.settings import ConfigurationError, InteractionSettings


class EnvironmentLoadingTests(unittest.TestCase):
    def test_loader_handles_quotes_comments_and_preserves_exported_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_path = Path(temporary_directory) / ".env"
            env_path.write_text(
                "export NAFI_TEST_ALPHA=from-file\n"
                "NAFI_TEST_BETA='value with spaces' # comment\n"
                "NAFI_TEST_GAMMA=plain # comment\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"NAFI_TEST_ALPHA": "from-shell"}, clear=True):
                loaded = load_env_file(env_path)
                self.assertEqual(os.environ["NAFI_TEST_ALPHA"], "from-shell")
                self.assertEqual(os.environ["NAFI_TEST_BETA"], "value with spaces")
                self.assertEqual(os.environ["NAFI_TEST_GAMMA"], "plain")
                self.assertNotIn("NAFI_TEST_ALPHA", loaded)

    def test_loader_reports_invalid_lines_with_file_and_line(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_path = Path(temporary_directory) / ".env"
            env_path.write_text("GOOD=value\nnot valid\n", encoding="utf-8")
            with self.assertRaisesRegex(EnvFileError, r"\.env:2: expected KEY=value"):
                load_env_file(env_path)

    def test_project_loader_uses_root_env(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / ".env").write_text("NAFI_TEST_ROOT=loaded\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                selected = load_project_env(root)
                self.assertEqual(selected, root / ".env")
                self.assertEqual(os.environ["NAFI_TEST_ROOT"], "loaded")


class InteractionSettingsTests(unittest.TestCase):
    def test_keyless_defaults_are_fully_runnable_in_mock_mode(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = InteractionSettings.from_env()

        self.assertEqual(settings.resolved_voice_provider, "mock")
        self.assertEqual(settings.security.guard_provider, "deterministic")
        self.assertEqual(settings.openai.chat_model, "gpt-5.6-luna")
        self.assertEqual(settings.openai.realtime_model, "gpt-realtime-2.1")
        self.assertEqual(settings.openai.realtime_voice, "marin")

    def test_one_openai_key_enables_auto_voice(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True):
            settings = InteractionSettings.from_env()

        self.assertEqual(settings.resolved_voice_provider, "openai")
        self.assertEqual(settings.openai.api_key, "test-key")

    def test_explicit_openai_without_key_falls_back_instead_of_crashing_demo(self) -> None:
        with patch.dict(os.environ, {"VOICE_AUDIO_PROVIDER": "openai"}, clear=True):
            settings = InteractionSettings.from_env()

        self.assertEqual(settings.resolved_voice_provider, "mock")
        self.assertIn("offline mock provider", settings.configuration_warnings[0])

    def test_required_remote_guard_fails_closed_when_unconfigured(self) -> None:
        environment = {
            "SECURITY_GUARD_PROVIDER": "openrouter",
            "SECURITY_GUARD_REQUIRED": "true",
        }
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(ConfigurationError, "requires SECURITY_GUARD_PROVIDER"):
                InteractionSettings.from_env()

    def test_invalid_boolean_has_an_actionable_error(self) -> None:
        with patch.dict(os.environ, {"SECURITY_GUARD_REQUIRED": "sometimes"}, clear=True):
            with self.assertRaisesRegex(ConfigurationError, "must be true or false"):
                InteractionSettings.from_env()


class LauncherConfigurationTests(unittest.TestCase):
    def test_launcher_builds_all_services_from_keyless_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            stack_settings = nafi_main.StackSettings.from_env()
            specs = nafi_main._service_specs(stack_settings, sys.executable)

        self.assertEqual([spec.name for spec in specs], ["agentic", "interaction", "web"])
        self.assertEqual(specs[0].environment["AGENTIC_BACKEND"], "mock")
        self.assertEqual(specs[1].environment["VOICE_AUDIO_PROVIDER"], "auto")
        self.assertEqual(specs[1].environment["AGENTIC_BASE_URL"], "http://127.0.0.1:8090")
        self.assertEqual(
            specs[2].environment["VITE_INTERACTION_API_URL"],
            "http://127.0.0.1:8088",
        )
        self.assertEqual(specs[2].health_url, "http://localhost:3000/api/health")


if __name__ == "__main__":
    unittest.main()
