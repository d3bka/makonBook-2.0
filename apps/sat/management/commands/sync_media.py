import logging
import multiprocessing
import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


LOG_FILE = os.path.join(settings.BASE_DIR, "logs", "sync_media_r2.log")
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


def _s3_client():
    session = boto3.session.Session()
    return session.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
    )


def _is_missing_object(exc: ClientError) -> bool:
    response = getattr(exc, "response", {}) or {}
    error = response.get("Error", {}) or {}
    status = (response.get("ResponseMetadata", {}) or {}).get("HTTPStatusCode")
    code = str(error.get("Code") or "").casefold()
    return status == 404 or code in {"404", "nosuchkey", "notfound", "no_such_key"}


def upload_file(file_path):
    """Worker-safe upload. Return a structured result instead of hiding errors."""
    client = _s3_client()
    relative_path = os.path.relpath(file_path, settings.MEDIA_ROOT).replace(os.sep, "/")
    s3_key = f"media/{relative_path}"

    try:
        try:
            client.head_object(Bucket=settings.R2_BUCKET_NAME, Key=s3_key)
            logging.info("Skipped (already exists): %s", s3_key)
            return ("skipped", s3_key, "")
        except ClientError as exc:
            if not _is_missing_object(exc):
                raise

        # Access policy is owned by the bucket/storage configuration. Do not set
        # per-object ACLs here; Cloudflare R2 deployments commonly disable ACLs.
        client.upload_file(file_path, settings.R2_BUCKET_NAME, s3_key)
        logging.info("Uploaded: %s", s3_key)
        return ("uploaded", s3_key, "")
    except (ClientError, BotoCoreError, OSError) as exc:
        safe_error = f"{type(exc).__name__}: {str(exc)[:300]}"
        logging.error("Failed: %s -> %s", file_path, safe_error)
        return ("failed", s3_key, safe_error)
    except Exception as exc:
        # Keep the worker alive but make the command fail at the end. This catches
        # unexpected SDK/runtime errors without falsely printing success.
        safe_error = f"{type(exc).__name__}: {str(exc)[:300]}"
        logging.exception("Unexpected failure: %s", file_path)
        return ("failed", s3_key, safe_error)


class Command(BaseCommand):
    help = "Sync local media files to Cloudflare R2 without masking provider errors"

    def add_arguments(self, parser):
        parser.add_argument(
            "--workers",
            type=int,
            default=max(1, min(4, (os.cpu_count() or 2) - 1)),
            help="Parallel upload workers (default: up to 4).",
        )

    def handle(self, *args, **options):
        if not settings.R2_BUCKET_NAME or not settings.R2_ENDPOINT_URL:
            raise CommandError("R2_BUCKET_NAME and R2_ENDPOINT_URL must be configured.")

        self.stdout.write("Starting media sync to Cloudflare R2...")
        media_files = [
            os.path.join(root, filename)
            for root, _, files in os.walk(settings.MEDIA_ROOT)
            for filename in files
        ]
        self.stdout.write(f"Found {len(media_files)} files to inspect.")
        if not media_files:
            self.stdout.write(self.style.SUCCESS("No local media files found."))
            return

        workers = max(1, min(16, int(options["workers"])))
        with multiprocessing.Pool(processes=workers) as pool:
            results = pool.map(upload_file, media_files)

        uploaded = sum(1 for status, _, _ in results if status == "uploaded")
        skipped = sum(1 for status, _, _ in results if status == "skipped")
        failures = [(key, error) for status, key, error in results if status == "failed"]
        self.stdout.write(f"Uploaded: {uploaded}; already present: {skipped}; failed: {len(failures)}")

        if failures:
            for key, error in failures[:20]:
                self.stderr.write(f"  {key}: {error}")
            if len(failures) > 20:
                self.stderr.write(f"  ... and {len(failures) - 20} more. See {LOG_FILE}")
            raise CommandError("Media sync completed with failures; see logs for details.")

        self.stdout.write(self.style.SUCCESS("Media sync completed successfully."))
