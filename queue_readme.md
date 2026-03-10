# Training Queue Feature

## Overview

The NAM trainer now includes a **Training Queue** system that allows you to queue up multiple training jobs and process them in the background, rather than training one model at a time.

## Features

### Queue Window
- **View all queued jobs** in a sortable table
- **Status tracking**: Pending, Queued, Processing, Completed, Failed, Cancelled
- **Results display**: Shows ESR and wall time for completed jobs
- **Job management**: Add, remove, and delete jobs from the queue

### Start/Stop Controls
- **Start Queue**: Begins processing queued jobs
- **Stop Queue**: Pauses processing without losing queued jobs

### Job Details
Each job in the queue tracks:
- Input file path
- Output file path  
- Architecture (Standard, Lite, Feather, Nano)
- Status (with visual indicators)
- Final ESR (Error-to-Signal Ratio)
- Processing wall time
- Output `.nam` model file path (when complete)

## How to Use

### Adding Jobs to the Queue

1. Click the **"Add to Queue"** button below the "Train" button
2. In the dialog that appears:
   - Select the **Input file** (dry signal)
   - Select the **Output file** (reamped recording through your gear)
   - Check the **Architectures** you want to train (can select multiple)
3. Click "Add to Queue"

### Processing the Queue

1. Open the queue window (it opens automatically when you click "Add to Queue")
2. Click **"Start Queue"** to begin processing
3. Jobs will be processed sequentially
4. Watch the table update in real-time:
   - **Processing** jobs show a spinner or status
   - **Completed** jobs show the ESR and processing time
   - **Failed** jobs show an error message

### Managing Jobs

- **Delete a job**: Select it in the table and press Delete key, or click the delete button
- **Refresh**: Click "Refresh" to update the queue status
- **View completed models**: Navigate to the training output directory to find the generated `.nam` files

## Architecture Selection

You can now select **multiple architectures** for each job via checkboxes in the Advanced Options dialog:
- **Standard**: Full-featured WaveNet
- **Lite**: Smaller, faster model
- **Feather**: Even more compact
- **Nano**: Smallest possible model

When multiple architectures are selected, the queue will train a separate model for each architecture, with filenames like:
- `guitar_stanard.nam`
- `guitar_lite.nam`
- `guitar_feather.nam`
- `guitar_nano.nam`

## Background Processing

Jobs run in a background thread, so the GUI remains responsive while training. The queue window can be minimized and will continue processing in the background.

## Notes

- Jobs are processed **sequentially** (one at a time)
- You can add as many jobs as you want to the queue
- Failed jobs can be removed and re-added with adjusted settings
- The queue persists while the trainer is open

## Files Modified

- `nam/train/gui/__init__.py` - Added queue button and integration
- `nam/train/gui/_resources/queue.py` - Queue management logic
- `nam/train/gui/_resources/queue_window.py` - Queue GUI interface