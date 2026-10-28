"""Hermes execution middleware, plus observer-only auxiliary accounting."""
import importlib.util
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace
from uuid import uuid4


def background(context):
    return context.get('platform')=='cron' or str(context.get('session_id') or '').startswith('cron_')


def source(context):
    return 'background' if background(context) else 'chat' if context.get('platform') or context.get('session_id') else 'unassigned'


def stopped(reason):
    # Execution middleware may short-circuit with a regular completed response. No network call.
    return SimpleNamespace(id='local-budget-'+uuid4().hex,model='local-budget',
        choices=[SimpleNamespace(index=0,finish_reason='stop',message=SimpleNamespace(role='assistant',content=reason,tool_calls=None,reasoning_content=None))],
        usage=SimpleNamespace(prompt_tokens=0,completion_tokens=0,total_tokens=0))


class Guard:
    def __init__(self,root,module):self.root=root;self.module=module

    def usage(self,response,context):
        raw=getattr(response,'usage',None)
        if not raw:return None
        fields=('prompt_tokens','completion_tokens','input_tokens','output_tokens')
        if not any((raw.get(k) if isinstance(raw,dict) else getattr(raw,k,None)) is not None for k in fields):return None
        from agent.usage_pricing import normalize_usage
        from dataclasses import asdict
        return asdict(normalize_usage(raw,provider=context.get('provider'),api_mode=context.get('api_mode','chat_completions')))

    def execute(self,request,next_call,**context):
        is_background=background(context);ident='main-'+uuid4().hex;prepared=request
        try:
            with self.module.Budget(self.root) as ledger:
                if is_background:
                    snapshot=ledger.snapshot()
                    prepared,estimate=self.module.prepare(request,snapshot['remaining'] if snapshot['settings']['enabled'] else None,context.get('api_mode','chat_completions'))
                else:estimate=self.module.estimate_request(request)+self.module.OUTPUT_CAP
                decision=ledger.reserve(ident,estimate,source=source(context),task='main',model=context.get('model',''),session=context.get('session_id',''))
            if not decision['allowed'] or prepared is None:
                return stopped(decision.get('reason') or '后台剩余额度不足以继续，本轮已暂停；未完成的收尾不会标成成功。')
        except Exception:
            if is_background:return stopped('本机鱼粮预检暂时不可用，本轮后台请求已跳过；聊天仍可使用。')
            ident=None  # A ledger fault must not prevent a human conversation.
        started=time.monotonic()
        try:response=next_call(prepared)
        except Exception:
            self.settle(ident,None,True,time.monotonic()-started);raise
        try:usage=self.usage(response,context)
        except Exception:usage=None
        self.settle(ident,usage,False,time.monotonic()-started)
        return response

    def settle(self,ident,usage,error=False,duration=None):
        if not ident:return
        try:
            with self.module.Budget(self.root) as ledger:ledger.settle(ident,usage,error=error,duration=duration)
        except Exception:pass  # The reservation remains charged if settlement fails.

    @staticmethod
    def auxiliary_id(context):
        # The pair shares started_at even when the provider reuses a logical request id on retry.
        return 'aux-'+__import__('hashlib').sha256(json.dumps([context.get('api_request_id'),context.get('retry_count'),context.get('started_at')]).encode()).hexdigest()

    def pre_auxiliary(self,**context):
        request=context.get('request_messages') or []
        estimate=self.module.estimate_request({'messages':request,'system':context.get('system_prompt','')})
        maximum=context.get('max_tokens');estimate+=maximum if type(maximum) is int and maximum>0 else self.module.OUTPUT_CAP
        try:
            with self.module.Budget(self.root) as ledger:
                # Native auxiliary hooks are observers, not vetoes. Count the attempt even over quota.
                ledger.reserve(self.auxiliary_id(context),estimate,source=source(context),task='aux:'+str(context.get('aux_task','other'))[:50],model=context.get('model',''),session=context.get('session_id',''),enforce=False)
        except Exception:pass

    def post_auxiliary(self,**context):
        self.settle(self.auxiliary_id(context),context.get('usage'),bool(context.get('error')),context.get('api_duration'))


def register(ctx):
    home=Path(os.environ.get('HERMES_HOME','')).resolve();root=home.parent
    if home.name!='.hermes' or not (root/'scripts/fish_budget.py').is_file():raise ValueError('Budget requires the project Hermes home.')
    spec=importlib.util.spec_from_file_location('_bigfish_request_budget',Path(__file__).with_name('budget.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    guard=Guard(root,module)
    ctx.register_middleware('llm_execution',guard.execute)
    ctx.register_hook('pre_auxiliary_call',guard.pre_auxiliary)
    ctx.register_hook('post_auxiliary_call',guard.post_auxiliary)
