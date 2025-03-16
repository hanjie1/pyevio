import os
import click

# Import and register commands
from pyevio.cli.info import info_command
from pyevio.cli.dump import dump_command
from pyevio.cli.debug import debug_command
from pyevio.cli.record import record_command
from pyevio.cli.event import event_command


@click.group()
@click.version_option(version="0.1.0")
@click.option('--verbose', '-v', is_flag=True, help="Enable verbose output")
@click.pass_context
def cli(ctx, verbose):
    """EVIO v6 file inspection toolkit."""
    # Create a context object to pass data between commands
    ctx.ensure_object(dict)
    ctx.obj['VERBOSE'] = verbose


# Register commands with the CLI
cli.add_command(info_command)
cli.add_command(dump_command)
cli.add_command(debug_command)
cli.add_command(record_command)
cli.add_command(event_command)


# Entry point for the CLI
def main():
    """Entry point for the CLI when installed via pip."""
    cli(prog_name="pyevio")


if __name__ == "__main__":
    main()
