"""
Setup script for TODO MCP Service CLI.
"""
from setuptools import setup, find_packages

setup(
    name="todo-mcp-service",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "click>=8.1.0",
        "httpx>=0.25.0",
    ],
    entry_points={
        "console_scripts": [
            "todo=src.cli:cli",
        ],
    },
    python_requires=">=3.8",
)
