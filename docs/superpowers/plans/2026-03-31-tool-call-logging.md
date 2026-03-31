# Tool Call Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update `mine/s3.py` so tool execution prints the tool name, arguments, and tool result to stdout without changing conversation history.

**Architecture:** Add a small logging helper in `mine/s3.py` and call it at the two existing tool-execution sites inside `agent_loop()`. Lock the behavior down with a focused unit test in `mine/test_s3.py` before implementing the helper.

**Tech Stack:** Python, `unittest`, `unittest.mock`

---

## File Structure

- Modify: `mine/s3.py`
  - Add a focused helper for stdout tool logging.
  - Call the helper in both the chat-completions and Responses API tool execution loops.
- Modify: `mine/test_s3.py`
  - Add a test that asserts tool name/args and tool result are printed to stdout.

### Task 1: Define stdout logging behavior in tests

**Files:**
- Modify: `mine/test_s3.py`
- Test: `mine/test_s3.py`

- [ ] **Step 1: Write a failing test for tool logging**

```python
    def test_agent_loop_prints_tool_name_and_result(self):
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
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python -m unittest mine.test_s3.AgentLoopPromptTests.test_agent_loop_prints_tool_name_and_result -v`
Expected: `FAIL` because no tool logging is printed yet.

### Task 2: Implement lightweight stdout logging

**Files:**
- Modify: `mine/s3.py`
- Test: `mine/test_s3.py`

- [ ] **Step 1: Add a minimal helper to format tool name, arguments, and result**

```python
def log_tool_event(tool_name: str, tool_args: dict, output: str) -> None:
    print(f"[tool] {tool_name} {json.dumps(tool_args, ensure_ascii=False)}")
    print(f"[result] {output}")
```

- [ ] **Step 2: Call the helper in both tool execution branches inside `agent_loop()`**

```python
                log_tool_event(tool_name, tool_args, str(output))
```

- [ ] **Step 3: Re-run the focused test**

Run: `python -m unittest mine.test_s3.AgentLoopPromptTests.test_agent_loop_prints_tool_name_and_result -v`
Expected: `ok`

### Task 3: Verify regression safety

**Files:**
- Modify: none
- Test: `mine/test_s3.py`

- [ ] **Step 1: Run the full target test file**

Run: `python -m unittest mine/test_s3.py -v`
Expected: all tests pass.
