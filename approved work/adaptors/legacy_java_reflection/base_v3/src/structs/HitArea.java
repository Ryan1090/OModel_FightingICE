package structs;

public class HitArea {
    private int l, r, t, b;

    public HitArea() {}
    public HitArea(int l, int r, int t, int b) { this.l = l; this.r = r; this.t = t; this.b = b; }
    public HitArea(struct.HitArea source) {
        this(source == null ? 0 : source.getLeft(), source == null ? 0 : source.getRight(),
             source == null ? 0 : source.getTop(), source == null ? 0 : source.getBottom());
    }
    public void setParameters(HitArea other) { l = other.l; r = other.r; t = other.t; b = other.b; }
    public void move(int x, int y) { l += x; r += x; t += y; b += y; }
    public int getL() { return l; }
    public int getR() { return r; }
    public int getT() { return t; }
    public int getB() { return b; }
}
