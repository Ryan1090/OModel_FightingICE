import gameInterface.AIInterface;
import java.io.File;
import java.net.URL;
import java.net.URLClassLoader;

/** Current 7.1 entry point delegating to an unmodified 1.x-era controller. */
public final class LegacyAdapter implements aiinterface.AIInterface {
    private AIInterface legacy;
    private boolean player;

    @Override public int initialize(struct.GameData gameData, boolean playerNumber) {
        player = playerNumber;
        String className = System.getProperty("legacy.agent.class");
        if (className == null || className.isBlank()) throw new IllegalStateException("-Dlegacy.agent.class is required");
        try {
            URL agentJar = new File("data/ai/LegacyAdapter.jar").toURI().toURL();
            ClassLoader loader = new URLClassLoader(new URL[]{agentJar}, LegacyAdapter.class.getClassLoader());
            legacy = (AIInterface) Class.forName(className, true, loader).getDeclaredConstructor().newInstance();
            return legacy.initialize(new structs.GameData(gameData), playerNumber);
        } catch (ReflectiveOperationException | java.net.MalformedURLException e) {
            throw new IllegalStateException("cannot construct legacy agent " + className, e);
        }
    }

    @Override public void getInformation(struct.FrameData frameData, boolean isControl) {
        legacy.getInformation(new structs.FrameData(frameData));
        // Historical CommandCenter instances receive their frame through the agent's own call.
    }
    @Override public void processing(){legacy.processing();}
    @Override public struct.Key input(){structs.Key key=legacy.input(); return key==null?new struct.Key():key.toCurrent();}
    @Override public void close(){if(legacy!=null)legacy.close();}
}
