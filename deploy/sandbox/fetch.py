"""Fetch Soar's release zip, check its digest, install its Linux library and Python SML bindings where `python -I`
finds them (site-packages; the judge's sandbox ignores PYTHON* variables), and keep the demo agents in /opt/soar."""
import hashlib
import io
import shutil
import sys
import sysconfig
import urllib.request
import zipfile
from pathlib import Path

url, want = sys.argv[1], sys.argv[2]
data = urllib.request.urlopen(url, timeout=600).read()
got = hashlib.sha256(data).hexdigest()
if got != want:
    sys.exit(f"digest mismatch: {got}")
z = zipfile.ZipFile(io.BytesIO(data))
for n in z.namelist():
    if n.startswith(("bin/linux_x86-64/", "Agents/")) and "/SoarUnitTests/" not in n and not n.endswith(".gif"):
        z.extract(n, "/opt/soar")
b = Path("/opt/soar/bin/linux_x86-64")
site = Path(sysconfig.get_paths()["purelib"])
shutil.copy(b / "Python_sml_ClientInterface.py", site)
shutil.copy(b / "_Python_sml_ClientInterface.abi3.so", site)
shutil.copy(b / "libSoar.so", "/usr/local/lib/libSoar.so")
print("installed Soar, sha256", got)
