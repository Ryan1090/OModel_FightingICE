package structs;

import java.util.ArrayDeque;
import java.util.Deque;

public final class FrameData {
    private final struct.FrameData source;
    // Public in the 2014 ABI; keeping them also satisfies later getter-based agents.
    public CharacterData P1, P2;
    public long remainingTime;
    public int round;
    public Deque<fighting.Attack> attack;
    public KeyData keyData;
    public boolean emptyFlag;
    public FrameData(){this(new struct.FrameData());}
    public FrameData(struct.FrameData source){
        this.source = new struct.FrameData(source);
        P1=wrap(true); P2=wrap(false); remainingTime=historicalRemainingTime(source); round=source.getRound();
        attack=buildAttacks(); keyData=buildKeyData(); emptyFlag=source.getEmptyFlag();
    }
    public FrameData(FrameData other){this(other.source);}
    public void empty(){emptyFlag=true;} public void loading(int ignored){}
    public CharacterData getP1(){return P1;} public CharacterData getP2(){return P2;}
    public long getRemainingTime(){return remainingTime;} public int getRound(){return round;}
    public long getRemainingTimeMilliseconds(){return source.getRemainingTimeMilliseconds();}
    public long getRemainingTimeNanoSeconds(){return source.getRemainingTimeMilliseconds()*1_000_000L;}
    public long getRemainingFramesNumber(){return source.getRemainingFramesNumber();}
    public long getRemainingFrame(){return source.getRemainingFramesNumber();}
    // The audited v3.20 toolkit initializes its dummy pre-round FrameData.nowFrame to -1.
    // The audited v2.10 toolkit instead derives getFrameNumber() from dummy remainingTime=-1;
    // Java's double-to-int conversion makes that result 0. Some older-source submissions
    // explicitly test for 0, so the recovery launcher can select that historical convention.
    // This changes only an empty snapshot marker; valid engine frame numbers are untouched.
    public int getFrameNumber(){
        return emptyFlag ? Integer.getInteger("legacy.empty.frame.number", -1) : source.getFramesNumber();
    }
    public Deque<fighting.Attack> getProjectiles(){return attack;}
    public Deque<fighting.Attack> getProjectilesByP1(){return buildProjectileSide(true);}
    public Deque<fighting.Attack> getProjectilesByP2(){return buildProjectileSide(false);}
    private Deque<fighting.Attack> buildAttacks(){
        Deque<fighting.Attack> result = new ArrayDeque<>();
        for (struct.AttackData attack : source.getProjectiles()) result.add(new fighting.Attack(attack));
        return result;
    }
    public Deque<fighting.Attack> getAttack(){return attack;}
    private KeyData buildKeyData(){
        KeyData result = new KeyData(2);
        CharacterData p1 = getP1(), p2 = getP2();
        struct.CharacterData c1 = source.getCharacter(true), c2 = source.getCharacter(false);
        if(c1 != null && !c1.getInputCommand().isEmpty()) result.setPlayerOne(Key.fromCurrent(c1.getInputCommand().peekLast()));
        if(c2 != null && !c2.getInputCommand().isEmpty()) result.setPlayerTwo(Key.fromCurrent(c2.getInputCommand().peekLast()));
        return result;
    }
    public KeyData getKeyData(){return keyData;}
    public CharacterData getMyCharacter(boolean p){return p?P1:P2;} public CharacterData getOpponentCharacter(boolean p){return p?P2:P1;}
    public boolean getEmptyFlag(){return emptyFlag;}
    public struct.FrameData toCurrent(){return new struct.FrameData(source);}
    private Deque<fighting.Attack> buildProjectileSide(boolean p){
        Deque<fighting.Attack> result=new ArrayDeque<>();
        for(struct.AttackData value:(p?source.getProjectilesByP1():source.getProjectilesByP2())) result.add(new fighting.Attack(value));
        return result;
    }
    private CharacterData wrap(boolean p){struct.CharacterData value=source.getCharacter(p); return value==null?null:new CharacterData(value);}

    /**
     * Reproduce the unit used by the API generation for which the archived policy was built.
     *
     * <p>The 1.01, 1.21 and 2.10 toolkit bytecode stores wall-clock milliseconds in the
     * historical {@code remainingTime} field.  The 3.20 and 4.50 toolkits changed
     * {@code getRemainingTime()} to whole seconds.  v7.1 retains the latter method, so simply
     * delegating to it silently changed every old threshold such as 5,000 or 30,000.</p>
     *
     * <p>The recovery launcher sets {@code -Dlegacy.remaining.time.unit=milliseconds} for the
     * 2014--2016 generations and {@code seconds} for later generations.  Empty data preserves
     * the adapter's established zero sentinel.</p>
     */
    private static long historicalRemainingTime(struct.FrameData value){
        if(value.getEmptyFlag()) return 0;
        String unit=System.getProperty("legacy.remaining.time.unit", "seconds");
        if("milliseconds".equalsIgnoreCase(unit)) return value.getRemainingTimeMilliseconds();
        if("seconds".equalsIgnoreCase(unit)) return value.getRemainingTime();
        throw new IllegalArgumentException("Unsupported legacy.remaining.time.unit="+unit);
    }
}
