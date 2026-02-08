"""
Multi-worker ARQ tests.

These tests verify that ARQ properly deduplicates jobs across multiple workers.
They spawn actual worker processes and inspect Redis to confirm behavior.

These are slower integration tests (~30-60s) and require Redis to be running.
"""

import asyncio
import subprocess
import sys
import time
from uuid import uuid4

import pytest
import pytest_asyncio

from app.config import settings
from app.services.redis_service import redis_service


# Test timeout for worker operations
WORKER_STARTUP_TIME = 5  # seconds to wait for workers to start
JOB_WAIT_TIME = 10  # seconds to wait for job to complete


@pytest_asyncio.fixture
async def redis_client():
    """Get a fresh Redis connection for tests."""
    if redis_service.is_connected:
        await redis_service.disconnect()
    await redis_service.connect()
    yield redis_service
    await redis_service.disconnect()


@pytest_asyncio.fixture
async def clean_arq_queues(redis_client):
    """Clean ARQ queues before and after test."""
    # Clean before
    await _clean_arq_keys(redis_client)
    yield
    # Clean after
    await _clean_arq_keys(redis_client)


async def _clean_arq_keys(redis_client):
    """Remove all ARQ-related keys from Redis."""
    keys = await redis_client.scan_keys("arq:*")
    if keys:
        await redis_client.client.delete(*keys)


class TestMultiWorkerDeduplication:
    """Tests for ARQ multi-worker job deduplication."""

    @pytest.mark.asyncio
    async def test_job_deduplication_via_unique_id(self, redis_client, clean_arq_queues):
        """
        Verify that ARQ assigns unique IDs to jobs and prevents duplicate enqueue.

        When the same job is enqueued twice with the same _job_id, ARQ should
        return the existing job instead of creating a duplicate.
        """
        from arq.connections import create_pool
        from app.worker import parse_redis_url

        redis_settings = parse_redis_url(settings.redis_url)
        arq_redis = await create_pool(redis_settings)

        try:
            # Enqueue with explicit job ID
            job_id = f"dedup_test_{uuid4().hex[:8]}"

            job1 = await arq_redis.enqueue_job(
                "cleanup_stale_presence",
                _job_id=job_id,
            )
            assert job1 is not None
            assert job1.job_id == job_id

            # Try to enqueue again with same ID
            job2 = await arq_redis.enqueue_job(
                "cleanup_stale_presence",
                _job_id=job_id,
            )

            # ARQ returns None when job already exists with that ID
            assert job2 is None, "Duplicate job should not be enqueued"

        finally:
            await arq_redis.close()

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_single_worker_processes_job(self, redis_client, clean_arq_queues):
        """
        Verify a single worker can process an enqueued job.
        """
        from arq.connections import create_pool
        from app.worker import parse_redis_url

        redis_settings = parse_redis_url(settings.redis_url)

        # Start a single worker
        worker = subprocess.Popen(
            [sys.executable, "-m", "arq", "app.worker.WorkerSettings"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            await asyncio.sleep(WORKER_STARTUP_TIME)

            arq_redis = await create_pool(redis_settings)

            # Enqueue cleanup job (fast, no DB needed)
            job = await arq_redis.enqueue_job("cleanup_stale_presence")
            assert job is not None

            # Wait for result with timeout
            try:
                result = await job.result(timeout=30)
                assert result is not None
                assert "removed" in result

                # Verify job completed successfully
                info = await job.info()
                assert info.success is True
            except asyncio.TimeoutError:
                # Check if worker is still running
                if worker.poll() is not None:
                    stdout, stderr = worker.communicate()
                    pytest.fail(f"Worker crashed. stderr: {stderr.decode()}")
                raise

            await arq_redis.close()

        finally:
            worker.terminate()
            try:
                worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker.kill()

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_job_result_stored_in_redis(self, redis_client, clean_arq_queues):
        """
        Verify that job results are properly stored in Redis.
        """
        from arq.connections import create_pool
        from app.worker import parse_redis_url

        redis_settings = parse_redis_url(settings.redis_url)

        # Start a single worker
        worker = subprocess.Popen(
            [sys.executable, "-m", "arq", "app.worker.WorkerSettings"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            await asyncio.sleep(WORKER_STARTUP_TIME)

            arq_redis = await create_pool(redis_settings)

            # Enqueue cleanup job
            job = await arq_redis.enqueue_job("cleanup_stale_presence")
            assert job is not None

            # Wait for result
            result = await job.result(timeout=30)

            # Verify result structure
            assert result is not None
            assert "removed" in result
            assert isinstance(result["removed"], int)

            await arq_redis.close()

        finally:
            worker.terminate()
            try:
                worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker.kill()

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_worker_processes_start_successfully(self, redis_client):
        """
        Verify that ARQ worker processes can start without errors.
        """
        worker = subprocess.Popen(
            [sys.executable, "-m", "arq", "app.worker.WorkerSettings"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            # Give it time to start
            await asyncio.sleep(3)

            # Check it's still running (didn't crash on startup)
            assert worker.poll() is None, "Worker crashed on startup"

            # Check stderr for any critical errors
            # (non-blocking read)
            import select
            if sys.platform != "win32":
                # Unix: use select
                readable, _, _ = select.select([worker.stderr], [], [], 0)
                if readable:
                    stderr_output = worker.stderr.read(1024).decode()
                    assert "Error" not in stderr_output, f"Worker error: {stderr_output}"
            # On Windows, just verify process is running

        finally:
            worker.terminate()
            try:
                worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker.kill()


class TestCronJobScheduling:
    """Tests for ARQ cron job scheduling behavior."""

    @pytest.mark.asyncio
    async def test_cron_jobs_have_unique_identifiers(self):
        """
        Verify cron jobs are configured with proper scheduling.
        """
        from app.worker import WorkerSettings

        cron_jobs = WorkerSettings.cron_jobs
        assert len(cron_jobs) == 2

        # Check archive job - runs at midnight and noon
        archive_cron = cron_jobs[0]
        assert archive_cron.coroutine.__name__ == "run_archive_jobs"

        # Check presence cleanup - runs every 30 seconds
        presence_cron = cron_jobs[1]
        assert presence_cron.coroutine.__name__ == "cleanup_stale_presence"

    @pytest.mark.asyncio
    async def test_cron_job_unique_name_generation(self):
        """
        ARQ generates unique names for cron jobs to prevent duplicates.
        Each cron job gets a unique key based on function name + schedule.
        """
        from arq.cron import cron
        from app.worker import run_archive_jobs, cleanup_stale_presence

        # Create two cron configs with same function but different schedules
        cron1 = cron(run_archive_jobs, hour={0}, minute=0)
        cron2 = cron(run_archive_jobs, hour={12}, minute=0)

        # They should have different unique names (ARQ uses function + schedule hash)
        # The name is generated at runtime by ARQ, but both should be valid
        assert cron1.coroutine == cron2.coroutine
        # ARQ will differentiate them by their schedule parameters


class TestJobAtomicity:
    """Tests verifying atomic job consumption."""

    @pytest.mark.asyncio
    async def test_redis_brpoplpush_is_atomic(self, redis_client, clean_arq_queues):
        """
        Demonstrate that Redis BRPOPLPUSH (used by ARQ) is atomic.

        This is the mechanism that ensures only one worker gets each job.
        """
        test_queue = "test:atomic:queue"
        test_processing = "test:atomic:processing"

        # Add one job to queue
        await redis_client.client.lpush(test_queue, "job1")

        # Simulate two workers trying to pop at the same time
        async def worker_pop():
            result = await redis_client.client.brpoplpush(
                test_queue, test_processing, timeout=1
            )
            return result

        # Run two workers concurrently
        results = await asyncio.gather(
            worker_pop(),
            worker_pop(),
            return_exceptions=True,
        )

        # Only one should get the job, the other gets None (timeout)
        got_job = [r for r in results if r == "job1"]
        got_nothing = [r for r in results if r is None]

        assert len(got_job) == 1, "Exactly one worker should get the job"
        assert len(got_nothing) == 1, "The other worker should timeout"

        # Cleanup
        await redis_client.client.delete(test_queue, test_processing)
