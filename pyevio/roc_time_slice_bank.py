import mmap
import struct
from datetime import datetime
from typing import Optional, List

from pyevio.bank import Bank


class RocTimeSliceBank:
    """
    Class for parsing and analyzing RocTimeSliceBank (tag: 0xFF30) data.
    """

    # ROC Time Slice Bank tag
    TAG = 0xFF30

    def __init__(self, buffer: mmap.mmap, offset: int, endian: str = '<'):
        """
        Initialize a RocTimeSliceBank parser.

        Args:
            buffer: Memory-mapped buffer
            offset: Byte offset where the bank starts
            endian: Endianness ('<' for little endian, '>' for big endian)
        """
        self.buffer = buffer
        self.offset = offset
        self.endian = endian

        # Parse bank header
        self.bank = Bank.from_buffer(buffer, offset, endian)

        # Validate that this is indeed a ROC Time Slice Bank
        if self.bank.tag != self.TAG:
            raise ValueError(f"Not a ROC Time Slice Bank: tag = 0x{self.bank.tag:04x}, expected 0x{self.TAG:04x}")

        # Data starts after bank header
        self.data_offset = offset + 8

        # Parse timestamp and channel data
        self._parse_data()

    def _parse_data(self):
        """Parse the bank data to extract timestamp and channel data"""
        # The first 64 bits in the data section should be the timestamp
        if self.endian == '<':
            self.timestamp = struct.unpack('<Q', self.buffer[self.data_offset:self.data_offset+8])[0]
        else:
            self.timestamp = struct.unpack('>Q', self.buffer[self.data_offset:self.data_offset+8])[0]

        # Rest of the data is channel waveforms, typically uint16 arrays
        # For now, we'll just provide access to the raw data
        self.data_start = self.data_offset + 8
        self.data_length = (self.bank.length * 4) - 8  # Length in bytes after timestamp

    def get_channel_data(self, channel: int) -> Optional[List[int]]:
        """
        Get data for a specific channel.

        Args:
            channel: Channel number

        Returns:
            List of data points or None if channel not found
        """
        # This is a placeholder - actual implementation depends on
        # the exact format of how channels are stored
        # TODO: Implement channel data extraction based on format specification
        return None

    def to_numpy(self, dtype=None):
        """
        Convert bank data to NumPy array.

        Args:
            dtype: NumPy data type (default: determined based on bank_type)

        Returns:
            NumPy array containing the data
        """
        import numpy as np

        # Determine dtype if not provided
        if dtype is None:
            if self.bank.data_type == 0x1:  # 32-bit unsigned int
                dtype = np.uint32
            elif self.bank.data_type == 0x2:  # 32-bit float
                dtype = np.float32
            elif self.bank.data_type == 0x4:  # 16-bit signed short
                dtype = np.int16
            elif self.bank.data_type == 0x5:  # 16-bit unsigned short
                dtype = np.uint16
            elif self.bank.data_type == 0x6:  # 8-bit signed char
                dtype = np.int8
            elif self.bank.data_type == 0x7:  # 8-bit unsigned char
                dtype = np.uint8
            elif self.bank.data_type == 0x8:  # 64-bit double
                dtype = np.float64
            elif self.bank.data_type == 0x9:  # 64-bit signed int
                dtype = np.int64
            elif self.bank.data_type == 0xa:  # 64-bit unsigned int
                dtype = np.uint64
            elif self.bank.data_type == 0xb:  # 32-bit signed int
                dtype = np.int32
            else:
                raise ValueError(f"Unsupported bank type for NumPy conversion: 0x{self.bank.data_type:x}")

        # For FADC250 data - typically uint16
        if dtype == np.uint16:
            # Skip the timestamp (8 bytes) and convert the rest
            data = np.frombuffer(
                self.buffer[self.data_start:self.data_start + self.data_length],
                dtype=dtype
            )
            return data
        else:
            raise NotImplementedError(f"Conversion to {dtype} not implemented yet")

    def __str__(self) -> str:
        """Return string representation of the bank"""
        seconds = self.timestamp / 10**9  # Assuming nanoseconds
        timestamp_str = datetime.fromtimestamp(seconds).strftime('%Y-%m-%d %H:%M:%S.%f')

        return f"""ROC Time Slice Bank (0x{self.TAG:04x}):
  Bank Length:    {self.bank.length} words ({self.bank.length * 4} bytes)
  Bank Tag:       0x{self.bank.tag:04x}
  Bank Pad:       {self.bank.pad}
  Bank Type:      0x{self.bank.data_type:02x}
  Bank Num:       {self.bank.num}
  Timestamp:      {self.timestamp} ({timestamp_str})
  Data Length:    {self.data_length} bytes"""
