import sys, time

duration_ms = int(sys.argv[1]) if len(sys.argv) > 1 else 900_000
time.sleep(duration_ms / 1000)
