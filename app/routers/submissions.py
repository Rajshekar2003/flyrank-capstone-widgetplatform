"""HTTP layer for the public submission endpoint."""
from fastapi import APIRouter, BackgroundTasks, Request

from app.db import connection
from app.services import submissions as service
from app.services.abuse import IP_LIMITER, get_client_ip, too_many_requests

router = APIRouter()


@router.post("/submissions", status_code=201)
async def create_submission(request: Request, background_tasks: BackgroundTasks):
    client_ip = get_client_ip(request)
    retry = IP_LIMITER.check(client_ip)
    if retry > 0:
        too_many_requests(retry, "per-IP")
    service.check_declared_size(request.headers.get("content-length"))
    raw = await request.body()
    service.check_size(raw)
    data = service.parse_body(raw)
    with connection() as conn:
        return await service.create(conn, data, client_ip, background_tasks.add_task)
