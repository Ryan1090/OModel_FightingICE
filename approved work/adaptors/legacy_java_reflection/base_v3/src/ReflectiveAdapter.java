import java.io.File;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLClassLoader;

/**
 * Current entry point for historical agents whose callback signatures vary by release.
 * It translates only API objects/callback shapes; it never selects an action itself.
 */
public final class ReflectiveAdapter implements aiinterface.AIInterface {
    private Object agent;
    private Method initialize, information, processing, input, close;
    private boolean oldStructs;
    private final AdapterAudit audit = new AdapterAudit();

    @Override public int initialize(struct.GameData gameData, boolean playerNumber) {
        String className = System.getProperty("legacy.agent.class");
        if (className == null || className.isBlank()) throw new IllegalStateException("-Dlegacy.agent.class is required");
        try {
            URL agentJar = new File("data/ai/ReflectiveAdapter.jar").toURI().toURL();
            ClassLoader loader = new URLClassLoader(new URL[]{agentJar}, ReflectiveAdapter.class.getClassLoader());
            Class<?> type = Class.forName(className, true, loader);
            agent = type.getDeclaredConstructor().newInstance();
            initialize = find(type, "initialize", 2);
            information = find(type, "getInformation", -1);
            processing = find(type, "processing", 0);
            input = find(type, "input", 0);
            close = find(type, "close", 0);
            oldStructs = initialize.getParameterTypes()[0].getName().equals("structs.GameData");
            Object result = initialize.invoke(agent, oldStructs ? new structs.GameData(gameData) : gameData, playerNumber);
            audit.initialized(className, playerNumber);
            return result instanceof Number ? ((Number) result).intValue() : 0;
        } catch (ReflectiveOperationException | java.net.MalformedURLException e) {
            throw failure("initialize", e);
        }
    }

    @Override public void getInformation(struct.FrameData frameData, boolean isControl) {
        try {
            Object translated = oldStructs ? new structs.FrameData(frameData) : frameData;
            if (oldStructs) audit.input(frameData, (structs.FrameData) translated, isControl);
            if (information.getParameterCount() == 1) information.invoke(agent, translated);
            else information.invoke(agent, translated, isControl);
        } catch (ReflectiveOperationException e) { throw failure("getInformation", e); }
    }

    @Override public void processing(){invokeVoid(processing, "processing");}
    @Override public void getNonDelayFrameData(struct.FrameData frameData){audit.nonDelay(frameData);}
    @Override public struct.Key input(){
        try {
            Object value = input.invoke(agent);
            if (value == null) { struct.Key key=new struct.Key(); audit.output(key); return key; }
            if (value instanceof struct.Key) { struct.Key key=(struct.Key)value; audit.output(key); return key; }
            if (value instanceof structs.Key) { struct.Key key=((structs.Key)value).toCurrent(); audit.output(key); return key; }
            throw new IllegalStateException("unsupported key type " + value.getClass().getName());
        } catch (ReflectiveOperationException e) { throw failure("input", e); }
    }
    @Override public void close(){if(agent!=null)invokeVoid(close,"close"); audit.close();}

    private void invokeVoid(Method method, String callback) {
        try { method.invoke(agent); } catch (ReflectiveOperationException e) { throw failure(callback,e); }
    }
    private static Method find(Class<?> type, String name, int parameters) throws NoSuchMethodException {
        for (Method method : type.getMethods())
            if (method.getName().equals(name) && (parameters < 0 || method.getParameterCount() == parameters)) return method;
        throw new NoSuchMethodException(type.getName()+"."+name);
    }
    private static IllegalStateException failure(String callback, Exception error) {
        Throwable cause = error instanceof InvocationTargetException && error.getCause()!=null ? error.getCause() : error;
        return new IllegalStateException("historical agent failed in "+callback, cause);
    }
}
