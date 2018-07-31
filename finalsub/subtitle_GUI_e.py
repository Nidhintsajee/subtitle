#!/usr/bin/env python
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

        self.label2 = QtGui.QLabel(self)
        self.label2.setText("Performing speech recognition")
        self.label2.setGeometry(90, 300,300, 30)

        self.progress2 = QtGui.QProgressBar(self)
        self.progress2.setGeometry(40, 350, 300, 30)             
        
        self.connect(self.quitButton,   QtCore.SIGNAL('clicked()'), QtGui.qApp, QtCore.SLOT('quit()'))
        self.connect(self.uploadButton, QtCore.SIGNAL('clicked()'), self.open)
        self.PhraseButton.clicked.connect(lambda:self.subtitle_gen())

        self.palette = QtGui.QPalette()
        self.palette.setBrush(QtGui.QPalette.Background,QtGui.QBrush(QtGui.QPixmap("DarkBackground.jpg")))
        self.setPalette(self.palette)

    def closeEvent(self, event):
        self.reply = QtGui.QMessageBox.critical(self, 'Message',"Are you sure to quit?", QtGui.QMessageBox.Yes,QtGui.QMessageBox.No)
        print self.reply
        if self.reply == QtGui.QMessageBox.Yes:
            event.accept() 
            print "Clicked YES to Quit"
        else:
            event.ignore()
            print "Clicked NO"      


    def open (self):
        self.filename = QtGui.QFileDialog.getOpenFileName(self, 'Open MP4 File', "", "*.mp4")
        print 'Path file :', self.filename
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

        from autosub.constants import LANGUAGE_CODES, \
            GOOGLE_SPEECH_API_KEY, GOOGLE_SPEECH_API_URL
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


        def is_same_language(lang1, lang2):
            return lang1.split("-")[0] == lang2.split("-")[0]


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
                    # if os.name == 'nt':
                    #     tempfile.tempdir = 'D:/temp'
                    temp = tempfile.NamedTemporaryFile(suffix='.flac')
                    command = [
                    "ffmpeg", "-y", "-i", 
                    self.source_path, 
                    "-ss", str(start), 
                    "-t", str(end - start),
                    "-loglevel", 
                    "error", 
                    temp.name
                    ]
                    subprocess.check_output(command, shell=True)
                    os.system('stty sane')
                    return temp.read()

                except KeyboardInterrupt:
                    return


        class SpeechRecognizer(object):
            def __init__(self, language="en", rate=44100, retries=3, api_key=GOOGLE_SPEECH_API_KEY):
                self.language = language
                self.rate = rate
                self.api_key = api_key
                self.retries = retries

            def __call__(self, data):
                try:
                    for i in range(self.retries):
                        url = GOOGLE_SPEECH_API_URL.format(lang=self.language, key=self.api_key)
                        headers = {"Content-Type": "audio/x-flac; rate=%d" % self.rate}

                        try:
                            resp = requests.post(url, data=data, headers=headers)
                        except requests.exceptions.ConnectionError:
                            continue

                        for line in resp.content.split("\n"):
                            try:
                                line = json.loads(line)
                                return line['result'][0]['alternative'][0]['transcript'].capitalize()
                            except:
                                # no result
                                continue

                except KeyboardInterrupt:
                    return


        class translator(object):
            def __init__(self, language, api_key, src, dst):
                self.language = language
                self.api_key = api_key
                self.service = build('translate', 'v2',
                                     developerKey=self.api_key)
                self.src = src
                self.dst = dst

            def __call__(self, sentence):
                try:
                    if not sentence: return
                    result = self.service.translations().list(
                        source=self.src,
                        target=self.dst,
                        q=[sentence]
                    ).execute()
                    if 'translations' in result and len(result['translations']) and \
                                    'translatedText' in result['translations'][0]:
                        return result['translations'][0]['translatedText']
                    return ""

                except KeyboardInterrupt:
                    return


        def extract_audio(filename, channels=1, rate=16000):
            temp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            command = ["ffmpeg", "-y", "-i", filename, "-ac", str(channels), "-ar", str(rate), "-loglevel", "error", temp.name]
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

            args = parser.parse_args()
            print args

            if (os.name == "posix"):
                args.source_path = str(self.filename)
            else:
                args.source_path = (str(self.filename)).replace("/","\\")
                pas = (args.source_path).replace("/","\\")
                args.source_path = pas
                print " Printing pas >>>",pas
            print args
            
            path = args.source_path[:-3]
            srt_path = path+"srt"

            if args.list_formats:
                print("List of formats:")
                for subtitle_format in FORMATTERS.keys():
                    print("{format}".format(format=subtitle_format))
                return 0

            if args.list_languages:
                print("List of all languages:")
                for code, language in sorted(LANGUAGE_CODES.items()):
                    print("{code}\t{language}".format(code=code, language=languages))
                return 0

            if args.format not in FORMATTERS.keys():
                print("Subtitle format not supported. Run with --list-formats to see all supported formats.")
                return 1

            if args.src_language not in LANGUAGE_CODES.keys():
                print("Source language not supported. Run with --list-languages to see all supported languages.")
                return 1

            if args.dst_language not in LANGUAGE_CODES.keys():
                print(
                    "Destination language not supported. Run with --list-languages to see all supported languages.")
                return 1

            if not args.source_path:
                print("Error: You need to specify a source path.")
                return 1

            audio_filename, audio_rate = extract_audio(args.source_path)

            regions = find_speech_regions(audio_filename)
            pool = ProcessingPool(args.concurrency)
            converter = FLACConverter(source_path=audio_filename)
            recognizer = SpeechRecognizer(language=args.src_language, rate=audio_rate, api_key=GOOGLE_SPEECH_API_KEY)

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

                    widgets = ["Performing speech recognition: ", Percentage(), ' ', Bar(), ' ', ETA()]
                    pbar = ProgressBar(widgets=widgets, maxval=len(regions)).start()

                    for i, transcript in enumerate(pool.imap(recognizer, extracted_regions)):
                        transcripts.append(transcript)
                        pbar.update(i)
                        self.progress2.setValue(i)
                    pbar.finish()
                    QMessageBox.about(self, "Subtitles created","Created at "+srt_path)
                    if not is_same_language(args.src_language, args.dst_language):
                        if args.api_key:
                            google_translate_api_key = args.api_key
                            translator = Translator(args.dst_language, google_translate_api_key, dst=args.dst_language,
                                                    src=args.src_language)
                            prompt = "Translating from {0} to {1}: ".format(args.src_language, args.dst_language)
                            widgets = [prompt, Percentage(), ' ', Bar(), ' ', ETA()]
                            pbar = ProgressBar(widgets=widgets, maxval=len(regions)).start()
                            translated_transcripts = []
                            for i, transcript in enumerate(pool.imap(translator, transcripts)):
                                translated_transcripts.append(transcript)
                                pbar.update(i)
                                self.progress2.setValue(i)
                            pbar.finish()
                            transcripts = translated_transcripts
                        else:
                            print "Error: Subtitle translation requires specified Google Translate API key. \See --help for further information."
                            return 1

                except KeyboardInterrupt:
                    pbar.finish()
                    pool.terminate()
                    pool.join()
                    print "Cancelling transcription"
                    return 1

            timed_subtitles = [(r, t) for r, t in zip(regions, transcripts) if t]
            formatter = FORMATTERS.get(args.format)
            formatted_subtitles = formatter(timed_subtitles)

            dest = args.output

            if not dest:
                base, ext = os.path.splitext(args.source_path)
                dest = "{base}.{format}".format(base=base, format=args.format)

            with open(dest, 'wb') as f:
                f.write(formatted_subtitles.encode("utf-8"))

            print "Subtitles file created at {}".format(dest)

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



