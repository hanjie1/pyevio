import struct
import logging
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import click
import os
import binascii

# Constants for VTP data parsing
HEADER_LENGTH = 14  # Default header length in 32-bit words
EVENT_SIZE = 356    # Default event size in bytes
FRAME_SIZE = 8      # Default frame size in bytes (2 words)

def diagnose_vtp_data(filename, event_count=10, max_frames=20):
    """
    Diagnose VTP data format by examining raw patterns in the data.

    Args:
        filename: Path to the VTP data file
        event_count: Number of events to examine
        max_frames: Maximum frames per event to print
    """
    print(f"Diagnosing VTP data format in: {filename}")

    with open(filename, "rb") as f:
        # Read file header
        header_size = HEADER_LENGTH * 4
        header = f.read(header_size)

        print("\nFile Header (hex):")
        for i in range(0, len(header), 16):
            chunk = header[i:i+16]
            hex_str = binascii.hexlify(chunk).decode()
            hex_formatted = ' '.join(hex_str[j:j+8] for j in range(0, len(hex_str), 8))
            print(f"  {i:04x}: {hex_formatted}")

        # Parse key header words
        if len(header) >= 16:
            word0 = struct.unpack(">I", header[0:4])[0]
            word1 = struct.unpack(">I", header[4:8])[0]
            word2 = struct.unpack(">I", header[8:12])[0]
            word3 = struct.unpack(">I", header[12:16])[0]

            print("\nKey Header Fields (big-endian):")
            print(f"  Word 0: 0x{word0:08x} (Block Length)")
            print(f"  Word 1: 0x{word1:08x} (Block Number)")
            print(f"  Word 2: 0x{word2:08x} (Header Length)")
            print(f"  Word 3: 0x{word3:08x} (Event Count)")

            # Check streaming bit (bit 15)
            bit_info = word3
            is_streaming = (bit_info >> 15) & 0x1
            print(f"  Streaming Mode: {'Yes' if is_streaming else 'No'} (bit 15 of word 3)")

        # Read sample events
        events = []
        for i in range(event_count):
            event_offset = header_size + (i * EVENT_SIZE)
            f.seek(event_offset)
            event_data = f.read(EVENT_SIZE)
            if len(event_data) < EVENT_SIZE:
                break
            events.append(event_data)

        # Analyze first word of each event
        if events:
            print("\nFirst word of each event:")
            for i, event in enumerate(events):
                if len(event) >= 4:
                    first_word = struct.unpack(">I", event[0:4])[0]
                    print(f"  Event {i+1}: 0x{first_word:08x}")

        # Analyze patterns in event frames
        if events:
            print("\nFrame Analysis for Event 1:")
            event = events[0]

            # Skip first word if it's the size marker
            start_offset = 4 if len(event) >= 4 and event[0:4] == b'\x00\x00\x00\x58' else 0

            frame_data = []
            for j in range(start_offset, min(len(event), start_offset + max_frames * FRAME_SIZE), FRAME_SIZE):
                if j + FRAME_SIZE <= len(event):
                    word0 = struct.unpack(">I", event[j:j+4])[0]
                    word1 = struct.unpack(">I", event[j+4:j+8])[0]

                    # Add frame data
                    frame_data.append((word0, word1))

            # Print raw frame data
            print("\nRaw Frame Data (hex):")
            for i, (word0, word1) in enumerate(frame_data):
                print(f"  Frame {i+1:2d}: 0x{word0:08x} 0x{word1:08x}")

            # Print binary representation for detailed bit analysis
            print("\nBinary representation of word0 (first 4 frames):")
            for i, (word0, _) in enumerate(frame_data[:4]):
                binary = bin(word0)[2:].zfill(32)
                print(f"  Frame {i+1}: {binary}")
                print(f"            {' ' * 8}|{' ' * 8}|{' ' * 8}|{' ' * 8}")
                print(f"           31       23       15        7       0")

            # Try different bit field interpretations
            print("\nTrying different bit field interpretations:")

            interpretation_options = [
                ("Standard", lambda w0: (w0 >> 27) & 0x1F, lambda w0: (w0 >> 23) & 0xF),
                ("JLab", lambda w0: (w0 >> 27) & 0x1F, lambda w0: (w0 >> 19) & 0xF),
                ("Custom1", lambda w0: (w0 >> 24) & 0xFF, lambda w0: (w0 >> 16) & 0xFF),
                ("VTP", lambda w0: (w0 >> 24) & 0xFF, lambda w0: (w0 >> 16) & 0xF),
                ("Module+Chan", lambda w0: ((w0 >> 20) & 0xF), lambda w0: (w0 >> 16) & 0xF),
                ("NoBitShift", lambda w0: w0 & 0xFFFFFFFF, lambda w0: None),
            ]

            for name, slot_fn, channel_fn in interpretation_options:
                slots = set()
                channels = set()

                for word0, _ in frame_data:
                    slot = slot_fn(word0)
                    channel = channel_fn(word0) if channel_fn is not None else None

                    slots.add(slot)
                    if channel is not None:
                        channels.add(channel)

                print(f"  {name}:")
                print(f"    Slots: {sorted(slots)}")
                if channel_fn is not None:
                    print(f"    Channels: {sorted(channels)}")

            # Special analysis for calorimeter-specific format
            print("\nCalorimeter-specific analysis:")

            # Try combining different bit fields to see if we get 32 unique values
            for i, (word0, word1) in enumerate(frame_data[:20]):  # First 20 frames
                # Extract various bit fields
                hi_byte = (word0 >> 24) & 0xFF
                mid_byte = (word0 >> 16) & 0xFF
                lo_word = word0 & 0xFFFF

                # Try different FADC250 interpretations
                slot = (word0 >> 27) & 0x1F
                crate = (word0 >> 24) & 0x7
                module = (word0 >> 19) & 0xF
                channel = (word0 >> 16) & 0xF

                # Check if composite index creates a pattern for 32 channels
                composite1 = (hi_byte << 4) | (mid_byte & 0xF)  # Combine bytes with shifting
                composite2 = ((word0 >> 20) & 0xF) * 16 + ((word0 >> 16) & 0xF)  # Module*16 + channel

                print(f"  Frame {i+1:2d}: slot={slot}, module={module}, channel={channel}, "
                      f"composite1={composite1}, composite2={composite2}")

            # Check for repeating patterns across the first few events
            if len(events) >= 2:
                print("\nChecking for repeating patterns across events...")

                # Extract frames from the first 2 events
                frames_event1 = []
                frames_event2 = []

                # Event 1
                event = events[0]
                start_offset = 4 if len(event) >= 4 and event[0:4] == b'\x00\x00\x00\x58' else 0
                for j in range(start_offset, min(len(event), start_offset + 10 * FRAME_SIZE), FRAME_SIZE):
                    if j + FRAME_SIZE <= len(event):
                        word0 = struct.unpack(">I", event[j:j+4])[0]
                        word1 = struct.unpack(">I", event[j+4:j+8])[0]
                        frames_event1.append((word0, word1))

                # Event 2
                event = events[1]
                start_offset = 4 if len(event) >= 4 and event[0:4] == b'\x00\x00\x00\x58' else 0
                for j in range(start_offset, min(len(event), start_offset + 10 * FRAME_SIZE), FRAME_SIZE):
                    if j + FRAME_SIZE <= len(event):
                        word0 = struct.unpack(">I", event[j:j+4])[0]
                        word1 = struct.unpack(">I", event[j+4:j+8])[0]
                        frames_event2.append((word0, word1))

                # Compare frames
                print("  Comparing the same frame across events:")
                for i in range(min(len(frames_event1), len(frames_event2))):
                    word0_evt1, word1_evt1 = frames_event1[i]
                    word0_evt2, word1_evt2 = frames_event2[i]

                    # Check what bits change between events
                    diff_word0 = word0_evt1 ^ word0_evt2
                    diff_word1 = word1_evt1 ^ word1_evt2

                    print(f"  Frame {i+1}:")
                    print(f"    Event 1: 0x{word0_evt1:08x} 0x{word1_evt1:08x}")
                    print(f"    Event 2: 0x{word0_evt2:08x} 0x{word1_evt2:08x}")
                    print(f"    Diff:    0x{diff_word0:08x} 0x{diff_word1:08x}")

                    # If difference is primarily in word1, that suggests word1 contains the data sample
                    # and word0 contains mostly metadata that's consistent between events

def plot_adc_patterns(filename, event_count=5, output_file=None):
    """
    Create visualizations to help understand the ADC patterns in the data.

    Args:
        filename: Path to the VTP data file
        event_count: Number of events to analyze
        output_file: Path to save the visualization (or None to display)
    """
    with open(filename, "rb") as f:
        # Skip header
        header_size = HEADER_LENGTH * 4
        f.seek(header_size)

        # Read events
        events = []
        for i in range(event_count):
            event_data = f.read(EVENT_SIZE)
            if len(event_data) < EVENT_SIZE:
                break
            events.append(event_data)

        if not events:
            print("No events found!")
            return

        # Extract frames from each event
        all_frames = []

        for event_num, event in enumerate(events):
            # Skip the first word if it's 0x58
            start_offset = 4 if len(event) >= 4 and event[0:4] == b'\x00\x00\x00\x58' else 0

            # Extract frames
            frames = []
            for j in range(start_offset, len(event), FRAME_SIZE):
                if j + FRAME_SIZE <= len(event):
                    word0 = struct.unpack(">I", event[j:j+4])[0]
                    word1 = struct.unpack(">I", event[j+4:j+8])[0]

                    # Store frame with event number for reference
                    frames.append({
                        "event": event_num + 1,
                        "word0": word0,
                        "word1": word1,
                        "possible_slot": (word0 >> 27) & 0x1F,
                        "possible_channel": (word0 >> 23) & 0xF,
                        "hi_byte": (word0 >> 24) & 0xFF,
                        "mid_byte": (word0 >> 16) & 0xFF,
                        "composite": ((word0 >> 20) & 0xF) * 16 + ((word0 >> 16) & 0xF)
                    })

            all_frames.extend(frames)

        # Now create visualizations

        # 1. Visualize word1 (ADC values) by composite channel
        composite_channels = {}

        for frame in all_frames:
            composite = frame["composite"]
            if composite not in composite_channels:
                composite_channels[composite] = []

            composite_channels[composite].append({
                "event": frame["event"],
                "adc": frame["word1"]
            })

        # 2. Create a heatmap/grid visualization to show all channels
        # This can help see if there's a pattern that matches a 4x8 calorimeter
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))

        # First plot: ADC values for a few composite channels across events
        ax = axes[0, 0]
        for composite, data in list(composite_channels.items())[:5]:  # First 5 channels
            events = [d["event"] for d in data]
            adc_values = [d["adc"] for d in data]
            ax.plot(events, adc_values, 'o-', label=f"Channel {composite}")

        ax.set_title("ADC Values by Composite Channel (first 5 channels)")
        ax.set_xlabel("Event Number")
        ax.set_ylabel("ADC Value")
        ax.legend()
        ax.grid(True, alpha=0.3)

        # Second plot: Distribution of composite channel values
        ax = axes[0, 1]
        composite_values = list(composite_channels.keys())
        composite_counts = [len(composite_channels[c]) for c in composite_values]

        ax.bar(composite_values, composite_counts)
        ax.set_title("Distribution of Composite Channel Values")
        ax.set_xlabel("Composite Channel")
        ax.set_ylabel("Frame Count")
        ax.grid(True, alpha=0.3)

        # Third plot: Visualize using module and channel separately
        ax = axes[1, 0]
        module_channel_map = {}

        for frame in all_frames:
            module = (frame["word0"] >> 20) & 0xF
            channel = (frame["word0"] >> 16) & 0xF
            key = f"{module}:{channel}"

            if key not in module_channel_map:
                module_channel_map[key] = []

            module_channel_map[key].append(frame["word1"])  # ADC value

        # Get unique modules and channels
        modules = sorted(set((frame["word0"] >> 20) & 0xF for frame in all_frames))
        channels = sorted(set((frame["word0"] >> 16) & 0xF for frame in all_frames))

        # Create a 2D grid for visualization
        grid_data = np.zeros((len(modules), len(channels)))

        for i, module in enumerate(modules):
            for j, channel in enumerate(channels):
                key = f"{module}:{channel}"
                if key in module_channel_map:
                    # Use average ADC value for this module/channel
                    grid_data[i, j] = np.mean(module_channel_map[key])

        img = ax.imshow(grid_data, cmap='viridis')
        ax.set_title("Average ADC Value by Module and Channel")
        ax.set_xlabel("Channel")
        ax.set_ylabel("Module")
        ax.set_xticks(range(len(channels)))
        ax.set_yticks(range(len(modules)))
        ax.set_xticklabels(channels)
        ax.set_yticklabels(modules)
        fig.colorbar(img, ax=ax, label="Average ADC Value")

        # Fourth plot: Histogram of ADC values
        ax = axes[1, 1]
        all_adc_values = [frame["word1"] for frame in all_frames]
        ax.hist(all_adc_values, bins=50)
        ax.set_title("Histogram of All ADC Values")
        ax.set_xlabel("ADC Value")
        ax.set_ylabel("Count")
        ax.grid(True, alpha=0.3)

        plt.tight_layout()

        if output_file:
            plt.savefig(output_file, dpi=150)
            print(f"Visualization saved to {output_file}")
        else:
            plt.show()

        # Final analysis: Check how many times each composite channel appears per event
        # This can help confirm if we're seeing a fixed number of channels per event
        channel_counts_per_event = {}

        for event_num in range(1, event_count + 1):
            # Count channels in this event
            channels_in_event = {}

            for frame in all_frames:
                if frame["event"] == event_num:
                    composite = frame["composite"]
                    if composite not in channels_in_event:
                        channels_in_event[composite] = 0
                    channels_in_event[composite] += 1

            channel_counts_per_event[event_num] = channels_in_event

        print("\nChannel counts per event:")
        for event_num, counts in channel_counts_per_event.items():
            unique_channels = len(counts)
            print(f"  Event {event_num}: {unique_channels} unique channels")

            # List channels with counts
            for composite, count in sorted(counts.items()):
                print(f"    Channel {composite}: {count} frames")

@click.command()
@click.argument("filename", type=click.Path(exists=True))
@click.option("--diagnose", is_flag=True, help="Run detailed diagnostic on data format")
@click.option("--plot", is_flag=True, help="Create visualization of ADC patterns")
@click.option("--events", type=int, default=5, help="Number of events to analyze")
@click.option("--output", type=click.Path(), help="Output file path for visualization")
def main(filename, diagnose, plot, events, output):
    """
    VTP Data Diagnostic Tool

    This tool helps analyze the structure and patterns in VTP data files,
    particularly for FADC data from calorimeter setups.
    """
    if diagnose:
        diagnose_vtp_data(filename, event_count=events)

    if plot:
        plot_adc_patterns(filename, event_count=events, output_file=output)

    if not diagnose and not plot:
        # Default to both if no specific action requested
        diagnose_vtp_data(filename, event_count=events)
        plot_adc_patterns(filename, event_count=events)

if __name__ == "__main__":
    main()