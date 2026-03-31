# S3 Native SSE Streaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update `mine/s3.py` so assistant text streams to stdout via native `/responses` SSE while tool logs continue printing immediately and conversation history still captures the final assistant message.

**Architecture:** Keep `agent_loop()` in place and replace the request layer with a focused SSE request/parser path. Parse text delta events for live terminal output, return the final `response.completed` payload for the existing tool loop, and keep tests narrow by mocking the stream transport.

**Tech Stack:** Python, `httpx`, `unittest`, `unittest.mock`

---

## File Structure

- Modify: `mine/s3.py`
  - Add a native SSE request helper and event parser.
  - Route `agent_loop()` through the streaming helper.
  - Avoid duplicate final-answer printing in the CLI entrypoint.
- Modify: `mine/test_s3.py`
  - Add a focused test for SSE delta parsing and stdout printing.
  - Update loop tests to patch the new streaming request helper.

### Task 1: Lock down SSE behavior in tests

**Files:**
- Modify: `mine/test_s3.py`
- Test: `mine/test_s3.py`

- [ ] **Step 1: Write a failing parser test for streamed text deltas**
- [ ] **Step 2: Run the focused test and confirm it fails for missing SSE support**
- [ ] **Step 3: Update agent loop tests to use the new streaming request seam**

### Task 2: Implement native SSE parsing

**Files:**
- Modify: `mine/s3.py`
- Test: `mine/test_s3.py`

- [ ] **Step 1: Add a helper that parses SSE events and prints `response.output_text.delta` chunks**
- [ ] **Step 2: Add a request helper that posts to `/responses` with `"stream": true`**
- [ ] **Step 3: Route `agent_loop()` through the new streaming helper and keep tool execution unchanged**
- [ ] **Step 4: Restore tool result logging**

### Task 3: Verify behavior

**Files:**
- Modify: none
- Test: `mine/test_s3.py`

- [ ] **Step 1: Run the focused streaming test**
- [ ] **Step 2: Run `mine/test_s3.py` end to end**
