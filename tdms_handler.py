from nptdms import TdmsFile
import numpy as np

class TdmsHandler:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.time_axis = None
        self.channel_data = {}
        self._load()

    def _load(self):
        tdms_file = TdmsFile.read(self.file_path)
        group = tdms_file.groups()[0]

        wf_increment = 1.0
        for ch in group.channels():
            if "wf_increment" in ch.properties:
                wf_increment = ch.properties["wf_increment"]
                break

        self.channel_data = {ch.name: ch.data for ch in group.channels()}
        num_samples = len(next(iter(self.channel_data.values())))
        self.time_axis = np.arange(num_samples) * wf_increment

    def get_time_axis(self):
        return self.time_axis

    def get_channels(self):
        return list(self.channel_data.keys())

    def get_data(self):
        return self.channel_data
