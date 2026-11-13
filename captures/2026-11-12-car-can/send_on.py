"""send_on.py [--fire]  -- send 0x2A3 00 04 ("auto-brake ON"). Guard: only if byte1==07 (brake OFF)."""
import sys, time, serial
FIRE = "--fire" in sys.argv
ON_REQ = "t2A380004000000000000"   # 0x2A3 DLC8 00 04 00 00 00 00 00 00
RELEASE = "t2A380000000000000000"
STATUS = "T05C17002"
p = serial.Serial("/dev/ttyACM0", 115200, timeout=0.02)
def cmd(c, s=0.0): p.write(c.encode()+b"\r"); p.flush(); time.sleep(s)
def read_state(secs):
    t0=time.monotonic(); buf=b""; b0=b1=None
    while time.monotonic()-t0 < secs:
        buf += p.read(4096)
        while b"\r" in buf:
            line,_,buf = buf.partition(b"\r")
            st = line.decode("ascii","replace")
            if st.startswith(STATUS) and len(st)>=14: b0,b1 = st[10:12], st[12:14]
    return b0,b1
cmd("C",0.05); p.reset_input_buffer()
cmd("S6",0.05); cmd("M0" if FIRE else "M1",0.05); cmd("O",0.05)
b0,b1 = read_state(2.0)
print(f"before: 0x05C17002 byte0={b0} byte1={b1}  (09=on, 07=off)")
if not FIRE:
    print("listen-only: sent nothing.")
elif b1 != "07":
    print(f"ABORT: brake not confirmed OFF (byte1={b1}); sent nothing.")
else:
    print(f"request frame: {ON_REQ}")
    for _ in range(3): cmd(ON_REQ); time.sleep(0.05)
    for _ in range(3): cmd(RELEASE); time.sleep(0.05)
    b0b,b1b = read_state(3.0)
    print(f"after:  0x05C17002 byte0={b0b} byte1={b1b}")
    print("RESULT:", "brake ON (07->09) OK" if b1b=="09" else f"no change (byte1={b1b})")
cmd("C",0.05); p.close()
