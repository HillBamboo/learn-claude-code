import importlib
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PROMPT = "Build a CLI calculator that supports add, subtract, multiply, divide operations. The script should be named calculator.py. Use argparse for argument parsing. Don't include explanations, only the code."
REPO_ROOT = Path(__file__).resolve().parent.parent
MOCK_FILE_PATH = "calculator.py"
MOCK_CALCULATOR_CODE = """import argparse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["add", "subtract", "multiply", "divide"])
    parser.add_argument("left", type=float)
    parser.add_argument("right", type=float)
    args = parser.parse_args()

    if args.operation == "add":
        result = args.left + args.right
    elif args.operation == "subtract":
        result = args.left - args.right
    elif args.operation == "multiply":
        result = args.left * args.right
    else:
        result = args.left / args.right

    if result.is_integer():
        print(int(result))
    else:
        print(result)


if __name__ == "__main__":
    main()
"""


def load_s3_module():
    repo_root_str = str(REPO_ROOT)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)

    if os.getenv("S3_MOCK") != "1":
        sys.modules.setdefault("litellm", types.SimpleNamespace(completion=lambda **_: None))

    sys.modules.pop("mine.s3", None)
    return importlib.import_module("mine.s3")


def make_tool_call(name: str, arguments: dict, call_id: str = "call_1"):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


def make_response(
    text: str | None = None,
    finish_reason: str = "stop",
    tool_calls: list | None = None,
):
    message = SimpleNamespace(role="assistant", content=text, tool_calls=tool_calls or [])
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice])


class FakeStreamingResponse:
    def __init__(self, lines: list[str]):
        self._lines = lines

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        return None

    def iter_lines(self):
        return iter(self._lines)


def assert_cli_calculator_behavior(test_case: unittest.TestCase, script_path: Path):
    code = script_path.read_text()
    compile(code, str(script_path), "exec")

    expectations = [
        ("add", "2", "3", "5"),
        ("subtract", "7", "4", "3"),
        ("multiply", "6", "5", "30"),
        ("divide", "8", "2", "4"),
    ]

    for operation, left, right, expected in expectations:
        completed = subprocess.run(
            [sys.executable, str(script_path), operation, left, right],
            capture_output=True,
            text=True,
            check=True,
        )
        test_case.assertEqual(completed.stdout.strip(), expected)


def find_generated_python_file(workdir: Path) -> Path:
    python_files = sorted(workdir.glob("*.py"))
    print(f"{workdir} => {python_files = }")
    if len(python_files) != 1:
        raise AssertionError(f"Expected exactly one generated Python file, found {len(python_files)}")
    return python_files[0]


class AgentLoopPromptTests(unittest.TestCase):
    def test_parse_sse_events_streams_text_and_returns_completed_response(self):
        s3 = load_s3_module()
        completed_response = {
            "id": "resp_123",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "hello world"}],
                }
            ],
        }
        stream = FakeStreamingResponse(
            [
                'event: response.output_text.delta',
                'data: {"type":"response.output_text.delta","delta":"hello "}',
                "",
                'event: response.output_text.delta',
                'data: {"type":"response.output_text.delta","delta":"world"}',
                "",
                'event: response.completed',
                f"data: {json.dumps({'type': 'response.completed', 'response': completed_response})}",
                "",
            ]
        )

        with patch.object(s3, "print") as mock_print:
            result = s3.parse_sse_events(stream.iter_lines())

        self.assertEqual(result, completed_response)
        self.assertEqual(mock_print.call_args_list[0].args, ("hello ",))
        self.assertEqual(mock_print.call_args_list[0].kwargs, {"end": "", "flush": True})
        self.assertEqual(mock_print.call_args_list[1].args, ("world",))
        self.assertEqual(mock_print.call_args_list[1].kwargs, {"end": "", "flush": True})

    def test_agent_loop_prints_tool_name_and_result(self):
        s3 = load_s3_module()
        history = [
            {"role": "system", "content": s3.SYSTEM},
            {"role": "user", "content": PROMPT},
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            responses = [
                make_response(
                    finish_reason="tool_calls",
                    tool_calls=[
                        make_tool_call(
                            "write_file",
                            {"path": MOCK_FILE_PATH, "content": MOCK_CALCULATOR_CODE},
                        )
                    ],
                ),
                make_response(text="calculator.py created"),
            ]

            with patch.object(s3, "WORKDIR", workdir), \
                 patch.object(s3, "request_stream_completion", side_effect=responses), \
                 patch.object(s3, "print") as mock_print:
                s3.agent_loop(history)

            self.assertEqual(mock_print.call_args_list[0].args[0], f'[tool] write_file {json.dumps({"path": MOCK_FILE_PATH, "content": MOCK_CALCULATOR_CODE}, ensure_ascii=False)}')
            self.assertEqual(mock_print.call_args_list[1].args[0], f"[result] Wrote {len(MOCK_CALCULATOR_CODE)} bytes")

    def test_cli_calculator_prompt_generates_expected_code(self):
        s3 = load_s3_module()
        history = [
            {"role": "system", "content": s3.SYSTEM},
            {"role": "user", "content": PROMPT},
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)

            if os.getenv("S3_NO_MOCK") == "1":
                with patch.object(s3, "WORKDIR", workdir):
                    s3.agent_loop(history)
                # raise
                script_path = find_generated_python_file(workdir)
            else:
                responses = [
                    {
                        "output": [
                            {
                                "type": "function_call",
                                "call_id": "call_1",
                                "name": "write_file",
                                "arguments": json.dumps(
                                    {"path": MOCK_FILE_PATH, "content": MOCK_CALCULATOR_CODE}
                                ),
                            }
                        ]
                    },
                    {
                        "output": [
                            {
                                "type": "message",
                                "content": [{"type": "output_text", "text": "calculator.py created"}],
                            }
                        ]
                    },
                ]
                with patch.object(s3, "WORKDIR", workdir), \
                     patch.object(s3, "request_stream_completion", side_effect=responses), \
                     patch.object(s3, "print"):
                    s3.agent_loop(history)
                script_path = workdir / MOCK_FILE_PATH

            self.assertEqual(history[-1]["role"], "assistant")
            self.assertTrue(script_path.exists())
            assert_cli_calculator_behavior(self, script_path)

    def test_main_skips_blank_input_and_keeps_prompting(self):
        s3 = load_s3_module()

        with patch.object(s3, "input", side_effect=["build calculator", "   ", "exit"]), \
             patch.object(s3, "agent_loop", return_value=False) as mock_agent_loop:
            s3.main()

        self.assertEqual(
            mock_agent_loop.call_args_list,
            [
                unittest.mock.call(
                    [
                        {"role": "system", "content": s3.SYSTEM},
                        {"role": "user", "content": "build calculator"},
                    ]
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
