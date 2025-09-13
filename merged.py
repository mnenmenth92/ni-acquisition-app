import nidaqmx
from nidaqmx.constants import AcquisitionType, TerminalConfiguration, LoggingMode, VoltageUnits
from nidaqmx.stream_readers import AnalogMultiChannelReader
from nptdms import TdmsFile
import matplotlib.pyplot as plt
from matplotlib.widgets import Button
import numpy as np
import os
from datetime import datetime
from threading import Thread, Event
from tkinter import Tk
from tkinter.filedialog import askopenfilename, asksaveasfilename
import configparser

script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, "config.ini")
config = configparser.ConfigParser()
config.optionxform = str
config.read(config_path)

device = config.get("global", "device")
channel_dict = {}
for name, val in config.items("channels"):
    parts = [p.strip() for p in val.split(',')]
    channel_dict[name] = {
        'channel': parts[0],
        'terminal': parts[1],
        'scale': parts[2] if len(parts) > 2 else None
    }

fig, ax = plt.subplots(figsize=(10, 5))
plt.subplots_adjust(left=0.1, right=0.95, top=0.8, bottom=0.1)
line_plots = {}
for ch_name in channel_dict.keys():
    line_plots[ch_name], = ax.plot([], [], label=ch_name)
ax.set_xlabel("Time (s)")
ax.set_ylabel("Voltage (V)")
ax.set_title("DAQ Measurement & TDMS Viewer")
ax.legend()

stop_event = Event()
task = None
reader = None
acquiring = False
max_samples = 5000 * 60

channel_names = list(channel_dict.keys())
data_buffer = np.zeros((len(channel_names), max_samples), dtype=np.float64)
time_buffer = np.zeros(max_samples, dtype=np.float64)
current_time_axis = None
current_channel_data = None

def get_tdms_filename():
    save_dir = os.path.join(script_dir, "Measurements")
    os.makedirs(save_dir, exist_ok=True)
    dt_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(save_dir, f"measurement_{dt_str}.tdms")

def acquire_data(tdms_file_path):
    global task, reader, data_buffer, time_buffer, acquiring
    idx = 0
    n_ch = len(channel_names)

    while not stop_event.is_set():
        available = task.in_stream.avail_samp_per_chan
        num_to_read = min(available, 1000)
        if num_to_read > 0:
            temp_data = np.zeros((n_ch, num_to_read), dtype=np.float64)
            reader.read_many_sample(temp_data, number_of_samples_per_channel=num_to_read, timeout=1.0)

            data_buffer = np.roll(data_buffer, -num_to_read, axis=1)
            data_buffer[:, -num_to_read:] = temp_data

            time_buffer = np.roll(time_buffer, -num_to_read)
            time_buffer[-num_to_read:] = (idx + np.arange(num_to_read)) / 5000
            idx += num_to_read

            for i, ch_name in enumerate(channel_names):
                line_plots[ch_name].set_data(time_buffer, data_buffer[i, :])
            ax.relim()
            ax.autoscale_view()
            ax.set_title("Real-Time Acquisition")
            ax.legend(channel_names)
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
    global task, reader, stop_event, line_plots, acquiring, data_buffer, time_buffer
    if not acquiring:
        stop_event.clear()
        tdms_file_path = get_tdms_filename()

        data_buffer[:] = 0
        time_buffer[:] = 0
        ax.clear()
        for ch_name in channel_names:
            line_plots[ch_name], = ax.plot([], [], label=ch_name)
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Voltage (V)")
        ax.set_title("Real-Time Acquisition")
        ax.legend()
        fig.canvas.draw()

        task = nidaqmx.Task()
        for ch_name, ch_info in channel_dict.items():
            term_conf = getattr(TerminalConfiguration, ch_info['terminal'])
            if ch_info['scale']:
                task.ai_channels.add_ai_voltage_chan(
                    f"{device}/{ch_info['channel']}",
                    terminal_config=term_conf,
                    units=VoltageUnits.FROM_CUSTOM_SCALE,
                    custom_scale_name=ch_info['scale']
                )
            else:
                task.ai_channels.add_ai_voltage_chan(f"{device}/{ch_info['channel']}", terminal_config=term_conf)

        task.timing.cfg_samp_clk_timing(rate=5000, sample_mode=AcquisitionType.CONTINUOUS)
        task.in_stream.input_buf_size = 10000
        tdms_file_path = get_tdms_filename()
        task.in_stream.configure_logging(file_path=tdms_file_path,
                                         logging_mode=LoggingMode.LOG_AND_READ)

        reader = AnalogMultiChannelReader(task.in_stream)
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
    global current_time_axis, current_channel_data, line_plots
    if acquiring:
        print("Cannot load TDMS while acquiring!")
        return

    Tk().withdraw()
    file_path = askopenfilename(title="Select TDMS file", filetypes=[("TDMS files", "*.tdms")],
                                initialdir=script_dir)
    if not file_path:
        print("No file selected!")
        return

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
    line_plots.clear()
    for name, data in current_channel_data.items():
        line_plots[name], = ax.plot(current_time_axis, data, label=name)
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
    file_path = asksaveasfilename(title="Save CSV", defaultextension=".csv",
                                  filetypes=[("CSV files", "*.csv")],
                                  initialdir=script_dir,
                                  initialfile="exported_data.csv")
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
