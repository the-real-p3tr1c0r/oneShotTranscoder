from setuptools import setup, find_packages

setup(
    name="transcoder",
    version="0.1.0",
    description="Transcoder project",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "easyocr",
        "opencv-python",
        "babelfish",
        "pgsrip",
    ],
    entry_points={
        "console_scripts": [
            "transcode=transcoder.main:main",
        ],
    },
)

