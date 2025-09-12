import nidaqmx
from nidaqmx.constants import AcquisitionType, TerminalConfiguration, LoggingMode, VoltageUnits
from nidaqmx.stream_readers import AnalogSingleChannelReader
import matplotlib.pyplot as plt
from matplotlib.widgets import Button
import numpy as np
import os
from datetime import datetime
from threading import Thread, Event


# -----------------------------
# Configuration
# -----------------------------
device_channel = "Dev3/ai4"  # change your AI channel here
fs_acq = 5000  # sample rate in Hz
buffer_size = 1000  # samples per read
display_time = 60  # seconds of data to display

max_samples = fs_acq * display_time

# -----------------------------
# Global variables
# -----------------------------
fig, ax = plt.subplots(figsize=(10, 5))
plt.subplots_adjust(bottom=0.25)  # leave space for buttons
line_plot, = ax.plot([], [], label=device_channel)
ax.set_xlabel("Time (s)")
ax.set_ylabel("Voltage (V)")
ax.set_title("Real-Time Acquisition (Last 60 s)")
ax.legend()

stop_event = Event()
task = None
reader = None

data_buffer = np.zeros(max_samples, dtype=np.float64)
time_buffer = np.zeros(max_samples, dtype=np.float64)

# -----------------------------
# Helper functions
# -----------------------------
def get_tdms_filename():
    save_dir = os.path.expanduser("~/Documents/Measurements")
    os.makedirs(save_dir, exist_ok=True)
    dt_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(save_dir, f"measurement_{dt_str}.tdms")

def acquire_data(tdms_file_path):
    global task, reader, data_buffer, time_buffer
    idx = 0

    while not stop_event.is_set():
        available = task.in_stream.avail_samp_per_chan
        num_to_read = min(available, buffer_size)
        if num_to_read > 0:
            temp_data = np.zeros(num_to_read, dtype=np.float64)
            reader.read_many_sample(temp_data, number_of_samples_per_channel=num_to_read, timeout=1.0)

            # Shift old data and append new
            data_buffer = np.roll(data_buffer, -num_to_read)
            data_buffer[-num_to_read:] = temp_data

            time_buffer = np.roll(time_buffer, -num_to_read)
            time_buffer[-num_to_read:] = (idx + np.arange(num_to_read)) / fs_acq
            idx += num_to_read

            # Update plot
            line_plot.set_data(time_buffer, data_buffer)
            ax.relim()
            ax.autoscale_view()
            fig.canvas.draw_idle()

    # Stop the task when done
    task.stop()
    task.close()
    print(f"Acquisition stopped. TDMS saved to {tdms_file_path}")

# -----------------------------
# Button callbacks
# -----------------------------
def start_acq(event=None):
    global task, reader, stop_event
    stop_event.clear()
    tdms_file_path = get_tdms_filename()

    task = nidaqmx.Task()
    task.ai_channels.add_ai_voltage_chan(
        device_channel,
        terminal_config=TerminalConfiguration.RSE,
        min_val=-10.0,
        max_val=10.0,
        units=VoltageUnits.VOLTS
    )
    task.timing.cfg_samp_clk_timing(rate=fs_acq, sample_mode=AcquisitionType.CONTINUOUS)
    task.in_stream.input_buf_size = buffer_size * 10
    task.in_stream.configure_logging(file_path=tdms_file_path, logging_mode=LoggingMode.LOG_AND_READ)

    reader = AnalogSingleChannelReader(task.in_stream)

    # **Start the task before reading samples**
    task.start()

    # Start acquisition in a separate thread
    acq_thread = Thread(target=acquire_data, args=(tdms_file_path,), daemon=True)
    acq_thread.start()
    print("Acquisition started...")


def stop_acq(event=None):
    stop_event.set()

# -----------------------------
# GUI buttons
# -----------------------------
ax_start = plt.axes([0.02, 0.88, 0.1, 0.07])
btn_start = Button(ax_start, "Start")
btn_start.on_clicked(start_acq)

ax_stop = plt.axes([0.14, 0.88, 0.1, 0.07])
btn_stop = Button(ax_stop, "Stop")
btn_stop.on_clicked(stop_acq)

plt.show()
