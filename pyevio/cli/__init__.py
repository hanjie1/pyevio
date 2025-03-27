import os
import click

# Import and register commands
from pyevio.cli.info import info_command
from pyevio.cli.dump import dump_command
from pyevio.cli.debug import debug_command
from pyevio.cli.record import record_command
from pyevio.cli.event import event_command
from pyevio.cli.hex import hex_command
from pyevio.cli.ui import ui_command


@click.group()
@click.version_option(version="0.1.0")
@click.option('--verbose', '-v', is_flag=True, help="Enable verbose output")
@click.pass_context
def cli(ctx, verbose):
    """EVIO v6 file inspection toolkit."""
    # Create a context object to pass data between commands
    ctx.ensure_object(dict)
    ctx.obj['VERBOSE'] = verbose


@cli.command(name="ui")
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

# Register commands with the CLI
cli.add_command(info_command)
cli.add_command(dump_command)
cli.add_command(debug_command)
cli.add_command(record_command)
cli.add_command(event_command)
cli.add_command(hex_command)
cli.add_command(ui_command)


# Entry point for the CLI
def main():
    """Entry point for the CLI when installed via pip."""
    cli(prog_name="pyevio")


if __name__ == "__main__":
    main()
