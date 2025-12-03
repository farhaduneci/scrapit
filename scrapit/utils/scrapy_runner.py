"""Standalone Scrapy runner for subprocess execution."""

import json
import logging
import os
import sys
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from scrapy import Request, signals
from scrapy.crawler import CrawlerProcess
from scrapy.utils.log import configure_logging
from scrapy.utils.project import get_project_settings

from scrapit.utils.logging_config import set_request_id, setup_logging_with_request_id

# Create logger for this module
logger = logging.getLogger(__name__)


class JSONEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime and other non-serializable objects."""

    def default(self, obj):
        """Convert non-serializable objects to serializable format."""
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        # Handle other common non-serializable types
        try:
            return super().default(obj)
        except TypeError:
            # Fallback: convert to string
            return str(obj)


def json_serialize(obj: Any) -> Any:
    """Recursively serialize an object, converting datetime objects to strings.

    Args:
        obj: Object to serialize.

    Returns:
        Serializable version of the object.
    """
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {key: json_serialize(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [json_serialize(item) for item in obj]
    elif hasattr(obj, "__dict__"):
        # Handle objects with __dict__ attribute
        return json_serialize(obj.__dict__)
    else:
        return obj


class ItemCollectorPipeline:
    """Pipeline to collect all scraped items."""

    def __init__(self):
        """Initialize the item collector."""
        self.items: List[Dict[str, Any]] = []

    def process_item(self, item, spider):
        """Process and collect an item.

        Args:
            item: Scraped item.
            spider: Spider instance.

        Returns:
            The item.
        """
        # Convert item to dict if it's an Item object
        if hasattr(item, "asdict"):
            self.items.append(item.asdict())
        elif isinstance(item, dict):
            self.items.append(item)
        else:
            # Fallback: convert to dict
            self.items.append(dict(item))
        return item


def run_spider(
    spider_name: str,
    start_requests: bool = True,
    crawl_args: Optional[Dict[str, Any]] = None,
    request_obj: Optional[Dict[str, Any]] = None,
    project_path: Optional[str] = None,
    additional_settings: Optional[Dict[str, Any]] = None,
    debug: bool = False,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Run a Scrapy spider and collect results.

    Args:
        spider_name: Name of the spider to run.
        start_requests: Whether to use spider's start_requests method.
        crawl_args: Additional arguments to pass to spider.
        request_obj: Custom request object (url, callback, meta, etc.).
        project_path: Path to Scrapy project (defaults to CWD).
        additional_settings: Additional Scrapy settings.
        debug: Enable debug mode with verbose logging.
        request_id: Unique identifier for this request.

    Returns:
        Dictionary with items, stats, and errors.
    """
    # Set request ID in context
    if request_id:
        set_request_id(request_id)

    # Setup logging with request ID support
    setup_logging_with_request_id(debug=debug)

    # Configure Scrapy logging (it may override our handlers, so we need to reapply)
    log_level = logging.DEBUG if debug else logging.INFO
    configure_logging(install_root_handler=False, settings={"LOG_LEVEL": log_level})

    # Reapply our logging configuration after Scrapy's configure_logging
    setup_logging_with_request_id(debug=debug)

    # Set logger level
    logger.setLevel(log_level)

    logger.info(f"Starting spider execution: {spider_name}")
    logger.debug(
        f"Parameters: start_requests={start_requests}, crawl_args={crawl_args}, request_obj={request_obj}"
    )

    # Change to project directory if specified
    original_cwd = os.getcwd()
    if project_path:
        project_path_abs = os.path.abspath(project_path)
        logger.debug(f"Changing to project directory: {project_path_abs}")
        os.chdir(project_path_abs)
        # Add project directory to Python path so local modules can be imported
        if project_path_abs not in sys.path:
            sys.path.insert(0, project_path_abs)
            logger.debug(f"Added {project_path_abs} to sys.path")

    try:
        # Get project settings
        logger.debug("Loading Scrapy project settings")
        settings = get_project_settings()

        # Apply additional settings
        if additional_settings:
            logger.debug(f"Applying additional settings: {additional_settings}")
            settings.update(additional_settings)

        # Add item collector pipeline
        settings.set(
            "ITEM_PIPELINES", {"scrapit.utils.scrapy_runner.ItemCollectorPipeline": 300}
        )
        logger.debug("Item collector pipeline configured")

        # Create crawler process
        logger.debug("Creating CrawlerProcess")
        process = CrawlerProcess(settings)

        # Store items and stats
        collected_items: List[Dict[str, Any]] = []
        crawl_stats: Dict[str, Any] = {}
        errors: List[str] = []

        def item_scraped(item, response, spider):
            """Callback when item is scraped."""
            if hasattr(item, "asdict"):
                collected_items.append(item.asdict())
            elif isinstance(item, dict):
                collected_items.append(item)
            else:
                collected_items.append(dict(item))
            if debug:
                logger.debug(
                    f"Item scraped: {len(collected_items)} items collected so far"
                )

        def spider_closed(spider, reason):
            """Callback when spider closes."""
            nonlocal crawl_stats
            crawl_stats = dict(spider.crawler.stats.get_stats())
            logger.info(
                f"Spider closed: reason={reason}, items={len(collected_items)}, stats_keys={len(crawl_stats)}"
            )
            if debug:
                logger.debug(f"Spider stats: {crawl_stats}")

        # Get the spider class
        logger.debug(f"Loading spider class: {spider_name}")
        spider_loader = process.spider_loader
        original_spider_class = spider_loader.load(spider_name)
        logger.debug(f"Spider class loaded: {original_spider_class}")

        # Create a wrapper spider class if we need custom request handling
        # or if start_requests should be disabled
        if request_obj or not start_requests:
            logger.debug("Creating wrapper spider class for custom request handling")
            # Capture variables for closure
            captured_request_obj = request_obj
            captured_start_requests = start_requests

            # Create wrapper class dynamically
            class WrappedSpider(original_spider_class):
                """Wrapper spider for custom request handling."""

                def start_requests(self):
                    """Override start_requests based on parameters."""
                    # If we have a custom request object, use it
                    if captured_request_obj:
                        req_url = captured_request_obj.get("url")
                        if not req_url:
                            return

                        # Get callback method
                        callback_name = captured_request_obj.get("callback")
                        if callback_name:
                            callback_method = getattr(self, callback_name, self.parse)
                        else:
                            callback_method = getattr(self, "parse", None)

                        # Get errback if specified
                        errback_method = None
                        if captured_request_obj.get("errback"):
                            errback_method = getattr(
                                self, captured_request_obj.get("errback"), None
                            )

                        # Create Scrapy Request
                        scrapy_request = Request(
                            url=req_url,
                            callback=callback_method,
                            errback=errback_method,
                            meta=captured_request_obj.get("meta", {}),
                            headers=captured_request_obj.get("headers"),
                            cookies=captured_request_obj.get("cookies"),
                            body=captured_request_obj.get("body"),
                            method=captured_request_obj.get("method", "GET"),
                        )
                        yield scrapy_request
                    # If start_requests is False and no request_obj, don't yield anything
                    elif not captured_start_requests:
                        return
                    # Otherwise, use parent's start_requests
                    else:
                        yield from super().start_requests()

            spider_class = WrappedSpider
            logger.debug("Using wrapped spider class")
        else:
            spider_class = original_spider_class
            logger.debug("Using original spider class")

        # Start crawling
        logger.info(f"Starting crawl for spider: {spider_name}")
        logger.debug(f"Crawl args: {crawl_args}")
        process.crawl(
            spider_class,
            **crawl_args or {},
        )

        # Connect signals to the crawler
        # After crawl() is called, the crawler is available in process.crawlers
        def connect_signals_to_crawler(crawler):
            """Connect signals to a crawler."""
            crawler.signals.connect(item_scraped, signal=signals.item_scraped)
            crawler.signals.connect(spider_closed, signal=signals.spider_closed)

        # Connect signals to all crawlers (usually just one)
        for crawler in process.crawlers:
            connect_signals_to_crawler(crawler)

        # Run the crawler
        try:
            logger.debug("Starting CrawlerProcess")
            process.start()
            logger.debug("CrawlerProcess completed")
        except Exception as e:
            logger.error(f"Error during crawl execution: {e}", exc_info=debug)
            errors.append(str(e))
            # Try to get partial stats from any crawler
            if process.crawlers:
                crawl_stats = dict(process.crawlers[0].stats.get_stats())
                logger.debug(f"Collected partial stats: {len(crawl_stats)} keys")

        logger.info(
            f"Execution completed: items={len(collected_items)}, errors={len(errors)}"
        )

        if debug:
            logger.debug(f"Final stats: {crawl_stats}")
            if errors:
                logger.debug(f"Errors: {errors}")

        # Serialize datetime objects in stats and items before returning
        serialized_items = json_serialize(collected_items)
        serialized_stats = json_serialize(crawl_stats)

        return {
            "items": serialized_items,
            "stats": serialized_stats,
            "errors": errors if errors else None,
        }
    except Exception as e:
        logger.error(f"Fatal error in run_spider: {e}", exc_info=debug)
        return {
            "items": [],
            "stats": {},
            "errors": [str(e)],
        }
    finally:
        os.chdir(original_cwd)
        logger.debug(f"Restored working directory: {original_cwd}")


def main():
    """Main entry point for subprocess execution."""
    # Read input from stdin or command line args
    if len(sys.argv) > 1:
        # Read from command line argument (JSON file path)
        with open(sys.argv[1], "r") as f:
            config = json.load(f)
    else:
        # Read from stdin
        config = json.load(sys.stdin)

    # Extract parameters
    spider_name = config["spider_name"]
    start_requests = config.get("start_requests", True)
    crawl_args = config.get("crawl_args", {})
    request_obj = config.get("request")
    project_path = config.get("project_path")
    additional_settings = config.get("additional_settings")
    debug = config.get("debug", False)
    request_id = config.get("request_id")

    # Run spider
    result = run_spider(
        spider_name=spider_name,
        start_requests=start_requests,
        crawl_args=crawl_args,
        request_obj=request_obj,
        project_path=project_path,
        additional_settings=additional_settings,
        debug=debug,
        request_id=request_id,
    )

    # Output result as JSON with custom encoder for datetime objects
    print(json.dumps(result, indent=2, cls=JSONEncoder, default=str))
    sys.exit(0 if not result.get("errors") else 1)


if __name__ == "__main__":
    main()
