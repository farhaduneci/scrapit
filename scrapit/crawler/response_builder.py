"""Response normalization to ScrapyRT format."""

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ResponseBuilder:
    """Builds ScrapyRT-compatible responses from crawl results."""

    @staticmethod
    def build_response(
        items: List[Dict[str, Any]],
        stats: Dict[str, Any],
        errors: Optional[List[str]] = None,
        status: str = "ok",
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a ScrapyRT-compatible response.

        Args:
            items: List of scraped items.
            stats: Crawl statistics dictionary.
            errors: List of error messages (optional).
            status: Response status ('ok' or 'error').
            request_id: Unique identifier for this request.

        Returns:
            Dictionary matching ScrapyRT response format.
        """
        response: Dict[str, Any] = {
            "status": status,
            "request_id": request_id or "",
            "items": items,
            "stats": stats,
        }

        if errors:
            response["errors"] = errors

        return response

    @staticmethod
    def build_error_response(
        error_message: str,
        errors: Optional[List[str]] = None,
        stats: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build an error response in ScrapyRT format.

        Args:
            error_message: Main error message.
            errors: Additional error messages (optional).
            stats: Partial stats if available (optional).
            request_id: Unique identifier for this request.

        Returns:
            Error response dictionary.
        """
        error_list = [error_message]
        if errors:
            error_list.extend(errors)

        response: Dict[str, Any] = {
            "status": "error",
            "request_id": request_id or "",
            "items": [],
            "stats": stats or {},
            "errors": error_list,
        }

        return response

    @staticmethod
    def parse_subprocess_output(output: str) -> Dict[str, Any]:
        """Parse JSON output from subprocess.

        Args:
            output: JSON string from subprocess (may contain extra text).

        Returns:
            Parsed dictionary with items, stats, errors.

        Raises:
            ValueError: If output cannot be parsed.
        """
        if not output or not output.strip():
            raise ValueError("Empty output from subprocess")

        # Try to extract JSON from output (in case there's extra logging before/after)
        # Look for JSON object boundaries
        output = output.strip()

        # Try to find the JSON object in the output
        # First, try parsing the whole thing
        try:
            logger.debug(
                f"Attempting to parse full output as JSON (length: {len(output)})"
            )
            data = json.loads(output)
            logger.debug("Successfully parsed full output as JSON")
            return {
                "items": data.get("items", []),
                "stats": data.get("stats", {}),
                "errors": data.get("errors"),
            }
        except json.JSONDecodeError as e:
            logger.debug(
                f"Full output parse failed: {e}, trying to extract JSON object"
            )

            # Find the last valid JSON object (the one with our expected structure)
            # Strategy: Find the last occurrence of "items" key and work backwards/forwards to get the JSON object
            items_key_pos = output.rfind('"items"')
            if items_key_pos == -1:
                # Fallback: try to find any JSON object from the end
                last_brace = output.rfind("}")
                if last_brace == -1:
                    logger.error("No closing brace found in output")
                    raise ValueError(
                        f"Failed to parse subprocess output: {e}. No JSON object found."
                    ) from e

                # Work backwards from last } to find matching {
                brace_count = 0
                start_pos = -1
                for i in range(last_brace, -1, -1):
                    if output[i] == "}":
                        brace_count += 1
                    elif output[i] == "{":
                        brace_count -= 1
                        if brace_count == 0:
                            start_pos = i
                            break

                if start_pos == -1:
                    logger.error("Could not find matching opening brace")
                    raise ValueError(
                        f"Failed to parse subprocess output: {e}. No valid JSON object found."
                    ) from e

                json_str = output[start_pos : last_brace + 1]
            else:
                # Found "items" key, find the JSON object containing it
                # Work backwards to find the opening {
                start_pos = output.rfind("{", 0, items_key_pos)
                if start_pos == -1:
                    logger.error("Could not find opening brace before 'items' key")
                    raise ValueError(
                        f"Failed to parse subprocess output: {e}. No JSON object found."
                    ) from e

                # Work forwards from start_pos to find the matching closing }
                brace_count = 0
                last_brace = -1
                for i in range(start_pos, len(output)):
                    if output[i] == "{":
                        brace_count += 1
                    elif output[i] == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            last_brace = i
                            break

                if last_brace == -1:
                    logger.error("Could not find matching closing brace")
                    raise ValueError(
                        f"Failed to parse subprocess output: {e}. No valid JSON object found."
                    ) from e

                json_str = output[start_pos : last_brace + 1]

            logger.debug(
                f"Extracted JSON substring (chars {start_pos}-{last_brace}, length: {len(json_str)})"
            )
            logger.debug(
                f"Extracted JSON preview (first 200 chars): {json_str[:200]}..."
            )
            try:
                data = json.loads(json_str)
                # Verify it has the expected structure
                if "items" in data or "stats" in data or "errors" in data:
                    logger.debug(
                        "Successfully parsed extracted JSON with expected structure"
                    )
                    return {
                        "items": data.get("items", []),
                        "stats": data.get("stats", {}),
                        "errors": data.get("errors"),
                    }
                else:
                    logger.warning("Extracted JSON doesn't have expected structure")
                    raise json.JSONDecodeError("Unexpected structure", json_str, 0)
            except json.JSONDecodeError as e2:
                logger.error(f"Extracted JSON also failed to parse: {e2}")
                logger.error(
                    f"Extracted JSON string (first 500 chars): {json_str[:500]}"
                )
                # Last resort: try to find JSON in the last few lines
                lines = output.split("\n")
                for line in reversed(lines):
                    line = line.strip()
                    if line.startswith("{") and '"items"' in line:
                        try:
                            data = json.loads(line)
                            if "items" in data or "stats" in data:
                                logger.debug(
                                    "Found valid JSON in line containing 'items'"
                                )
                                return {
                                    "items": data.get("items", []),
                                    "stats": data.get("stats", {}),
                                    "errors": data.get("errors"),
                                }
                        except json.JSONDecodeError:
                            continue
                raise ValueError(
                    f"Failed to parse subprocess output: {e}. Extracted JSON also failed: {e2}"
                ) from e2
            else:
                logger.error("Could not find JSON object boundaries in output")
                logger.error(f"Output preview (first 500 chars): {output[:500]}")
                raise ValueError(
                    f"Failed to parse subprocess output: {e}. No JSON object found in output."
                ) from e
