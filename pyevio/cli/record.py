import click
from rich.console import Console
from rich.panel import Panel
from rich import box
from rich.table import Table
from rich.tree import Tree
from rich.text import Text
from rich.columns import Columns
import struct
from datetime import datetime
import numpy as np
from collections import Counter

from pyevio.evio_file import EvioFile
from pyevio.roc_time_slice_bank import RocTimeSliceBank
from pyevio.utils import make_hex_dump, print_offset_hex


def analyze_event_tags(record, start_event=None, end_event=None, detailed=False):
    """
    Analyze event tags (signatures) within a record and their size statistics.

    Args:
        record: Record object to analyze
        start_event: Optional starting event index
        end_event: Optional ending event index (exclusive)
        detailed: Whether to include detailed size distribution

    Returns:
        Dictionary with statistics about event tags and sizes
    """
    # Get event offsets and lengths
    event_infos = record.get_event_offsets(start_event, end_event)

    if not event_infos:
        return {"tags": {}, "total_events": 0, "total_size": 0}

    # Extract offsets and lengths
    offsets = np.array([offset for offset, _ in event_infos], dtype=np.int64)
    lengths = np.array([length for _, length in event_infos], dtype=np.int64)

    # Initialize array for signatures
    signatures = np.zeros(len(offsets), dtype=np.uint32)

    # Extract signatures (tags)
    for i in range(len(offsets)):
        # Extract the second word (bytes 4-8)
        second_word = int.from_bytes(
            record.mm[offsets[i] + 4:offsets[i] + 8],
            byteorder='little' if record.endian == '<' else 'big'
        )
        signatures[i] = second_word >> 16

    # Get unique signatures and count occurrences
    unique_signatures, counts = np.unique(signatures, return_counts=True)

    # Analyze sizes by tag
    tag_stats = {}
    for sig in unique_signatures:
        mask = signatures == sig
        sig_lengths = lengths[mask]

        # Check if all events of this tag are the same size
        is_uniform = np.all(sig_lengths == sig_lengths[0])

        # Create size statistics
        stat_dict = {
            "count": int(np.sum(mask)),
            "uniform_size": is_uniform,
            "min_size": int(np.min(sig_lengths)),
            "max_size": int(np.max(sig_lengths)),
            "avg_size": float(np.mean(sig_lengths)),
            "total_size": int(np.sum(sig_lengths))
        }

        # Add detailed size distribution if requested and sizes are not uniform
        if detailed and not is_uniform:
            # Convert to regular list and use Counter for distribution
            size_counter = Counter(sig_lengths.tolist())

            # Sort by size for better presentation
            sorted_sizes = sorted(size_counter.items())

            # Store the distribution
            stat_dict["size_distribution"] = sorted_sizes

            # Calculate some additional statistics
            stat_dict["mode_size"] = int(Counter(sig_lengths).most_common(1)[0][0])
            stat_dict["median_size"] = int(np.median(sig_lengths))
            stat_dict["std_size"] = float(np.std(sig_lengths))

            # Create histogram bins for a prettier visualization
            if len(sorted_sizes) > 10:
                # If we have many different sizes, create range-based bins
                min_size = stat_dict["min_size"]
                max_size = stat_dict["max_size"]
                bin_count = min(10, max_size - min_size + 1)

                bins = np.linspace(min_size, max_size, bin_count + 1, dtype=int)
                hist, _ = np.histogram(sig_lengths, bins=bins)

                # Create bin labels
                bin_labels = [f"{bins[i]}-{bins[i+1]-1}" for i in range(len(bins)-1)]
                if bin_labels[-1].endswith("-0"):
                    bin_labels[-1] = bin_labels[-1].split("-")[0]

                stat_dict["histogram"] = list(zip(bin_labels, hist))

        tag_stats[f"0x{sig:04X}"] = stat_dict

    # Compute total stats
    result = {
        "tags": tag_stats,
        "total_events": len(signatures),
        "total_size": int(np.sum(lengths))
    }

    return result


@click.command(name="record")
@click.argument("filename", type=click.Path(exists=True))
@click.argument("record", type=int)
@click.option("--summary/--no-summary", default=True, help="Show record summary information")
@click.option("--events/--no-events", default=True, help="List events in the record")
@click.option("--tags/--no-tags", default=True, help="Show event tag statistics")
@click.option("--analyze", "-a", is_flag=True, help="Show detailed event size distribution")
@click.option("--limit", type=int, default=10, help="Limit the number of events shown in details")
@click.option("--hexdump/--no-hexdump", default=False, help="Show hex dump of record header")
@click.option('--verbose', '-v', is_flag=True, help="Enable verbose output")
@click.pass_context
def record_command(ctx, filename, record, summary, events, tags, analyze, limit, hexdump, verbose):
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
            table.add_row("Event Count", str(record_obj.event_count))
            table.add_row("Event Type", record_obj.header.event_type)
            table.add_row("Is Last Record", "Yes" if record_obj.header.is_last_record else "No")

            console.print(table)

            # Show hexdump if requested
            if hexdump:
                console.print()
                console.print(record_obj.get_hex_dump(record_obj.header.header_length, "Record Header"))

        # Show event tag statistics if requested
        if tags and record_obj.event_count > 0:
            try:
                event_analysis = analyze_event_tags(record_obj, detailed=analyze)

                # Create a table for tag statistics
                console.print()
                console.print("[bold]Event Tag Statistics:[/bold]")

                stats_table = Table(box=box.SIMPLE)
                stats_table.add_column("Tag", style="cyan")
                stats_table.add_column("Count", style="green")
                stats_table.add_column("Size (bytes)", style="yellow")
                stats_table.add_column("Uniform Size", style="magenta")
                stats_table.add_column("Total Size", style="blue")

                # Track tags with non-uniform sizes for detailed analysis
                non_uniform_tags = []

                for tag, tag_data in event_analysis["tags"].items():
                    size_info = f"{tag_data['min_size']}"
                    if not tag_data["uniform_size"]:
                        size_info += f" to {tag_data['max_size']}"
                        non_uniform_tags.append(tag)

                    stats_table.add_row(
                        tag,
                        str(tag_data["count"]),
                        size_info,
                        "✓" if tag_data["uniform_size"] else "✗",
                        f"{tag_data['total_size'] / 1024:.2f} KB"
                    )

                # Add a total row
                stats_table.add_row(
                    "[bold]Total[/bold]",
                    f"[bold]{event_analysis['total_events']}[/bold]",
                    "",
                    "",
                    f"[bold]{event_analysis['total_size'] / 1024:.2f} KB[/bold]"
                )

                console.print(stats_table)

                # Show detailed distribution for non-uniform sizes if analyze flag is set
                if analyze and non_uniform_tags:
                    console.print()
                    console.print("[bold]Event Size Distribution for Non-Uniform Tags:[/bold]")

                    for tag in non_uniform_tags:
                        tag_data = event_analysis["tags"][tag]
                        console.print(f"\n[bold cyan]{tag}[/bold cyan] (Count: {tag_data['count']}):")

                        # Print additional statistics
                        console.print(f"  Min: {tag_data['min_size']} bytes, Max: {tag_data['max_size']} bytes")
                        console.print(f"  Mean: {tag_data['avg_size']:.2f} bytes, Median: {tag_data['median_size']} bytes")
                        console.print(f"  Mode: {tag_data['mode_size']} bytes, StdDev: {tag_data['std_size']:.2f} bytes")

                        # Create a simple ASCII histogram if we have histogram data
                        if "histogram" in tag_data:
                            # Create a table for the histogram
                            hist_table = Table(box=None, show_header=False, show_edge=False, pad_edge=False)
                            hist_table.add_column("Range", style="bright_blue")
                            hist_table.add_column("Count", style="bright_green")
                            hist_table.add_column("Bar", style="yellow")

                            # Find the max count for scaling
                            max_count = max(count for _, count in tag_data["histogram"])

                            # Add rows for each bin
                            for bin_range, count in tag_data["histogram"]:
                                # Create a bar representation
                                bar_length = max(1, int(30 * count / max_count))
                                bar = "█" * bar_length

                                # Add the row
                                hist_table.add_row(
                                    f"{bin_range}",
                                    f"{count}",
                                    bar
                                )

                            console.print(hist_table)

                        # If we have the raw distribution and not many unique sizes, show them
                        elif "size_distribution" in tag_data and len(tag_data["size_distribution"]) <= 15:
                            dist_table = Table(box=None, show_header=False, show_edge=False, pad_edge=False)
                            dist_table.add_column("Size", style="bright_blue")
                            dist_table.add_column("Count", style="bright_green")
                            dist_table.add_column("Bar", style="yellow")

                            # Find the max count for scaling
                            max_count = max(count for _, count in tag_data["size_distribution"])

                            # Add rows for each unique size
                            for size, count in tag_data["size_distribution"]:
                                # Create a bar representation
                                bar_length = max(1, int(30 * count / max_count))
                                bar = "█" * bar_length

                                # Add the row
                                dist_table.add_row(
                                    f"{size}",
                                    f"{count}",
                                    bar
                                )

                            console.print(dist_table)

            except Exception as e:
                console.print(f"[red]Error analyzing event tags: {str(e)}[/red]")
                if verbose:
                    import traceback
                    console.print(f"[dim]{traceback.format_exc()}[/dim]")

        # Display events if requested
        if events and record_obj.event_count > 0:
            console.print()
            console.print("[bold]Event Index:[/bold]")

            events_table = Table(title="Events in Record", box=box.SIMPLE)
            events_table.add_column("Event #", style="cyan")
            events_table.add_column("Offset[words]", style="green")
            events_table.add_column("Length (bytes)", style="yellow")
            events_table.add_column("Tag", style="blue")
            events_table.add_column("Type", style="magenta")

            # Get all events
            record_events = record_obj.get_events()

            # Display events (with limit)
            max_display = limit
            for i, event in enumerate(record_events):
                if i < max_display // 2 or i >= len(record_events) - (max_display // 2) or len(record_events) <= max_display:
                    # Get bank type if possible
                    bank_info = event.get_bank_info()
                    tag = f"0x{bank_info.get('tag', 0):04X}" if 'tag' in bank_info else "Unknown"

                    events_table.add_row(
                        str(i),
                        f"0x{event.offset:X}[{event.offset//4}]",
                        str(event.length),
                        tag,
                        bank_info.get("bank_type", "Unknown")
                    )
                elif i == max_display // 2 and len(record_events) > max_display:
                    events_table.add_row("...", "...", "...", "...", "...")

            console.print(events_table)