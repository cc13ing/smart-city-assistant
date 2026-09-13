"""轻量 FastMCP 实现（HTTP 工具服务，兼容 tools/mcp_client.py）"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
from typing import Any, Callable, Dict, List, Optional, get_type_hints

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)


class MCPResponse:
    def __init__(self, content: List[Dict[str, Any]] | None = None, is_error: bool = False):
        self.content = content or []
        self.is_error = is_error

    def to_dict(self) -> Dict[str, Any]:
        return {"content": self.content, "isError": self.is_error}


def text_response(text: str) -> MCPResponse:
    return MCPResponse(content=[{"type": "text", "text": text}])


def error_response(message: str) -> MCPResponse:
    return MCPResponse(content=[{"type": "text", "text": message}], is_error=True)


def _format_response(result: Any) -> MCPResponse:
    if isinstance(result, MCPResponse):
        return result
    if isinstance(result, dict) and "content" in result:
        return MCPResponse(content=result["content"], is_error=result.get("isError", False))
    if isinstance(result, str):
        return text_response(result)
    if isinstance(result, list) and all(isinstance(item, str) for item in result):
        return MCPResponse(content=[{"type": "text", "text": item} for item in result])
    try:
        return text_response(json.dumps(result, ensure_ascii=False))
    except Exception:
        return text_response(str(result))


class ToolDefinition:
    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        handler: Callable[..., Any],
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.handler = handler

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class FastMCP:
    def __init__(
        self,
        name: str,
        version: str = "1.0.0",
        description: str = "",
        dependencies: List[str] | None = None,
    ):
        self.name = name
        self.version = version
        self.description = description or f"{name} MCP Server"
        self.dependencies = dependencies or []
        self.tools: Dict[str, ToolDefinition] = {}
        self.metadata = {
            "name": name,
            "version": version,
            "description": self.description,
            "capabilities": ["tools"],
        }

    def tool(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            tool_name = name or func.__name__
            tool_description = description or (func.__doc__ or "").strip()
            sig = inspect.signature(func)
            type_hints = get_type_hints(func)
            parameters: Dict[str, Any] = {"type": "object", "properties": {}, "required": []}

            for param_name, param in sig.parameters.items():
                if param_name in ("self", "cls"):
                    continue
                param_type = type_hints.get(param_name, str)
                if param_type is str:
                    json_type = "string"
                elif param_type is int:
                    json_type = "integer"
                elif param_type is float:
                    json_type = "number"
                elif param_type is bool:
                    json_type = "boolean"
                else:
                    json_type = "string"
                parameters["properties"][param_name] = {"type": json_type, "description": ""}
                if param.default is inspect.Parameter.empty:
                    parameters["required"].append(param_name)

            self.tools[tool_name] = ToolDefinition(
                name=tool_name,
                description=tool_description,
                parameters=parameters,
                handler=func,
            )
            return func

        return decorator

    async def call_tool(self, tool_name: str, params: Dict[str, Any]) -> MCPResponse:
        if tool_name not in self.tools:
            raise ValueError(f"Tool not found: {tool_name}")
        tool = self.tools[tool_name]
        try:
            if asyncio.iscoroutinefunction(tool.handler):
                result = await tool.handler(**params)
            else:
                result = tool.handler(**params)
            return _format_response(result)
        except Exception as e:
            logger.error("Error calling tool %s: %s", tool_name, e)
            return error_response(f"Error calling tool {tool_name}: {e}")

    def get_tools(self) -> List[Dict[str, Any]]:
        return [tool.to_dict() for tool in self.tools.values()]

    def get_metadata(self) -> Dict[str, Any]:
        return self.metadata.copy()


def create_fastapi_app(mcp_server: FastMCP) -> FastAPI:
    app = FastAPI(
        title=mcp_server.name,
        description=mcp_server.description,
        version=mcp_server.version,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health_check():
        return {"status": "healthy"}

    @app.get("/metadata")
    async def get_metadata():
        return mcp_server.get_metadata()

    @app.get("/tools")
    async def list_tools():
        return mcp_server.get_tools()

    @app.post("/tools/{tool_name}")
    async def call_tool(tool_name: str, request: Request):
        try:
            params = await request.json()
        except json.JSONDecodeError:
            params = {}
        if not isinstance(params, dict):
            params = {}
        try:
            response = await mcp_server.call_tool(tool_name, params)
            return response.to_dict()
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except Exception as e:
            logger.error("Error calling tool %s: %s", tool_name, e)
            return error_response(f"Error calling tool {tool_name}: {e}").to_dict()

    return app
