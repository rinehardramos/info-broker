
class AutoTestNode:
    node_type = "auto_test_node"
    display_name = "Auto Test"
    category = "source"
    config_schema = {"type": "object", "properties": {}}

    async def execute(self, config, inputs, context):
        return [{"source": "auto_test_node"}]
