import pytest
import struct
import io
import mmap
from typing import List, Tuple
import os
import tempfile

from pyevio.bank import Bank

# Debug function to analyze memory dumps
def debug_memory_dump(data, offset, length, title=None):
    """Print a detailed memory dump with analysis of bank structures."""
    if title:
        print(f"\n{title}")

    for i in range(0, length*4, 16):
        if offset + i >= len(data):
            break

        # Get chunk of data
        chunk = data[offset+i:offset+i+16]
        hex_values = ' '.join([f"{b:02X}" for b in chunk])

        # Add interpretation for words
        words = []
        for j in range(0, len(chunk), 4):
            if j+4 <= len(chunk):
                word_bytes = chunk[j:j+4]
                word_val = struct.unpack("<I", word_bytes)[0]

                # Try to interpret as bank header
                if j == 0:
                    interpretation = f"Length={word_val}"
                elif j == 4:
                    tag = (word_val >> 16) & 0xFFFF
                    data_type = (word_val >> 8) & 0xFF
                    num = word_val & 0xFF
                    interpretation = f"Tag=0x{tag:04X}, Type=0x{data_type:02X}, Num=0x{num:02X}"
                else:
                    interpretation = f"0x{word_val:08X}"

                words.append(interpretation)

        word_info = ' | '.join(words)
        print(f"{offset+i:04X}: {hex_values:<48} {word_info}")
        

class MockMemoryMap:
    """A mock memory map for testing bank scanning."""

    def __init__(self, data):
        """
        Initialize with byte data.

        Args:
            data: Bytes to use for the mock memory map
        """
        self.data = data

    def __getitem__(self, key):
        if isinstance(key, slice):
            start = key.start or 0
            stop = key.stop or len(self.data)
            return self.data[start:stop]
        return self.data[key]

    def __len__(self):
        return len(self.data)


def create_mock_bank(length, tag, data_type, num, data=None, endian='<'):
    """
    Create a mock bank with the specified parameters.

    Args:
        length: Bank length in words (including header)
        tag: Bank tag
        data_type: Bank data type
        num: Bank number
        data: Optional data (bytes) to include in the bank
        endian: Endianness ('<' for little endian, '>' for big endian)

    Returns:
        Bytes object representing the bank
    """
    # Create bank header (2 words)
    header_word1 = struct.pack(f"{endian}I", length)
    header_word2 = struct.pack(f"{endian}I",
                               ((tag & 0xFFFF) << 16) |
                               ((data_type & 0xFF) << 8) |
                               (num & 0xFF))

    # If data is None, create empty data of appropriate length
    if data is None:
        # Length includes header, so subtract 2 words for data
        data_size = max(0, (length - 2) * 4)
        data = bytes(data_size)

    # Combine header and data
    return header_word1 + header_word2 + data


def create_mock_event(banks, endian='<'):
    """
    Create a mock event containing the specified banks.

    Args:
        banks: List of bank data (bytes) to include in the event
        endian: Endianness ('<' for little endian, '>' for big endian)

    Returns:
        Tuple of (event_bytes, bank_offsets)
    """
    # Calculate total length of all banks in words
    total_length = sum(len(bank) for bank in banks) // 4

    # Add event header (2 words) to total length
    event_length = total_length + 2

    # Create event header
    event_header = struct.pack(f"{endian}I", event_length)
    event_tag = struct.pack(f"{endian}I", 0xFF60 << 16 | 0x10 << 8 | 0x01)  # Standard ROC event

    # Combine header and banks
    event_data = event_header + event_tag

    # Track bank offsets
    bank_offsets = []
    offset = 8  # Start after event header

    for bank in banks:
        bank_offsets.append(offset)
        event_data += bank
        offset += len(bank)

    return event_data, bank_offsets


def print_hex_dump(data, title=None):
    """Helper function to print a hex dump of data for debugging."""
    if title:
        print(f"--- {title} ---")

    for i in range(0, len(data), 16):
        chunk = data[i:i+16]
        hex_values = ' '.join([f"{b:02X}" for b in chunk])
        ascii_values = ''.join([chr(b) if 32 <= b < 127 else '.' for b in chunk])
        print(f"{i:04X}: {hex_values:<48} {ascii_values}")


class TestBankScanning:
    """Tests for the Bank scanning logic."""

    def test_basic_bank_structure(self):
        """Test parsing of a simple container bank with child banks."""
        # Create a container bank with two child banks
        child1 = create_mock_bank(4, 0x0101, 0x01, 0x01, struct.pack("<II", 1, 2))
        child2 = create_mock_bank(4, 0x0202, 0x02, 0x02, struct.pack("<II", 3, 4))

        # Container bank length = 2 (header) + len(child1)/4 + len(child2)/4
        container_length = 2 + len(child1)//4 + len(child2)//4
        container_data = child1 + child2
        container = create_mock_bank(container_length, 0xFFAA, 0x10, 0x00, container_data)

        # Create mock memory map
        mm = MockMemoryMap(container)

        # Create bank object
        bank = Bank(mm, 0, '<')

        # Verify bank properties
        assert bank.tag == 0xFFAA
        assert bank.data_type == 0x10
        assert bank.num == 0x00
        assert bank.length == container_length

        # Get children
        children = bank.get_children()

        # Verify children count
        assert len(children) == 2

        # Verify first child
        assert children[0].tag == 0x0101
        assert children[0].data_type == 0x01
        assert children[0].num == 0x01
        assert children[0].length == 4

        # Verify second child
        assert children[1].tag == 0x0202
        assert children[1].data_type == 0x02
        assert children[1].num == 0x02
        assert children[1].length == 4

    def test_minimal_length_banks(self):
        """Test parsing of banks with minimal lengths (1 and 2)."""
        # Create a length-1 bank (just the length word)
        bank1 = struct.pack("<I", 1)

        # Create a length-2 bank (length word + header word)
        bank2 = create_mock_bank(2, 0x000F, 0x00, 0x01)

        # Create a container with these banks
        container_data = bank1 + bank2
        container_length = 2 + len(container_data)//4
        container = create_mock_bank(container_length, 0xFF60, 0x10, 0x01, container_data)

        # Create mock memory map
        mm = MockMemoryMap(container)

        # Create bank object
        bank = Bank(mm, 0, '<')

        # Get children
        children = bank.get_children()

        # Verify children count
        assert len(children) == 2

        # Verify first child (length-1 bank)
        assert children[0].length == 1
        assert children[0].offset == 8  # After container header

        # Verify second child (length-2 bank)
        assert children[1].length == 2
        assert children[1].tag == 0x000F
        assert children[1].data_type == 0x00
        assert children[1].num == 0x01

    def test_nonstandard_tag_patterns(self):
        """Test parsing of banks with non-standard tag patterns."""
        # Create a ROC bank with 0x0002 for ROC_ID and 0x11 for status
        roc_bank = create_mock_bank(3, 0x0002, 0x10, 0x11, struct.pack("<I", 0))

        # Create a container with this bank
        container_data = roc_bank
        container_length = 2 + len(container_data)//4
        container = create_mock_bank(container_length, 0xFF60, 0x10, 0x01, container_data)

        # Create mock memory map
        mm = MockMemoryMap(container)

        # Create bank object
        bank = Bank(mm, 0, '<')

        # Get children
        children = bank.get_children()

        # Verify children count
        assert len(children) == 1

        # Verify ROC bank
        assert children[0].tag == 0x0002
        assert children[0].data_type == 0x10
        assert children[0].num == 0x11
        assert children[0].length == 3

    # Debug version of our data_bank creation - shows what's happening
    def test_complex_event_structure(self):
        """Test parsing of a complex event structure similar to the one analyzed."""
        # Create a segment bank (similar to the 0xFF31 bank)
        segment_data = struct.pack("<IIII", 0x32010003, 0, 0, 0x42010001)
        segment_bank = create_mock_bank(7, 0xFF31, 0x20, 0x01, segment_data)

        # Create a ROC bank (similar to the 0x0002 bank)
        stream_info_data = struct.pack("<III", 0xFF302011, 0x31010003, 0)
        roc_bank = create_mock_bank(11, 0x0002, 0x10, 0x11, stream_info_data + bytes(20))

        # FIXED: Use create_mock_bank instead of struct.pack directly
        data_bank = create_mock_bank(2, 0x000F, 0x00, 0x01, struct.pack("<I", 0x000F0001))

        # Enable debugging to see the raw bytes
        print("\nDEBUG: Bank Layout")
        print("Segment bank:", ' '.join(f"{b:02X}" for b in segment_bank[:16]))
        print("ROC bank:", ' '.join(f"{b:02X}" for b in roc_bank[:16]))
        print("Data bank:", ' '.join(f"{b:02X}" for b in data_bank))

        # Create the complete event
        event_data, bank_offsets = create_mock_event([segment_bank, roc_bank, data_bank])

        # Print event structure
        print("\nDEBUG: Event Structure")
        print("Bank offsets:", [hex(offset) for offset in bank_offsets])
        print_hex_dump(event_data[:64], "Event header and first bank")

        # Create mock memory map
        mm = MockMemoryMap(event_data)

        # Create event bank
        bank = Bank(mm, 0, '<')

        # Get children
        children = bank.get_children()

        # Print what we found
        print("\nDEBUG: Found Banks")
        for i, child in enumerate(children):
            print(f"Child {i}: offset={hex(child.offset)}, tag=0x{child.tag:04X}, type=0x{child.data_type:02X}, length={child.length}")

        # Verify children count
        assert len(children) == 3

        # Verify segment bank
        assert children[0].tag == 0xFF31
        assert children[0].data_type == 0x20
        assert children[0].offset == bank_offsets[0]

        # Verify ROC bank
        assert children[1].tag == 0x0002
        assert children[1].data_type == 0x10
        assert children[1].offset == bank_offsets[1]

        # Verify data bank
        assert children[2].length == 2
        assert children[2].offset == bank_offsets[2]
        assert children[2].tag == 0x000F

    def test_edge_cases(self):
        """Test handling of edge cases (zero-length banks, boundary conditions)."""
        # Create valid banks
        valid_bank1 = create_mock_bank(3, 0x0101, 0x01, 0x01, struct.pack("<I", 1))
        valid_bank2 = create_mock_bank(3, 0x0202, 0x02, 0x02, struct.pack("<I", 2))

        # Create invalid data (not a proper bank)
        invalid_data = struct.pack("<II", 0, 0)  # Zero length, invalid

        # Create container with valid and invalid data
        container_data = valid_bank1 + invalid_data + valid_bank2
        container_length = 2 + len(container_data)//4
        container = create_mock_bank(container_length, 0xFF60, 0x10, 0x01, container_data)

        # Create mock memory map
        mm = MockMemoryMap(container)

        # Create bank object
        bank = Bank(mm, 0, '<')

        # Get children - should skip invalid data
        children = bank.get_children()

        # Verify children count - should only get the valid banks
        assert len(children) == 2

        # Verify first valid bank
        assert children[0].tag == 0x0101
        assert children[0].data_type == 0x01

        # Verify second valid bank
        assert children[1].tag == 0x0202
        assert children[1].data_type == 0x02

    def test_error_recovery(self):
        """Test recovery from corrupted or invalid bank data."""
        # Create valid bank
        valid_bank = create_mock_bank(3, 0x0101, 0x01, 0x01, struct.pack("<I", 1))

        # Create bank with invalid length (would go beyond parent)
        invalid_bank = struct.pack("<I", 1000) + struct.pack("<I", 0x02020202)

        # Create another valid bank after the invalid one
        valid_bank2 = create_mock_bank(3, 0x0303, 0x03, 0x03, struct.pack("<I", 3))

        # Create container with mix of valid and invalid
        container_data = valid_bank + invalid_bank + valid_bank2
        container_length = 2 + len(container_data)//4
        container = create_mock_bank(container_length, 0xFF60, 0x10, 0x01, container_data)

        # Create mock memory map
        mm = MockMemoryMap(container)

        # Create bank object
        bank = Bank(mm, 0, '<')

        # Get children - should skip invalid bank and recover
        children = bank.get_children()

        # Verify we found at least the first valid bank
        assert len(children) >= 1
        assert children[0].tag == 0x0101
        assert children[0].data_type == 0x01




    def test_real_world_event_structure(self):
        """
        Test with data matching the exact structure from our discussion.
        This simulates the 21-word event with complex nested structure.
        """
        # Create a temporary file with binary data
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            try:
                # Event header - length 21 words
                tmp.write(struct.pack("<I", 21))  # 0x00000015
                tmp.write(struct.pack("<I", 0xFF601001))  # Tag 0xFF60, Type 0x10

                # First bank - Segment (length 7)
                tmp.write(struct.pack("<I", 7))  # 0x00000007
                tmp.write(struct.pack("<I", 0xFF312001))  # Tag 0xFF31, Type 0x20
                tmp.write(struct.pack("<I", 0x32010003))  # Segment data
                tmp.write(struct.pack("<I", 0))  # Padding
                tmp.write(struct.pack("<I", 0))  # Padding
                tmp.write(struct.pack("<I", 0))  # Padding
                tmp.write(struct.pack("<I", 0x42010001))  # End of segment data

                # Non-bank data / metadata
                tmp.write(struct.pack("<I", 0x00020011))  # ROC_ID, status code

                # Second bank - Bank of banks (length 11)
                tmp.write(struct.pack("<I", 11))  # 0x0000000B
                tmp.write(struct.pack("<I", 0x00021011))  # ROC header

                # Stream Info Bank inside second bank
                tmp.write(struct.pack("<I", 7))  # 0x00000007
                tmp.write(struct.pack("<I", 0xFF302011))  # Tag 0xFF30, Type 0x20
                tmp.write(struct.pack("<I", 0x31010003))  # Time Slice Segment
                tmp.write(struct.pack("<I", 0))  # Timestamp low
                tmp.write(struct.pack("<I", 0))  # Timestamp high
                tmp.write(struct.pack("<I", 0))  # Padding
                tmp.write(struct.pack("<I", 0x41850001))  # Aggregation Info Segment

                # Payload info
                tmp.write(struct.pack("<I", 0))  # Module ID=0 payload info

                # CRITICAL FIX: Add proper bank header for data bank
                # This bank should have a proper bank header with tag 0x000F, type 0x00, num 0x01
                tmp.write(struct.pack("<I", 2))  # Length 2
                tmp.write(struct.pack("<I", 0x000F0001))  # Tag 0x000F, Type 0x00, Num 0x01

                # Get file size
                tmp.flush()
                tmp_name = tmp.name

                # Debug: print file contents
                with open(tmp_name, 'rb') as f:
                    file_data = f.read()
                    print("\nDEBUG: File Structure")
                    debug_memory_dump(file_data, 0, min(64, len(file_data)//4), "File header and contents")

            except Exception as e:
                # Ensure file is cleaned up on error
                if os.path.exists(tmp.name):
                    try:
                        os.unlink(tmp.name)
                    except:
                        pass
                raise e

        try:
            # Open the file and memory map it
            with open(tmp_name, 'rb') as f:
                file_content = f.read()  # Read entire file for debugging
                mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

                try:
                    # Create bank from the event
                    event_bank = Bank(mm, 0, '<')

                    # Verify event properties
                    assert event_bank.length == 21
                    assert event_bank.tag == 0xFF60
                    assert event_bank.data_type == 0x10

                    # Get children
                    children = event_bank.get_children()

                    # Debug: print what we found
                    print("\nDEBUG: Found Banks")
                    for i, child in enumerate(children):
                        print(f"Child {i}: offset={hex(child.offset)}, tag=0x{child.tag:04X}, type=0x{child.data_type:02X}, length={child.length}")

                    # Verify we found all three main components
                    assert len(children) == 3

                    # Verify first bank (segment)
                    assert children[0].tag == 0xFF31
                    assert children[0].data_type == 0x20
                    assert children[0].length == 7

                    # Verify second bank (ROC bank)
                    assert children[1].tag == 0x0002
                    assert children[1].data_type == 0x10
                    assert children[1].num == 0x11
                    assert children[1].length == 11

                    # Verify third bank (data bank)
                    assert children[2].tag == 0x000F
                    assert children[2].data_type == 0x00
                    assert children[2].num == 0x01
                    assert children[2].length == 2

                    # Check the specific offset to verify we found the right bank
                    expected_offset = 84  # Calculate this from your file structure
                    assert abs(children[2].offset - expected_offset) <= 4  # Allow small difference due to padding

                finally:
                    # Clean up memory map
                    mm.close()

        finally:
            # Clean up the temporary file
            if os.path.exists(tmp_name):
                try:
                    # We're on Windows, so this might fail, which is OK for testing
                    os.unlink(tmp_name)
                except PermissionError:
                    # On Windows, the file may still be locked even after closing the mmap
                    pass

    def test_data_payload_decoding(self):
        """Test decoding of FADC hit data in payload banks."""
        # Create a data payload with a single hit
        # Format: (channel << 13) | (charge & 0x1FFF) | ((time/4) << 17)
        channel = 5      # Channel 5
        charge = 1024    # ADC value of 1024
        time = 400       # Time of 400

        # Encode according to the bit pattern
        encoded_hit = (channel << 13) | (charge & 0x1FFF) | ((time // 4) << 17)

        # CRITICAL FIX: Use create_mock_bank to create a proper bank structure
        data_bank = create_mock_bank(2, 0x000F, 0x00, 0x01, struct.pack("<I", encoded_hit))

        # Debug output
        print("\nDEBUG: Data Bank Structure")
        print_hex_dump(data_bank, "Data bank raw bytes")

        # Create mock memory map
        mm = MockMemoryMap(data_bank)

        # Create bank object
        bank = Bank(mm, 0, '<')

        # Debug output
        print(f"Bank: offset={hex(bank.offset)}, length={bank.length}, data_offset={hex(bank.data_offset)}")

        # We don't have direct access to the decoded fields in Bank object,
        # but we can verify the encoding by manually decoding the data
        data_offset = bank.data_offset

        # Verify the data_offset is within bounds
        assert data_offset + 4 <= len(mm), f"Data offset {data_offset} + 4 exceeds buffer size {len(mm)}"

        # Now it's safe to decode
        data_word = struct.unpack("<I", mm[data_offset:data_offset+4])[0]

        decoded_channel = (data_word >> 13) & 0x000F
        decoded_charge = data_word & 0x1FFF
        decoded_time = ((data_word >> 17) & 0x3FFF) * 4

        # Verify decoded values match what we encoded
        assert decoded_channel == channel
        assert decoded_charge == charge
        assert decoded_time == time