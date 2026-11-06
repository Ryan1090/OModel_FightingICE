package structs;

import enumerate.State;

/** Snapshot of the current engine's motion row exposed through the 1.x ABI. */
public class MotionData {
    public String motionName, attackImage, image;
    public int frameNumber, speedX, speedY, attackSpeedX, attackSpeedY, attackStartUp,
        attackActive, attackInterval, attackRepeat, attackHitDamage, attackGuardDamage,
        attackStartAddEnergy, attackHitAddEnergy, attackGuardAddEnergy, attackGiveEnergy,
        attackImpactX, attackImpactY, attackGiveGuardRecov, attackKnockBack, attackHitStop,
        attackType, cancelAbleFrame, cancelAbleMotionLevel, motionLevel;
    public HitArea hit, attackHit;
    public State state;
    public boolean attackDownProperty, control, landingFlag;

    public MotionData() {}
    public MotionData(struct.MotionData source) {
        motionName = source.getActionName(); frameNumber = source.getFrameNumber();
        speedX = source.getSpeedX(); speedY = source.getSpeedY();
        hit = new HitArea(source.getCharacterHitArea()); state = source.getState();
        attackHit = new HitArea(source.getAttackHitArea());
        attackSpeedX = source.getAttackSpeedX(); attackSpeedY = source.getAttackSpeedY();
        attackStartUp = source.getAttackStartUp(); attackActive = source.getAttackActive();
        attackHitDamage = source.getAttackHitDamage(); attackGuardDamage = source.getAttackGuardDamage();
        attackStartAddEnergy = source.getAttackStartAddEnergy(); attackHitAddEnergy = source.getAttackHitAddEnergy();
        attackGuardAddEnergy = source.getAttackGuardAddEnergy(); attackGiveEnergy = source.getAttackGiveEnergy();
        attackImpactX = source.getAttackImpactX(); attackImpactY = source.getAttackImpactY();
        attackGiveGuardRecov = source.getAttackGiveGuardRecov(); attackType = source.getAttackType();
        attackDownProperty = source.isAttackDownProp(); cancelAbleFrame = source.getCancelAbleFrame();
        cancelAbleMotionLevel = source.getCancelAbleMotionLevel(); motionLevel = source.getMotionLevel();
        control = source.isControl(); landingFlag = source.isLandingFlag();
        // These fields disappeared from v7.1. Zero/null are compatibility placeholders.
        attackInterval = attackRepeat = attackKnockBack = attackHitStop = 0;
        attackImage = image = null;
    }

    public String getMotionName(){return motionName;} public void setMotionName(String v){motionName=v;}
    public int getFrameNumber(){return frameNumber;} public void setFrameNumber(int v){frameNumber=v;}
    public int getSpeedX(){return speedX;} public void setSpeedX(int v){speedX=v;}
    public int getSpeedY(){return speedY;} public void setSpeedY(int v){speedY=v;}
    public HitArea getHit(){return hit;} public void setHit(HitArea v){hit=v;}
    public State getState(){return state;} public void setState(State v){state=v;}
    public HitArea getAttackHit(){return attackHit;} public void setAttackHit(HitArea v){attackHit=v;}
    public int getAttackSpeedX(){return attackSpeedX;} public void setAttackSpeedX(int v){attackSpeedX=v;}
    public int getAttackSpeedY(){return attackSpeedY;} public void setAttackSpeedY(int v){attackSpeedY=v;}
    public int getAttackStartUp(){return attackStartUp;} public void setAttackStartUp(int v){attackStartUp=v;}
    public int getAttackActive(){return attackActive;} public void setAttackActive(int v){attackActive=v;}
    public int getAttackInterval(){return attackInterval;} public void setAttackInterval(int v){attackInterval=v;}
    public int getAttackRepeat(){return attackRepeat;} public void setAttackRepeat(int v){attackRepeat=v;}
    public int getAttackHitDamage(){return attackHitDamage;} public void setAttackHitDamage(int v){attackHitDamage=v;}
    public int getAttackGuardDamage(){return attackGuardDamage;} public void setAttackGuardDamage(int v){attackGuardDamage=v;}
    public int getAttackStartAddEnergy(){return attackStartAddEnergy;} public void setAttackStartAddEnergy(int v){attackStartAddEnergy=v;}
    public int getAttackHitAddEnergy(){return attackHitAddEnergy;} public void setAttackHitAddEnergy(int v){attackHitAddEnergy=v;}
    public int getAttackGuardAddEnergy(){return attackGuardAddEnergy;} public void setAttackGuardAddEnergy(int v){attackGuardAddEnergy=v;}
    public int getAttackGiveEnergy(){return attackGiveEnergy;} public void setAttackGiveEnergy(int v){attackGiveEnergy=v;}
    public int getAttackImpactX(){return attackImpactX;} public void setAttackImpactX(int v){attackImpactX=v;}
    public int getAttackImpactY(){return attackImpactY;} public void setAttackImpactY(int v){attackImpactY=v;}
    public int getAttackGiveGuardRecov(){return attackGiveGuardRecov;} public void setAttackGiveGuardRecov(int v){attackGiveGuardRecov=v;}
    public int getAttackKnockBack(){return attackKnockBack;} public void setAttackKnockBack(int v){attackKnockBack=v;}
    public int getAttackHitStop(){return attackHitStop;} public void setAttackHitStop(int v){attackHitStop=v;}
    public int getAttackType(){return attackType;} public void setAttackType(int v){attackType=v;}
    public boolean isAttackDownProperty(){return attackDownProperty;} public void setAttackDownProperty(boolean v){attackDownProperty=v;}
    public String getAttackImage(){return attackImage;} public void setAttackImage(String v){attackImage=v;}
    public int getCancelAbleFrame(){return cancelAbleFrame;} public void setCancelAbleFrame(int v){cancelAbleFrame=v;}
    public int getCancelAbleMotionLevel(){return cancelAbleMotionLevel;} public void setCancelAbleMotionLevel(int v){cancelAbleMotionLevel=v;}
    public int getMotionLevel(){return motionLevel;} public void setMotionLevel(int v){motionLevel=v;}
    public boolean isControl(){return control;} public void setControl(boolean v){control=v;}
    public boolean isLandingFlag(){return landingFlag;} public void setLandingFlag(boolean v){landingFlag=v;}
    public String getImage(){return image;} public void setImage(String v){image=v;}
}
