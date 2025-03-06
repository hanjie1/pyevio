import click
from .parser import parse_file

@click.command()
@click.argument("filename", type=click.Path(exists=True))
@click.argument("event_number", type=int, required=False)
def main(filename, event_number):
    """
    pyevio CLI entry point.

    Usage:
      pyevio FILENAME [EVENT_NUMBER]

    If EVENT_NUMBER is omitted, it displays how many events are in the file.
    If EVENT_NUMBER is provided, it parses and prints a summary of that event.
    """
    all_events = parse_file(filename)

    if event_number is None:
        click.echo(f"Found {len(all_events)} events total.")
    else:
        # If the user wants the Nth event, we must make sure N is in [1..len]
        if event_number < 1 or event_number > len(all_events):
            click.echo(f"Event_number={event_number} out of range (1..{len(all_events)})")
            return

        # Grab that event (1-based index => event_number-1)
        evraw = all_events[event_number - 1]
        # Print a minimal summary: length, maybe first 8 bytes, etc.
        length_words = len(evraw) // 4
        click.echo(f"Event {event_number} has {length_words} words, raw size={len(evraw)} bytes")
        # Optionally show first few bytes
        if length_words <= 8:
            click.echo("Raw (hex): " + evraw.hex())
        else:
            click.echo("First 32 bytes (hex): " + evraw[:32].hex())
