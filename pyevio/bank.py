import mmap
import struct
from typing import List, Tuple, Optional, Dict, Any, Union
import numpy as np
from datetime import datetime

from pyevio.utils import make_hex_dump


class BankHeader:
    """Base class for bank headers."""
    def __init__(self):
        self.length = None
        self.tag = None
        self.pad = None
        self.data_type = None
        self.num = None
        self.offset = None
        self.type_name = "Unknown"


class Bank(BankHeader):
    """
    Represents a Bank with a full 2-word header.

    Structure:
    - Word 1: length
    - Word 2: tag (16 bits) | pad (2 bits) | type (6 bits) | num (8 bits)

    Banks can contain data or other banks, depending on the data_type.
    """

    # Data type constants
    TYPE_UNKNOWN32 = 0x0
    TYPE_UINT32 = 0x1
    TYPE_FLOAT32 = 0x2
    TYPE_STRING = 0x3
    TYPE_INT16 = 0x4
    TYPE_UINT16 = 0x5
    TYPE_INT8 = 0x6
    TYPE_UINT8 = 0x7
    TYPE_FLOAT64 = 0x8
    TYPE_INT64 = 0x9
    TYPE_UINT64 = 0xa
    TYPE_INT32 = 0xb
    TYPE_TAGSEGMENT = 0xc
    TYPE_SEGMENT = 0xd
    TYPE_BANK = 0xe
    TYPE_COMPOSITE = 0xf
    TYPE_BANK2 = 0x10
    TYPE_SEGMENT2 = 0x20

    # Mapping from data types to numpy dtypes
    _NUMPY_DTYPES = {
        TYPE_UNKNOWN32: np.uint32,
        TYPE_UINT32: np.uint32,
        TYPE_FLOAT32: np.float32,
        TYPE_INT16: np.int16,
        TYPE_UINT16: np.uint16,
        TYPE_INT8: np.int8,
        TYPE_UINT8: np.uint8,
        TYPE_FLOAT64: np.float64,
        TYPE_INT64: np.int64,
        TYPE_UINT64: np.uint64,
        TYPE_INT32: np.int32
    }

    def __init__(self, mm: mmap.mmap, offset: int, endian: str = '<'):
        """
        Initialize a Bank object.

        Args:
            mm: Memory-mapped file containing the bank
            offset: Byte offset in the file where the bank starts
            endian: Endianness ('<' for little endian, '>' for big endian)
        """
        super().__init__()
        self.mm = mm
        self.offset = offset
        self.endian = endian

        # Parse bank header
        self._parse_header()

        # Calculate data offset and size
        self.header_size = 8  # 2 words * 4 bytes
        self.data_offset = self.offset + self.header_size
        self.data_length = (self.length * 4) - self.header_size
        self.size = self.length * 4

        # End offset for this bank
        self.end_offset = self.offset + self.size

        # Child banks (will be parsed on demand)
        self._children = None

    def _parse_header(self):
        """Parse the bank header from the buffer."""
        # Parse 2-word header
        self.length = struct.unpack(self.endian + 'I', self.mm[self.offset:self.offset+4])[0]
        bank_info = struct.unpack(self.endian + 'I', self.mm[self.offset+4:self.offset+8])[0]

        # Unpack bank info
        self.tag = (bank_info >> 16) & 0xFFFF
        self.pad = (bank_info >> 14) & 0x3
        self.data_type = (bank_info >> 8) & 0x3F
        self.num = bank_info & 0xFF

        # Determine special bank types by tag
        if (self.tag & 0xFF00) == 0xFF00:
            tag_type = self.tag & 0x00FF
            if (tag_type & 0x10) == 0x10:
                self.type_name = "RocRawDataRecord"
            elif tag_type == 0x30:
                self.type_name = "RocTimeSliceBank"
            elif tag_type == 0x31:
                self.type_name = "PhysicsEvent"

    @classmethod
    def from_buffer(cls, buffer: mmap.mmap, offset: int, endian: str = '<') -> 'Bank':
        """
        Create a Bank object from a memory-mapped buffer.

        Args:
            buffer: Memory-mapped buffer containing the bank
            offset: Byte offset in the buffer where the bank starts
            endian: Endianness ('<' for little endian, '>' for big endian)

        Returns:
            Bank object
        """
        return cls(buffer, offset, endian)

    def is_container(self) -> bool:
        """
        Check if this bank is a container for other banks.

        Returns:
            True if this bank contains other banks, False otherwise
        """
        return self.data_type in (self.TYPE_BANK, self.TYPE_BANK2, self.TYPE_SEGMENT, self.TYPE_SEGMENT2)

    def get_children(self) -> List['Bank']:
        """
        Get child banks if this is a container bank.

        Returns:
            List of Bank objects
        """
        # Return empty list for non-container banks
        if not self.is_container():
            return []

        # Return cached children if already parsed
        if self._children is not None:
            return self._children

        # Initialize empty children list
        self._children = []

        # Start from the beginning of the data section
        current_offset = self.data_offset
        end_offset = self.end_offset

        while current_offset < end_offset:
            # We need at least 4 bytes to read a length
            if current_offset + 4 > end_offset:
                break

            try:
                # Read bank length
                bank_length = struct.unpack(self.endian + 'I',
                                            self.mm[current_offset:current_offset+4])[0]

                # Basic sanity check: bank shouldn't exceed parent boundary
                if current_offset + (bank_length * 4) > end_offset:
                    # If we're near the end (just a word or two left), this might be data padding
                    # Skip to the next word and continue
                    current_offset += 4
                    continue

                # Even a length of 1 is valid for data banks (just the length word itself)
                # In this case the bank has no additional data beyond the length word

                # Check if we have enough space for this bank
                if bank_length == 0:
                    # Zero-length banks are invalid - skip this word
                    current_offset += 4
                    continue

                if current_offset + (bank_length * 4) > end_offset:
                    # Bank goes beyond parent boundary - skip this word
                    current_offset += 4
                    continue

                # Try to create bank object
                try:
                    child = Bank.from_buffer(self.mm, current_offset, self.endian)

                    # Add to children
                    self._children.append(child)

                    # Move to next bank by adding this bank's length
                    current_offset += bank_length * 4

                except Exception as e:
                    # Error creating bank - skip ahead
                    if self._children and hasattr(self, 'verbose') and self.verbose:
                        print(f"Error parsing bank at 0x{current_offset:X}: {str(e)}")
                    current_offset += 4
                    continue

            except Exception as e:
                # Error reading/processing data - skip ahead
                current_offset += 4

        return self._children

    def get_data(self) -> bytes:
        """
        Get the raw data for this bank.

        Returns:
            Bytes object containing the raw bank data
        """
        return self.mm[self.data_offset:self.data_offset + self.data_length + 4]

    def to_numpy(self) -> Optional[np.ndarray]:
        """
        Convert bank data to a NumPy array if possible.

        Returns:
            NumPy array containing the data, or None if not convertible
        """
        if self.is_container():
            return None

        dtype = self._NUMPY_DTYPES.get(self.data_type)
        if dtype is None:
            return None

        # Calculate the number of elements
        element_size = np.dtype(dtype).itemsize
        num_elements = self.data_length // element_size

        # Create NumPy array from buffer
        return np.frombuffer(
            self.mm[self.data_offset:self.data_offset + (num_elements * element_size)],
            dtype=dtype
        )

    def to_string(self) -> Optional[str]:
        """
        Convert bank data to a string if it's a string type.

        Returns:
            String representation of the data, or None if not a string
        """
        if self.data_type != self.TYPE_STRING:
            return None

        # Extract string data (null-terminated)
        data = self.mm[self.data_offset:self.data_offset + self.data_length]

        # Find null terminator
        null_pos = data.find(b'\0')
        if null_pos >= 0:
            data = data[:null_pos]

        # Decode as ASCII
        try:
            return data.decode('ascii')
        except UnicodeDecodeError:
            return None

    def get_hex_dump(self, max_bytes: int = 64, title: Optional[str] = None) -> str:
        """
        Generate a hex dump of the bank data.

        Args:
            max_bytes: Maximum number of bytes to include in the dump
            title: Optional title for the hex dump

        Returns:
            String containing formatted hexdump
        """
        display_len = min(max_bytes, self.data_length)
        data = self.mm[self.data_offset:self.data_offset + display_len + 4]
        return make_hex_dump(data, title=title or f"Bank Data at offset 0x{self.data_offset:X}")

    def __str__(self) -> str:
        """Return string representation of the bank header."""
        return f"""Bank (0x{self.tag:04x}, {self.type_name}):
  Offset:    0x{self.offset:08x}
  Length:    {self.length} words ({self.length * 4} bytes)
  Tag:       0x{self.tag:04x}
  Pad:       {self.pad}
  Data Type: 0x{self.data_type:02x}
  Num:       {self.num}"""

    def __repr__(self) -> str:
        """Return a string representation for debugging."""
        return f"Bank(offset=0x{self.offset:X}, tag=0x{self.tag:04X}, type=0x{self.data_type:02X})"
