package gameInterface;

import structs.FrameData;
import structs.GameData;
import structs.Key;

/** Binary-compatible surface used by FightingICE 1.x-era agents. */
public interface AIInterface {
    String CHARACTER_ZEN = "ZEN";
    String CHARACTER_GARNET = "GARNET";
    String CHARACTER_LUD = "LUD";
    String CHARACTER_KFM = "KFM";

    int initialize(GameData gameData, boolean playerNumber);
    void getInformation(FrameData frameData);
    void processing();
    Key input();
    void close();
    String getCharacter();
}
