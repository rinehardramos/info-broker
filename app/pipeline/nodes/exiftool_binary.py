"""ExifTool binary node — full EXIF extraction via Docker-sandboxed exiftool binary."""

from app.pipeline.nodes.docker_tool import DockerToolNode


class ExifToolBinaryNode(DockerToolNode):
    node_type = "exiftool_binary"
    display_name = "ExifTool (Binary)"
    category = "enrich"
    docker_image = "info-broker/exiftool:latest"
    docker_command_template = "exiftool -json {input_file}"
    output_format = "json"
    timeout_seconds = 30
    network_enabled = False
    memory_limit = "256m"
    _REASON = "Full EXIF/metadata extraction via exiftool binary — more complete than Python PIL"

    config_schema = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "title": "File Path",
                "description": "Path to image or document file to extract metadata from",
            },
        },
        "required": [],
    }
