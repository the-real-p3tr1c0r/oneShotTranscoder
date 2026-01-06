from pathlib import Path

path = Path('build.py')
text = path.read_text()
start = text.index('def build_executable')
end = text.index('\ndef main(')
new_block = '''def build_executable(spec_file: Path, build_mode: str = "full") -> None:
    """Build the executable using PyInstaller.

    Args:
        spec_file: Path to spec file
        build_mode: "full" for self-contained, "lightweight" for on-demand
    """
    print(f"Building executable in {build_mode} mode...")

    # Check if PyInstaller is installed
    try:
        import PyInstaller  # type: ignore
    except ImportError:
        print("Error: PyInstaller is not installed.")
        print("Install it with: pip install pyinstaller")
        sys.exit(1)

    dist_dir = Path("dist")
    if build_mode == "full":
        output_dir = dist_dir / "transcode"
    else:
        output_dir = dist_dir / "transcode-lightweight"

    if output_dir.exists():
        print(f"Cleaning existing output directory: {output_dir}")
        shutil.rmtree(output_dir)

    # Run PyInstaller with the modified spec file using wrapper script
    # The wrapper patches importlib.metadata to handle corrupted numpy metadata
    wrapper_script = Path(__file__).parent / "pyinstaller_wrapper.py"
    cmd = [sys.executable, str(wrapper_script), str(spec_file), "--clean", "--noconfirm"]

    result = subprocess.run(cmd, cwd=Path.cwd())

    if result.returncode != 0:
        print("Error: PyInstaller build failed")
        sys.exit(1)

    print("Build completed successfully!")
    exe_ext = ".exe" if platform.system() == "Windows" else ""

    exe_path = output_dir / f"transcode{exe_ext}"
    if exe_path.exists():
        print(f"Executable location: {exe_path.resolve()}"
)
        bundle_babelfish_runtime_data(output_dir)
    else:
        print("Warning: Executable not found at expected location")

'''

path.write_text(text[:start] + new_block + text[end:])
