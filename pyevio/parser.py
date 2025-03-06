"""
parser.py -- Basic, partial EVIO v4 parsing for demonstration.

In EVIO v4 format, each file is composed of blocks:
  - Each block has an 8-word (32-bit ints) header.
  - Each block can contain multiple events, but each event is wholly contained (no cross-block splitting).
  - The header layout in words is:
       0) block length in ints
       1) block number
       2) header length (8)
       3) event count in this block
       4) reserved1
       5) bit info + version (lowest 8 bits = version, e.g. 4)
       6) reserved2
       7) magic number = 0xc0da0100
"""

import struct
from collections import namedtuple


# Named tuple for holding minimal block header data
BlockHeaderV4 = namedtuple("BlockHeaderV4", [
    "block_length",     # total words in block
    "block_number",
    "header_length",    # always 8 for v4
    "event_count",
    "bitinfo_version",  # bits plus version in lowest 8 bits
    "magic",
])


def read_block_header_v4(file_obj, debug=False):
    """
    Read 8 words (32-bit ints) from file_obj as an EVIO v4 block header.
    Returns a `BlockHeaderV4` named tuple. Raises EOFError if we cannot
    read enough bytes.

    If debug=True, print out raw hex values from the first 8 words
    so we can see endianness or unexpected format.
    """
    header_bytes = file_obj.read(32)
    if len(header_bytes) < 32:
        raise EOFError("Not enough bytes to read a full v4 block header")

    if debug:
        print("== Debug: Raw 8 words in hex (as read) ==")
        for i in range(8):
            # show each 4-byte chunk in hex
            chunk = header_bytes[4*i : 4*(i+1)]
            # convert chunk to a 32-bit integer in LE vs. BE for printing?
            # Let's just interpret chunk as raw big-endian first:
            val_BE = int.from_bytes(chunk, byteorder='big')
            # and as little-endian:
            val_LE = int.from_bytes(chunk, byteorder='little')
            print(f" Word {i}: chunk={chunk.hex()}  BE=0x{val_BE:x}  LE=0x{val_LE:x}")

    # interpret them in local-endian for actual code:
    data = struct.unpack("=8I", header_bytes)
    block_length     = data[0]
    block_number     = data[1]
    header_length    = data[2]
    event_count      = data[3]
    bitinfo_version  = data[5]
    magic            = data[7]

    return BlockHeaderV4(
        block_length, block_number, header_length,
        event_count, bitinfo_version, magic
    )



def parse_v4_block(file_obj):
    """
    Reads a single v4 block from file_obj (including its header),
    parses all events, returns a list of raw event bytes.

    If the header indicates 0 events, returns empty list.

    Raises:
      EOFError if block header cannot be read
      ValueError if block format is invalid
    """
    block_header = read_block_header_v4(file_obj, True)

    # Validate magic number for v4
    if block_header.magic != 0xc0da0100:
        raise ValueError(f"Invalid magic 0x{block_header.magic:x} (expected 0xc0da0100)")

    # If the header length isn't 8, we have a mismatch from standard v4
    if block_header.header_length != 8:
        raise ValueError(f"Header length {block_header.header_length} != 8, not standard v4?")

    # The entire block = block_length * 4 bytes
    # But we already read 32 bytes (the header).
    bytes_remaining = (block_header.block_length - block_header.header_length) * 4

    # read the rest of the block
    block_data = file_obj.read(bytes_remaining)
    if len(block_data) < bytes_remaining:
        raise EOFError("Not enough data to read entire v4 block")

    # We'll parse event by event from block_data
    # We know event_count from the header. Each event is 'bank-len+1' words, but we must parse them in sequence.
    events = []
    offset = 0
    for _ in range(block_header.event_count):
        # at least first 4 bytes is "bank length"
        if offset + 4 > len(block_data):
            raise ValueError("Block data ends unexpectedly while reading event length")

        # read the first 4 bytes to get the event length in words
        # interpret as 32-bit int, again system-endian for simplicity
        bank_len = struct.unpack_from("=I", block_data, offset)[0]
        event_words = bank_len + 1  # event includes the bank header itself
        event_bytes = event_words * 4

        if offset + event_bytes > len(block_data):
            raise ValueError("Block data ends unexpectedly for full event read")

        # extract the raw bytes of this event
        event_raw = block_data[offset : offset + event_bytes]
        events.append(event_raw)

        offset += event_bytes

    return events


def parse_file(filename):
    """
    Detects if file is v4 (by reading first 8 words).
    Reads all blocks, accumulates all events in a list and returns it.
    For demonstration only – no partial reading or v6 handling yet.
    """
    all_events = []

    with open(filename, "rb") as f:
        while True:
            try:
                # parse one block
                block_events = parse_v4_block(f)
                # add to our big list
                all_events.extend(block_events)

                # Check if we should stop if we see "last block" bit?
                # v4 "last block" bit is 10th bit (value 0x200) in word #5 of header.
                # Let's check it:
                # => block_header.bitinfo_version & 0x200 => if nonzero => last block
                # For now, we do not implement that – let's just keep reading
                if len(block_events) == 0:
                    # If a block says it has 0 events, maybe it's the last block?
                    # We'll treat that as the end
                    break

            except EOFError:
                # done reading file
                break

    return all_events
