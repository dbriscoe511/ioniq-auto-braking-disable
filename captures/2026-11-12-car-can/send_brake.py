"""send_brake.py [--fire] [--req HEX16]  -- send infotainment 0x2A3 "auto-brake off".
Transmits ONLY 0x2A3: three request frames (~50ms) then three all-zero releases, then stops.
Refuses to transmit unless it first sees 0x05C17002 byte1 == 09 (brake ON). Listen-only without --fire.
Default request matches the head unit's first-from-idle "off": 00 02 00 0F 00 00 00 00.
"""
import sys, time, serial
FIRE = "--fire" in sys.argv
REQ = sys.argv[sys.argv.index("--req")+1] if "--req" in sys.argv else "0002000F00000000"
assert len(REQ) == 16, "req must be 16 hex chars"
OFF_REQ = "t2A38" + REQ
RELEASE = "t2A380000000000000000"
STATUS = "T05C17002"
p = serial.Serial("/dev/ttyACM0", 115200, timeout=0.02)
def cmd(c, settle=0.0): p.write(c.encode()+b"\r"); p.flush(); time.sleep(settle)
def read_state(secs):
    t0=time.monotonic(); buf=b""; b0=b1=None
    while time.monotonic()-t0 < secs:
        buf += p.read(4096)
        while b"\r" in buf:
            line,_,buf = buf.partition(b"\r")
            s = line.decode("ascii","replace")
            if s.startswith(STATUS) and len(s)>=14: b0,b1 = s[10:12], s[12:14]
    return b0,b1
cmd("C",0.05); p.reset_input_buffer()
cmd("S6",0.05); cmd("M0" if FIRE else "M1",0.05); cmd("O",0.05)
b0,b1 = read_state(2.0)
print(f"before: 0x05C17002 byte0={b0} byte1={b1}  (09=on, 07=off)")
if not FIRE:
    print("listen-only: sent nothing.")
elif b1 != "09":
    print(f"ABORT: brake not confirmed ON (byte1={b1}); sent nothing.")
else:
    print(f"request frame: {OFF_REQ}")
    for _ in range(3): cmd(OFF_REQ); time.sleep(0.05)
    for _ in range(3): cmd(RELEASE); time.sleep(0.05)
    b0b,b1b = read_state(3.0)
    print(f"after:  0x05C17002 byte0={b0b} byte1={b1b}")
    print("RESULT:", "brake OFF (09->07) OK" if b1b=="07" else f"no change (byte1={b1b})")
cmd("C",0.05); p.close()
