import sqlite3,pathlib,time,ctypes,json,sys
p=pathlib.Path('results/expanded/wave3-20261019-212023-main/experiment.sqlite3')
c=sqlite3.connect(p,timeout=.15,isolation_level=None)
k=ctypes.WinDLL('kernel32',use_last_error=True)
held=False
for i in range(1500):
 try:
  c.execute('BEGIN IMMEDIATE')
  active=c.execute("select count(*) from attempts where state='RUNNING'").fetchone()[0]
  if active==0:
   held=True;break
  c.execute('ROLLBACK')
 except sqlite3.OperationalError:
  if c.in_transaction:c.execute('ROLLBACK')
 time.sleep(.01)
if not held:raise SystemExit('No idle boundary acquired; no signal sent')
try:
 k.FreeConsole()
 if not k.AttachConsole(44752):raise OSError(ctypes.get_last_error(),'AttachConsole failed')
 if not k.SetConsoleCtrlHandler(None,True):raise OSError(ctypes.get_last_error(),'SetConsoleCtrlHandler failed')
 if not k.GenerateConsoleCtrlEvent(0,0):raise OSError(ctypes.get_last_error(),'GenerateConsoleCtrlEvent failed')
 time.sleep(.15)
 k.FreeConsole()
 print(json.dumps({'signal':'CTRL_C','target_runtime_pid':44752,'running_attempts_at_signal':active,'preserved_all_results':True}))
finally:
 if c.in_transaction:c.execute('ROLLBACK')
 c.close()