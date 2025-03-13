import struct
import logging
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import click
import os
import time
from datetime import datetime, timedelta

# Constants for VTP data parsing
HEADER_LENGTH = 14  # Default header length in 32-bit words
EVENT_SIZE = 356    # Default event size in bytes
FRAME_SIZE = 8      # Default frame size in bytes (2 words)

def has_cosmic_data(event_data):
    """
    Check if an event contains cosmic ray data or is just empty 0x58 frames.

    Args:
        event_data: Raw event bytes

    Returns:
        True if the event contains cosmic ray data, False otherwise
    """
    # Skip first word (0x58 size marker)
    for i in range(4, len(event_data), FRAME_SIZE):
        if i + FRAME_SIZE <= len(event_data):
            # Check if the frame has something other than 0x58
            if event_data[i:i+4] != b'\x00\x00\x00\x58':
                return True

    return False

def parse_cosmic_event(event_data, is_big_endian=True):
    """
    Parse an event that contains cosmic ray data.

    Args:
        event_data: Raw event bytes
        is_big_endian: Whether to interpret as big-endian

    Returns:
        List of decoded frames with cosmic ray data
    """
    byte_order = ">" if is_big_endian else "<"
    frames = []

    # Skip first word (0x58 size marker)
    for i in range(4, len(event_data), FRAME_SIZE):
        if i + FRAME_SIZE <= len(event_data):
            word0 = struct.unpack(byte_order + "I", event_data[i:i+4])[0]
            word1 = struct.unpack(byte_order + "I", event_data[i+4:i+8])[0]

            # Check if this is a cosmic ray hit (non-zero data)
            # Look for the 0xFF marker in the high byte
            if (word0 >> 24) == 0xFF:
                # Extract fields - these are based on observed values
                module = (word0 >> 16) & 0xFF
                channel = (word0 >> 8) & 0xFF
                adc_value = word1

                frames.append({
                    "word0": word0,
                    "word1": word1,
                    "module": module,
                    "channel": channel,
                    "adc": adc_value,
                    "hex": f"0x{word0:08x} 0x{word1:08x}"
                })

    return frames

def scan_cosmic_file(filename, max_events=None, check_every=100, verbose=False):
    """
    Scan a VTP file for cosmic ray events.

    Args:
        filename: Path to the VTP data file
        max_events: Maximum number of events to scan (None for all)
        check_every: Only check every N events for cosmic data
        verbose: Print verbose output

    Returns:
        List of event numbers that contain cosmic ray data
    """
    print(f"Scanning {filename} for cosmic ray events...")

    cosmic_events = []
    total_events = 0
    start_time = time.time()

    with open(filename, "rb") as f:
        # Skip header
        header_size = HEADER_LENGTH * 4
        f.seek(header_size)

        # Get file size
        f.seek(0, 2)
        file_size = f.tell()
        f.seek(header_size)

        # Calculate number of events
        available_events = (file_size - header_size) // EVENT_SIZE
        events_to_scan = available_events if max_events is None else min(available_events, max_events)

        print(f"File contains approximately {available_events:,} events")
        print(f"Will scan {events_to_scan:,} events, checking every {check_every}")

        # Scan for cosmic events
        last_update = time.time()

        for i in range(events_to_scan):
            if i % check_every == 0:  # Only check every Nth event for speed
                # Calculate position and read event
                event_offset = header_size + (i * EVENT_SIZE)
                f.seek(event_offset)
                event_data = f.read(EVENT_SIZE)

                # Check if it contains cosmic data
                if has_cosmic_data(event_data):
                    cosmic_events.append(i + 1)  # Convert to 1-based event number
                    if verbose:
                        print(f"Found cosmic data in event {i+1}")

            # Update progress every second
            current_time = time.time()
            if current_time - last_update >= 1.0:
                progress = (i + 1) / events_to_scan * 100
                elapsed = current_time - start_time
                estimated_total = elapsed / (i + 1) * events_to_scan
                remaining = estimated_total - elapsed

                print(f"Progress: {progress:.1f}% ({i+1:,}/{events_to_scan:,}) - "
                      f"Found {len(cosmic_events)} cosmic events - "
                      f"ETA: {timedelta(seconds=int(remaining))}")

                last_update = current_time

    total_time = time.time() - start_time
    print(f"Scan complete. Found {len(cosmic_events)} cosmic events in {total_time:.1f} seconds")

    return cosmic_events

def analyze_cosmic_event(filename, event_number, is_big_endian=True, verbose=False):
    """
    Analyze a specific cosmic ray event in detail.

    Args:
        filename: Path to the VTP data file
        event_number: Event number to analyze (1-based)
        is_big_endian: Whether to interpret as big-endian
        verbose: Print verbose output

    Returns:
        Dictionary with event analysis
    """
    with open(filename, "rb") as f:
        # Calculate position
        header_size = HEADER_LENGTH * 4
        event_offset = header_size + ((event_number - 1) * EVENT_SIZE)

        # Read event
        f.seek(event_offset)
        event_data = f.read(EVENT_SIZE)

        if len(event_data) < EVENT_SIZE:
            print(f"Error: Could not read event {event_number}")
            return None

        # Parse the event
        frames = parse_cosmic_event(event_data, is_big_endian)

        if verbose:
            print(f"Event {event_number} contains {len(frames)} cosmic ray hits:")
            for i, frame in enumerate(frames):
                print(f"  Hit {i+1}: Module={frame['module']} Channel={frame['channel']} ADC={frame['adc']}")

        return {
            "event_number": event_number,
            "frames": frames,
            "total_hits": len(frames)
        }

def visualize_calorimeter(hits, output_file=None, title=None):
    """
    Visualize hits in a 4x8 calorimeter.

    Args:
        hits: List of hits with module and channel information
        output_file: Path to save the plot (None to display)
        title: Plot title
    """
    # Create a 4x8 grid for the calorimeter
    grid = np.zeros((4, 8))

    # Fill grid with hit information
    for hit in hits:
        # Extract module and channel
        module = hit.get("module", 0)
        channel = hit.get("channel", 0)
        adc = hit.get("adc", 0)

        # Map module/channel to grid position
        # This mapping depends on your hardware setup - adjust as needed
        row = module % 4  # Assume modules 0-3 map to rows
        col = channel % 8  # Assume channels 0-7 map to columns

        # Add ADC value to the grid
        grid[row, col] += adc

    # Create the plot
    plt.figure(figsize=(10, 6))

    # Plot the grid
    plt.imshow(grid, cmap='viridis', interpolation='nearest')
    plt.colorbar(label='ADC Value')

    # Add grid lines
    plt.grid(True, color='white', linestyle='-', linewidth=0.5, alpha=0.3)

    # Add labels
    plt.xlabel('Channel')
    plt.ylabel('Module')
    plt.title(title or 'Cosmic Ray Hits in 4x8 Calorimeter')

    # Add axis ticks
    plt.xticks(range(8), range(8))
    plt.yticks(range(4), range(4))

    # Save or show
    if output_file:
        plt.savefig(output_file, dpi=150)
        plt.close()
    else:
        plt.tight_layout()
        plt.show()

def visualize_cosmic_events(filename, event_numbers, output_dir=None, is_big_endian=True):
    """
    Visualize multiple cosmic ray events.

    Args:
        filename: Path to the VTP data file
        event_numbers: List of event numbers to visualize
        output_dir: Directory to save plots (None to display)
        is_big_endian: Whether to interpret as big-endian
    """
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    for i, event_num in enumerate(event_numbers):
        # Analyze the event
        event_data = analyze_cosmic_event(filename, event_num, is_big_endian)

        if event_data and event_data["frames"]:
            # Visualize the event
            output_file = None
            if output_dir:
                output_file = os.path.join(output_dir, f"cosmic_event_{event_num}.png")

            visualize_calorimeter(
                event_data["frames"],
                output_file=output_file,
                title=f"Cosmic Ray Event #{event_num} ({len(event_data['frames'])} hits)"
            )

            print(f"Visualized event {event_num} ({i+1}/{len(event_numbers)})")
        else:
            print(f"Skipping event {event_num} - no cosmic data found")

        # If displaying, only show a few at a time
        if not output_dir and i >= 5:
            user_input = input("Show more events? (y/n): ")
            if user_input.lower() != 'y':
                break

def plot_time_distribution(filename, cosmic_events, output_file=None):
    """
    Plot the time distribution of cosmic ray events.

    Args:
        filename: Path to the VTP data file
        cosmic_events: List of event numbers with cosmic ray data
        output_file: Path to save the plot (None to display)
    """
    if not cosmic_events:
        print("No cosmic events to plot")
        return

    # Create the plot
    plt.figure(figsize=(12, 6))

    # Calculate time between events (assuming constant data collection rate)
    event_spacing = np.diff(cosmic_events)

    # Plot histogram of time between events
    plt.subplot(2, 1, 1)
    plt.hist(event_spacing, bins=50, alpha=0.7)
    plt.xlabel('Events Between Cosmic Rays')
    plt.ylabel('Frequency')
    plt.title('Distribution of Time Between Cosmic Ray Events')
    plt.grid(True, alpha=0.3)

    # Plot cumulative distribution of events over time
    plt.subplot(2, 1, 2)
    plt.plot(range(len(cosmic_events)), cosmic_events, 'b-')
    plt.xlabel('Cosmic Event Index')
    plt.ylabel('Event Number')
    plt.title('Cumulative Distribution of Cosmic Events')
    plt.grid(True, alpha=0.3)

    plt.tight_layout()

    # Save or show
    if output_file:
        plt.savefig(output_file, dpi=150)
        plt.close()
    else:
        plt.show()

@click.command()
@click.argument("filename", type=click.Path(exists=True))
@click.option("--scan", is_flag=True, help="Scan file for cosmic ray events")
@click.option("--max-events", type=int, help="Maximum events to scan")
@click.option("--check-every", type=int, default=100, help="Check every N events for cosmic data")
@click.option("--event", type=int, help="Analyze specific event number")
@click.option("--output-dir", type=click.Path(), help="Directory to save output files")
@click.option("--little-endian", is_flag=True, help="Use little-endian interpretation")
@click.option("--verbose", is_flag=True, help="Print verbose output")
def main(filename, scan, max_events, check_every, event, output_dir, little_endian, verbose):
    """
    Cosmic Ray Data Analyzer for VTP files.

    This tool analyzes VTP data files containing cosmic ray events from a calorimeter setup.
    It can scan for cosmic events, visualize individual events, and analyze hit patterns.
    """
    is_big_endian = not little_endian

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    if scan:
        # Scan for cosmic events
        cosmic_events = scan_cosmic_file(
            filename,
            max_events=max_events,
            check_every=check_every,
            verbose=verbose
        )

        # Save the event list
        if output_dir:
            output_file = os.path.join(output_dir, "cosmic_events.txt")
            with open(output_file, "w") as f:
                f.write("\n".join(str(e) for e in cosmic_events))
            print(f"Saved cosmic event list to {output_file}")

        # Plot time distribution
        if cosmic_events:
            output_file = None
            if output_dir:
                output_file = os.path.join(output_dir, "cosmic_time_distribution.png")

            plot_time_distribution(filename, cosmic_events, output_file)

        # Visualize a sample of cosmic events
        if cosmic_events:
            sample_size = min(10, len(cosmic_events))
            sample_indices = np.linspace(0, len(cosmic_events)-1, sample_size, dtype=int)
            sample_events = [cosmic_events[i] for i in sample_indices]

            visualize_cosmic_events(
                filename,
                sample_events,
                output_dir=output_dir,
                is_big_endian=is_big_endian
            )

    elif event:
        # Analyze specific event
        event_data = analyze_cosmic_event(
            filename,
            event,
            is_big_endian=is_big_endian,
            verbose=True
        )

        if event_data and event_data["frames"]:
            # Visualize the event
            output_file = None
            if output_dir:
                output_file = os.path.join(output_dir, f"cosmic_event_{event}.png")

            visualize_calorimeter(
                event_data["frames"],
                output_file=output_file,
                title=f"Cosmic Ray Event #{event} ({len(event_data['frames'])} hits)"
            )
        else:
            print(f"No cosmic ray data found in event {event}")

    else:
        # Default action: check a few random events for cosmic data
        print("Checking random events for cosmic ray data...")

        with open(filename, "rb") as f:
            # Get file size
            f.seek(0, 2)
            file_size = f.tell()

            # Calculate number of events
            header_size = HEADER_LENGTH * 4
            available_events = (file_size - header_size) // EVENT_SIZE

            # Check a sample of events
            found_cosmic = False
            sample_size = min(1000, available_events)

            for _ in range(100):  # Try up to 100 random events
                # Pick a random event
                event_num = np.random.randint(1, available_events + 1)

                # Calculate position and read event
                event_offset = header_size + ((event_num - 1) * EVENT_SIZE)
                f.seek(event_offset)
                event_data = f.read(EVENT_SIZE)

                # Check if it contains cosmic data
                if has_cosmic_data(event_data):
                    found_cosmic = True
                    print(f"Found cosmic data in event {event_num}")

                    # Analyze the event
                    event_analysis = analyze_cosmic_event(
                        filename,
                        event_num,
                        is_big_endian=is_big_endian,
                        verbose=True
                    )

                    # Visualize the event
                    if event_analysis and event_analysis["frames"]:
                        output_file = None
                        if output_dir:
                            output_file = os.path.join(output_dir, f"cosmic_event_{event_num}.png")

                        visualize_calorimeter(
                            event_analysis["frames"],
                            output_file=output_file,
                            title=f"Cosmic Ray Event #{event_num} ({len(event_analysis['frames'])} hits)"
                        )

                    # Ask to continue
                    if not output_dir:
                        user_input = input("Look for more cosmic events? (y/n): ")
                        if user_input.lower() != 'y':
                            break

            if not found_cosmic:
                print("No cosmic events found in the random sample.")
                print("Try using --scan to perform a comprehensive scan of the file.")

if __name__ == "__main__":
    main()