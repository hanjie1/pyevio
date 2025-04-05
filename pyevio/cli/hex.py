import mmap
import os
import click
from rich.console import Console

from pyevio.utils import print_offset_hex


@click.command(name="hex")
@click.argument("filename", type=click.Path(exists=True))
@click.argument("offset", type=int, default=0)
@click.option("--size", "-s", type=int, default=30, help="Number of words to display (default: 30)")
@click.option("--bytes", "-b", is_flag=True, help="Interpret offset as bytes instead of words")
@click.option("--endian", "-e", type=click.Choice(['<', '>']), default='>', help="Endianness: < for little-endian, > for big-endian")
@click.option('--verbose', '-v', is_flag=True, help="Enable verbose output")
@click.pass_context
def hex_command(ctx, filename, offset, size, bytes, endian, verbose):
    """
    Display hexadecimal dump of memory at the specified offset.

    OFFSET is specified in number of 32-bit words by default, or in bytes if --bytes is used.

    Examples:

    \b
    # Show 30 words starting at word offset 10
    pyevio hex sample.evio 10

    \b
    # Show 20 words starting at byte offset 0x1000
    pyevio hex sample.evio 0x1000 --size 20 --bytes

    \b
    # Use big-endian interpretation
    pyevio hex sample.evio 10 --endian >
    """
    # Use either the command-specific verbose flag or the global one
    verbose = verbose or ctx.obj.get('VERBOSE', False)
    console = Console()

    # Convert word offset to byte offset if needed
    byte_offset = offset if bytes else offset * 4

    try:
        # Open the file directly rather than using EvioFile
        with open(filename, 'rb') as file:
            file_size = os.path.getsize(filename)
            with mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                title = f"Memory dump at offset: {'0x{:X}'.format(byte_offset) if bytes else f'word {offset}'}"
                print_offset_hex(mm, byte_offset, size, title, endian)
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        if verbose:
            import traceback
            console.print(traceback.format_exc())