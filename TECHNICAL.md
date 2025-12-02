# Technical Documentation

## Architecture Overview

scrapit is a FastAPI-based wrapper that provides a ScrapyRT-compatible API for executing Scrapy spiders. The architecture is designed to support concurrent spider executions through subprocess isolation, avoiding Twisted reactor conflicts.

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Application                      │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              API Endpoint Layer                       │  │
│  │  POST /crawl.json - Request/Response Handling         │  │
│  └─────────────────────────────────────────────────────┘  │
│                          │                                  │
│                          ▼                                  │
│  ┌─────────────────────────────────────────────────────┐  │
│  │           Crawl Executor (Async)                      │  │
│  │  - Subprocess Management                              │  │
│  │  - Timeout Handling                                   │  │
│  │  - Output Collection                                  │  │
│  └─────────────────────────────────────────────────────┘  │
│                          │                                  │
│                          ▼                                  │
│  ┌─────────────────────────────────────────────────────┐  │
│  │      Subprocess: scrapy_runner.py                    │  │
│  │  - Isolated Scrapy Execution                         │  │
│  │  - Item Collection                                    │  │
│  │  - Stats Collection                                   │  │
│  │  - Log Capture                                        │  │
│  └─────────────────────────────────────────────────────┘  │
│                          │                                  │
│                          ▼                                  │
│  ┌─────────────────────────────────────────────────────┐  │
│  │         Response Builder                              │  │
│  │  - JSON Serialization                                 │  │
│  │  - Datetime Conversion                                │  │
│  │  - ScrapyRT Format Normalization                      │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. API Layer (`scrapit/api/`)

#### `endpoints.py`
- **Purpose**: Handles HTTP requests and responses
- **Key Functions**:
  - `create_router()`: Creates FastAPI router with crawl endpoint
  - `crawl()`: POST `/crawl.json` endpoint handler
- **Features**:
  - Accepts parameters via both query parameters and JSON body
  - Body parameters take precedence over query parameters (ScrapyRT behavior)
  - Validates spider existence before execution
  - Handles parameter merging and normalization

#### `models.py`
- **Purpose**: Pydantic models for request/response validation
- **Models**:
  - `RequestObject`: Nested request object (url, callback, meta, headers, etc.)
  - `CrawlRequest`: Main request model with spider_name, start_requests, crawl_args
  - `CrawlResponse`: Response model matching ScrapyRT format (status, items, stats, errors, logs)

### 2. Crawler Orchestration (`scrapit/crawler/`)

#### `spider_loader.py`
- **Purpose**: Discovers and validates Scrapy spiders
- **Key Features**:
  - Auto-discovers Scrapy project from current working directory
  - Uses Scrapy's `CrawlerProcess` to load spider classes
  - Validates spider existence before execution
  - Caches discovered spiders for performance

#### `executor.py`
- **Purpose**: Manages subprocess-based crawl execution
- **Key Features**:
  - Creates isolated subprocess for each crawl
  - Manages process lifecycle (spawn, monitor, timeout, cleanup)
  - Sets PYTHONPATH to ensure local modules can be imported
  - Collects stdout/stderr from subprocess
  - Handles timeout and error scenarios
  - Filters logs based on `include_logs` setting

**Process Flow**:
1. Prepare configuration JSON file
2. Spawn subprocess with `scrapy_runner.py`
3. Wait for completion with timeout
4. Parse JSON output from stdout
5. Build ScrapyRT-compatible response
6. Clean up temporary files

#### `response_builder.py`
- **Purpose**: Normalizes crawl results to ScrapyRT format
- **Key Features**:
  - Builds response dictionaries with proper structure
  - Handles error responses
  - Parses subprocess JSON output
  - Extracts JSON from mixed stdout (handles log messages before JSON)
  - Uses intelligent JSON extraction (finds last valid JSON object)

**JSON Extraction Strategy**:
1. Try parsing entire output as JSON
2. If fails, find last occurrence of `"items"` key
3. Work backwards to find opening `{`
4. Work forwards to find matching closing `}`
5. Extract and parse that JSON object
6. Verify it has expected structure

### 3. Subprocess Worker (`scrapit/utils/scrapy_runner.py`)

- **Purpose**: Standalone script that runs in subprocess to execute spiders
- **Key Features**:
  - Accepts configuration via JSON file (command-line argument)
  - Configures Scrapy logging to capture logs
  - Creates CrawlerProcess with project settings
  - Handles custom request objects and start_requests flag
  - Collects items via signal handlers
  - Collects stats when spider closes
  - Serializes datetime objects to ISO format strings
  - Outputs results as JSON to stdout

**Spider Execution Flow**:
1. Parse configuration from JSON file
2. Change to project directory
3. Add project directory to sys.path
4. Configure Scrapy logging
5. Load project settings
6. Create CrawlerProcess
7. Load spider class
8. Create wrapper spider if custom request handling needed
9. Connect signal handlers for items and stats
10. Start crawl
11. Collect results
12. Serialize and output JSON

**Custom Request Handling**:
- If `request_obj` is provided, creates a wrapper spider class
- Wrapper overrides `start_requests()` to use custom request
- Handles callback/errback method resolution
- Supports all Scrapy Request parameters (url, meta, headers, cookies, body, method)

**Datetime Serialization**:
- Recursively processes items and stats
- Converts `datetime` and `date` objects to ISO format strings
- Handles nested dictionaries and lists
- Ensures JSON serializability

## Request Flow

### 1. HTTP Request Received
```
POST /crawl.json
{
  "spider_name": "example_spider",
  "start_requests": true,
  "crawl_args": {...}
}
```

### 2. API Endpoint Processing
- Parse query parameters and JSON body
- Merge parameters (body takes precedence)
- Validate `spider_name` is present
- Validate spider exists using `SpiderLoader`

### 3. Crawl Execution
- `CrawlExecutor.execute_crawl()` is called
- Creates temporary JSON config file
- Spawns subprocess with `scrapy_runner.py`
- Subprocess runs in isolated environment

### 4. Subprocess Execution
- `scrapy_runner.py` reads config file
- Changes to project directory
- Sets up Python path
- Configures Scrapy
- Executes spider
- Collects items, stats, logs
- Serializes datetime objects
- Outputs JSON to stdout

### 5. Output Collection
- Executor reads stdout from subprocess
- Parses JSON (handles mixed output with logs)
- Builds response dictionary
- Filters logs if `include_logs=False`

### 6. Response Returned
```json
{
  "status": "ok",
  "items": [...],
  "stats": {...},
  "errors": null,
  "logs": [...]  // or null if include_logs=False
}
```

## Concurrency Model

### Subprocess Isolation
- Each crawl runs in a separate subprocess
- Prevents Twisted reactor conflicts
- Allows concurrent executions without interference
- Each subprocess has isolated:
  - Python path
  - Working directory
  - Environment variables
  - Scrapy settings

### Process Management
- Async subprocess execution using `asyncio.create_subprocess_exec`
- Timeout handling per crawl
- Process cleanup on completion or timeout
- Proper signal handling for graceful shutdown

## Configuration

### CLI Options
- `--port, -p`: Server port (default: 9080)
- `--host, -i`: Host address (default: 0.0.0.0)
- `--project, -P`: Scrapy project path (default: CWD)
- `--settings, -s`: Scrapy settings (KEY=VALUE format)
- `--timeout, -t`: Default crawl timeout in seconds
- `--debug, -d`: Enable debug logging
- `--include-logs/--no-logs`: Include/exclude logs in responses (default: include)

### Environment Setup
- PYTHONPATH is set to project directory for subprocess
- Project directory is added to sys.path in runner
- Scrapy project settings are loaded from `scrapy.cfg`

## Error Handling

### API Level
- Invalid requests return 400 with error details
- Spider not found returns 404
- Internal errors return 500

### Execution Level
- Subprocess failures are caught and returned as error responses
- Timeout errors are handled gracefully
- JSON parsing errors include detailed output for debugging

### Response Format
- Errors are always included in response (even if logs are excluded)
- Error responses follow ScrapyRT format
- Partial stats may be included if available

## Logging

### Log Levels
- **INFO**: Normal operation (requests, completions)
- **DEBUG**: Detailed information (parameters, parsing steps)
- **WARNING**: Non-fatal issues (invalid settings, parse attempts)
- **ERROR**: Failures (subprocess errors, parse failures)

### Log Capture
- Scrapy logs are captured via custom handler
- Logs are collected during spider execution
- Can be included or excluded from API responses
- Debug mode provides verbose logging at all stages

## ScrapyRT Compatibility

### Request Compatibility
- Supports all ScrapyRT request fields
- Parameter merging matches ScrapyRT behavior
- Request object structure matches ScrapyRT
- Default values match ScrapyRT

### Response Compatibility
- Response structure matches ScrapyRT exactly
- Field names are identical
- Stats format matches ScrapyRT
- Error format matches ScrapyRT
- Logs format matches ScrapyRT (when included)

### Behavioral Compatibility
- Spider discovery works like ScrapyRT
- Request handling matches ScrapyRT
- Stats collection matches ScrapyRT
- Error handling matches ScrapyRT

## Performance Considerations

### Subprocess Overhead
- Each crawl spawns a new process (necessary for reactor isolation)
- Process creation overhead is minimal
- Subprocess execution is async (non-blocking)

### Memory Management
- Each subprocess has isolated memory
- No memory leaks from reactor reuse
- Proper cleanup of temporary files

### Concurrent Execution
- Multiple crawls can run simultaneously
- Each in isolated subprocess
- No interference between crawls
- Limited only by system resources

## Security Considerations

### Subprocess Isolation
- Each crawl runs in isolated process
- No shared state between crawls
- Project directory isolation

### Input Validation
- Pydantic models validate all inputs
- Spider name validation prevents arbitrary code execution
- Parameter sanitization

### Error Information
- Error messages don't expose sensitive information
- Debug mode provides detailed logging (use with caution)

## Extension Points

### Custom Settings
- Additional Scrapy settings can be passed via CLI
- Settings are applied to CrawlerProcess
- Supports all Scrapy settings

### Custom Request Handling
- Request objects support all Scrapy Request parameters
- Custom callbacks and errbacks
- Custom meta, headers, cookies

### Response Customization
- Response builder can be extended
- Log filtering is configurable
- Stats can be customized

## Troubleshooting

### Common Issues

1. **Module Import Errors**
   - Ensure project directory is in PYTHONPATH
   - Check that project structure is correct
   - Verify scrapy.cfg exists

2. **JSON Parse Errors**
   - Check if logs are interfering with JSON output
   - Enable debug mode to see raw output
   - Verify scrapy_runner.py outputs valid JSON

3. **Spider Not Found**
   - Verify spider name matches exactly
   - Check that spider is in correct project
   - Ensure scrapy.cfg is in project root

4. **Timeout Issues**
   - Increase timeout via CLI option
   - Check spider performance
   - Verify network connectivity

### Debug Mode
- Enable with `--debug` flag
- Provides detailed logging at all stages
- Shows subprocess output
- Helps identify parsing issues

## Future Enhancements

### Potential Improvements
- Process pool for subprocess reuse (with reactor reset)
- Streaming responses for long-running crawls
- WebSocket support for real-time updates
- Metrics collection and monitoring
- Rate limiting and queue management

