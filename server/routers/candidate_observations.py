"""Agent endpoint for unmatched candidate observations."""

from fastapi import APIRouter

from server.candidate_observation import CandidateObservationError, persist
from server.db import get_conn
from server.job_service import JobProtocolError, error_data
from server.quota import QuotaExceeded
from server.schemas import ApiOk, CandidateObservationIn
from server.services import get_device_by_key

router = APIRouter(prefix="/api/candidate-observations", tags=["candidate-observations"])


@router.post("")
def upload_candidate_observation(body: CandidateObservationIn):
    with get_conn() as conn:
        cur = conn.cursor()
        device = get_device_by_key(cur, body.device_key)
        if not device:
            return ApiOk(ok=False, message="device not registered", data={"error_code": "DEVICE_REVOKED_OR_UNKNOWN"})
        try:
            result = persist(cur, body=body, device=device)
        except JobProtocolError as exc:
            return ApiOk(ok=False, message=str(exc), data=error_data(exc))
        except (CandidateObservationError, QuotaExceeded) as exc:
            code = getattr(exc, "code", str(exc))
            return ApiOk(ok=False, message=str(exc), data={"error_code": code})
        return ApiOk(message="candidate observation persisted", data=result)
