import argparse, json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.config import get_config
from overdue_reminder_agent.agent import OverdueReminderAgent

p=argparse.ArgumentParser(); p.add_argument("--send-tests",action="store_true"); p.add_argument("--reconcile-payments",action="store_true"); p.add_argument("--count",type=int,default=3); p.add_argument("--test-to",action="append",default=[]); a=p.parse_args()
agent=OverdueReminderAgent(get_config(),"/home/menteso_os/data/accountant_agent/overdue-reminder-status.json")
result=agent.send_tests(a.count,a.test_to or None) if a.send_tests else (agent.reconcile_payments() if a.reconcile_payments else agent.previews(a.count))
print(json.dumps(result,default=str,indent=2))
