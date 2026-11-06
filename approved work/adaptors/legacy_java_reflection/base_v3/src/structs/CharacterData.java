package structs;

import enumerate.Action;
import enumerate.State;

public class CharacterData {
    private final struct.CharacterData source;
    // Public fields match the 2015 ABI; accessors support both 2014 and later binaries.
    public int hp, energy, x, y, left, right, top, bottom, speedX, speedY, remainingFrame;
    public State state; public Action action; public boolean front, control; public fighting.Attack attack;
    public CharacterData(struct.CharacterData source) {
        this.source = source;
        hp=source.getHp(); energy=source.getEnergy(); x=source.getX(); y=source.getY();
        left=source.getLeft(); right=source.getRight(); top=source.getTop(); bottom=source.getBottom();
        speedX=source.getSpeedX(); speedY=source.getSpeedY(); state=source.getState(); action=source.getAction();
        front=source.isFront(); control=source.isControl(); remainingFrame=source.getRemainingFrame();
        attack=source.getAttack()==null?null:new fighting.Attack(source.getAttack());
    }
    public CharacterData(CharacterData other) { this.source = new struct.CharacterData(other.source); }
    public int getHp(){return hp;} public int getEnergy(){return energy;}
    public int getMaxHp(){return source.getMaxHp();}
    public int getX(){return x;} public int getY(){return y;}
    public int getLeft(){return left;} public int getRight(){return right;}
    public int getTop(){return top;} public int getBottom(){return bottom;}
    public int getSpeedX(){return speedX;} public int getSpeedY(){return speedY;}
    public State getState(){return state;} public Action getAction(){return action;}
    public boolean isFront(){return front;} public boolean isControl(){return control;}
    public int getRemainingFrame(){return remainingFrame;}
    public fighting.Attack getAttack(){return attack;}
    // 1.x--3.x called the sprite anchor "graphic centre".  v4+ renamed the horizontal
    // value to graphicAdjustX; hit-box centre is a different quantity.
    public int getGraphicCenterX(){return source.getGraphicAdjustX();}
    public int getGraphicCenterY(){return LegacyGeometry.centerY(source.isPlayerNumber());}
    public int getGraphicSizeX(){return source.getGraphicSizeX();} public int getGraphicSizeY(){return source.getGraphicSizeY();}
    public void setHp(int v){hp=v;source.setHp(v);} public void setEnergy(int v){energy=v;source.setEnergy(v);}
    public void setX(int v){x=v;source.setX(v);} public void setY(int v){y=v;source.setY(v);}
    public void setSpeedX(int v){speedX=v;source.setSpeedX(v);} public void setSpeedY(int v){speedY=v;source.setSpeedY(v);}
    public void setState(State v){state=v;source.setState(v);} public void setAction(Action v){action=v;source.setAction(v);}
    public void setFront(boolean v){front=v;source.setFront(v);} public void setControl(boolean v){control=v;source.setControl(v);}
    public void setRemainingFrame(int v){remainingFrame=v;source.setRemainingFrame(v);}
    public void setTop(int v){top=v;source.setTop(v);} public void setBottom(int v){bottom=v;source.setBottom(v);}
    public void setLeft(int v){left=v;source.setLeft(v);} public void setRight(int v){right=v;source.setRight(v);}
    public void setAttack(fighting.Attack v){attack=v;}
    public void setGraphicCenterX(int ignored){} public void setGraphicCenterY(int ignored){}
    public void setGraphicSizeX(int ignored){} public void setGraphicSizeY(int ignored){}
}
