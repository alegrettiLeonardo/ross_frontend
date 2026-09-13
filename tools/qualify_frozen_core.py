"""Execute the Core sentinel harness inside the actual distributed process."""
import json
from pathlib import Path
import platform
import subprocess
import sys

root=Path(sys.argv[1])
output=Path(sys.argv[2]).resolve();output.parent.mkdir(parents=True,exist_ok=True)
exe=(root/'ROSS-Studio'/('ROSS-Studio.exe' if platform.system()=='Windows' else 'ROSS-Studio')).resolve()
run=subprocess.run([str(exe),'--core-output',str(output)],timeout=300)
data=json.loads(output.read_text())
assert run.returncode==0,data
assert data['status']=='PASS' and data['frozen'] is True,data
assert data['ross_version']=='2.3.0'
assert len(data['comparisons'])>=50
assert all(row['status']=='PASS' for row in data['comparisons'])
print(json.dumps(data,indent=2))
