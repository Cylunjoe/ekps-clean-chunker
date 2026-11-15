from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.chunker import clean_chunk, parent_child


class CleanChunkParentChildTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        r = clean_chunk(
            tool_parameters.get("input_text") or "",
            max_length=max(100, int(tool_parameters.get("max_length") or 500)),
            title=tool_parameters.get("title") or "",
            header=tool_parameters.get("context_header", True) is not False,
        )
        yield self.create_variable_message("result", parent_child(r))
