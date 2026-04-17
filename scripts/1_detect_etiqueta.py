import subprocess
import sys
import os

if __name__ == "__main__":
    # Execute detect_etiqueta.py as a subprocess to avoid import issues
    cmd = [sys.executable, "scripts/detect_etiqueta.py"]
    env = os.environ.copy()
    # Add current directory to Python path
    env['PYTHONPATH'] = os.getcwd()
    result = subprocess.run(cmd, env=env)
    sys.exit(result.returncode)
