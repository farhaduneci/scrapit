"""API endpoints for ScrapyRT-compatible crawl requests."""

import json
import logging
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from scrapit.api.models import CrawlResponse
from scrapit.crawler.executor import CrawlExecutor
from scrapit.crawler.spider_loader import SpiderLoader
from scrapit.utils.logging_config import set_request_id

logger = logging.getLogger(__name__)


def create_router(
    project_path: Optional[str] = None,
    timeout: Optional[float] = None,
    additional_settings: Optional[Dict[str, Any]] = None,
    debug: bool = False,
) -> APIRouter:
    """Create API router with crawl endpoint.

    Args:
        project_path: Path to Scrapy project.
        timeout: Default timeout for crawls.
        additional_settings: Additional Scrapy settings.
        debug: Enable debug mode with verbose logging.

    Returns:
        Configured APIRouter instance.
    """
    router = APIRouter()
    executor = CrawlExecutor(
        project_path=project_path,
        timeout=timeout,
        additional_settings=additional_settings,
        debug=debug,
    )
    spider_loader = SpiderLoader(project_path=project_path)

    @router.post("/crawl.json", response_model=CrawlResponse)
    async def crawl(
        request: Request,
        spider_name: Optional[str] = Query(None, description="Spider name"),
        url: Optional[str] = Query(None, description="URL to crawl (deprecated)"),
        start_requests: Optional[bool] = Query(
            None, description="Use start_requests method"
        ),
        crawl_args: Optional[str] = Query(
            None, description="Crawl args as JSON string"
        ),
    ) -> JSONResponse:
        """ScrapyRT-compatible crawl endpoint.

        Accepts parameters via both query parameters and JSON body.
        Body parameters take precedence over query parameters.
        """
        request_id = str(uuid.uuid4())[:8]
        set_request_id(request_id)
        logger.info("Received crawl request")
        logger.debug(
            f"Query parameters: spider_name={spider_name}, url={url}, start_requests={start_requests}, crawl_args={crawl_args}"
        )

        # Parse query parameters
        query_params: Dict[str, Any] = {}
        if spider_name:
            query_params["spider_name"] = spider_name
        if url:
            query_params["url"] = url
        if start_requests is not None:
            query_params["start_requests"] = start_requests
        if crawl_args:
            try:
                query_params["crawl_args"] = json.loads(crawl_args)
            except json.JSONDecodeError:
                return JSONResponse(
                    status_code=400,
                    content={
                        "status": "error",
                        "items": [],
                        "stats": {},
                        "request_id": request_id,
                        "errors": ["Invalid JSON in crawl_args query parameter"],
                    },
                )

        # Parse body if present
        body_params: Dict[str, Any] = {}
        try:
            body_content = await request.body()
            if body_content:
                body_params = json.loads(body_content)
                logger.debug(f"Parsed body parameters: {body_params}")
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse body as JSON: {e}")
            pass  # Body is optional

        # Merge parameters: body takes precedence over query
        merged_params = {**query_params, **body_params}
        logger.debug(f"Merged parameters: {merged_params}")

        # Validate spider_name is present
        if "spider_name" not in merged_params:
            logger.warning("Request rejected: spider_name is required")
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "request_id": request_id,
                    "items": [],
                    "stats": {},
                    "errors": ["spider_name is required"],
                },
            )

        # Validate spider exists
        spider_name_value = merged_params["spider_name"]
        logger.debug(f"Validating spider: {spider_name_value}")
        if not spider_loader.validate_spider(spider_name_value):
            available = ", ".join(sorted(spider_loader.list_spiders()))
            logger.warning(
                f"Spider not found: {spider_name_value}. Available: {available}"
            )
            return JSONResponse(
                status_code=404,
                content={
                    "status": "error",
                    "request_id": request_id,
                    "items": [],
                    "stats": {},
                    "errors": [
                        f"Spider '{spider_name_value}' not found. Available spiders: {available}"
                    ],
                },
            )

        # Extract parameters
        start_requests_value = merged_params.get("start_requests", True)
        crawl_args_value = merged_params.get("crawl_args", {})
        request_obj = merged_params.get("request")

        # Handle deprecated url parameter
        if "url" in merged_params and not request_obj:
            # Convert url to request object
            request_obj = {"url": merged_params["url"]}
            logger.debug(
                f"Converted deprecated url parameter to request object: {request_obj}"
            )

        logger.info(f"Starting crawl for spider: {spider_name_value}")
        logger.debug(
            f"Crawl parameters: start_requests={start_requests_value}, crawl_args={crawl_args_value}, request_obj={request_obj}"
        )

        # Execute crawl
        try:
            response = await executor.execute_crawl(
                spider_name=spider_name_value,
                start_requests=start_requests_value,
                crawl_args=crawl_args_value if crawl_args_value else None,
                request_obj=request_obj,
                request_id=request_id,
            )
            logger.info(
                f"Crawl completed for spider: {spider_name_value}, status: {response.get('status')}"
            )
            logger.debug(
                f"Response stats: {response.get('stats')}, items count: {len(response.get('items', []))}"
            )
            if response.get("errors"):
                logger.warning(f"Crawl completed with errors: {response.get('errors')}")
            return JSONResponse(content=response)
        except Exception as e:
            logger.error(f"Exception during crawl execution: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "request_id": request_id,
                    "items": [],
                    "stats": {},
                    "errors": [f"Internal error: {str(e)}"],
                },
            )

    return router
