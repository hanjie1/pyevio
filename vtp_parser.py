import logging
import struct
from collections import namedtuple
import click

# Constants for VTP streaming data format
VTP_FRAME_SIZE = 8  # Most VTP frames are 2 words (8 bytes)

def parse_vtp_file(filename, header_length=14, event_pattern_size=None, verbose=False):
    """
    Parse a VTP streaming data file without strict EVIO validation.

    Args:
        filename: Path to the VTP data file
        header_length: Expected header length in 32-bit words
        event_pattern_size: If provided, use this fixed size for event detection
        verbose: Whether to print debug information

    Returns:
        List of parsed event data
    """
    logger = logging.getLogger(__name__)

    # Configure logging
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=log_level, format='%(levelname)s: %(message)s')

    events = []

    with open(filename, "rb") as f:
        # Get file size for verification
        f.seek(0, 2)
        file_size = f.tell()
        f.seek(0)

        logger.debug(f"File size: {file_size} bytes")

        try:
            # Read file header
            header_bytes = f.read(header_length * 4)
            if len(header_bytes) < header_length * 4:
                logger.warning("File too small for expected header")
                return events

            # Display header in verbose mode
            if verbose:
                logger.debug(f"File header: {header_bytes.hex(' ')}")

                # Try both endianness for potential fields
                for byte_order in ['big', 'little']:
                    logger.debug(f"Header values ({byte_order}-endian):")
                    for i in range(0, min(len(header_bytes), header_length * 4), 4):
                        if i + 4 <= len(header_bytes):
                            val = int.from_bytes(header_bytes[i:i+4], byte_order)
                            logger.debug(f"  Word {i//4}: 0x{val:08x} ({val})")

            # Check for event pattern size
            if event_pattern_size is None:
                # Try to detect pattern from first few entries
                # Read a chunk of data to analyze
                chunk = f.read(1024)
                f.seek(header_length * 4)  # Reset to after header

                # Look for repeating patterns
                pattern_sizes = detect_event_patterns(chunk)
                if pattern_sizes:
                    event_pattern_size = pattern_sizes[0]
                    logger.debug(f"Detected event pattern size: {event_pattern_size} bytes")
                else:
                    # Default to common VTP event size if detection fails
                    event_pattern_size = 356  # From the scan output, most events were 356 bytes
                    logger.debug(f"Using default event pattern size: {event_pattern_size} bytes")

            # Process events
            current_pos = f.tell()
            event_num = 1

            while current_pos < file_size:
                # Read event data
                event_data = f.read(event_pattern_size)
                if not event_data:
                    break

                # Add to events list
                events.append(event_data)

                # Update position and event counter
                current_pos = f.tell()
                event_num += 1

                if verbose and event_num % 1000 == 0:
                    logger.debug(f"Processed {event_num} events...")

            logger.debug(f"Extracted {len(events)} events total")

        except Exception as e:
            logger.error(f"Error parsing file: {e}")
            import traceback
            logger.debug(traceback.format_exc())

    return events

def detect_event_patterns(data):
    """
    Analyze a chunk of data to detect possible event patterns.

    Args:
        data: Bytes to analyze

    Returns:
        List of possible event sizes in bytes
    """
    if len(data) < 64:
        return []

    # Look for common patterns - first check if the pattern is based on a common
    # word that repeats at regular intervals (like 0x00000058 in the example)

    # Extract 32-bit words
    words = []
    for i in range(0, len(data) - 3, 4):
        words.append(int.from_bytes(data[i:i+4], 'big'))

    # Look for repeating patterns
    pattern_sizes = []

    # Check for common VTP patterns
    for pattern_len in [89, 128, 64, 32, 16, 8]:  # Common sizes in 32-bit words
        pattern_size = pattern_len * 4  # Convert to bytes

        # Check if this pattern size fits evenly in the data
        if len(data) >= pattern_size * 2:
            is_pattern = True

            # Compare several instances of the pattern
            for i in range(min(3, len(data) // pattern_size - 1)):
                start1 = i * pattern_size
                start2 = (i + 1) * pattern_size

                # Check if first word matches (common in VTP data)
                if data[start1:start1+4] != data[start2:start2+4]:
                    is_pattern = False
                    break

            if is_pattern:
                pattern_sizes.append(pattern_size)

    # If we found patterns, return them sorted by size
    return sorted(pattern_sizes)

def decode_vtp_frames(event_data, is_big_endian=True):
    """
    Decode VTP frames from an event payload.

    Args:
        event_data: Raw event bytes
        is_big_endian: Whether data is in big-endian format

    Returns:
        List of decoded frames
    """
    frames = []
    byte_order = ">" if is_big_endian else "<"

    # Check for repeating pattern at the start
    if len(event_data) >= 16:
        first_word = struct.unpack(byte_order + "I", event_data[0:4])[0]
        # Many VTP events start with the same word repeated
        if all(struct.unpack(byte_order + "I", event_data[i:i+4])[0] == first_word for i in range(0, 16, 4)):
            # This looks like VTP data with a repeating header pattern

            # Process the data in 8-byte frames (2 words per frame)
            offset = 0
            while offset + VTP_FRAME_SIZE <= len(event_data):
                w0 = struct.unpack(byte_order + "I", event_data[offset:offset+4])[0]
                w1 = struct.unpack(byte_order + "I", event_data[offset+4:offset+8])[0]

                # Extract fields - these bit positions are based on the common VTP format
                # but may need adjustment for specific setups
                slot = (w0 >> 24) & 0xFF  # Usually in the high byte
                channel = (w0 >> 16) & 0xFF  # Often in second byte
                timestamp = w0 & 0xFFFF  # Lower 16 bits often contain timing

                # Add the frame with all potentially useful fields
                frames.append({
                    "word0": w0,
                    "word1": w1,
                    "slot": slot,
                    "channel": channel,
                    "timestamp": timestamp,
                    "adc": w1  # Second word often contains the ADC value
                })

                offset += VTP_FRAME_SIZE

    return frames

def analyze_vtp_events(events, max_events=10, is_big_endian=True):
    """
    Analyze VTP events to determine structure and content.

    Args:
        events: List of raw event data
        max_events: Maximum number of events to analyze
        is_big_endian: Whether to interpret as big-endian

    Returns:
        Summary information about the events
    """
    byte_order = ">" if is_big_endian else "<"
    event_count = min(max_events, len(events))

    summary = {
        "total_events": len(events),
        "analyzed_events": event_count,
        "event_sizes": {},
        "frame_counts": {},
        "slots": set(),
        "channels": set(),
        "frame_patterns": []
    }

    # Analyze a sample of events
    for i in range(event_count):
        event_data = events[i]
        size = len(event_data)

        # Count event sizes
        if size in summary["event_sizes"]:
            summary["event_sizes"][size] += 1
        else:
            summary["event_sizes"][size] = 1

        # Decode frames
        frames = decode_vtp_frames(event_data, is_big_endian)

        # Count frames per event
        frame_count = len(frames)
        if frame_count in summary["frame_counts"]:
            summary["frame_counts"][frame_count] += 1
        else:
            summary["frame_counts"][frame_count] = 1

        # Collect slot and channel information
        for frame in frames:
            if "slot" in frame:
                summary["slots"].add(frame["slot"])
            if "channel" in frame:
                summary["channels"].add(frame["channel"])

        # Record the first few frames for pattern analysis
        if i == 0 and frames:
            summary["frame_patterns"] = frames[:min(5, len(frames))]

    return summary

@click.command()
@click.argument("filename", type=click.Path(exists=True))
@click.option("--header-length", type=int, default=14, help="Header length in 32-bit words")
@click.option("--event-size", type=int, help="Fixed event size in bytes")
@click.option("--big-endian", is_flag=True, default=True, help="Use big-endian interpretation")
@click.option("--little-endian", is_flag=True, help="Use little-endian interpretation")
@click.option("--analyze", is_flag=True, help="Analyze event structures")
@click.option("--max-events", type=int, default=500, help="Maximum events to process")
@click.option("--verbose", is_flag=True, help="Enable verbose output")
def main(filename, header_length, event_size, big_endian, little_endian, analyze, max_events, verbose):
    """
    Parse and analyze VTP data files.

    This tool processes VTP data files that may not conform to standard EVIO format,
    extracting events based on pattern detection or fixed sizes.
    """
    # Handle endianness flags
    if little_endian:
        big_endian = False

    # Parse the file
    events = parse_vtp_file(
        filename,
        header_length=header_length,
        event_pattern_size=event_size,
        verbose=verbose
    )

    # Print basic info
    print(f"Found {len(events)} events in {filename}")

    if len(events) == 0:
        return

    # Print sizes of first few events
    print("\nFirst 5 event sizes:")
    for i, event in enumerate(events[:5]):
        print(f"Event {i+1}: {len(event)} bytes")

    # Analyze if requested
    if analyze and events:
        summary = analyze_vtp_events(events, max_events=min(max_events, len(events)), is_big_endian=big_endian)

        print("\nEvent Analysis Summary:")
        print(f"Total events: {summary['total_events']}")
        print(f"Analyzed events: {summary['analyzed_events']}")

        print("\nEvent sizes (bytes):")
        for size, count in sorted(summary["event_sizes"].items()):
            percent = (count / summary["analyzed_events"]) * 100
            print(f"  {size} bytes: {count} events ({percent:.1f}%)")

        print("\nFrames per event:")
        for count, events in sorted(summary["frame_counts"].items()):
            percent = (events / summary["analyzed_events"]) * 100
            print(f"  {count} frames: {events} events ({percent:.1f}%)")

        if summary["slots"]:
            print(f"\nDetected slots: {sorted(summary['slots'])}")

        if summary["channels"]:
            print(f"Detected channels: {sorted(summary['channels'])}")

        # Display example frames from first event
        if summary["frame_patterns"]:
            print("\nExample frames from first event:")
            for i, frame in enumerate(summary["frame_patterns"]):
                frame_str = ", ".join(f"{k}={v}" for k, v in frame.items()
                                      if k not in ("word0", "word1"))
                print(f"  Frame {i+1}: {frame_str}")

        # If we have frames with slot and channel info, show sample data
        if events and isinstance(events, list) and len(events) > 0:
            first_event = events[0]
            frames = decode_vtp_frames(first_event, is_big_endian=big_endian)

            if frames and len(frames) > 0 and isinstance(frames[0], dict) and "slot" in frames[0] and "channel" in frames[0]:
                print("\nDetailed view of first event:")
                for i, frame in enumerate(frames[:10]):  # Show up to 10 frames
                    print(f"  Frame {i+1}: Slot={frame['slot']} Channel={frame['channel']} "
                          f"Timestamp={frame['timestamp']} ADC={frame['adc']}")

                if len(frames) > 10:
                    print(f"  ... ({len(frames)-10} more frames not shown)")

if __name__ == "__main__":
    main()