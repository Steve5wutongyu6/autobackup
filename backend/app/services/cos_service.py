"""Tencent COS configuration, connectivity, and transfer helpers."""

from __future__ import annotations

from datetime import UTC, datetime
import socket
import subprocess

from qcloud_cos import CosConfig, CosS3Client
from sqlalchemy.orm import Session

from app.core.security import decrypt_text, encrypt_text, is_private_ip
from app.models.entities import ArtifactReplica, CosBucket, CosCredential
from app.repositories.cos import CosRepository
from app.services.log_service import LogService


class CosService:
    """Encapsulate COS credentials, buckets, health checks, and object transfers."""

    def __init__(self, session: Session) -> None:
        """
        Initialize the COS service.

        Args:
            session: Active SQLAlchemy session.
        """

        self.session = session
        self.repository = CosRepository(session)
        self.log_service = LogService(session)

    def _decrypt_credential_secrets(self, credential: CosCredential) -> tuple[str, str, str | None]:
        """
        Decrypt stored credential secrets for COS SDK calls.

        Args:
            credential: Stored COS credential entity.

        Returns:
            Tuple of SecretId, SecretKey, and optional session token.
        """

        secret_id = decrypt_text(
            credential.secret_id_ciphertext,
            credential.secret_id_nonce,
            f"cos_secret_id:{credential.name}",
        )
        secret_key = decrypt_text(
            credential.secret_key_ciphertext,
            credential.secret_key_nonce,
            f"cos_secret_key:{credential.name}",
        )
        token = None
        if credential.session_token_ciphertext and credential.session_token_nonce:
            token = decrypt_text(
                credential.session_token_ciphertext,
                credential.session_token_nonce,
                f"cos_session_token:{credential.name}",
            )
        return secret_id, secret_key, token

    def _build_credential_client(self, credential: CosCredential, region: str = "ap-beijing") -> CosS3Client:
        """
        Build a COS SDK client directly from a stored credential.

        Args:
            credential: Stored COS credential entity.
            region: Region passed to the SDK when the API requires one.

        Returns:
            Configured COS S3 client.
        """

        secret_id, secret_key, token = self._decrypt_credential_secrets(credential)
        config = CosConfig(
            Region=region,
            SecretId=secret_id,
            SecretKey=secret_key,
            Token=token,
            Scheme="https",
        )
        return CosS3Client(config)

    def create_credential(self, name: str, secret_id: str, secret_key: str, session_token: str | None, description: str | None) -> CosCredential:
        """
        Store a COS access credential with encrypted secrets.

        Args:
            name: Friendly credential name.
            secret_id: Tencent Cloud SecretId.
            secret_key: Tencent Cloud SecretKey.
            session_token: Optional temporary session token.
            description: Optional operator note.

        Returns:
            Saved credential entity.
        """

        encrypted_id = encrypt_text(secret_id, f"cos_secret_id:{name}")
        encrypted_key = encrypt_text(secret_key, f"cos_secret_key:{name}")
        token_ciphertext = None
        token_nonce = None
        if session_token:
            encrypted_token = encrypt_text(session_token, f"cos_session_token:{name}")
            token_ciphertext = encrypted_token["ciphertext"]
            token_nonce = encrypted_token["nonce"]

        credential = CosCredential(
            name=name,
            secret_id_ciphertext=encrypted_id["ciphertext"],
            secret_id_nonce=encrypted_id["nonce"],
            secret_key_ciphertext=encrypted_key["ciphertext"],
            secret_key_nonce=encrypted_key["nonce"],
            session_token_ciphertext=token_ciphertext,
            session_token_nonce=token_nonce,
            description=description,
            enabled=True,
        )
        saved_credential = self.repository.create_credential(credential)
        self.log_service.audit(
            action="cos.credential_create",
            actor="admin",
            target_type="cos_credential",
            target_id=str(saved_credential.id),
            outcome="success",
            detail=f"Credential {name} created.",
        )
        return saved_credential

    def list_credentials(self) -> list[CosCredential]:
        """
        Return all stored COS credentials.

        Returns:
            Credential entities.
        """

        return self.repository.list_credentials()

    def delete_credential(self, credential_id: int) -> None:
        """
        Delete a stored COS credential that is no longer used by any bucket.

        Args:
            credential_id: Credential primary key.

        Returns:
            None. The credential row is removed.

        Raises:
            ValueError: Raised when the credential does not exist or is still referenced.
        """

        credential = self.repository.get_credential(credential_id)
        if not credential:
            raise ValueError("COS credential not found")
        if self.repository.credential_has_bucket_refs(credential_id):
            raise ValueError("Credential is still referenced by one or more buckets")

        self.repository.delete_credential(credential)
        self.log_service.audit(
            action="cos.credential_delete",
            actor="admin",
            target_type="cos_credential",
            target_id=str(credential.id),
            outcome="success",
            detail=f"Credential {credential.name} deleted.",
        )

    def create_or_update_bucket(self, bucket_id: int | None, payload: dict[str, object]) -> CosBucket:
        """
        Create or update a COS bucket definition.

        Args:
            bucket_id: Existing bucket primary key or None for new buckets.
            payload: Bucket field dictionary from the API schema.

        Returns:
            Saved bucket entity.

        Raises:
            ValueError: Raised when the referenced credential does not exist.
        """

        credential = self.repository.get_credential(int(payload["credential_id"]))
        if not credential:
            raise ValueError("COS credential not found")

        bucket = self.repository.get_bucket(bucket_id) if bucket_id else None
        if not bucket:
            bucket = CosBucket(credential_id=credential.id, name="", app_id="", region="")

        bucket.credential_id = credential.id
        bucket.name = str(payload["name"])
        bucket.app_id = str(payload["app_id"])
        bucket.region = str(payload["region"])
        bucket.endpoint_mode = str(payload["endpoint_mode"])
        bucket.custom_endpoint = str(payload["custom_endpoint"]) if payload.get("custom_endpoint") else None
        bucket.use_https = bool(payload["use_https"])
        bucket.user_expected_private_route = bool(payload["user_expected_private_route"])
        existing_bucket = self.repository.get_bucket_by_identity(bucket.name, bucket.app_id, bucket.region)
        if existing_bucket and existing_bucket.id != bucket.id:
            raise ValueError("Bucket already exists in local configuration")
        saved_bucket = self.repository.save_bucket(bucket)
        self.log_service.audit(
            action="cos.bucket_save",
            actor="admin",
            target_type="cos_bucket",
            target_id=str(saved_bucket.id),
            outcome="success",
            detail=f"Bucket {saved_bucket.name}-{saved_bucket.app_id} saved.",
        )
        return saved_bucket

    def list_buckets(self) -> list[CosBucket]:
        """
        Return all stored bucket definitions.

        Returns:
            Bucket entities.
        """

        return self.repository.list_buckets()

    def discover_buckets(self, credential_id: int) -> list[dict[str, object]]:
        """
        Load COS buckets from the Tencent Cloud account linked to a credential.

        Args:
            credential_id: Credential primary key used for discovery.

        Returns:
            Discovered bucket summaries sorted with private-route candidates first.

        Raises:
            ValueError: Raised when the credential does not exist.
        """

        credential = self.repository.get_credential(credential_id)
        if not credential:
            raise ValueError("COS credential not found")

        client = self._build_credential_client(credential)
        response = client.list_buckets()
        bucket_items = response.get("Buckets", {}).get("Bucket", [])
        if isinstance(bucket_items, dict):
            bucket_items = [bucket_items]

        discovered_buckets: list[dict[str, object]] = []
        for item in bucket_items:
            full_bucket_name = str(item.get("Name", "")).strip()
            region = str(item.get("Location", "")).strip()
            if not full_bucket_name or not region or "-" not in full_bucket_name:
                continue

            name, app_id = full_bucket_name.rsplit("-", 1)
            resolved_ip, private_route = self._resolve_bucket_route(
                f"{name}-{app_id}.cos.{region}.myqcloud.com",
            )
            existing_bucket = self.repository.get_bucket_by_identity(name, app_id, region)
            discovered_buckets.append(
                {
                    "name": name,
                    "app_id": app_id,
                    "region": region,
                    "bucket": full_bucket_name,
                    "endpoint_mode": "default",
                    "use_https": True,
                    "user_expected_private_route": True,
                    "resolved_ip": resolved_ip,
                    "private_route": private_route,
                    "already_added": existing_bucket is not None,
                    "existing_bucket_id": existing_bucket.id if existing_bucket else None,
                },
            )

        discovered_buckets.sort(
            key=lambda item: (
                not bool(item["private_route"]),
                bool(item["already_added"]),
                str(item["region"]),
                str(item["name"]),
            ),
        )
        return discovered_buckets

    def delete_bucket(self, bucket_id: int) -> None:
        """
        Delete a bucket configuration.

        Args:
            bucket_id: Bucket primary key.

        Returns:
            None. The bucket row is removed.

        Raises:
            ValueError: Raised when the bucket does not exist.
        """

        bucket = self.repository.get_bucket(bucket_id)
        if not bucket:
            raise ValueError("Bucket not found")
        self.repository.delete_bucket(bucket)
        self.log_service.audit(
            action="cos.bucket_delete",
            actor="admin",
            target_type="cos_bucket",
            target_id=str(bucket.id),
            outcome="success",
            detail=f"Bucket {bucket.name}-{bucket.app_id} deleted.",
        )

    def _bucket_host(self, bucket: CosBucket) -> str:
        """
        Compute the COS host used for DNS and SDK access.

        Args:
            bucket: Bucket configuration entity.

        Returns:
            Hostname string for the current endpoint mode.
        """

        if bucket.endpoint_mode == "custom" and bucket.custom_endpoint:
            return bucket.custom_endpoint
        if bucket.endpoint_mode == "accelerate":
            return "cos.accelerate.myqcloud.com"
        if bucket.endpoint_mode == "cdn":
            return bucket.custom_endpoint or "file.myqcloud.com"
        return f"{bucket.name}-{bucket.app_id}.cos.{bucket.region}.myqcloud.com"

    def _resolve_bucket_route(self, host: str) -> tuple[str | None, bool | None]:
        """
        Resolve a COS host and determine whether the address looks private.

        Args:
            host: COS endpoint hostname.

        Returns:
            Tuple of resolved IP and private-route flag. Both may be None when resolution fails.
        """

        resolved_ip = None
        try:
            process = subprocess.run(
                ["nslookup", host],
                check=False,
                capture_output=True,
                text=True,
            )
            for line in process.stdout.splitlines():
                if "Address:" in line:
                    candidate = line.split("Address:", 1)[1].strip()
                    if candidate and "#" not in candidate:
                        resolved_ip = candidate
            if not resolved_ip:
                resolved_ip = socket.gethostbyname(host)
        except Exception:
            try:
                resolved_ip = socket.gethostbyname(host)
            except Exception:
                return None, None

        return resolved_ip, is_private_ip(resolved_ip)

    def _build_client(self, bucket: CosBucket) -> CosS3Client:
        """
        Build a COS SDK client for the provided bucket.

        Args:
            bucket: Bucket configuration entity.

        Returns:
            Configured COS S3 client.
        """

        credential = self.repository.get_credential(bucket.credential_id)
        if not credential:
            raise ValueError("Bucket credential not found")

        secret_id, secret_key, token = self._decrypt_credential_secrets(credential)
        endpoint = self._bucket_host(bucket)
        config = CosConfig(
            Region=None if bucket.endpoint_mode in {"accelerate", "custom", "cdn"} else bucket.region,
            SecretId=secret_id,
            SecretKey=secret_key,
            Token=token,
            Endpoint=endpoint if bucket.endpoint_mode in {"accelerate", "cdn"} else None,
            Domain=endpoint if bucket.endpoint_mode == "custom" else None,
            Scheme="https" if bucket.use_https else "http",
        )
        return CosS3Client(config)

    def check_bucket_connectivity(self, bucket_id: int) -> dict[str, object]:
        """
        Resolve and validate a bucket hostname for private-route awareness.

        Args:
            bucket_id: Bucket primary key.

        Returns:
            Connectivity summary including DNS result and route privacy.

        Raises:
            ValueError: Raised when the bucket does not exist.
        """

        bucket = self.repository.get_bucket(bucket_id)
        if not bucket:
            raise ValueError("Bucket not found")

        host = self._bucket_host(bucket)
        resolved_ip, private_route = self._resolve_bucket_route(host)
        if private_route is None:
            status = "unresolved"
            detail = "Bucket endpoint could not be resolved."
        else:
            status = "private_route" if private_route else "public_route"
            detail = "Bucket resolves to a private address." if private_route else "Bucket resolves to a public address."

        try:
            client = self._build_client(bucket)
            client.head_bucket(Bucket=f"{bucket.name}-{bucket.app_id}")
            if private_route is None:
                status = "available_unresolved"
                detail = "Bucket is reachable, but the endpoint route could not be classified."
            else:
                status = "available_private" if private_route else "available_public"
        except Exception as error:
            status = "unreachable"
            detail = f"Bucket lookup or authentication failed: {error}"

        bucket.last_nslookup_ip = resolved_ip
        bucket.last_nslookup_private = private_route
        bucket.last_connectivity_check_at = datetime.now(UTC)
        bucket.status = status
        self.repository.save_bucket(bucket)
        self.log_service.audit(
            action="cos.bucket_check",
            actor="admin",
            target_type="cos_bucket",
            target_id=str(bucket.id),
            outcome="success" if status != "unreachable" else "failure",
            detail=detail,
        )
        return {
            "bucket_id": bucket.id,
            "resolved_ip": resolved_ip,
            "private_route": private_route,
            "status": status,
            "detail": detail,
        }

    def upload_file(
        self,
        bucket: CosBucket,
        object_key: str,
        file_path: str,
        progress_callback: object | None = None,
    ) -> dict[str, object]:
        """
        Upload a local file into a target bucket.

        Args:
            bucket: Target bucket entity.
            object_key: COS object key.
            file_path: Local file path.
            progress_callback: Optional COS SDK progress callback.

        Returns:
            SDK response dictionary.
        """

        client = self._build_client(bucket)
        return client.upload_file(
            Bucket=f"{bucket.name}-{bucket.app_id}",
            Key=object_key,
            LocalFilePath=file_path,
            MAXThread=1,
            EnableMD5=False,
            progress_callback=progress_callback,
        )

    def delete_object(self, bucket: CosBucket, object_key: str) -> None:
        """
        Delete an object from a configured COS bucket.

        Args:
            bucket: Target bucket entity.
            object_key: COS object key to remove.

        Returns:
            None. The object is deleted from COS.
        """

        client = self._build_client(bucket)
        client.delete_object(Bucket=f"{bucket.name}-{bucket.app_id}", Key=object_key)

    def verify_download_route(self, replica: ArtifactReplica) -> tuple[bool, str | None]:
        """
        Re-check whether a replica's bucket currently resolves to a private route.

        Args:
            replica: Artifact replica to evaluate.

        Returns:
            Tuple of private-route flag and resolved IP string.
        """

        bucket = self.repository.get_bucket(replica.bucket_id)
        if not bucket:
            raise ValueError("Bucket not found")
        result = self.check_bucket_connectivity(bucket.id)
        replica.is_private_route_verified = bool(result["private_route"])
        replica.last_verified_at = datetime.now(UTC)
        self.session.add(replica)
        self.session.flush()
        return bool(result["private_route"]), result["resolved_ip"]

    def download_file(self, replica: ArtifactReplica, destination_path: str) -> None:
        """
        Download an object from COS into a local file path.

        Args:
            replica: Artifact replica to download.
            destination_path: Local target file path.

        Returns:
            None. The file is written to disk.
        """

        bucket = self.repository.get_bucket(replica.bucket_id)
        if not bucket:
            raise ValueError("Bucket not found")
        client = self._build_client(bucket)
        client.download_file(
            Bucket=f"{bucket.name}-{bucket.app_id}",
            Key=replica.object_key,
            DestFilePath=destination_path,
        )
