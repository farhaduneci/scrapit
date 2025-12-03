"""Pydantic models for ScrapyRT-compatible request/response schemas."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RequestObject(BaseModel):
    """Nested request object for custom initial requests."""

    url: str = Field(..., description="URL for the initial request")
    callback: Optional[str] = Field(None, description="Callback method name")
    meta: Optional[Dict[str, Any]] = Field(None, description="Request metadata")
    headers: Optional[Dict[str, str]] = Field(None, description="Custom headers")
    cookies: Optional[Dict[str, str]] = Field(None, description="Cookies")
    body: Optional[str] = Field(None, description="Request body (for POST requests)")
    method: Optional[str] = Field("GET", description="HTTP method (default: GET)")


class CrawlRequest(BaseModel):
    """ScrapyRT-compatible crawl request model.

    Supports both query parameters and JSON body.
    When both are provided, body parameters take precedence.
    """

    spider_name: str = Field(..., description="Name of the spider to execute")
    url: Optional[str] = Field(
        None, description="URL to crawl (deprecated, use request.url)"
    )
    start_requests: bool = Field(
        True, description="Whether to use spider's start_requests method"
    )
    crawl_args: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Additional arguments to pass to the spider"
    )
    request: Optional[RequestObject] = Field(
        None, description="Custom initial request object"
    )

    class Config:
        """Pydantic config."""

        extra = "allow"  # Allow extra fields for compatibility


class CrawlResponse(BaseModel):
    """ScrapyRT-compatible crawl response model."""

    status: str = Field(..., description="Status of the crawl: 'ok' or 'error'")
    request_id: str = Field(..., description="Unique identifier for this request")
    items: List[Dict[str, Any]] = Field(
        default_factory=list, description="Scraped items"
    )
    stats: Dict[str, Any] = Field(default_factory=dict, description="Crawl statistics")
    errors: Optional[List[str]] = Field(None, description="List of error messages")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "status": "ok",
                "request_id": "123e4567-e89b-12d3-a456-426614174000",
                "items": [{"title": "Example", "url": "http://example.com"}],
                "stats": {"downloader/request_count": 1, "item_scraped_count": 1},
            }
        }
