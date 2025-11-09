"""
Adapter for HTTP client library (httpx).
Isolates httpx-specific imports to make library replacement easier.
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, AsyncIterator
try:
    import httpx
    HTTP_CLIENT_AVAILABLE = True
except ImportError:
    HTTP_CLIENT_AVAILABLE = False
    httpx = None


class HTTPResponse:
    """Abstracted HTTP response interface."""
    
    def __init__(self, response):
        """Initialize with underlying response object."""
        self._response = response
    
    @property
    def status_code(self) -> int:
        """Get HTTP status code."""
        return self._response.status_code
    
    def raise_for_status(self) -> None:
        """Raise exception if status code indicates error."""
        self._response.raise_for_status()
    
    def json(self) -> Any:
        """Parse response as JSON."""
        return self._response.json()
    
    @property
    def content(self) -> bytes:
        """Get response content as bytes."""
        return self._response.content
    
    @property
    def text(self) -> str:
        """Get response content as text."""
        return self._response.text
    
    @property
    def headers(self) -> Dict[str, str]:
        """Get response headers."""
        return dict(self._response.headers)
    
    def aiter_lines(self):
        """Async iterator for response lines (for streaming)."""
        # Delegate to underlying response for streaming support
        return self._response.aiter_lines()
    
    @property
    def response(self):
        """Get underlying response object (for advanced use cases)."""
        return self._response


class HTTPClientAdapter(ABC):
    """Abstract adapter for HTTP client operations."""
    
    @abstractmethod
    def get(self, url: str, **kwargs) -> HTTPResponse:
        """Make GET request."""
        pass
    
    @abstractmethod
    def post(self, url: str, **kwargs) -> HTTPResponse:
        """Make POST request."""
        pass
    
    @abstractmethod
    def put(self, url: str, **kwargs) -> HTTPResponse:
        """Make PUT request."""
        pass
    
    @abstractmethod
    def delete(self, url: str, **kwargs) -> HTTPResponse:
        """Make DELETE request."""
        pass


class AsyncHTTPClientAdapter(ABC):
    """Abstract adapter for async HTTP client operations."""
    
    @abstractmethod
    async def get(self, url: str, **kwargs) -> HTTPResponse:
        """Make async GET request."""
        pass
    
    @abstractmethod
    async def post(self, url: str, **kwargs) -> HTTPResponse:
        """Make async POST request."""
        pass
    
    @abstractmethod
    async def stream(self, method: str, url: str, **kwargs) -> AsyncIterator[HTTPResponse]:
        """Make async streaming request."""
        pass


class HttpxClientAdapter(HTTPClientAdapter):
    """httpx implementation of HTTPClientAdapter."""
    
    def __init__(self, timeout: Optional[float] = None, **kwargs):
        """Initialize httpx client."""
        if not HTTP_CLIENT_AVAILABLE:
            raise ImportError("httpx is not available. Install httpx to use this adapter.")
        self._client = httpx.Client(timeout=timeout, **kwargs)
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self._client.close()
    
    def get(self, url: str, **kwargs) -> HTTPResponse:
        """Make GET request."""
        response = self._client.get(url, **kwargs)
        return HTTPResponse(response)
    
    def post(self, url: str, **kwargs) -> HTTPResponse:
        """Make POST request."""
        response = self._client.post(url, **kwargs)
        return HTTPResponse(response)
    
    def put(self, url: str, **kwargs) -> HTTPResponse:
        """Make PUT request."""
        response = self._client.put(url, **kwargs)
        return HTTPResponse(response)
    
    def delete(self, url: str, **kwargs) -> HTTPResponse:
        """Make DELETE request."""
        response = self._client.delete(url, **kwargs)
        return HTTPResponse(response)
    
    def close(self):
        """Close the client."""
        self._client.close()


class HttpxAsyncClientAdapter(AsyncHTTPClientAdapter):
    """httpx async implementation of AsyncHTTPClientAdapter."""
    
    def __init__(self, timeout: Optional[float] = None, **kwargs):
        """Initialize httpx async client."""
        if not HTTP_CLIENT_AVAILABLE:
            raise ImportError("httpx is not available. Install httpx to use this adapter.")
        self._client = httpx.AsyncClient(timeout=timeout, **kwargs)
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self._client.aclose()
    
    async def get(self, url: str, **kwargs) -> HTTPResponse:
        """Make async GET request."""
        response = await self._client.get(url, **kwargs)
        return HTTPResponse(response)
    
    async def post(self, url: str, **kwargs) -> HTTPResponse:
        """Make async POST request."""
        response = await self._client.post(url, **kwargs)
        return HTTPResponse(response)
    
    async def stream(self, method: str, url: str, **kwargs):
        """Make async streaming request. Returns context manager."""
        # Return the stream context manager directly so caller can use it
        # The response inside will be accessible and can be wrapped when needed
        return self._client.stream(method, url, **kwargs)
    
    async def aclose(self):
        """Close the async client."""
        await self._client.aclose()


class HTTPClientAdapterFactory:
    """Factory for creating HTTP client adapters."""
    
    @staticmethod
    def create_client(timeout: Optional[float] = None, **kwargs) -> HTTPClientAdapter:
        """Create synchronous HTTP client adapter."""
        if not HTTP_CLIENT_AVAILABLE:
            raise ImportError("httpx is not available. Install httpx to use this adapter.")
        return HttpxClientAdapter(timeout=timeout, **kwargs)
    
    @staticmethod
    def create_async_client(timeout: Optional[float] = None, **kwargs) -> AsyncHTTPClientAdapter:
        """Create async HTTP client adapter."""
        if not HTTP_CLIENT_AVAILABLE:
            raise ImportError("httpx is not available. Install httpx to use this adapter.")
        return HttpxAsyncClientAdapter(timeout=timeout, **kwargs)


# Export exception classes for compatibility
if HTTP_CLIENT_AVAILABLE:
    HTTPError = httpx.HTTPError
    HTTPStatusError = httpx.HTTPStatusError
    TimeoutException = httpx.TimeoutException
    NetworkError = httpx.NetworkError
    RequestError = httpx.RequestError
else:
    # Fallback exception classes when httpx is not available
    class HTTPError(Exception):
        """Base HTTP error."""
        pass
    
    class HTTPStatusError(HTTPError):
        """HTTP status error."""
        def __init__(self, message: str, response=None):
            super().__init__(message)
            self.response = response
    
    class TimeoutException(HTTPError):
        """Timeout exception."""
        pass
    
    class NetworkError(HTTPError):
        """Network error."""
        pass
    
    class RequestError(HTTPError):
        """Request error."""
        pass
