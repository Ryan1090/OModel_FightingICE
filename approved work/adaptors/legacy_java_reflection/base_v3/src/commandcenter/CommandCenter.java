package commandcenter;

public class CommandCenter {
    private final aiinterface.CommandCenter delegate = new aiinterface.CommandCenter();
    private structs.FrameData frame;
    private boolean player;
    public CommandCenter() {}
    public boolean getskillFlag(){return delegate.getSkillFlag();}
    public boolean getSkillFlag(){return delegate.getSkillFlag();}
    public void setFrameData(structs.FrameData value, boolean playerNumber){this.frame=value; this.player=playerNumber; delegate.setFrameData(value.toCurrent(),playerNumber);}
    public void setFrameData(struct.FrameData current, boolean playerNumber){this.frame=new structs.FrameData(current); this.player=playerNumber; delegate.setFrameData(current,playerNumber);}
    public void commandCall(String command){delegate.commandCall(command);}
    public void skillCancel(){delegate.skillCancel();}
    public structs.Key getSkillKey(){return structs.Key.fromCurrent(delegate.getSkillKey());}
    public int getMyHP(){return getMyCharacter().getHp();} public int getMyEnergy(){return getMyCharacter().getEnergy();}
    public int getEnemyHP(){return getEnemyCharacter().getHp();} public int getEnemyEnergy(){return getEnemyCharacter().getEnergy();}
    public int getMyX(){return getMyCharacter().getX();} public int getMyY(){return getMyCharacter().getY();}
    public int getEnemyX(){return getEnemyCharacter().getX();} public int getEnemyY(){return getEnemyCharacter().getY();}
    public int getDistanceX(){return Math.abs(getMyX()-getEnemyX());} public int getDistanceY(){return Math.abs(getMyY()-getEnemyY());}
    public structs.CharacterData getMyCharacter(){return frame.getMyCharacter(player);}
    public structs.CharacterData getEnemyCharacter(){return frame.getOpponentCharacter(player);}
}
