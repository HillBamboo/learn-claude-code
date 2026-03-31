import locale
import os
import json
import sys
import httpx
from openai import APIConnectionError, APIStatusError, Omit, OpenAI
import subprocess

try:
    import readline
except ImportError:
    readline = None



BASE_URL = "https://risingsun.top/v1"
API_KEY = os.getenv(
    "OPENAI_API_KEY",
    "sk-2f9d6ade55a83b39b589421b3b66216462a468e73cd71dff8c538b8f5ae76e8f",
)
MODEL = "gpt-5.4"
PROMPT = "Write a one-sentence bedtime story about a unicorn."

SYSTEM = f"You are a coding agent at {os.getcwd()}. Use bash to solve tasks. Act, don't explain."

TOOLS = [
    {
        "type": "function",
        "name": "bash",
        "description": "Run a shell command.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                "type": "string",
                "description": "The shell command to run."
                }
            },
            "required": ["command"],
            "additionalProperties": False
        }
    }
]
def run_bash(command: str) -> str:
    """
    执行 bash 命令并返回其输出
    
    Args:
        command (str): 要执行的 bash 命令字符串
    
    Returns:
        str: 命令执行的输出结果，或错误信息
    
    功能说明：
    1. 首先检查命令是否包含危险操作（如删除系统文件、使用 sudo、关机等）
    2. 如果是危险命令，直接返回错误信息
    3. 尝试执行命令，设置 120 秒超时
    4. 捕获命令的标准输出和标准错误，合并后返回
    5. 对输出进行截断，最多返回 50000 个字符
    6. 如果命令超时，返回超时错误信息
    """
    # 定义危险命令列表，包含可能对系统造成危害的操作
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    # 检查命令是否包含危险操作
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"
    try:
        # 执行命令，设置 shell=True 允许执行 bash 命令，捕获输出，设置 120 秒超时
        r = subprocess.run(command, shell=True, cwd=os.getcwd(), capture_output=True, text=True, timeout=120)
        # 合并标准输出和标准错误，并去除首尾空白
        out = (r.stdout + r.stderr).strip()
        # 返回输出，最多返回 50000 个字符，若输出为空则返回 "(no output)"
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        # 处理命令执行超时的情况
        return "Error: Timeout (120s)"


def decode_console_bytes(raw: bytes) -> str:
    encodings = []
    for encoding in [sys.stdin.encoding, locale.getpreferredencoding(False), "utf-8", "gb18030"]:
        if encoding and encoding not in encodings:
            encodings.append(encoding)

    for encoding in encodings:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue

    return raw.decode(encodings[0] if encodings else "utf-8", errors="replace")


def can_use_readline() -> bool:
    return (
        readline is not None
        and sys.stdin is not None
        and sys.stdout is not None
        and sys.stdin.isatty()
        and sys.stdout.isatty()
    )


def add_input_history(user_input: str) -> None:
    if readline is None:
        return

    text = user_input.strip()
    if not text or text.startswith("/"):
        return

    readline.add_history(user_input)


def read_console_input(prompt: str = "> ") -> str:
    if can_use_readline():
        return input(prompt)

    sys.stdout.write(prompt)
    sys.stdout.flush()

    buffer = getattr(sys.stdin, "buffer", None)
    if buffer is None:
        line = sys.stdin.readline()
        if line == "":
            raise EOFError("EOF when reading a line")
        return line.rstrip("\r\n")

    raw = buffer.readline()
    if raw == b"":
        raise EOFError("EOF when reading a line")

    return decode_console_bytes(raw).rstrip("\r\n")


def build_response_body(user_prompts: str, extra: dict = None) -> dict:
    if extra is None:
        extra = {}

    return {
        "model": MODEL,
        "stream": False,
        "instructions": SYSTEM,
        "input": user_prompts,
        "tool_choice": "auto",
        "tools": TOOLS,
        **extra,
    }

def build_user_input(inputs: any) -> list:
    if isinstance(inputs, str):
        return [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": inputs}]
            }
        ]

    user_inputs = []
    for _input in inputs:
        if isinstance(_input, str):
            user_inputs.append({
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": _input,
                    }
                ],
            })
        else:
            user_inputs.append(_input)
    return user_inputs


def build_tool_result_item(call_id: str, output: str) -> dict:
    return {
        "type": "function_call_output",
        "call_id": call_id,
        "output": output,
    }


def normalize_response(response: any) -> dict:
    if isinstance(response, dict):
        return response
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="python")
    return dict(response)


def build_client() -> OpenAI:
    return OpenAI(api_key=API_KEY, base_url=BASE_URL)

client = build_client()

def stream_response(client: OpenAI, user_prompt: list[str], extra: dict = None) -> dict:
    body = build_response_body(user_prompt, extra=extra)
    try:
        response = client.post(
            "/responses",
            cast_to=httpx.Response,
            body=body,
            options={
                "headers": {
                    "Content-Type": "application/json",
                    "User-Agent": Omit(),
                    "X-Stainless-Lang": Omit(),
                    "X-Stainless-Package-Version": Omit(),
                    "X-Stainless-OS": Omit(),
                    "X-Stainless-Arch": Omit(),
                    "X-Stainless-Runtime": Omit(),
                    "X-Stainless-Runtime-Version": Omit(),
                    "X-Stainless-Async": Omit(),
                    "X-Stainless-Retry-Count": Omit(),
                    "X-Stainless-Read-Timeout": Omit(),
                    "OpenAI-Organization": Omit(),
                    "OpenAI-Project": Omit(),
                }
            },
        )
        return json.loads(response.text)
    except APIStatusError as err:
        print(f"status_code: {err.status_code}")
        print(f"request body: {body}")
        raise
    except APIConnectionError:
        raise
    except json.JSONDecodeError:
        print(f"response text: {response.text}")
        raise
    except Exception:
        raise


def agentic_loop(user_input: list[str]):
    conversation = list(user_input)
    while True:
        response = stream_response(client, list(conversation))
        if len(response["output"]) and response["output"][0]["type"] != "function_call":
            return response["output"][0]
        
        output = response["output"][0]
        arguments = json.loads(output["arguments"])
        print("  calling tools: ", list(arguments.values())[0])
        tool_result = run_bash(**arguments)
        conversation.extend(response["output"])
        conversation.append(build_tool_result_item(output["call_id"], tool_result))


def main():
    while True:
        user_input = read_console_input("> ")
        if user_input.startswith("/q") or user_input.startswith("/e"):
            print("Good bye!")
            return
        add_input_history(user_input)
        result = agentic_loop(build_user_input(user_input))
        final_msg = result["content"][0]["text"]
        print("  * ", final_msg)
        

if __name__ == "__main__":
    # res = stream_response(build_client(), "今天是何年何月？")
    # print(res)
    raise SystemExit(main())