# ScrapyRT-Compatible FastAPI Wrapper

A minimal, fully ScrapyRT-compatible POST API for triggering Scrapy spiders. This FastAPI wrapper provides 100% behavioral parity with ScrapyRT's request and response schemas, designed for internal testing with support for concurrent spider executions.

## Features

- **100% ScrapyRT Compatibility**: Exact match of ScrapyRT's POST API schema and behavior
- **Concurrent Execution**: Support for multiple simultaneous spider executions without interference
- **Subprocess Isolation**: Each crawl runs in an isolated subprocess to avoid Twisted reactor conflicts
- **Flexible Input**: Accepts parameters via both query parameters and JSON body
- **Modern CLI**: Clean command-line interface using Typer
- **Debug Mode**: Comprehensive logging at all stages for easy debugging and spider testing

## Installation

```bash
# Using pip
pip install -e .

# Using uv (recommended)
# First create a virtual environment
uv venv

# Then install the package
uv pip install -e .

# Or use uv sync (which handles venv automatically)
uv sync
```

## Usage

### Starting the Server

```bash
# Basic usage
scrapit -p 9080 -i 0.0.0.0

# With Scrapy project path
scrapit -p 9080 -i 0.0.0.0 -P /path/to/scrapy/project

# With additional Scrapy settings
scrapit -p 9080 -i 0.0.0.0 -s TIMEOUT_LIMIT=120 -s CONCURRENT_REQUESTS=16

# With timeout
scrapit -p 9080 -i 0.0.0.0 -t 300

# With debug mode (verbose logging for testing)
scrapit -p 9080 -i 0.0.0.0 --debug

# Exclude logs from responses (smaller response size)
scrapit -p 9080 -i 0.0.0.0 --no-logs
```

### CLI Options

- `-p, --port`: Port number to bind to (default: 9080)
- `-i, --host`: Host address to bind to (default: 0.0.0.0)
- `-P, --project`: Path to Scrapy project (defaults to current working directory)
- `-s, --settings`: Scrapy settings in KEY=VALUE format (can be used multiple times)
- `-t, --timeout`: Default timeout for crawls in seconds
- `-d, --debug`: Enable debug mode with verbose logging (useful for testing spiders)
- `--include-logs/--no-logs`: Include or exclude logs in API responses (default: include logs)

### API Endpoint

#### POST `/crawl.json`

Triggers a Scrapy spider crawl. Accepts parameters via both query parameters and JSON body. Body parameters take precedence over query parameters.

**Request Parameters:**

- `spider_name` (required): Name of the spider to execute
- `url` (optional, deprecated): URL to crawl (use `request.url` instead)
- `start_requests` (optional, default: `true`): Whether to use spider's `start_requests` method
- `crawl_args` (optional): Dictionary of additional arguments to pass to the spider
- `request` (optional): Custom request object with:
  - `url` (required): URL for the initial request
  - `callback` (optional): Callback method name
  - `meta` (optional): Request metadata dictionary
  - `headers` (optional): Custom headers dictionary
  - `cookies` (optional): Cookies dictionary
  - `body` (optional): Request body (for POST requests)
  - `method` (optional, default: "GET"): HTTP method

**Response Format:**

```json
{
  "status": "ok",
  "items": [
    {"field1": "value1", "field2": "value2"}
  ],
  "stats": {
    "downloader/request_count": 1,
    "item_scraped_count": 1
  },
  "errors": null,
  "logs": null
}
```

**Example Requests:**

```bash
# Using JSON body
curl -X POST http://localhost:9080/crawl.json \
  -H "Content-Type: application/json" \
  -d '{
    "spider_name": "example_spider",
    "start_requests": true,
    "crawl_args": {"arg1": "value1"}
  }'

# Using query parameters
curl -X POST "http://localhost:9080/crawl.json?spider_name=example_spider&start_requests=true"

# Using custom request object
curl -X POST http://localhost:9080/crawl.json \
  -H "Content-Type: application/json" \
  -d '{
    "spider_name": "example_spider",
    "request": {
      "url": "https://example.com",
      "callback": "parse",
      "method": "GET"
    }
  }'
```

## Compatibility with ScrapyRT

This implementation maintains 100% compatibility with ScrapyRT v0.12:

- **Request Schema**: All ScrapyRT request fields are supported with identical behavior
- **Response Schema**: Responses match ScrapyRT's format exactly, including field names and structure
- **Parameter Handling**: Query parameters and JSON body are merged with the same prioritization rules as ScrapyRT
- **Error Handling**: Error responses follow ScrapyRT's format
- **Spider Execution**: Spiders are executed with the same parameter passing and request handling as ScrapyRT

## Architecture

- **API Layer** (`scrapit/api/`): FastAPI endpoints and request/response models
- **Crawler Orchestration** (`scrapit/crawler/`): Spider discovery, execution, and response building
- **Subprocess Worker** (`scrapit/utils/scrapy_runner.py`): Standalone script that runs spiders in isolated processes
- **CLI** (`scrapit/main.py`): Command-line interface for starting the server

## Requirements

- Python 3.9+
- Scrapy 2.8.0+
- FastAPI
- Uvicorn

## Using in Another Local Project

To use this package in another local project, you have several options:

### Option 1: Path Dependency (Recommended for Development)

Add it as a local dependency in your other project's `pyproject.toml`:

**Using absolute path:**
```toml
[project]
dependencies = [
    "scrapit @ file:///absolute/path/to/scrapit-api",
    # ... other dependencies
]
```

**Using relative path (if projects are in the same parent directory):**
```toml
[project]
dependencies = [
    "scrapit @ file:///${PROJECT_ROOT}/../scrapit-api",
    # ... other dependencies
]
```

**Example:** If your projects are structured like:
```
/path/to/projects/
├── scrapit-api/
└── your-other-project/
```

Then in `your-other-project/pyproject.toml`:
```toml
[project]
dependencies = [
    "scrapit @ file:///${PROJECT_ROOT}/../scrapit-api",
]
```

Then install:

```bash
cd /path/to/your/other/project
uv sync
# or
uv pip install -e .
```

### Option 2: Install from Local Path (Simplest)

In your other project directory:

```bash
# Using uv (recommended)
uv pip install -e /absolute/path/to/scrapit-api

# Or using pip
pip install -e /absolute/path/to/scrapit-api

# Example:
# uv pip install -e /Users/farhad/Documents/Work/Dataak/DCP/scrapit-api
```

**Note:** With this approach, you don't need to modify your `pyproject.toml`. The package will be installed in editable mode, so changes to `scrapit` will be reflected immediately.

### Option 3: Using UV Workspaces

If you want to manage both projects together, create a workspace:

1. Create a parent directory with a `pyproject.toml`:

```toml
[tool.uv.workspace]
members = [
    "scrapit-api",
    "your-other-project"
]
```

2. In your other project's `pyproject.toml`, add:

```toml
[project]
dependencies = [
    "scrapit",
    # ... other dependencies
]
```

3. Install from the workspace root:

```bash
cd /path/to/workspace
uv sync
```

### Using the Package in Your Code

Once installed, you can import and use it:

```python
from scrapit.api.endpoints import create_router
from scrapit.crawler.executor import CrawlExecutor
from scrapit.crawler.spider_loader import SpiderLoader

# Or use the CLI command
# scrapit -p 9080
```

## Debug Mode

When testing spiders, use the `--debug` flag to enable verbose logging:

```bash
scrapit -p 9080 --debug
```

Debug mode provides detailed logging at every stage:

- **API Layer**: Request parameters, validation, parameter merging
- **Executor**: Subprocess creation, execution, output parsing
- **Spider Runner**: Spider loading, crawl execution, item collection, stats
- **Response Building**: Response formatting and error handling

All logs include timestamps, module names, and line numbers for easy debugging.

## Development

```bash
# Install in development mode
pip install -e ".[dev]"

# Run the server
scrapit -p 9080

# Run with debug mode for testing
scrapit -p 9080 --debug
```

## Technical Documentation

For detailed technical documentation on how the project works internally, see [TECHNICAL.md](TECHNICAL.md). This document covers:

- System architecture and component details
- Request/response flow
- Concurrency model and subprocess isolation
- ScrapyRT compatibility details
- Error handling and troubleshooting
- Extension points and future enhancements

## License

See LICENCE file for details.

