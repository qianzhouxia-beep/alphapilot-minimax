from pathlib import Path
import sys
path = Path(sys.argv[1])
start = int(sys.argv[2])
end = int(sys.argv[3])
lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
for i in range(start - 1, min(end, len(lines))):
    print(f"{i+1}: {lines[i]!r}".encode("utf-8", errors="replace").decode("utf-8"))
    import sys
    sys.stdout.buffer.write(f"{i+1}: {lines[i]!r}\n".encode("utf-8", errors="replace"))
