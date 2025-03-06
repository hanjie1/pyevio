# pyevio
Yet another Jefferson Lab EVIO introspect tool. LLM bless this effort!

# **pyevio – Developer Specification**

## **1. Overview**

**pyevio** is a pure Python library and CLI tool for reading and inspecting **EVIO** (Event Input/Output) files. EVIO is a format developed at Jefferson Lab for storing event-based data with possible compression. The goal is to make a user-friendly, pip-installable Python package that can:

1. Stream and parse EVIO **v4** and **v6** files.
2. Handle **compressed v6** records (LZ4, gzip).
3. Expose an **in-memory object model** of EVIO structures (banks, segments, tagsegments) at runtime.
4. Provide a **command-line tool** (`pyevio`) that:
    - Prints general file info (event count, dictionary presence, etc.).
    - Dumps a single event’s structure in a human-readable format.
    - Optionally dumps raw data in hex/decimal form if requested.
5. Handle any embedded **EVIO dictionary** or **first event**, displaying them in a summarized or user-friendly way.

---

## **2. Requirements**

1. **Language & Compatibility**
    - Python **3.9+**.
    - Must install cleanly via `pip install pyevio`.

2. **Dependencies**
    - **`click`** for CLI.
    - **`lz4`** for LZ4 decompression of EVIO v6 records.
    - Built-in **`zlib/gzip`** for gzip decompression.
    - Built-in **`xml.etree.ElementTree`** for XML dictionary parsing.
    - **VitePress** (or standard Node-based tooling) for docs (not installed via Python dependencies—used separately in `docs/`).
    - **`pytest`** for unit testing (dev dependency).

3. **File Size Constraints**
    - Files can be **very large** (GBs to 100s of GBs). The library must **stream** records from disk (not load entire file).

4. **CLI Usage**
    - `pyevio FILE` → Summarize file (event count, dictionary presence, first event presence, etc.).
    - `pyevio FILE EVENT_NUMBER` → Sequentially read events until EVENT_NUMBER is reached, then dump structure.
    - `pyevio FILE [options]` → Additional flags, e.g. `--verbose` / `--show-data` to dump raw payloads.

5. **Functionality Scope**
    - V4 & V6 reading (including **LZ4** and **gzip** compression).
    - Minimal “fADC 250” recognition: identify presence by tag or known pattern, no deep decoding in v1 (only note it’s an fADC 250 block).
    - Summaries of dictionary data.
    - Summaries of each event’s or each structure’s header (tag, length, num, type), with raw data stored but *not* fully parsed or auto-decoded.

---

## **3. Architecture & Package Layout**

A recommended directory structure:

```
pyevio/
  __init__.py           # May contain version, top-level imports
  cli.py                # click-based CLI
  parser.py             # streaming logic, file record reading, decompression
  structures.py         # EvioBank, EvioSegment, EvioTagSegment
  utils.py              # optional: small helpers (byte swaps, logging, etc.)

tests/
  test_parser.py
  test_cli.py
  ...any additional test_*.py

docs/                   # For VitePress-based doc site
  .vitepress/
  index.md
  ...other .md

pyproject.toml          # Modern build system config + dependencies
```

### **3.1 Modules**

1. **`pyevio.parser`**
    - Implements core EVIO streaming:
        - **`read_file_header`** / `read_record_header` functions for v6.
        - **`read_block_header_v4`** for v4.
        - Decompression logic (using `lz4` or `zlib`).
        - Iterating events within each record.
    - Provides an API like `parse_file(filename) → generator of EvioEventInfo`, or a context manager that yields events.

2. **`pyevio.structures`**
    - `EvioBank`, `EvioSegment`, `EvioTagSegment` classes.
    - Each has fields for `tag`, `num`, `type`, `length`, `children`, etc.
    - Leaf structures hold a **raw payload** (`bytes`), *not* automatically decoded.
    - Might provide helper methods for partial decoding if needed.

3. **`pyevio.cli`**
    - Uses `click` to define the `pyevio` command-line interface.
    - Commands:
        1. **Default** (`pyevio file`) → print file-level summary.
        2. **`pyevio file event_number`** → parse sequentially until event N, display structure.
        3. **Options** like `--verbose` / `--show-data` / `--help`.

4. **`pyevio.utils`** (optional)
    - Byte-swap logic, small print-helpers, dictionary parsing, etc.

---

## **4. Data Handling**

1. **Streaming**
    - For v6, read the **file header** first, then read each **record** in turn.
    - If compressed, decompress with `lz4.frame` or `zlib`.
    - For v4, read **blocks**. Each block can have multiple events.
    - Maintain a counter of total events encountered so far.
    - Stop when we find the requested event or when file is exhausted.

2. **EVIO Structure Extraction**
    - For each event, parse from the first **bank** header (tag/num/type/length).
    - Recursively parse children if it’s a container type (`BANK`, `SEGMENT`, or `TAGSEGMENT`).
    - Store them as a tree of `EvioBank`/`EvioSegment`/`EvioTagSegment`.
        - Container → `children = [...]`.
        - Leaf → `raw_data = bytes(...)`.
    - Return that object tree for downstream usage.

3. **Dictionary Handling**
    - If the file’s first record (v6) or block (v4) includes a dictionary event (bit set in header or recognized as “dictionary bank”), parse the XML.
    - Use `xml.etree.ElementTree` to parse.
    - Summarize or store it for reference. Display it on user request.

4. **fADC 250**
    - If we see a bank whose **tag** matches known fADC 250 IDs (or some pattern), note that it’s an fADC 250 structure.
    - For now, no deep decoding. Just mention “fADC 250 data found” in the event summary.

---

## **5. CLI Behaviors**

### **5.1 Command: `pyevio file`**

1. **Read** the EVIO file’s initial headers.
2. **Print**:
    - EVIO version, compression info (if v6).
    - Total event count (if easily determined). Otherwise, just note we’ll parse on-demand.
    - Presence of dictionary or first event if discovered in the earliest record/block.
3. Possibly parse all events sequentially and print a short line for each event’s top-level bank, e.g.:
   ```
   Event #1: top bank tag=1, num=0
   Event #2: top bank tag=2, num=1
   ...
   ```
   or we can skip enumerating all events if the file is huge—**this is optional**.

### **5.2 Command: `pyevio file N`**

1. Parse sequentially from the start, counting events.
2. When event #N is reached, build the in-memory structure tree:
    - *If dictionary or first event are encountered earlier, store or note them, but skip them in the event count if they are not part of the normal numbering (as EVIO v4/v6 may do).*
3. Print a **structured dump**:
    - **Header**: tag, type, length (words), num/pad for banks, maybe a short “(container/leaf)”.
    - If container → print children’s headers (indented).
    - If leaf → mention “N raw bytes”.
    - If recognized as fADC 250 → print “(fADC 250 bank)”.
4. Stop parsing further.

### **5.3 Optional Flags**

- `--show-data` or `--verbose`:
    - If set, for leaf nodes, show a brief hex or decimal snippet (e.g., first 16 bytes) of the raw data.
- `--dict-xml`:
    - If set, print the dictionary’s XML in full if found.
- `--help`:
    - Standard usage message from `click`.

---

## **6. Error Handling**

1. **File Not Found / Permission Errors**
    - For CLI, catch `FileNotFoundError` or `PermissionError`. Print a user-friendly error and exit non-zero.
    - For library usage, raise a suitable Python exception.

2. **Corrupted Headers**
    - If any record or block header is invalid (e.g., magic number mismatch, negative length, etc.), we:
        - Print an error if using CLI or raise a custom `EvioFormatError` (or similar) in the library.
    - Stop parsing if corruption is fatal.

3. **Compressed Data Fails to Decompress**
    - If decompression raises an error from `lz4` or `zlib`, handle similarly—raise `EvioCompressionError` or log a warning and skip.

4. **Unsupported EVIO Versions**
    - If we detect a version other than 4 or 6, raise an `EvioVersionError`.

5. **Dictionary Parse Fail**
    - If the dictionary XML is malformed, log a warning or raise `EvioDictionaryError` but keep parsing events if possible.

---

## **7. Testing Plan**

1. **Testing Framework**:
    - Use **`pytest`** in the `tests/` directory.

2. **Unit Tests**:
    - **`test_parser.py`**:
        - Test parsing small mock EVIO v4 files (uncompressed).
        - Test parsing small mock EVIO v6 files (uncompressed and compressed with LZ4/gzip).
        - Verify that we correctly parse event counts, dictionary presence, and detect major fields.
    - **`test_cli.py`**:
        - Mock or use small test files to confirm CLI output lines up with expected structured dumps.
        - Check error messages for missing files or corruption.

3. **Integration Tests**:
    - Possibly have a few real small EVIO sample files from Jefferson Lab with known contents:
        - v4 with a dictionary
        - v6 uncompressed
        - v6 with LZ4
        - v6 with gzip
        - Some with a “first event”

4. **GitHub Actions**:
    - A `.github/workflows/test.yaml` to:
        - Install dependencies (`click`, `lz4`, `pytest`).
        - Run `pytest`.
        - Possibly build docs or run linter if desired.

---

## **8. Documentation & Release**

1. **Docstrings**
    - Each public class/function has a docstring in Markdown style, primarily for reference.

2. **VitePress** Docs
    - Keep top-level docs in `docs/` with a standard VitePress config.
    - Outline usage, examples, known issues.
    - Deployed via GitHub Actions to GitHub Pages.

3. **Publishing**
    - `pyproject.toml` includes `[project]` metadata and `[project.dependencies]` for `click` and `lz4`.
    - `pip install build; pip install twine` can be used to build and publish to PyPI.

---

## **9. Implementation Roadmap**

1. **Core Parser**
    - Implement `parse_v4_block` and `parse_v6_record`.
    - Decompression hooks for `lz4` or `zlib`.
    - Properly yield events in a streaming manner.

2. **Structure Classes**
    - `EvioBank`, `EvioSegment`, `EvioTagSegment` (inherit from a common base class if desired).
    - Store header fields and raw payload if leaf.

3. **CLI**
    - A single `click` group or command with sub-commands or argument-based behavior.
    - Summarize vs. dump event.
    - Add `--show-data` / `--verbose`.

4. **Dictionary Parsing**
    - Identify dictionary event, parse XML with `xml.etree.ElementTree`.
    - Optional user-friendly output.

5. **Testing**
    - Write and run unit tests using small example EVIO files.
    - Validate CLI behavior and parser correctness.

6. **Docs**
    - Add usage examples, references to EVIO format resources, and any known limitations.

---

## **10. Future Enhancements (Beyond v1)**

- **Random Access**: Optionally build an index of event offsets for large files.
- **Detailed Decoding**: e.g., interpret fADC 250 data or other JLab-specific hardware formats.
- **Performance Optimizations**: e.g., partial read caching or concurrent decompression.
- **Extended CLI**: more commands or interactive console using `textual`/`rich`.

