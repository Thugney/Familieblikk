"""Checks design-contract arithmetic, not an implemented app calculation engine."""
from pathlib import Path
import json
checks=[]
def check(name,actual,expected):
    checks.append({'name':name,'actual':actual,'expected':expected,'passed':actual==expected})
def available(i,e,b,goals,debt=0,annual=0):
    # Inputs in ore: (plan, gross deposits, gross withdrawals).
    net=[(p,d-w) for p,d,w in goals]
    reserve=sum(max(p,max(n,0)) for p,n in net)
    released=sum(max(-n,0) for _,n in net)
    return i+released-e-b-reserve-debt-annual
goals=[(400000,450000,0),(200000,0,0)]
check('core-fixture-ore',available(6200000,2845000,865000,goals),1840000)
check('extended-fixture-ore',available(6200000,2995000,865000,goals,350000,200000),1140000)
check('per-goal-reserve-cannot-offset',available(1000000,0,0,[(400000,450000,0),(200000,0,0)]),350000)
base=available(1000000,0,0,[(100000,0,0)])
check('withdraw-redeposit-roundtrip',available(1000000,0,0,[(100000,10000,10000)]),base)
check('withdrawal-release',available(1000000,0,0,[(100000,0,10000)]),base+10000)
check('over-plan-contribution',available(1000000,0,0,[(100000,150000,0)]),850000)
check('fund-before-payment-month-charge',80000+160000,240000)
check('fund-after-payment-balance',720000+80000+160000-960000,0)
check('historical-all-actual-classes',6200000+100000-2995000-350000-960000-450000,1545000)
check('bill-payment-invariant',available(3000000,600000,900000,[(200000,250000,0)]),available(3000000,500000,1000000,[(200000,250000,0)]))
check('no-income-new-month-negative',available(0,0,100000,[(200000,0,0)]),-300000)
check('same-day-count-inclusive',31-20+1,12)
result={'kind':'proposed-specification-arithmetic-only','passed':all(c['passed'] for c in checks),'checks':checks,'applicationTests':False,'limitation':'Only numerical examples; does not implement/verify transactions, isolation, corrections or time reconstruction.'}
out=Path('.project-init/evidence/financial-example-checks.json');out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({'passed':result['passed'],'checks':len(checks)}))
raise SystemExit(0 if result['passed'] else 1)
