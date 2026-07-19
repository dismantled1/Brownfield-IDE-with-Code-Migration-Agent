"""
Quick diagnostic script to test pywinpty API compatibility.
Run: .\venv\Scripts\python.exe test_pty.py
"""
import sys
import time

print(f"Python: {sys.version}")

# Test 1: Import
try:
    from winpty import PtyProcess
    print("[OK] import winpty.PtyProcess")
except ImportError as e:
    print(f"[FAIL] Import: {e}")
    sys.exit(1)

# Test 2: Spawn with list
try:
    pty = PtyProcess.spawn(["powershell.exe", "-NoLogo", "-NonInteractive"],
                           dimensions=(24, 80))
    print(f"[OK] Spawn: {pty}")
    print(f"[OK] isalive: {pty.isalive()}")
    time.sleep(2)

    # Test 3: Read
    try:
        data = pty.read(4096)
        print(f"[OK] read() returned: {repr(data[:100] if data else None)}")
    except Exception as e:
        print(f"[FAIL] read(): {e}")

    # Test 4: Write
    try:
        pty.write("echo HELLO_TEST\r\n")
        time.sleep(0.5)
        data2 = pty.read(4096)
        print(f"[OK] write+read: {repr(data2[:200] if data2 else None)}")
    except Exception as e:
        print(f"[FAIL] write: {e}")

    # Test 5: setwinsize
    try:
        pty.setwinsize(30, 120)
        print("[OK] setwinsize")
    except Exception as e:
        print(f"[FAIL] setwinsize: {e}")

    # Test 6: terminate
    try:
        pty.terminate(force=True)
        print("[OK] terminate")
    except Exception as e:
        print(f"[FAIL] terminate: {e}")

except Exception as e:
    print(f"[FAIL] Spawn: {e}")
    import traceback
    traceback.print_exc()

# Test 7: Spawn with string
try:
    pty2 = PtyProcess.spawn("powershell.exe -NoLogo -NonInteractive",
                            dimensions=(24, 80))
    print(f"[OK] Spawn with string: {pty2}")
    pty2.terminate(force=True)
except Exception as e:
    print(f"[INFO] Spawn with string: {e}")

print("\nDone.")
