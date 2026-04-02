---
name: save-chat-history
description: "Save the current conversation to docs/llm-chat-history/. Use when the user asks to save, archive, or record the current chat, conversation history, or session notes. Creates a dated markdown file with only user questions and assistant answers, stripping thinking steps, code reads, and command outputs."
argument-hint: "Brief English description of what was done, e.g. implement-album-page"
---

# Save Chat History

Saves the current conversation as a cleaned-up markdown file under `docs/llm-chat-history/`.

## When to Use

- User asks to save or archive the current conversation
- User wants to record what was discussed or implemented in this session
- Invoked via `/save-chat-history <description>`

## Procedure

### Step 1 – Determine the filename

1. Get today's date in `YYYYMMdd` format (e.g. `20260402`).
2. List existing files in `docs/llm-chat-history/` that start with today's date prefix.
3. Count how many already exist → the new file's sequence number = count + 1.
4. Use the argument provided by the user as the English description slug (kebab-case). If no argument was given, infer a short English description from the conversation topic.
5. Compose the filename: `{YYYYMMdd}-{seq}-{description}.md`  
   Example: `20260402-1-implement-album-page.md`

### Step 2 – Compose the file content

Write the file using this structure:

```
# {Short title describing the session topic}

> Saved: {YYYY-MM-DD}

{For each exchange in the conversation:}

## {User's question or request, verbatim or lightly paraphrased}

{Assistant's answer — keep the final written answer only.}
{Strip: <think>…</think> blocks, inline code the assistant read but didn't explain, raw command output listings, intermediate search results.}
{Keep: explanations, decisions made, code snippets the assistant wrote or explained, summaries.}
```

Rules for cleaning assistant responses:
- **Remove**: tool call results (file reads, grep output, build logs, terminal output dumps)
- **Remove**: "Let me check…", "I'll look at…", "Reading file…" filler sentences
- **Keep**: the substance — what was decided, written, or explained
- **Keep**: code blocks that the assistant wrote as part of the answer
- If an assistant turn was purely mechanical (e.g., only ran a search with no narrative), omit it entirely

### Step 3 – Write the file

Create the file at `docs/llm-chat-history/{filename}` with the composed content.

Confirm the file path to the user when done.
