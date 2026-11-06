package structs;

import java.util.Vector;

public class GameData {
    private final struct.GameData source;
    public GameData(struct.GameData source){
        this.source=source;
        LegacyGeometry.configure(true, source.getCharacterName(true));
        LegacyGeometry.configure(false, source.getCharacterName(false));
    }
    public int getStageXMax(){return source.getStageWidth();} public int getStageYMax(){return source.getStageHeight();}
    public int getPlayerOneMaxEnergy(){return source.getMaxEnergy(true);} public int getPlayerTwoMaxEnergy(){return source.getMaxEnergy(false);}
    public Vector<MotionData> getPlayerOneMotion(){return motion(true);} public Vector<MotionData> getPlayerTwoMotion(){return motion(false);}
    public String getPlayerOneCharacterName(){return source.getCharacterName(true);} public String getPlayerTwoCharacterName(){return source.getCharacterName(false);}
    public int getMyMaxEnergy(boolean p){return source.getMaxEnergy(p);} public int getOpponentMaxEnergy(boolean p){return source.getMaxEnergy(!p);}
    public Vector<MotionData> getMyMotion(boolean p){return motion(p);} public Vector<MotionData> getOpponentMotion(boolean p){return motion(!p);}
    public String getMyName(boolean p){return source.getCharacterName(p);} public String getOpponentName(boolean p){return source.getCharacterName(!p);}
    public simulator.Simulator getSimulator(){return source.getSimulator();}
    /** Infrastructure bridge used only by the engine's historical Simulator overload. */
    public struct.GameData toCurrent(){return source;}
    private Vector<MotionData> motion(boolean p){Vector<MotionData> out=new Vector<>(); for(struct.MotionData m:source.getMotionData(p))out.add(new MotionData(m)); return out;}
}
