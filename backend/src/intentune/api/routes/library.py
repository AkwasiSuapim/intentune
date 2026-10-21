"""The managed library: sources, scans, tracks, and analysis jobs (B8).

Import and Rescan run the scan in the request (on FastAPI's thread pool) and
answer with its report. Scans never overlap: one asked for while another runs
(the startup scan, say) is refused with CONFLICT.
"""

from typing import Literal, Optional

from fastapi import APIRouter, Response

from src.intentune.api import views
from src.intentune.api.dependencies import DEFAULT_LIMIT, ERROR_RESPONSES, ContainerDep, Limit, Offset
from src.intentune.api.schemas import (
    ImportIn,
    JobPageOut,
    RegisterSourceIn,
    ScanReportOut,
    ScanReportsOut,
    SourceListOut,
    SourceOut,
    TrackPageOut,
)
from src.intentune.domain.analysis import AnalysisJobStatus

router = APIRouter(prefix="/api/v1/library", tags=["library"], responses=ERROR_RESPONSES)

JobStatusName = Literal["pending", "running", "succeeded", "failed", "skipped"]


@router.get("/tracks", response_model=TrackPageOut)
def list_tracks(container: ContainerDep, limit: Limit = DEFAULT_LIMIT, offset: Offset = 0) -> TrackPageOut:
    return TrackPageOut(**views.page(container.library().list_tracks(), limit, offset, views.track_out))


@router.post("/sources", response_model=SourceOut, status_code=201)
def register_source(body: RegisterSourceIn, response: Response, container: ContainerDep) -> SourceOut:
    """Register a folder (201). A folder already registered is returned as it is (200). Registering does not scan."""
    library = container.library()
    known = {source.source_id for source in library.list_sources()}
    source = library.register_source(body.path)
    if source.source_id in known:
        response.status_code = 200
    return views.source_out(source)


@router.get("/sources", response_model=SourceListOut)
def list_sources(container: ContainerDep) -> SourceListOut:
    sources = container.library().list_sources()
    return SourceListOut(items=[views.source_out(source) for source in sources], scanning=container.scans.is_scanning)


@router.post("/import", response_model=ScanReportOut)
def import_source(body: ImportIn, container: ContainerDep) -> ScanReportOut:
    """Scan one source and import what is new or changed."""
    return views.scan_report_out(container.scans.scan_source(body.source_id))


@router.post("/rescan", response_model=ScanReportsOut)
def rescan_library(container: ContainerDep) -> ScanReportsOut:
    """Scan every source (Rescan Library)."""
    return ScanReportsOut(reports=[views.scan_report_out(report) for report in container.scans.rescan_library()])


@router.get("/jobs", response_model=JobPageOut)
def list_jobs(
    container: ContainerDep,
    status: Optional[JobStatusName] = None,
    limit: Limit = DEFAULT_LIMIT,
    offset: Offset = 0,
) -> JobPageOut:
    """Analysis jobs, oldest first, optionally only those with one status."""
    jobs = container.analysis().list_jobs(AnalysisJobStatus(status.upper()) if status is not None else None)
    return JobPageOut(**views.page(jobs, limit, offset, views.job_out))
