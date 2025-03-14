import mmap
import os
import struct
from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime

from pyevio.utils import make_hex_dump


class FileHeader:
    """
    Parses and represents an EVIO v6 file header.
    """

    # EVIO magic number and bytes
    MAGIC_BYTES = b'EVIO'
    MAGIC_NUMBER = 0xc0da0100

    # Size of file header in bytes
    HEADER_SIZE = 56  # 14 words * 4 bytes

    def __init__(self):
        """Initialize an empty FileHeader object"""
        self.file_type_id = None
        self.file_number = None
        self.header_length = None
        self.record_count = None
        self.index_array_length = None
        self.bit_info = None
        self.version = None
        self.user_header_length = None
        self.magic_number = None
        self.user_register = None
        self.trailer_position = None
        self.user_integer1 = None
        self.user_integer2 = None

        # Derived properties
        self.endian = '<'  # Default to little endian
        self.has_dictionary = False
        self.has_first_event = False
        self.has_trailer = False

    @staticmethod
    def from_buffer(buffer: mmap.mmap, offset: int = 0) -> 'FileHeader':
        """
        Parse FileHeader from a memory-mapped buffer.

        Args:
            buffer: Memory-mapped buffer
            offset: Byte offset where the header starts

        Returns:
            FileHeader object
        """
        header = FileHeader()

        # Try little endian first
        endian = '<'

        # Read header fields
        header.file_type_id = struct.unpack(endian + 'I', buffer[offset:offset+4])[0]

        # Check if the file type is EVIO (ASCII for "EVIO" is 0x4556494F)
        if header.file_type_id != 0x4556494F:
            # Try big endian if little endian didn't work
            endian = '>'
            header.file_type_id = struct.unpack(endian + 'I', buffer[offset:offset+4])[0]

            # If still not EVIO, raise error
            if header.file_type_id != 0x4556494F:
                raise ValueError(f"Invalid EVIO file: file_type_id = 0x{header.file_type_id:08x}, expected 0x4556494F")

        header.endian = endian

        # Continue parsing with detected endianness
        header.file_number = struct.unpack(endian + 'I', buffer[offset+4:offset+8])[0]
        header.header_length = struct.unpack(endian + 'I', buffer[offset+8:offset+12])[0]
        header.record_count = struct.unpack(endian + 'I', buffer[offset+12:offset+16])[0]
        header.index_array_length = struct.unpack(endian + 'I', buffer[offset+16:offset+20])[0]

        bit_info_version = struct.unpack(endian + 'I', buffer[offset+20:offset+24])[0]
        header.bit_info = bit_info_version >> 8
        header.version = bit_info_version & 0xFF

        header.user_header_length = struct.unpack(endian + 'I', buffer[offset+24:offset+28])[0]
        header.magic_number = struct.unpack(endian + 'I', buffer[offset+28:offset+32])[0]

        # 64-bit values
        if endian == '<':
            header.user_register = struct.unpack('<Q', buffer[offset+32:offset+40])[0]
            header.trailer_position = struct.unpack('<Q', buffer[offset+40:offset+48])[0]
        else:
            header.user_register = struct.unpack('>Q', buffer[offset+32:offset+40])[0]
            header.trailer_position = struct.unpack('>Q', buffer[offset+40:offset+48])[0]

        header.user_integer1 = struct.unpack(endian + 'I', buffer[offset+48:offset+52])[0]
        header.user_integer2 = struct.unpack(endian + 'I', buffer[offset+52:offset+56])[0]

        # Validate header
        if header.version != 6:
            raise ValueError(f"Unsupported EVIO version: {header.version}, expected 6")

        if header.magic_number != FileHeader.MAGIC_NUMBER:
            raise ValueError(f"Invalid magic number: 0x{header.magic_number:08x}, expected 0x{FileHeader.MAGIC_NUMBER:08x}")

        # Parse bit_info fields
        header.has_dictionary = bool((header.bit_info >> 0) & 1)  # Bit 8
        header.has_first_event = bool((header.bit_info >> 1) & 1)  # Bit 9
        header.has_trailer = bool((header.bit_info >> 2) & 1)  # Bit 10

        return header

    def get_hex_dump(self, buffer: mmap.mmap, offset: int = 0) -> str:
        """ Generate a hex dump of the raw header bytes.

        Args:
            buffer: Memory-mapped buffer containing the header
            offset: Byte offset where the header starts

        Returns:
            String containing formatted hexdump
        """
        # Extract the bytes for the header
        header_bytes = buffer[offset:offset + self.HEADER_SIZE]
        return make_hex_dump(header_bytes, chunk_size=4, title="File Header Hex Dump")

    def __str__(self) -> str:
        """Return string representation of the header"""
        endian_str = "Little Endian" if self.endian == '<' else "Big Endian"

        return f"""EVIO File Header:
  Magic Number:      0x{self.magic_number:08x}
  Version:           {self.version}
  Endianness:        {endian_str}
  File Type ID:      0x{self.file_type_id:08x} ({"EVIO" if self.file_type_id == 0x4556494F else "Unknown"})
  File Number:       {self.file_number}
  Header Length:     {self.header_length} words ({self.header_length * 4} bytes)
  Record Count:      {self.record_count}
  Index Array Len:   {self.index_array_length} bytes
  User Header Len:   {self.user_header_length} bytes
  Has Dictionary:    {self.has_dictionary}
  Has First Event:   {self.has_first_event}
  Has Trailer:       {self.has_trailer}
  Trailer Position:  0x{self.trailer_position:016x}
  User Register:     0x{self.user_register:016x}
  User Integer 1:    {self.user_integer1}
  User Integer 2:    {self.user_integer2}"""
