"""Stock jump construction from Character.update/gravityEffect, not recipes."""


def jump_profile(table):
    jump=table['JUMP'];air=table['AIR'];row=jump
    y=640-table['STAND']['hitAreaDown'];vy=jump['speedY'];remaining=jump['frameNumber'];action='JUMP';samples=[]
    for age in range(1,1001):
        y+=vy
        bottom=y+row['hitAreaDown'];top=y+row['hitAreaUp']
        if bottom>=640:vy=0
        elif top<=0:vy=1
        else:vy+=1
        if bottom>=640:break
        remaining-=1
        if remaining<=0:
            if action!='AIR':remaining=air['frameNumber']
            action='AIR';row=air;vy+=air['speedY']
        samples.append({'issue_age':age,'age':age-1,'raw_y':y,'velocity_y':vy,
            'body_top':y+row['hitAreaUp'],'body_bottom':y+row['hitAreaDown'],
            'control':row['control'],'action':action})
    return {'runs':[{'samples':samples}],
        'basis':'stock Motion + engine integer gravity/floor/ceiling/action-expiry rules',
        'incomplete':bool(samples and samples[-1]['issue_age']==1000)}
