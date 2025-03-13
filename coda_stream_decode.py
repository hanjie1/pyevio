#!/usr/bin/env python3

import struct
import sys
import matplotlib.pyplot as plt

def read_coda_stream_file(filename):
    """
    Generator that reads a CODA 3.11 streaming-mode file,
    skips the 14-word block header, then yields each event (as bytes).
    """
    with open(filename, "rb") as f:
        # 1) Read 14-word streaming block header (14 x 4 bytes = 56).
        block_header_len_words = 14
        header_bytes = f.read(block_header_len_words * 4)

        if len(header_bytes) < block_header_len_words * 4:
            print("Error: File too short to contain 14-word block header.")
            return

        # 2) Read events until EOF
        while True:
            # Each event starts with a 32-bit 'event length in words'
            length_bytes = f.read(4)
            if len(length_bytes) < 4:
                break  # EOF or partial

            event_len_words = struct.unpack(">I", length_bytes)[0]
            if event_len_words < 1:
                break  # Defensive check

            event_body = f.read((event_len_words - 1) * 4)
            if len(event_body) < (event_len_words - 1) * 4:
                print("Warning: Incomplete event read near EOF.")
                break

            event_data = length_bytes + event_body
            yield event_data


def parse_evio_event(event_data):
    """
    Parse an EVIO event (big-endian) and return a list of top-level banks.
    """
    event_len_words = struct.unpack(">I", event_data[:4])[0]
    total_bytes = event_len_words * 4

    if len(event_data) < total_bytes:
        raise ValueError("Truncated event data")

    # Parse banks after the first word
    banks = []
    offset = 4
    while offset < total_bytes:
        bank_info, bank_size, _ = parse_evio_bank(event_data, offset)
        if bank_info is None or bank_size == 0:
            break
        banks.append(bank_info)
        offset += bank_size

    return banks


def parse_evio_bank(event_data, offset):
    """
    Parse a single EVIO bank/segment/tagsegment from 'event_data' (big-endian),
    starting at 'offset'. Returns (bank_dict, bank_size_bytes, raw_data).

    If parsing fails, returns (None, 0, None).
    """
    if offset + 4 > len(event_data):
        return None, 0, None

    header_word = struct.unpack(">I", event_data[offset:offset+4])[0]

    length_minus1 = (header_word >> 16) & 0xFFFF
    data_type     = (header_word >> 8)  & 0xFF
    tag           =  header_word        & 0xFF

    num_words = length_minus1 + 1
    bank_size_bytes = num_words * 4
    if offset + bank_size_bytes > len(event_data):
        return None, 0, None

    # Grab the payload (all minus the 4-byte header)
    data_offset = offset + 4
    data_length_bytes = bank_size_bytes - 4
    raw_data = event_data[data_offset:data_offset+data_length_bytes]

    bank_dict = {
        "tag": tag,
        "data_type": data_type,
        "length_words": num_words,
        "sub_banks": [],      # for nested structures
        "decoded_data": None, # for primitive arrays
    }

    # Bank-of-banks type
    TYPE_BANK = 0x10
    TYPE_SEG  = 0x20
    # (Tagsegments = 0x40, etc.)

    if data_type == TYPE_BANK:
        # Parse sub-banks recursively
        sub_offset = 0
        while sub_offset < data_length_bytes:
            sb_info, sb_size, _ = parse_evio_bank(raw_data, sub_offset)
            if sb_info is None or sb_size == 0:
                break
            bank_dict["sub_banks"].append(sb_info)
            sub_offset += sb_size

    elif data_type == TYPE_SEG:
        # parse sub-segments if needed, or store raw
        # You can do segment-specific logic here.
        pass

    else:
        # For data_type = 0x01, 0x02, etc. => It's a primitive data array
        # We'll decode them as 32-bit, 16-bit, or 8-bit arrays, etc.
        bank_dict["decoded_data"] = decode_primitive_data(data_type, raw_data)

    return bank_dict, bank_size_bytes, raw_data


def decode_primitive_data(data_type, raw_data):
    """
    Convert raw_data into a Python list of integers/bytes depending on data_type.
    Common EVIO data_type codes for 'primitive' arrays:
      - 0x01 => 32-bit unsigned int
      - 0x02 => 16-bit short
      - 0x03 => 8-bit char
      - 0x04 => 64-bit double? (less common in old EVIO)
    Adjust as needed for your CODA version.
    """
    if data_type == 0x01:
        # 32-bit words, big-endian
        n = len(raw_data)//4
        return list(struct.unpack(">" + "I"*n, raw_data))

    elif data_type == 0x02:
        # 16-bit shorts
        n = len(raw_data)//2
        return list(struct.unpack(">" + "H"*n, raw_data))

    elif data_type == 0x03:
        # 8-bit chars
        return list(raw_data)

    else:
        # Fallback: just keep the raw bytes
        return raw_data


def dump_evio_structure(banks, indent=0, max_sub_banks=20):
    """
    Recursively print out all banks found.
    Shows data_type, length, etc. If there's a decoded_data array,
    mention how many elements are in it.
    """
    prefix = "  " * indent
    for i, bank in enumerate(banks):
        if i >= max_sub_banks:
            print(f"{prefix}... (Skipping additional sub-banks beyond {max_sub_banks})")
            break

        tag_str = f"0x{bank['tag']:02X}"
        dtype_str = f"0x{bank['data_type']:02X}"
        length_words = bank["length_words"]
        msg = f"{prefix}Bank: tag={tag_str}, data_type={dtype_str}, length_words={length_words}"

        # If there's a decoded array, show a brief summary
        if bank["decoded_data"] is not None:
            data_size = len(bank["decoded_data"])
            msg += f", decoded_data len={data_size}"

        print(msg)

        sub_banks = bank["sub_banks"]
        if sub_banks:
            dump_evio_structure(sub_banks, indent=indent+1, max_sub_banks=max_sub_banks)


def plot_primitive_data(int_array, title="Primitive Data Array"):
    """
    Example function to plot the given list of integers as a simple waveform or histogram.
    """
    if not int_array:
        print("No data to plot.")
        return

    # For example, let's do a histogram:
    plt.figure(figsize=(10,5))
    plt.hist(int_array, bins=50, alpha=0.7, color='blue')
    plt.title(title)
    plt.xlabel("Value")
    plt.ylabel("Count")
    plt.grid(True, alpha=0.3)
    plt.show()


def main(filename, max_events=3):
    event_count = 0

    for event_data in read_coda_stream_file(filename):
        event_count += 1
        if event_count > max_events:
            break

        banks = parse_evio_event(event_data)

        print(f"\n===== Event {event_count} =====")
        print(f"  Raw size: {len(event_data)} bytes")

        if not banks:
            print("  No top-level banks found.")
            continue

        print("  Banks found in event:")
        dump_evio_structure(banks, indent=1, max_sub_banks=2000)  # or fewer if you like

        # Example: find the first bank that has "decoded_data"
        # and do a quick plot. (Adapt as you like.)
        for b in banks:
            if b["decoded_data"] is not None and isinstance(b["decoded_data"], list):
                # Could be your 32-bit array from streaming
                plot_primitive_data(b["decoded_data"], title=f"Event {event_count}, tag=0x{b['tag']:02X}")
                break  # plot only the first one, for demo

    print("\nDone.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <filename> [max_events]")
        sys.exit(1)

    input_file = sys.argv[1]
    max_evs = 3
    if len(sys.argv) > 2:
        max_evs = int(sys.argv[2])

    main(input_file, max_evs)
