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
import uuid as _uuid

try:
    from nam.train import core as _core
    from nam.models.metadata import GearType as _GearType
    from nam.models.metadata import ToneType as _ToneType
    from nam.train.gui._resources.queue import TrainingQueue, TrainingJob, JobStatus
    from nam.train.gui._resources import config as _config
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

        # Second row of controls
        self._frame_controls2 = _ttk.Frame(self._root)
        self._frame_controls2.pack(fill=_tk.X, padx=5, pady=(0, 5))

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

        # Delete selected button
        self._button_delete = _ttk.Button(
            self._frame_controls2,
            text="Delete Selected",
            command=self._delete_selected_job,
        )
        self._button_delete.pack(side=_tk.LEFT, padx=2)

        # Move up button
        self._button_move_up = _ttk.Button(
            self._frame_controls2,
            text="Move Up",
            command=self._move_selected_up,
        )
        self._button_move_up.pack(side=_tk.LEFT, padx=2)

        # Move down button
        self._button_move_down = _ttk.Button(
            self._frame_controls2,
            text="Move Down",
            command=self._move_selected_down,
        )
        self._button_move_down.pack(side=_tk.LEFT, padx=2)

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
            "dry",
            "wet",
            "size",
            "filename",
            "status",
            "ESR",
            "elapsed",
            "remaining",
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
        self._tree.column("job_id", width=55, minwidth=50)
        self._tree.column("dry", width=120, minwidth=80)
        self._tree.column("wet", width=120, minwidth=80)
        self._tree.column("size", width=40, minwidth=60)
        self._tree.column("filename", width=300, minwidth=100)
        self._tree.column("status", width=139, minwidth=80)
        self._tree.column("ESR", width=60, minwidth=50)
        self._tree.column("elapsed", width=70, minwidth=50)
        self._tree.column("remaining", width=70, minwidth=50)

        # Headers
        self._tree.heading("#0", text="")
        self._tree.heading("job_id", text="ID")
        self._tree.heading("dry", text="Dry")
        self._tree.heading("wet", text="Wet")
        self._tree.heading("size", text="Size")
        self._tree.heading("filename", text="File Name")
        self._tree.heading("status", text="Status")
        self._tree.heading("ESR", text="ESR")
        self._tree.heading("elapsed", text="Elapsed")
        self._tree.heading("remaining", text="Remaining")

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

    def _pause_queue(self):
        self._queue.request_pause()
        self._update_status()
        self._refresh_queue()

    def _resume_queue(self):
        self._queue.request_resume()
        self._update_status()
        self._refresh_queue()

    def _update_status(self):
        if self._queue.is_running():
            self._label_status.config(text="Queue is running")
        else:
            self._label_status.config(text="Queue is stopped")

    def _refresh_queue(self):
        # Save current selection
        selected = self._tree.selection()
        selected_job_id = selected[0] if selected else None

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

            # Build ESR text - show best ESR during processing
            if job.best_esr is not None:
                esr_text = f"{job.best_esr:.4f}"
            elif job.esr is not None:
                esr_text = f"{job.esr:.4f}"
            else:
                esr_text = ""

            # Build elapsed time text
            if job.status == JobStatus.PROCESSING and job.start_time is not None:
                import time as _time_module
                elapsed = _time_module.time() - job.start_time
                elapsed_min = int(elapsed // 60)
                elapsed_sec = int(elapsed % 60)
                elapsed_text = f"{elapsed_min}m {elapsed_sec}s"
            elif job.wall_time is not None:
                elapsed_min = int(job.wall_time // 60)
                elapsed_sec = int(job.wall_time % 60)
                elapsed_text = f"{elapsed_min}m {elapsed_sec}s"
            else:
                elapsed_text = ""

            # Build remaining time text (estimate based on epoch progress)
            if job.status == JobStatus.PROCESSING and job.current_epoch is not None and job.start_time is not None:
                import time as _time_module
                elapsed = _time_module.time() - job.start_time
                if job.current_epoch > 0:
                    time_per_epoch = elapsed / job.current_epoch
                    remaining_epochs = job.num_epochs - job.current_epoch
                    remaining = time_per_epoch * remaining_epochs
                    remaining_min = int(remaining // 60)
                    remaining_sec = int(remaining % 60)
                    remaining_text = f"{remaining_min}m {remaining_sec}s"
                else:
                    remaining_text = ""
            else:
                remaining_text = ""

            self._tree.insert(
                "",
                _tk.END,
                iid=job.job_id,  # Use job_id as item ID for easier lookup
                values=(
                    job.job_id[:8],
                    _Path(job.input_path).name,
                    _Path(job.output_path).name,
                    job.architecture.value,
                    job.get_basename(),
                    status_text,
                    esr_text,
                    elapsed_text,
                    remaining_text,
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
            # Schedule another refresh in 500ms if queue is running
            self._root.after(500, self._refresh_queue)
        else:
            self._label_status.config(
                text=f"Stopped | Queued: {pending} | Done: {completed} | Failed: {failed}"
            )

        # Restore selection
        if selected_job_id and self._tree.exists(selected_job_id):
            self._tree.selection_set(selected_job_id)

    def _delete_selected_job(self):
        selected = self._tree.selection()
        if selected:
            for item in selected:
                job_id = item  # iid is the job_id
                self._queue.remove_job(job_id)
            self._refresh_queue()

    def _move_selected_up(self):
        selected = self._tree.selection()
        if selected:
            for item in selected:
                self._queue.move_job_up(item)
            self._refresh_queue()

    def _move_selected_down(self):
        selected = self._tree.selection()
        if selected:
            for item in selected:
                self._queue.move_job_down(item)
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
        dialog.title("Add Job")
        dialog.geometry("750x700")

        cfg = _config.load() if _config else {}

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

        # Mode selection: Single vs Batch
        mode_frame = _ttk.Frame(dialog)
        # File selection fields
        input_var = _tk.StringVar(value=cfg.get("dry_path", ""))
        create_labeled_field(dialog, "Dry:", input_var, is_file_path=True)

        output_var = _tk.StringVar(value=cfg.get("wet_path", ""))
        create_labeled_field(dialog, "Wet:", output_var, is_file_path=True)

        dest_var = _tk.StringVar(value=cfg.get("default_destination", ""))
        create_labeled_field(dialog, "Output Directory:", dest_var, is_directory=True)

        # File name template section
        _ttk.Label(dialog, text="File Name Template:").pack(anchor=_tk.W, padx=5, pady=(5, 0))
        template_frame = _ttk.Frame(dialog)
        template_frame.pack(fill=_tk.X, padx=5, pady=3)
        output_template_var = _tk.StringVar(value=cfg.get("output_template", "__ID_{guid}__{model}_{type}_{size}_{date}"))
        _ttk.Entry(template_frame, textvariable=output_template_var, width=50).pack(
            side=_tk.LEFT, fill=_tk.X, expand=True
        )
        _ttk.Label(
            dialog,
            text="Tokens: {input} {size} {date} {time} {creator} {type} {model} __ID_{guid}__",
            font=("Helvetica", 8),
        ).pack(anchor=_tk.W, padx=5)

        # Batch GUID for grouping jobs
        batch_frame = _ttk.Frame(dialog)
        batch_frame.pack(fill=_tk.X, padx=5, pady=3)
        _ttk.Label(batch_frame, text="Batch GUID:", width=15, anchor=_tk.W).pack(side=_tk.LEFT)
        batch_guid_var = _tk.StringVar(value=_uuid.uuid4().hex[:8])
        _ttk.Entry(batch_frame, textvariable=batch_guid_var, width=20).pack(
            side=_tk.LEFT, fill=_tk.X, expand=True
        )
        _ttk.Button(
            batch_frame,
            text="Generate",
            command=lambda: batch_guid_var.set(_uuid.uuid4().hex[:8]),
        ).pack(side=_tk.RIGHT, padx=2)

        # Architecture section
        _ttk.Separator(dialog, orient=_tk.HORIZONTAL).pack(fill=_tk.X, padx=5, pady=10)
        _ttk.Label(dialog, text="size:").pack(anchor=_tk.W, padx=5, pady=3)
        arch_frame = _ttk.Frame(dialog)
        arch_frame.pack(anchor=_tk.W, padx=5)

        arch_vars = {}
        default_archs = cfg.get("default_architectures", ["standard"])
        for arch in reversed(_core.Architecture):
            var = _tk.BooleanVar(value=arch.value in default_archs)
            check = _ttk.Checkbutton(
                arch_frame, text=arch.value.capitalize(), variable=var
            )
            check.pack(side=_tk.LEFT, padx=5)
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
                if not var.get():
                    combo.set("")
            else:
                entry = _ttk.Entry(frame, textvariable=var, width=width)
                entry.pack(side=_tk.LEFT, fill=_tk.X, expand=True)
            return frame

        # Metadata fields
        name_var = _tk.StringVar(value=cfg.get("model_name", ""))
        create_metadata_row(dialog, "Model name:", name_var)

        modeled_by_var = _tk.StringVar(value=cfg.get("modeled_by", ""))
        create_metadata_row(dialog, "Modeled by:", modeled_by_var)

        gear_type_var = _tk.StringVar(value=cfg.get("gear_type", ""))
        create_metadata_row(
            dialog,
            "Gear type:",
            gear_type_var,
            is_combo=True,
            combo_values=[g.value for g in _GearType] + [""],
        )

        make_var = _tk.StringVar(value=cfg.get("gear_make", ""))
        create_metadata_row(dialog, "Gear make:", make_var)

        model_var = _tk.StringVar(value=cfg.get("gear_model", ""))
        create_metadata_row(dialog, "Gear model:", model_var)

        tone_var = _tk.StringVar(value=cfg.get("tone_type", ""))
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
        input_level_var = _tk.StringVar(value=cfg.get("input_level_dbu", ""))
        _ttk.Entry(level_frame, textvariable=input_level_var, width=15).pack(
            side=_tk.LEFT, padx=5
        )
        _ttk.Label(level_frame, text="Output (dBu):", width=20, anchor=_tk.W).pack(
            side=_tk.LEFT, padx=(20, 0)
        )
        output_level_var = _tk.StringVar(value=cfg.get("output_level_dbu", ""))
        _ttk.Entry(level_frame, textvariable=output_level_var, width=15).pack(
            side=_tk.LEFT, padx=5
        )

        def on_add():
            # Save settings to config
            _config.save({
                "default_architectures": [arch.value for arch, var in arch_vars.items() if var.get()],
                "output_template": output_template_var.get(),
                "dry_path": input_var.get(),
                "wet_path": output_var.get(),
                "default_destination": dest_var.get(),
                "model_name": name_var.get(),
                "modeled_by": modeled_by_var.get(),
                "gear_type": gear_type_var.get(),
                "gear_make": make_var.get(),
                "gear_model": model_var.get(),
                "tone_type": tone_var.get(),
                "input_level_dbu": input_level_var.get(),
                "output_level_dbu": output_level_var.get(),
            })

            selected_archs = [arch for arch, var in arch_vars.items() if var.get()]
            if not selected_archs:
                _tk.messagebox.showerror(
                    "Error", "Please select at least one architecture"
                )
                return

            # Get shared fields
            train_dest = _Path(dest_var.get()) if dest_var.get() else None
            if train_dest and not train_dest.exists():
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

            batch_guid = batch_guid_var.get() if batch_guid_var.get() else None

            # Get input and output paths
            input_path = _Path(input_var.get())
            output_path = _Path(output_var.get())

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

            # Add jobs for each architecture
            for arch in selected_archs:
                job_id = f"{_uuid.uuid4().hex[:8]}"
                job = TrainingJob(
                    job_id=job_id,
                    input_path=input_path,
                    output_path=output_path,
                    train_destination=train_dest,
                    architecture=arch,
                    output_template=output_template_var.get(),
                    batch_guid=batch_guid,
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
