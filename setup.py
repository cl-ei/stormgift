"""
This script is writen for generation an executable file
for windows operation system by cxFreeze.
"""
import os
from cx_Freeze import setup, Executable

os.environ['TCL_LIBRARY'] = r'C:\backup\programfiles\python36\tcl\tcl8.6'
os.environ['TK_LIBRARY'] = r'C:\backup\programfiles\python36\tcl\tk8.6'

setup(
    name="bilibili_admin_assist",
    version="1.0",
    description="Some description",
    options={
        'build_exe': {
            'packages': ['asyncio']
        },
    },
    executables=[
        Executable("run.py")
    ]
)
