"""
Setup script for TODO MCP Service CLI.
"""
from setuptools import setup, find_packages

setup(
    name="todorama",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "click>=8.1.0",
        "httpx>=0.25.0",
    ],
    entry_points={
        "console_scripts": [
            "todorama=todorama.__main__:main",
            "todo=todorama.cli:cli",  # Backward compatibility
        ],
    },
    python_requires=">=3.11",
)
