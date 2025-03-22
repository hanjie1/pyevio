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

def display_bank_structure(console, bank, depth=0, max_depth=5, preview=3, hexdump=False, evio_file=None):
    """
    Display bank structure in a hierarchical format.

    Args:
        console: Rich console for output
        bank: Bank object to display
        depth: Current depth level
        max_depth: Maximum depth to display
        preview: Number of elements to preview
        hexdump: Whether to show hex dumps
        evio_file: EvioFile object for hexdumps
    """
    # Create prefix based on depth
    prefix = "  " * depth

    # Display bank information
    console.print(f"{prefix}[bold]Bank 0x{bank.tag:04X} ({get_bank_type_name(bank)})[/bold]")
    console.print(f"{prefix}  Offset: 0x{bank.offset:X}[{bank.offset//4}], Length: {bank.length} words")

    # If this is a container bank, recursively display children
    if bank.is_container() and depth < max_depth:
        children = bank.get_children()

        if not children:
            console.print(f"{prefix}  [dim]No child banks[/dim]")
            return

        console.print(f"{prefix}  [bold]{len(children)} child banks:[/bold]")

        # Display each child (up to a limit)
        child_limit = min(len(children), preview * 2)
        for i, child in enumerate(children):
            if i < preview or i >= len(children) - preview or len(children) <= preview * 2:
                display_bank_structure(
                    console, child, depth + 1, max_depth, preview, hexdump, evio_file
                )
            elif i == preview and len(children) > preview * 2:
                console.print(f"{prefix}    [dim]... {len(children) - (preview * 2)} more banks ...[/dim]")

    # If this is a data bank, show preview
    elif depth < max_depth:
        # Try to get data as numpy array for better display
        data = bank.to_numpy()
        if data is not None:
            # Show preview of data
            preview_count = min(preview, len(data))
            data_preview = ", ".join([f"{x}" for x in data[:preview_count]])

            if len(data) > preview_count:
                data_preview += f", ... ({len(data) - preview_count} more values)"

            console.print(f"{prefix}  Data: [{data_preview}]")

        # Show hexdump if requested
        if hexdump and evio_file:
            display_len = min(16, bank.data_length // 4)
            if display_len > 0:
                print_offset_hex(evio_file.mm, bank.data_offset, display_len,
                                 f"{prefix}Bank Data at 0x{bank.data_offset:X}[{bank.data_offset//4}]")

def display_bank_structure(console, bank, depth=0, max_depth=5, preview=3, hexdump=False, evio_file=None):
    """
    Display bank structure in a hierarchical format.

    Args:
        console: Rich console for output
        bank: Bank object to display
        depth: Current depth level
        max_depth: Maximum depth to display
        preview: Number of elements to preview
        hexdump: Whether to show hex dumps
        evio_file: EvioFile object for hexdumps
    """
    # Create prefix based on depth
    prefix = "  " * depth

    # Display bank information
    console.print(f"{prefix}[bold]Bank 0x{bank.tag:04X} ({get_bank_type_name(bank)})[/bold]")
    console.print(f"{prefix}  Offset: 0x{bank.offset:X}[{bank.offset//4}], Length: {bank.length} words")

    # If this is a container bank, recursively display children
    if bank.is_container() and depth < max_depth:
        children = bank.get_children()

        if not children:
            console.print(f"{prefix}  [dim]No child banks[/dim]")
            return

        console.print(f"{prefix}  [bold]{len(children)} child banks:[/bold]")

        # Display each child (up to a limit)
        child_limit = min(len(children), preview * 2)
        for i, child in enumerate(children):
            if i < preview or i >= len(children) - preview or len(children) <= preview * 2:
                display_bank_structure(
                    console, child, depth + 1, max_depth, preview, hexdump, evio_file
                )
            elif i == preview and len(children) > preview * 2:
                console.print(f"{prefix}    [dim]... {len(children) - (preview * 2)} more banks ...[/dim]")

    # If this is a data bank, show preview
    elif depth < max_depth:
        # Try to get data as numpy array for better display
        data = bank.to_numpy()
        if data is not None:
            # Show preview of data
            preview_count = min(preview, len(data))
            data_preview = ", ".join([f"{x}" for x in data[:preview_count]])

            if len(data) > preview_count:
                data_preview += f", ... ({len(data) - preview_count} more values)"

            console.print(f"{prefix}  Data: [{data_preview}]")

        # Show hexdump if requested
        if hexdump and evio_file:
            display_len = min(16, bank.data_length // 4)
            if display_len > 0:
                print_offset_hex(evio_file.mm, bank.data_offset, display_len,
                                 f"{prefix}Bank Data at 0x{bank.data_offset:X}[{bank.data_offset//4}]")


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
        # Validate record index
        if record < 0 or record >= evio_file.record_count:
            raise click.BadParameter(f"Record {record} out of range (0-{evio_file.record_count-1})")

        # Get the record object
        record_obj = evio_file.get_record(record)

        console.print(f"[bold]Record #{record} [Offset: 0x{record_obj.offset:X}[{record_obj.offset//4}], Length: {record_obj.header.record_length} words][/bold]")
        console.print(f"[bold]Type: {record_obj.header.event_type}, Events: {record_obj.event_count}[/bold]")

        # Show hexdump of record header if requested
        if hexdump:
            console.print()
            print_offset_hex(evio_file.mm, record_obj.offset, record_obj.header.header_length, "Record Header")

        # Determine which events to dump
        event_count = min(events, record_obj.event_count) if events > 0 else record_obj.event_count
        events_to_dump = list(range(min(event_count, 20)))  # Limit to 20 max

        # Dump each event
        for event_idx in events_to_dump:
            try:
                event_obj = record_obj.get_event(event_idx)

                console.print()
                console.print(f"[bold yellow]Event #{event_idx} [Offset: 0x{event_obj.offset:X}[{event_obj.offset//4}], Length: {event_obj.length} bytes][/bold yellow]")

                # Show hexdump of event if requested
                if hexdump:
                    print_offset_hex(evio_file.mm, event_obj.offset, min(16, event_obj.length//4),
                                     f"Event #{event_idx} at 0x{event_obj.offset:X}[{event_obj.offset//4}]")

                # Get the bank
                try:
                    bank = event_obj.get_bank()

                    # Handle based on bank type
                    if isinstance(bank, RocTimeSliceBank):
                        # Display ROC Time Slice Bank with specialized handling
                        console.print(f"[bold]ROC Time Slice Bank [ROC ID: {bank.roc_id}][/bold]")
                        console.print(f"Timestamp: {bank.get_formatted_timestamp()}")
                        console.print(f"Frame Number: {bank.sib.frame_number}")
                        console.print(f"Payload Banks: {len(bank.payload_banks)}")

                        # Show more detailed info if verbose
                        if verbose:
                            # Display Stream Info Bank
                            console.print("\n[bold]Stream Info Bank:[/bold]")
                            display_bank_structure(console, bank.sib, 1, depth, preview, hexdump, evio_file)

                            # Display payload banks
                            for i, payload in enumerate(bank.payload_banks[:min(preview, len(bank.payload_banks))]):
                                console.print(f"\n[bold]Payload Bank #{i}:[/bold]")
                                display_bank_structure(console, payload, 1, depth, preview, hexdump, evio_file)

                            if len(bank.payload_banks) > preview:
                                console.print(f"[dim]... {len(bank.payload_banks) - preview} more payload banks ...[/dim]")
                    else:
                        # Display generic bank structure
                        display_bank_structure(console, bank, 0, depth, preview, hexdump, evio_file)

                except Exception as e:
                    console.print(f"[red]Error parsing bank: {str(e)}[/red]")
                    if verbose:
                        import traceback
                        console.print(f"[dim]{traceback.format_exc()}[/dim]")

            except Exception as e:
                console.print(f"[red]Error processing event {event_idx}: {str(e)}[/red]")

        # Show summary if multiple events processed
        if len(events_to_dump) > 1:
            console.print(f"\n[bold]Processed {len(events_to_dump)} of {record_obj.event_count} events in record {record}[/bold]")