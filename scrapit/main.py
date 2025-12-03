"""FastAPI application and CLI entrypoint for ScrapyRT-compatible API."""

import logging
import os
from typing import Any, Dict, Optional

import typer
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from scrapit.api.endpoints import create_router
from scrapit.utils.logging_config import setup_logging_with_request_id

logger = logging.getLogger(__name__)

# Create Typer app for CLI
cli = typer.Typer()


def create_app(
    project_path: Optional[str] = None,
    timeout: Optional[float] = None,
    additional_settings: Optional[Dict[str, Any]] = None,
    debug: bool = False,
) -> FastAPI:
    """Create and configure FastAPI application.

    Args:
        project_path: Path to Scrapy project.
        timeout: Default timeout for crawls.
        additional_settings: Additional Scrapy settings.
        debug: Enable debug mode with verbose logging.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(
        title="ScrapyRT-Compatible API",
        description="FastAPI wrapper for Scrapy spiders with ScrapyRT compatibility",
        version="1.0.3",
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allow all origins for internal testing
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Create and include router
    router = create_router(
        project_path=project_path,
        timeout=timeout,
        additional_settings=additional_settings,
        debug=debug,
    )
    app.include_router(router)

    return app


@cli.command()
def run(
    port: int = typer.Option(9080, "--port", "-p", help="Port number to bind to"),
    host: str = typer.Option("0.0.0.0", "--host", "-i", help="Host address to bind to"),
    project: Optional[str] = typer.Option(
        None, "--project", "-P", help="Path to Scrapy project (defaults to CWD)"
    ),
    settings: Optional[str] = typer.Option(
        None,
        "--settings",
        "-s",
        help="Scrapy settings in KEY=VALUE format (can be used multiple times)",
    ),
    timeout: Optional[float] = typer.Option(
        None, "--timeout", "-t", help="Default timeout for crawls in seconds"
    ),
    debug: bool = typer.Option(
        False, "--debug", "-d", help="Enable debug mode with verbose logging"
    ),
):
    """Run the ScrapyRT-compatible API server.

    Example:
        scrapit -p 9080 -i 0.0.0.0 -s TIMEOUT_LIMIT=120
        scrapit -p 9080 --debug  # Enable debug logging
    """
    # Setup logging based on debug mode
    setup_logging_with_request_id(debug=debug)
    # Parse additional settings
    additional_settings: Dict[str, Any] = {}
    if settings:
        # Support multiple -s flags or comma-separated values
        settings_list = settings.split(",") if "," in settings else [settings]
        for setting in settings_list:
            if "=" in setting:
                key, value = setting.split("=", 1)
                # Try to convert value to appropriate type
                if value.lower() in ("true", "false"):
                    additional_settings[key.strip()] = value.lower() == "true"
                elif value.isdigit():
                    additional_settings[key.strip()] = int(value)
                else:
                    try:
                        additional_settings[key.strip()] = float(value)
                    except ValueError:
                        additional_settings[key.strip()] = value
            else:
                logger.warning(f"Ignoring invalid setting format: {setting}")

    # Determine project path
    project_path = project or os.getcwd()
    if not os.path.isdir(project_path):
        logger.error(f"Project path does not exist: {project_path}")
        raise typer.Exit(code=1)

    logger.info("Starting ScrapyRT-compatible API server")
    logger.info(f"Host: {host}, Port: {port}")
    logger.info(f"Project path: {project_path}")
    logger.info(f"Debug mode: {debug}")
    if additional_settings:
        logger.info(f"Additional settings: {additional_settings}")
    if timeout:
        logger.info(f"Default timeout: {timeout} seconds")

    # Create app
    app = create_app(
        project_path=project_path,
        timeout=timeout,
        additional_settings=additional_settings,
        debug=debug,
    )

    # Run server
    log_level = "debug" if debug else "info"
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=log_level,
    )


def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
