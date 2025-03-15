import mmap
import os
import struct
from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime

from pyevio.bank import Bank
from pyevio.file_header import FileHeader
from pyevio.record_header import RecordHeader
from pyevio.utils import make_hex_dump


class EvioFile:
    """
    Main class for handling EVIO v6 files. Manages file resources and provides
    methods for navigating through the file structure.
    """

    def __init__(self, filename: str, verbose: bool):
        """
        Initialize EvioFile object with a file path.

        Args:
            filename: Path to the EVIO file
        """
        self.verbose = verbose
        self.filename = filename
        self.file = open(filename, 'rb')
        self.file_size = os.path.getsize(filename)
        # Memory map the file for efficient access
        self.mm = mmap.mmap(self.file.fileno(), 0, access=mmap.ACCESS_READ)

        # Will be populated by scan_structure
        self.header = None
        self.record_offsets = []

        # Scan file structure upon initialization
        self.scan_structure()

    def __del__(self):
        """Cleanup resources when object is destroyed"""
        try:
            if hasattr(self, 'mm') and self.mm and not getattr(self.mm, 'closed', True):
                self.mm.close()
            if hasattr(self, 'file') and self.file and not self.file.closed:
                self.file.close()
        except (ValueError, AttributeError):
            # Ignore errors during cleanup
            pass

    def __enter__(self):
        """Support for context manager protocol"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Cleanup when exiting context"""
        self.__del__()

    def scan_structure(self):
        """
        Scan file structure, parse the file header, and identify record offsets
        by sequentially navigating through the file structure.
        """
        offset = 0  # Start at the beginning of the file

        # 1. Parse file header
        self.header = FileHeader.from_buffer(self.mm, offset)
        offset += self.header.header_length * 4  # Move past file header (length in bytes)

        # 2. Skip index array if present
        if self.header.index_array_length > 0:
            offset += self.header.index_array_length

        # 3. Skip user header if present
        if self.header.user_header_length > 0:
            offset += self.header.user_header_length

        # 4. Parse records sequentially
        while offset < self.file_size:
            try:
                # Store this record's position
                self.record_offsets.append(offset)

                # Parse record header
                record_header = self.scan_record(self.mm, offset)

                # Move to next record
                offset += record_header.record_length * 4  # Length in bytes

                # Stop if this was the last record
                if record_header.is_last_record:
                    break

            except Exception as e:
                print(f"Error scanning record at offset 0x{offset:X}: {e}")
                print(make_hex_dump(self.mm[offset:offset+64], title="Data dump at this offset"))
                raise

    @staticmethod
    def scan_record(mm: mmap.mmap, offset: int) -> RecordHeader:
        """
        Scan a record at the given offset and return its header.

        Args:
            mm: Memory-mapped file
            offset: Byte offset where the record starts

        Returns:
            RecordHeader object
        """
        return RecordHeader.from_buffer(mm, offset)

    def find_record(self, index: int) -> Tuple[int, int]:
        """
        Find a record by index and return its data offsets.

        Args:
            index: Record index (0-based)

        Returns:
            Tuple of (start_offset, end_offset) for the record data
        """
        if index < 0 or index >= len(self.record_offsets):
            raise IndexError(f"Record index {index} out of range (0-{len(self.record_offsets)-1})")

        record_start = self.record_offsets[index]
        record_header = self.scan_record(self.mm, record_start)

        # Calculate data start (after record header)
        data_start = record_start + record_header.header_length * 4

        # Skip over index array
        data_start += record_header.index_array_length

        # Skip over user header if present
        data_start += record_header.user_header_length

        # Calculate data end
        if index < len(self.record_offsets) - 1:
            data_end = self.record_offsets[index + 1]
        else:
            data_end = record_start + record_header.record_length * 4

        return data_start, data_end

    def parse_first_bank_header(self, record_index: int) -> Bank:
        """
        Parse the first bank header within a record.

        Args:
            record_index: Record index (0-based)

        Returns:
            Bank object with header information
        """
        data_start, _ = self.find_record(record_index)
        return Bank.from_buffer(self.mm, data_start, self.header.endian)

