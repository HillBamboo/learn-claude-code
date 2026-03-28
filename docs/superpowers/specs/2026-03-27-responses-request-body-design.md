# Responses Request Body Design

## Goal

Update `mine/s0.py` so the HTTP request sent to `/responses` includes:

- `instructions`, populated from `SYSTEM`
- `tools`, populated from `TOOLS`
- `input` as a message array instead of a plain string

Keep the existing streaming output behavior unchanged.

## Scope

In scope:

- Add a small request-body builder in `mine/s0.py`
- Route `stream_response()` through that builder
- Update tests in `mine/test_s0.py` to validate the new request shape

Out of scope:

- Changing SSE parsing behavior
- Changing error handling behavior
- Adding tool execution to the local client loop
- Refactoring unrelated constants or runtime flow

## Recommended Approach

Use a dedicated `build_response_body()` helper.

This keeps request-shape logic isolated from transport and stream parsing. The helper should return a dict with:

- `model`
- `instructions`
- `input`
- `tools`
- `stream`

`stream_response()` should call `build_response_body()` and pass the returned dict as the `body` argument to `client.post()`.

## Request Shape

The body should be:

```python
{
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

## Component Responsibilities

### `build_response_body()`

- Owns all `/responses` body construction
- Reads from existing module constants
- Returns a plain Python dict

### `stream_response()`

- Sends the request to `/responses`
- Keeps the current request headers
- Keeps the current SSE event loop and output printing logic
- Does not inline body construction details

## Error Handling

No functional changes.

The existing `APIStatusError` handling remains in place:

- print `status_code`
- print response text when present
- re-raise

## Testing Strategy

Update `mine/test_s0.py` to assert the new body shape in the existing request-shape test:

- `instructions == s0.SYSTEM`
- `tools == s0.TOOLS`
- `input` is a message array with one user message
- the user message content contains one `input_text` item using `s0.PROMPT`

Add a direct unit test for `build_response_body()` so request-shape failures can be diagnosed without going through streaming behavior.

## Risks

- The upstream API may reject malformed message content if `input` is encoded incorrectly
- A test that asserts the full body too rigidly could become noisy if harmless metadata is added later

Mitigation:

- Keep the helper small and deterministic
- Assert the critical body structure explicitly

## Verification Plan

After implementation:

1. Run `python -m unittest mine/test_s0.py`
2. Confirm the updated request-shape assertions pass
3. Avoid claiming success without test output
