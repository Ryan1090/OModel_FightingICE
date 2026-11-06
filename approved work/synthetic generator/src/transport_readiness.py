"""Run-local transport readiness; never connects a dummy protocol client."""
import ctypes,functools,inspect,os,socket,struct,textwrap

def listener_rows(family):
    if os.name!='nt':raise RuntimeError('Windows TCP ownership inspection required')
    api=ctypes.windll.iphlpapi.GetExtendedTcpTable
    size=ctypes.c_ulong(0)
    result=api(None,ctypes.byref(size),False,family,3,0)
    if family==23 and result==50:return []
    if result not in (0,122):raise ctypes.WinError(result)
    while True:
        data=ctypes.create_string_buffer(size.value)
        result=api(data,ctypes.byref(size),False,family,3,0)
        if result==122:continue
        if result:raise ctypes.WinError(result)
        count=struct.unpack_from('<I',data.raw)[0]
        rows=[]
        for i in range(count):
            if family==2:
                state,address,local_port,remote,remote_port,owner=struct.unpack_from('<6I',data.raw,4+24*i)
            else:
                offset=4+56*i
                local_port=struct.unpack_from('<I',data.raw,offset+20)[0]
                state,owner=struct.unpack_from('<2I',data.raw,offset+48)
            # Table class 3 requests OWNER_PID_LISTENER entries exclusively.
            # Match the table's owned listening endpoint, without a redundant
            # state-field filter that rejected real listeners on this host.
            rows.append({'port':socket.ntohs(local_port & 65535),'pid':owner,'family':family,'native_state':state})
        return rows

def listening(port,pid):
    return any(row['port']==port and row['pid']==pid for family in (2,23) for row in listener_rows(family))

def transformed_source(original):
    source=textwrap.dedent(inspect.getsource(original))
    before="if 'Socket server is started' in text or 'Waiting to launch a game' in text:break"
    after="if ('Socket server is started' in text or 'Waiting to launch a game' in text) and production_tcp_listening(self.port,self.proc.pid):break"
    if source.count(before)!=1:raise RuntimeError('Transport readiness source precondition')
    return source.replace(before,after)

