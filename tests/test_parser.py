import pytest
from pyevio.parser import parse_file
import os

@pytest.fixture
def mock_v4_file(tmp_path):
    """
    Create a minimal EVIO v4 file with:
     - 1 block (8 words header)
     - block_length=14 words total
     - header_length=8
     - event_count=1
     - magic=0xc0da0100
     - Then 1 event: length=3, so 4 words total => 16 bytes
    The data for the event is arbitrary.

    Layout (all 32-bit ints):
    Block header (8 words):
       0) 14  (block length in words)
       1)  1  (block number)
       2)  8  (header length)
       3)  1  (event count)
       4)  0  (reserved)
       5)  (bit info + version=4 => let's just use 0x4)
       6)  0  (reserved2)
       7)  0xc0da0100 (magic)
    Then event of 4 words:
       word0 => 3 (bank length)
       word1 => 0xfadecafe
       word2 => 0x12345678
       word3 => 0x9abcdef0
    Total = 12 words. But let's match the block_length=14 => we add 2 dummy words of 0 at the end or treat it as leftover?

    Let's keep it consistent: block_length=12 is simpler. We'll do that.
    We'll update the header's block_length=12 to match exactly. No leftover words.

    In real evio, we might also have a "last block" bit, but let's skip that detail.
    """
    block_header = [
        12,      # block_length
        1,       # block_number
        8,       # header_length
        1,       # event_count
        0,       # reserved
        4,       # bitinfo + version (lowest 8 bits=4)
        0,       # reserved2
        0xc0da0100,  # magic
    ]
    event_data = [
        3,           # bank length => 3 => total words = 4
        0xfadecafe,
        0x12345678,
        0x9abcdef0,
    ]
    all_words = block_header + event_data
    # convert to bytes in system-endian
    file_bytes = b"".join(int(x).to_bytes(4, "little") for x in all_words)

    fpath = tmp_path / "mock_v4.evio"
    with open(fpath, "wb") as f:
        f.write(file_bytes)

    return str(fpath)


def test_parse_v4_file(mock_v4_file):
    events = parse_file(mock_v4_file)
    assert len(events) == 1, "Should find exactly 1 event"
    evraw = events[0]
    # length = 4 words => 16 bytes
    assert len(evraw) == 16, "Event #0 should have 16 bytes"
    # check data inside
    w0 = int.from_bytes(evraw[0:4], "little")
    w1 = int.from_bytes(evraw[4:8], "little")
    w2 = int.from_bytes(evraw[8:12], "little")
    w3 = int.from_bytes(evraw[12:16], "little")
    assert w0 == 3
    assert w1 == 0xfadecafe
    assert w2 == 0x12345678
    assert w3 == 0x9abcdef0

