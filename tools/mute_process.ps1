param(
    [Parameter(Mandatory = $true)][int]$ProcessId,
    [int]$Seconds = 40,
    [switch]$Unmute
)
# Mutes (or unmutes) ONLY the Windows audio sessions of one process. The system volume, other applications and the
# volume settings of the game itself are not touched. Sessions that the process opens later are muted too.
$src = @"
using System;
using System.Runtime.InteropServices;
namespace GhostOpsAudio {
  [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class MMDeviceEnumeratorCom {}
  [ComImport, Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IMMDeviceEnumerator { int EnumAudioEndpoints(int f, int m, out IntPtr d); int GetDefaultAudioEndpoint(int f, int r, out IMMDevice d); }
  [ComImport, Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IMMDevice { int Activate(ref Guid id, int ctx, IntPtr p, [MarshalAs(UnmanagedType.IUnknown)] out object o); }
  [ComImport, Guid("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IAudioSessionManager2 { int a(); int b(); int GetSessionEnumerator(out IAudioSessionEnumerator e); }
  [ComImport, Guid("E2F5BB11-0570-40CA-ACDD-3AA01277DEE8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IAudioSessionEnumerator { int GetCount(out int c); int GetSession(int i, out IAudioSessionControl2 s); }
  [ComImport, Guid("bfb7ff88-7239-4fc9-8fa2-07c950be9c6d"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IAudioSessionControl2 {
    int a(); int b(); int c(); int d(); int e(); int f(); int g(); int h(); int i();
    int GetSessionIdentifier([MarshalAs(UnmanagedType.LPWStr)] out string s);
    int GetSessionInstanceIdentifier([MarshalAs(UnmanagedType.LPWStr)] out string s);
    int GetProcessId(out int pid);
    int IsSystemSoundsSession(); int SetDuckingPreference(bool b);
  }
  [ComImport, Guid("87CE5498-68D6-44E5-9215-6DA47EF883D8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface ISimpleAudioVolume { int SetMasterVolume(float v, ref Guid c); int GetMasterVolume(out float v); int SetMute(bool m, ref Guid c); int GetMute(out bool m); }
  public static class Sessions {
    // returns the number of sessions of the process; sets their mute flag; muted = how many report the wanted state afterwards
    public static int Apply(int pid, bool mute, out int confirmed) {
      confirmed = 0; int found = 0;
      var en = (IMMDeviceEnumerator)new MMDeviceEnumeratorCom();
      IMMDevice dev; en.GetDefaultAudioEndpoint(0, 1, out dev);
      Guid iid = typeof(IAudioSessionManager2).GUID; object o; dev.Activate(ref iid, 23, IntPtr.Zero, out o);
      var mgr = (IAudioSessionManager2)o; IAudioSessionEnumerator se; mgr.GetSessionEnumerator(out se);
      int n; se.GetCount(out n);
      for (int i = 0; i < n; i++) {
        IAudioSessionControl2 c; se.GetSession(i, out c); int p; c.GetProcessId(out p);
        if (p != pid) continue;
        found++; var v = (ISimpleAudioVolume)c; Guid g = Guid.Empty; v.SetMute(mute, ref g);
        bool m; v.GetMute(out m); if (m == mute) confirmed++;
      }
      return found;
    }
  }
}
"@
Add-Type -TypeDefinition $src
$want = -not $Unmute
$deadline = (Get-Date).AddSeconds($Seconds)
$lastFound = 0; $lastConfirmed = 0
while ((Get-Date) -lt $deadline) {
    if (-not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) { break }
    $confirmed = 0
    $found = [GhostOpsAudio.Sessions]::Apply($ProcessId, $want, [ref]$confirmed)
    $lastFound = $found; $lastConfirmed = $confirmed
    Start-Sleep -Milliseconds 500
}
"sessions=$lastFound confirmed=$lastConfirmed mute=$want"
