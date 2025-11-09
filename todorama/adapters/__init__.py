"""
Adapters for external services and third-party libraries.
"""
from todorama.adapters.http_client import (
    HTTPClientAdapterFactory,
    HTTPResponse,
    HTTPError,
    HTTPStatusError,
    TimeoutException,
    NetworkError,
    RequestError,
    HTTP_CLIENT_AVAILABLE
)
from todorama.adapters.graphql_adapter import (
    GraphQLAdapter,
    GraphQLType,
    GraphQLInput,
    GraphQLField,
    GraphQLSchema,
    GraphQLRouterAdapter,
    GRAPHQL_AVAILABLE
)
from todorama.adapters.metrics import MetricsAdapter, METRICS_AVAILABLE
from todorama.adapters.http_framework import HTTPFrameworkAdapter, HTTP_FRAMEWORK_AVAILABLE

__all__ = [
    # HTTP Client
    "HTTPClientAdapterFactory",
    "HTTPResponse",
    "HTTPError",
    "HTTPStatusError",
    "TimeoutException",
    "NetworkError",
    "RequestError",
    "HTTP_CLIENT_AVAILABLE",
    # GraphQL
    "GraphQLAdapter",
    "GraphQLType",
    "GraphQLInput",
    "GraphQLField",
    "GraphQLSchema",
    "GraphQLRouterAdapter",
    "GRAPHQL_AVAILABLE",
    # Metrics
    "MetricsAdapter",
    "METRICS_AVAILABLE",
    # HTTP Framework
    "HTTPFrameworkAdapter",
    "HTTP_FRAMEWORK_AVAILABLE",
]
