import click
from rich.console import Console
from rich.table import Table
from rich import box
from datetime import datetime

from pyevio.evio_file import EvioFile
from pyevio.utils import make_hex_dump

@click.command(name="ui")
@click.argument("filename", type=click.Path(exists=True))
@click.option('--verbose', '-v', is_flag=True, help="Enable verbose output")
@click.pass_context
def ui_command(ctx, filename, verbose):
    """Launch the textual UI for EVIO file inspection."""
    try:
        from pyevio.ui.app import PyEvioApp
    except ImportError:
        print("Error: The textual library is required for the UI.")
        print("Please install it with: pip install textual>=0.30.0")
        return

    app = PyEvioApp(filename)
    app.run()