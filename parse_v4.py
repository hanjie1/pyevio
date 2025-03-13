#!/usr/bin/env python3

import struct
import sys

def parse_evio_v4_blocks(filename):
    """
    Generator that reads a standard EVIO v4 file block by block, event by event.
    Yields (block_index, event_index_in_block, event_data).
    """
    with open(filename, "rb") as f:
        block_index = 0

        while True:
            # 1) Read 8-word block header (each word = 4 bytes)
            block_header_bytes = f.read(8 * 4)
            if len(block_header_bytes) < 8 * 4:
                # Reached EOF or partial
                break

            # Parse big-endian:
            header_words = struct.unpack(">8I", block_header_bytes)

            block_length   = header_words[0]  # total words in this block (including header)
            block_number   = header_words[1]
            header_length  = header_words[2]  # should be 8 for EVIO v4
            event_count    = header_words[3]
            reserved1      = header_words[4]
            bit_info       = header_words[5]
            reserved2      = header_words[6]
            magic          = header_words[7]  # should be 0xc0da0100

            # Sanity checks:
            if magic != 0xc0da0100:
                print(f"Warning: block magic 0x{magic:08X} != 0xc0da0100 at block {block_index+1}.")
                break
            if header_length != 8:
                print(f"Warning: header_length={header_length}, expected 8 (EVIOv4). Possibly corrupted or streaming file.")
                break

            block_index += 1
            # The block length is in 32-bit words. We already read 8 words for the header,
            # so the block has (block_length - 8) more words to read for events + block trailer.

            block_data_bytes = (block_length - 8) * 4
            block_data = f.read(block_data_bytes)
            if len(block_data) < block_data_bytes:
                print("Warning: incomplete block read near EOF.")
                break

            # 2) Now we have the entire block after the 8-word header in 'block_data'.
            #    We must parse out 'event_count' events from that chunk.
            #    In EVIO v4, each event starts with a 32-bit 'event length' word, then that many words follow.

            offset = 0
            event_in_block = 0
            for evt_i in range(event_count):
                if offset + 4 > len(block_data):
                    print("Warning: ran out of block data before reading all events.")
                    break

                event_len_words = struct.unpack(">I", block_data[offset:offset+4])[0]
                event_total_bytes = event_len_words * 4
                if offset + event_total_bytes > len(block_data):
                    print("Warning: event extends beyond block data size.")
                    break

                event_data = block_data[offset : offset + event_total_bytes]
                event_in_block += 1
                yield (block_index, event_in_block, event_data)
                offset += event_total_bytes

            # If there is any leftover data in the block after these events,
            # typically that's the block trailer in EVIO v4. It's common to just skip it
            # or it may be 0. Usually event_count * event_size sums up to block_length-8.


def parse_evio_event_banks(event_data):
    """
    Parse top-level banks in one EVIO event (big-endian).
    Return a list of banks:
       Each bank has: { 'tag':..., 'data_type':..., 'length_words':..., 'raw_data':... }
    """
    # 1) The first 32-bit word is the event length in words
    event_len_words = struct.unpack(">I", event_data[:4])[0]
    total_bytes = event_len_words * 4

    # We'll parse banks after the first word
    banks = []
    offset = 4
    while offset + 4 <= total_bytes:
        header_word = struct.unpack(">I", event_data[offset:offset+4])[0]
        length_minus1 = (header_word >> 16) & 0xFFFF
        data_type     = (header_word >> 8) & 0xFF
        tag           = (header_word & 0xFF)

        num_words = length_minus1 + 1
        bank_size_bytes = num_words * 4
        if offset + bank_size_bytes > total_bytes:
            break

        payload_offset = offset + 4
        payload_len_bytes = bank_size_bytes - 4
        raw_data = event_data[payload_offset : payload_offset + payload_len_bytes]

        bdict = {
            "tag": tag,
            "data_type": data_type,
            "length_words": num_words,
            "raw_data": raw_data
        }
        banks.append(bdict)
        offset += bank_size_bytes

    return banks


def main(filename):
    block_count = 0
    event_count_global = 0

    for (block_index, event_in_block, event_data) in parse_evio_v4_blocks(filename):
        block_count = max(block_count, block_index)
        event_count_global += 1
        print(f"\nBlock {block_index}, event {event_in_block} (global event {event_count_global})")
        print(f"  Event size: {len(event_data)} bytes")

        # Parse top-level banks in this event:
        banks = parse_evio_event_banks(event_data)
        for b in banks:
            print(f"    Bank: tag=0x{b['tag']:02X}, data_type=0x{b['data_type']:02X}, length_words={b['length_words']}")

    print(f"\nFinished. Read {block_count} blocks, {event_count_global} total events.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <filename>")
        sys.exit(1)

    main(sys.argv[1])
