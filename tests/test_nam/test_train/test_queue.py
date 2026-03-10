# File: test_queue.py
# Created Date: Tuesday March 26th 2024
# Author: Gene

"""
Tests for the training queue system
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import uuid

try:
    from nam.train.gui._resources.queue import (
        TrainingQueue,
        TrainingJob,
        JobStatus,
    )
    from nam.train import core
except ImportError:
    pytest.skip("NAM not installed", allow_module_level=True)


class TestJobStatus:
    """Tests for JobStatus enum"""

    def test_status_values(self):
        """Test that all status values exist"""
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.QUEUED.value == "queued"
        assert JobStatus.PROCESSING.value == "processing"
        assert JobStatus.COMPLETED.value == "completed"
        assert JobStatus.FAILED.value == "failed"
        assert JobStatus.CANCELLED.value == "cancelled"


class TestTrainingJob:
    """Tests for TrainingJob dataclass"""

    def test_job_creation(self):
        """Test creating a new job with default values"""
        job = TrainingJob(
            job_id="test123",
            input_path=Path("/input.wav"),
            output_path=Path("/output.wav"),
            train_destination=Path("/dest"),
            architecture=core.Architecture.STANDARD,
        )

        assert job.job_id == "test123"
        assert job.input_path == Path("/input.wav")
        assert job.output_path == Path("/output.wav")
        assert job.train_destination == Path("/dest")
        assert job.architecture == core.Architecture.STANDARD
        assert job.status == JobStatus.PENDING
        assert job.train_output is None
        assert job.nam_file_path is None
        assert job.start_time is None
        assert job.end_time is None
        assert job.esr is None
        assert job.wall_time is None

    def test_get_basename(self):
        """Test generating basename from path and architecture"""
        job = TrainingJob(
            job_id="test123",
            input_path=Path("/input.wav"),
            output_path=Path("/path/to/guitar.wav"),
            train_destination=Path("/dest"),
            architecture=core.Architecture.LITE,
        )

        assert job.get_basename() == "guitar_lite"


class TestTrainingQueue:
    """Tests for TrainingQueue class"""

    def test_queue_initialization(self):
        """Test queue starts empty"""
        queue = TrainingQueue()

        assert queue.get_queue_size() == 0
        assert queue.is_running() == False
        assert queue.get_all_jobs() == []

    def test_add_job(self):
        """Test adding a job to the queue"""
        queue = TrainingQueue()
        job = TrainingJob(
            job_id="job1",
            input_path=Path("/input.wav"),
            output_path=Path("/output.wav"),
            train_destination=Path("/dest"),
            architecture=core.Architecture.STANDARD,
        )

        queue.add_job(job)

        assert queue.get_queue_size() == 1
        assert queue.is_running() == False
        assert job.status == JobStatus.QUEUED

    def test_get_job(self):
        """Test retrieving a job by ID"""
        queue = TrainingQueue()
        job = TrainingJob(
            job_id="job1",
            input_path=Path("/input.wav"),
            output_path=Path("/output.wav"),
            train_destination=Path("/dest"),
            architecture=core.Architecture.STANDARD,
        )

        queue.add_job(job)
        retrieved = queue.get_job("job1")

        assert retrieved == job
        assert queue.get_job("nonexistent") is None

    def test_get_all_jobs(self):
        """Test retrieving all jobs"""
        queue = TrainingQueue()

        job1 = TrainingJob(
            job_id="job1",
            input_path=Path("/input1.wav"),
            output_path=Path("/output1.wav"),
            train_destination=Path("/dest"),
            architecture=core.Architecture.STANDARD,
        )
        job2 = TrainingJob(
            job_id="job2",
            input_path=Path("/input2.wav"),
            output_path=Path("/output2.wav"),
            train_destination=Path("/dest"),
            architecture=core.Architecture.LITE,
        )

        queue.add_job(job1)
        queue.add_job(job2)

        jobs = queue.get_all_jobs()
        assert len(jobs) == 2
        job_ids = [j.job_id for j in jobs]
        assert "job1" in job_ids
        assert "job2" in job_ids

    def test_remove_job(self):
        """Test removing a job from the queue"""
        queue = TrainingQueue()

        job = TrainingJob(
            job_id="job1",
            input_path=Path("/input.wav"),
            output_path=Path("/output.wav"),
            train_destination=Path("/dest"),
            architecture=core.Architecture.STANDARD,
        )

        queue.add_job(job)
        queue.remove_job("job1")

        assert queue.get_queue_size() == 0
        assert queue.get_job("job1") is None

    def test_remove_nonexistent_job(self):
        """Test removing a job that doesn't exist"""
        queue = TrainingQueue()

        queue.remove_job("nonexistent")

        assert queue.get_queue_size() == 0

    def test_job_order_preserved(self):
        """Test that jobs are returned in insertion order"""
        queue = TrainingQueue()

        for i in range(5):
            job = TrainingJob(
                job_id=f"job{i}",
                input_path=Path(f"/input{i}.wav"),
                output_path=Path(f"/output{i}.wav"),
                train_destination=Path("/dest"),
                architecture=core.Architecture.STANDARD,
            )
            queue.add_job(job)

        jobs = queue.get_all_jobs()
        job_ids = [j.job_id for j in jobs]

        assert job_ids == ["job0", "job1", "job2", "job3", "job4"]


class TestTrainingQueueWorker:
    """Tests for queue worker functionality"""

    @patch("nam.train.gui._resources.queue._subprocess.Popen")
    def test_process_job_success(self, mock_popen):
        """Test successful job processing via subprocess"""
        # Setup mock subprocess
        mock_process = Mock()
        mock_process.stdout = iter(
            [
                "Epoch[1] Val ESR: 0.010",
                "Epoch[2] Val ESR: 0.005",
                "Epoch[3] Val ESR: 0.001",
            ]
        )
        mock_process.returncode = 0
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        # Use a temp directory that exists
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            queue = TrainingQueue()
            job = TrainingJob(
                job_id="job1",
                input_path=Path("/input.wav"),
                output_path=Path("/output.wav"),
                train_destination=Path(tmpdir),
                architecture=core.Architecture.STANDARD,
            )

            queue.add_job(job)

            # Manually process the job
            queue._process_job(job)

            # Verify results
            assert job.status == JobStatus.COMPLETED
            assert job.wall_time is not None
            assert job.wall_time > 0
            assert job.start_time is not None
            assert job.end_time is not None

    @patch("nam.train.gui._resources.queue._subprocess.Popen")
    def test_process_job_failure(self, mock_popen):
        """Test job processing with error"""
        # Setup mock subprocess to fail
        mock_process = Mock()
        mock_process.stdout = iter(["Epoch[1]"])
        mock_process.returncode = 1
        mock_process.wait.return_value = 1
        mock_popen.return_value = mock_process

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            queue = TrainingQueue()
            job = TrainingJob(
                job_id="job1",
                input_path=Path("/input.wav"),
                output_path=Path("/output.wav"),
                train_destination=Path(tmpdir),
                architecture=core.Architecture.STANDARD,
            )

            queue.add_job(job)

            # Manually process the job
            queue._process_job(job)

            # Verify failure state
            assert job.status == JobStatus.FAILED
            assert "exited with code 1" in job.error_message
            assert job.wall_time is not None
            assert job.wall_time > 0
        assert job.start_time is not None
        assert job.end_time is not None

    @patch("nam.train.gui._resources.queue._subprocess.Popen")
    def test_process_job_failure(self, mock_popen):
        """Test job processing with error"""
        # Setup mock subprocess to fail
        mock_process = Mock()
        mock_process.stdout = iter(["Epoch[1]"])
        mock_process.returncode = 1
        mock_process.wait.return_value = 1
        mock_popen.return_value = mock_process

        queue = TrainingQueue()
        job = TrainingJob(
            job_id="job1",
            input_path=Path("/input.wav"),
            output_path=Path("/output.wav"),
            train_destination=Path("/dest"),
            architecture=core.Architecture.STANDARD,
        )

        queue.add_job(job)

        # Manually process the job
        queue._process_job(job)

        # Verify failure
        assert job.status == JobStatus.FAILED
        assert "exited with code 1" in job.error_message
        assert job.wall_time is not None
        assert job.wall_time > 0
        assert job.start_time is not None
        assert job.end_time is not None

    @patch("nam.train.gui._resources.queue._subprocess.Popen")
    def test_process_job_failure(self, mock_popen):
        """Test job processing with error"""
        # Setup mock subprocess to fail
        mock_process = Mock()
        mock_process.stdout = iter(["Epoch[1]"])
        mock_process.returncode = 1
        mock_process.wait.return_value = 1
        mock_popen.return_value = mock_process

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            queue = TrainingQueue()
            job = TrainingJob(
                job_id="job1",
                input_path=Path("/input.wav"),
                output_path=Path("/output.wav"),
                train_destination=Path(tmpdir),
                architecture=core.Architecture.STANDARD,
            )

            queue.add_job(job)

            # Manually process the job
            queue._process_job(job)

            # Verify failure state
            assert job.status == JobStatus.FAILED
            assert "exited with code 1" in job.error_message
            assert job.wall_time is not None
            assert job.wall_time > 0

    def test_start_stop_queue(self):
        """Test starting and stopping the queue worker"""
        queue = TrainingQueue()

        assert queue.is_running() == False

        # Mock the worker loop to avoid actual threading
        with patch.object(queue, "_worker_loop"):
            queue.start()
            assert queue.is_running() == True

            queue.stop()
            assert queue.is_running() == False

    def test_get_next_job_returns_queued(self):
        """Test that get_next_job returns the first queued job"""
        queue = TrainingQueue()

        job1 = TrainingJob(
            job_id="job1",
            input_path=Path("/input1.wav"),
            output_path=Path("/output1.wav"),
            train_destination=Path("/dest"),
            architecture=core.Architecture.STANDARD,
        )
        job2 = TrainingJob(
            job_id="job2",
            input_path=Path("/input2.wav"),
            output_path=Path("/output2.wav"),
            train_destination=Path("/dest"),
            architecture=core.Architecture.LITE,
        )

        queue.add_job(job1)
        queue.add_job(job2)

        # Simulate job1 being completed
        job1.status = JobStatus.COMPLETED

        next_job = queue._get_next_job()

        assert next_job == job2


class TestQueueWithMultipleArchitectures:
    """Test queue with multiple architecture selection"""

    def test_job_with_different_architectures(self):
        """Test creating jobs for different architectures"""
        queue = TrainingQueue()

        architectures = [
            core.Architecture.STANDARD,
            core.Architecture.LITE,
            core.Architecture.FEATHER,
            core.Architecture.NANO,
        ]

        for i, arch in enumerate(architectures):
            job = TrainingJob(
                job_id=f"job_{arch.value}",
                input_path=Path("/input.wav"),
                output_path=Path("/output.wav"),
                train_destination=Path("/dest"),
                architecture=arch,
            )
            queue.add_job(job)

        jobs = queue.get_all_jobs()
        assert len(jobs) == 4

        for job in jobs:
            assert job.architecture in architectures

    def test_basenames_are_unique(self):
        """Test that different architectures produce unique basenames"""
        queue = TrainingQueue()

        basenames = set()
        for arch in core.Architecture:
            job = TrainingJob(
                job_id=f"job_{arch.value}",
                input_path=Path("/input.wav"),
                output_path=Path("/path/to/guitar.wav"),
                train_destination=Path("/dest"),
                architecture=arch,
            )
            basename = job.get_basename()
            basenames.add(basename)
            queue.add_job(job)

        assert len(basenames) == 4
        assert "guitar_standard" in basenames
        assert "guitar_lite" in basenames
        assert "guitar_feather" in basenames
        assert "guitar_nano" in basenames


if __name__ == "__main__":
    pytest.main()
