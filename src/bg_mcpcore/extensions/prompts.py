"""Register operator-defined prompts from the extensions catalogue.

Each prompt becomes a FastMCP prompt whose body is
``string.Template(...).substitute(**kwargs)``. The function signature is
synthesised at registration time so FastMCP can introspect arguments (no
``exec()``). Ported verbatim from bg-shlink-mcp (neutral logger).
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from string import Template
from typing import TYPE_CHECKING, Any

from ..observability import get_logger
from .config import PromptConfig, python_annotation_for

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = get_logger("bg-mcpcore.extensions.prompts")


def register_prompts(mcp: FastMCP, prompts: list[PromptConfig]) -> int:
    """Register every prompt; one bad entry is logged + skipped, not fatal."""
    registered = 0
    for cfg in prompts:
        try:
            fn = _build_prompt_function(cfg)
            mcp.prompt(
                name=cfg.name,
                title=cfg.title,
                description=cfg.description or None,
                tags=set(cfg.tags) if cfg.tags else None,
            )(fn)
            registered += 1
            logger.info("extensions.prompt_registered", name=cfg.name)
        except Exception as exc:
            logger.error("extensions.prompt_registration_failed", name=cfg.name, error=str(exc))
    return registered


def _build_prompt_function(cfg: PromptConfig) -> Callable[..., str]:
    template = Template(cfg.template)

    def _runner(**kwargs: Any) -> str:
        return template.substitute({k: str(v) for k, v in kwargs.items()})

    _runner.__name__ = cfg.name
    _runner.__doc__ = cfg.description or None

    parameters: list[inspect.Parameter] = []
    annotations: dict[str, Any] = {}
    for arg in cfg.arguments:
        annotation = python_annotation_for(arg)
        default: Any = inspect.Parameter.empty
        if arg.default is not None:
            default = arg.default
        elif not arg.required:
            default = annotation()
        parameters.append(
            inspect.Parameter(
                name=arg.name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=default,
                annotation=annotation,
            )
        )
        annotations[arg.name] = annotation

    _runner.__signature__ = inspect.Signature(parameters=parameters, return_annotation=str)  # type: ignore[attr-defined]
    _runner.__annotations__ = {**annotations, "return": str}
    return _runner


__all__ = ["register_prompts"]
