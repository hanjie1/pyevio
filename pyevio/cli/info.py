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

        # Add header fields to the table
        table.add_row("Magic Number", f"EVIO (0x{header.magic_number:08X})")
        table.add_row("Format Version", str(header.version))
        table.add_row("Endianness", "Little" if header.endian == '<' else "Big")
        table.add_row("Record Count", str(evio_file.record_count))
        table.add_row("Index Array Size", f"{header.index_array_length // 8} entries")
        table.add_row("User Header Length", f"{header.user_header_length} bytes")

        # Additional header fields...

        # Print the table
        console.print(table)

        # Print record information
        console.print("\n[bold]Record Information:[/bold]")

        records_table = Table(box=box.SIMPLE)
        records_table.add_column("Record #", style="cyan")
        records_table.add_column("Offset[hex]", style="green")
        records_table.add_column("(words)", style="green")
        records_table.add_column("Length (words)", style="yellow")
        records_table.add_column("Events", style="magenta")
        records_table.add_column("Type", style="blue")
        records_table.add_column("Last?", style="red")

        # Iterate through records using the new object-oriented structure
        for i in range(evio_file.record_count):
            if i < 10 or i >= evio_file.record_count - 5 or evio_file.record_count <= 15:
                try:
                    record = evio_file.get_record(i)
                    records_table.add_row(
                        str(i),
                        f"0x{record.offset:X}",
                        str(record.offset//4),
                        str(record.header.record_length),
                        str(record.event_count),
                        record.header.event_type,
                        "✓" if record.header.is_last_record else ""
                    )
                except Exception as e:
                    records_table.add_row(
                        str(i),
                        f"0x{evio_file._record_offsets[i]:X}",
                        "Error", "", f"[red]{str(e)}[/red]", ""
                    )
            elif i == 10 and evio_file.record_count > 15:
                records_table.add_row("...", "...", "...", "...", "...", "")

        console.print(records_table)

        # Print summary statistics
        console.print("\n[bold]Summary Statistics:[/bold]")
        console.print(f"Total Records: {evio_file.record_count}")
        console.print(f"Total Events (approx): {evio_file.get_total_event_count()}")
        console.print(f"File Size: {evio_file.file_size / (1024*1024):.2f} MB")