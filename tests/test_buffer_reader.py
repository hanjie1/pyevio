import pytest
import struct
import mmap
from io import BytesIO
from unittest.mock import MagicMock, patch

# Import the BufferReader class - adjust import path as needed
from pyevio.buffer_reader import BufferReader


class TestBufferReader:

    def setup_method(self):
        """Set up test fixtures before each test."""
        # Create a simple test buffer with known values
        # First create little-endian data
        self.le_data = bytearray(64)  # 16 words

        # Write some test values in little endian
        struct.pack_into('<I', self.le_data, 0, 0x12345678)  # Word 0
        struct.pack_into('<I', self.le_data, 4, 0xAABBCCDD)  # Word 1
        struct.pack_into('<I', self.le_data, 8, 14)          # Word 2 (header length)
        struct.pack_into('<I', self.le_data, 28, 0xc0da0100) # Word 7 (magic number)
        struct.pack_into('<Q', self.le_data, 40, 0x1122334455667788) # Words 10-11 (64-bit value)

        # Create the same data in big endian
        self.be_data = bytearray(64)

        # Write the same test values in big endian
        struct.pack_into('>I', self.be_data, 0, 0x12345678)
        struct.pack_into('>I', self.be_data, 4, 0xAABBCCDD)
        struct.pack_into('>I', self.be_data, 8, 14)
        struct.pack_into('>I', self.be_data, 28, 0xc0da0100)
        struct.pack_into('>Q', self.be_data, 40, 0x1122334455667788)

        # Mock mmap objects
        self.le_mmap = MagicMock(spec=mmap.mmap)
        self.le_mmap.__getitem__.side_effect = lambda idx: self.le_data[idx] if isinstance(idx, int) else self.le_data[idx.start:idx.stop]

        self.be_mmap = MagicMock(spec=mmap.mmap)
        self.be_mmap.__getitem__.side_effect = lambda idx: self.be_data[idx] if isinstance(idx, int) else self.be_data[idx.start:idx.stop]

    def test_init_with_default_endian(self):
        """Test BufferReader initialization with default endianness."""
        reader = BufferReader(self.le_mmap, 0)
        assert reader.buffer == self.le_mmap
        assert reader.offset == 0
        assert reader.endian == '<'  # Should detect little endian

    def test_endian_detection_le(self):
        """Test endianness detection with little-endian data."""
        reader = BufferReader(self.le_mmap, 0)
        assert reader.endian == '<'

    def test_endian_detection_be(self):
        """Test endianness detection with big-endian data."""
        reader = BufferReader(self.be_mmap, 0)
        assert reader.endian == '>'

    def test_read_uint32_le(self):
        """Test reading 32-bit uint values from little-endian buffer."""
        reader = BufferReader(self.le_mmap, 0)
        assert reader.read_uint32(0) == 0x12345678
        assert reader.read_uint32(1) == 0xAABBCCDD
        assert reader.read_uint32(2) == 14
        assert reader.read_uint32(7) == 0xc0da0100

    def test_read_uint32_be(self):
        """Test reading 32-bit uint values from big-endian buffer."""
        reader = BufferReader(self.be_mmap, 0)
        assert reader.read_uint32(0) == 0x12345678
        assert reader.read_uint32(1) == 0xAABBCCDD
        assert reader.read_uint32(2) == 14
        assert reader.read_uint32(7) == 0xc0da0100

    def test_read_uint64_le(self):
        """Test reading 64-bit uint values from little-endian buffer."""
        reader = BufferReader(self.le_mmap, 0)
        assert reader.read_uint64(10) == 0x1122334455667788

    def test_read_uint64_be(self):
        """Test reading 64-bit uint values from big-endian buffer."""
        reader = BufferReader(self.be_mmap, 0)
        assert reader.read_uint64(10) == 0x1122334455667788

    def test_get_bytes(self):
        """Test getting byte slices from the buffer."""
        reader = BufferReader(self.le_mmap, 0)
        # Get bytes for words 0-1
        bytes_slice = reader.get_bytes(0, 2)
        self.le_mmap.__getitem__.assert_called_with(slice(0, 8))

    def test_hex_dump(self):
        """Test generating a hex dump."""
        # Mock the make_hex_dump function - patch where it's used, not where it's defined
        with patch('pyevio.buffer_reader.make_hex_dump', return_value="mocked hex dump"):
            reader = BufferReader(self.le_mmap, 0)
            dump = reader.hex_dump(2)  # Dump first 2 words
            assert dump == "mocked hex dump"
            # Assert the make_hex_dump was called with correct arguments
            from pyevio.buffer_reader import make_hex_dump
            make_hex_dump.assert_called_once()

    def test_invalid_magic_number(self):
        """Test behavior when magic number is invalid."""
        # Create data with invalid magic number
        invalid_data = bytearray(64)
        struct.pack_into('<I', invalid_data, 28, 0xDEADBEEF)  # Invalid magic

        invalid_mmap = MagicMock(spec=mmap.mmap)
        invalid_mmap.__getitem__.side_effect = lambda idx: invalid_data[idx] if isinstance(idx, int) else invalid_data[idx.start:idx.stop]

        # BufferReader should raise ValueError on initialization
        with pytest.raises(ValueError, match="Invalid magic number"):
            BufferReader(invalid_mmap, 0)

    def test_offset_parameter(self):
        """Test that offset parameter is respected."""
        # Create data with magic number at different position
        offset_data = bytearray(100)
        offset = 20  # 5 words offset
        struct.pack_into('<I', offset_data, offset + 28, 0xc0da0100)  # Magic at word 7 + offset

        offset_mmap = MagicMock(spec=mmap.mmap)
        offset_mmap.__getitem__.side_effect = lambda idx: offset_data[idx] if isinstance(idx, int) else offset_data[idx.start:idx.stop]

        # Should initialize without error, finding magic at correct offset
        reader = BufferReader(offset_mmap, offset)
        assert reader.offset == offset