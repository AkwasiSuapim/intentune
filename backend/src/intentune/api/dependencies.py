"""What routes ask FastAPI for (B8): the container, and the paging query parameters."""

from typing import Annotated, Any, Dict

from fastapi import Depends, Query, Request

from src.intentune.api.container import Container
from src.intentune.api.schemas import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, ErrorOut


def get_container(request: Request) -> Container:
    return request.app.state.container


ContainerDep = Annotated[Container, Depends(get_container)]
Limit = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]  # page size: 1 to 500
Offset = Annotated[int, Query(ge=0)]

DEFAULT_LIMIT = DEFAULT_PAGE_SIZE  # 100

# Every route may answer with the error envelope; documented once as the OpenAPI default response.
ERROR_RESPONSES: Dict[Any, Dict[str, Any]] = {"default": {"model": ErrorOut, "description": "An error (spec §26 envelope)"}}
