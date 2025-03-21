import mmap
import struct
from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime

from pyevio.record_header import RecordHeader
from pyevio.utils import make_hex_dump


class Record:
    """
    Represents a record in an EVIO file.

    A record contains a header followed by an event index array, optional user header,
    and multiple events. This class provides methods to access and parse the record
    structure efficiently.
    """

    def __init__(self, mm: mmap.mmap, offset: int, endian: str = '<'):
        """
        Initialize a Record object.

        Args:
            mm: Memory-mapped file containing the record
            offset: Byte offset in the file where the record starts
            endian: Endianness ('<' for little endian, '>' for big endian)
        """
        self.mm = mm
        self.offset = offset
        self.endian = endian

        # Parse the record header
        self.header = RecordHeader.parse(mm, offset)

        # Calculate key positions in the record
        self.header_size = self.header.header_length * 4
        self.index_start = self.offset + self.header_size
        self.index_end = self.index_start + self.header.index_array_length
        self.data_start = self.index_end + self.header.user_header_length
        self.data_end = self.offset + (self.header.record_length * 4)
        self.size = self.header.record_length * 4

        # Cache for events (will be populated on demand)
        self._events = None
        self._event_count = None

    @property
    def event_count(self) -> int:
        """Get the number of events in this record."""
        if self._event_count is None:
            self._event_count = self.header.event_count
        return self._event_count

    def scan_events(self) -> List[Tuple[int, int]]:
        """
        Scan and parse all events in this record.

        Returns:
            List of tuples (offset, length) for all events in the record
        """
        event_info = []

        if self.header.index_array_length > 0:
            # Parse events from index array
            event_count = self.header.index_array_length // 4
            current_offset = self.data_start

            for i in range(event_count):
                length_offset = self.index_start + (i * 4)
                event_length = struct.unpack(self.endian + 'I',
                                             self.mm[length_offset:length_offset+4])[0]

                # Store event offset and length
                event_info.append((current_offset, event_length))

                # Update cumulative offset for next event
                current_offset += event_length

        return event_info

    def get_events(self):
        """
        Get all events in this record.

        Returns:
            List of Event objects
        """
        if self._events is None:
            from pyevio.event import Event  # Import here to avoid circular import

            event_info = self.scan_events()
            self._events = [
                Event(self.mm, offset, length, self.endian, i)
                for i, (offset, length) in enumerate(event_info)
            ]

        return self._events

    def get_event(self, index: int):
        """
        Get an event by index within this record.

        Args:
            index: Event index (0-based)

        Returns:
            Event object

        Raises:
            IndexError: If index is out of range
        """
        events = self.get_events()

        if index < 0 or index >= len(events):
            raise IndexError(f"Event index {index} out of range (0-{len(events)-1})")

        return events[index]

    def get_hex_dump(self, word_count: int = 14, title: Optional[str] = None) -> str:
        """
        Generate a hex dump of the record header.

        Args:
            word_count: Number of 32-bit words to include in the dump
            title: Optional title for the hex dump

        Returns:
            String containing formatted hexdump
        """
        data = self.mm[self.offset:self.offset + min(word_count * 4, self.size)]
        return make_hex_dump(data, title=title or f"Record Header at offset 0x{self.offset:X}")

    def __str__(self) -> str:
        """Return a string representation of this record."""
        return f"Record at offset 0x{self.offset:X} with {self.event_count} events"

    def __repr__(self) -> str:
        """Return a string representation for debugging."""
        return f"Record(offset=0x{self.offset:X}, size={self.size}, events={self.event_count})"