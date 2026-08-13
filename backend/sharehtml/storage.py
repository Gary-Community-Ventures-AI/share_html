from __future__ import annotations

from pathlib import Path

import boto3
from flask import current_app


class DocumentStorage:
    def ready(self) -> None:
        if current_app.config["STORAGE_BACKEND"] == "s3":
            self._s3().head_bucket(Bucket=current_app.config["S3_BUCKET"])
            return
        Path(current_app.config["LOCAL_STORAGE_PATH"]).resolve().mkdir(parents=True, exist_ok=True)

    def put(self, key: str, content: str) -> None:
        self.put_bytes(key, content.encode("utf-8"), "text/html; charset=utf-8")

    def put_bytes(self, key: str, content: bytes, content_type: str) -> None:
        if current_app.config["STORAGE_BACKEND"] == "s3":
            self._s3().put_object(
                Bucket=current_app.config["S3_BUCKET"],
                Key=key,
                Body=content,
                ContentType=content_type,
            )
            return
        path = self._local_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def get(self, key: str) -> str:
        return self.get_bytes(key).decode("utf-8")

    def get_bytes(self, key: str) -> bytes:
        if current_app.config["STORAGE_BACKEND"] == "s3":
            response = self._s3().get_object(Bucket=current_app.config["S3_BUCKET"], Key=key)
            return response["Body"].read()
        return self._local_path(key).read_bytes()

    def delete(self, key: str) -> None:
        if current_app.config["STORAGE_BACKEND"] == "s3":
            self._s3().delete_object(Bucket=current_app.config["S3_BUCKET"], Key=key)
            return
        self._local_path(key).unlink(missing_ok=True)

    def _local_path(self, key: str) -> Path:
        root = Path(current_app.config["LOCAL_STORAGE_PATH"]).resolve()
        path = (root / key).resolve()
        if root not in path.parents:
            raise ValueError("Invalid storage key")
        return path

    def _s3(self):
        return boto3.client(
            "s3",
            endpoint_url=current_app.config["S3_ENDPOINT"],
            region_name=current_app.config["S3_REGION"],
            aws_access_key_id=current_app.config["S3_ACCESS_KEY_ID"],
            aws_secret_access_key=current_app.config["S3_SECRET_ACCESS_KEY"],
        )


storage = DocumentStorage()
