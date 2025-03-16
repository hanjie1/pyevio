import click
from rich.console import Console
from rich.panel import Panel
from rich import box
from rich.tree import Tree
import struct
from datetime import datetime

from pyevio.core import EvioFile
from pyevio.roc_time_slice_bank import RocTimeSliceBank
from pyevio.utils import make_hex_dump


@click.command(name="dump")
@click.argument("filename", type=click.Path(exists=True))
@click.argument("record", type=int)
@click.option("--depth", type=int, default=5, help="Maximum depth to display")
@click.option("--events", type=int, default=1, help="Number of events to display (0 for all)")
@click.option("--color/--no-color", default=True, help="Use ANSI colors")
@click.option("--preview", type=int, default=3, help="Number of preview elements")
@click.option("--hexdump/--no-hexdump", default=False, help="Show hex dump of data")
@click.option('--verbose', '-v', is_flag=True, help="Enable verbose output")
@click.pass_context
def dump_command(ctx, filename, record, depth, events, color, preview, hexdump, verbose):
    """Inspect record structure in detail."""
    # Use either the command-specific verbose flag or the global one
    verbose = verbose or ctx.obj.get('VERBOSE', False)
    console = Console(highlight=color)

    with EvioFile(filename, verbose) as evio_file:
        if record < 0 or record >= len(evio_file.record_offsets):
            raise click.BadParameter(f"Record {record} out of range (0-{len(evio_file.record_offsets)-1})")

        record_offset = evio_file.record_offsets[record]
        record_header = evio_file.scan_record(evio_file.mm, record_offset)

        console.print(f"[bold]Record #{record} [Offset: 0x{record_offset:X}, Length: {record_header.record_length} words][/bold]")
        console.print(f"[bold]Type: {record_header.event_type}, Events: {record_header.event_count}[/bold]")

        # Get record data range (after header, index array, and user header)
        data_start = record_offset + record_header.header_length * 4
        index_start = data_start
        index_end = index_start + record_header.index_array_length
        content_start = index_end + record_header.user_header_length
        data_end = record_offset + record_header.record_length * 4

        # If hexdump requested, show record header
        if hexdump:
            console.print()
            console.print("[bold]Record Header Hexdump:[/bold]")
            header_data = evio_file.mm[record_offset:record_offset + record_header.header_length * 4]
            console.print(make_hex_dump(header_data, title="Record Header"))

        # Parse event index array to get event offsets
        event_offsets = []
        event_lengths = []

        if record_header.index_array_length > 0:
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

                # Update cumulative offset for next event
                current_offset += event_length

            # Show event index summary
            console.print()
            console.print(f"[bold]Event Index: {len(event_offsets)} events found[/bold]")

        # Determine which events to dump
        events_to_dump = []
        if events == 0:
            # Dump all events (up to a reasonable limit to prevent overwhelming output)
            max_events = min(len(event_offsets), 20)
            events_to_dump = list(range(max_events))
        else:
            # Dump the first N events
            max_events = min(events, len(event_offsets))
            events_to_dump = list(range(max_events))

        # Dump each event
        for event_idx in events_to_dump:
            if event_idx >= len(event_offsets):
                break

            evt_offset = event_offsets[event_idx]
            evt_length = event_lengths[event_idx]
            evt_end = evt_offset + evt_length

            console.print()
            console.print(f"[bold yellow]Event #{event_idx} [Offset: 0x{evt_offset:X}, Length: {evt_length} bytes][/bold yellow]")

            # Try to parse the event as a ROC Time Slice Bank
            try:
                roc_bank = RocTimeSliceBank(evio_file.mm, evt_offset, evio_file.header.endian)

                # Create a hierarchical tree view of the bank structure
                tree = Tree(f"[bold]ROC Time Slice Bank (ROC ID: {roc_bank.roc_id})[/bold]")

                # Add Stream Info Bank to tree
                sib_node = tree.add(f"[bold]Stream Info Bank (0xFF30)[/bold]")

                # Add Time Slice Segment info
                tss_node = sib_node.add(f"Time Slice Segment (0x31)")
                tss_node.add(f"Frame Number: {roc_bank.sib.frame_number}")

                # Format timestamp for display
                timestamp_seconds = roc_bank.sib.timestamp / 1e9  # Convert to seconds (assuming nanoseconds)
                timestamp_str = datetime.fromtimestamp(timestamp_seconds).strftime('%Y-%m-%d %H:%M:%S.%f')
                tss_node.add(f"Timestamp: {roc_bank.sib.timestamp} ({timestamp_str})")

                # Add Aggregation Info Segment
                ais_node = sib_node.add(f"Aggregation Info Segment (0x41)")
                ais_node.add(f"Payload Count: {len(roc_bank.sib.payload_infos)}")

                # Add info for each payload info
                if depth > 2:
                    for i, payload_info in enumerate(roc_bank.sib.payload_infos):
                        if i < preview or i >= len(roc_bank.sib.payload_infos) - 1:
                            pi_node = ais_node.add(f"Payload Info {i}")
                            pi_node.add(f"Module ID: {payload_info['module_id']}")
                            pi_node.add(f"Bond: {payload_info['bond']}")
                            pi_node.add(f"Lane ID: {payload_info['lane_id']}")
                            pi_node.add(f"Port Number: {payload_info['port_num']}")
                        elif i == preview and len(roc_bank.sib.payload_infos) > preview * 2:
                            ais_node.add(f"... ({len(roc_bank.sib.payload_infos) - preview * 2} more) ...")

                # Add payload banks
                payload_node = tree.add(f"[bold]Payload Banks ({len(roc_bank.payload_banks)})[/bold]")

                # Add info for each payload bank
                if depth > 1:
                    for i, payload_bank in enumerate(roc_bank.payload_banks):
                        if i < preview or i >= len(roc_bank.payload_banks) - 1:
                            pb_node = payload_node.add(f"Payload Bank {i}")
                            pb_node.add(f"Length: {payload_bank.length} words ({payload_bank.data_length} bytes)")
                            pb_node.add(f"Tag: 0x{payload_bank.tag:04X}")

                            # Add data analysis if available
                            if hasattr(payload_bank, 'num_samples'):
                                data_node = pb_node.add(f"Data: {payload_bank.num_samples} samples")

                                if hasattr(payload_bank, 'channels') and hasattr(payload_bank, 'samples_per_channel'):
                                    data_node.add(f"Structure: {payload_bank.channels} channels × {payload_bank.samples_per_channel} samples/channel")

                                # Add data preview if depth allows
                                if depth > 3:
                                    data = payload_bank.get_waveform_data()
                                    if data:
                                        preview_count = min(preview, len(data))
                                        preview_start = ", ".join([f"0x{x:04X}" for x in data[:preview_count]])

                                        if len(data) <= preview_count * 2:
                                            # Show all data if it's small enough
                                            data_node.add(f"Values: [{preview_start}]")
                                        else:
                                            preview_end = ", ".join([f"0x{x:04X}" for x in data[-preview_count:]])
                                            data_node.add(f"Values: [{preview_start}, ... {preview_end}]")

                                            # Add statistics
                                            data_min = min(data)
                                            data_max = max(data)
                                            data_mean = sum(data) / len(data)
                                            data_node.add(f"Statistics: Min={data_min}, Max={data_max}, Mean={data_mean:.2f}")
                        elif i == preview and len(roc_bank.payload_banks) > preview * 2:
                            payload_node.add(f"... ({len(roc_bank.payload_banks) - preview * 2} more payload banks) ...")

                console.print(tree)

                # If hexdump requested, show event data
                if hexdump:
                    console.print()
                    console.print(f"[bold]Event #{event_idx} Hexdump (First 256 bytes):[/bold]")
                    display_len = min(256, evt_length)
                    event_data = evio_file.mm[evt_offset:evt_offset + display_len]
                    console.print(make_hex_dump(event_data, title=f"Event #{event_idx} Data"))

            except Exception as e:
                console.print(f"[red]Error parsing event as ROC Time Slice Bank: {str(e)}[/red]")

                # Try to display bank header info for debugging
                try:
                    # Read first two words to try to identify bank type
                    if evt_offset + 8 <= data_end:
                        first_word = struct.unpack(evio_file.header.endian + 'I',
                                                   evio_file.mm[evt_offset:evt_offset+4])[0]
                        second_word = struct.unpack(evio_file.header.endian + 'I',
                                                    evio_file.mm[evt_offset+4:evt_offset+8])[0]

                        bank_length = first_word
                        tag = (second_word >> 16) & 0xFFFF
                        data_type = (second_word >> 8) & 0xFF
                        num = second_word & 0xFF

                        console.print(f"Bank Header: Length={bank_length}, Tag=0x{tag:04X}, Type=0x{data_type:02X}, Num={num}")
                except Exception:
                    pass

                # Show hexdump for debugging
                if hexdump or verbose:
                    console.print()
                    console.print(f"[bold]Event #{event_idx} Hexdump (First 64 bytes - error case):[/bold]")
                    display_len = min(64, evt_length)
                    event_data = evio_file.mm[evt_offset:evt_offset + display_len]
                    console.print(make_hex_dump(event_data, title=f"Event #{event_idx} Data (Error)"))