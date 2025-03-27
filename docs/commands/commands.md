# PyEVIO Info Command: Quick Reference

## Basic Usage

The `info` command displays file metadata and record structure information for EVIO v6 files.

```bash
pyevio info <filename>
```

## Options

| Option | Description |
|--------|-------------|
| `--verbose`, `-v` | Enable verbose output |
| `--hexdump/--no-hexdump` | Show hex dump of file header (first 50 words) |
| `--full`, `-f` | Show all records without truncation |

## Examples

Basic file information:
```bash
pyevio info experiment.evio
```

Display with hex dump of header:
    ```bash
pyevio info experiment.evio --hexdump
```

Show all records (no truncation):
```bash
pyevio info experiment.evio --full
```

## Output Explanation

The command displays:

1. **File Header Table**: Magic number, version, endianness, record count, etc.
2. **Record Information Table**: Lists records with their offsets, length, event count, and type
3. **Summary Statistics**: Total records, total events, and file size

By default, only the first 10 and last 5 records are shown unless `--full` is specified.

## Tips

- Use `--hexdump` to inspect the raw header bytes for debugging
    - When examining large files, use `--full` to see information about all records
- The offsets are displayed in both hex and as word offsets for convenience