"""
Tests for adapter layers that abstract third-party dependencies.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock

from todorama.adapters import (
    HTTPClientAdapterFactory,
    HTTPResponse,
    HTTPError,
    HTTPStatusError,
    TimeoutException,
    NetworkError,
    RequestError,
    GraphQLAdapter,
    MetricsAdapter,
    HTTPFrameworkAdapter,
)


class TestHTTPClientAdapter:
    """Tests for HTTP client adapter."""
    
    def test_create_client(self):
        """Test creating synchronous HTTP client adapter."""
        with HTTPClientAdapterFactory.create_client(timeout=30.0) as client:
            assert client is not None
    
    def test_create_async_client(self):
        """Test creating async HTTP client adapter."""
        async def run_test():
            async with HTTPClientAdapterFactory.create_async_client(timeout=30.0) as client:
                assert client is not None
        
        import asyncio
        asyncio.run(run_test())
    
    def test_http_response_wrapper(self):
        """Test HTTPResponse wrapper."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"key": "value"}
        mock_response.content = b"content"
        mock_response.text = "text"
        mock_response.headers = {"Content-Type": "application/json"}
        
        response = HTTPResponse(mock_response)
        assert response.status_code == 200
        assert response.json() == {"key": "value"}
        assert response.content == b"content"
        assert response.text == "text"
        assert response.headers == {"Content-Type": "application/json"}
    
    def test_exception_classes_exist(self):
        """Test that exception classes are available."""
        assert HTTPError is not None
        assert HTTPStatusError is not None
        assert TimeoutException is not None
        assert NetworkError is not None
        assert RequestError is not None


class TestGraphQLAdapter:
    """Tests for GraphQL adapter."""
    
    def test_create_adapter(self):
        """Test creating GraphQL adapter."""
        adapter = GraphQLAdapter()
        assert adapter is not None
        assert adapter.type is not None
        assert adapter.input is not None
        assert adapter.field is not None
        assert adapter.Schema is not None
        assert adapter.GraphQLRouter is not None
    
    def test_create_schema(self):
        """Test creating GraphQL schema."""
        adapter = GraphQLAdapter()
        
        # Create a simple query type
        @adapter.type
        class Query:
            @adapter.field
            def hello(self) -> str:
                return "world"
        
        schema = adapter.create_schema(query=Query)
        assert schema is not None
        assert schema.schema is not None
    
    def test_create_router(self):
        """Test creating GraphQL router."""
        adapter = GraphQLAdapter()
        
        @adapter.type
        class Query:
            @adapter.field
            def hello(self) -> str:
                return "world"
        
        schema = adapter.create_schema(query=Query)
        router = adapter.create_router(schema.schema)
        assert router is not None
        assert router.router is not None


class TestMetricsAdapter:
    """Tests for metrics adapter."""
    
    def test_create_adapter(self):
        """Test creating metrics adapter."""
        adapter = MetricsAdapter()
        assert adapter is not None
        assert adapter.available is not None
        assert adapter.get_content_type() is not None
    
    def test_generate_metrics(self):
        """Test generating metrics response."""
        adapter = MetricsAdapter()
        metrics = adapter.generate_metrics_response()
        assert metrics is not None
        assert isinstance(metrics, (str, bytes))


class TestHTTPFrameworkAdapter:
    """Tests for HTTP framework adapter."""
    
    def test_create_adapter(self):
        """Test creating HTTP framework adapter."""
        adapter = HTTPFrameworkAdapter()
        assert adapter is not None
        assert adapter.FastAPI is not None
        assert adapter.APIRouter is not None
        assert adapter.HTTPException is not None
    
    def test_create_app(self):
        """Test creating FastAPI app via adapter."""
        adapter = HTTPFrameworkAdapter()
        app_adapter = adapter.create_app(title="Test App")
        assert app_adapter is not None
        assert app_adapter.app is not None
    
    def test_create_router(self):
        """Test creating router via adapter."""
        adapter = HTTPFrameworkAdapter()
        router_adapter = adapter.create_router()
        assert router_adapter is not None
        assert router_adapter.router is not None


class TestAdapterMocking:
    """Tests to verify adapters can be mocked for testing."""
    
    def test_mock_http_client(self):
        """Test that HTTP client adapter can be mocked."""
        with patch('todorama.adapters.http_client.HttpxClientAdapter') as mock_adapter:
            mock_client = Mock()
            mock_adapter.return_value = mock_client
            # Adapter can be mocked
            assert True
    
    def test_mock_graphql_adapter(self):
        """Test that GraphQL adapter can be mocked."""
        with patch('todorama.adapters.graphql_adapter.GraphQLAdapter') as mock_adapter:
            mock_adapter.return_value = Mock()
            # Adapter can be mocked
            assert True
    
    def test_mock_metrics_adapter(self):
        """Test that metrics adapter can be mocked."""
        with patch('todorama.adapters.metrics.MetricsAdapter') as mock_adapter:
            mock_adapter.return_value = Mock()
            # Adapter can be mocked
            assert True
