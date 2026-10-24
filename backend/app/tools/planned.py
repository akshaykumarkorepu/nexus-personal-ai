"""Tools that are designed but NOT implemented yet.

They are registered (so the UI can show the roadmap and their permission level)
but have no handler, so the registry never offers them to the model and refuses
any call to them. Each one requires explicit user approval once implemented.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .registry import PermissionLevel, Tool


class RunCommandInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: str = Field(
        ...,
        description="ID of a pre-approved command (e.g. 'npm-test'). Never free-form shell.",
        pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$",
    )
    project: str = Field(..., description="Approved project directory to run it in.")


class BrowserInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["open", "read", "click", "fill", "submit"]
    url: str | None = Field(None, max_length=2048)
    selector: str | None = Field(None, max_length=500)
    value: str | None = Field(None, max_length=2000)


class WriteFileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(..., max_length=4096)
    content: str


PLANNED_TOOLS = [
    Tool(
        name="run_dev_command",
        description=(
            "Run one command from an allowlist of development commands (tests, lint, build) "
            "in an approved project, with a timeout and output cap. Requires approval."
        ),
        input_model=RunCommandInput,
        permission=PermissionLevel.EXECUTE,
        category="projects",
    ),
    Tool(
        name="browser",
        description="Drive a Playwright browser session. Form submission requires approval.",
        input_model=BrowserInput,
        permission=PermissionLevel.EXTERNAL,
        category="browser",
    ),
    Tool(
        name="write_file",
        description="Create or modify a file in an approved directory. Requires approval.",
        input_model=WriteFileInput,
        permission=PermissionLevel.WRITE,
        category="files",
    ),
]
