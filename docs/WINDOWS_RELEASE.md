# Windows builds

Run the source directly using Python 3.11+:

```powershell
py -3 -m sqlbench serve
```

To create an optional Windows **single-file executable** on a **Windows computer** using PyInstaller:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1
```

PyInstaller is a build-time dependency, not a runtime dependency. The build includes `web/` and `examples/` as read-only resources; runtime analysis is local. The resulting `dist/KTNS-SQLBench.exe` is an **unsigned development build** and can trigger Windows SmartScreen. Commercial distribution requires code signing, malware scanning and real Windows installation QA. The build recipe does not implement commercial licensing.

Use a non-administrator account. Do not expose the program's loopback port to other machines.
