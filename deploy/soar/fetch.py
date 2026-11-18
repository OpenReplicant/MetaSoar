"""Fetch Soar's release zip, check its digest, and extract the Linux binaries and the demo agents to /opt/soar."""
import hashlib
import io
import sys
import urllib.request
import zipfile

url, want = sys.argv[1], sys.argv[2]
data = urllib.request.urlopen(url, timeout=600).read()
got = hashlib.sha256(data).hexdigest()
if got != want:
    sys.exit(f"digest mismatch: {got}")
z = zipfile.ZipFile(io.BytesIO(data))
for n in z.namelist():
    if n.startswith(("bin/linux_x86-64/", "Agents/")) and "/SoarUnitTests/" not in n and not n.endswith(".gif"):
        z.extract(n, "/opt/soar")
print("extracted, sha256", got)
