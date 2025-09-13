import nidaqmx
from nidaqmx.constants import AcquisitionType, TerminalConfiguration, LoggingMode, VoltageUnits
from nidaqmx.stream_readers import AnalogSingleChannelReader
from nptdms import TdmsFile
import matplotlib.pyplot as plt
from matplotlib.widgets import Button
import numpy as np
import os
from datetime import datetime
from threading import Thread, Event
from tkinter import Tk
from tkinter.filedialog import askopenfilename, asksaveasfilename

device_channel = "Dev3/ai4"
fs_acq = 5000
buffer_size = 1000
display_time = 60
max_samples = fs_acq * display_time

fig, ax = plt.subplots(figsize=(10, 5))
plt.subplots_adjust(left=0.1, right=0.95, top=0.8, bottom=0.1)
line_plot, = ax.plot([], [], label=device_channel)
ax.set_xlabel("Time (s)")
ax.set_ylabel("Voltage (V)")
ax.set_title("DAQ Measurement & TDMS Viewer")
ax.legend()

stop_event = Event()
task = None
reader = None

acquiring = False
data_buffer = np.zeros(max_samples, dtype=np.float64)
time_buffer = np.zeros(max_samples, dtype=np.float64)

current_time_axis = None
current_channel_data = None

def get_tdms_filename():
    save_dir = os.path.expanduser("~/Documents/Measurements")
    os.makedirs(save_dir, exist_ok=True)
    dt_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(save_dir, f"measurement_{dt_str}.tdms")


def acquire_data(tdms_file_path):
    global task, reader, data_buffer, time_buffer, acquiring
    idx = 0

    while not stop_event.is_set():
        available = task.in_stream.avail_samp_per_chan
        num_to_read = min(available, buffer_size)
        if num_to_read > 0:
            temp_data = np.zeros(num_to_read, dtype=np.float64)
            reader.read_many_sample(temp_data, number_of_samples_per_channel=num_to_read, timeout=1.0)

            data_buffer = np.roll(data_buffer, -num_to_read)
            data_buffer[-num_to_read:] = temp_data

            time_buffer = np.roll(time_buffer, -num_to_read)
            time_buffer[-num_to_read:] = (idx + np.arange(num_to_read)) / fs_acq
            idx += num_to_read

            line_plot.set_data(time_buffer, data_buffer)
            ax.relim()
            ax.autoscale_view()
            ax.set_title("Real-Time Acquisition")
            ax.legend([device_channel])
            fig.canvas.draw_idle()

    task.stop()
    task.close()
    acquiring = False
    btn_toggle.label.set_text("Start")
    btn_load.ax.set_visible(True)
    btn_export.ax.set_visible(True)
    fig.canvas.draw_idle()
    print(f"Acquisition stopped. TDMS saved to {tdms_file_path}")


def toggle_acq(event=None):
    global task, reader, stop_event, line_plot, acquiring, data_buffer, time_buffer
    if not acquiring:
        stop_event.clear()
        tdms_file_path = get_tdms_filename()

        data_buffer = np.zeros(max_samples, dtype=np.float64)
        time_buffer = np.zeros(max_samples, dtype=np.float64)

        ax.clear()
        line_plot, = ax.plot([], [], label=device_channel)
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Voltage (V)")
        ax.set_title("Real-Time Acquisition")
        ax.legend()
        fig.canvas.draw()

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
        task.start()

        acq_thread = Thread(target=acquire_data, args=(tdms_file_path,), daemon=True)
        acq_thread.start()
        acquiring = True
        btn_toggle.label.set_text("Stop")
        btn_load.ax.set_visible(False)
        btn_export.ax.set_visible(False)
        fig.canvas.draw_idle()
        print("Acquisition started...")
    else:
        stop_event.set()


def load_and_plot(event=None):
    global current_time_axis, current_channel_data, line_plot
    if acquiring:
        print("Cannot load TDMS while acquiring!")
        return

    Tk().withdraw()
    file_path = askopenfilename(
        title="Select TDMS file",
        filetypes=[("TDMS files", "*.tdms")],
        initialdir=os.path.expanduser("~/Documents/Measurements")
    )
    if not file_path:
        print("No file selected!")
        return

    print("Selected file:", file_path)
    tdms_file = TdmsFile.read(file_path)
    group = tdms_file.groups()[0]

    wf_increment = 1.0
    for ch in group.channels():
        if "wf_increment" in ch.properties:
            wf_increment = ch.properties["wf_increment"]
            break

    current_channel_data = {ch.name: ch.data for ch in group.channels()}
    num_samples = len(next(iter(current_channel_data.values())))
    current_time_axis = np.arange(num_samples) * wf_increment

    ax.clear()
    for name, data in current_channel_data.items():
        ax.plot(current_time_axis, data, label=name)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Voltage (V)")
    ax.set_title("TDMS Data Viewer")
    ax.legend()
    ax.grid(True)
    fig.canvas.draw()


def export_csv(event=None):
    global current_time_axis, current_channel_data
    if acquiring:
        print("Cannot export while acquiring!")
        return

    if current_time_axis is None or current_channel_data is None:
        print("No data to export!")
        return

    Tk().withdraw()
    file_path = asksaveasfilename(
        title="Save CSV",
        defaultextension=".csv",
        filetypes=[("CSV files", "*.csv")],
        initialdir=os.path.expanduser("~/Documents/Measurements"),
        initialfile="exported_data.csv"
    )
    if not file_path:
        print("Export cancelled!")
        return

    header = "Time," + ",".join(current_channel_data.keys())
    data_matrix = np.column_stack([current_time_axis] + [v for v in current_channel_data.values()])
    np.savetxt(file_path, data_matrix, delimiter=",", header=header, comments="")
    print(f"Data exported to {file_path}")


ax_toggle = plt.axes([0.02, 0.88, 0.1, 0.07])
btn_toggle = Button(ax_toggle, "Start")
btn_toggle.on_clicked(toggle_acq)

ax_load = plt.axes([0.14, 0.88, 0.15, 0.07])
btn_load = Button(ax_load, "Load TDMS")
btn_load.on_clicked(load_and_plot)

ax_export = plt.axes([0.3, 0.88, 0.15, 0.07])
btn_export = Button(ax_export, "Export CSV")
btn_export.on_clicked(export_csv)

plt.show()