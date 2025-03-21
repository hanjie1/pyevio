import click
from rich.console import Console
from rich.table import Table
from rich import box
from datetime import datetime

from pyevio.core import EvioFile
from pyevio.utils import make_hex_dump


@click.command(name="info")
@click.argument("filename", type=click.Path(exists=True))
@click.option('--verbose', '-v', is_flag=True, help="Enable verbose output")
@click.option('--hexdump/--no-hexdump', default=False, help="Show hex dump of file header")
@click.pass_context
def info_command(ctx, filename, verbose, hexdump):
    """Show file metadata and structure."""
    # Use either the command-specific verbose flag or the global one
    verbose = verbose or ctx.obj.get('VERBOSE', False)
    console = Console()

    with EvioFile(filename, verbose) as evio_file:
        # Create a table for file header
        table = Table(title=f"EVIO File: {filename}", box=box.DOUBLE)
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="green")

        header = evio_file.header

        # If hexdump mode is enabled, display hex dump of the header
        if hexdump:
            console.print(header.get_hex_dump(evio_file.mm, 0))
            console.print()

        # Add rows to the table
        table.add_row("Magic Number", f"EVIO (0x{header.magic_number:08X})")
        table.add_row("Format Version", str(header.version))
        table.add_row("Endianness", "Little" if header.endian == '<' else "Big")
        table.add_row("Record Count", str(header.record_count))
        table.add_row("Index Array Size", f"{header.index_array_length // 8} entries")
        table.add_row("User Header Length", f"{header.user_header_length} bytes")
        table.add_row("File Type ID", f"0x{header.file_type_id:08X} ({'EVIO' if header.file_type_id == 0x4556494F else 'Unknown'})")
        table.add_row("File Number", str(header.file_number))
        table.add_row("Header Length", f"{header.header_length} words ({header.header_length * 4} bytes)")
        table.add_row("Has Dictionary", str(header.has_dictionary))
        table.add_row("Has First Event", str(header.has_first_event))
        table.add_row("Has Trailer", str(header.has_trailer))

        if header.trailer_position > 0:
            trailer_pos_str = f"0x{header.trailer_position:X} ({header.trailer_position / (1024*1024):.2f} MB)"
        else:
            trailer_pos_str = "Not present (0x0)"
        table.add_row("Trailer Position", trailer_pos_str)

        # Add timestamp info if available
        # This is a placeholder - actual timestamp extraction would depend on format
        table.add_row("File Size", f"{evio_file.file_size / (1024*1024):.2f} MB")

        # Print the table
        console.print(table)

        # Print record information
        console.print("\n[bold]Record Information:[/bold]")

        records_table = Table(box=box.SIMPLE)
        records_table.add_column("Record #", style="cyan")
        records_table.add_column("Offset", style="green")
        records_table.add_column("[Words]", style="green")
        records_table.add_column("Length (words)", style="yellow")
        records_table.add_column("Events")
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
                        str(int(offset/4)),
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

        # Print summary statistics
        console.print("\n[bold]Summary Statistics:[/bold]")

        total_events = sum(evio_file.scan_record(evio_file.mm, offset).event_count
                           for offset in evio_file.record_offsets)

        console.print(f"Total Records: {len(evio_file.record_offsets)}")
        console.print(f"Total Events (approx): {total_events}")
        console.print(f"File Size: {evio_file.file_size / (1024*1024):.2f} MB")

        # If verbose, show file structure
        if verbose:
            console.print("\n[bold]File Structure:[/bold]")
            console.print(f"File Header: 0x0 - 0x{header.header_length * 4:X} ({header.header_length * 4} bytes)")

            offset = header.header_length * 4

            if header.index_array_length > 0:
                console.print(f"Index Array: 0x{offset:X} - 0x{offset + header.index_array_length:X} ({header.index_array_length} bytes)")
                offset += header.index_array_length

            if header.user_header_length > 0:
                console.print(f"User Header: 0x{offset:X} - 0x{offset + header.user_header_length:X} ({header.user_header_length} bytes)")
                offset += header.user_header_length

            console.print(f"Records: Start at 0x{offset:X}")