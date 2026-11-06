import java.io.*;
import java.lang.reflect.*;
import command.CommandTable;
import enumerate.State;
import struct.Key;

/** Read-only calls into the approved jar; does not patch any engine class. */
public class CommandOracle {
    public static void main(String[] args) throws Exception {
        Method method=CommandTable.class.getDeclaredMethod("convertKeyToAction",boolean.class,boolean.class,
            boolean.class,Key.class,int[].class,State.class,boolean.class);
        method.setAccessible(true);
        CommandTable table=new CommandTable();
        BufferedReader input=new BufferedReader(new InputStreamReader(System.in));
        String line;
        while((line=input.readLine())!=null){
            // Framed batches let the diagnostic reuse this read-only decoder.
            // Each row still calls the approved engine's stateless converter.
            if(line.equals("__GMTV_END__")){
                System.out.println("__GMTV_END__");System.out.flush();continue;
            }
            String[] a=line.split("\t"); Key key=new Key();
            key.A=a[5].charAt(0)=='1';key.B=a[5].charAt(1)=='1';key.C=a[5].charAt(2)=='1';
            key.U=a[5].charAt(3)=='1';key.D=a[5].charAt(4)=='1';key.L=a[5].charAt(5)=='1';key.R=a[5].charAt(6)=='1';
            int[] directions={Integer.parseInt(a[6]),Integer.parseInt(a[7]),Integer.parseInt(a[8]),Integer.parseInt(a[9])};
            System.out.println(method.invoke(table,Boolean.parseBoolean(a[2]),Boolean.parseBoolean(a[3]),
                Boolean.parseBoolean(a[4]),key,directions,State.valueOf(a[0]),Boolean.parseBoolean(a[1])));
        }
    }
}
