package structs;

/** Legacy key object. Field names deliberately match the historical ABI. */
public class Key {
    public boolean A, B, C, U, R, D, L;

    public Key() {}

    public Key(Key other) {
        A = other.A; B = other.B; C = other.C;
        U = other.U; R = other.R; D = other.D; L = other.L;
    }

    public void empty() { A = B = C = U = R = D = L = false; }

    public int getLever() { return getLever(true); }

    public int getLever(boolean front) {
        int horizontal = L ? (front ? 4 : 6) : R ? (front ? 6 : 4) : 0;
        if (U) return horizontal == 4 ? 7 : horizontal == 6 ? 9 : 8;
        if (D) return horizontal == 4 ? 1 : horizontal == 6 ? 3 : 2;
        return horizontal == 0 ? 5 : horizontal;
    }

    public static Key fromCurrent(struct.Key source) {
        Key key = new Key();
        if (source != null) {
            key.A = source.A; key.B = source.B; key.C = source.C;
            key.U = source.U; key.R = source.R; key.D = source.D; key.L = source.L;
        }
        return key;
    }

    public struct.Key toCurrent() {
        struct.Key key = new struct.Key();
        key.A = A; key.B = B; key.C = C;
        key.U = U; key.R = R; key.D = D; key.L = L;
        return key;
    }
}
