"""psu.py status|on|off|cycle [secs]  -- DP932E CH state. Only toggles outputs that the user already had configured."""
import sys, time, pyvisa
RES = "USB0::6833::42152::DP9D272M00090::0::INSTR"
def status(i):
    for ch in ("CH1", "CH2", "CH3"):
        print(ch, "set", i.query(f":APPL? {ch}").strip(), "| out", i.query(f":OUTP? {ch}").strip(),
              "| meas", i.query(f":MEAS:ALL? {ch}").strip())
    print("err", i.query(":SYST:ERR?").strip())
cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
ch = sys.argv[2] if len(sys.argv) > 2 else None
with pyvisa.ResourceManager("@py").open_resource(RES, timeout=3000) as i:
    if cmd == "status":
        status(i)
    elif cmd in ("on", "off"):
        i.write(f":OUTP {ch},{cmd.upper()}"); time.sleep(0.3); status(i)
    elif cmd == "cycle":
        secs = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
        i.write(f":OUTP {ch},OFF"); time.sleep(secs); i.write(f":OUTP {ch},ON"); time.sleep(0.3); status(i)
