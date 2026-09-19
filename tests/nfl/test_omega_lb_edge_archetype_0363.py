#!/usr/bin/env python3
from pathlib import Path
import importlib.util
import sys

root=Path(__file__).resolve().parents[2]
p=root/'packages/models/nfl/omega/lb_edge_archetype_0363.py'
spec=importlib.util.spec_from_file_location('arch0363',p)
m=importlib.util.module_from_spec(spec);sys.modules['arch0363']=m;spec.loader.exec_module(m)

assert m.explicit_role_label({'position':'ILB','position_group':'LB'})=='OFFBALL_LB'
assert m.explicit_role_label({'position':'MLB','position_group':'LB'})=='OFFBALL_LB'
assert m.explicit_role_label({'position':'DE','position_group':'LB'})=='EDGE'
assert m.explicit_role_label({'position':'OLB','position_group':'LB'})=='EDGE'
assert m.explicit_role_label({'position':'LB','position_group':'LB'})=='AMBIG_LB'
assert m.explicit_role_label({'position':'LB','position_group':'DL'})=='EDGE'

def row(i,offball,ambig=False):
    if ambig:
        pos='LB';pg='LB'
    elif offball:
        pos='ILB';pg='LB'
    else:
        pos='DE';pg='DL'
    if offball:
        cr={'RUSH':3.4,'COMPLETE_PASS':2.0,'SCRAMBLE':.45,'SACK':.08,'OTHER_PASS':.08}
        rates={'RUSH':.18,'COMPLETE_PASS':.13,'SCRAMBLE':.19,'SACK':.03,'OTHER_PASS':.05}
        xtc=6.0;ss=.88
    else:
        cr={'RUSH':1.2,'COMPLETE_PASS':.35,'SCRAMBLE':.18,'SACK':.75,'OTHER_PASS':.07}
        rates={'RUSH':.08,'COMPLETE_PASS':.03,'SCRAMBLE':.08,'SACK':.42,'OTHER_PASS':.03}
        xtc=2.6;ss=.76
    r={'game_id':f'G{i//4}','player_id':f'P{i}','position':pos,'position_group':pg,
       'control_xtc':xtc,'predicted_xto':45,'predicted_snap_share':ss,'prior_games':8}
    for fam,v in cr.items():r['pred_credit_'+fam]=v
    for fam,v in rates.items():r['shrunk_rate_'+fam]=v
    return r

train=[row(i,True) for i in range(140)]+[row(200+i,False) for i in range(140)]
model=m.fit(train)
met=m.metrics(train,model)
assert met['accuracy']>.95
assert met['brier']<.10

generic_off=row(500,True,ambig=True)
generic_edge=row(501,False,ambig=True)
co=m.classify(generic_off,model)
ce=m.classify(generic_edge,model)
assert co['eligibleForLbChallenger'] is True and co['offballProbability']>=m.GENERIC_LB_OFFBALL_THRESHOLD
assert ce['eligibleForLbChallenger'] is False and ce['offballProbability']<m.GENERIC_LB_OFFBALL_THRESHOLD

clone=m.ArchetypeModel.from_dict(model.to_dict())
assert abs(clone.probability_offball(generic_off)-model.probability_offball(generic_off))<1e-12
print('PASS OMEGA 0.36.3 LB-edge archetype contracts · generic edge-like LB blocked')
