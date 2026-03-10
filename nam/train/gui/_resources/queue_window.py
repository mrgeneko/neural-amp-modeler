# File: queue_window.py
# Created Date: Tuesday March 26th 2024
# Author: Gene

"""
Training queue GUI window
"""

import tkinter as _tk
import tkinter.ttk as _ttk
from pathlib import Path as _Path
from typing import Optional as _Optional
import tkinter.filedialog as _filedialog
import tkinter.messagebox as _messagebox

try:
    from nam.train import core as _core
    from nam.models.metadata import GearType as _GearType
    from nam.models.metadata import ToneType as _ToneType
    from nam.train.gui._resources.queue import TrainingQueue, TrainingJob, JobStatus
except ImportError:
    pass


class QueueWindow:
    """Window displaying the training queue."""

    def __init__(self, parent: _tk.Tk, queue: TrainingQueue):
        self._parent = parent
        self._queue = queue
        self._root = _tk.Toplevel(parent)
        self._root.title("Training Queue")
        self._root.geometry("800x600")
        self._root.minsize(600, 400)

        # Frame for controls
        self._frame_controls = _ttk.Frame(self._root)
        self._frame_controls.pack(fill=_tk.X, padx=5, pady=5)

        # Start button
        self._button_start = _ttk.Button(
            self._frame_controls, text="Start Queue", command=self._start_queue
        )
        self._button_start.pack(side=_tk.LEFT, padx=2)

        # Stop button
        self._button_stop = _ttk.Button(
            self._frame_controls, text="Stop Queue", command=self._stop_queue
        )
        self._button_stop.pack(side=_tk.LEFT, padx=2)

        # Refresh button
        self._button_refresh = _ttk.Button(
            self._frame_controls, text="Refresh", command=self._refresh_queue
        )
        self._button_refresh.pack(side=_tk.LEFT, padx=2)

        # Delete selected button
        self._button_delete = _ttk.Button(
            self._frame_controls,
            text="Delete Selected",
            command=self._delete_selected_job,
        )
        self._button_delete.pack(side=_tk.LEFT, padx=2)

        # Add job button
        self._button_add_job = _ttk.Button(
            self._frame_controls, text="Add Job", command=self._add_job_dialog
        )
        self._button_add_job.pack(side=_tk.RIGHT, padx=2)

        # Status label
        self._label_status = _ttk.Label(self._frame_controls, text="Queue is stopped")
        self._label_status.pack(side=_tk.RIGHT, padx=2)

        # Treeview for job list
        self._tree_frame = _ttk.Frame(self._root)
        self._tree_frame.pack(fill=_tk.BOTH, expand=True, padx=5, pady=5)

        # Scrollbars
        self._scroll_y = _ttk.Scrollbar(self._tree_frame, orient=_tk.VERTICAL)
        self._scroll_x = _ttk.Scrollbar(self._tree_frame, orient=_tk.HORIZONTAL)

        # Treeview columns
        columns = (
            "job_id",
            "input",
            "output",
            "architecture",
            "status",
            "ESR",
            "time",
        )
        self._tree = _ttk.Treeview(
            self._tree_frame,
            columns=columns,
            yscrollcommand=self._scroll_y.set,
            xscrollcommand=self._scroll_x.set,
            selectmode="browse",
            show="tree headings",  # Show both tree column and headings
        )

        self._scroll_y.pack(side=_tk.RIGHT, fill=_tk.Y)
        self._scroll_x.pack(side=_tk.BOTTOM, fill=_tk.X)

        self._scroll_y.configure(command=self._tree.yview)
        self._scroll_x.configure(command=self._tree.xview)

        # Configure column widths
        self._tree.column("#0", width=0, stretch=False)  # Hide tree column
        self._tree.column("job_id", width=60, minwidth=50)
        self._tree.column("input", width=120, minwidth=80)
        self._tree.column("output", width=120, minwidth=80)
        self._tree.column("architecture", width=80, minwidth=60)
        self._tree.column("status", width=120, minwidth=100)
        self._tree.column("ESR", width=70, minwidth=50)
        self._tree.column("time", width=70, minwidth=50)

        # Headers
        self._tree.heading("#0", text="")
        self._tree.heading("job_id", text="ID")
        self._tree.heading("input", text="Input")
        self._tree.heading("output", text="Output")
        self._tree.heading("architecture", text="Arch")
        self._tree.heading("status", text="Status")
        self._tree.heading("ESR", text="ESR")
        self._tree.heading("time", text="Time")

        self._tree.pack(fill=_tk.BOTH, expand=True)

        # Bind delete key
        self._root.bind("<Delete>", lambda e: self._delete_selected_job())

        # Bind double-click to show job details
        self._tree.bind("<Double-Button-1>", self._show_job_details)

        # Refresh queue on show
        self._root.after(100, self._refresh_queue)

    def _start_queue(self):
        self._queue.reset_stop()  # Reset stop flag before starting
        self._queue.start()
        self._update_status()
        self._refresh_queue()

    def _stop_queue(self):
        self._queue.stop()
        self._update_status()
        self._refresh_queue()

    def _update_status(self):
        if self._queue.is_running():
            self._label_status.config(text="Queue is running")
        else:
            self._label_status.config(text="Queue is stopped")

    def _refresh_queue(self):
        # Clear existing items
        for item in self._tree.get_children():
            self._tree.delete(item)

        # Add jobs
        for job in self._queue.get_all_jobs():
            # Build status text
            if job.status == JobStatus.PROCESSING:
                if job.current_epoch is not None:
                    status_text = f"Epoch {job.current_epoch}/{job.num_epochs}"
                    if job.current_esr is not None:
                        status_text += f" ESR:{job.current_esr:.4f}"
                else:
                    status_text = "Processing..."
            elif job.status == JobStatus.COMPLETED:
                status_text = "Completed"
            elif job.status == JobStatus.FAILED:
                status_text = "Failed"
            elif job.status == JobStatus.CANCELLED:
                status_text = "Cancelled"
            elif job.status == JobStatus.QUEUED:
                status_text = "Queued"
            else:
                status_text = job.status.value

            # Build ESR text
            if job.current_esr is not None and job.status == JobStatus.PROCESSING:
                esr_text = f"{job.current_esr:.4f}"
            elif job.esr is not None:
                esr_text = f"{job.esr:.4f}"
            else:
                esr_text = ""

            # Build time text
            if job.wall_time is not None:
                time_text = f"{job.wall_time:.1f}s"
            else:
                time_text = ""

            self._tree.insert(
                "",
                _tk.END,
                iid=job.job_id,  # Use job_id as item ID for easier lookup
                values=(
                    job.job_id[:8],
                    _Path(job.input_path).name,
                    _Path(job.output_path).name,
                    job.architecture.value,
                    status_text,
                    esr_text,
                    time_text,
                ),
            )

        # Update status bar
        running = self._queue.is_running()
        pending = sum(
            1 for j in self._queue.get_all_jobs() if j.status == JobStatus.QUEUED
        )
        completed = sum(
            1 for j in self._queue.get_all_jobs() if j.status == JobStatus.COMPLETED
        )
        failed = sum(
            1 for j in self._queue.get_all_jobs() if j.status == JobStatus.FAILED
        )

        if running:
            self._label_status.config(
                text=f"Running | Queued: {pending} | Done: {completed} | Failed: {failed}"
            )
            # Schedule another refresh in 2 seconds if queue is running
            self._root.after(2000, self._refresh_queue)
        else:
            self._label_status.config(
                text=f"Stopped | Queued: {pending} | Done: {completed} | Failed: {failed}"
            )

    def _delete_selected_job(self):
        selected = self._tree.selection()
        if selected:
            for item in selected:
                job_id = item  # iid is the job_id
                self._queue.remove_job(job_id)
            self._refresh_queue()

    def _show_job_details(self, event=None):
        """Show details about a job when double-clicked"""
        selected = self._tree.selection()
        if not selected:
            return

        item = selected[0]
        job = self._queue.get_job(item)
        if not job:
            return

        # Build detail message
        if job.status == JobStatus.FAILED:
            title = f"Job Failed: {job.job_id[:8]}"
            message = (
                f"Error details:\n\n{job.error_message or 'No error details available'}"
            )
        elif job.status == JobStatus.COMPLETED:
            title = f"Job Completed: {job.job_id[:8]}"
            details = f"ESR: {job.esr:.4f}\n" if job.esr else ""
            details += f"Wall time: {job.wall_time:.1f}s\n" if job.wall_time else ""
            details += f"Output: {job.nam_file_path}" if job.nam_file_path else ""
            message = details if details else "No additional details"
        elif job.status == JobStatus.CANCELLED:
            title = f"Job Cancelled: {job.job_id[:8]}"
            message = "This job was cancelled by the user."
        else:
            return  # Don't show details for other statuses

        # Show in a dialog
        dialog = _tk.Toplevel(self._root)
        dialog.title(title)
        dialog.geometry("500x300")

        text = _tk.Text(dialog, wrap=_tk.WORD, height=15)
        text.pack(fill=_tk.BOTH, expand=True, padx=10, pady=10)
        text.insert(_tk.END, message)
        text.config(state=_tk.DISABLED)

        _ttk.Button(dialog, text="Close", command=dialog.destroy).pack(pady=10)

    def _add_job_dialog(self):
        """Open dialog to add a new job to the queue."""
        dialog = _tk.Toplevel(self._root)
        dialog.title("Add Training Job")
        dialog.geometry("750x700")

        # Helper function to create row with label on left and field on right
        def create_labeled_field(
            parent, label_text, var, is_file_path=False, is_directory=False, width=30
        ):
            frame = _ttk.Frame(parent)
            frame.pack(fill=_tk.X, padx=5, pady=3)
            label = _ttk.Label(frame, text=label_text, width=20, anchor=_tk.W)
            label.pack(side=_tk.LEFT)
            entry = _ttk.Entry(frame, textvariable=var, width=width)
            entry.pack(side=_tk.LEFT, fill=_tk.X, expand=True)
            if is_file_path:
                btn = _ttk.Button(
                    frame,
                    text="Browse",
                    command=lambda: var.set(
                        _tk.filedialog.askopenfilename(
                            title=f"Select {label_text}",
                            filetypes=[("WAV files", "*.wav"), ("All files", "*.*")],
                        )
                        if is_file_path
                        else _tk.filedialog.askdirectory(title=f"Select {label_text}")
                    ),
                )
            else:
                btn = _ttk.Button(
                    frame,
                    text="Browse",
                    command=lambda: var.set(
                        _tk.filedialog.askdirectory(title=f"Select {label_text}")
                    ),
                )
            btn.pack(side=_tk.RIGHT, padx=2)
            return frame

        # Input file row
        input_var = _tk.StringVar()
        create_labeled_field(dialog, "Input (dry):", input_var, is_file_path=True)

        # Output file row
        output_var = _tk.StringVar()
        create_labeled_field(dialog, "Output (reamped):", output_var, is_file_path=True)

        # Training destination row
        dest_var = _tk.StringVar()
        create_labeled_field(dialog, "Destination:", dest_var, is_directory=True)

        # Architecture section
        _ttk.Separator(dialog, orient=_tk.HORIZONTAL).pack(fill=_tk.X, padx=5, pady=10)
        _ttk.Label(dialog, text="Architecture:").pack(anchor=_tk.W, padx=5, pady=3)
        arch_frame = _ttk.Frame(dialog)
        arch_frame.pack(anchor=_tk.W, padx=5)

        arch_vars = {}
        for arch in _core.Architecture:
            var = _tk.BooleanVar()
            check = _ttk.Checkbutton(
                arch_frame, text=arch.value.capitalize(), variable=var
            )
            check.pack(anchor=_tk.W, padx=2)
            arch_vars[arch] = var

        # Metadata section
        _ttk.Separator(dialog, orient=_tk.HORIZONTAL).pack(fill=_tk.X, padx=5, pady=10)
        _ttk.Label(dialog, text="Metadata (optional):").pack(
            anchor=_tk.W, padx=5, pady=3
        )

        # Helper for metadata rows with label on left
        def create_metadata_row(
            parent, label_text, var, width=30, is_combo=False, combo_values=None
        ):
            frame = _ttk.Frame(parent)
            frame.pack(fill=_tk.X, padx=5, pady=3)
            label = _ttk.Label(frame, text=label_text, width=20, anchor=_tk.W)
            label.pack(side=_tk.LEFT)
            if is_combo and combo_values:
                combo = _ttk.Combobox(
                    frame,
                    textvariable=var,
                    values=combo_values,
                    width=width,
                    state="readonly",
                )
                combo.pack(side=_tk.LEFT)
                combo.set("")
            else:
                entry = _ttk.Entry(frame, textvariable=var, width=width)
                entry.pack(side=_tk.LEFT, fill=_tk.X, expand=True)
            return frame

        # Metadata fields
        name_var = _tk.StringVar()
        create_metadata_row(dialog, "Model name:", name_var)

        modeled_by_var = _tk.StringVar()
        create_metadata_row(dialog, "Modeled by:", modeled_by_var)

        gear_type_var = _tk.StringVar()
        create_metadata_row(
            dialog,
            "Gear type:",
            gear_type_var,
            is_combo=True,
            combo_values=[g.value for g in _GearType] + [""],
        )

        make_var = _tk.StringVar()
        create_metadata_row(dialog, "Gear make:", make_var)

        model_var = _tk.StringVar()
        create_metadata_row(dialog, "Gear model:", model_var)

        tone_var = _tk.StringVar()
        create_metadata_row(
            dialog,
            "Tone type:",
            tone_var,
            is_combo=True,
            combo_values=[t.value for t in _ToneType] + [""],
        )

        # Level fields side by side
        level_frame = _ttk.Frame(dialog)
        level_frame.pack(fill=_tk.X, padx=5, pady=3)
        _ttk.Label(level_frame, text="Input (dBu):", width=20, anchor=_tk.W).pack(
            side=_tk.LEFT
        )
        input_level_var = _tk.StringVar()
        _ttk.Entry(level_frame, textvariable=input_level_var, width=15).pack(
            side=_tk.LEFT, padx=5
        )
        _ttk.Label(level_frame, text="Output (dBu):", width=20, anchor=_tk.W).pack(
            side=_tk.LEFT, padx=(20, 0)
        )
        output_level_var = _tk.StringVar()
        _ttk.Entry(level_frame, textvariable=output_level_var, width=15).pack(
            side=_tk.LEFT, padx=5
        )

        def on_add():
            selected_archs = [arch for arch, var in arch_vars.items() if var.get()]
            if not selected_archs:
                _tk.messagebox.showerror(
                    "Error", "Please select at least one architecture"
                )
                return

            input_path = _Path(input_var.get())
            output_path = _Path(output_var.get())
            train_dest = _Path(dest_var.get())

            if not input_path.exists():
                _tk.messagebox.showerror(
                    "Error", f"Input file does not exist: {input_path}"
                )
                return
            if not output_path.exists():
                _tk.messagebox.showerror(
                    "Error", f"Output file does not exist: {output_path}"
                )
                return
            if not train_dest.exists():
                _tk.messagebox.showerror(
                    "Error", f"Training destination does not exist: {train_dest}"
                )
                return

            # Parse metadata
            gear_type_val = gear_type_var.get() if gear_type_var.get() else None
            gear_type = _GearType(gear_type_val) if gear_type_val else None

            tone_val = tone_var.get() if tone_var.get() else None
            tone_type = _ToneType(tone_val) if tone_val else None

            input_level = (
                float(input_level_var.get()) if input_level_var.get() else None
            )
            output_level = (
                float(output_level_var.get()) if output_level_var.get() else None
            )

            # Add job for each selected architecture
            import uuid

            for arch in selected_archs:
                job_id = f"{uuid.uuid4().hex[:8]}"
                job = TrainingJob(
                    job_id=job_id,
                    input_path=input_path,
                    output_path=output_path,
                    train_destination=train_dest,
                    architecture=arch,
                    model_name=name_var.get() if name_var.get() else None,
                    modeled_by=modeled_by_var.get() if modeled_by_var.get() else None,
                    gear_type=gear_type,
                    gear_make=make_var.get() if make_var.get() else None,
                    gear_model=model_var.get() if model_var.get() else None,
                    tone_type=tone_type,
                    input_level_dbu=input_level,
                    output_level_dbu=output_level,
                )
                self._queue.add_job(job)

            self._refresh_queue()
            dialog.destroy()

        _ttk.Button(dialog, text="Add to Queue", command=on_add).pack(pady=10)
        _ttk.Button(dialog, text="Cancel", command=dialog.destroy).pack()

    def close(self):
        self._root.destroy()
