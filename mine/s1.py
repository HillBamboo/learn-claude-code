import locale
import os
import json
import sys
import httpx
from openai import APIConnectionError, APIStatusError, Omit, OpenAI
import subprocess
from pathlib import Path

# 导入 litellm 相关模块
from litellm import completion
import litellm

# litellm._turn_on_debug()

try:
    import readline
except ImportError:
    readline = None


# BASE_URL = "https://risingsun.top/v1"
BASE_URL = "https://api.siliconflow.cn/v1"
API_KEY = os.getenv(
    "OPENAI_API_KEY",
    # "sk-2f9d6ade55a83b39421b421b3b66216462a468e73cd71dff8c538b8f5ae76e8f", # risingsun API Key
    "sk-acwpgbragsdovfdlffmqtuhgssyhsmwypuewxjfgmcucyzxu", # SiliconFlow API Key
)
API_KEY = "sk-acwpgbragsdovfdlffmqtuhgssyhsmwypuewxjfgmcucyzxu"
# MODEL = "gpt-5.4" # risingsun Model
MODEL = "openai/deepseek-ai/DeepSeek-R1" # siliconFlow Model
PROMPT = "Write a one-sentence bedtime story about a unicorn."
WORKDIR = Path.cwd()
SYSTEM = f"You are a coding agent at {WORKDIR}. Use bash to solve tasks. Act, don't explain."

def safe_path(path: str) -> Path:
    path = (WORKDIR / path).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {path}")
    return path

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

def run_read_file(path: str, limit: int = None) -> str:
    try:
        text = safe_path(path).read_text()
        lines = text.splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]
        return "\n".join(lines)[:50000]
    except Exception as e:
        return f"Error: {e}"


def run_write_file(path: str, content: str) -> None:
    try:
        fp = safe_path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content)
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"


def run_edit_file(path: str, old_text: str, new_text: str) -> str:
    try:
        fp = safe_path(path)
        content = fp.read_text()
        if old_text not in content:
            return f"Error: Text not found in {path}"
        fp.write_text(content.replace(old_text, new_text, 1))
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"

TOOLS = [ 
    {"type": "function", "function": {"name": "bash", "description": "Run a shell command.", "parameters": {"type": "object", "properties": {"command": {"type": "string", "description": "The shell command to run."}}, "required": ["command"], "additionalProperties": False}}}, \
    {"type": "function", "function": {"name": "read_file", "description": "Read a file.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "The file to read."}}, "required": ["path"], "additionalProperties": False}}}, \
    {"type": "function", "function": {"name": "write_file", "description": "Write a file.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "The file to write."}, "content": {"type": "string", "description": "The content to write to the file."}}, "required": ["path", "content"], "additionalProperties": False}}}, \
    {"type": "function", "function": {"name": "edit_file", "description": "Edit a file.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "The file to edit."}, "old_text": {"type": "string", "description": "The text to replace."}, "new_text": {"type": "string", "description": "The new text to use."}}, "required": ["path", "old_text", "new_text"], "additionalProperties": False}}} \
]

TOOL_HANDLER = {
    "bash": lambda **kw: run_bash(kw["command"]),
    "read_file": lambda **kw: run_read_file(kw["path"], kw.get("limit")),
    "write_file": lambda **kw: run_write_file(kw["path"], kw["content"]),
    "edit_file": lambda **kw: run_edit_file(kw["path"], kw["old_text"], kw["new_text"]),
}

def add_input_history(user_input: str) -> None:
    if readline is None:
        return

    text = user_input.strip()
    if not text or text.startswith("/"):
        return

    readline.add_history(user_input)

def can_use_readline() -> bool:
    return (
        readline is not None
        and sys.stdin is not None
        and sys.stdout is not None
        and sys.stdin.isatty()
        and sys.stdout.isatty()
    )

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


def stream_response(user_prompt: list[str] = None, extra: dict = None) -> dict:
    # 使用 litellm 的 completion 方法来支持多种 API 格式
    # 构建消息列表
    messages = []
    
    # 添加系统提示
    messages.append({"role": "system", "content": SYSTEM})
    
    # 处理用户提示
    if user_prompt:
        for prompt in user_prompt:
            if isinstance(prompt, dict) and "content" in prompt:
                # 如果是字典格式，提取内容
                content = prompt.get("content", "")
                if isinstance(content, list):
                    # 如果内容是列表，提取文本
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "input_text":
                            messages.append({"role": "user", "content": item.get("text", "")})
                else:
                    messages.append({"role": "user", "content": content})
            else:
                # 如果是字符串格式
                messages.append({"role": "user", "content": str(prompt)})
    
    try:
        # 使用 litellm 的 completion 方法
        response = completion(
            model=MODEL,
            messages=messages,
            api_base=BASE_URL,
            api_key=API_KEY,
            tools=TOOLS,
            tool_choice="auto",
            stream=True,
            **(extra or {})
        )
        
        # 将 litellm 响应转换为原有格式
        result = {
            "output": []
        }

        
        # 处理响应内容
        message = response.choices[0].message
        if message:
            content = message.content
            tool_calls = message.tool_calls
            
            if tool_calls:
                # 处理工具调用
                for tool_call in tool_calls:
                    result["output"].append({
                        "type": "function_call",
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                        "id": tool_call.id,
                    })
            else:
                # 处理普通文本回复
                result["output"].append({
                    "role": "assistant",
                    "type": "message",
                    "content": [
                        {
                            "type": "text",
                            "text": content if content else ""
                        }
                    ]
                })
        
        return result
        
    except Exception as e:
        print(f"Error in stream_response: {e}")
        raise


def agentic_loop(user_input: list[str]):
    conversation = list(user_input)
    while True:
        response = stream_response(list(conversation))
        if len(response["output"]) and response["output"][0]["type"] != "function_call":
            return response["output"][0]
        
        output = response["output"][0]
        print(output)
        arguments = json.loads(output["arguments"])
        print("  calling tools: ", list(arguments.values())[0])
        
        # 根据工具名称调用相应的处理器
        tool_name = output["name"]
        if tool_name in TOOL_HANDLER:
            tool_result = TOOL_HANDLER[tool_name](**arguments)
        else:
            tool_result = f"Error: Unknown tool {tool_name}"
        
        conversation.extend(response["output"])
        conversation.append(build_tool_result_item(output["id"], tool_result))


def main():
    def stream_callback(chunk: str):
        """流式输出回调函数，实时显示AI回复内容"""
        print(chunk, end="", flush=True)
    
    while True:
        try:
            user_input = read_console_input("> ")
            if user_input.startswith("/q") or user_input.startswith("/e"):
                raise KeyboardInterrupt()
        except (KeyboardInterrupt, EOFError):
            print("\nGood bye!")
            return
        add_input_history(user_input)
        try:
            print("  * ", end="", flush=True)  # 开始显示回复
            result = agentic_loop(build_user_input(user_input))
            print()  # 换行结束流式输出
            
            # 处理最终结果（用于工具调用后的处理）
            if isinstance(result, dict) and "content" in result:
                content_list = result["content"]
                if isinstance(content_list, list) and len(content_list) > 0:
                    answer = content_list[0].get("text", str(content_list[0]))
            answer = str(result)
            
            # 只有在有最终消息时才显示
            if answer and answer != "None":
                print("  * ", answer)
        except Exception as e:
            print(f"Error during processing: {e}")
            continue
        

if __name__ == "__main__":
    raise SystemExit(main())