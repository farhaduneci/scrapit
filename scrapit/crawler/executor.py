"""Subprocess-based crawl executor with isolation."""

import asyncio
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from scrapit.crawler.response_builder import ResponseBuilder
from scrapit.utils.logging_config import set_request_id

logger = logging.getLogger(__name__)


class CrawlExecutor:
    """Executes Scrapy crawls in isolated subprocesses."""

    def __init__(
        self,
        project_path: Optional[str] = None,
        timeout: Optional[float] = None,
        additional_settings: Optional[Dict[str, Any]] = None,
        debug: bool = False,
    ):
        """Initialize crawl executor.

        Args:
            project_path: Path to Scrapy project.
            timeout: Timeout for crawl execution in seconds.
            additional_settings: Additional Scrapy settings to apply.
            debug: Enable debug mode with verbose logging.
        """
        self.project_path = project_path or os.getcwd()
        self.timeout = timeout
        self.additional_settings = additional_settings or {}
        self.debug = debug
        self.response_builder = ResponseBuilder()
        logger.debug(
            f"Initialized CrawlExecutor: project_path={self.project_path}, timeout={self.timeout}, debug={self.debug}"
        )

    async def execute_crawl(
        self,
        spider_name: str,
        start_requests: bool = True,
        crawl_args: Optional[Dict[str, Any]] = None,
        request_obj: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute a crawl in a subprocess.

        Args:
            spider_name: Name of the spider to run.
            start_requests: Whether to use spider's start_requests method.
            crawl_args: Additional arguments to pass to spider.
            request_obj: Custom request object.
            request_id: Unique identifier for this request.

        Returns:
            ScrapyRT-compatible response dictionary.
        """
        if request_id:
            set_request_id(request_id)
        logger.info(
            f"Executing crawl: spider={spider_name}, start_requests={start_requests}"
        )
        logger.debug(f"Crawl args: {crawl_args}, request_obj: {request_obj}")

        # Prepare configuration for subprocess
        config = {
            "spider_name": spider_name,
            "start_requests": start_requests,
            "crawl_args": crawl_args or {},
            "request": request_obj,
            "project_path": self.project_path,
            "additional_settings": self.additional_settings,
            "debug": self.debug,
            "request_id": request_id,
        }

        # Create temporary file for config
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config, f, indent=2)
            config_file = f.name
        logger.debug(f"Created config file: {config_file}")

        try:
            # Get path to scrapy_runner script
            runner_script = Path(__file__).parent.parent / "utils" / "scrapy_runner.py"
            logger.debug(f"Using runner script: {runner_script}")

            # Run subprocess
            logger.debug(
                f"Starting subprocess: {sys.executable} {runner_script} {config_file}"
            )

            # Set up environment with PYTHONPATH to include project directory
            # This ensures local modules can be imported
            env = os.environ.copy()
            project_path_abs = os.path.abspath(self.project_path)
            pythonpath = env.get("PYTHONPATH", "")
            if pythonpath:
                env["PYTHONPATH"] = f"{project_path_abs}{os.pathsep}{pythonpath}"
            else:
                env["PYTHONPATH"] = project_path_abs
            logger.debug(f"PYTHONPATH set to: {env['PYTHONPATH']}")

            process = await asyncio.create_subprocess_exec(
                sys.executable,
                str(runner_script),
                config_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.project_path,
                env=env,
            )
            logger.debug(f"Subprocess started with PID: {process.pid}")

            try:
                # Wait for process with timeout
                logger.debug(f"Waiting for subprocess (timeout: {self.timeout}s)")
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=self.timeout
                )
                logger.debug(
                    f"Subprocess completed with return code: {process.returncode}"
                )
            except asyncio.TimeoutError:
                # Kill process on timeout
                logger.warning(
                    f"Crawl timed out after {self.timeout} seconds, killing process"
                )
                process.kill()
                await process.wait()
                return self.response_builder.build_error_response(
                    f"Crawl timed out after {self.timeout} seconds",
                    request_id=request_id,
                )

            # Decode output
            stdout_text = stdout.decode("utf-8") if stdout else ""
            stderr_text = stderr.decode("utf-8") if stderr else ""

            # Always log output details for debugging
            logger.info(f"Subprocess stdout length: {len(stdout_text)} bytes")
            logger.info(f"Subprocess stderr length: {len(stderr_text)} bytes")

            if stdout_text:
                logger.debug(f"Subprocess stdout: {stdout_text}")

            if stderr_text:
                logger.warning(f"Subprocess stderr: {stderr_text}")

            if process.returncode != 0:
                error_msg = stderr_text or stdout_text or "Unknown error occurred"
                logger.error(
                    f"Subprocess failed with return code {process.returncode}: {error_msg[:500]}"
                )
                return self.response_builder.build_error_response(
                    f"Subprocess failed with return code {process.returncode}: {error_msg}",
                    request_id=request_id,
                )

            # Parse output
            try:
                logger.debug("Parsing subprocess output")
                result = self.response_builder.parse_subprocess_output(stdout_text)
                logger.debug(
                    f"Parsed result: items={len(result.get('items', []))}, stats_keys={len(result.get('stats', {}))}"
                )
            except ValueError as e:
                # If parsing fails, log the actual output for debugging
                logger.error(f"Failed to parse subprocess output: {e}")
                logger.error(
                    f"Raw stdout that failed to parse (first 1000 chars): {stdout_text[:1000]}"
                )
                if len(stdout_text) > 1000:
                    logger.error(f"Raw stdout (last 1000 chars): {stdout_text[-1000:]}")
                error_msg = f"Failed to parse subprocess output: {e}"
                if stderr_text:
                    error_msg += f"\nStderr: {stderr_text[:500]}"
                return self.response_builder.build_error_response(
                    error_msg, request_id=request_id
                )

            # Build response
            status = "error" if result.get("errors") else "ok"
            logger.info(
                f"Crawl execution completed: status={status}, items={len(result.get('items', []))}"
            )
            if result.get("errors"):
                logger.warning(f"Crawl errors: {result.get('errors')}")

            response = self.response_builder.build_response(
                items=result.get("items", []),
                stats=result.get("stats", {}),
                errors=result.get("errors"),
                status=status,
                request_id=request_id,
            )

            if self.debug:
                logger.debug(
                    f"Response built: status={response.get('status')}, items_count={len(response.get('items', []))}"
                )
                if response.get("stats"):
                    logger.debug(f"Response stats: {response.get('stats')}")

            return response

        except Exception as e:
            logger.error(f"Executor error: {e}", exc_info=True)
            return self.response_builder.build_error_response(
                f"Executor error: {str(e)}",
                request_id=request_id,
            )
        finally:
            # Clean up config file
            try:
                os.unlink(config_file)
                logger.debug(f"Cleaned up config file: {config_file}")
            except OSError as e:
                logger.warning(f"Failed to clean up config file {config_file}: {e}")
