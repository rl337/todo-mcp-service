"""
Adapter for GraphQL library (strawberry).
Isolates strawberry-specific imports to make library replacement easier.
"""
from typing import Any, Callable, Optional
try:
    import strawberry
    from strawberry.fastapi import GraphQLRouter
    GRAPHQL_AVAILABLE = True
except ImportError:
    GRAPHQL_AVAILABLE = False
    strawberry = None
    GraphQLRouter = None


class GraphQLType:
    """Abstracted GraphQL type decorator."""
    
    @staticmethod
    def type(cls=None, **kwargs):
        """Decorator for GraphQL types."""
        if not GRAPHQL_AVAILABLE:
            raise ImportError("strawberry is not available. Install strawberry to use this adapter.")
        if cls is None:
            return lambda cls: strawberry.type(cls, **kwargs)
        return strawberry.type(cls, **kwargs)


class GraphQLInput:
    """Abstracted GraphQL input decorator."""
    
    @staticmethod
    def input(cls=None, **kwargs):
        """Decorator for GraphQL input types."""
        if not GRAPHQL_AVAILABLE:
            raise ImportError("strawberry is not available. Install strawberry to use this adapter.")
        if cls is None:
            return lambda cls: strawberry.input(cls, **kwargs)
        return strawberry.input(cls, **kwargs)


class GraphQLField:
    """Abstracted GraphQL field decorator."""
    
    @staticmethod
    def field(func=None, **kwargs):
        """Decorator for GraphQL fields."""
        if not GRAPHQL_AVAILABLE:
            raise ImportError("strawberry is not available. Install strawberry to use this adapter.")
        if func is None:
            return lambda func: strawberry.field(func, **kwargs)
        return strawberry.field(func, **kwargs)


class GraphQLSchema:
    """Abstracted GraphQL schema."""
    
    def __init__(self, query: Optional[Any] = None, mutation: Optional[Any] = None, **kwargs):
        """Create GraphQL schema."""
        if not GRAPHQL_AVAILABLE:
            raise ImportError("strawberry is not available. Install strawberry to use this adapter.")
        self._schema = strawberry.Schema(query=query, mutation=mutation, **kwargs)
    
    @property
    def schema(self):
        """Get underlying schema object."""
        return self._schema


class GraphQLRouterAdapter:
    """Adapter for GraphQL router."""
    
    def __init__(self, schema: Any, **kwargs):
        """Create GraphQL router."""
        if not GRAPHQL_AVAILABLE:
            raise ImportError("strawberry is not available. Install strawberry to use this adapter.")
        self._router = GraphQLRouter(schema, **kwargs)
    
    @property
    def router(self):
        """Get underlying router object."""
        return self._router


class GraphQLAdapter:
    """Adapter for GraphQL operations."""
    
    def __init__(self):
        if not GRAPHQL_AVAILABLE:
            raise ImportError("strawberry is not available. Install strawberry to use this adapter.")
        
        self.type = GraphQLType.type
        self.input = GraphQLInput.input
        self.field = GraphQLField.field
        self.Schema = GraphQLSchema
        self.GraphQLRouter = GraphQLRouterAdapter
    
    def create_schema(self, query: Optional[Any] = None, mutation: Optional[Any] = None, **kwargs) -> GraphQLSchema:
        """Create a GraphQL schema."""
        return GraphQLSchema(query=query, mutation=mutation, **kwargs)
    
    def create_router(self, schema: Any, **kwargs) -> GraphQLRouterAdapter:
        """Create a GraphQL router."""
        return GraphQLRouterAdapter(schema, **kwargs)
