import click
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich import box
from rich.table import Table
from rich.tree import Tree
import struct
from datetime import datetime

from pyevio.core import EvioFile
from pyevio.roc_time_slice_bank import RocTimeSliceBank
from pyevio.utils import make_hex_dump, print_offset_hex


@click.command(name="debug")
@click.argument("filename", type=click.Path(exists=True))
@click.option("--record", "-r", "record_index", type=int, required=True, help="Record number to debug")
@click.option("--event", "-e", type=int, help="Event number within the record (if omitted, scans all events)")
@click.option("--payload", "-p", type=int, help="Payload number to focus on (if omitted, shows all payloads)")
@click.option("--hexdump/--no-hexdump", default=False, help="Show hex dump of data structures")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.pass_context
def debug_command(ctx, filename, record_index, event, payload, hexdump, verbose):
    """
    Debug EVIO file structure at a detailed level.

    Analyzes a specific record and optionally a specific event within that record.
    Shows the internal structure of ROC Time Slice Banks, Stream Info Banks, and Payload Banks.
    """
    # Use either the command-specific verbose flag or the global one
    verbose = verbose or ctx.obj.get('VERBOSE', False)
    console = Console()

    with EvioFile(filename, verbose) as evio_file:
        if record_index < 0 or record_index >= len(evio_file.record_offsets):
            raise click.BadParameter(f"Record {record_index} out of range (0-{len(evio_file.record_offsets) - 1})")

        record_offset = evio_file.record_offsets[record_index]
        record_header = evio_file.scan_record(evio_file.mm, record_offset)

        # Display record header information
        console.print(f"[bold cyan]Record #{record_index} Analysis[/bold cyan]")
        console.print(f"[bold]Offset: [green]0x{record_offset:X}[/green], Length: [green]{record_header.record_length}[/green] words[/bold]")
        console.print(f"[bold]Type: [green]{record_header.event_type}[/green], Events: [green]{record_header.event_count}[/green][/bold]")

        # If hexdump requested, show record header hexdump
        if hexdump:
            console.print()
            print_offset_hex(evio_file.mm, record_offset, record_header.header_length, "Record Header:")

        # Calculate record data range (start after record header + index array + user header)
        data_start = record_offset + record_header.header_length * 4
        index_start = data_start
        index_end = index_start + record_header.index_array_length
        data_start = index_end + record_header.user_header_length
        data_end = record_offset + record_header.record_length * 4

        # Parse event index array to get event offsets
        event_offsets = []
        if record_header.index_array_length > 0:
            console.print()
            console.print("[bold]Event Index Array:[/bold]")

            index_table = Table(title="Event Lengths", box=box.SIMPLE)
            index_table.add_column("Event #", style="cyan")
            index_table.add_column("Length (bytes)", style="green")

            # Read event lengths from index array (32-bit ints)
            event_count = record_header.index_array_length // 4

            # Calculate cumulative offset for each event
            current_offset = data_start

            for i in range(event_count):
                length_offset = index_start + (i * 4)
                event_length = struct.unpack(evio_file.header.endian + 'I',
                                             evio_file.mm[length_offset:length_offset+4])[0]

                # Store event offset
                event_offsets.append(current_offset)

                # Update cumulative offset
                current_offset += event_length

                # Add to table (only display at most 20 events to avoid overloading output)
                if i < 10 or i >= event_count - 5 or event_count <= 20:
                    index_table.add_row(str(i), f"{event_length}")
                elif i == 10 and event_count > 20:
                    index_table.add_row("...", "...")

            console.print(index_table)

        # Handle event parameter - scan specific event or all events
        events_to_scan = []
        if event is not None:
            if event < 0 or event >= len(event_offsets):
                raise click.BadParameter(f"Event {event} out of range (0-{len(event_offsets)-1})")
            events_to_scan = [event]
        else:
            # Limit to first 5 events by default if not specified
            events_to_scan = list(range(min(5, len(event_offsets))))

        # Scan each event
        for evt_idx in events_to_scan:
            console.print()
            console.print(f"[bold yellow]Event #{evt_idx}[/bold yellow]")

            if evt_idx >= len(event_offsets):
                console.print("[red]Event index out of range[/red]")
                continue

            evt_offset = event_offsets[evt_idx]

            # Calculate event end
            evt_end = data_end
            if evt_idx < len(event_offsets) - 1:
                evt_end = event_offsets[evt_idx + 1]

            console.print(f"[bold]Offset: [green]0x{evt_offset:X}[/green], Size: [green]{evt_end - evt_offset}[/green] bytes[/bold]")

            # Try to parse the event as a ROC Time Slice Bank
            try:
                roc_bank = RocTimeSliceBank(evio_file.mm, evt_offset, evio_file.header.endian)

                # Show bank information
                tree = Tree(f"[bold]ROC Time Slice Bank (ROC ID: {roc_bank.roc_id})[/bold]")

                # Add Stream Info Bank to tree
                sib_node = tree.add(f"[bold]Stream Info Bank (0xFF30)[/bold]")

                # Add Time Slice Segment info
                tss_node = sib_node.add(f"[bold]Time Slice Segment (0x31)[/bold]")
                tss_node.add(f"Frame Number: {roc_bank.sib.frame_number}")

                # Format timestamp for display
                timestamp_seconds = roc_bank.sib.timestamp / 1e9  # Convert to seconds (assuming nanoseconds)
                timestamp_str = datetime.fromtimestamp(timestamp_seconds).strftime('%Y-%m-%d %H:%M:%S.%f')
                tss_node.add(f"Timestamp: {roc_bank.sib.timestamp} ({timestamp_str})")

                # Add Aggregation Info Segment
                ais_node = sib_node.add(f"[bold]Aggregation Info Segment (0x41)[/bold]")
                ais_node.add(f"Payload Count: {len(roc_bank.sib.payload_infos)}")

                # Add info for each payload
                payload_count = len(roc_bank.payload_banks)
                payloads_node = tree.add(f"[bold]Payload Banks ({payload_count})[/bold]")

                # Filter payloads based on --payload option
                payload_indices = range(payload_count)
                if payload is not None:
                    if payload < 0 or payload >= payload_count:
                        console.print(f"[yellow]Warning: Payload {payload} out of range (0-{payload_count-1})[/yellow]")
                    else:
                        payload_indices = [payload]

                for p_idx in payload_indices:
                    if p_idx >= payload_count:
                        continue

                    payload_bank = roc_bank.payload_banks[p_idx]
                    payload_info = roc_bank.sib.payload_infos[p_idx] if p_idx < len(roc_bank.sib.payload_infos) else None

                    # Get payload details
                    if payload_info:
                        p_node = payloads_node.add(f"[bold]Payload {p_idx} (Module: {payload_info['module_id']}, Lane: {payload_info['lane_id']}, Port: {payload_info['port_num']})[/bold]")
                    else:
                        p_node = payloads_node.add(f"[bold]Payload {p_idx}[/bold]")

                    p_node.add(f"Length: {payload_bank.length} words ({payload_bank.data_length} bytes of data)")
                    p_node.add(f"Tag: 0x{payload_bank.tag:04X}")

                    # Show data analysis
                    if hasattr(payload_bank, 'num_samples'):
                        p_node.add(f"Total Samples: {payload_bank.num_samples}")
                        if hasattr(payload_bank, 'channels'):
                            p_node.add(f"Channels: {payload_bank.channels}")
                        if hasattr(payload_bank, 'samples_per_channel'):
                            p_node.add(f"Samples/Channel: {payload_bank.samples_per_channel}")

                        # Add a preview of the data
                        data = payload_bank.get_waveform_data()
                        if data:
                            preview_count = min(8, len(data))
                            preview_start = ", ".join([f"0x{x:04X}" for x in data[:preview_count]])
                            preview_end = ", ".join([f"0x{x:04X}" for x in data[-preview_count:]])

                            if len(data) <= preview_count * 2:
                                # Show all data if it's small enough
                                p_node.add(f"Data: [{preview_start}]")
                            else:
                                p_node.add(f"Data Preview: [{preview_start}, ... {preview_end}]")

                console.print(tree)

                # If hexdump requested, show event hexdump
                if hexdump:
                    console.print()
                    console.print(f"[bold]Event Hexdump (First 256 bytes):[/bold]")
                    event_data = evio_file.mm[evt_offset:min(evt_offset + 256, evt_end)]
                    console.print(make_hex_dump(event_data, title=f"Event #{evt_idx} Data"))

            except Exception as e:
                console.print(f"[red]Error parsing event as ROC Time Slice Bank: {str(e)}[/red]")
                if hexdump:
                    # Show partial dump to help debug
                    event_data = evio_file.mm[evt_offset:min(evt_offset + 64, evt_end)]
                    console.print(make_hex_dump(event_data, title=f"Event #{evt_idx} Data (Error)"))