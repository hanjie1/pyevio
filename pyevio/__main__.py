"""
__main__.py -- entry point when running `python -m pyevio`.
It delegates to our CLI's main() function.
"""

from .cli import main

if __name__ == "__main__":
    main(prog_name="pyevio")