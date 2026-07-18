import subprocess
import time
p = subprocess.Popen(["python", "test_streamlit_bootstrap.py"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
time.sleep(3)
p.terminate()
print(p.stdout.read())
