"""Tencent COS configuration schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CosCredentialCreateRequest(BaseModel):
    """
    Request to create a COS access credential.

    Attributes:
        name: Friendly name for the credential.
        secret_id: Tencent Cloud SecretId.
        secret_key: Tencent Cloud SecretKey.
        session_token: Optional temporary token.
        description: Optional operator note.
    """

    name: str = Field(min_length=1, max_length=255)
    secret_id: str = Field(min_length=1, max_length=255)
    secret_key: str = Field(min_length=1, max_length=255)
    session_token: str | None = None
    description: str | None = None


class CosCredentialResponse(BaseModel):
    """
    Redacted COS credential summary for listing views.

    Attributes:
        id: Credential primary key.
        name: Friendly name.
        description: Optional operator note.
        enabled: Whether the credential is active.
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
    """

    id: int
    name: str
    description: str | None = None
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CosBucketCreateRequest(BaseModel):
    """
    Request to create or update a COS bucket definition.

    Attributes:
        credential_id: Linked credential primary key.
        name: Bucket name without AppID suffix.
        app_id: Tencent Cloud AppID.
        region: COS region identifier.
        endpoint_mode: Domain selection mode.
        custom_endpoint: Optional custom endpoint or domain.
        use_https: Whether to use HTTPS when calling COS.
        user_expected_private_route: Whether the operator expects private networking.
    """

    credential_id: int
    name: str = Field(min_length=1, max_length=255)
    app_id: str = Field(min_length=1, max_length=64)
    region: str = Field(min_length=1, max_length=64)
    endpoint_mode: str = Field(default="default", min_length=1, max_length=64)
    custom_endpoint: str | None = Field(default=None, max_length=255)
    use_https: bool = True
    user_expected_private_route: bool = False


class CosBucketResponse(BaseModel):
    """
    COS bucket summary returned to the UI.

    Attributes:
        id: Bucket primary key.
        credential_id: Linked credential primary key.
        name: Bucket name.
        app_id: AppID suffix.
        region: COS region.
        endpoint_mode: Routing endpoint mode.
        custom_endpoint: Custom endpoint if configured.
        use_https: HTTPS flag.
        user_expected_private_route: Operator expectation for private networking.
        last_nslookup_ip: Last resolved address.
        last_nslookup_private: Whether the last resolved address was private.
        last_connectivity_check_at: Last health-check time.
        status: Connectivity and validation status.
        created_at: Creation timestamp.
        updated_at: Update timestamp.
    """

    id: int
    credential_id: int
    name: str
    app_id: str
    region: str
    endpoint_mode: str
    custom_endpoint: str | None
    use_https: bool
    user_expected_private_route: bool
    last_nslookup_ip: str | None
    last_nslookup_private: bool | None
    last_connectivity_check_at: datetime | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BucketConnectivityResponse(BaseModel):
    """
    Immediate bucket connectivity test result.

    Attributes:
        bucket_id: Tested bucket primary key.
        resolved_ip: DNS result selected for evaluation.
        private_route: Whether the route is treated as private.
        status: Overall connectivity outcome.
        detail: Additional operator-facing context.
    """

    bucket_id: int
    resolved_ip: str | None = None
    private_route: bool | None = None
    status: str
    detail: str

    model_config = ConfigDict(from_attributes=True)
