import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

/** Optional callback-level trace used only by the separate adapter audit pass. */
final class AdapterAudit {
    private final BufferedWriter writer;
    private long callback;
    private int delayedFrame = -1;
    private String agent = "";
    private boolean controlledSide;

    AdapterAudit() {
        String configured = System.getProperty("legacy.adapter.audit.file", "").trim();
        if (configured.isEmpty()) { writer = null; return; }
        try {
            Path path = Path.of(configured);
            if (path.getParent() != null) Files.createDirectories(path.getParent());
            writer = Files.newBufferedWriter(path, StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING);
            writer.write("kind,callback,agent,controlled_side,frame,non_delay_frame,round,is_control,side,"+
                    "raw_hp,legacy_hp,raw_energy,legacy_energy,raw_x,legacy_x,raw_y,legacy_y,"+
                    "raw_left,legacy_left,raw_right,legacy_right,raw_top,legacy_top,raw_bottom,legacy_bottom,"+
                    "raw_speed_x,legacy_speed_x,raw_speed_y,legacy_speed_y,raw_front,legacy_front,"+
                    "raw_control,legacy_control,raw_action,legacy_action,raw_state,legacy_state,"+
                    "raw_remaining,legacy_remaining,projectiles,legacy_projectiles,key_A,key_B,key_C,key_U,key_R,key_D,key_L\n");
        } catch (IOException error) { throw new IllegalStateException("Cannot open adapter audit", error); }
    }

    void initialized(String name, boolean player) { agent = name; controlledSide = player; }

    void input(struct.FrameData raw, structs.FrameData legacy, boolean isControl) {
        callback++; delayedFrame = raw.getFramesNumber();
        if (writer == null) return;
        for (boolean side : new boolean[]{true, false}) {
            struct.CharacterData r = raw.getCharacter(side);
            structs.CharacterData l = legacy.getMyCharacter(side);
            if (r == null || l == null) continue;
            write("input,"+callback+","+agent+","+sideName(controlledSide)+","+raw.getFramesNumber()+",,"+
                    raw.getRound()+","+isControl+","+sideName(side)+","+
                    pair(r.getHp(),l.getHp())+pair(r.getEnergy(),l.getEnergy())+
                    pair(r.getX(),l.getX())+pair(r.getY(),l.getY())+
                    pair(r.getLeft(),l.getLeft())+pair(r.getRight(),l.getRight())+
                    pair(r.getTop(),l.getTop())+pair(r.getBottom(),l.getBottom())+
                    pair(r.getSpeedX(),l.getSpeedX())+pair(r.getSpeedY(),l.getSpeedY())+
                    pair(r.isFront(),l.isFront())+pair(r.isControl(),l.isControl())+
                    pair(r.getAction(),l.getAction())+pair(r.getState(),l.getState())+
                    pair(r.getRemainingFrame(),l.getRemainingFrame())+
                    raw.getProjectiles().size()+","+legacy.getProjectiles().size()+",,,,,,,\n");
        }
    }

    void nonDelay(struct.FrameData current) {
        if (writer == null) return;
        write("timing,"+callback+","+agent+","+sideName(controlledSide)+","+delayedFrame+","+
                current.getFramesNumber()+","+current.getRound()+",,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n");
    }

    void output(struct.Key key) {
        if (writer == null) return;
        write("output,"+callback+","+agent+","+sideName(controlledSide)+","+delayedFrame+",,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,"+
                key.A+","+key.B+","+key.C+","+key.U+","+key.R+","+key.D+","+key.L+"\n");
    }

    void close() {
        if (writer == null) return;
        try { writer.close(); } catch (IOException error) { throw new IllegalStateException(error); }
    }

    private static String pair(Object raw, Object legacy) { return raw+","+legacy+","; }
    private static String sideName(boolean value) { return value ? "P1" : "P2"; }
    private void write(String value) {
        try { writer.write(value); } catch (IOException error) { throw new IllegalStateException(error); }
    }
}
