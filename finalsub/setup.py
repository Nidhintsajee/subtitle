from distutils.core import setup
import py2exe
from glob import glob
data_files = [("Microsoft.VC90.CRT", glob(r'C:\Program Files\Microsoft Visual Studio 9.0\VC\redist\x86\Microsoft.VC90.CRT\*.*'))]

# setup(console=['subtitle_GUI.py'])

setup(
	data_files=data_files,
    options = {
            "py2exe":{
            "dll_excludes": ["MSVCP90.dll", "HID.DLL", "w9xpopen.exe"],
            }
    },
    windows = [{'script': 'subtitle_GUI.py'}]
)
# import sys
# from cx_Freeze import setup, Executable

# # Dependencies are automatically detected, but it might need fine tuning.
# build_exe_options = {"packages": ["os"], "excludes": ["tkinter"]}

# # GUI applications require a different base on Windows (the default is for a
# # console application).
# base = None
# if sys.platform == "win32":
#     base = "Win32GUI"

# setup(  name = "guifoo",
#         version = "0.1",
#         description = "My GUI application!",
#         options = {"build_exe": build_exe_options},
#         executables = [Executable("subtitle_GUI.py", base=base)])

# command =[
                    # "ffmpeg","-ss",str(start),"-t",str(end-start),self.source_path,"-vn","-ac",1,"-ar",16000,"-acodec",temp.name]