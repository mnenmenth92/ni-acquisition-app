import nidaqmx
from nidaqmx.constants import AcquisitionType, TerminalConfiguration, LoggingMode, VoltageUnits
from nidaqmx.stream_readers import AnalogMultiChannelReader
import numpy as np
import os
import configparser
from datetime import datetime
from threading import Thread, Event
from hardware_base import HardwareBase
import sys
import tkinter as tk
from tkinter import messagebox

"""
Safe version check for nidaqmx
Reason: When running a PyInstaller executable, importlib.metadata
may fail to find package metadata for nidaqmx, causing a crash.
This try/except ensures a fallback version is used so the program runs.
"""

try:
    from importlib.metadata import version
    nidaqmx_version = version("nidaqmx")
except Exception:
    nidaqmx_version = "1.2.0"  # hard-coded version



class MeasurementHandler(HardwareBase):
    def __init__(self, config_path: str):

        # Determine base path depending on environment
        if getattr(sys, 'frozen', False):
            # Running inside PyInstaller exe
            base_path = os.path.dirname(sys.executable)
        else:
            # Running as a normal script
            base_path = os.path.dirname(os.path.abspath(__file__))

        # Full path to config.ini
        self.config_path = os.path.join(base_path, "config.ini")

        # Load config
        self.config = configparser.ConfigParser()
        self.config.read(self.config_path)

        self.device = self.config.get("global", "device")


        self.channel_dict = {}
        for name, val in self.config.items("channels"):
            parts = [p.strip() for p in val.split(",")]
            self.channel_dict[name] = {
                'channel': parts[0],
                'terminal': parts[1],
                'scale': parts[2] if len(parts) > 2 else None,
                'max': int(parts[3]),
                'unit': parts[4]
            }

        self.task = None
        self.reader = None
        self.stop_event = Event()
        self.acquiring = False

        self.sample_rate = 100
        self.max_samples = self.sample_rate * 60
        self.channel_names = list(self.channel_dict.keys())
        self.channel_units = [x['unit'] for x in list(self.channel_dict.values())]
        self.data_buffer = np.zeros((len(self.channel_names), self.max_samples), dtype=np.float64)
        self.time_buffer = np.zeros(self.max_samples, dtype=np.float64)

        self._stream_callback = None  # function to push data to UI
        self.tdms_file_path = None

    def _get_tdms_filename(self):
        save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Measurements")
        os.makedirs(save_dir, exist_ok=True)
        dt_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        return os.path.join(save_dir, f"measurement_{dt_str}.tdms")

    def _acquire_loop(self, tdms_file_path):
        idx = 0
        n_ch = len(self.channel_names)

        while not self.stop_event.is_set():
            available = self.task.in_stream.avail_samp_per_chan
            num_to_read = min(available, 1000)
            if num_to_read > 0:
                temp_data = np.zeros((n_ch, num_to_read), dtype=np.float64)
                self.reader.read_many_sample(temp_data, number_of_samples_per_channel=num_to_read, timeout=1.0)

                self.data_buffer = np.roll(self.data_buffer, -num_to_read, axis=1)
                self.data_buffer[:, -num_to_read:] = temp_data

                self.time_buffer = np.roll(self.time_buffer, -num_to_read)
                self.time_buffer[-num_to_read:] = (idx + np.arange(num_to_read)) / self.sample_rate
                idx += num_to_read

                if self._stream_callback:
                    self._stream_callback(self.time_buffer, self.data_buffer)

        self.task.stop()
        self.task.close()
        self.acquiring = False

    def set_stream_callback(self, callback):
        """Callback gets (time_buffer, data_buffer)."""
        self._stream_callback = callback

    def start_acquisition(self):
        if self.acquiring:
            return

        self.stop_event.clear()
        self.tdms_file_path = self._get_tdms_filename()

        self.data_buffer[:] = 0
        self.time_buffer[:] = 0

        self.task = nidaqmx.Task()
        try:
            for ch_name, ch_info in self.channel_dict.items():
                term_conf = getattr(TerminalConfiguration, ch_info['terminal'])
                if ch_info['scale']:
                    self.task.ai_channels.add_ai_voltage_chan(
                        f"{self.device}/{ch_info['channel']}",
                        terminal_config=term_conf,
                        units=VoltageUnits.FROM_CUSTOM_SCALE,
                        custom_scale_name=ch_info['scale'],
                        max_val=ch_info['max']
                    )
                else:
                    self.task.ai_channels.add_ai_voltage_chan(
                        f"{self.device}/{ch_info['channel']}",
                        terminal_config=term_conf)

            self.task.timing.cfg_samp_clk_timing(rate=self.sample_rate,
                                                 sample_mode=AcquisitionType.CONTINUOUS,
                                                 samps_per_chan=1000)
            self.task.in_stream.input_buf_size = 10000
            self.task.in_stream.configure_logging(file_path=self.tdms_file_path,
                                                  logging_mode=LoggingMode.LOG_AND_READ)

            self.reader = AnalogMultiChannelReader(self.task.in_stream)
            self.task.start()

            acq_thread = Thread(target=self._acquire_loop, args=(self.tdms_file_path,), daemon=True)
            acq_thread.start()
            self.acquiring = True
        except Exception as e:

            root = tk.Tk()
            root.withdraw()  # hide main window
            if "Custom scale specified does not exist" in str(e):
                messagebox.showerror(
                    "Missing NI MAX Scale",
                    f"The custom scale '{ch_info['scale']}' does not exist.\n\n"
                    f"Please create this scale in NI MAX and restart acquisition."
                )
            else:
                messagebox.showerror(
                    "Missing NI MAX Issue",
                    f"Task creation issue.\n\n"
                    f"Not defined NI task creation issue."
                )
            if self.task:
                self.task.close()
            self.task = None
            self.acquiring = False
    def stop_acquisition(self):
        if self.acquiring:
            self.stop_event.set()

    def is_acquiring(self) -> bool:
        return self.acquiring


a = MeasurementHandler("config.ini")