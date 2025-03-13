#!/usr/bin/env python
"""
A simple EVIO v6 stream parser example.

This script reads an EVIO file (version 6), parses its file header and then
each record header. For each record the code:
  1. Reads the 14-word record header.
  2. Reads the index array (if any) that lists the byte lengths of each event.
  3. Reads the user header (if any).
  4. Reads the remaining record data containing the events.
  5. Uses the index array to slice out each event’s data and prints a summary.

In EVIO v6 (the CODA streaming format), the record’s “index array” tells you
the exact byte lengths for each event (bank). You must use that array rather than
naively reading a “length word” from the event data.

This example uses big-endian unpacking.
"""

import sys
import struct


def parse_file_header(f):
    # EVIO file header is 14 32-bit words = 56 bytes.
    header_bytes = f.read(56)
    if len(header_bytes) < 56:
        print("Error: incomplete file header")
        sys.exit(1)
    # Unpack 14 unsigned ints (big-endian)
    header = struct.unpack(">14I", header_bytes)
    return header


def print_file_header(header):
    file_magic = header[0]
    # The version is in word 5 (lowest 8 bits)
    version = header[5] & 0xFF
    record_count = header[3]
    index_array_len = header[4]
    user_header_len = header[6]
    print("=== File Header ===")
    print(f"  file_magic = {hex(file_magic)} (should be 0x4556494f = 'EVIO')")
    print(f"  version    = {version}")
    print(f"  record_count = {record_count}")
    print(f"  index_array_len (file) = {index_array_len} bytes")
    print(f"  user_header_len (file) = {user_header_len} bytes")
    print()


def parse_record_header(f):
    # Each record header is 14 words (56 bytes)
    data = f.read(56)
    if len(data) < 56:
        return None
    header = struct.unpack(">14I", data)
    return header


def print_record_header(header):
    # Unpack the header fields (indices are zero based)
    record_length_words = header[0]
    record_number = header[1]
    header_length = header[2]
    event_count = header[3]
    index_array_len = header[4]  # in bytes
    # word5 holds bit info and version; lowest 8 bits is version
    version = header[5] & 0xFF
    user_header_len = header[6]  # in bytes
    magic = header[7]
    print(f"=== Record {record_number} ===")
    print(f"  length in words   = {record_length_words}")
    print(f"  record_number     = {record_number}")
    print(f"  header_length     = {header_length}")
    print(f"  event_count       = {event_count}")
    print(f"  index_array_len   = {index_array_len} bytes")
    print(f"  user_header_len   = {user_header_len} bytes")
    print(f"  version           = {version}")
    print(f"  magic             = {hex(magic)}")


def parse_record(f):
    """
    Parse one record from file f.
    Returns a dictionary containing header info and a list of event data bytes.
    """
    header = parse_record_header(f)
    if header is None:
        return None

    rec = {}
    rec["record_length_words"] = header[0]
    rec["record_number"] = header[1]
    rec["header_length"] = header[2]
    rec["event_count"] = header[3]
    rec["index_array_len"] = header[4]   # bytes
    rec["bit_info_version"] = header[5]    # lower 8 bits is version
    rec["user_header_len"] = header[6]     # bytes
    rec["magic"] = header[7]

    # Print record header summary
    print_record_header(header)

    # Read the index array. It should be an array of (event_count) 32-bit integers.
    index_array = []
    if rec["index_array_len"] > 0:
        index_data = f.read(rec["index_array_len"])
        if len(index_data) != rec["index_array_len"]:
            print("Warning: incomplete index array")
        # Each event length is 4 bytes.
        for i in range(0, rec["index_array_len"], 4):
            (evlen,) = struct.unpack(">I", index_data[i:i+4])
            index_array.append(evlen)
    else:
        print("  No index array found!")
    rec["index_array"] = index_array

    # Read the user header (if any)
    if rec["user_header_len"] > 0:
        user_header = f.read(rec["user_header_len"])
    else:
        user_header = b""
    rec["user_header"] = user_header

    # Now determine how many bytes remain for event data.
    total_record_bytes = rec["record_length_words"] * 4
    header_total_bytes = rec["header_length"] * 4 + rec["index_array_len"] + rec["user_header_len"]
    data_bytes = total_record_bytes - header_total_bytes
    rec["data_bytes"] = data_bytes

    # Read the event data block.
    event_data = f.read(data_bytes)
    if len(event_data) != data_bytes:
        print("Warning: record event data truncated")
    rec["event_data"] = event_data

    # Now use the index array to extract individual events.
    events = []
    offset = 0
    for i, evlen in enumerate(index_array):
        if offset + evlen > len(event_data):
            print(f"  Event {i+1}: event length ({evlen} bytes) exceeds available data. Stopping.")
            break
        ev = event_data[offset:offset+evlen]
        events.append(ev)
        print(f"  Event {i+1}: length = {evlen} bytes")
        offset += evlen

    rec["events"] = events

    # If there are extra bytes (or not enough events), you might want to warn.
    if offset != len(event_data):
        print(f"  Note: parsed event data length {offset} does not equal expected {len(event_data)}")
    print()

    return rec


def main():
    if len(sys.argv) < 2:
        print("Usage: python stream_parser.py <evio_file>")
        sys.exit(1)
    filename = sys.argv[1]
    try:
        with open(filename, "rb") as f:
            file_header = parse_file_header(f)
            print_file_header(file_header)

            rec_count = 0
            while True:
                pos = f.tell()
                rec = parse_record(f)
                if rec is None:
                    break
                rec_count += 1
            print(f"Reached EOF after parsing {rec_count} records.")
    except Exception as e:
        print(f"Error reading file: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
