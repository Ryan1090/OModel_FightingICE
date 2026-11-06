package structs;

import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

/** Loads the sprite anchor values that the 1.x--3.x CharacterData API exposed. */
final class LegacyGeometry {
    private static final int[] centerY = new int[]{Integer.MIN_VALUE, Integer.MIN_VALUE};

    private LegacyGeometry() {}

    static synchronized void configure(boolean playerNumber, String characterName) {
        int index = playerNumber ? 0 : 1;
        Path path = Path.of("data", "characters", characterName, "gSetting.txt");
        try (BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
            reader.readLine();
            String[] center = reader.readLine().split(",");
            centerY[index] = Integer.parseInt(center[1].trim());
        } catch (IOException | RuntimeException error) {
            throw new IllegalStateException("Cannot recover legacy graphic centre from " + path, error);
        }
    }

    static int centerY(boolean playerNumber) {
        int value = centerY[playerNumber ? 0 : 1];
        if (value == Integer.MIN_VALUE) {
            throw new IllegalStateException("LegacyGeometry used before GameData initialization");
        }
        return value;
    }
}
