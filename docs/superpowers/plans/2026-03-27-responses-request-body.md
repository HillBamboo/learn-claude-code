# Responses Request Body Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update `mine/s0.py` so `/responses` requests include `instructions`, `tools`, and a message-array `input`, while preserving existing streaming behavior.

**Architecture:** Keep request-body construction separate from transport and stream parsing by adding a focused helper in `mine/s0.py`. Update tests first so the request contract is explicit, then implement the minimal body-builder and route `stream_response()` through it.

**Tech Stack:** Python, `unittest`, OpenAI Python client, `httpx`

---

## File Structure

- Modify: `mine/s0.py`
  - Add `build_response_body()` to centralize request-body construction.
  - Update `stream_response()` to call the helper instead of inlining the request body.
- Modify: `mine/test_s0.py`
  - Update the existing request-shape test to assert `instructions`, `tools`, and message-array `input`.
  - Add a focused unit test for `build_response_body()`.

### Task 1: Lock down the new request contract in tests

**Files:**
- Modify: `mine/test_s0.py`
- Test: `mine/test_s0.py`

- [ ] **Step 1: Write the failing test for `build_response_body()`**

```python
    def test_build_response_body_includes_instructions_tools_and_message_input(self):
        self.assertEqual(
            s0.build_response_body(),
            {
                "model": s0.MODEL,
                "instructions": s0.SYSTEM,
                "input": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": s0.PROMPT,
                            }
                        ],
                    }
                ],
                "tools": s0.TOOLS,
                "stream": True,
            },
        )
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python -m unittest mine.test_s0.StreamResponseTests.test_build_response_body_includes_instructions_tools_and_message_input -v`

Expected: `ERROR` because `build_response_body` does not exist yet.

- [ ] **Step 3: Update the request-shape streaming test to require the new body**

```python
                        "body": {
                            "model": s0.MODEL,
                            "instructions": s0.SYSTEM,
                            "input": [
                                {
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "input_text",
                                            "text": s0.PROMPT,
                                        }
                                    ],
                                }
                            ],
                            "tools": s0.TOOLS,
                            "stream": True,
                        },
```

- [ ] **Step 4: Run the streaming request-shape test to verify it fails**

Run: `python -m unittest mine.test_s0.StreamResponseTests.test_stream_response_posts_exact_request_shape -v`

Expected: `FAIL` because `stream_response()` still posts the old body.

- [ ] **Step 5: Commit the test-only change**

```bash
git add mine/test_s0.py
git commit -m "test: define responses request body contract"
```

### Task 2: Implement the request-body builder

**Files:**
- Modify: `mine/s0.py`
- Test: `mine/test_s0.py`

- [ ] **Step 1: Add the minimal `build_response_body()` implementation**

```python
def build_response_body() -> dict:
    return {
        "model": MODEL,
        "instructions": SYSTEM,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": PROMPT,
                    }
                ],
            }
        ],
        "tools": TOOLS,
        "stream": True,
    }
```

- [ ] **Step 2: Update `stream_response()` to use the helper**

```python
            body=build_response_body(),
```

- [ ] **Step 3: Run the focused builder test**

Run: `python -m unittest mine.test_s0.StreamResponseTests.test_build_response_body_includes_instructions_tools_and_message_input -v`

Expected: `ok`

- [ ] **Step 4: Run the streaming request-shape test**

Run: `python -m unittest mine.test_s0.StreamResponseTests.test_stream_response_posts_exact_request_shape -v`

Expected: `ok`

- [ ] **Step 5: Commit the implementation change**

```bash
git add mine/s0.py mine/test_s0.py
git commit -m "feat: send instructions and tools in responses request"
```

### Task 3: Verify the final behavior

**Files:**
- Modify: none
- Test: `mine/test_s0.py`

- [ ] **Step 1: Run the full target test file**

Run: `python -m unittest mine/test_s0.py -v`

Expected: all tests pass.

- [ ] **Step 2: Inspect the diff for scope control**

Run: `git diff -- mine/s0.py mine/test_s0.py docs/superpowers/plans/2026-03-27-responses-request-body.md`

Expected: only the request-body helper, request-body call site, and related tests appear.

- [ ] **Step 3: Record completion status**

```bash
git status --short
```

Expected: only intended modified files are listed, with no accidental unrelated edits from this task.
