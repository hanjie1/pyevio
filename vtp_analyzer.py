import struct
import logging
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import click
import os

# Constants for VTP data parsing
HEADER_LENGTH = 14  # Default header length in 32-bit words
EVENT_SIZE = 356    # Default event size in bytes
FRAME_SIZE = 8      # Default frame size in bytes (2 words)

def decode_frame_channel_options(word0, word1):
    """
    Try different bit positions for extracting channel information from VTP frames.
    This helps identify the correct bit field layout for your specific hardware setup.

    Args:
        word0: First word of the frame
        word1: Second word of the frame

    Returns:
        Dictionary with different possible channel interpretations
    """
    options = {}

    # Standard pattern used initially - might be incorrect
    options["original"] = {
        "slot": (word0 >> 24) & 0xFF,
        "channel": (word0 >> 16) & 0xFF,
        "timestamp": word0 & 0xFFFF,
        "adc": word1
    }

    # Common FADC channel layouts
    # Option 1: Channel in bits 21-24 (4 bits for 16 channels)
    options["option1"] = {
        "slot": (word0 >> 27) & 0x1F,       # 5 bits for slot (0-31)
        "channel": (word0 >> 21) & 0xF,     # 4 bits for channel (0-15)
        "timestamp": word0 & 0x1FFFFF,       # Lower 21 bits for timestamp
        "adc": word1
    }

    # Option 2: Channel in bits 16-19 (4 bits for 16 channels)
    options["option2"] = {
        "slot": (word0 >> 24) & 0xFF,      # 8 bits for slot
        "channel": (word0 >> 16) & 0xF,    # 4 bits for channel (0-15)
        "timestamp": word0 & 0xFFFF,        # Lower 16 bits for timestamp
        "adc": word1
    }

    # Option 3: Assumes specific FADC250 layout
    options["fadc250"] = {
        "slot": (word0 >> 27) & 0x1F,       # 5 bits for slot (0-31)
        "channel": (word0 >> 23) & 0xF,     # 4 bits for channel (0-15)
        "timestamp": word0 & 0x7FFFFF,      # Lower 23 bits for timestamp
        "adc": word1
    }

    # Option 4: More extreme bit shift for channel
    options["extreme"] = {
        "slot": (word0 >> 27) & 0x1F,      # 5 bits for slot
        "channel": (word0 >> 19) & 0xF,    # 4 bits for channel at a different position
        "timestamp": word0 & 0x7FFFF,       # Lower 19 bits for timestamp
        "adc": word1
    }

    # Option 5: Check if channel might be in the second word
    options["word1_channel"] = {
        "slot": (word0 >> 27) & 0x1F,      # 5 bits for slot
        "channel": (word1 >> 28) & 0xF,    # 4 bits for channel in the second word
        "timestamp": word0 & 0x7FFFFFF,     # Rest of word0 as timestamp
        "adc": word1 & 0x0FFFFFFF           # Lower 28 bits as ADC value
    }

    return options

def read_vtp_file(filename, header_length=HEADER_LENGTH, event_size=EVENT_SIZE,
                  frame_size=FRAME_SIZE, max_events=None, is_big_endian=True):
    """
    Read a VTP data file and extract events and frames with multiple channel interpretations.

    Args:
        filename: Path to the VTP data file
        header_length: Header length in 32-bit words
        event_size: Event size in bytes
        frame_size: Frame size in bytes
        max_events: Maximum number of events to read (None for all)
        is_big_endian: Whether to use big-endian byte order

    Returns:
        Dictionary with events and channel statistics
    """
    byte_order = "big" if is_big_endian else "little"
    header_size = header_length * 4

    events = []
    channel_stats = {
        "original": {},
        "option1": {},
        "option2": {},
        "fadc250": {},
        "extreme": {},
        "word1_channel": {}
    }

    with open(filename, "rb") as f:
        # Get file size
        file_size = os.path.getsize(filename)

        # Skip header
        f.seek(header_size)

        # Calculate available events
        available_events = (file_size - header_size) // event_size
        events_to_read = available_events if max_events is None else min(available_events, max_events)

        print(f"Reading {events_to_read} events from {filename}...")

        # Read events
        for i in range(events_to_read):
            event_data = f.read(event_size)
            if len(event_data) < event_size:
                break

            # Process frames in this event
            frames = []

            # Skip the first word if it's 0x58 (common in VTP data)
            start_offset = 4 if event_data[:4] == b'\x00\x00\x00\x58' else 0

            for j in range(start_offset, len(event_data), frame_size):
                if j + frame_size <= len(event_data):
                    w0 = int.from_bytes(event_data[j:j+4], byte_order)
                    w1 = int.from_bytes(event_data[j+4:j+8], byte_order)

                    # Try different channel interpretations
                    options = decode_frame_channel_options(w0, w1)

                    # Update channel statistics
                    for option_name, option_data in options.items():
                        channel = option_data["channel"]
                        if channel in channel_stats[option_name]:
                            channel_stats[option_name][channel] += 1
                        else:
                            channel_stats[option_name][channel] = 1

                    # Store the frame with all options
                    frame = {
                        "word0": w0,
                        "word1": w1,
                        "options": options
                    }
                    frames.append(frame)

            # Add event to list
            events.append({
                "event_number": i + 1,
                "raw_data": event_data,
                "frames": frames
            })

            # Show progress
            if (i + 1) % 1000 == 0:
                print(f"Read {i + 1} events...")

    # Analyze channel statistics to determine the best option
    best_option = None
    max_channels = 0

    for option_name, channels in channel_stats.items():
        distinct_channels = len(channels)
        if distinct_channels > max_channels:
            max_channels = distinct_channels
            best_option = option_name

    print(f"Best channel detection option: {best_option} with {max_channels} distinct channels")
    print("Channel distributions by option:")

    for option_name, channels in channel_stats.items():
        print(f"  {option_name}: {sorted(channels.keys())}")

    return {
        "events": events,
        "channel_stats": channel_stats,
        "best_option": best_option
    }

def analyze_adc_values(events, channel_option):
    """
    Analyze ADC values across events.

    Args:
        events: List of events with frames
        channel_option: Which channel interpretation to use

    Returns:
        Dictionary with ADC statistics by slot and channel
    """
    # Initialize stats dictionary
    stats = {}

    for event in events:
        event_num = event["event_number"]

        for frame in event["frames"]:
            # Get frame data using specified option
            frame_data = frame["options"][channel_option]

            slot = frame_data["slot"]
            channel = frame_data["channel"]
            adc = frame_data["adc"]

            # Create slot-channel key
            key = f"slot{slot}-ch{channel}"

            if key not in stats:
                stats[key] = {
                    "slot": slot,
                    "channel": channel,
                    "adc_values": [],
                    "event_numbers": []
                }

            stats[key]["adc_values"].append(adc)
            stats[key]["event_numbers"].append(event_num)

    return stats

def plot_adc_values(adc_stats, output_dir=None, max_plots=16):
    """
    Generate plots of ADC values over time (event number).

    Args:
        adc_stats: Dictionary with ADC statistics
        output_dir: Directory to save plots (None for display only)
        max_plots: Maximum number of plots to generate
    """
    # Create output directory if needed
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # Sort keys by slot and channel
    sorted_keys = sorted(adc_stats.keys(),
                         key=lambda k: (adc_stats[k]["slot"], adc_stats[k]["channel"]))

    # Limit number of plots
    plot_keys = sorted_keys[:max_plots]

    # Create individual plots for each slot-channel combination
    for i, key in enumerate(plot_keys):
        data = adc_stats[key]

        plt.figure(figsize=(10, 6))
        plt.plot(data["event_numbers"], data["adc_values"], 'b-', alpha=0.7)
        plt.title(f"ADC Values for Slot {data['slot']}, Channel {data['channel']}")
        plt.xlabel("Event Number")
        plt.ylabel("ADC Value")
        plt.grid(True, alpha=0.3)

        # Add some statistics
        if len(data["adc_values"]) > 0:
            adc_mean = np.mean(data["adc_values"])
            adc_std = np.std(data["adc_values"])
            adc_min = np.min(data["adc_values"])
            adc_max = np.max(data["adc_values"])

            plt.axhline(y=adc_mean, color='r', linestyle='-', label=f"Mean: {adc_mean:.1f}")
            plt.axhline(y=adc_mean + adc_std, color='g', linestyle='--',
                        label=f"Mean + StdDev: {adc_mean + adc_std:.1f}")
            plt.axhline(y=adc_mean - adc_std, color='g', linestyle='--',
                        label=f"Mean - StdDev: {adc_mean - adc_std:.1f}")

            plt.legend()

            # Add text with statistics
            plt.figtext(0.02, 0.02,
                        f"Min: {adc_min}\nMax: {adc_max}\nMean: {adc_mean:.1f}\nStdDev: {adc_std:.1f}",
                        fontsize=9, bbox=dict(facecolor='white', alpha=0.8))

        # Save or show the plot
        if output_dir:
            plt.savefig(os.path.join(output_dir, f"{key}_adc_over_time.png"), dpi=150)
            plt.close()
        else:
            plt.tight_layout()
            plt.show()

    # Create a summary plot with the first few channels
    plt.figure(figsize=(12, 8))

    for i, key in enumerate(plot_keys[:8]):  # Limit to avoid cluttering
        data = adc_stats[key]
        plt.plot(data["event_numbers"], data["adc_values"], '-',
                 label=f"Slot {data['slot']}, Ch {data['channel']}")

    plt.title("ADC Values by Channel Over Time")
    plt.xlabel("Event Number")
    plt.ylabel("ADC Value")
    plt.grid(True, alpha=0.3)
    plt.legend()

    if output_dir:
        plt.savefig(os.path.join(output_dir, "summary_adc_over_time.png"), dpi=150)
        plt.close()
    else:
        plt.tight_layout()
        plt.show()

@click.command()
@click.argument("filename", type=click.Path(exists=True))
@click.option("--output-dir", "-o", type=click.Path(), help="Directory to save plots")
@click.option("--max-events", "-m", type=int, default=1000, help="Maximum events to process")
@click.option("--channel-option", "-c", default=None,
              help="Channel detection option to use (auto-detected if not specified)")
@click.option("--header-length", type=int, default=HEADER_LENGTH,
              help=f"Header length in 32-bit words (default: {HEADER_LENGTH})")
@click.option("--event-size", type=int, default=EVENT_SIZE,
              help=f"Event size in bytes (default: {EVENT_SIZE})")
@click.option("--big-endian", is_flag=True, default=True,
              help="Use big-endian byte order (default)")
@click.option("--little-endian", is_flag=True, help="Use little-endian byte order")
def main(filename, output_dir, max_events, channel_option, header_length,
         event_size, big_endian, little_endian):
    """
    Analyze and visualize ADC values from VTP data files.

    This tool tries different bit field interpretations to correctly identify
    channels in VTP FADC data, then plots ADC values over time.
    """
    # Handle endianness flags
    if little_endian:
        big_endian = False

    # Read the VTP file
    result = read_vtp_file(
        filename,
        header_length=header_length,
        event_size=event_size,
        max_events=max_events,
        is_big_endian=big_endian
    )

    # Use specified option or auto-detected best option
    best_option = channel_option or result["best_option"]
    print(f"Using channel detection option: {best_option}")

    # Analyze ADC values
    events = result["events"]
    adc_stats = analyze_adc_values(events, best_option)

    # Plot the results
    print(f"Generating plots for {len(adc_stats)} slot-channel combinations...")
    plot_adc_values(adc_stats, output_dir)

    print("Analysis complete!")

if __name__ == "__main__":
    main()