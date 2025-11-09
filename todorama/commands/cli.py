"""
CLI command - Run the command-line interface tool.

This wraps the existing click-based CLI.
"""
import sys
import argparse
import logging
from todorama.__main__ import Command

logger = logging.getLogger(__name__)


class CLICommand(Command):
    """Command to run the Todorama CLI tool."""
    
    @classmethod
    def add_arguments(cls, parser):
        """Add CLI-specific arguments."""
        # The CLI uses click internally, so we just pass through remaining args
        parser.add_argument(
            "cli_args",
            nargs=argparse.REMAINDER,
            help="Arguments to pass to the CLI tool"
        )
    
    def init(self):
        """Initialize the CLI command."""
        super().init()
        # Import here to avoid circular dependencies
        # We'll import the click CLI module
        logger.debug("CLI command initialized")
    
    def run(self) -> int:
        """Run the CLI tool."""
        # Import the click CLI
        from todorama.cli import cli
        
        # Get remaining args (everything after 'cli')
        # The args.cli_args should contain the click command and its args
        if hasattr(self.args, 'cli_args'):
            click_args = self.args.cli_args
        else:
            click_args = []
        
        # Call click CLI with the remaining args
        # Click expects sys.argv format, so we need to reconstruct it
        original_argv = sys.argv[:]
        try:
            # Reconstruct argv: ['todorama', 'cli', ...click_args]
            sys.argv = ['todorama', 'cli'] + click_args
            cli()
            return 0
        except SystemExit as e:
            # Click uses SystemExit for exit codes
            return e.code if e.code is not None else 0
        except Exception as e:
            logger.exception(f"CLI error: {e}")
            return 1
        finally:
            sys.argv = original_argv
    
    def cleanup(self):
        """Clean up CLI resources."""
        super().cleanup()
        logger.debug("CLI command cleaned up")

