
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