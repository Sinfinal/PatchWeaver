"""环境诊断接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from patchweaver.api.deps import ApiContext, get_api_context
from patchweaver.api.services.doctor_service import DoctorApiService

router = APIRouter(tags=["doctor"])


@router.get("/doctor")
def get_doctor(context: ApiContext = Depends(get_api_context)) -> dict:
    """读取最近一次诊断结果。"""

    return DoctorApiService(context).get_report(refresh=False)


@router.post("/doctor/run")
def run_doctor(context: ApiContext = Depends(get_api_context)) -> dict:
    """重新执行一次诊断。"""

    return DoctorApiService(context).get_report(refresh=True)
