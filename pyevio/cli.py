import logging
import click
import struct

from .parser import parse_file, decode_event_structures

@click.command()
@click.argument("filename", type=click.Path(exists=True))
@click.argument("event_number", type=int, required=False)
@click.option("--verbose", is_flag=True, help="Enable debug logging")
@click.option("--show-raw", is_flag=True, help="Show raw event data in hex")
@click.option("--show-fadc", is_flag=True, help="Show all FADC frames (instead of just summary)")
@click.option("--big-endian", is_flag=True, help="Force big-endian parsing")
@click.option("--little-endian", is_flag=True, help="Force little-endian parsing")
@click.option("--format", "format_type", type=click.Choice(['v4', 'v6', 'streaming', 'streaming14']),
              help="Force specific format (v4, v6, streaming, streaming14)")
@click.option("--header-length", type=int, help="Force specific header length for streaming mode")
@click.option("--scan", is_flag=True, help="Scan all events in the file and display summary")
@click.option("--scan-range", nargs=2, type=int, metavar="START END",
              help="Range of events to scan (requires --scan)")
def main(filename, event_number, verbose, show_raw, show_fadc, big_endian, little_endian,
         format_type, header_length, scan, scan_range):
    """
    pyevio CLI entry point.

    Usage:
      pyevio FILENAME [EVENT_NUMBER] [--options]

    If EVENT_NUMBER is omitted, it displays how many events are in the file.
    If EVENT_NUMBER is provided, it parses that event's structure and prints details.
    If --scan is specified, it scans events and displays their properties.

    Options:
      --verbose: Turn on debug logging
      --show-raw: Show full raw event data in hex
      --show-fadc: Show all FADC frames (not just a summary)
      --big-endian: Force big-endian parsing
      --little-endian: Force little-endian parsing
      --format: Force specific format (v4, v6, streaming, streaming14)
      --header-length: Force specific header length (for streaming mode)
      --scan: Scan all events in the file and display summary
      --scan-range: Range of events to scan (START END)
    """

    # Configure logging
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=log_level,
                        format='%(levelname)s: %(message)s')
    logger = logging.getLogger(__name__)

    if verbose:
        logger.debug("Verbose mode enabled: DEBUG logging")

    # Process endianness flags
    if big_endian and little_endian:
        click.echo("Error: Cannot specify both --big-endian and --little-endian")
        return

    # If header length is specified but format isn't set to streaming,
    # set format to streaming automatically
    if header_length is not None and format_type is None:
        format_type = 'streaming'
        logger.debug(f"Setting format to 'streaming' since header-length ({header_length}) was specified")

    # If format_type is streaming and header_length is specified, create a custom format string
    if format_type == 'streaming' and header_length is not None:
        format_override = f'streaming{header_length}'
        logger.debug(f"Using custom streaming format with header length: {header_length}")
    else:
        format_override = format_type

    # Parse the file
    try:
        all_events = parse_file(filename, format_override)

        if len(all_events) == 0:
            click.echo("No events found in file.")
            return

        # If scan mode is active, we'll scan events instead of displaying a single event
        if scan:
            scan_events(all_events, scan_range, big_endian, little_endian, verbose)
            return

        if event_number is None:
            click.echo(f"Found {len(all_events)} events total.")
            return

        # If event number is given, parse that event's structure
        if event_number < 1 or event_number > len(all_events):
            click.echo(
                f"Event_number={event_number} out of range (1..{len(all_events)})"
            )
            return

        evraw = all_events[event_number - 1]
        length_words = len(evraw) // 4
        click.echo(
            f"Event {event_number} has {length_words} words (raw size={len(evraw)} bytes)."
        )

        # If small, show entire raw hex, else partial
        if length_words <= 8 or show_raw:
            click.echo("Raw (hex): " + evraw.hex())
        else:
            click.echo("First 32 bytes (hex): " + evraw[:32].hex())

        # Handle events that are too small to be valid EVIO structures
        if len(evraw) < 8:
            click.echo("Event is too small to be a valid EVIO structure (minimum 8 bytes required).")
            return

        # Determine endianness for structure decoding
        is_big_endian = determine_endianness(evraw, big_endian, little_endian)
        logger.debug(f"Using {'big' if is_big_endian else 'little'}-endian for structure decoding")

        # Now do deeper decode: parse sub-banks and see if there's FADC data
        structure_tree = decode_event_structures(evraw, is_big_endian=is_big_endian)

        # Print the nested structure
        _print_structure_tree(structure_tree, indent=0, show_all_fadc=show_fadc)

    except Exception as e:
        click.echo(f"Error: {str(e)}")
        if verbose:
            import traceback
            click.echo(traceback.format_exc())


def determine_endianness(event_data, big_endian=False, little_endian=False):
    """
    Determine the likely endianness of the data.

    Args:
        event_data: The event data bytes
        big_endian: Whether big endian was explicitly requested
        little_endian: Whether little endian was explicitly requested

    Returns:
        True for big endian, False for little endian
    """
    # If explicitly set, use that
    if big_endian:
        return True
    if little_endian:
        return False

    # Otherwise try to auto-detect
    # First, check which endianness gives a sensible event length
    len_be = int.from_bytes(event_data[0:4], 'big')
    len_le = int.from_bytes(event_data[0:4], 'little')

    bytes_be = (len_be + 1) * 4
    bytes_le = (len_le + 1) * 4
    actual_len = len(event_data)

    # If one matches and the other doesn't, we have a winner
    if abs(bytes_be - actual_len) < abs(bytes_le - actual_len):
        return True
    elif abs(bytes_le - actual_len) < abs(bytes_be - actual_len):
        return False

    # If we can't determine by length, check the type field
    # Valid EVIO types are generally small numbers
    type_be = (int.from_bytes(event_data[4:8], 'big') >> 8) & 0x3F
    type_le = (int.from_bytes(event_data[4:8], 'little') >> 8) & 0x3F

    if 0 < type_be <= 0x20 and not (0 < type_le <= 0x20):
        return True
    elif 0 < type_le <= 0x20 and not (0 < type_be <= 0x20):
        return False

    # Default to big endian for JLab data
    return True


def scan_events(events, scan_range, big_endian, little_endian, verbose):
    """
    Scan events and display information about them.

    Args:
        events: List of event byte arrays
        scan_range: Range of events to scan (START, END) or None for all
        big_endian: Whether big endian was explicitly requested
        little_endian: Whether little endian was explicitly requested
        verbose: Whether to show verbose output
    """
    # Set up the range of events to scan
    start_event = 1
    end_event = len(events)

    if scan_range:
        start_event = max(1, scan_range[0])
        end_event = min(len(events), scan_range[1])

    click.echo(f"Total events in file: {len(events)}")
    click.echo(f"Scanning events {start_event} to {end_event}")
    click.echo("-" * 100)
    click.echo(f"{'Event#':>6} | {'Size(B)':>8} | {'Words':>6} | {'Valid':>5} | {'First 16 bytes (hex)':48} | {'Type':>4} | Note")
    click.echo("-" * 100)

    # Try both endianness for validation unless one is explicitly set
    if big_endian:
        primary_endian = True
        both_endian = False
    elif little_endian:
        primary_endian = False
        both_endian = False
    else:
        # Auto-detect endianness from first 10 events
        both_endian = True
        valid_be_count = 0
        valid_le_count = 0

        for i in range(min(10, end_event - start_event + 1)):
            event_num = start_event + i - 1
            event_data = events[event_num]
            if len(event_data) >= 8:
                valid_be, _ = is_valid_evio_event(event_data, True)
                valid_le, _ = is_valid_evio_event(event_data, False)
                if valid_be:
                    valid_be_count += 1
                if valid_le:
                    valid_le_count += 1

        # If one endianness is clearly better, use only that
        if valid_be_count > valid_le_count * 2:
            both_endian = False
            primary_endian = True
            click.echo("File appears to be big-endian based on initial event analysis")
        elif valid_le_count > valid_be_count * 2:
            both_endian = False
            primary_endian = False
            click.echo("File appears to be little-endian based on initial event analysis")
        else:
            click.echo("Checking both endianness for each event (no clear winner)")

    # Display information about each event
    for i in range(start_event, end_event + 1):
        event_num = i - 1  # Convert to 0-based index
        event_data = events[event_num]

        # Basic event information
        event_size = len(event_data)
        event_words = event_size // 4

        # Get type if possible
        evio_type = ""
        if event_size >= 8:
            try:
                if both_endian:
                    type_be = (int.from_bytes(event_data[4:8], 'big') >> 8) & 0x3F
                    type_le = (int.from_bytes(event_data[4:8], 'little') >> 8) & 0x3F
                    if 0 < type_be <= 0x20:
                        evio_type = f"0x{type_be:X}b"
                    if 0 < type_le <= 0x20:
                        evio_type = f"0x{type_le:X}l"
                else:
                    byte_order = "big" if primary_endian else "little"
                    evio_type = f"0x{((int.from_bytes(event_data[4:8], byte_order) >> 8) & 0x3F):X}"
            except:
                pass

        # Check if valid EVIO
        if event_size < 8:
            valid_str = "No"
            reason = f"Too short ({event_size} bytes)"
        elif both_endian:
            valid_be, reason_be = is_valid_evio_event(event_data, True)
            valid_le, reason_le = is_valid_evio_event(event_data, False)

            if valid_be:
                valid_str = "BE"
                reason = reason_be
            elif valid_le:
                valid_str = "LE"
                reason = reason_le
            else:
                valid_str = "No"
                reason = reason_be if len(reason_be) < len(reason_le) else reason_le
        else:
            valid, reason = is_valid_evio_event(event_data, primary_endian)
            valid_str = "Yes" if valid else "No"

        # Get first 16 bytes as hex
        hex_bytes = event_data[:min(16, len(event_data))].hex()
        hex_str = ' '.join(hex_bytes[j:j+2] for j in range(0, len(hex_bytes), 2))

        # Output
        click.echo(f"{i:6d} | {event_size:8d} | {event_words:6d} | {valid_str:>5} | {hex_str:48} | {evio_type:>4} | {reason}")

        # If verbose and the event is valid, try to decode FADC frames
        if verbose and valid_str in ("Yes", "BE", "LE") and event_size >= 8:
            is_big = valid_str != "LE"  # Use detected endianness
            try:
                struct_tree = decode_event_structures(event_data, is_big_endian=is_big)
                if struct_tree and "fadc_frames" in struct_tree:
                    frames = struct_tree["fadc_frames"]
                    click.echo(f"    --> Found {len(frames)} FADC frames in event {i}")
                    # Show statistics on found frames
                    slots = set()
                    channels = set()
                    for frm in frames:
                        if "slot" in frm:
                            slots.add(frm["slot"])
                        if "channel" in frm:
                            channels.add(frm["channel"])
                    if slots:
                        click.echo(f"    --> Slots: {sorted(slots)}")
                    if channels:
                        click.echo(f"    --> Channels: {sorted(channels)}")
            except Exception as e:
                if verbose:
                    click.echo(f"    --> Error decoding event structure: {str(e)}")


def is_valid_evio_event(event_data, is_big_endian=False):
    """
    Checks if an event appears to be valid EVIO format.

    Args:
        event_data: Raw event bytes
        is_big_endian: Whether to interpret as big-endian

    Returns:
        (bool, str) - Whether it's valid and reason if not
    """
    if len(event_data) < 8:
        return False, f"Too short ({len(event_data)} bytes)"

    try:
        # Check if length in event header matches actual length
        byte_order = ">" if is_big_endian else "<"
        word_len = struct.unpack(byte_order + "I", event_data[:4])[0]
        event_len_bytes = (word_len + 1) * 4

        if event_len_bytes != len(event_data):
            return False, f"Length mismatch: header says {event_len_bytes} bytes, actual is {len(event_data)} bytes"

        # Very basic sanity check on type field
        type_word = struct.unpack(byte_order + "I", event_data[4:8])[0]
        data_type = (type_word >> 8) & 0x3F

        # Check if datatype is valid
        if data_type == 0 or data_type > 0x20:  # Most valid types are 1-0x10
            return False, f"Unusual data type: 0x{data_type:X}"

        return True, "Valid EVIO format"

    except Exception as e:
        return False, f"Error parsing: {str(e)}"


def _print_structure_tree(node, indent=0, show_all_fadc=False):
    """
    Recursively prints a dictionary describing the EVIO event bank/segments,
    including any FADC frames found.

    Args:
        node: The structure node to print
        indent: Current indentation level
        show_all_fadc: Whether to show all FADC frames or just a summary
    """
    if not node:
        click.echo(" " * indent + "[Empty structure or parse error]")
        return

    line_prefix = " " * indent
    tag   = node.get("tag")
    ttype = node.get("type")
    num   = node.get("num")
    click.echo(f"{line_prefix}Bank: tag=0x{tag:X}, type=0x{ttype:X}, num={num}")

    # If there's a list of fADC frames, print them
    if "fadc_frames" in node:
        frames = node["fadc_frames"]
        click.echo(f"{line_prefix}  FADC frames found: {len(frames)}")

        # Collect statistics on the FADC frames
        slots = set()
        channels = set()
        for frm in frames:
            if "slot" in frm:
                slots.add(frm["slot"])
            if "channel" in frm:
                channels.add(frm["channel"])

        click.echo(f"{line_prefix}  Slots: {sorted(slots)}")
        click.echo(f"{line_prefix}  Channels: {sorted(channels)}")

        # Print frame details if requested or if there are few frames
        if show_all_fadc or len(frames) <= 16:
            for i, frm in enumerate(frames):
                if "slot" in frm and "channel" in frm and "adc" in frm:
                    # Standard format
                    click.echo(f"{line_prefix}    slot={frm['slot']} chan={frm['channel']} adc={frm['adc']}")
                elif "timestamp" in frm:
                    # VTP streaming format with timestamp
                    click.echo(f"{line_prefix}    slot={frm['slot']} chan={frm['channel']} "
                               f"time={frm['timestamp']} adc={frm['adc']}")
                elif "raw" in frm:
                    # Raw format (fallback)
                    click.echo(f"{line_prefix}    raw=0x{frm['raw']:08X} hex={frm['bytes']}")
                else:
                    # Unknown format - dump all keys
                    keys_str = ", ".join(f"{k}={frm[k]}" for k in frm)
                    click.echo(f"{line_prefix}    {keys_str}")

                # Limit output if not showing all
                if not show_all_fadc and i >= 15:
                    remaining = len(frames) - i - 1
                    if remaining > 0:
                        click.echo(f"{line_prefix}    ... ({remaining} more frames not shown)")
                    break

    # Recurse into substructures
    subs = node.get("substructures", [])
    for child in subs:
        _print_structure_tree(child, indent + 2, show_all_fadc)