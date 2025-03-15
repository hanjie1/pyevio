from pyevio.buffer_reader import BufferReader


class RecordHeader:
    """Parses and represents an EVIO v6 record header."""

    # EVIO record header magic number
    MAGIC_NUMBER = 0xc0da0100

    # Size of record header in bytes
    HEADER_SIZE = 56  # 14 words * 4 bytes

    def __init__(self):
        """Initialize an empty RecordHeader object"""
        # [Fields initialization as before]

    @staticmethod
    def from_buffer(buffer, offset=0):
        """
        Parse a RecordHeader from a memory-mapped buffer.
        
        Args:
            buffer: Memory-mapped buffer containing EVIO data
            offset: Byte offset where the record header starts
            
        Returns:
            RecordHeader object with parsed data
        """
        header = RecordHeader()
        reader = BufferReader(buffer, offset)

        # Basic header fields (already validated in reader initialization)
        header.record_length = reader.read_uint32(0)
        header.record_number = reader.read_uint32(1)
        header.header_length = reader.read_uint32(2)
        header.endian = reader.endian

        # Read remaining fields
        header.event_count = reader.read_uint32(3)
        header.index_array_length = reader.read_uint32(4)

        bit_info_version = reader.read_uint32(5)
        header.version = bit_info_version & 0xFF
        header.bit_info = (bit_info_version >> 8) & 0xFFFFFF

        header.user_header_length = reader.read_uint32(6)
        header.magic_number = reader.read_uint32(7)

        header.uncompressed_data_length = reader.read_uint32(8)

        compression_data = reader.read_uint32(9)
        header.compression_type = (compression_data >> 28) & 0xF
        header.compressed_data_length = compression_data & 0x0FFFFFFF

        # 64-bit values
        header.user_register1 = reader.read_uint64(10)  # Words 10-11
        header.user_register2 = reader.read_uint64(12)  # Words 12-13

        # Validate header
        if header.version != 6:
            print(f"Record version validation failed: got {header.version}, expected 6")
            print(f"bit_info_version raw value: 0x{bit_info_version:08X}")
            print(reader.hex_dump())
            raise ValueError(f"Unsupported EVIO version in record: {header.version}, expected 6")

        if header.magic_number != RecordHeader.MAGIC_NUMBER:
            print(reader.hex_dump())
            raise ValueError(f"Invalid record magic number: 0x{header.magic_number:08x}, expected 0x{RecordHeader.MAGIC_NUMBER:08x}")

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