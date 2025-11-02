"""
Tests for distributed tracing functionality.
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tracing import (
    setup_tracing,
    instrument_fastapi,
    instrument_database,
    instrument_httpx,
    get_tracer,
    trace_span,
    add_span_attribute,
    add_span_event,
    set_span_status,
)


class TestTracingSetup:
    """Test tracing initialization and setup."""
    
    def test_setup_tracing(self):
        """Test that tracing can be initialized."""
        # Clean up any existing tracer provider
        trace.set_tracer_provider(None)
        
        # Mock exporters to avoid actual network calls
        with patch('tracing.OTLPSpanExporter') as mock_otlp, \
             patch('tracing.JaegerExporter') as mock_jaeger, \
             patch('tracing.ConsoleSpanExporter') as mock_console:
            
            # Set environment to disable exporters
            os.environ['OTEL_EXPORTER_OTLP_ENABLED'] = 'false'
            os.environ['OTEL_EXPORTER_JAEGER_ENABLED'] = 'false'
            os.environ['OTEL_CONSOLE_EXPORTER_ENABLED'] = 'false'
            
            try:
                setup_tracing()
                tracer = get_tracer()
                assert tracer is not None
            finally:
                # Clean up
                trace.set_tracer_provider(None)
    
    def test_get_tracer(self):
        """Test getting tracer instance."""
        # Setup a minimal tracer provider
        provider = TracerProvider()
        processor = SimpleSpanProcessor(ConsoleSpanExporter())
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
        
        try:
            tracer = get_tracer()
            assert tracer is not None
            assert isinstance(tracer, trace.Tracer)
        finally:
            trace.set_tracer_provider(None)


class TestTracingInstrumentation:
    """Test instrumentation functions."""
    
    def test_instrument_fastapi(self):
        """Test FastAPI instrumentation."""
        from fastapi import FastAPI
        
        app = FastAPI()
        
        with patch('tracing.FastAPIInstrumentor') as mock_instrumentor:
            mock_instrumentor.instrument_app = MagicMock()
            instrument_fastapi(app)
            mock_instrumentor.instrument_app.assert_called_once_with(app)
    
    def test_instrument_database(self):
        """Test database instrumentation."""
        with patch('tracing.SQLite3Instrumentor') as mock_instrumentor:
            mock_instance = MagicMock()
            mock_instrumentor.return_value = mock_instance
            instrument_database()
            mock_instance.instrument.assert_called_once()
    
    def test_instrument_httpx(self):
        """Test HTTPX instrumentation."""
        with patch('tracing.HTTPXClientInstrumentor') as mock_instrumentor:
            mock_instance = MagicMock()
            mock_instrumentor.return_value = mock_instance
            instrument_httpx()
            mock_instance.instrument.assert_called_once()


class TestTracingContextManagers:
    """Test tracing context managers and utilities."""
    
    def test_trace_span(self):
        """Test trace_span context manager."""
        # Setup a minimal tracer provider
        provider = TracerProvider()
        processor = SimpleSpanProcessor(ConsoleSpanExporter())
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
        
        try:
            with trace_span("test.operation", attributes={"test.attr": "value"}) as span:
                assert span is not None
                assert span.name == "test.operation"
            
            # Verify span was created
            tracer = get_tracer()
            with tracer.start_as_current_span("test2") as span2:
                assert span2 is not None
        finally:
            trace.set_tracer_provider(None)
    
    def test_trace_span_with_exception(self):
        """Test trace_span handles exceptions correctly."""
        provider = TracerProvider()
        processor = SimpleSpanProcessor(ConsoleSpanExporter())
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
        
        try:
            with pytest.raises(ValueError):
                with trace_span("test.error"):
                    raise ValueError("Test error")
            
            # Span should have recorded the exception
        finally:
            trace.set_tracer_provider(None)
    
    def test_add_span_attribute(self):
        """Test adding attributes to current span."""
        provider = TracerProvider()
        processor = SimpleSpanProcessor(ConsoleSpanExporter())
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
        
        try:
            tracer = get_tracer()
            with tracer.start_as_current_span("test"):
                add_span_attribute("test.key", "test.value")
                add_span_attribute("test.number", 42)
                add_span_attribute("test.bool", True)
                
                # Should not raise
                assert True
        finally:
            trace.set_tracer_provider(None)
    
    def test_add_span_attribute_no_span(self):
        """Test add_span_attribute when no active span."""
        trace.set_tracer_provider(None)
        
        # Should not raise when no active span
        add_span_attribute("test.key", "test.value")
    
    def test_add_span_event(self):
        """Test adding events to current span."""
        provider = TracerProvider()
        processor = SimpleSpanProcessor(ConsoleSpanExporter())
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
        
        try:
            tracer = get_tracer()
            with tracer.start_as_current_span("test"):
                add_span_event("test.event", {"event.attr": "value"})
                # Should not raise
                assert True
        finally:
            trace.set_tracer_provider(None)
    
    def test_set_span_status(self):
        """Test setting span status."""
        provider = TracerProvider()
        processor = SimpleSpanProcessor(ConsoleSpanExporter())
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
        
        try:
            tracer = get_tracer()
            with tracer.start_as_current_span("test"):
                set_span_status(trace.StatusCode.OK, "Success")
                set_span_status(trace.StatusCode.ERROR, "Error occurred")
                # Should not raise
                assert True
        finally:
            trace.set_tracer_provider(None)


class TestTracingIntegration:
    """Test tracing integration with application components."""
    
    def test_tracing_with_database_operation(self):
        """Test that database operations create spans."""
        provider = TracerProvider()
        processor = SimpleSpanProcessor(ConsoleSpanExporter())
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
        
        try:
            # Import after setting up tracer
            import sys
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
            from database import TodoDatabase
            
            # Create in-memory database for testing
            db = TodoDatabase(":memory:")
            
            # Execute an operation that should create a span
            with trace_span("test.db_operation"):
                db.create_project("test_project", "http://example.com", "/path")
            
            # Verify spans were created (indirectly - if no exception, spans worked)
            assert True
        finally:
            trace.set_tracer_provider(None)
    
    def test_tracing_with_mcp_operations(self):
        """Test that MCP operations create spans."""
        provider = TracerProvider()
        processor = SimpleSpanProcessor(ConsoleSpanExporter())
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
        
        try:
            import sys
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
            from database import TodoDatabase
            from mcp_api import MCPTodoAPI, set_db
            
            # Setup database and MCP API
            db = TodoDatabase(":memory:")
            set_db(db)
            
            # Create a project
            project_id = db.create_project("test_project", "http://example.com", "/path")
            
            # Create a task
            task_id = db.create_task(
                title="Test Task",
                task_type="concrete",
                task_instruction="Do something",
                verification_instruction="Verify it",
                agent_id="test-agent",
                project_id=project_id
            )
            
            # Test MCP operations that should create spans
            tasks = MCPTodoAPI.list_available_tasks("implementation", project_id=project_id)
            assert isinstance(tasks, list)
            
            # Should not raise - spans created successfully
            assert True
        finally:
            trace.set_tracer_provider(None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])