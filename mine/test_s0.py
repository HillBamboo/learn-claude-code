import io
import unittest
from unittest.mock import patch

from mine import s0


class ReadConsoleInputTests(unittest.TestCase):
    def test_read_console_input_uses_builtin_input_for_interactive_readline(self):
        with patch.object(s0, "readline", object()), \
             patch.object(s0, "can_use_readline", return_value=True), \
             patch.object(s0, "input", return_value="history-enabled", create=True) as mock_input:
            self.assertEqual(s0.read_console_input("> "), "history-enabled")

        mock_input.assert_called_once_with("> ")

    def test_read_console_input_decodes_utf8_bytes(self):
        fake_stdin = io.TextIOWrapper(io.BytesIO("1 + 1\n".encode("utf-8")), encoding="utf-8")
        fake_stdout = io.StringIO()

        with patch.object(s0.sys, "stdin", fake_stdin), patch.object(s0.sys, "stdout", fake_stdout):
            self.assertEqual(s0.read_console_input("> "), "1 + 1")

        self.assertEqual(fake_stdout.getvalue(), "> ")

    def test_read_console_input_falls_back_for_gbk_bytes(self):
        fake_stdin = io.TextIOWrapper(io.BytesIO("必须调用工具告诉我今夕是何年\n".encode("gbk")), encoding="utf-8")
        fake_stdout = io.StringIO()

        with patch.object(s0.sys, "stdin", fake_stdin), patch.object(s0.sys, "stdout", fake_stdout):
            self.assertEqual(s0.read_console_input("> "), "必须调用工具告诉我今夕是何年")

        self.assertEqual(fake_stdout.getvalue(), "> ")

    def test_read_console_input_raises_eof_error_on_empty_stream(self):
        fake_stdin = io.TextIOWrapper(io.BytesIO(b""), encoding="utf-8")

        with patch.object(s0.sys, "stdin", fake_stdin), self.assertRaises(EOFError):
            s0.read_console_input("> ")


class AgenticLoopTests(unittest.TestCase):
    def test_agentic_loop_resubmits_explicit_history_after_tool_call(self):
        first_response = {
            "id": "resp_1",
            "output": [
                {
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "bash",
                    "arguments": '{"command":"date +%Y年%m月"}',
                }
            ],
        }
        second_response = {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "2026年03月"}],
                }
            ]
        }
        calls = []

        def fake_stream_response(client, user_prompt, extra=None):
            calls.append((user_prompt, extra))
            return first_response if len(calls) == 1 else second_response

        initial_input = s0.build_user_input("必须调用工具告诉我今夕是何年何月？")
        with patch.object(s0, "build_client", return_value=object()), \
             patch.object(s0, "stream_response", side_effect=fake_stream_response), \
             patch.object(s0, "run_bash", return_value="2026年03月"):
            result = s0.agentic_loop(initial_input)

        self.assertEqual(result, second_response["output"][0])
        self.assertEqual(calls[0], (initial_input, None))
        self.assertEqual(
            calls[1],
            (
                initial_input
                + [first_response["output"][0]]
                + [
                    {
                        "type": "function_call_output",
                        "call_id": "call_1",
                        "output": "2026年03月",
                    }
                ],
                None,
            ),
        )


class StreamResponseTests(unittest.TestCase):
    def test_stream_response_uses_post_responses_endpoint(self):
        client = unittest.mock.Mock()
        client.post.return_value = unittest.mock.Mock(text='{"output": []}')

        s0.stream_response(client, s0.build_user_input("hi"))

        client.post.assert_called_once()

    def test_stream_response_returns_completed_message(self):
        final_response = {"output": [{"type": "message", "content": [{"type": "output_text", "text": "你好"}]}]}
        client = unittest.mock.Mock()
        client.post.return_value = unittest.mock.Mock(text='{"output": [{"type": "message", "content": [{"type": "output_text", "text": "\\u4f60\\u597d"}]}]}')

        result = s0.stream_response(client, s0.build_user_input("hi"))

        self.assertEqual(
            result["output"][0]["content"][0]["text"],
            "你好",
        )


class HistoryTests(unittest.TestCase):
    def test_add_input_history_records_non_empty_user_input(self):
        readline = unittest.mock.Mock()

        with patch.object(s0, "readline", readline):
            s0.add_input_history("what time is it?")

        readline.add_history.assert_called_once_with("what time is it?")

    def test_add_input_history_ignores_blank_and_command_input(self):
        readline = unittest.mock.Mock()

        with patch.object(s0, "readline", readline):
            s0.add_input_history("   ")
            s0.add_input_history("/q")

        readline.add_history.assert_not_called()

    def test_main_adds_user_input_to_history_for_current_session(self):
        response = {"content": [{"type": "output_text", "text": "pong"}]}

        with patch.object(s0, "read_console_input", side_effect=["ping", "/q"]), \
             patch.object(s0, "agentic_loop", return_value=response), \
             patch.object(s0, "build_user_input", return_value=[{"role": "user"}]), \
             patch.object(s0, "add_input_history") as mock_add_history, \
             patch.object(s0, "print") as mock_print:
            s0.main()

        mock_add_history.assert_called_once_with("ping")
        mock_print.assert_any_call("  * ", "pong")
        mock_print.assert_any_call("Good bye!")


if __name__ == "__main__":
    unittest.main()
