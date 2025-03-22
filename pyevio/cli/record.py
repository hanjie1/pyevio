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
    """Display details about a specific record in an EVIO file."""
    verbose = verbose or ctx.obj.get('VERBOSE', False)
    console = Console()

    with EvioFile(filename, verbose) as evio_file:
        # Validate record index
        if record < 0 or record >= evio_file.record_count:
            raise click.BadParameter(f"Record {record} out of range (0-{evio_file.record_count-1})")

        # Get the record object
        record_obj = evio_file.get_record(record)

        if summary:
            # Display record header information in a table
            table = Table(title=f"Record #{record} Header", box=box.ROUNDED)
            table.add_column("Field", style="cyan")
            table.add_column("Value", style="green")

            table.add_row("Offset", f"0x{record_obj.offset:X}")
            table.add_row("Length", f"{record_obj.header.record_length} words ({record_obj.size} bytes)")
            table.add_row("Record Number", str(record_obj.header.record_number))

            # Add more record header fields...

            console.print(table)

            # Show hexdump if requested
            if hexdump:
                console.print()
                console.print(record_obj.get_hex_dump(record_obj.header.header_length, "Record Header"))

        # Display events if requested
        if events and record_obj.event_count > 0:
            console.print()
            console.print("[bold]Event Index:[/bold]")

            events_table = Table(title="Events in Record", box=box.SIMPLE)
            events_table.add_column("Event #", style="cyan")
            events_table.add_column("Offset[words]", style="green")
            events_table.add_column("Length (bytes)", style="yellow")
            events_table.add_column("Type", style="magenta")

            # Get all events
            record_events = record_obj.get_events()

            # Display events (with limit)
            max_display = limit
            for i, event in enumerate(record_events):
                if i < max_display // 2 or i >= len(record_events) - (max_display // 2) or len(record_events) <= max_display:
                    # Get bank type if possible
                    bank_info = event.get_bank_info()
                    events_table.add_row(
                        str(i),
                        f"0x{event.offset:X}[{event.offset//4}]",
                        str(event.length),
                        bank_info.get("bank_type", "Unknown")
                    )
                elif i == max_display // 2 and len(record_events) > max_display:
                    events_table.add_row("...", "...", "...", "...")

            console.print(events_table)