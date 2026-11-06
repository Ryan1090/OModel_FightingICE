import java.io.File;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLClassLoader;

/**
 * Side-scoped form of the validated legacy adapter.
 *
 * It translates only callback/API shapes.  It does not select, suppress, retry,
 * or otherwise alter an agent action.  Side-specific property names allow two
 * independently configured legacy adapters to coexist in one engine process.
 */
abstract class SideReflectiveAdapter implements aiinterface.AIInterface {
    private final String propertyPrefix;
    private final String ownJar;
    private Object agent;
    private Method initialize, information, processing, input, close;
    private boolean oldStructs;
    private int emptyFrameNumber;
    private String remainingTimeUnit;

    SideReflectiveAdapter(String side, String ownJar) {
        this.propertyPrefix = "legacy." + side + ".";
        this.ownJar = ownJar;
    }

    @Override public int initialize(struct.GameData gameData, boolean playerNumber) {
        String className = System.getProperty(propertyPrefix + "agent.class");
        if (className == null || className.isBlank())
            throw new IllegalStateException("-D" + propertyPrefix + "agent.class is required");
        try {
            URL agentJar = new File(ownJar).toURI().toURL();
            ClassLoader loader = new URLClassLoader(new URL[]{agentJar}, getClass().getClassLoader());
            Class<?> type = Class.forName(className, true, loader);
            agent = type.getDeclaredConstructor().newInstance();
            initialize = find(type, "initialize", 2);
            information = find(type, "getInformation", -1);
            processing = find(type, "processing", 0);
            input = find(type, "input", 0);
            close = find(type, "close", 0);
            oldStructs = initialize.getParameterTypes()[0].getName().equals("structs.GameData");
            emptyFrameNumber = Integer.getInteger(propertyPrefix + "empty.frame.number", -1);
            remainingTimeUnit = System.getProperty(propertyPrefix + "remaining.time.unit", "seconds");
            Object result = initialize.invoke(agent, oldStructs ? new structs.GameData(gameData) : gameData, playerNumber);
            return result instanceof Number ? ((Number) result).intValue() : 0;
        } catch (ReflectiveOperationException | java.net.MalformedURLException error) {
            throw failure("initialize", error);
        }
    }

    @Override public void getInformation(struct.FrameData frameData, boolean isControl) {
        try {
            Object translated = oldStructs
                    ? new structs.FrameData(frameData, emptyFrameNumber, remainingTimeUnit)
                    : frameData;
            if (information.getParameterCount() == 1) information.invoke(agent, translated);
            else information.invoke(agent, translated, isControl);
        } catch (ReflectiveOperationException error) { throw failure("getInformation", error); }
    }

    @Override public void processing() { invokeVoid(processing, "processing"); }
    @Override public void getNonDelayFrameData(struct.FrameData frameData) { }

    @Override public struct.Key input() {
        try {
            Object value = input.invoke(agent);
            if (value == null) return new struct.Key();
            if (value instanceof struct.Key) return (struct.Key) value;
            if (value instanceof structs.Key) return ((structs.Key) value).toCurrent();
            throw new IllegalStateException("unsupported key type " + value.getClass().getName());
        } catch (ReflectiveOperationException error) { throw failure("input", error); }
    }

    @Override public void close() { if (agent != null) invokeVoid(close, "close"); }

    private void invokeVoid(Method method, String callback) {
        try { method.invoke(agent); } catch (ReflectiveOperationException error) { throw failure(callback, error); }
    }

    private static Method find(Class<?> type, String name, int parameters) throws NoSuchMethodException {
        for (Method method : type.getMethods())
            if (method.getName().equals(name) && (parameters < 0 || method.getParameterCount() == parameters)) return method;
        throw new NoSuchMethodException(type.getName() + "." + name);
    }

    private static IllegalStateException failure(String callback, Exception error) {
        Throwable cause = error instanceof InvocationTargetException && error.getCause() != null ? error.getCause() : error;
        return new IllegalStateException("historical agent failed in " + callback, cause);
    }
}
