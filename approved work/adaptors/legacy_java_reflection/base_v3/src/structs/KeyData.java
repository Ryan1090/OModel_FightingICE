package structs;

public class KeyData {
    private final Key[] keys;
    public KeyData(int players){keys = new Key[Math.max(2, players)]; for(int i=0;i<keys.length;i++)keys[i]=new Key();}
    public KeyData(Key[] source){keys=source.clone();}
    public KeyData(KeyData source){this(source.keys);}
    public Key[] getKey(){return keys;} public void setPlayerOne(Key k){keys[0]=k;} public void setPlayerTwo(Key k){keys[1]=k;}
    public Key getPlayer(int i){return keys[i];} public Key getPlayer(boolean p){return keys[p?0:1];}
    public Key getPlayerOne(){return keys[0];} public Key getPlayerTwo(){return keys[1];}
    public Key getMyKey(boolean p){return getPlayer(p);} public Key getOpponentKey(boolean p){return getPlayer(!p);}
}
