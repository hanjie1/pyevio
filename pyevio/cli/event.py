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
from pyevio.utils import make_hex_dump


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
    # Use either the command-specific verbose flag or the global one
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

        # Show event information
        console.print(f"[bold cyan]Record #{record} Event #{event}[/bold cyan]")
        console.print(f"[bold]Offset: [green]0x{event_obj.offset:X}[{event_obj.offset//4}][/green], Length: [green]{event_obj.length}[/green] bytes[/bold]")

        # Get bank information
        bank_info = event_obj.get_bank_info()
        if bank_info:
            console.print(f"[bold]Bank Type: {bank_info.get('bank_type', 'Unknown')} (Tag: 0x{bank_info.get('tag', 0):04X})[/bold]")

        # Display hexdump if requested
        if hexdump:
            console.print()
            console.print(event_obj.get_hex_dump(title="Event Data"))

        # Try to get the bank object
        try:
            bank = event_obj.get_bank()

            # If it's a ROC Time Slice Bank, show detailed information
            if isinstance(bank, RocTimeSliceBank):
                console.print()
                console.print("[bold]ROC Time Slice Bank Details:[/bold]")

                # Show bank header information
                header_table = Table(box=box.SIMPLE)
                header_table.add_column("Field", style="cyan")
                header_table.add_column("Value", style="green")

                header_table.add_row("ROC ID", str(bank.roc_id))
                header_table.add_row("Data Type", f"0x{bank.data_type:02X} (Bank of banks)")
                header_table.add_row("Stream Status", f"0x{bank.stream_status:02X}")
                header_table.add_row("Error Flag", str(bank.error_flag))
                header_table.add_row("Total Streams", str(bank.total_streams))
                header_table.add_row("Stream Mask", f"0x{bank.stream_mask:01X}")

                # Format timestamp
                timestamp_seconds = bank.sib.timestamp / 1e9  # Convert to seconds (assuming nanoseconds)
                timestamp_str = datetime.fromtimestamp(timestamp_seconds).strftime('%Y-%m-%d %H:%M:%S.%f')
                header_table.add_row("Timestamp", f"{bank.sib.timestamp} ({timestamp_str})")
                header_table.add_row("Frame Number", str(bank.sib.frame_number))

                console.print(header_table)

                # Show payload info
                console.print()
                console.print(f"[bold]Payload Banks ({len(bank.payload_banks)}):[/bold]")

                # Filter payloads based on --payload option
                payload_indices = range(len(bank.payload_banks))
                if payload is not None:
                    if payload < 0 or payload >= len(bank.payload_banks):
                        console.print(f"[yellow]Warning: Payload {payload} out of range (0-{len(bank.payload_banks)-1})[/yellow]")
                    else:
                        payload_indices = [payload]

                # Process each payload
                for p_idx in payload_indices:
                    payload_bank = bank.payload_banks[p_idx]
                    payload_info = bank.sib.payload_infos[p_idx] if p_idx < len(bank.sib.payload_infos) else None

                    # Build payload info string
                    payload_header = [f"Length: {payload_bank.length} words ({payload_bank.data_length} bytes)",
                                      f"Tag: 0x{payload_bank.tag:04X}",
                                      f"Data Type: 0x{payload_bank.data_type:02X}"]

                    if payload_info:
                        payload_header.extend([
                            f"Module ID: {payload_info['module_id']}",
                            f"Bond: {payload_info['bond']}",
                            f"Lane ID: {payload_info['lane_id']}",
                            f"Port Number: {payload_info['port_num']}"
                        ])

                    # Add data analysis
                    if hasattr(payload_bank, 'num_samples'):
                        payload_header.append(f"Total Samples: {payload_bank.num_samples}")
                        if hasattr(payload_bank, 'channels'):
                            payload_header.append(f"Channels: {payload_bank.channels}")
                        if hasattr(payload_bank, 'samples_per_channel'):
                            payload_header.append(f"Samples/Channel: {payload_bank.samples_per_channel}")

                    # Create a panel for the payload
                    payload_panel = Panel(
                        "\n".join(payload_header),
                        title=f"Payload {p_idx}",
                        box=box.ROUNDED
                    )
                    console.print(payload_panel)

                    # Get waveform data for display/plotting
                    if hasattr(payload_bank, 'channels') and payload_bank.channels > 0:
                        # Filter channels if --channel option is provided
                        channel_indices = range(payload_bank.channels)
                        if channel is not None:
                            if channel < 0 or channel >= payload_bank.channels:
                                console.print(f"[yellow]Warning: Channel {channel} out of range (0-{payload_bank.channels-1})[/yellow]")
                            else:
                                channel_indices = [channel]

                        # Display/plot channel data
                        for c_idx in channel_indices:
                            try:
                                channel_data = payload_bank.get_waveform_data(c_idx)
                                if channel_data:
                                    # Display statistics
                                    data_min = min(channel_data)
                                    data_max = max(channel_data)
                                    data_mean = sum(channel_data) / len(channel_data)

                                    console.print(f"  [bold]Channel {c_idx}:[/bold] Min={data_min}, Max={data_max}, Mean={data_mean:.2f}")

                                    # Show data preview
                                    preview_count = min(8, len(channel_data))
                                    preview_start = ", ".join([f"0x{x:04X}" for x in channel_data[:preview_count]])
                                    preview_end = ", ".join([f"0x{x:04X}" for x in channel_data[-preview_count:]])

                                    if len(channel_data) <= preview_count * 2:
                                        # Show all data if it's small enough
                                        console.print(f"    Data: [{preview_start}]")
                                    else:
                                        console.print(f"    Data Preview: [{preview_start}, ... {preview_end}]")

                                    # Plot if requested
                                    if plot:
                                        # Create plot with matplotlib
                                        fig, ax = plt.subplots(figsize=(10, 6))
                                        ax.plot(channel_data, '-')
                                        ax.set_title(f"Record {record}, Event {event}, Payload {p_idx}, Channel {c_idx}")
                                        ax.set_xlabel("Sample")
                                        ax.set_ylabel("ADC Value")
                                        ax.grid(True)

                                        # Save to file if output specified
                                        if output:
                                            output_file = output
                                            if len(channel_indices) > 1 or len(payload_indices) > 1:
                                                # If multiple channels/payloads, create unique filenames
                                                base, ext = os.path.splitext(output)
                                                if not ext:
                                                    ext = ".png"
                                                output_file = f"{base}_r{record}_e{event}_p{p_idx}_c{c_idx}{ext}"

                                            plt.savefig(output_file)
                                            console.print(f"    [green]Plot saved to {output_file}[/green]")
                                        else:
                                            # Display plot in terminal using ASCII art
                                            buf = io.BytesIO()
                                            plt.savefig(buf, format='png')
                                            buf.seek(0)

                                            img = Image.open(buf)
                                            width, height = img.size

                                            # Create ASCII art from image (simple version)
                                            img = img.resize((min(80, width), min(25, height)))
                                            img = img.convert('L')  # Convert to grayscale

                                            chars = ' .:-=+*#%@'
                                            pixels = list(img.getdata())
                                            ascii_art = []

                                            for i in range(0, len(pixels), img.width):
                                                row = pixels[i:i+img.width]
                                                ascii_row = ''.join([chars[min(int(p / 25), 9)] for p in row])
                                                ascii_art.append(ascii_row)

                                            console.print("    [dim]Waveform Plot:[/dim]")
                                            console.print("    [dim]" + "\n    ".join(ascii_art) + "[/dim]")

                                        plt.close(fig)

                            except Exception as e:
                                console.print(f"  [red]Error processing channel {c_idx}: {str(e)}[/red]")

                    # Show hexdump of payload data if requested
                    if hexdump:
                        console.print()
                        console.print(f"[bold]Payload {p_idx} Hexdump (First 256 bytes):[/bold]")
                        console.print(payload_bank.get_hex_dump(256, title=f"Payload {p_idx} Data"))

            # For other bank types, show generic information
            else:
                console.print()
                console.print("[bold]Bank Information:[/bold]")

                bank_table = Table(box=box.SIMPLE)
                bank_table.add_column("Field", style="cyan")
                bank_table.add_column("Value", style="green")

                bank_table.add_row("Tag", f"0x{bank.tag:04X}")
                bank_table.add_row("Data Type", f"0x{bank.data_type:02X}")
                bank_table.add_row("Num", str(bank.num))
                bank_table.add_row("Length", f"{bank.length} words ({bank.size} bytes)")
                bank_table.add_row("Pad", str(bank.pad))

                console.print(bank_table)

                # If it's a container bank, show child banks
                if bank.is_container():
                    console.print()
                    console.print("[bold]Child Banks:[/bold]")

                    children = bank.get_children()

                    child_table = Table(box=box.SIMPLE)
                    child_table.add_column("#", style="cyan")
                    child_table.add_column("Tag", style="green")
                    child_table.add_column("Type", style="yellow")
                    child_table.add_column("Size", style="magenta")

                    for i, child in enumerate(children):
                        child_table.add_row(
                            str(i),
                            f"0x{child.tag:04X}",
                            f"0x{child.data_type:02X}",
                            f"{child.size} bytes"
                        )

                    console.print(child_table)

                # For data banks, show a preview of the data
                else:
                    console.print()
                    console.print("[bold]Data Preview:[/bold]")

                    # Try to convert to different formats
                    numpy_array = bank.to_numpy()
                    string_data = bank.to_string()

                    if string_data is not None:
                        console.print(f"String data: {string_data}")
                    elif numpy_array is not None:
                        preview_count = min(10, len(numpy_array))
                        preview = ", ".join([str(x) for x in numpy_array[:preview_count]])

                        if len(numpy_array) > preview_count:
                            preview += f", ... (total {len(numpy_array)} elements)"

                        console.print(f"Numeric data: [{preview}]")
                    else:
                        # Show hex dump of the data
                        console.print(bank.get_hex_dump(title="Bank Data"))

        except Exception as e:
            console.print(f"[red]Error parsing event bank: {str(e)}[/red]")

            # Show hexdump to help debug
            if hexdump or verbose:
                console.print()
                console.print(f"[bold]Event Hexdump (First 256 bytes):[/bold]")
                console.print(event_obj.get_hex_dump(title=f"Event #{event} Data"))