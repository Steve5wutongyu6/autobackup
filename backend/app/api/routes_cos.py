"""COS credential and bucket management routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.schemas.common import ApiMessage
from app.schemas.cos import BucketConnectivityResponse, CosBucketCreateRequest, CosBucketResponse
from app.schemas.cos import CosCredentialCreateRequest, CosCredentialResponse
from app.services.cos_service import CosService


router = APIRouter(prefix="/api/cos", tags=["cos"])


@router.post("/credentials", response_model=CosCredentialResponse)
def create_credential(
    payload: CosCredentialCreateRequest,
    _: int = Depends(require_admin),
    session: Session = Depends(get_db),
) -> CosCredentialResponse:
    """
    Create a new encrypted COS credential.

    Args:
        payload: COS credential creation payload.
        _: Authenticated administrator ID.
        session: Active SQLAlchemy session.

    Returns:
        Redacted stored credential response.
    """

    credential = CosService(session).create_credential(
        payload.name,
        payload.secret_id,
        payload.secret_key,
        payload.session_token,
        payload.description,
    )
    return CosCredentialResponse.model_validate(credential)


@router.get("/credentials", response_model=list[CosCredentialResponse])
def list_credentials(_: int = Depends(require_admin), session: Session = Depends(get_db)) -> list[CosCredentialResponse]:
    """
    List stored COS credentials.

    Args:
        _: Authenticated administrator ID.
        session: Active SQLAlchemy session.

    Returns:
        Credential summary list.
    """

    return [CosCredentialResponse.model_validate(item) for item in CosService(session).list_credentials()]


@router.post("/buckets", response_model=CosBucketResponse)
def create_bucket(
    payload: CosBucketCreateRequest,
    _: int = Depends(require_admin),
    session: Session = Depends(get_db),
) -> CosBucketResponse:
    """
    Create a new COS bucket definition.

    Args:
        payload: Bucket creation payload.
        _: Authenticated administrator ID.
        session: Active SQLAlchemy session.

    Returns:
        Stored bucket response.
    """

    try:
        bucket = CosService(session).create_or_update_bucket(None, payload.model_dump())
        return CosBucketResponse.model_validate(bucket)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/buckets", response_model=list[CosBucketResponse])
def list_buckets(_: int = Depends(require_admin), session: Session = Depends(get_db)) -> list[CosBucketResponse]:
    """
    List configured COS buckets.

    Args:
        _: Authenticated administrator ID.
        session: Active SQLAlchemy session.

    Returns:
        Bucket summary list.
    """

    return [CosBucketResponse.model_validate(item) for item in CosService(session).list_buckets()]


@router.put("/buckets/{bucket_id}", response_model=CosBucketResponse)
def update_bucket(
    bucket_id: int,
    payload: CosBucketCreateRequest,
    _: int = Depends(require_admin),
    session: Session = Depends(get_db),
) -> CosBucketResponse:
    """
    Update an existing COS bucket definition.

    Args:
        bucket_id: Bucket primary key.
        payload: Bucket update payload.
        _: Authenticated administrator ID.
        session: Active SQLAlchemy session.

    Returns:
        Updated bucket response.
    """

    try:
        bucket = CosService(session).create_or_update_bucket(bucket_id, payload.model_dump())
        return CosBucketResponse.model_validate(bucket)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/buckets/{bucket_id}/check", response_model=BucketConnectivityResponse)
def check_bucket(
    bucket_id: int,
    _: int = Depends(require_admin),
    session: Session = Depends(get_db),
) -> BucketConnectivityResponse:
    """
    Run a private-route and credential health check for a bucket.

    Args:
        bucket_id: Bucket primary key.
        _: Authenticated administrator ID.
        session: Active SQLAlchemy session.

    Returns:
        Connectivity result.
    """

    try:
        return BucketConnectivityResponse(**CosService(session).check_bucket_connectivity(bucket_id))
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.delete("/buckets/{bucket_id}", response_model=ApiMessage)
def delete_bucket(
    bucket_id: int,
    _: int = Depends(require_admin),
    session: Session = Depends(get_db),
) -> ApiMessage:
    """
    Delete a COS bucket definition.

    Args:
        bucket_id: Bucket primary key.
        _: Authenticated administrator ID.
        session: Active SQLAlchemy session.

    Returns:
        Success message.
    """

    try:
        CosService(session).delete_bucket(bucket_id)
        return ApiMessage(message="Bucket deleted")
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

