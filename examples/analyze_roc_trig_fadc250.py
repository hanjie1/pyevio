import argparse
import numpy as np
from pyevio import EvioFile
from pyevio.decoders.fadc250_triggered import FaDecoder, FadcDataStruct
import matplotlib.pyplot as plt
import os

def decode_fadc_bank(bank, decoder, verbose=False):
    """
    Decode a single FADC bank.

    Args:
        bank: Bank object to decode
        decoder: FaDecoder instance to use
        verbose: Enable verbose output

    Returns:
        decoder: Updated decoder with processed data
    """
    # Get the raw data from the bank
    payload = bank.get_data()

    # Convert payload to words
    words = np.frombuffer(payload, dtype=np.dtype(f'{bank.endian}u4'))

    # Process each word with the decoder
    for word in words:
        decoder.faDataDecode(int(word), verbose=verbose)

    return decoder

def process_event(event, event_index, verbose=False):
    """
    Process a single event to extract FADC data.

    Args:
        event: Event object to process
        event_index: Index of this event
        verbose: Enable verbose output

    Returns:
        dict: Dictionary containing processed event data or None if no valid data
    """
    try:
        # Get the root bank for this event
        root_bank = event.get_bank()

        # Check for physics events (0xFF50 or 0xFF60)
        if root_bank.tag not in [0xFF50, 0xFF60]:
            if verbose:
                print(f"Skipping non-physics event {event_index} with tag 0x{root_bank.tag:04X}")
            return None

        # Get child banks
        children = list(root_bank.get_children())
        if len(children) < 2:
            return None

        # Find FF21 bank (trigger bank)
        if children[0].tag == 0xFF21:
            if verbose:
                print(f"Found FF21 bank in event {event_index}")
        else:
            return None

        # Initialize data structures
        FADC_NCHAN = 16
        MAX_SAMPLES = 4096

        # Data structures to hold results
        event_data = {
            'waveforms': np.zeros((FADC_NCHAN, MAX_SAMPLES), dtype=np.int16),
            'info': {
                'slot_id': 0,
                'evt_num': 0,
                'time': 0,
                'channels': [],
                'widths': np.zeros(FADC_NCHAN, dtype=np.int32),
                'integrals': np.zeros(FADC_NCHAN, dtype=np.int32),
                'peaks': np.zeros(FADC_NCHAN, dtype=np.int32),
                'overs': np.zeros(FADC_NCHAN, dtype=np.bool_),
            },
            'has_data': False
        }

        # Process all FADC banks
        for bank in children[1:]:
            # Create a new decoder for each bank
            decoder = FaDecoder()

            # Decode the bank
            decoder = decode_fadc_bank(bank, decoder, verbose)

            # Check if we have raw data
            for chan in range(FADC_NCHAN):
                if decoder.fadc_nhit[chan] > 0:
                    # Update event data with info from this channel
                    event_data['info']['slot_id'] = decoder.fadc_data.slot_id_hd
                    event_data['info']['evt_num'] = decoder.fadc_data.evt_num_1
                    event_data['info']['time'] = decoder.fadc_trigtime

                    if chan not in event_data['info']['channels']:
                        event_data['info']['channels'].append(chan)

                    event_data['info']['widths'][chan] = decoder.fadc_data.width
                    event_data['info']['integrals'][chan] = decoder.fadc_int[chan]
                    event_data['info']['overs'][chan] = bool(decoder.fadc_data.over)

                    # Copy the raw data to our waveform array
                    if hasattr(decoder, 'frawdata'):
                        # Determine the number of valid samples
                        valid_samples = 0
                        for i, sample in enumerate(decoder.frawdata[chan]):
                            if sample > 0:  # Assuming 0 means no data
                                valid_samples = i + 1
                                # Update peak if this sample is larger
                                if sample > event_data['info']['peaks'][chan]:
                                    event_data['info']['peaks'][chan] = sample

                        # Copy data to waveform array
                        event_data['waveforms'][chan, :valid_samples] = decoder.frawdata[chan][:valid_samples]
                        event_data['has_data'] = True

        if event_data['has_data']:
            return event_data
        else:
            return None

    except Exception as e:
        print(f"Error processing event {event_index}: {e}")
        return None

def collect_event_data(events_data):
    """
    Collect data from processed events into arrays.

    Args:
        events_data: List of dictionaries containing event data

    Returns:
        tuple: (waveforms array, info structured array)
    """
    FADC_NCHAN = 16

    # Count valid events
    valid_events = len(events_data)

    if valid_events == 0:
        return np.array([]), np.array([])

    # Find maximum sample count
    max_samples = 0
    for event_data in events_data:
        for chan in range(FADC_NCHAN):
            # Find the last non-zero sample
            non_zero = np.nonzero(event_data['waveforms'][chan])[0]
            if len(non_zero) > 0:
                max_samples = max(max_samples, non_zero[-1] + 1)

    # Create waveform array
    waveforms = np.zeros((valid_events, FADC_NCHAN, max_samples), dtype=np.int16)

    # Create structured array for metadata
    fadc_dtype = np.dtype([
        ('slot_id', np.int32),
        ('evt_num', np.int32),
        ('time', np.int64),
        ('channels', np.object_),  # List of active channels
        ('widths', np.object_),    # Array of channel widths
        ('integrals', np.object_), # Array of channel integrals
        ('peaks', np.object_),     # Array of channel peaks
        ('overs', np.object_)      # Array of channel over flags
    ])

    fadc_info = np.zeros(valid_events, dtype=fadc_dtype)

    # Fill arrays
    for i, event_data in enumerate(events_data):
        # Copy waveform data
        waveforms[i, :, :] = event_data['waveforms'][:, :max_samples]

        # Copy metadata
        fadc_info[i]['slot_id'] = event_data['info']['slot_id']
        fadc_info[i]['evt_num'] = event_data['info']['evt_num']
        fadc_info[i]['time'] = event_data['info']['time']
        fadc_info[i]['channels'] = event_data['info']['channels']
        fadc_info[i]['widths'] = event_data['info']['widths']
        fadc_info[i]['integrals'] = event_data['info']['integrals']
        fadc_info[i]['peaks'] = event_data['info']['peaks']
        fadc_info[i]['overs'] = event_data['info']['overs']

    return waveforms, fadc_info

def generate_time_histogram(fadc_info, output_dir):
    """
    Generate a histogram showing event density over time.

    Args:
        fadc_info: Array containing event information
        output_dir: Directory for output files
    """
    # Extract timestamp values from all events
    times = []
    for info in fadc_info:
        # Make sure the time is actually a number and not zero
        if info['time'] > 0:
            times.append(info['time'])

    if not times:
        print("No valid time data available for histogram")
        return

    # Convert to numpy array
    times_array = np.array(times)

    # Find min and max times
    min_time = np.min(times_array)
    max_time = np.max(times_array)

    # Print time range information
    print(f"Time range: {min_time} to {max_time}")
    print(f"Time span: {max_time - min_time}")
    print(f"Number of events with time data: {len(times_array)}")

    # Calculate number of bins
    # Adjust this value for different time resolutions
    num_bins = 50
    if max_time - min_time > 0:
        bin_width = (max_time - min_time) / num_bins
        print(f"Bin width: {bin_width}")
    else:
        print("Warning: All events have the same timestamp")
        num_bins = 1

    # Create histogram
    plt.figure(figsize=(12, 6))
    counts, bins, _ = plt.hist(times_array, bins=num_bins, color='skyblue', edgecolor='black')

    # Add labels and title
    plt.title("Event Density over Time")
    plt.xlabel("Time (arbitrary units)")
    plt.ylabel("Number of Events")
    plt.grid(True, alpha=0.3)

    # Format x-axis to show reasonable tick marks
    plt.ticklabel_format(axis='x', style='sci', scilimits=(0,0))

    # Annotate with some statistics
    mean_time = np.mean(times_array)
    median_time = np.median(times_array)
    std_time = np.std(times_array)

    stats_text = (
        f"Total Events: {len(times_array)}\n"
        f"Mean Time: {mean_time:.2e}\n"
        f"Median Time: {median_time:.2e}\n"
        f"Std Dev: {std_time:.2e}\n"
        f"Min Time: {min_time:.2e}\n"
        f"Max Time: {max_time:.2e}"
    )

    # Place the text box in the upper right
    plt.annotate(stats_text, xy=(0.95, 0.95), xycoords='axes fraction',
                 bbox=dict(boxstyle="round,pad=0.5", fc="white", alpha=0.8),
                 ha='right', va='top')

    # Save the plot
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "event_time_histogram.png"))

    # Print a table of bin counts
    print("\nEvent count per time bin:")
    print(f"{'Bin Start':<15} {'Bin End':<15} {'Count':<8}")
    print("-" * 40)
    for i in range(len(counts)):
        print(f"{bins[i]:<15.2e} {bins[i+1]:<15.2e} {int(counts[i]):<8}")

    # Close the figure to free memory
    plt.close()

    return counts, bins

def generate_diagnostic_plots(waveforms, fadc_info, output_dir):
    """Generate diagnostic plots from the processed data."""
    # Create directories for plots
    channel_dir = os.path.join(output_dir, "channel_histograms")
    os.makedirs(channel_dir, exist_ok=True)

    event_dir = os.path.join(output_dir, "event_waveforms")
    os.makedirs(event_dir, exist_ok=True)

    # Plot waveforms for the first 10 events (or fewer if less are available)
    num_events_to_plot = min(10, waveforms.shape[0])
    for event_idx in range(num_events_to_plot):
        plt.figure(figsize=(12, 8))
        has_data = False

        for chan in range(waveforms.shape[1]):
            # Skip empty channels
            if np.sum(waveforms[event_idx, chan, :]) > 0:
                plt.plot(waveforms[event_idx, chan, :], label=f"Channel {chan}")
                has_data = True

        if has_data:
            plt.title(f"FADC Waveforms - Event {event_idx}")
            plt.xlabel("Sample")
            plt.ylabel("ADC Value")
            plt.legend()
            plt.grid(True)
            plt.savefig(os.path.join(event_dir, f"event_{event_idx}_waveforms.png"))
        plt.close()

    # Overall waveform plot (first event)
    if waveforms.shape[0] > 0:
        plt.figure(figsize=(12, 8))
        event_idx = 0
        for chan in range(waveforms.shape[1]):
            # Skip empty channels
            if np.sum(waveforms[event_idx, chan, :]) > 0:
                plt.plot(waveforms[event_idx, chan, :], label=f"Channel {chan}")

        plt.title(f"FADC Waveforms - Event {event_idx}")
        plt.xlabel("Sample")
        plt.ylabel("ADC Value")
        plt.legend()
        plt.grid(True)
        plt.savefig(os.path.join(output_dir, "sample_waveforms.png"))
        plt.close()

        # Plot histogram of peak ADC values
        # Extract peaks from the structured array
        all_peaks = []
        for i in range(len(fadc_info)):
            peaks = fadc_info[i]['peaks']
            for chan in range(len(peaks)):
                if peaks[chan] > 0:
                    all_peaks.append(peaks[chan])

        if all_peaks:
            plt.figure(figsize=(10, 6))
            plt.hist(all_peaks, bins=50)
            plt.title("Histogram of Peak ADC Values")
            plt.xlabel("ADC Value")
            plt.ylabel("Count")
            plt.grid(True)
            plt.savefig(os.path.join(output_dir, "peak_adc_histogram.png"))
            plt.close()

        # Plot of all integral values
        all_integrals = []
        for i in range(len(fadc_info)):
            integrals = fadc_info[i]['integrals']
            for chan in range(len(integrals)):
                if integrals[chan] > 0:
                    all_integrals.append(integrals[chan])

        if all_integrals:
            plt.figure(figsize=(10, 6))
            plt.hist(all_integrals, bins=50)
            plt.title("Histogram of All Integral Values")
            plt.xlabel("Integral")
            plt.ylabel("Count")
            plt.grid(True)
            plt.savefig(os.path.join(output_dir, "integral_histogram.png"))
            plt.close()

        # Find all active channels
        active_channels = set()
        for i in range(len(fadc_info)):
            channels = fadc_info[i]['channels']
            if isinstance(channels, list):
                active_channels.update(channels)

        print(f"Generating integral histograms for {len(active_channels)} active channels...")

        # Plot integral histograms for each active channel
        for chan in sorted(active_channels):
            # Collect integral values for this channel
            chan_integrals = []
            for i in range(len(fadc_info)):
                # Make sure the channel is active in this event
                if chan in fadc_info[i]['channels']:
                    integral = fadc_info[i]['integrals'][chan]
                    if integral > 0:
                        chan_integrals.append(integral)

            if chan_integrals:
                plt.figure(figsize=(10, 6))
                counts, bins, _ = plt.hist(chan_integrals, bins=50, alpha=0.75)

                # Add statistics
                mean_val = np.mean(chan_integrals)
                median_val = np.median(chan_integrals)
                std_val = np.std(chan_integrals)
                max_val = np.max(chan_integrals)
                min_val = np.min(chan_integrals)

                stats_text = (
                    f"Count: {len(chan_integrals)}\n"
                    f"Mean: {mean_val:.2f}\n"
                    f"Median: {median_val:.2f}\n"
                    f"Std Dev: {std_val:.2f}\n"
                    f"Min: {min_val}\n"
                    f"Max: {max_val}"
                )

                # Add text box with statistics
                plt.annotate(stats_text, xy=(0.95, 0.95), xycoords='axes fraction',
                             bbox=dict(boxstyle="round,pad=0.5", fc="white", alpha=0.8),
                             ha='right', va='top')

                plt.title(f"Channel {chan} Integral Histogram")
                plt.xlabel("Integral Value")
                plt.ylabel("Count")
                plt.grid(True, alpha=0.3)

                # Save the plot
                plt.savefig(os.path.join(channel_dir, f"channel_{chan}_integral_histogram.png"))
                plt.close()

                print(f"  Created histogram for channel {chan} with {len(chan_integrals)} entries")

def process_fadc_data(filename, max_event=None, output_dir="output", verbose=False):
    """
    Process EVIO file and extract FADC250 data into numpy arrays.

    Args:
        filename: Input EVIO file
        max_event: Maximum number of events to process (None for all)
        output_dir: Directory for output files
        verbose: Enable verbose output

    Returns:
        tuple: (waveforms array, info structured array)
    """
    print(f"Processing file: {filename}")

    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # Open the EVIO file
    with EvioFile(filename) as evio_file:
        total_event_count = evio_file.get_total_event_count()
        print(f"File contains {evio_file.record_count} records")
        print(f"File total_event_count = {total_event_count}")

        if max_event is None:
            max_event = total_event_count
        else:
            max_event = min(max_event, total_event_count)

        print(f"max_event is set to: {max_event}")

        # List to store processed event data
        processed_events = []

        # Iterate through events
        for global_evt_index, (record, event) in enumerate(evio_file.iter_events()):
            if global_evt_index >= max_event:
                break

            # Process this event
            event_data = process_event(event, global_evt_index, verbose)

            # Store valid event data
            if event_data is not None:
                processed_events.append(event_data)

                if verbose and len(processed_events) % 100 == 0:
                    print(f"Processed {len(processed_events)} valid events so far...")

        print(f"Processed {len(processed_events)} events with FADC data")

        # Collect data into arrays
        waveforms, fadc_info = collect_event_data(processed_events)

        if len(processed_events) > 0:
            print(f"Final waveform array shape: {waveforms.shape}")

            # Save data to numpy files
            np.save(os.path.join(output_dir, "fadc_waveforms.npy"), waveforms)
            np.save(os.path.join(output_dir, "fadc_info.npy"), fadc_info)

            # Generate time histogram
            print("\nGenerating time histogram...")
            generate_time_histogram(fadc_info, output_dir)

            # Generate diagnostic plots if requested
            if verbose:
                generate_diagnostic_plots(waveforms, fadc_info, output_dir)
        else:
            print("No valid FADC data found in this file.")

        return waveforms, fadc_info

def main():
    parser = argparse.ArgumentParser(description="Process EVIO files and extract FADC250 data")
    parser.add_argument("input_files", nargs="+", help="One or more EVIO files to process.")
    parser.add_argument("-e", "--events", type=int, default=None,
                        help="If set, stop processing after this many events.")
    parser.add_argument("-o", "--output-dir", default="output",
                        help="Directory where output files will be saved.")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable verbose output.")
    parser.add_argument("-p", "--plot", action="store_true",
                        help="Generate diagnostic plots.")
    parser.add_argument("-t", "--time-hist", action="store_true",
                        help="Generate only the time histogram without other plots.")
    args = parser.parse_args()

    # Run the processing for each file
    for file in args.input_files:
        waveforms, fadc_info = process_fadc_data(
            file,
            max_event=args.events,
            output_dir=args.output_dir,
            verbose=args.verbose or args.plot or args.time_hist
        )

        if waveforms.size > 0:
            print(f"Saved data to {args.output_dir}/fadc_waveforms.npy and {args.output_dir}/fadc_info.npy")

            # Print some statistics
            print("\nBasic Statistics:")
            print(f"Total events with data: {waveforms.shape[0]}")
            print(f"Channels per event: {waveforms.shape[1]}")
            print(f"Maximum samples per channel: {waveforms.shape[2]}")

            # Channel statistics
            active_channels = set()
            for i in range(len(fadc_info)):
                active_channels.update(fadc_info[i]['channels'])

            print(f"Active channels: {len(active_channels)}")
            print(f"Channels list: {sorted(list(active_channels))}")

            # Check if the time histogram was created successfully
            time_hist_path = os.path.join(args.output_dir, "event_time_histogram.png")
            if os.path.exists(time_hist_path):
                print(f"\nTime histogram saved to: {time_hist_path}")
        else:
            print("No valid FADC data found.")

if __name__ == "__main__":
    main()