import click
from rich.console import Console
from rich.table import Table
from rich import box
from pyevio.core import EvioFile
from datetime import datetime
from pyevio.roc_time_slice_bank import RocTimeSliceBank
from pyevio.utils import make_hex_dump


@click.group()
@click.version_option(version="0.1.0")
@click.option('--verbose', '-v', is_flag=True, help="Enable verbose output")
@click.pass_context
def cli(ctx, verbose):
    """EVIO v6 file inspection toolkit."""
    # Create a context object to pass data between commands
    ctx.ensure_object(dict)
    ctx.obj['VERBOSE'] = verbose

@cli.command(name="info")
@click.argument("filename", type=click.Path(exists=True))
@click.option('--verbose', '-v', is_flag=True, help="Enable verbose output")
@click.pass_context
def info_command(ctx, filename, verbose):
    """Show file metadata and structure."""
    # Use either the command-specific verbose flag or the global one
    verbose = verbose or ctx.obj.get('VERBOSE', False)
    console = Console()

    try:
        with EvioFile(filename) as evio_file:
            # Create a table for file header
            table = Table(title=f"EVIO File: {filename}", box=box.DOUBLE)
            table.add_column("Field", style="cyan")
            table.add_column("Value", style="green")

            header = evio_file.header

            # If verbose mode is enabled, display hex dump of the header
            if verbose:
                hex_dump = header.get_hex_dump(evio_file.mm, 0)
                console.print(hex_dump)
                console.print()

            # Add rows to the table
            table.add_row("Magic Number", f"EVIO (0x{header.magic_number:08X})")
            table.add_row("Format Version", str(header.version))
            table.add_row("Endianness", "Little" if header.endian == '<' else "Big")
            table.add_row("Record Count", str(header.record_count))
            table.add_row("Index Array Size", f"{header.index_array_length // 8} entries")
            table.add_row("User Header Length", f"{header.user_header_length} bytes")

            if header.trailer_position > 0:
                trailer_pos_str = f"0x{header.trailer_position:X} ({header.trailer_position / (1024*1024):.2f} MB)"
            else:
                trailer_pos_str = "Not present (0x0)"
            table.add_row("Trailer Position", trailer_pos_str)

            # Add timestamp if available via user register or other means
            # This is placeholder - actual timestamp extraction would depend on format
            table.add_row("File Size", f"{evio_file.file_size / (1024*1024):.2f} MB")

            # Print the table
            console.print(table)

            # Print record information
            console.print("\n[bold]Record Information:[/bold]")

            records_table = Table(box=box.SIMPLE)
            records_table.add_column("Record #", style="cyan")
            records_table.add_column("Offset", style="green")
            records_table.add_column("Length (words)", style="yellow")
            records_table.add_column("Events", style="magenta")
            records_table.add_column("Type", style="blue")
            records_table.add_column("Last?", style="red")

            for i, offset in enumerate(evio_file.record_offsets):
                if i < 10 or i >= len(evio_file.record_offsets) - 5 or len(evio_file.record_offsets) <= 15:
                    # Show first 10 and last 5, or all if less than 15
                    try:
                        record_header = evio_file.scan_record(evio_file.mm, offset)
                        records_table.add_row(
                            str(i),
                            f"0x{offset:X}",
                            str(record_header.record_length),
                            str(record_header.event_count),
                            record_header.event_type,
                            "✓" if record_header.is_last_record else ""
                        )
                    except Exception as e:
                        records_table.add_row(
                            str(i),
                            f"0x{offset:X}",
                            "Error", "", f"[red]{str(e)}[/red]", ""
                        )
                elif i == 10 and len(evio_file.record_offsets) > 15:
                    records_table.add_row("...", "...", "...", "...", "...", "")

            console.print(records_table)

    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        raise click.Abort()

@cli.command(name="dump")
@click.argument("filename", type=click.Path(exists=True))
@click.argument("record", type=int)
@click.option("--depth", type=int, default=5, help="Maximum depth to display")
@click.option("--color/--no-color", default=True, help="Use ANSI colors")
@click.option("--preview", type=int, default=3, help="Number of preview elements")
@click.option('--verbose', '-v', is_flag=True, help="Enable verbose output")
@click.pass_context
def dump_command(ctx, filename, record, depth, color, preview, verbose):
    """Inspect record structure in detail."""
    # Use either the command-specific verbose flag or the global one
    verbose = verbose or ctx.obj.get('VERBOSE', False)
    console = Console(highlight=color)

    try:
        with EvioFile(filename) as evio_file:
            if record < 0 or record >= len(evio_file.record_offsets):
                raise click.BadParameter(f"Record {record} out of range (0-{len(evio_file.record_offsets)-1})")

            record_offset = evio_file.record_offsets[record]
            record_header = evio_file.scan_record(evio_file.mm, record_offset)

            console.print(f"[bold]Record #{record} [Offset: 0x{record_offset:X}, Length: {record_header.record_length} words][/bold]")
            console.print(f"[bold]Type: {record_header.event_type}, Events: {record_header.event_count}[/bold]")

            # Get record data range
            data_start, data_end = evio_file.find_record(record)

            # Try to parse first bank
            try:
                bank = evio_file.parse_first_bank_header(record)

                console.print(f"[bold]├─ █ Bank 0x{bank.tag:04X} ({bank.type_name}) [Offset: +0x{bank.offset - record_offset:X}][/bold]")

                # If this is a ROC Time Slice Bank, parse it specially
                if bank.tag == RocTimeSliceBank.TAG:
                    try:
                        time_slice = RocTimeSliceBank(evio_file.mm, bank.offset, evio_file.header.endian)
                        seconds = time_slice.timestamp / 10**9  # Assuming nanoseconds
                        timestamp_str = datetime.fromtimestamp(seconds).strftime('%Y-%m-%d %H:%M:%S.%f')

                        console.print(f"[bold]│  ├─ Timestamp: {seconds} ({timestamp_str})[/bold]")

                        # For demonstration, show first few bytes of data
                        data_preview = evio_file.mm[time_slice.data_start:time_slice.data_start + min(20, time_slice.data_length)]
                        hex_values = ' '.join([f'0x{b:02X}' for b in data_preview])
                        console.print(f"[bold]│  └─ Data Preview: [{hex_values}, ...][/bold]")
                    except Exception as e:
                        console.print(f"[bold]│  └─ [red]Error parsing time slice: {str(e)}[/red][/bold]")

            except Exception as e:
                console.print(f"[red]Error parsing first bank: {str(e)}[/red]")

            # Show hexdump of record data (first 256 bytes)
            console.print("\n[bold]Record Data Hexdump (first 256 bytes):[/bold]")
            preview_len = min(256, data_end - data_start)
            data_preview = evio_file.mm[data_start:data_start + preview_len]

            console.print(make_hex_dump(data_preview))

    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        raise click.Abort()

if __name__ == "__main__":
    cli()