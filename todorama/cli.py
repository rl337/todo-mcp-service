#!/usr/bin/env python3
"""
Command-line interface for TODO MCP Service.
"""
import os
import sys
import json
import click
from typing import Optional, Dict, Any

from todorama.adapters import HTTPClientAdapterFactory, HTTPResponse, HTTPStatusError


def get_service_url() -> str:
    """Get service URL from environment or default."""
    return os.getenv("TODO_SERVICE_URL", "http://localhost:8000/mcp/todo-mcp-service")


def get_api_key() -> Optional[str]:
    """Get API key from environment."""
    return os.getenv("TODO_API_KEY")


def make_request(
    method: str,
    endpoint: str,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    **kwargs
) -> HTTPResponse:
    """Make HTTP request to TODO service."""
    base_url = base_url or get_service_url()
    url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
    
    headers = kwargs.pop("headers", {})
    if api_key:
        headers["X-API-Key"] = api_key
    
    with HTTPClientAdapterFactory.create_client(timeout=30.0) as client:
        try:
            if method.upper() == "GET":
                response = client.get(url, headers=headers, **kwargs)
            elif method.upper() == "POST":
                response = client.post(url, headers=headers, **kwargs)
            elif method.upper() == "PATCH":
                response = client.patch(url, headers=headers, **kwargs)
            elif method.upper() == "DELETE":
                response = client.delete(url, headers=headers, **kwargs)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            return response
        except HTTPStatusError as e:
            error_data = e.response.json() if e.response.content else {}
            click.echo(f"Error {e.response.status_code}: {error_data.get('detail', 'Unknown error')}", err=True)
            sys.exit(1)


def format_task(task: Dict[str, Any]) -> str:
    """Format task for display."""
    lines = [
        f"Task #{task['id']}: {task['title']}",
        f"  Type: {task.get('task_type', 'N/A')}",
        f"  Status: {task.get('task_status', 'N/A')}",
        f"  Priority: {task.get('priority', 'medium')}",
    ]
    
    if task.get('assigned_agent'):
        lines.append(f"  Assigned to: {task['assigned_agent']}")
    
    if task.get('project_id'):
        lines.append(f"  Project ID: {task['project_id']}")
    
    if task.get('created_at'):
        lines.append(f"  Created: {task['created_at']}")
    
    if task.get('task_instruction'):
        lines.append(f"  Instruction: {task['task_instruction'][:100]}...")
    
    return "\n".join(lines)


def format_json(data: Any) -> str:
    """Format data as JSON."""
    return json.dumps(data, indent=2, default=str)


@click.group()
@click.option('--url', envvar='TODO_SERVICE_URL', default=None,
              help='TODO service URL (default: http://localhost:8000/mcp/todo-mcp-service)')
@click.option('--api-key', envvar='TODO_API_KEY', default=None,
              help='API key for authentication')
@click.pass_context
def cli(ctx, url, api_key):
    """TODO MCP Service CLI tool for managing tasks."""
    ctx.ensure_object(dict)
    ctx.obj['url'] = url or get_service_url()
    ctx.obj['api_key'] = api_key or get_api_key()


@cli.command()
@click.option('--status', 'task_status', help='Filter by task status')
@click.option('--type', 'task_type', help='Filter by task type (concrete, abstract, epic)')
@click.option('--project-id', 'project_id', type=int, help='Filter by project ID')
@click.option('--agent', 'assigned_agent', help='Filter by assigned agent')
@click.option('--priority', help='Filter by priority (low, medium, high, critical)')
@click.option('--limit', type=int, default=100, help='Maximum number of results')
@click.option('--format', 'output_format', type=click.Choice(['table', 'json']),
              default='table', help='Output format')
@click.pass_context
def list(ctx, task_status, task_type, project_id, assigned_agent, priority, limit, output_format):
    """List tasks with optional filters."""
    params = {}
    if task_status:
        params['task_status'] = task_status
    if task_type:
        params['task_type'] = task_type
    if project_id:
        params['project_id'] = project_id
    if assigned_agent:
        params['assigned_agent'] = assigned_agent
    if priority:
        params['priority'] = priority
    if limit:
        params['limit'] = limit
    
    try:
        response = make_request(
            'GET',
            '/tasks',
            api_key=ctx.obj['api_key'],
            base_url=ctx.obj['url'],
            params=params
        )
        response.raise_for_status()
        tasks = response.json()
        
        if output_format == 'json':
            click.echo(format_json(tasks))
        else:
            if not tasks:
                click.echo("No tasks found.")
                return
            
            for task in tasks:
                click.echo(format_task(task))
                click.echo()
    
    except HTTPStatusError as e:
        error_data = e.response.json() if e.response.content else {}
        click.echo(f"Error {e.response.status_code}: {error_data.get('detail', 'Unknown error')}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--title', required=True, help='Task title')
@click.option('--type', 'task_type', required=True,
              type=click.Choice(['concrete', 'abstract', 'epic']),
              help='Task type')
@click.option('--instruction', 'task_instruction', required=True,
              help='Task instruction')
@click.option('--verification', 'verification_instruction', required=True,
              help='Verification instruction')
@click.option('--agent-id', 'agent_id', required=True, help='Agent ID')
@click.option('--project-id', 'project_id', type=int, help='Project ID')
@click.option('--priority', type=click.Choice(['low', 'medium', 'high', 'critical']),
              default='medium', help='Priority (default: medium)')
@click.option('--notes', help='Optional notes')
@click.option('--estimated-hours', 'estimated_hours', type=float, help='Estimated hours')
@click.pass_context
def create(ctx, title, task_type, task_instruction, verification_instruction,
           agent_id, project_id, priority, notes, estimated_hours):
    """Create a new task."""
    data = {
        'title': title,
        'task_type': task_type,
        'task_instruction': task_instruction,
        'verification_instruction': verification_instruction,
        'agent_id': agent_id,
        'priority': priority,
    }
    
    if project_id:
        data['project_id'] = project_id
    if notes:
        data['notes'] = notes
    if estimated_hours:
        data['estimated_hours'] = estimated_hours
    
    try:
        response = make_request(
            'POST',
            '/tasks',
            api_key=ctx.obj['api_key'],
            base_url=ctx.obj['url'],
            json=data
        )
        response.raise_for_status()
        task = response.json()
        click.echo(f"Task created successfully!")
        click.echo(format_task(task))
    
    except HTTPStatusError as e:
        error_data = e.response.json() if e.response.content else {}
        click.echo(f"Error {e.response.status_code}: {error_data.get('detail', 'Unknown error')}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--task-id', 'task_id', required=True, type=int, help='Task ID')
@click.option('--agent-id', 'agent_id', required=True, help='Agent ID')
@click.option('--notes', help='Completion notes')
@click.option('--actual-hours', 'actual_hours', type=float, help='Actual hours spent')
@click.pass_context
def complete(ctx, task_id, agent_id, notes, actual_hours):
    """Complete a task."""
    data = {'agent_id': agent_id}
    if notes:
        data['notes'] = notes
    if actual_hours:
        data['actual_hours'] = actual_hours
    
    try:
        response = make_request(
            'POST',
            f'/tasks/{task_id}/complete',
            api_key=ctx.obj['api_key'],
            base_url=ctx.obj['url'],
            json=data
        )
        response.raise_for_status()
        result = response.json()
        click.echo(f"Task {task_id} completed successfully!")
        if notes:
            click.echo(f"Notes: {notes}")
    
    except HTTPStatusError as e:
        error_data = e.response.json() if e.response.content else {}
        click.echo(f"Error {e.response.status_code}: {error_data.get('detail', 'Unknown error')}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--task-id', 'task_id', required=True, type=int, help='Task ID')
@click.option('--format', 'output_format', type=click.Choice(['table', 'json']),
              default='table', help='Output format')
@click.pass_context
def show(ctx, task_id, output_format):
    """Show task details."""
    try:
        response = make_request(
            'GET',
            f'/tasks/{task_id}',
            api_key=ctx.obj['api_key'],
            base_url=ctx.obj['url']
        )
        response.raise_for_status()
        task = response.json()
        
        if output_format == 'json':
            click.echo(format_json(task))
        else:
            click.echo(format_task(task))
            if task.get('notes'):
                click.echo(f"\nNotes: {task['notes']}")
            if task.get('task_instruction'):
                click.echo(f"\nFull Instruction:\n{task['task_instruction']}")
            if task.get('verification_instruction'):
                click.echo(f"\nVerification:\n{task['verification_instruction']}")
    
    except HTTPStatusError as e:
        error_data = e.response.json() if e.response.content else {}
        click.echo(f"Error {e.response.status_code}: {error_data.get('detail', 'Unknown error')}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--task-id', 'task_id', required=True, type=int, help='Task ID')
@click.option('--agent-id', 'agent_id', required=True, help='Agent ID')
@click.pass_context
def reserve(ctx, task_id, agent_id):
    """Reserve (lock) a task for an agent."""
    data = {'agent_id': agent_id}
    
    try:
        response = make_request(
            'POST',
            f'/tasks/{task_id}/lock',
            api_key=ctx.obj['api_key'],
            base_url=ctx.obj['url'],
            json=data
        )
        response.raise_for_status()
        result = response.json()
        click.echo(f"Task {task_id} reserved for {agent_id}")
    
    except HTTPStatusError as e:
        error_data = e.response.json() if e.response.content else {}
        click.echo(f"Error {e.response.status_code}: {error_data.get('detail', 'Unknown error')}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--task-id', 'task_id', required=True, type=int, help='Task ID')
@click.option('--agent-id', 'agent_id', required=True, help='Agent ID')
@click.pass_context
def unlock(ctx, task_id, agent_id):
    """Unlock (release) a reserved task."""
    data = {'agent_id': agent_id}
    
    try:
        response = make_request(
            'POST',
            f'/tasks/{task_id}/unlock',
            api_key=ctx.obj['api_key'],
            base_url=ctx.obj['url'],
            json=data
        )
        response.raise_for_status()
        result = response.json()
        click.echo(f"Task {task_id} unlocked")
    
    except HTTPStatusError as e:
        error_data = e.response.json() if e.response.content else {}
        click.echo(f"Error {e.response.status_code}: {error_data.get('detail', 'Unknown error')}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--user-id', 'user_id', required=True, help='User ID')
@click.option('--chat-id', 'chat_id', required=True, help='Chat ID')
@click.option('--format', 'export_format', default='json', type=click.Choice(['json', 'txt', 'pdf']), help='Export format')
@click.option('--output', 'output_file', type=click.Path(), help='Output file path (optional, defaults to stdout for json/txt)')
@click.option('--start-date', 'start_date', help='Start date for filtering messages (ISO format)')
@click.option('--end-date', 'end_date', help='End date for filtering messages (ISO format)')
@click.pass_context
def export_conversation(ctx, user_id, chat_id, export_format, output_file, start_date, end_date):
    """Export conversation to JSON, TXT, or PDF format."""
    params = {'format': export_format}
    if start_date:
        params['start_date'] = start_date
    if end_date:
        params['end_date'] = end_date
    
    try:
        response = make_request(
            'GET',
            f'/conversations/{user_id}/{chat_id}/export',
            api_key=ctx.obj['api_key'],
            base_url=ctx.obj['url'],
            params=params
        )
        response.raise_for_status()
        
        # Determine output destination
        if output_file:
            if export_format == 'pdf':
                with open(output_file, 'wb') as f:
                    f.write(response.content)
                click.echo(f"Conversation exported to {output_file}")
            else:
                with open(output_file, 'w', encoding='utf-8') as f:
                    if export_format == 'json':
                        json.dump(response.json(), f, indent=2)
                    else:
                        f.write(response.text)
                click.echo(f"Conversation exported to {output_file}")
        else:
            # Output to stdout
            if export_format == 'json':
                click.echo(json.dumps(response.json(), indent=2))
            elif export_format == 'pdf':
                click.echo("PDF content received (use --output to save to file)", err=True)
                sys.exit(1)
            else:
                click.echo(response.text)
    
    except HTTPStatusError as e:
        error_data = e.response.json() if e.response.content else {}
        click.echo(f"Error {e.response.status_code}: {error_data.get('detail', 'Unknown error')}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    cli()
