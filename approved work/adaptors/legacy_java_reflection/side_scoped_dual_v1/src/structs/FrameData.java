package structs;

import java.util.ArrayDeque;
import java.util.Deque;

/**
 * Legacy FrameData translation with instance-scoped compatibility settings.
 *
 * The validated single-adapter implementation used JVM-global properties.
 * A dual-adapter engine needs the same settings per adapter side so two
 * historical API generations can coexist without a property race.
 */
public final class FrameData {
    private final struct.FrameData source;
    private final int emptyFrameNumber;
    private final String remainingTimeUnit;
    public CharacterData P1, P2;
    public long remainingTime;
    public int round;
    public Deque<fighting.Attack> attack;
    public KeyData keyData;
    public boolean emptyFlag;

    public FrameData() {
        this(new struct.FrameData(),
                Integer.getInteger("legacy.empty.frame.number", -1),
                System.getProperty("legacy.remaining.time.unit", "seconds"));
    }

    public FrameData(struct.FrameData source) {
        this(source,
                Integer.getInteger("legacy.empty.frame.number", -1),
                System.getProperty("legacy.remaining.time.unit", "seconds"));
    }

    public FrameData(struct.FrameData source, int emptyFrameNumber, String remainingTimeUnit) {
        this.source = new struct.FrameData(source);
        this.emptyFrameNumber = emptyFrameNumber;
        this.remainingTimeUnit = remainingTimeUnit;
        P1 = wrap(true);
        P2 = wrap(false);
        remainingTime = historicalRemainingTime(source, remainingTimeUnit);
        round = source.getRound();
        attack = buildAttacks();
        keyData = buildKeyData();
        emptyFlag = source.getEmptyFlag();
    }

    public FrameData(FrameData other) {
        this(other.source, other.emptyFrameNumber, other.remainingTimeUnit);
    }

    public void empty() { emptyFlag = true; }
    public void loading(int ignored) { }
    public CharacterData getP1() { return P1; }
    public CharacterData getP2() { return P2; }
    public long getRemainingTime() { return remainingTime; }
    public int getRound() { return round; }
    public long getRemainingTimeMilliseconds() { return source.getRemainingTimeMilliseconds(); }
    public long getRemainingTimeNanoSeconds() { return source.getRemainingTimeMilliseconds() * 1_000_000L; }
    public long getRemainingFramesNumber() { return source.getRemainingFramesNumber(); }
    public long getRemainingFrame() { return source.getRemainingFramesNumber(); }
    public int getFrameNumber() { return emptyFlag ? emptyFrameNumber : source.getFramesNumber(); }
    public Deque<fighting.Attack> getProjectiles() { return attack; }
    public Deque<fighting.Attack> getProjectilesByP1() { return buildProjectileSide(true); }
    public Deque<fighting.Attack> getProjectilesByP2() { return buildProjectileSide(false); }
    public Deque<fighting.Attack> getAttack() { return attack; }
    public KeyData getKeyData() { return keyData; }
    public CharacterData getMyCharacter(boolean player) { return player ? P1 : P2; }
    public CharacterData getOpponentCharacter(boolean player) { return player ? P2 : P1; }
    public boolean getEmptyFlag() { return emptyFlag; }
    public struct.FrameData toCurrent() { return new struct.FrameData(source); }

    private Deque<fighting.Attack> buildAttacks() {
        Deque<fighting.Attack> result = new ArrayDeque<>();
        for (struct.AttackData value : source.getProjectiles()) result.add(new fighting.Attack(value));
        return result;
    }

    private KeyData buildKeyData() {
        KeyData result = new KeyData(2);
        struct.CharacterData first = source.getCharacter(true);
        struct.CharacterData second = source.getCharacter(false);
        if (first != null && !first.getInputCommand().isEmpty())
            result.setPlayerOne(Key.fromCurrent(first.getInputCommand().peekLast()));
        if (second != null && !second.getInputCommand().isEmpty())
            result.setPlayerTwo(Key.fromCurrent(second.getInputCommand().peekLast()));
        return result;
    }

    private Deque<fighting.Attack> buildProjectileSide(boolean player) {
        Deque<fighting.Attack> result = new ArrayDeque<>();
        for (struct.AttackData value : (player ? source.getProjectilesByP1() : source.getProjectilesByP2()))
            result.add(new fighting.Attack(value));
        return result;
    }

    private CharacterData wrap(boolean player) {
        struct.CharacterData value = source.getCharacter(player);
        return value == null ? null : new CharacterData(value);
    }

    private static long historicalRemainingTime(struct.FrameData value, String unit) {
        if (value.getEmptyFlag()) return 0;
        if ("milliseconds".equalsIgnoreCase(unit)) return value.getRemainingTimeMilliseconds();
        if ("seconds".equalsIgnoreCase(unit)) return value.getRemainingTime();
        throw new IllegalArgumentException("Unsupported legacy remaining-time unit=" + unit);
    }
}
