import pytest
from pyevio.core import parse_file

@pytest.fixture
def mock_v4_file(tmp_path):
    """
    Create a minimal EVIO v4 file with 1 block containing 1 event.
    """
    block_header = [
        12,   # block_length words
        1,    # block_number
        8,    # header_length
        1,    # event_count
        0,    # reserved
        4,    # bitinfo+version
        0,    # reserved
        0xc0da0100,  # magic in little-end form
    ]
    # one event: length=3 => total 4 words: [3, data1, data2, data3]
    event_data = [3, 0x11111111, 0x22222222, 0x33333333]
    all_words = block_header + event_data

    # little-end
    file_bytes = b''.join(int(x).to_bytes(4, 'little') for x in all_words)
    fpath = tmp_path / "mock_v4.evio"
    with open(fpath, "wb") as f:
        f.write(file_bytes)
    return str(fpath)

def test_v4_parsing(mock_v4_file):
    events = parse_file(mock_v4_file)
    assert len(events) == 1
    ev = events[0]
    assert len(ev) == 16  # 4 words
    # interpret them in little-end for checking
    w0 = int.from_bytes(ev[0:4], 'little')
    w1 = int.from_bytes(ev[4:8], 'little')
    w2 = int.from_bytes(ev[8:12], 'little')
    w3 = int.from_bytes(ev[12:16], 'little')
    assert (w0, w1, w2, w3) == (3, 0x11111111, 0x22222222, 0x33333333)


@pytest.fixture
def mock_v6_file(tmp_path):
    """
    Create a minimal EVIO v6 file with 1 record => 2 events uncompressed.
    This is a simplistic example ignoring the file's index array.
    """
    # The file header is 14 words => each 4 bytes => 56 bytes
    # We'll assume little-end.
    # Words [8..13] store the user reg/trailer pos ints, no big effect here.

    # file_type_id=0x4556494F ('EVIO'), file_number=1, header_length=14 words
    # record_count=0, index_array_len=0, bit_info_version= (lowest8bits=6 => v6)
    # user_header_len=0, magic=0xc0da0100
    # rest = 0
    file_header = [
        0x4556494F, 1, 14, 0, 0, 6, 0, 0xc0da0100,
        0,0, 0,0, 0,0
    ]

    # Then a single record (14 words).
    # record_length, record_number, header_length=14
    # event_count=2, index_array_len=8 (2 events => 8 bytes?), bit_info_version => version=6
    # user_header_len=0, magic=0xc0da0100
    # uncompressed_len => we'll fill later
    # compressed_len => top nibble=0 => uncompressed
    # the rest => 0
    rec_header = [
        0, 1, 14, 2,   # record_length=0 placeholder -> fix after we know total
        8, 6, 0, 0xc0da0100,
        0, 0, 0,0, 0,0
    ]
    # index array => 2 events => lengths in bytes
    # Suppose 1st event is 12 bytes, 2nd event is 16 bytes => total 28
    # We'll do [12,16]
    index_array = [12, 16]

    # user_header => none, so skip
    # event data => let's define 2 events
    # ev1 => 3 words => [2, 0xaaaaaaaa, 0xbbbbbbbb], total 12 bytes
    # ev2 => 4 words => [3, 0x11111111, 0x22222222, 0x33333333], total 16 bytes
    ev1_data = [2, 0xaaaaaaaa, 0xbbbbbbbb]  # length=2 => total=3 words => 12 bytes
    ev2_data = [3, 0x11111111, 0x22222222, 0x33333333]

    # total data bytes => 12 + 16 = 28
    # record_length => 14 (hdr) + 28/4=7 words => 21
    # uncompressed_len => 28 => but must be padded to multiple of 4 => 28 is multiple => so store 28
    rec_length_words = 14 + 7
    rec_header[0] = rec_length_words
    uncompressed_len = 28
    rec_header[8] = uncompressed_len  # word #9 => uncompressed data len in bytes

    # Build up the record
    rec_header_bytes = b''.join(int(x).to_bytes(4, 'little') for x in rec_header)
    index_array_bytes = b''.join(int(x).to_bytes(4, 'little') for x in index_array)
    ev1_bytes = b''.join(int(x).to_bytes(4, 'little') for x in ev1_data)
    ev2_bytes = b''.join(int(x).to_bytes(4, 'little') for x in ev2_data)
    record_bytes = rec_header_bytes + index_array_bytes + ev1_bytes + ev2_bytes

    # file header
    file_header_bytes = b''.join(int(x).to_bytes(4, 'little') for x in file_header)

    # write out
    all_bytes = file_header_bytes + record_bytes
    path = tmp_path / "mock_v6.evio"
    with open(path, "wb") as f:
        f.write(all_bytes)
    return str(path)


def test_v6_parsing(mock_v6_file):
    events = parse_file(mock_v6_file)
    assert len(events) == 2

    # check event #1
    ev1 = events[0]
    # 3 words => 12 bytes
    assert len(ev1) == 12
    w0 = int.from_bytes(ev1[0:4], 'little')
    w1 = int.from_bytes(ev1[4:8], 'little')
    w2 = int.from_bytes(ev1[8:12], 'little')
    assert (w0, w1, w2) == (2, 0xaaaaaaaa, 0xbbbbbbbb)

    # check event #2
    ev2 = events[1]
    assert len(ev2) == 16
    w0 = int.from_bytes(ev2[0:4], 'little')
    w1 = int.from_bytes(ev2[4:8], 'little')
    w2 = int.from_bytes(ev2[8:12], 'little')
    w3 = int.from_bytes(ev2[12:16], 'little')
    assert (w0, w1, w2, w3) == (3, 0x11111111, 0x22222222, 0x33333333)
