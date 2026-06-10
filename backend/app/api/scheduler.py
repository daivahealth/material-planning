from fastapi import APIRouter, Depends, HTTPException
from app.models.user import User
from app.scheduler import get_scheduler_status, run_job_now, run_all_jobs_now
from app.services.auth import get_current_user, require_master

router = APIRouter(
    prefix="/api/scheduler",
    tags=["Scheduler"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/status")
def scheduler_status():
    return {"jobs": get_scheduler_status()}


@router.post("/run-now/{job_id}")
def trigger_job_now(job_id: str, _: User = Depends(require_master)):
    found = run_job_now(job_id)
    if not found:
        raise HTTPException(404, f"Job '{job_id}' not found")
    return {"triggered": job_id}


@router.post("/run-all")
def trigger_all_jobs(_: User = Depends(require_master)):
    count = run_all_jobs_now()
    return {"triggered": count}
