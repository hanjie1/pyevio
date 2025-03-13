#!/usr/bin/env python3
import struct
import sys
import matplotlib.pyplot as plt

def read_coda_stream_file(filename):
    """
    Reads CODA 3.11 streaming-mode file, skipping 14-word block header,
    yields each event's bytes.
    """
    with open(filename, "rb") as f:
        # Skip 14-word block header
        f.seek(14 * 4, 0)

        while True:
            header = f.read(4)
            if len(header) < 4:
                break

            event_len_words = struct.unpack(">I", header)[0]
            if event_len_words < 1:
                break

            body = f.read((event_len_words - 1) * 4)
            if len(body) < (event_len_words - 1) * 4:
                break

            yield header + body

def parse_top_level_banks(event_data):
    """
    Minimal parse of top-level banks in an EVIO event. Not recursing fully,
    just to identify banks with data_type=0x01 or 0x00, etc.
    """
    event_len_words = struct.unpack(">I", event_data[:4])[0]
    total_bytes = event_len_words * 4
    offset = 4
    banks = []

    while offset + 4 <= total_bytes:
        header_word = struct.unpack(">I", event_data[offset:offset+4])[0]
        length_minus1 = (header_word >> 16) & 0xFFFF
        data_type     = (header_word >> 8)  & 0xFF
        tag           =  header_word        & 0xFF

        num_words = length_minus1 + 1
        bank_size = num_words * 4
        if offset + bank_size > total_bytes:
            break

        payload_offset = offset + 4
        payload_bytes = bank_size - 4
        raw_data = event_data[payload_offset:payload_offset+payload_bytes]

        banks.append({
            "tag": tag,
            "data_type": data_type,
            "length_words": num_words,
            "raw_data": raw_data
        })

        offset += bank_size

    return banks

def decode_32bit_array(raw_data):
    """
    Decode the raw bytes as big-endian 32-bit unsigned ints
    """
    n = len(raw_data)//4
    return list(struct.unpack(">" + "I"*n, raw_data))

def analyze_big_int_array(int_array):
    """
    Example function that tries to spot patterns in the big 32-bit array.
    For instance:
      - Check the first few words
      - Search for repeating 'headers'
      - Attempt to parse as FADC frames
    """
    print(f"Analyzing large array of {len(int_array)} 32-bit words...")

    if not int_array:
        return

    # 1. Print first 20 words (hex) to see if there's a recognizable pattern
    print("First 20 words (hex):")
    for i, val in enumerate(int_array[:20]):
        print(f"  [{i:2d}]: 0x{val:08X}")

    # 2. Look for repeated 'header' patterns
    #    For example, a word might have a 'magic' bit or 'slot' that occurs every so often.
    #    We'll do a naive approach: check if any 0xFFxx0100 patterns appear, etc.
    #    This is just an example -- adapt to your FADC format.
    suspicious_indices = []
    for i, val in enumerate(int_array):
        # For instance, some JLab boards put 0xFFxy0100, 0xCAFE, or 0xC0DA0100, etc.
        # We'll just do a naive check:
        if (val & 0xFFFF0000) == 0xFFd10000:
            suspicious_indices.append(i)
        if val == 0xC0DA0100:
            suspicious_indices.append(i)

    if suspicious_indices:
        print(f"Found potential 'header' words at indices: {suspicious_indices[:30]}")
        if len(suspicious_indices) > 30:
            print("  ... (more found) ...")

    # 3. If you know the FADC data format, parse in detail, e.g.:
    #    Each word might have bits for channel, sample, etc.
    # For demonstration, let's pretend each 32-bit word:
    #  bits [31..27] => slot
    #  bits [26..22] => channel
    #  bits [21..0 ] => sample
    # That’s not necessarily correct – adapt to your real format.
    # We'll just count how many different slots and channels we see.
    slots = set()
    channels = set()
    for val in int_array:
        slot = (val >> 27) & 0x1F
        ch   = (val >> 22) & 0x1F
        slots.add(slot)
        channels.add(ch)
    print(f"Unique 'slots' found (fake interpretation): {sorted(slots)}")
    print(f"Unique 'channels' found (fake interpretation): {sorted(channels)}")

def main(filename, max_events=3):
    for i, event_data in enumerate(read_coda_stream_file(filename), start=1):
        if i > max_events:
            break

        event_len_words = struct.unpack(">I", event_data[:4])[0]
        print(f"\n===== Event {i} =====")
        print(f"  Raw event size: {len(event_data)} bytes  ({event_len_words} words)")

        # Quick parse top-level banks
        banks = parse_top_level_banks(event_data)
        for b in banks:
            print(f"    Bank: tag=0x{b['tag']:02X}, data_type=0x{b['data_type']:02X}, "
                  f"length_words={b['length_words']}")

            # If it's a big array of 32-bit ints, let's decode and analyze
            if b["data_type"] == 0x01 and b["length_words"] > 10:
                int_array = decode_32bit_array(b["raw_data"])
                analyze_big_int_array(int_array)
                # If you want to plot, e.g. a histogram, you can do it here.
                # For instance:
                # import matplotlib.pyplot as plt
                # plt.hist(int_array, bins=100)
                # plt.show()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_stream_data.py <file> [max_events]")
        sys.exit(1)

    coda_file = sys.argv[1]
    max_evs = 3
    if len(sys.argv) > 2:
        max_evs = int(sys.argv[2])

    main(coda_file, 4)
