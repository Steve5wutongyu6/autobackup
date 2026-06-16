"""Repositories for COS credentials and buckets."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import CosBucket, CosCredential


class CosRepository:
    """Data access helper for COS configuration tables."""

    def __init__(self, session: Session) -> None:
        """
        Bind the repository to a database session.

        Args:
            session: Active SQLAlchemy session.
        """

        self.session = session

    def create_credential(self, credential: CosCredential) -> CosCredential:
        """
        Persist a COS access credential.

        Args:
            credential: New credential entity.

        Returns:
            Saved credential entity.
        """

        self.session.add(credential)
        self.session.flush()
        self.session.refresh(credential)
        return credential

    def list_credentials(self) -> list[CosCredential]:
        """
        List all COS credentials.

        Returns:
            Stored credentials ordered by creation time.
        """

        statement = select(CosCredential).order_by(CosCredential.created_at.desc())
        return list(self.session.scalars(statement))

    def get_credential(self, credential_id: int) -> CosCredential | None:
        """
        Fetch a COS credential by primary key.

        Args:
            credential_id: Credential primary key.

        Returns:
            Matching credential or None.
        """

        return self.session.get(CosCredential, credential_id)

    def save_bucket(self, bucket: CosBucket) -> CosBucket:
        """
        Persist a COS bucket definition.

        Args:
            bucket: Bucket entity to persist.

        Returns:
            Saved bucket entity.
        """

        self.session.add(bucket)
        self.session.flush()
        self.session.refresh(bucket)
        return bucket

    def list_buckets(self) -> list[CosBucket]:
        """
        List all configured buckets.

        Returns:
            Buckets ordered by creation time.
        """

        statement = select(CosBucket).order_by(CosBucket.created_at.desc())
        return list(self.session.scalars(statement))

    def get_bucket(self, bucket_id: int) -> CosBucket | None:
        """
        Fetch a bucket by primary key.

        Args:
            bucket_id: Bucket primary key.

        Returns:
            Matching bucket or None.
        """

        return self.session.get(CosBucket, bucket_id)

    def delete_bucket(self, bucket: CosBucket) -> None:
        """
        Delete a stored bucket definition.

        Args:
            bucket: Bucket entity to delete.

        Returns:
            None. The row is removed from the current session.
        """

        self.session.delete(bucket)

