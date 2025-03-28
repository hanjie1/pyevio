import click
from rich.console import Console
from rich.panel import Panel
from rich import box
from rich.table import Table
from rich.text import Text
from rich.progress import Progress, TaskID
import struct
from datetime import datetime
import numpy as np
from collections import Counter
import time

from pyevio.evio_file import EvioFile
from pyevio.cli.record import analyze_event_tags  # Reuse the function from record.py


def filter_valid_events(event_infos, record):
    """
    Filter out invalid or suspicious events.

    Args:
        event_infos: List of (offset, length) tuples for events
        record: Record object containing the events

    Returns:
        Filtered list of (offset, length) tuples
    """
    valid_events = []

    for offset, length in event_infos:
        # Skip suspiciously large events (>1MB - likely not a legitimate event)
        if length > 1024 * 1024:
            continue

        try:
            # Check if we can read a valid event tag
            if offset + 8 <= len(record.mm):
                second_word = int.from_bytes(
                    record.mm[offset + 4:offset + 8],
                    byteorder='little' if record.endian == '<' else 'big'
                )
                tag = second_word >> 16

                # Skip events with tag 0x0000 (likely not valid events)
                if tag == 0:
                    continue

                # This event passed validation
                valid_events.append((offset, length))
        except Exception:
            # Skip any events that cause errors
            continue

    return valid_events


def analyze_event_tags_safe(record, detailed=False):
    """
    Safely analyze event tags with validation of events.

    Args:
        record: Record object to analyze
        detailed: Whether to include detailed distribution analysis

    Returns:
        Analysis dictionary
    """
    # Get event offsets and lengths
    event_infos = record.get_event_offsets()

    # Filter out invalid events
    event_infos = filter_valid_events(event_infos, record)

    # Now proceed with regular analysis
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


def merge_tag_analyses(analyses):
    """
    Merge multiple tag analyses into a single combined analysis.

    Args:
        analyses: List of analysis dictionaries from analyze_event_tags

    Returns:
        Combined analysis dictionary
    """
    if not analyses:
        return {"tags": {}, "total_events": 0, "total_size": 0}

    # Initialize result with empty tag dictionary
    result = {
        "tags": {},
        "total_events": 0,
        "total_size": 0
    }

    # Combine tag information from all analyses
    all_tags = set()
    for analysis in analyses:
        all_tags.update(analysis["tags"].keys())

    # Process each tag
    for tag in all_tags:
        # Collect data for this tag across all analyses
        tag_data_list = [a["tags"].get(tag, {"count": 0, "total_size": 0}) for a in analyses]

        # Combine counts and sizes
        total_count = sum(td["count"] for td in tag_data_list)
        total_size = sum(td["total_size"] for td in tag_data_list)

        # Find min and max sizes accounting for potentially missing tags in some analyses
        sizes = [td for td in tag_data_list if td.get("count", 0) > 0]
        min_size = min(td["min_size"] for td in sizes) if sizes else 0
        max_size = max(td["max_size"] for td in sizes) if sizes else 0

        # Check if all events of this tag are uniform size
        is_uniform = all(td.get("uniform_size", True) for td in sizes if td.get("count", 0) > 0)
        is_uniform = is_uniform and (min_size == max_size)

        # Calculate average size
        avg_size = total_size / total_count if total_count > 0 else 0

        # Create combined tag entry
        result["tags"][tag] = {
            "count": total_count,
            "uniform_size": is_uniform,
            "min_size": min_size,
            "max_size": max_size,
            "avg_size": avg_size,
            "total_size": total_size
        }

        # Create combined size distribution for non-uniform sizes
        if not is_uniform:
            # Collect size distribution data from all records
            all_sizes = {}
            for td in tag_data_list:
                if "size_distribution" in td:
                    for size, count in td["size_distribution"]:
                        all_sizes[size] = all_sizes.get(size, 0) + count

            # Convert to sorted list of (size, count) tuples
            if all_sizes:
                size_distribution = sorted(all_sizes.items())
                result["tags"][tag]["size_distribution"] = size_distribution

                # Calculate additional statistics
                all_size_values = []
                for size, count in size_distribution:
                    all_size_values.extend([size] * count)

                # Calculate mode from the combined distribution
                if all_size_values:
                    result["tags"][tag]["mode_size"] = int(Counter(all_size_values).most_common(1)[0][0])
                    result["tags"][tag]["median_size"] = int(np.median(all_size_values))
                    result["tags"][tag]["std_size"] = float(np.std(all_size_values))

    # Update total events and size
    result["total_events"] = sum(a["total_events"] for a in analyses)
    result["total_size"] = sum(a["total_size"] for a in analyses)

    return result


def display_performance_metrics(console, analysis_duration, total_record_load_time,
                                total_analysis_time, processed_events, file_size):
    """
    Display performance metrics in a table format.

    Args:
        console: Rich console for output
        analysis_duration: Total analysis time in seconds
        total_record_load_time: Time spent loading records in seconds
        total_analysis_time: Time spent analyzing records in seconds
        processed_events: Number of events processed
        file_size: Total file size in bytes
    """
    console.print("\n[bold]Performance Metrics:[/bold]")

    perf_table = Table(box=box.SIMPLE)
    perf_table.add_column("Metric")
    perf_table.add_column("Value")

    events_per_sec = processed_events / analysis_duration if analysis_duration > 0 else 0
    mb_per_sec = file_size / (1024*1024) / analysis_duration if analysis_duration > 0 else 0

    perf_table.add_row("Total analysis time", f"{analysis_duration:.3f} seconds")
    perf_table.add_row("File read time", f"{total_record_load_time:.3f} seconds ({total_record_load_time/analysis_duration*100:.1f}%)")
    perf_table.add_row("Analysis time", f"{total_analysis_time:.3f} seconds ({total_analysis_time/analysis_duration*100:.1f}%)")
    perf_table.add_row("Event processing rate", f"{events_per_sec:.1f} events/second")
    perf_table.add_row("Data processing rate", f"{mb_per_sec:.2f} MB/second")
    perf_table.add_row("Processed events", f"{processed_events:,}")

    console.print(perf_table)


def display_progress_update(console, start_time, processed_events, processed_records,
                            prev_processed_events, prev_update_time):
    """
    Display a progress update with current processing rates.

    Args:
        console: Rich console for output
        start_time: Time when processing started
        processed_events: Total number of events processed so far
        processed_records: Number of records processed so far
        prev_processed_events: Number of events at previous update
        prev_update_time: Time of previous update
    """
    current_time = time.time()
    total_elapsed_time = current_time - start_time
    update_elapsed_time = current_time - prev_update_time

    # Calculate rate based on events processed since last update
    events_since_update = processed_events - prev_processed_events
    events_per_sec = events_since_update / update_elapsed_time if update_elapsed_time > 0 else 0

    # Calculate approximate MB processed based on average event size
    # To avoid calculating the actual bytes, we use the average event size
    avg_event_size = 88  # Average event size in bytes (typical for FF60 events)
    mb_since_update = (events_since_update * avg_event_size) / (1024*1024)
    mb_per_sec = mb_since_update / update_elapsed_time if update_elapsed_time > 0 else 0

    console.print(f"[bold]Progress Update:[/bold] {processed_records} records, {processed_events:,} events")
    console.print(f"Current rate: {events_per_sec:.1f} events/sec, {mb_per_sec:.2f} MB/sec")
    console.print(f"Elapsed: {total_elapsed_time:.1f} seconds")


def display_event_size_distribution(console, tag, tag_data):
    """
    Display the distribution of event sizes for a tag.

    Args:
        console: Rich console for output
        tag: Tag string (e.g., "0xFF60")
        tag_data: Tag data dictionary with size distribution
    """
    console.print(f"\n[bold]{tag}[/bold] (Count: {tag_data['count']:,}):")

    # Print detailed statistics if available
    if "median_size" in tag_data:
        console.print(f"  Min: {tag_data['min_size']} bytes, Max: {tag_data['max_size']} bytes")
        console.print(f"  Mean: {tag_data['avg_size']:.2f} bytes, Median: {tag_data['median_size']} bytes")
        console.print(f"  Mode: {tag_data['mode_size']} bytes, StdDev: {tag_data['std_size']:.2f} bytes")

    # Display size distribution histogram
    console.print("[bold]  Event Size Distribution:[/bold]")

    # Use raw size distribution if we have few unique sizes
    if "size_distribution" in tag_data and len(tag_data["size_distribution"]) <= 15:
        dist_table = Table(box=None, show_header=False, show_edge=False, pad_edge=False)
        dist_table.add_column("Size (bytes)")
        dist_table.add_column("Count")
        dist_table.add_column("Percentage", style="dim")
        dist_table.add_column("Bar", style="yellow")

        total_count = tag_data["count"]

        # Find the max count for scaling
        max_count = max(count for _, count in tag_data["size_distribution"])

        # Add rows for each unique size
        for size, count in tag_data["size_distribution"]:
            # Create a bar representation
            bar_length = max(1, int(30 * count / max_count))
            bar = "█" * bar_length

            # Calculate percentage
            percent = (count / total_count) * 100

            # Add the row
            dist_table.add_row(
                f"{size}",
                f"{count:,}",
                f"{percent:.2f}%",
                bar
            )

        console.print(dist_table)
    # Use binned histogram for many unique sizes
    elif "histogram" in tag_data:
        hist_table = Table(box=None, show_header=False, show_edge=False, pad_edge=False)
        hist_table.add_column("Size Range (bytes)")
        hist_table.add_column("Count")
        hist_table.add_column("Percentage", style="dim")
        hist_table.add_column("Bar", style="yellow")

        total_count = tag_data["count"]

        # Find the max count for scaling
        max_count = max(count for _, count in tag_data["histogram"])

        # Add rows for each bin
        for bin_range, count in tag_data["histogram"]:
            # Create a bar representation
            bar_length = max(1, int(30 * count / max_count))
            bar = "█" * bar_length

            # Calculate percentage
            percent = (count / total_count) * 100

            # Add the row
            hist_table.add_row(
                f"{bin_range}",
                f"{count:,}",
                f"{percent:.2f}%",
                bar
            )

        console.print(hist_table)


def display_record_analysis(console, record_idx, analysis):
    """
    Display analysis for a single record.

    Args:
        console: Rich console for output
        record_idx: Record index number
        analysis: Analysis dictionary for this record
    """
    console.print(f"\n[bold]Record #{record_idx}[/bold] ({analysis['total_events']} events):")

    # Create a table for tag statistics
    stats_table = Table(box=box.SIMPLE)
    stats_table.add_column("Tag")
    stats_table.add_column("Count")
    stats_table.add_column("Size")
    stats_table.add_column("Total Size")

    # Track non-uniform tags for distribution display
    non_uniform_tags = []

    for tag, tag_data in analysis["tags"].items():
        # For uniform sizes, just show the size
        if tag_data["uniform_size"]:
            size_info = f"{tag_data['min_size']} bytes"
        else:
            size_info = f"{tag_data['min_size']} to {tag_data['max_size']} bytes"
            non_uniform_tags.append(tag)

        stats_table.add_row(
            tag,
            str(tag_data["count"]),
            size_info,
            f"{tag_data['total_size'] / 1024:.2f} KB"
        )

    # Add a total row
    stats_table.add_row(
        "[bold]Total[/bold]",
        f"[bold]{analysis['total_events']}[/bold]",
        "",
        f"[bold]{analysis['total_size'] / 1024:.2f} KB[/bold]"
    )

    console.print(stats_table)

    # Show distributions for non-uniform sizes
    if non_uniform_tags:
        console.print(f"\n[bold]Event Size Distributions:[/bold]")

        for tag in non_uniform_tags:
            tag_data = analysis["tags"][tag]

            # Only show if we have the detailed data
            if "histogram" in tag_data or "size_distribution" in tag_data:
                display_event_size_distribution(console, tag, tag_data)


def display_file_analysis(console, combined_analysis):
    """
    Display analysis for the entire file.

    Args:
        console: Rich console for output
        combined_analysis: Combined analysis dictionary for the file
    """
    console.print("\n[bold]File-Wide Analysis:[/bold]")

    stats_table = Table(box=box.SIMPLE)
    stats_table.add_column("Tag")
    stats_table.add_column("Count")
    stats_table.add_column("Size")
    stats_table.add_column("Total Size")

    # Track non-uniform tags for distribution display
    file_non_uniform_tags = []

    for tag, tag_data in combined_analysis["tags"].items():
        # For uniform sizes, just show the size
        if tag_data["uniform_size"]:
            size_info = f"{tag_data['min_size']} bytes"
        else:
            size_info = f"{tag_data['min_size']} to {tag_data['max_size']} bytes"
            file_non_uniform_tags.append(tag)

        stats_table.add_row(
            tag,
            f"{tag_data['count']:,}",
            size_info,
            f"{tag_data['total_size'] / (1024*1024):.2f} MB"
        )

    # Add a total row
    stats_table.add_row(
        "[bold]Total[/bold]",
        f"[bold]{combined_analysis['total_events']:,}[/bold]",
        "",
        f"[bold]{combined_analysis['total_size'] / (1024*1024):.2f} MB[/bold]"
    )

    console.print(stats_table)

    # Show distribution information for non-uniform tags at file level
    if file_non_uniform_tags:
        console.print(f"\n[bold]File-Wide Event Size Distributions:[/bold]")

        for tag in file_non_uniform_tags:
            tag_data = combined_analysis["tags"][tag]

            # Display full distribution if available
            if "size_distribution" in tag_data:
                display_event_size_distribution(console, tag, tag_data)
            else:
                # Fallback to basic stats if distribution not available
                console.print(f"\n[bold]{tag}[/bold] (Count: {tag_data['count']:,}):")
                console.print(f"  Range: {tag_data['min_size']} to {tag_data['max_size']} bytes")
                console.print(f"  Mean Size: {tag_data['avg_size']:.2f} bytes")


@click.command(name="ana")
@click.argument("filename", type=click.Path(exists=True))
@click.option("--per-record", "-r", is_flag=True, help="Show per-record analysis")
@click.option("--limit", "-l", type=int, default=0, help="Limit analysis to first N records (0 for all)")
@click.option('--verbose', '-v', is_flag=True, help="Enable verbose output")
@click.pass_context
def ana_command(ctx, filename, per_record, limit, verbose):
    """Analyze event tags and sizes across the entire file with performance metrics."""
    verbose = verbose or ctx.obj.get('VERBOSE', False)
    console = Console()

    start_time = time.time()

    with EvioFile(filename, verbose) as evio_file:
        # Show file information
        console.print(f"[bold]File:[/bold] {filename}")
        console.print(f"[bold]Records:[/bold] {evio_file.record_count}")

        # Force limit to be an integer
        limit = int(limit)

        # Determine records to process
        if limit > 0:
            records_to_process = min(limit, evio_file.record_count)
        else:
            records_to_process = evio_file.record_count

        file_read_time = time.time()
        console.print(f"[dim]File opened in {(file_read_time - start_time) * 1000:.1f} ms[/dim]")

        # Process all records
        record_analyses = []

        if records_to_process < evio_file.record_count:
            console.print(f"[bold]Analyzing first {records_to_process} of {evio_file.record_count} records...[/bold]")
        else:
            console.print(f"[bold]Analyzing all {records_to_process} records...[/bold]")

        # Setup progress bar for longer processes
        with Progress() as progress:
            task = progress.add_task("[cyan]Analyzing records...", total=records_to_process)

            analysis_start_time = time.time()
            processed_events = 0
            prev_processed_events = 0
            total_record_load_time = 0
            total_analysis_time = 0
            last_progress_update = time.time()

            # Ensure we never process more than specified
            for record_idx in range(min(records_to_process, evio_file.record_count)):
                # Get and analyze the record
                record_start = time.time()
                record = evio_file.get_record(record_idx)
                record_load_time = time.time() - record_start
                total_record_load_time += record_load_time

                analysis_start = time.time()
                # Use our safe version that filters out invalid events
                record_analysis = analyze_event_tags_safe(record, detailed=True)
                analysis_time = time.time() - analysis_start
                total_analysis_time += analysis_time

                record_analyses.append(record_analysis)
                processed_events += record_analysis["total_events"]

                # Update progress
                progress.update(task, advance=1, description=f"[cyan]Analyzed {record_idx+1}/{records_to_process} records ({processed_events:,} events)")

                # Show verbose info if requested
                if verbose and record_idx % 10 == 0:
                    progress.console.print(f"Record {record_idx}: {record_analysis['total_events']} events, "
                                           f"loaded in {record_load_time * 1000:.1f} ms, "
                                           f"analyzed in {analysis_time * 1000:.1f} ms")

                # Print progress update every 5 seconds
                current_time = time.time()
                if current_time - last_progress_update >= 5.0:
                    progress.console.print("")  # Add some space
                    display_progress_update(
                        progress.console,
                        analysis_start_time,
                        processed_events,
                        record_idx + 1,
                        prev_processed_events,
                        last_progress_update
                    )
                    prev_processed_events = processed_events
                    last_progress_update = current_time

        analysis_end_time = time.time()
        analysis_duration = analysis_end_time - analysis_start_time

        # Show performance metrics
        display_performance_metrics(
            console,
            analysis_duration,
            total_record_load_time,
            total_analysis_time,
            processed_events,
            evio_file.file_size
        )

        # Show per-record analysis if requested
        if per_record:
            for record_idx, analysis in enumerate(record_analyses):
                if record_idx >= records_to_process:
                    break
                display_record_analysis(console, record_idx, analysis)

        # Merge all analyses into a single combined analysis
        combined_analysis = merge_tag_analyses(record_analyses)

        # Show combined analysis
        display_file_analysis(console, combined_analysis)