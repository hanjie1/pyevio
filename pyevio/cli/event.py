import click
from rich.console import Console
from rich.panel import Panel
from rich import box
from rich.table import Table
from rich.tree import Tree
import struct
from datetime import datetime
import numpy as np
import matplotlib.pyplot as plt
import io
from PIL import Image

from pyevio.core import EvioFile
from pyevio.roc_time_slice_bank import RocTimeSliceBank
from pyevio.utils import make_hex_dump, print_offset_hex


@click.command(name="event")
@click.argument("filename", type=click.Path(exists=True))
@click.argument("record", type=int)
@click.argument("event", type=int)
@click.option("--payload", "-p", type=int, help="Payload number to focus on (if omitted, shows all payloads)")
@click.option("--channel", "-c", type=int, help="Channel number to focus on (if omitted, shows all channels)")
@click.option("--hexdump/--no-hexdump", default=False, help="Show hex dump of event data")
@click.option("--plot/--no-plot", default=False, help="Generate plots of waveform data")
@click.option("--output", "-o", type=click.Path(), help="Save plot to file (only with --plot)")
@click.option('--verbose', '-v', is_flag=True, help="Enable verbose output")
@click.pass_context
def event_command(ctx, filename, record, event, payload, channel, hexdump, plot, output, verbose):
    """
    Display detailed information about a specific event in a record.

    Analyzes a particular event within a record, focusing on ROC Time Slice Banks
    and their payload data. Can optionally generate plots of waveform data.
    """
    # Use either the command-specific verbose flag or the global one
    verbose = verbose or ctx.obj.get('VERBOSE', False)
    console = Console()

    with EvioFile(filename, verbose) as evio_file:
        if record < 0 or record >= len(evio_file.record_offsets):
            raise click.BadParameter(f"Record {record} out of range (0-{len(evio_file.record_offsets)-1})")

        record_offset = evio_file.record_offsets[record]
        record_header = evio_file.scan_record(evio_file.mm, record_offset)

        # Calculate record data range
        data_start = record_offset + record_header.header_length * 4
        index_start = data_start
        index_end = index_start + record_header.index_array_length
        content_start = index_end + record_header.user_header_length
        data_end = record_offset + record_header.record_length * 4

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

        # Validate event index
        if event < 0 or event >= len(event_offsets):
            raise click.BadParameter(f"Event {event} out of range (0-{len(event_offsets)-1})")

        # Get event offset and length
        evt_offset_bytes = event_offsets[event]
        evt_offset_words = event_offsets[event]//4
        evt_length_bytes = event_lengths[event]
        evt_end = evt_offset_bytes + evt_length_bytes

        console.print(f"[bold cyan]Record #{record} Event #{event}[/bold cyan]")
        console.print(f"[bold]Offset: [green]0x{evt_offset_bytes:X}[{evt_offset_words}][/green], Length: [green]{evt_length_bytes}[/green] bytes[/bold]")
        if hexdump:
            print_offset_hex(evio_file.mm, evt_offset_bytes, evt_length_bytes//4, "Event content HEX:")

        # Try to parse the event as a ROC Time Slice Bank
        try:
            roc_bank = RocTimeSliceBank(evio_file.mm, evt_offset_bytes, evio_file.header.endian)

            # Create a detailed report
            console.print()
            console.print("[bold]ROC Time Slice Bank Details:[/bold]")

            # Show bank header information
            header_table = Table(box=box.SIMPLE)
            header_table.add_column("Field", style="cyan")
            header_table.add_column("Value", style="green")

            header_table.add_row("ROC ID", str(roc_bank.roc_id))
            header_table.add_row("Data Type", f"0x{roc_bank.data_type:02X} (Bank of banks)")
            header_table.add_row("Stream Status", f"0x{roc_bank.stream_status:02X}")
            header_table.add_row("Error Flag", str(roc_bank.error_flag))
            header_table.add_row("Total Streams", str(roc_bank.total_streams))
            header_table.add_row("Stream Mask", f"0x{roc_bank.stream_mask:01X}")

            # Format timestamp
            timestamp_seconds = roc_bank.sib.timestamp / 1e9  # Convert to seconds (assuming nanoseconds)
            timestamp_str = datetime.fromtimestamp(timestamp_seconds).strftime('%Y-%m-%d %H:%M:%S.%f')
            header_table.add_row("Timestamp", f"{roc_bank.sib.timestamp} ({timestamp_str})")
            header_table.add_row("Frame Number", str(roc_bank.sib.frame_number))

            console.print(header_table)

            # Show payload info
            console.print()
            console.print(f"[bold]Payload Banks ({len(roc_bank.payload_banks)}):[/bold]")

            # Filter payloads based on --payload option
            payload_indices = range(len(roc_bank.payload_banks))
            if payload is not None:
                if payload < 0 or payload >= len(roc_bank.payload_banks):
                    console.print(f"[yellow]Warning: Payload {payload} out of range (0-{len(roc_bank.payload_banks)-1})[/yellow]")
                else:
                    payload_indices = [payload]

            # Process each payload
            for p_idx in payload_indices:
                payload_bank = roc_bank.payload_banks[p_idx]
                payload_info = roc_bank.sib.payload_infos[p_idx] if p_idx < len(roc_bank.sib.payload_infos) else None

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
                    data = evio_file.mm[payload_bank.data_offset:min(payload_bank.data_offset+256, payload_bank.data_offset+payload_bank.data_length)]
                    console.print(make_hex_dump(data, title=f"Payload {p_idx} Data"))

        except Exception as e:
            console.print(f"[red]Error parsing event as ROC Time Slice Bank: {str(e)}[/red]")

            # Show hexdump of event to help debug
            if hexdump:
                console.print()
                console.print(f"[bold]Event Hexdump (First 256 bytes):[/bold]")
                event_data = evio_file.mm[evt_offset_bytes:min(evt_offset_bytes+256, evt_end)]
                console.print(make_hex_dump(event_data, title=f"Event #{event} Data"))