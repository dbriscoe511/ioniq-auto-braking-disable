"""slcan.py <Scode> <mode: silent|normal> <seconds> [logfile] [--fd Y]  -- CANable2 slcan logger.
Never transmits data frames. 'normal' only ACKs."""
import sys, time, serial, collections
s_code, mode, secs = sys.argv[1], sys.argv[2], float(sys.argv[3])
log = sys.argv[4] if len(sys.argv) > 4 and not sys.argv[4].startswith("--") else None
fd = sys.argv[sys.argv.index("--fd") + 1] if "--fd" in sys.argv else None
p = serial.Serial("/dev/ttyACM0", 115200, timeout=0.05)
def cmd(c):
    p.write(c.encode() + b"\r"); p.flush(); time.sleep(0.05)
cmd("C"); p.reset_input_buffer()
cmd("V"); time.sleep(0.1); ver = p.read(200)
cmd("S" + s_code)
if fd: cmd("Y" + fd)
cmd("M1" if mode == "silent" else "M0")
p.reset_input_buffer()
cmd("O")
t0 = time.monotonic(); buf = b""; n = 0; ids = collections.Counter(); other = collections.Counter()
f = open(log, "w") if log else None
try:
    while time.monotonic() - t0 < secs:
        buf += p.read(4096)
        while b"\r" in buf or b"\a" in buf:
            i = min(x for x in (buf.find(b"\r"), buf.find(b"\a")) if x >= 0)
            line, sep, buf = buf[:i], buf[i:i+1], buf[i+1:]
            t = time.monotonic() - t0
            txt = line.decode("ascii", "replace")
            if sep == b"\a": txt += "<BEL>"
            if not txt: continue
            if txt[0] in "tTrRdDbB":
                n += 1
                idlen = 3 if txt[0] in "trdb" else 8
                ids[txt[0] + txt[1:1+idlen]] += 1
            else:
                other[txt] += 1
            if f: f.write(f"{t:.4f} {txt}\n")
finally:
    cmd("C"); p.close()
    if f: f.close()
print(f"ver={ver!r} S{s_code} fd={fd} {mode} {secs}s frames={n} ids={dict(ids)} other={dict(other)}")
