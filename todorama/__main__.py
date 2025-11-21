#!/usr/bin/env python3
"""
Todorama - Main entry point

This module provides the Command base class and manages the command lifecycle.
All top-level scripts should be converted to Command subclasses.
"""
import argparse
import sys
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class Command(ABC):
    """
    Base class for all commands.
    
    Commands follow a lifecycle:
    1. init() - Initialize resources, parse arguments
    2. run() - Execute the command
    3. cleanup() - Clean up resources
    
    Commands can declare arguments using add_arguments().
    """
    
    def __init__(self, args: Optional[argparse.Namespace] = None):
        """
        Initialize command with parsed arguments.
        
        Args:
            args: Parsed command-line arguments (None if not yet parsed)
        """
        self.args = args
        self._initialized = False
        self._cleaned_up = False
    
    @classmethod
    def get_name(cls) -> str:
        """Get the command name (used in CLI)."""
        # Convert class name like "ServerCommand" to "server"
        name = cls.__name__.replace("Command", "").lower()
        return name
    
    @classmethod
    def get_description(cls) -> str:
        """Get command description for help text."""
        return cls.__doc__ or f"{cls.__name__} command"
    
    @classmethod
    def add_arguments(cls, parser: argparse.ArgumentParser) -> None:
        """
        Add command-specific arguments to the parser.
        
        Override this method in subclasses to add arguments.
        
        Args:
            parser: ArgumentParser instance for this command
        """
        pass
    
    def init(self) -> None:
        """
        Initialize the command.
        
        Called before run(). Override to set up resources, validate arguments, etc.
        """
        if self._initialized:
            return
        
        self._initialized = True
        logger.debug(f"Initialized {self.__class__.__name__}")
    
    @abstractmethod
    def run(self) -> int:
        """
        Execute the command.
        
        Returns:
            Exit code (0 for success, non-zero for failure)
        """
        pass
    
    def cleanup(self) -> None:
        """
        Clean up resources.
        
        Called after run() (even if run() raises an exception).
        Override to close connections, clean up files, etc.
        """
        if self._cleaned_up:
            return
        
        self._cleaned_up = True
        logger.debug(f"Cleaned up {self.__class__.__name__}")
    
    def __enter__(self):
        """Context manager entry."""
        self.init()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.cleanup()
        return False  # Don't suppress exceptions


# Import all commands here so they're registered
# Commands will be imported lazily to avoid circular dependencies
_COMMANDS: Dict[str, type] = {}


def register_command(command_class: type) -> None:
    """Register a command class."""
    name = command_class.get_name()
    _COMMANDS[name] = command_class


def get_command(name: str) -> Optional[type]:
    """Get a registered command class by name."""
    return _COMMANDS.get(name)


def list_commands() -> Dict[str, type]:
    """List all registered commands."""
    return _COMMANDS.copy()


def main():
    """Main entry point for the todorama package."""
    parser = argparse.ArgumentParser(
        description="Todorama - TODO Service for AI Agents",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(
        dest="command",
        help="Command to run",
        metavar="COMMAND"
    )
    
    # Import commands here to register them
    # This avoids circular imports
    try:
        from todorama.commands.server import ServerCommand
        register_command(ServerCommand)
    except ImportError as e:
        logger.warning(f"ServerCommand could not be imported: {e}")
    
    try:
        from todorama.commands.cli import CLICommand
        register_command(CLICommand)
    except ImportError as e:
        logger.warning(f"CLICommand could not be imported: {e}")
    
    try:
        from todorama.commands.migrate import MigrateCommand
        register_command(MigrateCommand)
    except ImportError as e:
        logger.warning(f"MigrateCommand could not be imported: {e}")
    
    try:
        from todorama.commands.keys import KeyManagementCommand
        register_command(KeyManagementCommand)
    except ImportError as e:
        logger.warning(f"KeyManagementCommand could not be imported: {e}")
    
    try:
        from todorama.commands.analyze import AnalyzeCommand
        register_command(AnalyzeCommand)
    except ImportError as e:
        logger.warning(f"AnalyzeCommand could not be imported: {e}")
    
    try:
        from todorama.commands.audit import AuditCommand
        register_command(AuditCommand)
    except ImportError as e:
        logger.warning(f"AuditCommand could not be imported: {e}")
    
    try:
        from todorama.commands.verify import VerifyCommand
        register_command(VerifyCommand)
    except ImportError as e:
        logger.warning(f"VerifyCommand could not be imported: {e}")
    
    try:
        from todorama.commands.initialize import InitializeCommand
        register_command(InitializeCommand)
    except ImportError as e:
        logger.warning(f"InitializeCommand could not be imported: {e}")
    
    # Create subparsers for each command
    for name, cmd_class in _COMMANDS.items():
        subparser = subparsers.add_parser(
            name,
            help=cmd_class.get_description(),
            description=cmd_class.get_description()
        )
        cmd_class.add_arguments(subparser)
    
    # Parse arguments
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Get command class
    cmd_class = get_command(args.command)
    if not cmd_class:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 1
    
    # Create and run command
    try:
        cmd = cmd_class(args)
        with cmd:
            exit_code = cmd.run()
            return exit_code
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 130
    except Exception as e:
        logger.exception(f"Command failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

