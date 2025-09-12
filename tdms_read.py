from nptdms import TdmsFile
import matplotlib.pyplot as plt
from matplotlib.widgets import Button
import numpy as np
import os
from tkinter import Tk
from tkinter.filedialog import askopenfilename, asksaveasfilename

current_time_axis = None
current_channel_data = None

def load_and_plot(event=None):
    global current_time_axis, current_channel_data
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
    ax.set_title("Pressure vs Time")
    ax.legend()
    ax.grid(True)
    fig.canvas.draw()


def export_csv(event=None):
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


fig, ax = plt.subplots(figsize=(10,5))
plt.subplots_adjust(left=0.1, right=0.95, top=0.8, bottom=0.1)

# Load TDMS button
ax_load = plt.axes([0.02, 0.88, 0.15, 0.07])
btn_load = Button(ax_load, "Load TDMS File")
btn_load.on_clicked(load_and_plot)

# Export CSV button
ax_export = plt.axes([0.18, 0.88, 0.15, 0.07])
btn_export = Button(ax_export, "Export CSV")
btn_export.on_clicked(export_csv)

plt.show()
