# File: queue.py
# Created Date: Tuesday March 26th 2024
# Author: Gene

"""
Training queue system for NAM trainer
"""

import json as _json
import threading as _threading
import time as _time
import re as _re
import subprocess as _subprocess
import shutil as _shutil
import tempfile as _tempfile
from dataclasses import dataclass as _dataclass
from enum import Enum as _Enum
from pathlib import Path as _Path
from typing import Dict as _Dict
from typing import Optional as _Optional
from typing import Sequence as _Sequence
from typing import List as _List

import tkinter as _tk
import tkinter.ttk as _ttk

# Import NAM modules - must be at module level for dataclass to work
from nam.train import core as _core
from nam.models.metadata import UserMetadata as _UserMetadata
from nam.models.metadata import GearType as _GearType
from nam.models.metadata import ToneType as _ToneType
from nam.train import metadata as _metadata


class JobStatus(_Enum):
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@_dataclass
class TrainingJob:
    """Represents a single training job in the queue."""

    job_id: str
    input_path: _Path
    output_path: _Path
    train_destination: _Path
    architecture: _core.Architecture
    num_epochs: int = 100  # Default epochs for queue jobs

    # Output filename template
    output_template: str = "{input}_{arch}"  # Default template

    # Batch/GUID for grouping multiple jobs
    batch_guid: _Optional[str] = None

    # Metadata fields
    model_name: _Optional[str] = None
    modeled_by: _Optional[str] = None
    gear_type: _Optional[_GearType] = None
    gear_make: _Optional[str] = None
    gear_model: _Optional[str] = None
    tone_type: _Optional[_ToneType] = None
    input_level_dbu: _Optional[float] = None
    output_level_dbu: _Optional[float] = None

    # Runtime fields
    status: JobStatus = JobStatus.PENDING
    train_output: _Optional[_core.TrainOutput] = None
    nam_file_path: _Optional[_Path] = None
    start_time: _Optional[float] = None
    end_time: _Optional[float] = None
    esr: _Optional[float] = None
    wall_time: _Optional[float] = None
    error_message: _Optional[str] = None

    # Progress tracking
    current_epoch: _Optional[int] = None
    current_esr: _Optional[float] = None
    best_esr: _Optional[float] = None

    def resolve_output_filename(self) -> str:
        """Resolve the output template using job fields."""
        import uuid
        from datetime import datetime

        input_name = _Path(self.input_path).stem
        arch = self.architecture.value
        now = datetime.now()
        
        # Build token replacements
        tokens = {
            "{input}": input_name,
            "{size}": arch,
            "{model}": self.model_name or "",
            "{date}": now.strftime("%Y_%m_%d"),
            "{time}": now.strftime("%H_%M_%S"),
            "{creator}": self.modeled_by or "",
            "{type}": self.gear_type.value if self.gear_type else "",
            "{guid}": f"__ID_{self.batch_guid}__" if self.batch_guid else "",
        }

        result = self.output_template
        for token, value in tokens.items():
            result = result.replace(token, value)

        # Clean up any empty braces from unused tokens
        import re
        result = re.sub(r'\{[^}]*\}', '', result)
        
        # Normalize separators (but preserve __ GUID marker)
        if '__' not in result:
            result = re.sub(r'[_-]+', '_', result)
            result = result.strip('_-')
        
        return result

    def get_basename(self) -> str:
        """Get the output filename (without extension) based on template."""
        return self.resolve_output_filename()

    def get_user_metadata(self) -> _UserMetadata:
        """Create UserMetadata from job fields"""
        return _UserMetadata(
            name=self.model_name,
            modeled_by=self.modeled_by,
            gear_type=self.gear_type,
            gear_make=self.gear_make,
            gear_model=self.gear_model,
            tone_type=self.tone_type,
            input_level_dbu=self.input_level_dbu,
            output_level_dbu=self.output_level_dbu,
        )


class TrainingQueue:
    """Manages a queue of training jobs."""

    def __init__(self):
        self._jobs: _Dict[str, TrainingJob] = {}
        self._job_order: _List[str] = []  # To maintain insertion order
        self._lock = _threading.Lock()
        self._running = False
        self._paused = False
        self._stop_requested = False
        self._worker_thread: _Optional[_threading.Thread] = None
        self._current_process: _Optional[_subprocess.Popen] = None
        self._current_job_id: _Optional[str] = None

    def add_job(self, job: TrainingJob):
        with self._lock:
            self._jobs[job.job_id] = job
            self._job_order.append(job.job_id)
            job.status = JobStatus.QUEUED

    def request_pause(self):
        """Request the queue to pause after current job completes."""
        self._paused = True

    def request_resume(self):
        """Request the queue to resume processing."""
        self._paused = False

    def is_paused(self) -> bool:
        return self._paused

    def request_stop(self):
        """Request the queue to stop. Current job will be marked as queued for retry."""
        self._stop_requested = True
        self._running = False
        # Mark current processing job as queued so it can be retried
        for job in self._jobs.values():
            if job.status == JobStatus.PROCESSING:
                job.status = JobStatus.QUEUED
                job.current_epoch = None
                job.current_esr = None
                job.best_esr = None

    def get_job(self, job_id: str) -> _Optional[TrainingJob]:
        return self._jobs.get(job_id)

    def get_all_jobs(self) -> _List[TrainingJob]:
        with self._lock:
            return [self._jobs[jid] for jid in self._job_order if jid in self._jobs]

    def remove_job(self, job_id: str):
        with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
            if job_id in self._job_order:
                self._job_order.remove(job_id)

    def move_job_up(self, job_id: str):
        """Move a job up in the queue (earlier execution)."""
        with self._lock:
            if job_id in self._job_order:
                idx = self._job_order.index(job_id)
                if idx > 0:
                    self._job_order[idx], self._job_order[idx - 1] = (
                        self._job_order[idx - 1],
                        self._job_order[idx],
                    )

    def move_job_down(self, job_id: str):
        """Move a job down in the queue (later execution)."""
        with self._lock:
            if job_id in self._job_order:
                idx = self._job_order.index(job_id)
                if idx < len(self._job_order) - 1:
                    self._job_order[idx], self._job_order[idx + 1] = (
                        self._job_order[idx + 1],
                        self._job_order[idx],
                    )

    def get_queue_size(self) -> int:
        with self._lock:
            return len(self._jobs)

    def is_running(self) -> bool:
        return self._running

    def start(self):
        self._running = True
        self._stop_requested = False
        self._paused = False
        self._worker_thread = _threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

    def stop(self):
        self.request_stop()
        self._kill_current_process()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)  # Wait up to 1 second

    def reset_stop(self):
        """Reset the stop request to allow starting again"""
        self._stop_requested = False

    def _kill_current_process(self):
        """Kill the currently running training process and all its children"""
        if self._current_process:
            try:
                import signal
                import os

                pgid = None
                # Get the process group ID to kill all children
                try:
                    pgid = os.getpgid(self._current_process.pid)
                    # Kill the entire process group
                    os.killpg(pgid, signal.SIGTERM)
                except (ProcessLookupError, OSError):
                    # Process already dead or can't get pgid, try individual kill
                    self._current_process.terminate()

                # Wait a bit for graceful termination
                try:
                    self._current_process.wait(timeout=3)
                except _subprocess.TimeoutExpired:
                    # Force kill if still running
                    try:
                        if pgid is not None:
                            os.killpg(pgid, signal.SIGKILL)
                        else:
                            self._current_process.kill()
                        self._current_process.wait(timeout=2)
                    except (ProcessLookupError, OSError):
                        pass  # Already dead

            except Exception as e:
                print(f"Warning: Error killing process: {e}")
            finally:
                self._current_process = None
                self._current_job_id = None

    def _worker_loop(self):
        while self._running and not self._stop_requested:
            # Check if paused
            while self._paused and not self._stop_requested:
                _time.sleep(0.5)

            if self._stop_requested:
                break

            job = self._get_next_job()
            if job is None:
                self._running = False
                break

            self._process_job(job)

            # Check if stop was requested after each job
            if self._stop_requested:
                break

            _time.sleep(0.1)

    def _get_next_job(self) -> _Optional[TrainingJob]:
        with self._lock:
            for job_id in self._job_order:
                job = self._jobs.get(job_id)
                if job and job.status in (JobStatus.QUEUED, JobStatus.PENDING):
                    return job
            return None

    def _process_job(self, job: TrainingJob):
        job.status = JobStatus.PROCESSING
        job.start_time = _time.time()

        try:
            self._do_train_subprocess(job)
            # Check status before marking as completed
            if job.status == JobStatus.QUEUED:
                # Job was stopped for retry, keep it queued
                pass
            elif self._stop_requested:
                job.status = JobStatus.CANCELLED
            else:
                job.status = JobStatus.COMPLETED
                # Save final ESR
                if job.current_esr is not None:
                    job.esr = job.current_esr
            job.end_time = _time.time()
            job.wall_time = job.end_time - job.start_time
        except Exception as e:
            if job.status == JobStatus.CANCELLED:
                # Already marked as cancelled by stop request
                pass
            else:
                job.status = JobStatus.FAILED
                job.error_message = str(e)
            job.end_time = _time.time()
            job.wall_time = job.end_time - job.start_time

    def _do_train_subprocess(self, job: TrainingJob):
        """Train using nam-full CLI subprocess for proper cancellation support"""
        import os
        import sys

        basename = job.get_basename()

        # Default to output file's directory if no destination set
        if job.train_destination is None or str(job.train_destination).strip() == "":
            outdir = job.output_path.parent
        else:
            outdir = job.train_destination

        # Create job-specific subdirectory to isolate checkpoints
        job_dir = outdir / f"job_{job.job_id[:8]}"
        job_dir.mkdir(parents=True, exist_ok=True)

        # Ensure output directory exists
        outdir.mkdir(parents=True, exist_ok=True)

        # Create a temporary directory for configs
        with _tempfile.TemporaryDirectory() as tmpdir:
            tmppath = _Path(tmpdir)

            # Determine model architecture settings
            if job.architecture.value == "standard":
                layers_configs = [
                    {
                        "input_size": 1,
                        "condition_size": 1,
                        "channels": 16,
                        "head_size": 8,
                        "kernel_size": 3,
                        "dilations": [1, 2, 4, 8, 16, 32, 64, 128, 256, 512],
                        "activation": "Tanh",
                        "head_bias": False,
                    },
                    {
                        "condition_size": 1,
                        "input_size": 16,
                        "channels": 8,
                        "head_size": 1,
                        "kernel_size": 3,
                        "dilations": [1, 2, 4, 8, 16, 32, 64, 128, 256, 512],
                        "activation": "Tanh",
                        "head_bias": True,
                    },
                ]
            elif job.architecture.value == "lite":
                layers_configs = [
                    {
                        "input_size": 1,
                        "condition_size": 1,
                        "channels": 12,
                        "head_size": 6,
                        "kernel_size": 3,
                        "dilations": [1, 2, 4, 8, 16, 32, 64],
                        "activation": "Tanh",
                        "head_bias": False,
                    },
                    {
                        "condition_size": 1,
                        "input_size": 12,
                        "channels": 6,
                        "head_size": 1,
                        "kernel_size": 3,
                        "dilations": [
                            128,
                            256,
                            512,
                            1,
                            2,
                            4,
                            8,
                            16,
                            32,
                            64,
                            128,
                            256,
                            512,
                        ],
                        "activation": "Tanh",
                        "head_bias": True,
                    },
                ]
            elif job.architecture.value == "feather":
                layers_configs = [
                    {
                        "input_size": 1,
                        "condition_size": 1,
                        "channels": 8,
                        "head_size": 4,
                        "kernel_size": 3,
                        "dilations": [1, 2, 4, 8, 16, 32, 64],
                        "activation": "Tanh",
                        "head_bias": False,
                    },
                    {
                        "condition_size": 1,
                        "input_size": 8,
                        "channels": 4,
                        "head_size": 1,
                        "kernel_size": 3,
                        "dilations": [
                            128,
                            256,
                            512,
                            1,
                            2,
                            4,
                            8,
                            16,
                            32,
                            64,
                            128,
                            256,
                            512,
                        ],
                        "activation": "Tanh",
                        "head_bias": True,
                    },
                ]
            elif job.architecture.value == "nano":
                layers_configs = [
                    {
                        "input_size": 1,
                        "condition_size": 1,
                        "channels": 4,
                        "head_size": 2,
                        "kernel_size": 3,
                        "dilations": [1, 2, 4, 8, 16, 32, 64],
                        "activation": "Tanh",
                        "head_bias": False,
                    },
                    {
                        "condition_size": 1,
                        "input_size": 4,
                        "channels": 2,
                        "head_size": 1,
                        "kernel_size": 3,
                        "dilations": [
                            128,
                            256,
                            512,
                            1,
                            2,
                            4,
                            8,
                            16,
                            32,
                            64,
                            128,
                            256,
                            512,
                        ],
                        "activation": "Tanh",
                        "head_bias": True,
                    },
                ]
            else:
                layers_configs = [
                    {
                        "input_size": 1,
                        "condition_size": 1,
                        "channels": 16,
                        "head_size": 8,
                        "kernel_size": 3,
                        "dilations": [1, 2, 4, 8, 16, 32, 64, 128, 256, 512],
                        "activation": "Tanh",
                        "head_bias": False,
                    },
                    {
                        "condition_size": 1,
                        "input_size": 16,
                        "channels": 8,
                        "head_size": 1,
                        "kernel_size": 3,
                        "dilations": [1, 2, 4, 8, 16, 32, 64, 128, 256, 512],
                        "activation": "Tanh",
                        "head_bias": True,
                    },
                ]

            # Create data config with proper splits
            # Use same structure as GUI trainer
            # Determine appropriate split points (90% train, 10% validation)
            # We'll use the stop_samples approach
            data_config = {
                "train": {
                    "ny": 8192,  # Use default from core._NY_DEFAULT
                    "stop_samples": None,  # Will use 90% of data
                },
                "validation": {
                    "ny": None,
                    "start_samples": None,  # Will use last 10% of data
                },
                "common": {
                    "x_path": str(job.input_path),
                    "y_path": str(job.output_path),
                    "delay": 0,
                    "allow_unequal_lengths": True,
                },
            }

            # Create model config using proper two-layer structure
            model_config = {
                "net": {
                    "name": "WaveNet",
                    "config": {
                        "layers_configs": layers_configs,
                        "head_scale": 0.02,
                    },
                },
                "loss": {"val_loss": "esr"},
                "optimizer": {"lr": 0.004},
                "lr_scheduler": {"class": "ExponentialLR", "kwargs": {"gamma": 0.993}},
            }

            # Create learning config
            learning_config = {
                "train_dataloader": {
                    "batch_size": 16,
                    "shuffle": True,
                    "pin_memory": False,
                    "drop_last": True,
                    "num_workers": 0,
                },
                "val_dataloader": {},
                "trainer": {
                    "max_epochs": job.num_epochs,
                },
                "trainer_fit_kwargs": {},
            }

            # Write config files
            data_config_path = tmppath / "data_config.json"
            model_config_path = tmppath / "model_config.json"
            learning_config_path = tmppath / "learning_config.json"

            with open(data_config_path, "w") as fp:
                _json.dump(data_config, fp)
            with open(model_config_path, "w") as fp:
                _json.dump(model_config, fp)
            with open(learning_config_path, "w") as fp:
                _json.dump(learning_config, fp)

            # Find nam-full executable
            import sys

            nam_full_cmd = _shutil.which("nam-full")
            if not nam_full_cmd:
                # Try to use python -m nam.cli
                nam_full_cmd = [sys.executable, "-m", "nam.cli", "nam_full"]

            # Run nam-full as subprocess
            cmd = [
                "nam-full",
                str(data_config_path),
                str(model_config_path),
                str(learning_config_path),
                str(job_dir),
                "--no-show",
                "--no-plots",
            ]

            # Set up process tracking
            self._current_job_id = job.job_id

            # Run subprocess in new process group for proper kill support
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            process = _subprocess.Popen(
                cmd,
                stdout=_subprocess.PIPE,
                stderr=_subprocess.STDOUT,
                text=True,
                bufsize=1,
                preexec_fn=os.setsid
                if hasattr(os, "setsid")
                else None,  # New process group on Unix
                env=env,
            )
            self._current_process = process

            # Start checkpoint monitoring thread
            import threading
            monitor_thread = _threading.Thread(
                target=self._monitor_checkpoints,
                args=(job, job_dir),
                daemon=True
            )
            monitor_thread.start()

            # Parse output for progress - more flexible patterns
            epoch_pattern = _re.compile(r"Epoch\s*\[?(\d+)\]?", _re.IGNORECASE)
            # Match ESR in various formats: ESR=0.044, ESR:0.044, _ESR_0.044_
            esr_pattern = _re.compile(r"(?:^|[_\s])ESR[:=\s]+([0-9.eE+-]+)", _re.IGNORECASE)

            # Collect output for error reporting
            output_lines = []

            try:
                for line in process.stdout:
                    output_lines.append(line)

                    # Check for stop request
                    if self._stop_requested:
                        process.terminate()
                        try:
                            process.wait(timeout=2)
                        except _subprocess.TimeoutExpired:
                            process.kill()
                        # Don't overwrite status - request_stop() already set it to QUEUED
                        return

                    # Parse epoch progress
                    epoch_match = epoch_pattern.search(line)
                    if epoch_match:
                        job.current_epoch = int(epoch_match.group(1))

                    # Parse ESR and track best
                    esr_match = esr_pattern.search(line)
                    if esr_match:
                        esr_value = float(esr_match.group(1))
                        job.current_esr = esr_value
                        if job.best_esr is None or esr_value < job.best_esr:
                            job.best_esr = esr_value

                # Wait for process to complete
                process.wait()

                # Check return code
                if process.returncode != 0 and not self._stop_requested:
                    # Include last 10 lines of output in error message
                    last_lines = "".join(output_lines[-10:])
                    raise RuntimeError(
                        f"nam-full exited with code {process.returncode}\n\nLast output:\n{last_lines}"
                    )

            finally:
                self._current_process = None
                self._current_job_id = None

            # Look for the output .nam file
            # nam-full creates a timestamped subdirectory with model.nam inside
            if job_dir.exists():
                # Find the most recently created subdirectory (the timestamp dir)
                subdirs = [d for d in job_dir.iterdir() if d.is_dir()]
                if subdirs:
                    # Get the most recent one (by modification time)
                    timestamp_dir = max(subdirs, key=lambda d: d.stat().st_mtime)
                    model_nam = timestamp_dir / "model.nam"

                    if model_nam.exists():
                        # Move and rename to desired location
                        target_nam = outdir / f"{basename}.nam"

                        # If target already exists, remove it
                        if target_nam.exists():
                            target_nam.unlink()

                        # Move the file
                        model_nam.rename(target_nam)
                        job.nam_file_path = target_nam

                        # Optionally clean up the timestamp directory
                        # import shutil
                        # shutil.rmtree(timestamp_dir)

    def _monitor_checkpoints(self, job: TrainingJob, job_dir: _Path):
        """Monitor checkpoint directory for new files and extract ESR."""
        import time as _time

        seen_files = set()
        esr_pattern = _re.compile(r"ESR[=_]([0-9.eE+-]+)", _re.IGNORECASE)

        while not self._stop_requested:
            try:
                # Find all checkpoint files
                for ckpt_file in job_dir.glob("**/checkpoints/*.ckpt"):
                    if ckpt_file.name not in seen_files:
                        seen_files.add(ckpt_file.name)

                        # Parse ESR from filename
                        esr_match = esr_pattern.search(ckpt_file.name)
                        if esr_match:
                            esr_value = float(esr_match.group(1))
                            job.current_esr = esr_value
                            if job.best_esr is None or esr_value < job.best_esr:
                                job.best_esr = esr_value

                _time.sleep(1)  # Check every second
            except Exception:
                pass
