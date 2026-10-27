"""Reuse the unchanged SDK observer and persistent physical accounting gates."""
from scripts.streaming_steer_real_uat_v2.adapter import ObservedStream, BudgetClient as BaseClient
from .plan import BARRIER

class BudgetClient(BaseClient):
 def __init__(self,original,config,ledger,case,streams,requests,source_rows,directory=None,barriers=BARRIER):
  super().__init__(original,config,ledger,case,streams,requests,source_rows,directory,barriers)
