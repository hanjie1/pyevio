import struct
from typing import Union, Optional
import mmap

def make_hex_dump(data, chunk_size=4, title=None):
    """
    Create a formatted hexdump of binary data.

    Args:
        data: Binary data to dump
        chunk_size: Number of bytes per line chunk
        title: Optional title to display before the hex dump

    Returns:
        String containing formatted hexdump
    """
    dump = []

    if title:
        dump.append(f"--- {title} ---")

    half_chunk = int(chunk_size / 2)
    dump.append("   {:<6}    {:<{}} {}".format("line", "data", chunk_size*3+3, "text"))
    dump.append("-"*len(dump[0]))
    for i in range(0, len(data), chunk_size):
        chunk = data[i:i+chunk_size]
        sub1 = chunk[:half_chunk]
        sub2 = chunk[half_chunk:chunk_size]
        hex1 = ' '.join(f"{b:02x}" for b in sub1)
        hex2 = ' '.join(f"{b:02x}" for b in sub2)
        hex_part = hex1 + '  ' + hex2
        ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        line_num = int(i/chunk_size)
        line = f"{line_num:>4}[{i:04x}]   {hex_part}    {ascii_str}"
        dump.append(line)
    return '\n'.join(dump)


def make_offset_dump(data: Union[mmap.mmap, bytes, bytearray],
                     offset: int,
                     show_size: int,
                     endian: str = '>',
                     chunk_size: int = 4) -> str:
    """
    Create a formatted offset dump of binary data with multiple representations.

    Args:
        data: Memory-mapped file or binary data to dump
        offset: Starting offset in bytes
        show_size: Number of 32-bit words to show
        endian: Endianness ('<' for little-endian, '>' for big-endian)
        chunk_size: Number of bytes per line chunk

    Returns:
        String containing formatted dump with various data representations
    """
    dump = []

    # Calculate end position
    end_pos = offset + (show_size * 4)
    if end_pos > len(data):
        end_pos = len(data)
        actual_words = (end_pos - offset) // 4
        if actual_words < show_size:
            show_size = actual_words

    # Create header row
    header = "{:<4} {:<10} {:<7} {:<14} {:<16} {:<12} {:<16}".format(
        "Idx", "Offset(hex)", "Word#", "Bytes", "Half-words", "Word", "Text"
    )
    dump.append(header)
    dump.append("-" * len(header))

    # Process data in chunks
    for i in range(0, show_size):
        pos = offset + (i * 4)
        if pos + 4 > len(data):
            break

        # Extract the 32-bit word
        word_bytes = data[pos:pos+4]

        # Calculate displays
        word_idx = i
        word_offset_hex = f"0x{pos:08x}"
        word_offset_dec = f"{pos // 4}"

        # Byte representation
        byte_hex = " ".join(f"{b:02x}" for b in word_bytes)

        # Half-word representation (16-bit values) both as hex and decimal
        hw1 = struct.unpack(f"{endian}H", word_bytes[0:2])[0]
        hw2 = struct.unpack(f"{endian}H", word_bytes[2:4])[0]
        half_words = f"{hw1:5d} {hw2:5d}"

        # Word representation (32-bit value) both as hex and decimal
        word_val = struct.unpack(f"{endian}I", word_bytes)[0]
        word_decimal = f"{word_val:10d}"

        # ASCII text representation
        text = "".join(chr(b) if 32 <= b < 127 else '.' for b in word_bytes)

        # Format the line
        line = f"{word_idx:<4} {word_offset_hex:<10} {word_offset_dec:<7} {byte_hex:<14} {half_words:<16} {word_decimal:<12} {text:<16}"
        dump.append(line)

    return "\n".join(dump)


def print_offset_hex_text(data: Union[mmap.mmap, bytes, bytearray],
                          offset: int,
                          show_size: int,
                          title: Optional[str] = None,
                          endian: str = '>',
                          chunk_size: int = 4) -> None:
    """
    Print a formatted offset dump with an optional header text (original implementation).

    Args:
        data: Memory-mapped file or binary data to dump
        offset: Starting offset in bytes
        show_size: Number of 32-bit words to show
        title: Optional title text to display before the dump
        endian: Endianness ('<' for little-endian, '>' for big-endian)
        chunk_size: Number of bytes per line chunk
    """
    if title:
        separator = "=" * len(title)
        print(separator)
        print(title)
        print(separator)

    dump_text = make_offset_dump(data, offset, show_size, endian, chunk_size)
    print(dump_text)


def format_bits(word):
    """
    Convert a 32-bit word to a formatted bit string with spacing every 8 bits.
    
    Args:
        word: 32-bit integer to format
        
    Returns:
        String of 32 bits with spaces every 8 bits
    """
    # Convert to binary string and ensure it's 32 bits
    binary = bin(word)[2:].zfill(32)

    # Add spaces every 8 bits
    formatted = ' '.join(binary[i:i+8] for i in range(0, 32, 8))

    return formatted


def print_offset_hex(data: Union[mmap.mmap, bytes, bytearray],
                     offset: int,
                     show_size: int,
                     title: Optional[str] = None,
                     endian: str = '>',
                     chunk_size: int = 4) -> None:
    """
    Print a formatted hex dump with binary representation similar to the C++ implementation.

    Args:
        data: Memory-mapped file or binary data to dump
        offset: Starting offset in bytes
        show_size: Number of 32-bit words to show
        title: Optional title text to display before the dump
        endian: Endianness ('<' for little-endian, '>' for big-endian)
        chunk_size: Number of bytes per line chunk
    """

    # Create header row. We need this first to calculate its len
    header = "{:<4} {:<16} {:<16} {:<17} {:<14} {:>35}".format(
        "Idx", "Addr[B|Wrd#]", "Bytes", "Half-words", "Word", "Bits (MSB→LSB)"
    )

    if title:
        separator = "=" * len(header)  # Match the width of the output
        print(separator)
        print(title)
        print(separator)

    print(header)
    print("-" * len(header))  # Set width to match header

    # Calculate end position
    end_pos = offset + (show_size * 4)
    if end_pos > len(data):
        end_pos = len(data)
        actual_words = (end_pos - offset) // 4
        if actual_words < show_size:
            show_size = actual_words

    # Process data in chunks
    for i in range(0, show_size):
        pos = offset + (i * 4)
        if pos + 4 > len(data):
            break

        # Extract the 32-bit word
        word_bytes = data[pos:pos+4]

        # Calculate displays
        word_idx = i
        word_offset_hex = f"{pos:08x}"  # No '0x' prefix to match example
        word_offset_dec = f"{pos // 4}"

        # Byte representation
        byte_hex = " ".join(f"{b:02x}" for b in word_bytes)

        # Half-word representation (16-bit values)
        hw1 = struct.unpack(f"{endian}H", word_bytes[0:2])[0]
        hw2 = struct.unpack(f"{endian}H", word_bytes[2:4])[0]
        half_words = f"{hw1:<8} {hw2:<8}"

        # Word representation (32-bit value)
        word_val = struct.unpack(f"{endian}I", word_bytes)[0]
        word_decimal = f"{word_val}"

        # Binary representation
        bits = format_bits(word_val)

        # Format the line
        line = f"{word_idx:<4} {word_offset_hex:<8} {word_offset_dec:<7} {byte_hex:<16} {half_words:<16} {word_decimal:<14} {bits}"
        print(line)