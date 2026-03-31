import json
import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(override=True)

WORKDIR = Path.cwd()
# SiliconFlow's DeepSeek-V3 accepts the first tool call but rejects the
# follow-up tool history; this default was verified to support the loop.
MODEL_ID = os.getenv("MODEL_ID")
BASE_URL = os.getenv("OPENAI_BASE_URL")
API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = MODEL_ID
# MODEL = (
#     MODEL_ID if MODEL_ID and MODEL_ID.startswith("openai/")
#     else f"openai/{MODEL_ID}" 
# )

SYSTEM = f"""You are a coding agent at {WORKDIR}.
Use the todo tool to plan multi-step tasks. Mark in_progress before starting, completed when done.
Prefer tools over prose."""


# -- TodoManager: structured state the LLM writes to --
class TodoManager:
    def __init__(self):
        self.items = []

    def update(self, items: list) -> str:
        if len(items) > 20:
            raise ValueError("Max 20 todos allowed")
        validated = []
        in_progress_count = 0
        for i, item in enumerate(items):
            text = str(item.get("text", "")).strip()
            status = str(item.get("status", "pending")).lower()
            item_id = str(item.get("id", str(i + 1)))
            if not text:
                raise ValueError(f"Item {item_id}: text required")
            if status not in ("pending", "in_progress", "completed"):
                raise ValueError(f"Item {item_id}: invalid status '{status}'")
            if status == "in_progress":
                in_progress_count += 1
            validated.append({"id": item_id, "text": text, "status": status})
        if in_progress_count > 1:
            raise ValueError("Only one task can be in_progress at a time")
        self.items = validated
        return self.render()

    def render(self) -> str:
        if not self.items:
            return "No todos."
        lines = []
        for item in self.items:
            marker = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]"}[item["status"]]
            lines.append(f"{marker} #{item['id']}: {item['text']}")
        done = sum(1 for t in self.items if t["status"] == "completed")
        lines.append(f"\n({done}/{len(self.items)} completed)")
        return "\n".join(lines)


TODO = TodoManager()


def build_client():
    from openai import OpenAI

    return OpenAI(api_key=API_KEY, base_url=BASE_URL)


CLIENT = None


def build_system_prompt() -> str:
    return f"""You are a coding agent at {WORKDIR}.
Use the todo tool to plan multi-step tasks. Mark in_progress before starting, completed when done.
Prefer tools over prose."""


def build_user_input(messages: list[dict]) -> list[dict]:
    items = []
    for message in messages:
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            items.append(
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": content}],
                }
            )
        else:
            items.append(message)
    return items


def build_response_body(response_input: list, extra: dict | None = None) -> dict:
    body = {
        "model": MODEL,
        "stream": False,
        "instructions": build_system_prompt(),
        "input": response_input,
        "tool_choice": "auto",
        "tools": TOOLS,
    }
    if extra:
        body.update(extra)
    return body


def build_tool_result_item(call_id: str, output: str) -> dict:
    return {
        "type": "function_call_output",
        "call_id": call_id,
        "output": output,
    }


def request_completion(response_input: list, extra: dict | None = None):
    import httpx
    from openai import APIConnectionError, APIStatusError, Omit
    global CLIENT
    if CLIENT is None:
        CLIENT = build_client()

    body = build_response_body(response_input, extra=extra)
    try:
        response = CLIENT.post(
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
    except APIStatusError:
        raise
    except APIConnectionError:
        raise
    except json.JSONDecodeError:
        raise


def normalize_message(message) -> dict:
    if isinstance(message, dict):
        return message
    if hasattr(message, "model_dump"):
        return message.model_dump(mode="python")
    return {
        "role": getattr(message, "role", "assistant"),
        "content": getattr(message, "content", None),
    }


def normalize_response(response) -> dict:
    if isinstance(response, dict):
        return response
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="python")
    return dict(response)


def extract_text_content(message: dict) -> str | None:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(text)
        return "\n".join(parts) if parts else None
    return None


def extract_response_text(response: dict) -> str | None:
    output = response.get("output", [])
    parts = []
    for item in output:
        if item.get("type") != "message":
            continue
        for content_item in item.get("content", []):
            text = content_item.get("text")
            if text:
                parts.append(text)
    return "\n".join(parts) if parts else None


def extract_function_calls(response: dict) -> list[dict]:
    return [item for item in response.get("output", []) if item.get("type") == "function_call"]


def log_tool_event(tool_name: str, tool_args: dict, output: str) -> None:
    print(f"[tool] {tool_name} {json.dumps(tool_args, ensure_ascii=False)}")
    print(f"[result] {output}")


def parse_sse_events(lines) -> dict:
    event_type = None
    data_lines = []
    completed_response = None
    saw_text_delta = False

    def flush_event(current_event_type, current_data_lines):
        nonlocal completed_response, saw_text_delta
        if not current_data_lines:
            return

        data = "\n".join(current_data_lines)
        if data == "[DONE]":
            return

        payload = json.loads(data)
        current_event_type = current_event_type or payload.get("type")

        if current_event_type == "response.output_text.delta":
            delta = payload.get("delta", "")
            if delta:
                saw_text_delta = True
                print(delta, end="", flush=True)
            return

        if current_event_type == "response.completed":
            completed_response = payload.get("response", payload)
            if not saw_text_delta:
                final_text = extract_response_text(completed_response)
                if final_text:
                    print(final_text, end="", flush=True)
            return

        if current_event_type == "response.failed":
            response = payload.get("response")
            if response:
                completed_response = response
            raise RuntimeError(payload)

    for raw_line in lines:
        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
        if line == "":
            flush_event(event_type, data_lines)
            event_type = None
            data_lines = []
            continue

        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_type = line[len("event:"):].strip()
            continue
        if line.startswith("data:"):
            data_lines.append(line[len("data:"):].strip())

    flush_event(event_type, data_lines)
    return completed_response or {"output": []}


def request_stream_completion(response_input: list, extra: dict | None = None) -> dict:
    import httpx

    body = build_response_body(response_input, extra={"stream": True, **(extra or {})})
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    with httpx.stream(
        "POST",
        f"{BASE_URL.rstrip('/')}/responses",
        headers=headers,
        json=body,
        timeout=120,
    ) as response:
        response.raise_for_status()
        return parse_sse_events(response.iter_lines())


# -- Tool implementations --
def safe_path(p: str) -> Path:
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path

def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"
    try:
        r = subprocess.run(command, shell=True, cwd=WORKDIR,
                           capture_output=True, text=True, timeout=120)
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"

def run_read(path: str, limit: int = None) -> str:
    try:
        lines = safe_path(path).read_text().splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more)"]
        return "\n".join(lines)[:50000]
    except Exception as e:
        return f"Error: {e}"

def run_write(path: str, content: str) -> str:
    try:
        fp = safe_path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content)
        return f"Wrote {len(content)} bytes"
    except Exception as e:
        return f"Error: {e}"

def run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        fp = safe_path(path)
        content = fp.read_text()
        if old_text not in content:
            return f"Error: Text not found in {path}"
        fp.write_text(content.replace(old_text, new_text, 1))
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"


TOOL_HANDLERS = {
    "bash":       lambda **kw: run_bash(kw["command"]),
    "read_file":  lambda **kw: run_read(kw["path"], kw.get("limit")),
    "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
    "edit_file":  lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
    "todo":       lambda **kw: TODO.update(kw["items"]),
}

# Responses API 格式的工具定义
TOOLS = [ 
    {"type": "function", "name": "bash", "description": "Run a shell command.", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"], "additionalProperties": False}}, \
    {"type": "function", "name": "read_file", "description": "Read file contents.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["path"], "additionalProperties": False}}, \
    {"type": "function", "name": "write_file", "description": "Write content to file.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"], "additionalProperties": False}}, \
    {"type": "function", "name": "edit_file", "description": "Replace exact text in file.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"], "additionalProperties": False}}, \
    {"type": "function", "name": "todo", "description": "Update task list. Track progress on multi-step tasks.", "parameters": {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}, "text": {"type": "string"}, "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]}}, "required": ["id", "text", "status"]}}}, "required": ["items"], "additionalProperties": False}} \
]


# -- Agent loop with Responses API --
def agent_loop(messages: list):
    response_input = build_user_input(messages)
    rounds_since_todo = 0
    while True:
        try:
            response = request_stream_completion(response_input)
        except Exception as e:
            error_message = f"Error: model request failed: {e}"
            messages.append({"role": "assistant", "content": error_message})
            return False
        if hasattr(response, "choices"):
            assistant_message = response.choices[0].message
            assistant_message_dict = normalize_message(assistant_message)
            messages.append(assistant_message_dict)
            finish_reason = response.choices[0].finish_reason
            if finish_reason != "tool_calls":
                return False

            results = []
            used_todo = False
            tool_calls = getattr(assistant_message, "tool_calls", None) or []
            for tool_call in tool_calls:
                try:
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)
                    handler = TOOL_HANDLERS.get(tool_name)
                    output = handler(**tool_args) if handler else f"Unknown tool: {tool_name}"
                except Exception as e:
                    tool_name = getattr(tool_call.function, "name", "unknown")
                    tool_args = {}
                    output = f"Error: {e}"
                log_tool_event(tool_name, tool_args, str(output))
                results.append({"role": "tool", "tool_call_id": tool_call.id, "content": str(output)})
                if tool_name == "todo":
                    used_todo = True
            rounds_since_todo = 0 if used_todo else rounds_since_todo + 1
            if rounds_since_todo >= 3:
                results.insert(0, {"role": "user", "content": "<reminder>Update your todos.</reminder>"})
            messages.extend(results)
            continue

        normalized = normalize_response(response)
        final_text = extract_response_text(normalized)
        if final_text:
            messages.append({"role": "assistant", "content": final_text})

        tool_calls = extract_function_calls(normalized)
        if not tool_calls:
            return bool(final_text)

        used_todo = False
        response_input.extend(normalized.get("output", []))
        for tool_call in tool_calls:
            tool_name = tool_call.get("name", "unknown")
            try:
                tool_args = json.loads(tool_call.get("arguments", "{}"))
                handler = TOOL_HANDLERS.get(tool_name)
                output = handler(**tool_args) if handler else f"Unknown tool: {tool_name}"
            except Exception as e:
                tool_args = {}
                output = f"Error: {e}"

            log_tool_event(tool_name, tool_args, str(output))
            response_input.append(build_tool_result_item(tool_call["call_id"], str(output)))
            if tool_name == "todo":
                used_todo = True

        rounds_since_todo = 0 if used_todo else rounds_since_todo + 1
        if rounds_since_todo >= 3:
            response_input.append(
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "<reminder>Update your todos.</reminder>"}],
                }
            )


def main():
    history = []
    while True:
        try:
            query = input("\033[36ms03 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit"):
            break
        if not query.strip():
            continue
        
        # 初始化消息（包含系统提示）
        history = [{"role": "system", "content": SYSTEM}]
        history.append({"role": "user", "content": query})
        
        streamed = agent_loop(history)
        if not streamed:
            for msg in reversed(history):
                if isinstance(msg, dict) and msg.get("role") == "assistant":
                    text = extract_text_content(msg)
                    if text:
                        print(text)
                        break
        print()


if __name__ == "__main__":
    main()
