import click
from rich.console import Console
from rich.panel import Panel
from rich import box
from rich.table import Table
from rich.tree import Tree
import struct
from datetime import datetime

from pyevio.core import EvioFile
from pyevio.roc_time_slice_bank import RocTimeSliceBank
from pyevio.utils import make_hex_dump, print_offset_hex


@click.command(name="record")
@click.argument("filename", type=click.Path(exists=True))
@click.argument("record", type=int)
@click.option("--summary/--no-summary", default=True, help="Show record summary information")
@click.option("--events/--no-events", default=True, help="List events in the record")
@click.option("--limit", type=int, default=10, help="Limit the number of events shown in details")
@click.option("--hexdump/--no-hexdump", default=False, help="Show hex dump of record header")
@click.option('--verbose', '-v', is_flag=True, help="Enable verbose output")
@click.pass_context
def record_command(ctx, filename, record, summary, events, limit, hexdump, verbose):
    """
    Display details about a specific record in an EVIO file.

    Shows the record header information, event index, and optionally lists all events
    in the record with basic information about each event.
    """
    # Use either the command-specific verbose flag or the global one
    verbose = verbose or ctx.obj.get('VERBOSE', False)
    console = Console()

    with EvioFile(filename, verbose) as evio_file:
        if record < 0 or record >= len(evio_file.record_offsets):
            raise click.BadParameter(f"Record {record} out of range (0-{len(evio_file.record_offsets)-1})")

        record_offset = evio_file.record_offsets[record]
        record_header = evio_file.scan_record(evio_file.mm, record_offset)

        if summary:
            # Display record header information in a table
            table = Table(title=f"Record #{record} Header", box=box.ROUNDED)
            table.add_column("Field", style="cyan")
            table.add_column("Value", style="green")

            table.add_row("Offset", f"0x{record_offset:X}")
            table.add_row("Length", f"{record_header.record_length} words ({record_header.record_length * 4} bytes)")
            table.add_row("Record Number", str(record_header.record_number))
            table.add_row("Header Length", f"{record_header.header_length} words ({record_header.header_length * 4} bytes)")
            table.add_row("Event Count", str(record_header.event_count))
            table.add_row("Index Array Length", f"{record_header.index_array_length} bytes")
            table.add_row("User Header Length", f"{record_header.user_header_length} bytes")
            table.add_row("Event Type", record_header.event_type)
            table.add_row("Bit Info", f"0x{record_header.bit_info:06X}")
            table.add_row("Has Dictionary", str(record_header.has_dictionary))
            table.add_row("Is Last Record", str(record_header.is_last_record))
            table.add_row("Has First Event", str(record_header.has_first_event))

            if record_header.compression_type > 0:
                compression_types = {
                    0: "None",
                    1: "LZ4 (fast)",
                    2: "LZ4 (best)",
                    3: "gzip"
                }
                compression_type = compression_types.get(record_header.compression_type, f"Unknown ({record_header.compression_type})")
                table.add_row("Compression Type", compression_type)
                table.add_row("Compressed Data Length", f"{record_header.compressed_data_length} words")
                table.add_row("Uncompressed Data Length", f"{record_header.uncompressed_data_length} bytes")

            console.print(table)

            # If hexdump requested, show record header hexdump
            if hexdump:
                print_offset_hex(evio_file.mm, record_offset, record_header.header_length, "Record Header")

        # Calculate record data range
        """
            The record header ends at offset e.g. 0x0000006c (word 27)
            Then comes the index array e.g. word 28(which appears to be 4 bytes long based on your output)
            The index array in an EVIO record contains the lengths of all events in that record.
            After the index array, there might be a user header (which could be 0 bytes in your case)
            Then the actual data content starts at offset 0x00000074 (word 29)
        """
        data_start = record_offset + record_header.header_length * 4
        index_start = data_start
        index_end = index_start + record_header.index_array_length
        content_start = index_end + record_header.user_header_length
        data_end = record_offset + record_header.record_length * 4

        if verbose:
            console.print()
            print_offset_hex(evio_file.mm, index_start, 30, "Data after header hexdump")


        # Parse event index array
        event_offsets = []
        event_lengths = []

        if events and record_header.index_array_length > 0:
            console.print()
            console.print("[bold]Event Index:[/bold]")

            events_table = Table(title="Events in Record", box=box.SIMPLE)
            events_table.add_column("Event #", style="cyan")
            events_table.add_column("Offset", style="green")
            events_table.add_column("[words]", style="green")
            events_table.add_column("Length (bytes)", style="yellow")
            events_table.add_column("Type", style="magenta")

            # Parse events from index array
            event_count = record_header.index_array_length // 4
            current_offset = content_start

            for i in range(event_count):
                length_offset = index_start + (i * 4)
                event_length = struct.unpack(evio_file.header.endian + 'I',
                                             evio_file.mm[length_offset:length_offset+4])[0]

                # Store event offset and length
                event_offsets.append(current_offset)
                event_lengths.append(event_length)

                # Get event type if possible
                event_type = "Unknown"
                try:
                    # Try to identify event type by looking at first two words
                    if current_offset + 8 <= data_end:
                        first_word = struct.unpack(evio_file.header.endian + 'I',
                                                   evio_file.mm[current_offset:current_offset+4])[0]
                        second_word = struct.unpack(evio_file.header.endian + 'I',
                                                    evio_file.mm[current_offset+4:current_offset+8])[0]



                        # Check for ROC Time Slice Bank pattern
                        data_type = (second_word >> 8) & 0xFF
                        tag = (second_word >> 16) & 0xFFFF

                        if data_type == 0x10:
                            event_type = "ROC Time Slice Bank"
                        elif (tag & 0xFF00) == 0xFF00:
                            tag_type = tag & 0x00FF
                            if (tag_type & 0x10) == 0x10:
                                event_type = "ROC Raw Data Record"
                            elif tag_type == 0x30:
                                event_type = "ROC Time Slice Bank"
                            elif tag_type == 0x31:
                                event_type = "Physics Event"
                except Exception:
                    # Ignore errors in determining event type
                    pass

                # Update cumulative offset for next event
                current_offset += event_length

                # Only add a subset of events to the table to avoid overwhelming output
                max_display = limit
                if i < max_display // 2 or i >= event_count - (max_display // 2) or event_count <= max_display:
                    events_table.add_row(
                        str(i),
                        f"0x{event_offsets[i]:X}",
                        str(event_offsets[i]//4),
                        str(event_length),
                        event_type
                    )
                elif i == max_display // 2 and event_count > max_display:
                    events_table.add_row("...", "...", "...", "...", "...")

            console.print(events_table)

            # Add summary of event types if we have many events
            if event_count > 10:
                console.print()
                console.print(f"[bold]Total Events: {event_count}[/bold]")

                # Try to get a sample of events to analyze types
                sample_size = min(100, event_count)
                step = max(1, event_count // sample_size)
                sampled_events = [i for i in range(0, event_count, step)]

                # Count event types
                event_type_counts = {}
                for i in sampled_events:
                    if i < len(event_offsets):
                        evt_offset = event_offsets[i]

                        try:
                            # Try to determine event type
                            first_word = struct.unpack(evio_file.header.endian + 'I',
                                                       evio_file.mm[evt_offset:evt_offset+4])[0]
                            second_word = struct.unpack(evio_file.header.endian + 'I',
                                                        evio_file.mm[evt_offset+4:evt_offset+8])[0]

                            # Check for patterns
                            data_type = (second_word >> 8) & 0xFF
                            tag = (second_word >> 16) & 0xFFFF

                            if data_type == 0x10:
                                event_type = "ROC Time Slice Bank"
                            elif (tag & 0xFF00) == 0xFF00:
                                tag_type = tag & 0x00FF
                                if (tag_type & 0x10) == 0x10:
                                    event_type = "ROC Raw Data Record"
                                elif tag_type == 0x30:
                                    event_type = "ROC Time Slice Bank"
                                elif tag_type == 0x31:
                                    event_type = "Physics Event"
                            else:
                                event_type = f"Unknown (tag=0x{tag:04X}, type=0x{data_type:02X})"

                            # Update count
                            event_type_counts[event_type] = event_type_counts.get(event_type, 0) + 1
                        except Exception:
                            # Ignore errors
                            pass

                # Display event type distribution
                if event_type_counts:
                    console.print("[bold]Event Type Distribution (sample):[/bold]")
                    for event_type, count in event_type_counts.items():
                        pct = count / len(sampled_events) * 100
                        console.print(f"  {event_type}: {count} events ({pct:.1f}%)")