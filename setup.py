"""
This script is writen for generation an executable file
for windows operation system by cxFreeze.
"""

from cx_Freeze import setup, Executable


setup(
    name="bilibili_admin_assist",
    version="1.0",
    description="Some description",
    executables=[
        Executable("run.py")
    ]
)