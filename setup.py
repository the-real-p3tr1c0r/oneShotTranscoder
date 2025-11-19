from setuptools import setup, find_packages

setup(
    name="transcoder",
    version="0.1.0",
    description="Transcoder project",
    packages=find_packages(),
    python_requires=">=3.9",
    license="GPL-3.0-or-later",
    install_requires=[
        "easyocr",
        "opencv-python",
        "babelfish",
        "pgsrip",
        "numpy",
        "torch",
    ],
    entry_points={
        "console_scripts": [
            "transcode=transcoder.main:main",
        ],
    },
)

