"""
__main__.py -- entry point when running `python -m pyevio`.
It delegates to our CLI's main() function.
"""

from .cli import cli as cli_app

if __name__ == "__main__":
    cli_app(prog_name="pyevio")