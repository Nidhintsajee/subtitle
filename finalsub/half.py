#!/usr/bin/python
import re

import operator

import string

import sys

import os.path as osp

from PyQt4 import QtCore, QtGui

from PyQt4.QtCore import *

from PyQt4.QtGui import *

import subprocess

from pathos.multiprocessing import ProcessingPool


path = 'key.png'

class QDataViewer(QtGui.QWidget):
    def __init__(self):
        QtGui.QWidget.__init__(self)                       # Class Constructor or Initialization method
        # Layout Init.

        self.setGeometry(650, 200, 400, 500)               # Position (OnScreen x pos, OnScreen y pos, Size x, Size y) 
        self.setWindowTitle('SubTitle Generator')
        self.setFixedSize(400, 500)
        # self.setWindowIcon(QtGui.QIcon(path))

        self.quitButton = QtGui.QPushButton('QUIT', self)
        self.quitButton.setGeometry(320, 400, 60, 35)
        
        self.filepath = QtGui.QLineEdit(self)
        self.filepath.setGeometry(30, 20, 250, 35)

        self.uploadButton = QtGui.QPushButton('UPLOAD', self)
        self.uploadButton.setGeometry(300, 20, 80, 35)

        self.PhraseButton = QtGui.QPushButton('Create SubTitle', self)
        self.PhraseButton.setGeometry(90, 150, 180, 35)
        
        self.label = QtGui.QLabel(self)
        self.label.setText("Converting speech regions to FLAC files")
        self.label.setGeometry(60, 200, 300, 30)

        self.progress1 = QtGui.QProgressBar(self)
        self.progress1.setGeometry(40, 250, 300, 30)
        
        self.connect(self.quitButton,   QtCore.SIGNAL('clicked()'), QtGui.qApp, QtCore.SLOT('quit()'))
        self.connect(self.uploadButton, QtCore.SIGNAL('clicked()'), self.open)
        self.PhraseButton.clicked.connect(lambda:self.subtitle_gen())

        self.palette = QtGui.QPalette()
        self.palette.setBrush(QtGui.QPalette.Background,QtGui.QBrush(QtGui.QPixmap("DarkBackground.jpg")))
        self.setPalette(self.palette)

    def closeEvent(self, event):
        self.reply = QtGui.QMessageBox.critical(self, 'Message',"Are you sure to quit?", QtGui.QMessageBox.Yes,QtGui.QMessageBox.No)
        if self.reply == QtGui.QMessageBox.Yes:
            event.accept() 
            print "Clicked YES to Quit"
        else:
            event.ignore()
            print "Clicked NO"      


    def open (self):
        self.filename = QtGui.QFileDialog.getOpenFileName(self, 'Open MP4 File', "", "*.mp4")
        # print 'Path file :', self.filename
        self.filepath.setText(self.filename)
        return self.filename
    

    def subtitle_gen(self):
        import argparse
        import audioop
        from googleapiclient.discovery import build
        import json
        import math
        import multiprocessing
        import os
        import requests
        import subprocess
        import sys
        import tempfile
        import wave
        import dill

        from progressbar import ProgressBar, Percentage, Bar, ETA

    
        from autosub.formatters import FORMATTERS

        def percentile(arr, percent):
            arr = sorted(arr)
            k = (len(arr) - 1) * percent
            f = math.floor(k)
            c = math.ceil(k)
            if f == c: return arr[int(k)]
            d0 = arr[int(f)] * (c - k)
            d1 = arr[int(c)] * (k - f)
            return d0 + d1


        class FLACConverter(object):
            def __init__(self, source_path, include_before=0.25, include_after=0.25):
                self.source_path = source_path
                self.include_before = include_before
                self.include_after = include_after

            def __call__(self, region):
                try:
                    start, end = region
                    start = max(0, start - self.include_before)
                    end += self.include_after
                    # temp = tempfile.NamedTemporaryFile(suffix='.flac')
                    temp =tempfile.NamedTemporaryFile(suffix='.flac',delete=False)
                    # print "temp file",temp.name

                    command = [
                    "ffmpeg", "-y", "-i", 
                    self.source_path, 
                    "-ss", str(start), 
                    "-t", str(end - start),
                    "-loglevel", 
                    "error", 
                    temp.name
                    ]

                    subprocess.check_output(command)
                 
                    os.system('stty sane')
                    return temp.read()
                    # return open(temp.name,"rb").read()
                except KeyboardInterrupt:
                    return




        def extract_audio(filename, channels=1, rate=16000):
            temp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            command = ["ffmpeg", "-y", "-i", filename, "-ac", str(channels), "-ar", str(rate), "-loglevel", "error", temp.name]
            # print "command",command
            subprocess.check_output(command)
            return temp.name, rate


        def find_speech_regions(filename, frame_width=4096, min_region_size=0.5, max_region_size=6):
            reader = wave.open(filename)
            sample_width = reader.getsampwidth()
            rate = reader.getframerate()
            n_channels = reader.getnchannels()

            total_duration = reader.getnframes() / rate
            chunk_duration = float(frame_width) / rate

            n_chunks = int(total_duration / chunk_duration)
            energies = []

            for i in range(n_chunks):
                chunk = reader.readframes(frame_width)
                energies.append(audioop.rms(chunk, sample_width * n_channels))

            threshold = percentile(energies, 0.2)

            elapsed_time = 0

            regions = []
            region_start = None

            for energy in energies:
                elapsed_time += chunk_duration

                is_silence = energy <= threshold
                max_exceeded = region_start and elapsed_time - region_start >= max_region_size

                if (max_exceeded or is_silence) and region_start:
                    if elapsed_time - region_start >= min_region_size:
                        regions.append((region_start, elapsed_time))
                    region_start = None

                elif (not region_start) and (not is_silence):
                    region_start = elapsed_time

            return regions


        def main():
            parser = argparse.ArgumentParser()
            parser.add_argument('source_path', help="Path to the video or audio file to subtitle", nargs='?')
            parser.add_argument('-C', '--concurrency', help="Number of concurrent API requests to make", type=int, default=10)
            parser.add_argument('-o', '--output',
                                help="Output path for subtitles (by default, subtitles are saved in \ the same directory and name as the source path)")
            parser.add_argument('-F', '--format', help="Destination subtitle format", default="srt")
            parser.add_argument('-S', '--src-language', help="Language spoken in source file", default="en")
            parser.add_argument('-D', '--dst-language', help="Desired language for the subtitles", default="en")
            parser.add_argument('-K', '--api-key',
                                help="The Google Translate API key to be used. (Required for subtitle translation)")
            parser.add_argument('--list-formats', help="List all available subtitle formats", action='store_true')
            parser.add_argument('--list-languages', help="List all available source/destination languages", action='store_true')

            if (os.name == "posix"):
                print os.system("uname -a")
            else:
                print "unknown OS"


            args = parser.parse_args()
            # print "arguments",args
            args.source_path = str(self.filename)
            print args.source_path,"SOURCE PATH"
            # print "CONCURRENCY >>>", args.concurrency
            # print args
            path = args.source_path[:-3]
            srt_path = path+"srt"
            print srt_path

            
            audio_filename, audio_rate = extract_audio(args.source_path)
            regions = find_speech_regions(audio_filename)
            pool = ProcessingPool(args.concurrency)
            converter = FLACConverter(source_path=audio_filename)
            
            transcripts = []
            if regions:
                try:
                    widgets = ["Converting speech regions to FLAC files: ", Percentage(), ' ', Bar(), ' ', ETA()]
                    pbar = ProgressBar(widgets=widgets, maxval=len(regions)).start()
                    extracted_regions = []
                    for i, extracted_region in enumerate(pool.imap(converter, regions)):
                        extracted_regions.append(extracted_region)
                        pbar.update(i)
                        self.progress1.setValue(i)
                    pbar.finish()

                    

                except KeyboardInterrupt:
                    pbar.finish()
                    pool.terminate()
                    pool.join()
                    print "Cancelling transcription"
                    return 1

            
            os.remove(audio_filename)

            return 0

        main()


        
def maingui():
    app = QtGui.QApplication(sys.argv)
    mw  = QDataViewer()
    mw.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    maingui()



