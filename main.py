import sys
import os
import numpy as np
import pyqtgraph as pg
import pyqtgraph.exporters
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QMessageBox
)
from measurement_handler import MeasurementHandler
from tdms_handler import TdmsHandler

from PySide6.QtCore import QObject, Signal

class PlotUpdater(QObject):
    data_ready = Signal(object, object)  # time_buffer, data_buffer

class MainApp(QMainWindow):
    def __init__(self, config_path: str):
        super().__init__()
        self.setWindowTitle("DAQ Measurement")
        self.resize(1000, 600)


        # Change plot background/foreground colors
        pg.setConfigOption("background", "w")   # white background
        pg.setConfigOption("foreground", "k")   # black axes, labels, grid

        # Measurement handler
        self.mh = MeasurementHandler(config_path)
        self.mh.set_stream_callback(self.update_plot)

        self.updater = PlotUpdater()
        # connect the signal to update_plot (runs in GUI thread)
        self.updater.data_ready.connect(self.update_plot)
        # tell MeasurementHandler to call the signal instead of update_plot directly
        self.mh.set_stream_callback(self.updater.data_ready.emit)

        # State variables
        self.current_time_axis = None
        self.current_channel_data = None
        self.curves = {}

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 5, 0, 5)
        layout.setSpacing(5)

        # Plot widget
        self.plot_widget = pg.PlotWidget(title="DAQ Measurement & TDMS Viewer")
        self.plot_widget.setLabel("bottom", "Time", units="s")
        self.plot_widget.setLabel("left", "Voltage", units="V")
        self.plot_widget.showGrid(x=True, y=True)
        self.plot_widget.addLegend()
        # self.plot_widget.setBackground(None)
        layout.addWidget(self.plot_widget)

        self.view_box = self.plot_widget.getViewBox()
        # Buttons
        button_layout = QHBoxLayout()
        layout.addLayout(button_layout)


        # Initialize plot with channel curves
        self.create_curves(self.mh.channel_names)

        self.btn_toggle = QPushButton("Start")
        self.btn_toggle.clicked.connect(self.toggle_acq)
        self.btn_toggle.setStyleSheet("background-color: #d9f0d9;")

        self.btn_load = QPushButton("Load TDMS")
        self.btn_load.clicked.connect(self.load_tdms)

        self.btn_export = QPushButton("Export CSV")
        self.btn_export.clicked.connect(self.export_csv)
        self.btn_export.setEnabled(False)

        self.btn_export_png = QPushButton("Export PNG")
        self.btn_export_png.clicked.connect(self.export_png)
        self.btn_export_png.setEnabled(False)

        self.btn_autoscale = QPushButton("Autoscale")
        self.btn_autoscale.clicked.connect(self.autoscale_plot)

        buttons = [
            self.btn_toggle,
            self.btn_load,
            self.btn_export,
            self.btn_export_png,
            self.btn_autoscale
        ]

        for btn in buttons:
            btn.setFixedSize(80, 30)  # set uniform size
            button_layout.addWidget(btn)

        button_layout.addStretch()

    def toggle_acq(self):
        if not self.mh.is_acquiring():
            # Reset curves and internal buffers for clean acquisition
            self.current_time_axis = None
            self.current_channel_data = None
            self.create_curves(self.mh.channel_names)

            # Start acquisition
            self.mh.start_acquisition()
            self.btn_toggle.setText("Stop")
            self.btn_toggle.setStyleSheet("background-color: #f0d9d9;")
            self.btn_load.setEnabled(False)
            self.btn_export.setEnabled(False)
            self.btn_export_png.setEnabled(False)
            self.btn_autoscale.setEnabled(False)
            self.view_box.setMouseEnabled(x=False, y=False)
            self.view_box.enableAutoRange(axis=pg.ViewBox.XYAxes)
        else:
            # Stop acquisition
            self.mh.stop_acquisition()
            self.btn_toggle.setText("Start")
            self.btn_toggle.setStyleSheet("background-color: #d9f0d9;")
            self.btn_load.setEnabled(True)
            self.btn_export.setEnabled(True)
            self.btn_export_png.setEnabled(True)
            self.btn_autoscale.setEnabled(True)
            self.view_box.setMouseEnabled(x=True, y=True)

    def update_plot(self, time_buffer, data_buffer):
        if not self.curves:  # nothing to update
            return
        for i, ch_name in enumerate(self.mh.channel_names):
            if ch_name in self.curves:
                self.curves[ch_name].setData(time_buffer, data_buffer[i, :])

        # Autoscale Y only
        if self.mh.is_acquiring():
            # compute min/max across all channels
            y_min = np.min(data_buffer)
            y_max = np.max(data_buffer)
            self.view_box.setYRange(y_min, y_max, padding=0.1)
            self.view_box.setXRange(time_buffer[0], time_buffer[-1], padding=0.0)

    def load_tdms(self):

        # buttons where disabled when app was started
        self.btn_export_png.setEnabled(True)
        self.btn_export.setEnabled(True)

        if self.mh.is_acquiring():
            QMessageBox.warning(self, "Warning", "Cannot load TDMS while acquiring!")
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select TDMS file", os.path.dirname(os.path.abspath(__file__)),
            "TDMS files (*.tdms)"
        )
        if not file_path:
            return

        tdms = TdmsHandler(file_path)
        self.current_time_axis = tdms.get_time_axis()
        self.current_channel_data = tdms.get_data()

        self.create_curves(list(self.current_channel_data.keys()),
                           time_axis=self.current_time_axis,
                           data_dict=self.current_channel_data)
        self.view_box.enableAutoRange(axis=pg.ViewBox.XYAxes)

    def export_csv(self):
        if self.mh.is_acquiring():
            QMessageBox.warning(self, "Warning", "Cannot export while acquiring!")
            return

        if self.current_time_axis is not None and self.current_channel_data is not None:
            tdms_path = None  # already loaded TDMS
        elif self.mh.tdms_file_path:
            tdms_path = self.mh.tdms_file_path
        else:
            QMessageBox.information(self, "Info", "No data to export!")
            return

        if tdms_path is not None:
            tdms = TdmsHandler(tdms_path)
            time_axis = tdms.get_time_axis()
            data_dict = tdms.get_data()
        else:
            time_axis = self.current_time_axis
            data_dict = self.current_channel_data

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save CSV", os.path.dirname(os.path.abspath(__file__)),
            "CSV files (*.csv)"
        )
        if not file_path:
            return

        header = "Time," + ",".join(data_dict.keys())
        data_matrix = np.column_stack([time_axis] + [v for v in data_dict.values()])
        np.savetxt(file_path, data_matrix, delimiter=",", header=header, comments="")
        QMessageBox.information(self, "Success", f"Data exported to {file_path}")

    def autoscale_plot(self):
        """
        Reset the plot view to auto-scale both axes.
        """
        self.view_box.enableAutoRange(axis=pg.ViewBox.XYAxes)

    def export_png(self):
        if self.curves == {}:
            QMessageBox.information(self, "Info", "No data to export!")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save PNG", os.path.dirname(os.path.abspath(__file__)),
            "PNG files (*.png)"
        )
        if not file_path:
            return

        # Export plot using pyqtgraph ImageExporter
        exporter = pg.exporters.ImageExporter(self.plot_widget.plotItem)
        exporter.parameters()['width'] = 1200  # optional: set image width
        exporter.export(file_path)

        QMessageBox.information(self, "Success", f"Plot exported to {file_path}")


    def create_curves(self, channel_names, time_axis=None, data_dict=None):
        """
        Create curves with assigned colors.

        Parameters:
        - channel_names: list of channel names
        - time_axis: optional, x-axis data (for TDMS)
        - data_dict: optional, dictionary of channel -> y-axis data (for TDMS)
        """
        self.plot_widget.clear()
        self.curves.clear()

        colors = ['r', 'g', 'b', 'c', 'm', 'y', 'k']  # default color cycle
        self.channel_colors = {}

        for i, ch_name in enumerate(channel_names):
            color = colors[i % len(colors)]
            self.channel_colors[ch_name] = color

            if data_dict is not None and time_axis is not None:
                y_data = data_dict[ch_name]
                curve = self.plot_widget.plot(time_axis, y_data, pen=pg.mkPen(color=color, width=2), name=ch_name)
            else:
                # initialize empty curve for live acquisition
                curve = self.plot_widget.plot([], [], pen=pg.mkPen(color=color, width=2), name=ch_name)

            self.curves[ch_name] = curve

        # add legend
        self.plot_widget.addLegend()


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "config.ini")

    app = QApplication(sys.argv)
    window = MainApp(config_path)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
