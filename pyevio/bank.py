import mmap
import os
import struct
from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime


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
    """

    def __init__(self):
        super().__init__()

    @classmethod
    def from_buffer(cls, buffer: mmap.mmap, offset: int, endian: str = '<') -> 'Bank':
        """Parse a Bank from memory-mapped buffer."""
        bank = cls()
        bank.offset = offset

        # Parse 2-word header
        bank.length = struct.unpack(endian + 'I', buffer[offset:offset+4])[0]
        bank_info = struct.unpack(endian + 'I', buffer[offset+4:offset+8])[0]

        # Unpack bank info
        bank.tag = (bank_info >> 16) & 0xFFFF
        bank.pad = (bank_info >> 14) & 0x3
        bank.data_type = (bank_info >> 8) & 0x3F
        bank.num = bank_info & 0xFF

        # Determine special bank types by tag
        if (bank.tag & 0xFF00) == 0xFF00:
            tag_type = bank.tag & 0x00FF
            if (tag_type & 0x10) == 0x10:
                bank.type_name = "RocRawDataRecord"
            elif tag_type == 0x30:
                bank.type_name = "RocTimeSliceBank"
            elif tag_type == 0x31:
                bank.type_name = "PhysicsEvent"

        return bank

    def __str__(self) -> str:
        """Return string representation of the bank header."""
        return f"""Bank Header:
  Offset:    0x{self.offset:08x}
  Length:    {self.length} words ({self.length * 4} bytes)
  Tag:       0x{self.tag:04x} ({self.type_name})
  Pad:       {self.pad}
  Data Type: 0x{self.data_type:02x}
  Num:       {self.num}"""
