import mmap
import os
import struct
from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime

from pyevio.utils import make_hex_dump


class RecordHeader:
    """
    Parses and represents an EVIO v6 record header.
    """

    # EVIO record header magic number
    MAGIC_NUMBER = 0xc0da0100

    # Size of record header in bytes
    HEADER_SIZE = 56  # 14 words * 4 bytes

    def __init__(self):
        """Initialize an empty RecordHeader object"""
        self.record_length = None
        self.record_number = None
        self.header_length = None
        self.event_count = None
        self.index_array_length = None
        self.bit_info = None
        self.version = None
        self.user_header_length = None
        self.magic_number = None
        self.uncompressed_data_length = None
        self.compression_type = None
        self.compressed_data_length = None
        self.user_register1 = None
        self.user_register2 = None

        # Derived properties
        self.endian = '<'  # Default to little endian
        self.is_last_record = False
        self.has_dictionary = False
        self.has_first_event = False
        self.event_type = None

    @classmethod
    def from_buffer(cls, buffer: mmap.mmap, offset: int = 0) -> 'RecordHeader':
        """
        Parse RecordHeader from a memory-mapped buffer.

        Args:
            buffer: Memory-mapped buffer
            offset: Byte offset where the header starts

        Returns:
            RecordHeader object
        """
        header = cls()

        # Try little endian first
        endian = '<'

        # Read first few fields
        header.record_length = struct.unpack(endian + 'I', buffer[offset:offset+4])[0]
        header.record_number = struct.unpack(endian + 'I', buffer[offset+4:offset+8])[0]
        header.header_length = struct.unpack(endian + 'I', buffer[offset+8:offset+12])[0]

        # Validate header length
        if header.header_length < 14:
            # Try big endian
            endian = '>'
            header.record_length = struct.unpack(endian + 'I', buffer[offset:offset+4])[0]
            header.record_number = struct.unpack(endian + 'I', buffer[offset+4:offset+8])[0]
            header.header_length = struct.unpack(endian + 'I', buffer[offset+8:offset+12])[0]

            if header.header_length < 14:
                raise ValueError(f"Invalid record header length: {header.header_length}, expected at least 14")

        header.endian = endian

        # Continue parsing with detected endianness
        header.event_count = struct.unpack(endian + 'I', buffer[offset+12:offset+16])[0]
        header.index_array_length = struct.unpack(endian + 'I', buffer[offset+16:offset+20])[0]

        bit_info_version = struct.unpack(endian + 'I', buffer[offset+20:offset+24])[0]
        header.bit_info = bit_info_version >> 8
        header.version = bit_info_version & 0xFF

        header.user_header_length = struct.unpack(endian + 'I', buffer[offset+24:offset+28])[0]
        header.magic_number = struct.unpack(endian + 'I', buffer[offset+28:offset+32])[0]

        header.uncompressed_data_length = struct.unpack(endian + 'I', buffer[offset+32:offset+36])[0]

        compression_data = struct.unpack(endian + 'I', buffer[offset+36:offset+40])[0]
        header.compression_type = (compression_data >> 28) & 0xF
        header.compressed_data_length = compression_data & 0x0FFFFFFF

        # 64-bit values
        if endian == '<':
            header.user_register1 = struct.unpack('<Q', buffer[offset+40:offset+48])[0]
            header.user_register2 = struct.unpack('<Q', buffer[offset+48:offset+56])[0]
        else:
            header.user_register1 = struct.unpack('>Q', buffer[offset+40:offset+48])[0]
            header.user_register2 = struct.unpack('>Q', buffer[offset+48:offset+56])[0]

        # Validate header
        if header.version != 6:
            raise ValueError(f"Unsupported EVIO version in record: {header.version}, expected 6")

        if header.magic_number != cls.MAGIC_NUMBER:
            raise ValueError(f"Invalid record magic number: 0x{header.magic_number:08x}, expected 0x{cls.MAGIC_NUMBER:08x}")

        # Parse bit_info fields
        header.has_dictionary = bool((header.bit_info >> 0) & 1)  # Bit 8
        header.is_last_record = bool((header.bit_info >> 1) & 1)  # Bit 9

        # Extract event type (bits 10-13)
        event_type_code = (header.bit_info >> 2) & 0xF
        event_types = {
            0: "ROC Raw",
            1: "Physics",
            2: "Partial Physics",
            3: "Disentangled Physics",
            4: "User",
            5: "Control",
            6: "Mixed",
            8: "ROC Raw Streaming",
            9: "Physics Streaming",
            15: "Other"
        }
        header.event_type = event_types.get(event_type_code, f"Unknown ({event_type_code})")

        header.has_first_event = bool((header.bit_info >> 6) & 1)  # Bit 14

        return header

    def get_hex_dump(self, buffer: mmap.mmap, offset: int = 0) -> str:
        """
        Generate a hex dump of the raw header bytes.

        Args:
            buffer: Memory-mapped buffer containing the header
            offset: Byte offset where the header starts

        Returns:
            String containing formatted hexdump
        """
        # Extract the bytes for the header
        header_bytes = buffer[offset:offset + self.HEADER_SIZE]
        return make_hex_dump(header_bytes, chunk_size=4, title="Record Header Hex Dump")

    def __str__(self) -> str:
        """Return string representation of the header"""
        endian_str = "Little Endian" if self.endian == '<' else "Big Endian"
        compression_types = {
            0: "None",
            1: "LZ4 (fast)",
            2: "LZ4 (best)",
            3: "gzip"
        }
        compression_str = compression_types.get(self.compression_type, f"Unknown ({self.compression_type})")

        return f"""EVIO Record Header:
  Magic Number:         0x{self.magic_number:08x}
  Version:              {self.version}
  Endianness:           {endian_str}
  Record Length:        {self.record_length} words ({self.record_length * 4} bytes)
  Record Number:        {self.record_number}
  Header Length:        {self.header_length} words ({self.header_length * 4} bytes)
  Event Count:          {self.event_count}
  Index Array Length:   {self.index_array_length} bytes
  User Header Length:   {self.user_header_length} bytes
  Event Type:           {self.event_type}
  Is Last Record:       {self.is_last_record}
  Has Dictionary:       {self.has_dictionary}
  Has First Event:      {self.has_first_event}
  Uncompressed Length:  {self.uncompressed_data_length} bytes
  Compression:          {compression_str}
  Compressed Length:    {self.compressed_data_length} words ({self.compressed_data_length * 4} bytes)
  User Register 1:      0x{self.user_register1:016x}
  User Register 2:      0x{self.user_register2:016x}"""
