"""Centralized HTTP request error handling utilities"""

import json
from typing import Any, Dict, Optional

import requests  # type: ignore[import-untyped]

from . import app_logger
from .exceptions import NetworkError


class RequestErrorHandler:
    """Handles common HTTP request error patterns for cloud services"""

    # HTTP Status Code Constants
    HTTP_OK = 200
    HTTP_BAD_REQUEST = 400
    HTTP_UNAUTHORIZED = 401
    HTTP_PAYMENT_REQUIRED = 402
    HTTP_FORBIDDEN = 403
    HTTP_NOT_FOUND = 404
    HTTP_TOO_MANY_REQUESTS = 429
    HTTP_SERVER_ERROR = 500
    HTTP_SERVICE_UNAVAILABLE = 503

    # Retry Configuration Constants
    MAX_RETRIES = 3
    RETRY_DELAY_BASE = 1.0
    RETRY_DELAY_MAX = 60.0
    TIMEOUT_RETRY_MAX = 10.0

    @staticmethod
    def parse_json_safely(
        response: requests.Response, provider_name: str = "API"
    ) -> Optional[Dict[str, Any]]:
        """Safely parse JSON response with error handling

        Args:
            response: HTTP response object
            provider_name: Name of API provider for logging

        Returns:
            Parsed JSON dict or None on error

        Raises:
            NetworkError: If JSON parsing fails critically
        """
        try:
            return response.json()
        except json.JSONDecodeError as e:
            app_logger.error(
                "Failed to parse JSON response",
                e,
                context={
                    "provider": provider_name,
                    "status_code": response.status_code,
                    "content_length": len(response.text),
                    "content_preview": response.text[:200],
                },
                component="json_parse_error",
            )
            raise NetworkError(
                f"{provider_name} returned invalid JSON",
                context={"status_code": response.status_code},
            )

    @staticmethod
    def handle_http_status(
        status_code: int, response_text: str, provider_name: str
    ) -> Optional[str]:
        """Handle common HTTP status codes

        Args:
            status_code: HTTP status code
            response_text: Response body text
            provider_name: Name of API provider

        Returns:
            Error message if error, None if retryable
        """
        error_messages = {
            RequestErrorHandler.HTTP_BAD_REQUEST: f"Bad request to {provider_name}: {response_text[:200]}",
            RequestErrorHandler.HTTP_UNAUTHORIZED: f"Invalid API key for {provider_name}",
            RequestErrorHandler.HTTP_PAYMENT_REQUIRED: f"{provider_name} account has insufficient credits",
            RequestErrorHandler.HTTP_FORBIDDEN: f"Access forbidden by {provider_name}",
            RequestErrorHandler.HTTP_NOT_FOUND: f"{provider_name} endpoint not found",
            RequestErrorHandler.HTTP_SERVER_ERROR: None,  # Retryable
            RequestErrorHandler.HTTP_SERVICE_UNAVAILABLE: None,  # Retryable
        }

        return error_messages.get(
            status_code,
            f"HTTP {status_code} from {provider_name}: {response_text[:200]}",
        )

    @staticmethod
    def should_retry_status(status_code: int) -> bool:
        """Check if status code is retryable

        Args:
            status_code: HTTP status code

        Returns:
            True if should retry
        """
        retryable_statuses = {
            RequestErrorHandler.HTTP_TOO_MANY_REQUESTS,
            RequestErrorHandler.HTTP_SERVER_ERROR,
            RequestErrorHandler.HTTP_SERVICE_UNAVAILABLE,
        }
        return status_code in retryable_statuses

    @staticmethod
    def calculate_retry_delay(
        attempt: int,
        base_delay: float = RETRY_DELAY_BASE,
        max_delay: float = RETRY_DELAY_MAX,
        is_timeout: bool = False,
    ) -> float:
        """Calculate exponential backoff delay

        Args:
            attempt: Current attempt number (0-indexed)
            base_delay: Base delay in seconds
            max_delay: Maximum delay cap
            is_timeout: Use shorter delays for timeouts

        Returns:
            Delay in seconds
        """
        if is_timeout:
            max_delay = RequestErrorHandler.TIMEOUT_RETRY_MAX
            return min(base_delay * (1.5**attempt), max_delay)
        return min(base_delay * (2**attempt), max_delay)

    @staticmethod
    def extract_error_message(response: requests.Response, provider_name: str) -> str:
        """Extract error message from response with fallback

        Args:
            response: HTTP response object
            provider_name: Name of API provider

        Returns:
            Extracted error message or generic error
        """
        try:
            # Try to parse JSON error response
            error_data = response.json()
            # Common error message patterns
            if isinstance(error_data, dict):
                # Try different common error keys
                for key in ["error", "message", "detail", "error_description"]:
                    if key in error_data:
                        error_value = error_data[key]
                        # Handle nested error objects
                        if isinstance(error_value, dict):
                            if "message" in error_value:
                                return str(error_value["message"])
                        return str(error_value)
        except Exception as e:
            app_logger.error(
                "Failed to extract error message from response",
                e,
                context={
                    "provider": provider_name,
                    "status_code": response.status_code,
                },
                component="extract_error_message_failed",
            )

        # Fallback to raw text
        return f"HTTP {response.status_code}: {response.text[:200]}"
