import argparse, json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.config import get_config
from overdue_reminder_agent.agent import OverdueReminderAgent

p=argparse.ArgumentParser(); p.add_argument("--send-tests",action="store_true"); p.add_argument("--send-live-singles",action="store_true"); p.add_argument("--send-live-multiples",action="store_true"); p.add_argument("--send-multi-payment-test",action="store_true"); p.add_argument("--monitor-activity",action="store_true"); p.add_argument("--enable-single-live",action="store_true"); p.add_argument("--reconcile-payments",action="store_true"); p.add_argument("--count",type=int,default=3); p.add_argument("--max-live",type=int,default=10); p.add_argument("--customer-id",default=""); p.add_argument("--test-to",action="append",default=[]); p.add_argument("--cc",action="append",default=[]); a=p.parse_args()
agent=OverdueReminderAgent(get_config(),"/home/menteso_os/data/accountant_agent/overdue-reminder-status.json")
if a.enable_single_live:
    agent.state["mode"]="single_live"; agent.save()
result=({"mode":"single_live","enabled":True} if a.enable_single_live else
        (agent.monitor_activity() if a.monitor_activity else
        (agent.send_tests(a.count,a.test_to or None) if a.send_tests else
        (agent.send_multi_payment_test(a.customer_id,(a.test_to or [""])[0],a.cc) if a.send_multi_payment_test else
        (agent.send_live_multiples(a.max_live) if a.send_live_multiples else
        (agent.send_live_singles(a.max_live) if a.send_live_singles else
         (agent.reconcile_payments() if a.reconcile_payments else agent.previews(a.count))))))))
print(json.dumps(result,default=str,indent=2))
