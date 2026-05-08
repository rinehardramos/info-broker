"""Tests for Docker tool node framework."""
from __future__ import annotations
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

from app.pipeline.nodes.docker_tool import DockerToolNode, _docker_available, _image_exists
from app.pipeline.nodes.exiftool_binary import ExifToolBinaryNode
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")


def _arun(coro):
    return asyncio.run(coro)


# --- DockerToolNode base tests ---

def test_docker_tool_node_interface():
    """DockerToolNode has the PipelineNode interface."""
    node = DockerToolNode()
    assert hasattr(node, "node_type")
    assert hasattr(node, "execute")
    assert hasattr(node, "config_schema")


def test_build_args_from_config():
    node = DockerToolNode()
    node.docker_command_template = "mytool --target {input}"
    args = node._build_args({"input": "example.com"}, [])
    assert "example.com" in args


def test_build_args_from_inputs():
    node = DockerToolNode()
    node.docker_command_template = "mytool {target}"
    args = node._build_args({}, [{"target": "10.0.0.1"}])
    assert "10.0.0.1" in args


def test_parse_output_json():
    node = DockerToolNode()
    node.output_format = "json"
    result = node._parse_output('[{"key": "value"}]')
    assert result == [{"key": "value"}]


def test_parse_output_text():
    node = DockerToolNode()
    node.output_format = "text"
    result = node._parse_output("hello world")
    assert result == [{"output": "hello world"}]


def test_parse_output_lines():
    node = DockerToolNode()
    node.output_format = "lines"
    result = node._parse_output("line1\nline2\nline3")
    assert len(result) == 3
    assert result[0]["line"] == "line1"


def test_parse_output_invalid_json():
    node = DockerToolNode()
    node.output_format = "json"
    result = node._parse_output("not valid json {")
    assert result[0].get("parse_error")


def test_execute_no_docker():
    with patch("app.pipeline.nodes.docker_tool._docker_available", return_value=False):
        node = DockerToolNode()
        node.node_type = "test_tool"
        results = _arun(node.execute({"input": "test"}, [], CTX))
    assert results[0]["error"] == "Docker not available"


def test_execute_no_image():
    with (
        patch("app.pipeline.nodes.docker_tool._docker_available", return_value=True),
        patch("app.pipeline.nodes.docker_tool._image_exists", return_value=False),
    ):
        node = DockerToolNode()
        node.node_type = "test_tool"
        node.docker_image = "nonexistent:latest"
        results = _arun(node.execute({"input": "test"}, [], CTX))
    assert "not found" in results[0]["error"]


def test_execute_no_input():
    node = DockerToolNode()
    node.node_type = "test_tool"
    results = _arun(node.execute({}, [], CTX))
    assert results[0].get("error")


# --- ExifToolBinaryNode tests ---

def test_exiftool_binary_metadata():
    node = ExifToolBinaryNode()
    assert node.node_type == "exiftool_binary"
    assert node.category == "enrich"
    assert node.docker_image == "info-broker/exiftool:latest"
    assert node.output_format == "json"


def test_exiftool_binary_command():
    node = ExifToolBinaryNode()
    args = node._build_args({"input": "/tmp/photo.jpg"}, [])
    assert "exiftool" in args
    assert "/tmp/photo.jpg" in args
