import click
from rich.console import Console
from rich.panel import Panel
from rich import box
from rich.table import Table
from rich.tree import Tree
import os
import io
from PIL import Image
import matplotlib.pyplot as plt
from datetime import datetime

from pyevio.core import EvioFile
from pyevio.roc_time_slice_bank import RocTimeSliceBank
from pyevio.utils import make_hex_dump, print_offset_hex


def display_bank_info(console, bank, payload_filter=None, channel_filter=None, hexdump=False, plot=False, output=None):
    """
    Display detailed information about a bank.

    Args:
        console: Rich console for output
        bank: Bank object
        payload_filter: Specific payload to display (or None for all)
        channel_filter: Specific channel to display (or None for all)
        hexdump: Whether to show hex dumps
        plot: Whether to generate plots
        output: Output file for plots
    """
    # Display bank header info
    console.print(f"[bold]Bank (0x{bank.tag:04X}):[/bold]")
    console.print(f"  Offset: 0x{bank.offset:X}[{bank.offset//4}]")
    console.print(f"  Length: {bank.length} words ({bank.length * 4} bytes)")
    console.print(f"  Tag: 0x{bank.tag:04X}, Type: 0x{bank.data_type:02X}, Num: {bank.num}")

    # Handle different bank types
    if isinstance(bank, RocTimeSliceBank):
        # Special handling for ROC Time Slice Bank
        console.print(f"\n[bold]ROC Time Slice Bank Details:[/bold]")
        console.print(f"  ROC ID: {bank.roc_id}")
        console.print(f"  Timestamp: {bank.get_formatted_timestamp()}")
        console.print(f"  Frame Number: {bank.sib.frame_number}")
        console.print(f"  Payload Count: {len(bank.payload_banks)}")

        # Filter payloads if requested
        payload_indices = range(len(bank.payload_banks))
        if payload_filter is not None:
            if payload_filter < 0 or payload_filter >= len(bank.payload_banks):
                console.print(f"[yellow]Warning: Payload {payload_filter} out of range (0-{len(bank.payload_banks)-1})[/yellow]")
            else:
                payload_indices = [payload_filter]

        # Display each payload
        for p_idx in payload_indices:
            if p_idx >= len(bank.payload_banks):
                continue

            payload_bank = bank.payload_banks[p_idx]
            payload_info = bank.sib.payload_infos[p_idx] if p_idx < len(bank.sib.payload_infos) else None

            console.print(f"\n  [bold]Payload {p_idx}:[/bold]")
            console.print(f"    Offset: 0x{payload_bank.offset:X}[{payload_bank.offset//4}]")
            console.print(f"    Length: {payload_bank.length} words ({payload_bank.data_length} bytes)")
            console.print(f"    Tag: 0x{payload_bank.tag:04X}, Type: 0x{payload_bank.data_type:02X}")

            if payload_info:
                console.print(f"    Module ID: {payload_info['module_id']}, Lane: {payload_info['lane_id']}, Port: {payload_info['port_num']}")

            # Display waveform data if available
            if hasattr(payload_bank, 'num_samples') and payload_bank.num_samples > 0:
                console.print(f"    Total Samples: {payload_bank.num_samples}")

                if hasattr(payload_bank, 'channels'):
                    console.print(f"    Channels: {payload_bank.channels}")

                if hasattr(payload_bank, 'samples_per_channel'):
                    console.print(f"    Samples/Channel: {payload_bank.samples_per_channel}")

                # Handle channel filtering
                channel_indices = range(payload_bank.channels) if hasattr(payload_bank, 'channels') else [None]
                if channel_filter is not None:
                    if channel_filter < 0 or channel_filter >= payload_bank.channels:
                        console.print(f"[yellow]Warning: Channel {channel_filter} out of range (0-{payload_bank.channels-1})[/yellow]")
                    else:
                        channel_indices = [channel_filter]

                # Display each channel
                for c_idx in channel_indices:
                    try:
                        channel_data = payload_bank.get_waveform_data(c_idx)
                        if channel_data:
                            # Display statistics
                            data_min = min(channel_data)
                            data_max = max(channel_data)
                            data_mean = sum(channel_data) / len(channel_data)

                            channel_label = f" Channel {c_idx}" if c_idx is not None else ""
                            console.print(f"    [bold]{channel_label} Stats:[/bold] Min={data_min}, Max={data_max}, Mean={data_mean:.2f}")

                            # Show data preview
                            preview_count = min(8, len(channel_data))
                            preview_data = channel_data[:preview_count]
                            preview_text = ", ".join([f"0x{x:04X}" for x in preview_data])

                            if len(channel_data) <= preview_count * 2:
                                console.print(f"    Data: [{preview_text}]")
                            else:
                                end_preview = channel_data[-preview_count:]
                                end_text = ", ".join([f"0x{x:04X}" for x in end_preview])
                                console.print(f"    Data Preview: [{preview_text}, ... {end_text}]")

                            # Handle plotting if requested
                            if plot:
                                # Implement plotting or visual representation...
                                pass

                    except Exception as e:
                        console.print(f"    [red]Error processing channel data: {str(e)}[/red]")

            # Show hexdump if requested
            if hexdump:
                # Implement hexdump display...
                pass

    elif bank.is_container():
        # Handle container banks
        try:
            children = bank.get_children()
            console.print(f"\n[bold]Child Banks ({len(children)}):[/bold]")

            # Create a table for child banks
            child_table = Table(box=box.SIMPLE)
            child_table.add_column("#", style="cyan")
            child_table.add_column("Offset", style="green")
            child_table.add_column("Tag", style="yellow")
            child_table.add_column("Type", style="magenta")
            child_table.add_column("Length", style="blue")

            for i, child in enumerate(children):
                child_table.add_row(
                    str(i),
                    f"0x{child.offset:X}[{child.offset//4}]",
                    f"0x{child.tag:04X}",
                    f"0x{child.data_type:02X}",
                    f"{child.length} words"
                )

            console.print(child_table)

            # Show detailed info for first few children
            for i, child in enumerate(children[:min(3, len(children))]):
                console.print(f"\n  [bold]Child #{i} (0x{child.tag:04X}):[/bold]")

                if child.is_container():
                    grandchildren = child.get_children()
                    console.print(f"    Contains {len(grandchildren)} banks")
                else:
                    data = child.to_numpy()
                    if data is not None:
                        preview = ", ".join([str(x) for x in data[:min(5, len(data))]])
                        if len(data) > 5:
                            preview += f", ... ({len(data)} total)"
                        console.print(f"    Data: [{preview}]")

        except Exception as e:
            console.print(f"[red]Error processing child banks: {str(e)}[/red]")

    else:
        # Handle leaf banks
        data = bank.to_numpy()
        if data is not None:
            preview_count = min(10, len(data))
            preview = ", ".join([str(x) for x in data[:preview_count]])

            if len(data) > preview_count:
                preview += f", ... ({len(data)} values total)"

            console.print(f"\n[bold]Data:[/bold] {preview}")

            # Show statistics for numeric data
            if len(data) > 0:
                data_min = min(data)
                data_max = max(data)
                data_mean = sum(data) / len(data)
                console.print(f"Min: {data_min}, Max: {data_max}, Mean: {data_mean:.2f}")

        # Try string conversion for string banks
        string_data = bank.to_string()
        if string_data is not None:
            console.print(f"\n[bold]String Data:[/bold] {string_data}")


@click.command(name="event")
@click.argument("filename", type=click.Path(exists=True))
@click.argument("record", type=int)
@click.argument("event", type=int)
@click.option("--payload", "-p", type=int, help="Payload number to focus on (if omitted, shows all payloads)")
@click.option("--channel", "-c", type=int, help="Channel number to focus on (if omitted, shows all channels)")
@click.option("--hexdump/--no-hexdump", default=False, help="Show hex dump of event data")
@click.option("--plot/--no-plot", default=False, help="Generate plots of waveform data")
@click.option("--output", "-o", type=click.Path(), help="Save plot to file (only with --plot)")
@click.option('--global-index', '-g', is_flag=True, help="Interpret EVENT as a global event index across all records")
@click.option('--verbose', '-v', is_flag=True, help="Enable verbose output")
@click.pass_context
def event_command(ctx, filename, record, event, payload, channel, hexdump, plot, output, global_index, verbose):
    """
    Display detailed information about a specific event in a record.

    Analyzes a particular event within a record, focusing on ROC Time Slice Banks
    and their payload data. Can optionally generate plots of waveform data.

    If --global-index is provided, EVENT is interpreted as a global event index
    across all records, and RECORD is ignored.
    """
    verbose = verbose or ctx.obj.get('VERBOSE', False)
    console = Console()

    with EvioFile(filename, verbose) as evio_file:
        # Handle global index access if requested
        if global_index:
            try:
                record_obj, event_obj = evio_file.get_event(event)
                # Update record and event variables to match the found objects
                record = evio_file._record_offsets.index(record_obj.offset)
                event = event_obj.index

                console.print(f"[dim]Global event {event} maps to record {record}, event {event_obj.index}[/dim]")
            except IndexError as e:
                raise click.BadParameter(str(e))
        else:
            # Normal record/event access
            if record < 0 or record >= evio_file.record_count:
                raise click.BadParameter(f"Record {record} out of range (0-{evio_file.record_count-1})")

            # Get the record object
            record_obj = evio_file.get_record(record)

            # Validate event index
            if event < 0 or event >= record_obj.event_count:
                raise click.BadParameter(f"Event {event} out of range (0-{record_obj.event_count-1})")

            # Get the event object
            event_obj = record_obj.get_event(event)

        # Display event header information
        console.print(f"[bold cyan]Record #{record} Event #{event}[/bold cyan]")
        console.print(f"[bold]Offset: [green]0x{event_obj.offset:X}[{event_obj.offset//4}][/green], Length: [green]{event_obj.length}[/green] bytes[/bold]")

        # Get bank information
        bank_info = event_obj.get_bank_info()
        if bank_info:
            console.print(f"[bold]Bank Type: {bank_info.get('bank_type', 'Unknown')} (Tag: 0x{bank_info.get('tag', 0):04X})[/bold]")

        # Show hexdump if requested
        if hexdump:
            print_offset_hex(evio_file.mm, event_obj.offset, min(16, event_obj.length//4),
                             f"Event at 0x{event_obj.offset:X}[{event_obj.offset//4}]")

        # Try to get the bank
        try:
            bank = event_obj.get_bank()
            display_bank_info(console, bank, payload, channel, hexdump, plot, output)

        except Exception as e:
            console.print(f"[red]Error parsing bank: {str(e)}[/red]")
            if verbose:
                import traceback
                console.print(f"[dim]{traceback.format_exc()}[/dim]")