"""
Server command - Run the web server.
"""
import os
import logging
import uvicorn
from todorama.__main__ import Command

logger = logging.getLogger(__name__)


class ServerCommand(Command):
    """Command to run the Todorama web server."""
    
    @classmethod
    def add_arguments(cls, parser):
        """Add server-specific arguments."""
        parser.add_argument(
            "--host",
            default="0.0.0.0",
            help="Host to bind to (default: 0.0.0.0)"
        )
        parser.add_argument(
            "--port",
            type=int,
            default=int(os.getenv("TODO_SERVICE_PORT", "8004")),
            help="Port to bind to (default: 8004 or TODO_SERVICE_PORT env var)"
        )
        parser.add_argument(
            "--log-level",
            default=os.getenv("LOG_LEVEL", "INFO").lower(),
            choices=["debug", "info", "warning", "error", "critical"],
            help="Log level (default: INFO or LOG_LEVEL env var)"
        )
        parser.add_argument(
            "--reload",
            action="store_true",
            help="Enable auto-reload (development mode)"
        )
        parser.add_argument(
            "--init-only",
            action="store_true",
            help="Initialize database and run migrations, then exit (does not start server)"
        )
    
    def init(self):
        """Initialize the server command."""
        super().init()
        
        # Import here to avoid circular dependencies
        from todorama.app import create_app
        
        self.app = create_app()
        logger.info(f"Server initialized on {self.args.host}:{self.args.port}")
    
    def run(self) -> int:
        """Run the web server or initialize database if --init-only is set."""
        # If --init-only, run initialization and exit
        if self.args.init_only:
            from todorama.commands.initialize import InitializeCommand
            from argparse import Namespace
            
            init_args = Namespace(
                database_path=None,
                skip_migrations=False,
                validate_only=False
            )
            
            init_cmd = InitializeCommand(init_args)
            try:
                init_cmd.init()
                result = init_cmd.run()
                if result == 0:
                    logger.info("✅ Database initialization complete")
                return result
            finally:
                init_cmd.cleanup()
        
        # Normal server startup
        config = uvicorn.Config(
            self.app,
            host=self.args.host,
            port=self.args.port,
            log_level=self.args.log_level,
            access_log=True,
            reload=self.args.reload,
            # Graceful shutdown settings
            timeout_keep_alive=30,
            timeout_graceful_shutdown=30,
        )
        
        server = uvicorn.Server(config)
        
        try:
            logger.info(f"Starting server on {self.args.host}:{self.args.port}")
            server.run()
            return 0
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, shutting down...")
            return 130
        except Exception as e:
            logger.exception(f"Server error: {e}")
            return 1
    
    def cleanup(self):
        """Clean up server resources."""
        super().cleanup()
        # Cleanup is handled by lifespan context manager in app/factory.py
        logger.info("Server stopped")

