import logging
import struct
from collections import namedtuple

MAGIC_V4 = 0xc0da0100

# For v4 extended block header (CODA 3.11 streaming mode)
ExtendedBlockHeaderV4 = namedtuple("ExtendedBlockHeaderV4", [
    "block_length",     # total words in block
    "block_number",
    "header_length",    # can be longer than 8 in streaming mode
    "event_count",
    "bitinfo_version",  # bits plus version in lowest 8 bits
    "reserved_words",   # list of any additional words in header
    "magic",
])

def parse_file(filename, format_override=None, raw_mode=False, prefer_vtp=False):
    """
    Enhanced version that handles various EVIO formats including streaming mode with extended headers.
    Also supports specialized VTP data format parsing.

    Args:
        filename: Path to the file to parse
        format_override: Force a specific format ('v4', 'v6', 'streaming', 'streaming14', 'vtp')
        raw_mode: If True, don't validate event format, just extract by size
        prefer_vtp: If True, try to parse as VTP data first

    Returns:
        List of events
    """
    logger = logging.getLogger(__name__)
    logger.debug(f"parse_file({filename}): detecting EVIO version")

    # Special case for VTP format
    if format_override == 'vtp' or prefer_vtp:
        logger.debug("Trying to parse as specialized VTP format")
        return parse_vtp_file(filename, raw_mode)

    # First, check if format is being forced
    if format_override is not None:
        logger.debug(f"Format override requested: {format_override}")

        if format_override == 'streaming14':
            # Force CODA 3.11 streaming format with 14-word headers
            logger.debug("Forcing CODA 3.11 streaming format with 14-word headers")
            return parse_streaming_file(filename, 14, True, raw_mode)

        elif format_override == 'raw':
            # Force raw mode with default header length
            logger.debug("Forcing raw mode with default header length")
            return parse_streaming_file(filename, 14, True, True)

        elif format_override.startswith('raw'):
            # Format like "raw14" for raw mode with specified header length
            try:
                header_len = int(format_override[3:])
                logger.debug(f"Forcing raw mode with header length {header_len}")
                return parse_streaming_file(filename, header_len, True, True)
            except ValueError:
                logger.debug("Invalid raw header length, using default 14")
                return parse_streaming_file(filename, 14, True, True)

        elif format_override == 'streaming':
            # Auto-detect header length but force streaming format
            with open(filename, "rb") as f:
                peek = f.read(64)
                # Try to detect header length from the data
                header_len = int.from_bytes(peek[8:12], 'big')
                if 8 < header_len < 100:
                    logger.debug(f"Forcing streaming format with detected header length: {header_len}")
                    return parse_streaming_file(filename, header_len, True, raw_mode)
                else:
                    # Default to 14-word headers if detection fails
                    logger.debug("Forcing streaming format with default 14-word headers")
                    return parse_streaming_file(filename, 14, True, raw_mode)

        elif format_override == 'v4':
            logger.debug("Forcing standard EVIO v4 format")
            return parse_v4_file(filename)

        elif format_override == 'v6':
            logger.debug("Forcing EVIO v6 format")
            return parse_v6_file(filename)

    # Try VTP format first if preferred
    if prefer_vtp:
        try:
            events = parse_vtp_file(filename, raw_mode)
            if events and len(events) > 0:
                logger.debug(f"Successfully parsed as VTP format: {len(events)} events")
                return events
        except Exception as e:
            logger.debug(f"VTP parsing failed: {e}, falling back to standard methods")

    # If we get here, just try the streaming format with reasonable defaults
    logger.debug("No valid format specified, trying streaming format with header_length=14")
    return parse_streaming_file(filename, 14, True, raw_mode)


def parse_vtp_file(filename, raw_mode=False):
    """
    Parse a file as VTP data, which doesn't strictly follow EVIO format.
    This is specialized for VTP streaming data with FADC frames.

    Args:
        filename: Path to the file to parse
        raw_mode: If True, use even more relaxed parsing

    Returns:
        List of events
    """
    logger = logging.getLogger(__name__)
    logger.debug(f"Parsing as VTP format")

    events = []

    # Common event sizes for VTP data based on observations
    common_sizes = [356, 84, 4, 20, 12]

    with open(filename, "rb") as f:
        # Get file size
        f.seek(0, 2)
        file_size = f.tell()
        f.seek(0)

        # Read a sample to detect patterns
        sample = f.read(4096)
        f.seek(0)

        # Try to detect the event pattern
        pattern_size = None

        # First check for the common 58-byte pattern seen in the sample data
        if sample.find(b'\x00\x00\x00\x58') == 0:
            logger.debug("Detected potential VTP pattern with 0x58 word size")
            pattern_size = 356  # Based on the sample output

        # Try detecting other patterns if needed
        if pattern_size is None:
            # Look for repeating patterns in the first chunk of data
            for size in common_sizes:
                if len(sample) >= size * 2 and sample[:size] == sample[size:size*2]:
                    pattern_size = size
                    logger.debug(f"Detected repeating pattern of size {size} bytes")
                    break

        if pattern_size is None:
            # Default to a common size if no pattern detected
            pattern_size = 356  # Default from sample data
            logger.debug(f"Using default pattern size: {pattern_size}")

        # Skip header - common for VTP data to have a header before events
        header_size = 14 * 4  # Default: 14 words
        f.seek(header_size)

        # Read events in fixed-size blocks
        while True:
            event_data = f.read(pattern_size)
            if not event_data or len(event_data) < pattern_size:
                break

            events.append(event_data)

            # Print progress for large files
            if len(events) % 10000 == 0:
                logger.debug(f"Extracted {len(events)} events so far")

    logger.debug(f"Total VTP events extracted: {len(events)}")
    return events


def parse_v4_file(filename):
    """Parse a standard EVIO v4 format file."""
    logger = logging.getLogger(__name__)

    events = []
    with open(filename, "rb") as f:
        while True:
            try:
                # Read block header
                header = f.read(32)
                if len(header) < 32:
                    break  # End of file

                # Determine endianness
                magic_be = int.from_bytes(header[28:32], 'big')
                magic_le = int.from_bytes(header[28:32], 'little')

                if magic_be == MAGIC_V4:
                    endian = 'big'
                elif magic_le == MAGIC_V4:
                    endian = 'little'
                else:
                    raise ValueError("Invalid magic number in block header")

                # Parse block header
                block_len = int.from_bytes(header[0:4], endian)
                block_num = int.from_bytes(header[4:8], endian)
                header_len = int.from_bytes(header[8:12], endian)
                event_count = int.from_bytes(header[12:16], endian)

                logger.debug(f"Block: len={block_len}, num={block_num}, headerLen={header_len}, events={event_count}")

                # Skip any extra header words
                if header_len > 8:
                    f.read(4 * (header_len - 8))

                # Read events in this block
                for _ in range(event_count):
                    event_len_bytes = f.read(4)
                    if len(event_len_bytes) < 4:
                        break

                    event_len = int.from_bytes(event_len_bytes, endian)
                    event_bytes = event_len_bytes + f.read(4 * event_len)
                    events.append(event_bytes)

            except EOFError:
                break

    logger.debug(f"Total events found in v4 format: {len(events)}")
    return events


def parse_v6_file(filename):
    """Parse an EVIO v6 format file."""
    logger = logging.getLogger(__name__)
    logger.debug("Parsing EVIO v6 format not implemented")
    return []  # Not implemented for this simple fix


def parse_streaming_file(filename, header_length, is_big_endian, raw_mode=False):
    """
    Parse a CODA 3.11 streaming format file with extended headers.

    Args:
        filename: Path to the file to parse
        header_length: Length of the header in 32-bit words
        is_big_endian: Whether file is in big-endian format
        raw_mode: If True, don't validate format, just extract by size

    Returns:
        List of events
    """
    logger = logging.getLogger(__name__)
    logger.debug(f"Parsing streaming format with header_length={header_length}, big_endian={is_big_endian}, raw_mode={raw_mode}")

    events = []
    byte_order = "big" if is_big_endian else "little"

    with open(filename, "rb") as f:
        file_size = 0
        try:
            # Get file size
            current_pos = f.tell()
            f.seek(0, 2)  # Seek to end
            file_size = f.tell()
            f.seek(current_pos)  # Return to original position
        except:
            pass

        while True:
            try:
                # Read the extended block header
                header_bytes = f.read(header_length * 4)
                if len(header_bytes) < header_length * 4:
                    logger.debug("End of file reached")
                    break

                # Enhanced header parsing for raw mode - don't require valid EVIO structure
                if raw_mode:
                    # In raw mode, parse header but don't validate
                    try:
                        # First word often indicates block size
                        block_length = int.from_bytes(header_bytes[0:4], byte_order)

                        # Check for reasonableness - not too small, not larger than file
                        if block_length < header_length or (block_length * 4) > file_size:
                            # If unreasonable, try scanning for a pattern that might indicate events
                            logger.debug(f"Suspicious block length: {block_length}, trying to detect events directly")

                            # Rewind to beginning of file, skipping header
                            f.seek(header_length * 4)

                            # For VTP data, events often have a fixed size pattern
                            # Try detecting by looking for common repeated patterns
                            sample = f.read(4096)
                            f.seek(header_length * 4)  # Reset position

                            # Check for common patterns seen in VTP data
                            pattern_size = None

                            # Common pattern with 0x58 as first word (356 bytes per event)
                            if b'\x00\x00\x00\x58' in sample[:16]:
                                pattern_size = 356
                                logger.debug("Detected 0x58 pattern, assuming 356-byte events")

                            if pattern_size:
                                # Read events in fixed-size chunks
                                current_pos = f.tell()
                                while current_pos + pattern_size <= file_size:
                                    event_data = f.read(pattern_size)
                                    if len(event_data) < pattern_size:
                                        break
                                    events.append(event_data)
                                    current_pos = f.tell()

                                logger.debug(f"Extracted {len(events)} events using pattern detection")
                                break  # Exit the main loop as we've processed the file

                        # Use a more lenient estimate for event count if not valid
                        event_count = int.from_bytes(header_bytes[12:16], byte_order)
                        if event_count <= 0 or event_count > 10000:
                            # Default to a reasonable number based on block size
                            event_count = min(1000, (block_length - header_length) // 2)
                            logger.debug(f"Invalid event count, defaulting to {event_count}")

                    except Exception as e:
                        logger.warning(f"Error parsing header in raw mode: {e}")
                        # Try to continue by assuming default values
                        block_length = (file_size - header_length * 4) // 4
                        event_count = 1000  # Just a guess
                else:
                    # Standard parsing for non-raw mode
                    block_length = int.from_bytes(header_bytes[0:4], byte_order)
                    event_count = int.from_bytes(header_bytes[12:16], byte_order)

                # Log the block information
                block_number = int.from_bytes(header_bytes[4:8], byte_order)
                logger.debug(f"Block: len={block_length}, num={block_number}, events={event_count}")

                # Calculate data bytes to read (total block size minus header size)
                data_bytes = (block_length - header_length) * 4

                # Enhanced sanity check for block length
                if data_bytes <= 0:
                    logger.warning(f"Invalid block data size: {data_bytes} bytes")
                    if raw_mode:
                        # In raw mode, try to recover by using file size as guide
                        data_bytes = file_size - f.tell()
                        logger.debug(f"In raw mode, continuing with {data_bytes} bytes")
                    else:
                        break

                if file_size > 0 and f.tell() + data_bytes > file_size:
                    logger.warning(f"Block size exceeds file size: need {data_bytes}, have {file_size - f.tell()}")
                    # Adjust to read only what's available
                    data_bytes = max(0, file_size - f.tell())

                # Read block data if there's anything to read
                if data_bytes > 0:
                    block_data = f.read(data_bytes)
                    if len(block_data) < data_bytes:
                        logger.warning(f"Short read: expected {data_bytes}, got {len(block_data)}")
                        if len(block_data) == 0:
                            break

                    # If we're in raw mode and having trouble parsing event structures,
                    # try using advanced pattern detection for VTP data
                    if raw_mode and (event_count <= 0 or event_count > 10000):
                        logger.debug("Using advanced pattern detection for events")

                        # For VTP data, common event sizes are multiple of 4 bytes
                        # Check for common patterns like event size is first 32-bit word
                        common_sizes = detect_common_vtp_patterns(block_data)

                        if common_sizes:
                            pattern_size = common_sizes[0]
                            logger.debug(f"Using detected pattern size: {pattern_size}")

                            # Extract events based on the fixed pattern size
                            offset = 0
                            while offset + pattern_size <= len(block_data):
                                events.append(block_data[offset:offset+pattern_size])
                                offset += pattern_size

                            logger.debug(f"Extracted {len(events)} events from block {block_number} using pattern")
                            continue  # Skip to next block

                    # Standard event parsing from the block data
                    # Parse events from the block data
                    offset = 0
                    for i in range(event_count):
                        if offset + 4 > len(block_data):
                            logger.warning(f"Block data truncated before event {i+1} length")
                            break

                        # Read event length (in words - 1)
                        event_len = int.from_bytes(block_data[offset:offset+4], byte_order)
                        event_size = (event_len + 1) * 4  # Total bytes including length word

                        # Validate event size
                        if event_size <= 0 or offset + event_size > len(block_data):
                            # In raw mode, try alternative event extraction
                            if raw_mode:
                                # Many VTP events have a fixed size
                                if offset + 356 <= len(block_data) and block_data[offset:offset+4] == b'\x00\x00\x00\x58':
                                    # This pattern is seen in the sample data
                                    event_data = block_data[offset:offset+356]
                                    events.append(event_data)
                                    offset += 356
                                    continue
                                else:
                                    logger.warning(f"Event {i+1} has invalid size: {event_size} bytes")
                                    break
                            else:
                                logger.warning(f"Event {i+1} truncated: need {event_size}, have {len(block_data) - offset}")
                                break

                        # Extract event and add to list
                        event_data = block_data[offset:offset+event_size]
                        events.append(event_data)
                        offset += event_size

                    logger.debug(f"Extracted {min(event_count, len(events) - (len(events) - i - 1))} events from block {block_number}")

            except Exception as e:
                logger.error(f"Error parsing streaming block: {e}")
                import traceback
                logger.debug(traceback.format_exc())

                if raw_mode:
                    # In raw mode, try to recover by skipping ahead and looking for patterns
                    try:
                        # Skip to a word boundary
                        pos = f.tell()
                        pos = (pos + 3) & ~3  # Align to 4-byte boundary
                        f.seek(pos)

                        # Try to find a recognizable pattern
                        logger.debug("Attempting recovery by pattern detection")
                        chunk = f.read(4096)

                        # Check for VTP pattern
                        vtp_pos = chunk.find(b'\x00\x00\x00\x58')
                        if vtp_pos >= 0:
                            # Found a potential VTP event
                            f.seek(pos + vtp_pos)
                            logger.debug(f"Found potential VTP pattern at offset {pos + vtp_pos}")
                            continue  # Try again with the new position
                    except:
                        # If recovery fails, just break
                        break

                break

    logger.debug(f"Total events extracted: {len(events)}")
    return events


def detect_common_vtp_patterns(data):
    """
    Detect common patterns in VTP data.

    Args:
        data: Raw block data

    Returns:
        List of potential event sizes or empty list if no pattern detected
    """
    if len(data) < 64:
        return []

    # VTP events often have a fixed size, like 356 bytes for a frame with
    # a header of 0x00000058

    # Check for the pattern seen in the sample output
    if data.startswith(b'\x00\x00\x00\x58'):
        return [356]  # Common size seen in sample

    # Try other common sizes in VTP data
    sizes = []

    # Look for repeating patterns of the first word
    for size in [356, 84, 20, 12, 4]:
        if len(data) >= size * 2 and data[:4] == data[size:size+4]:
            sizes.append(size)

    # If no specific pattern found, try general approaches
    if not sizes:
        # Check if dividing by common word sizes gives clean patterns
        for word_size in [89, 64, 32, 16, 8]:
            if len(data) % (word_size * 4) == 0:
                sizes.append(word_size * 4)

    return sizes


def decode_event_structures(event_data, is_big_endian=False):
    """
    Parse an event's raw bytes as an EVIO bank (or container),
    recursively scanning for sub-banks. If we see a known FADC
    tag, decode that data as streaming frames.

    Returns a nested dictionary describing the structure, e.g.:
    {
      "tag": ..., "type": ..., "num": ...,
      "substructures": [...],
      "fadc_frames": [...],
    }
    """
    logger = logging.getLogger(__name__)

    # Special handling for VTP data directly
    # Try to detect VTP event without EVIO structure
    if len(event_data) >= 8:
        # Common pattern for VTP FADC data: first word is 0x00000058
        if event_data[:4] == b'\x00\x00\x00\x58':
            logger.debug("Detected VTP data pattern with 0x58 marker")
            frames = decode_vtp_fadc_frames(event_data, is_big_endian)
            if frames and len(frames) > 0:
                return {
                    "tag": 0xE101,  # Use a standard FADC tag
                    "type": 0x10,   # Bank type
                    "num": 0,
                    "substructures": [],
                    "fadc_frames": frames,
                    "format": "vtp"
                }

    if len(event_data) < 8:
        logger.warning("Event data too short to contain an EVIO bank header.")
        return None

    byte_fmt = ">" if is_big_endian else "<"

    try:
        w0, w1 = struct.unpack(byte_fmt + "2I", event_data[:8])
        length_words = w0
        tag          = (w1 >> 16) & 0xFFFF
        type_val     = (w1 >> 8) & 0x3F
        num          = w1 & 0xFF

        total_bytes = (length_words + 1) * 4
        if total_bytes != len(event_data):
            logger.debug(
                f"Event says length={total_bytes} bytes, but actual= {len(event_data)} bytes. "
                "Could be dictionary or partial event, continuing best-effort parse."
            )

        structures = {
            "tag": tag,
            "type": type_val,
            "num": num,
            "substructures": []
        }

        # Check if this event could be VTP data directly (not in standard EVIO format)
        # For VTP streaming data, try to decode it directly
        if type_val == 0 and len(event_data) > 8:  # Type 0 is unusual in standard EVIO
            payload = event_data[8:]
            frames = decode_vtp_data(payload, is_big_endian)
            if frames and len(frames) > 0:
                structures["fadc_frames"] = frames
                return structures

        # If this is a container type (bank), parse children
        if type_val in (0x10, 0x20):  # 0x10 => BANK, 0x20 => ALSOBANK
            child_offset = 8
            end_offset = len(event_data)

            while child_offset + 8 <= end_offset:
                # read the first word => might be a sub-bank length
                if child_offset + 4 > end_offset:
                    break
                first_word = struct.unpack(byte_fmt + "I", event_data[child_offset:child_offset+4])[0]
                maybe_len = first_word  # # of words minus 1
                sub_size  = (maybe_len + 1) * 4
                if child_offset + sub_size > end_offset:
                    # Possibly a segment or partial
                    break

                sub_data = event_data[child_offset : child_offset+sub_size]
                child_struct = decode_event_structures(sub_data, is_big_endian)
                if child_struct:
                    structures["substructures"].append(child_struct)
                child_offset += sub_size

        else:
            # Leaf structure => if tag is FADC, decode the frames
            if _is_fadc_tag(tag):
                logger.debug(f"FADC sub-bank found: tag=0x{tag:X}, {len(event_data)-8} payload bytes")
                payload = event_data[8:]
                frames  = decode_fadc_frames(payload, is_big_endian)
                structures["fadc_frames"] = frames

        return structures
    except Exception as e:
        logger.warning(f"Error parsing event structure: {e}")
        return {
            "tag": 0,
            "type": 0,
            "num": 0,
            "substructures": [],
            "error": str(e)
        }


def _is_fadc_tag(tag):
    """
    Check if a tag corresponds to fADC data.
    This function supports different fADC tag patterns.
    """
    # Original range check for standard FADC data (0xE100-0xE1FF)
    if (tag & 0xFF00) == 0xE100:
        return True

    # VTP streaming FADC might use different tag values
    if 57000 <= tag <= 57999:  # Example range for VTP
        return True

    # For CODA 3.11 streaming mode, there might be other known tag patterns
    if 0xE000 <= tag <= 0xE0FF:  # Another possible range
        return True

    return False


def decode_vtp_data(payload_bytes, is_big_endian=False):
    """
    Attempt to decode VTP streaming data directly, even if not in standard EVIO format.

    Args:
        payload_bytes: Raw payload data
        is_big_endian: Whether data is in big-endian format

    Returns:
        List of decoded frames if successful, or None if not valid VTP data
    """
    logger = logging.getLogger(__name__)

    # For non-standard VTP data, we need to try different patterns
    # First, check if it follows a consistent pattern we can identify

    frames = []
    byte_fmt = ">" if is_big_endian else "<"

    # If the event starts with multiple words that are the same value,
    # it could be a VTP frame header pattern (seen in your scan output)
    if len(payload_bytes) >= 16:
        first_words = []
        for i in range(0, 16, 4):
            if i + 4 <= len(payload_bytes):
                word = struct.unpack(byte_fmt + "I", payload_bytes[i:i+4])[0]
                first_words.append(word)

        # Check if all first words are identical (suggests a pattern)
        if len(first_words) >= 4 and all(w == first_words[0] for w in first_words):
            logger.debug(f"Detected possible VTP data pattern, word value: 0x{first_words[0]:08x}")

            # Try to extract data in chunks of 4 or 8 bytes
            frame_size = 8  # Try 8-byte frames first
            offset = 0

            while offset + frame_size <= len(payload_bytes):
                try:
                    if frame_size == 8:
                        w0 = struct.unpack(byte_fmt + "I", payload_bytes[offset:offset+4])[0]
                        w1 = struct.unpack(byte_fmt + "I", payload_bytes[offset+4:offset+8])[0]

                        # Basic format for 8-byte frame
                        frames.append({
                            "word0": w0,
                            "word1": w1,
                            # Extract some potential fields - adapted for VTP data
                            "slot": (w0 >> 24) & 0xFF,
                            "channel": (w0 >> 16) & 0xFF,
                            "timestamp": w0 & 0xFFFF,
                            "adc": w1
                        })
                    else:
                        # 4-byte frame format
                        word = struct.unpack(byte_fmt + "I", payload_bytes[offset:offset+4])[0]
                        frames.append({"word": word})

                except Exception:
                    break

                offset += frame_size

            if len(frames) > 0:
                logger.debug(f"Decoded {len(frames)} frames from VTP data")
                return frames

    # If we couldn't decode it as VTP data, return None
    return None


def decode_vtp_fadc_frames(event_data, is_big_endian=False):
    """
    Specialized decoder for VTP event data with FADC frames.
    This handles the pattern where the entire event is a sequence of frames.

    Args:
        event_data: Raw event bytes (including any header)
        is_big_endian: Whether to interpret as big-endian

    Returns:
        List of decoded frames
    """
    logger = logging.getLogger(__name__)
    frames = []
    byte_fmt = ">" if is_big_endian else "<"

    # Handle common pattern where first word is 0x58 (length) and repeating patterns follow
    if len(event_data) >= 8 and event_data[:4] == b'\x00\x00\x00\x58':
        # This format typically has 89 words total (356 bytes)
        # Each frame is typically 8 bytes (2 words)

        # Skip the first word (length marker)
        offset = 4

        # Process in 8-byte frames
        while offset + 8 <= len(event_data):
            try:
                w0 = struct.unpack(byte_fmt + "I", event_data[offset:offset+4])[0]
                w1 = struct.unpack(byte_fmt + "I", event_data[offset+4:offset+8])[0]

                # Extract common fields for VTP FADC data
                # These bit positions are based on observed patterns
                slot = (w0 >> 24) & 0xFF  # High byte often contains slot
                channel = (w0 >> 16) & 0xFF  # Second byte often contains channel
                timestamp = w0 & 0xFFFF  # Lower 16 bits might be timing info

                frames.append({
                    "slot": slot,
                    "channel": channel,
                    "timestamp": timestamp,
                    "adc": w1,  # Second word typically contains ADC value
                    "raw": (w0, w1)
                })

                offset += 8
            except Exception as e:
                logger.debug(f"Error parsing VTP frame at offset {offset}: {e}")
                break

    logger.debug(f"Decoded {len(frames)} VTP FADC frames")
    return frames


def decode_fadc_frames(payload_bytes, is_big_endian=False):
    """
    Decode FADC frames from payload data, handling both standard FADC format
    and VTP streaming format.
    """
    frames = []
    logger = logging.getLogger(__name__)
    byte_fmt = ">" if is_big_endian else "<"

    # Try to detect VTP streaming format based on the first few words
    if len(payload_bytes) >= 16:
        first_word = struct.unpack(byte_fmt + "I", payload_bytes[0:4])[0]

        # Check for VTP streaming format patterns
        vtp_marker = (first_word >> 24) & 0xFF
        if vtp_marker == 0x56:  # ASCII 'V' might indicate VTP header
            logger.debug("Detected possible VTP streaming format")
            return _decode_vtp_streaming_fadc(payload_bytes, is_big_endian)

        # Check for the pattern where first word is 0x58
        if first_word == 0x58:
            logger.debug("Detected possible VTP pattern with 0x58 marker")
            frames = decode_vtp_fadc_frames(payload_bytes, is_big_endian)
            if frames and len(frames) > 0:
                return frames

    # Default to standard format if we didn't detect VTP format
    offset = 0
    while offset + 4 <= len(payload_bytes):
        word = struct.unpack(byte_fmt + "I", payload_bytes[offset:offset+4])[0]
        slot    = (word >> 27) & 0x1F
        channel = (word >> 22) & 0x1F
        adc     =  word & 0x3FFFFF
        frames.append({
            "slot": slot,
            "channel": channel,
            "adc": adc
        })
        offset += 4

    logger.debug(f"decode_fadc_frames => found {len(frames)} standard frame words")
    return frames


def _decode_vtp_streaming_fadc(payload_bytes, is_big_endian=False):
    """
    Specialized decoder for VTP streaming mode FADC data.
    This is based on the 4x8 cells electromagnetic calorimeter setup.
    """
    frames = []
    logger = logging.getLogger(__name__)
    byte_fmt = ">" if is_big_endian else "<"

    try:
        # Skip header words if present (8 bytes typical for VTP streaming)
        offset = 8
        frame_size = 8  # Two 32-bit words per frame (common in VTP formats)

        # Process data frames
        while offset + frame_size <= len(payload_bytes):
            w0 = struct.unpack(byte_fmt + "I", payload_bytes[offset:offset+4])[0]
            w1 = struct.unpack(byte_fmt + "I", payload_bytes[offset+4:offset+8])[0]

            # Example decoding for 4x8 FADC cells
            # Adjust these bit positions based on your actual data format
            slot = (w0 >> 24) & 0xFF
            channel = (w0 >> 16) & 0xFF
            timestamp = w0 & 0xFFFF
            adc_value = w1

            frames.append({
                "slot": slot,
                "channel": channel,
                "timestamp": timestamp,
                "adc": adc_value
            })

            offset += frame_size

        logger.debug(f"_decode_vtp_streaming_fadc => found {len(frames)} VTP frames")

    except Exception as e:
        logger.error(f"Error parsing VTP streaming data: {e}")
        # Fallback to simple 4-byte frame format
        offset = 0
        while offset + 4 <= len(payload_bytes):
            word = struct.unpack(byte_fmt + "I", payload_bytes[offset:offset+4])[0]
            # Use a simpler decoding as fallback
            frames.append({
                "raw": word,
                "bytes": payload_bytes[offset:offset+4].hex()
            })
            offset += 4
        logger.debug(f"_decode_vtp_streaming_fadc => fallback mode, found {len(frames)} raw words")

    return frames