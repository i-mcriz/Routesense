Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\chris\Downloads\Routesense"
WshShell.Run "cmd /c ""C:\Users\chris\Downloads\Routesense\Launch_RouteSense_WebApp.bat""", 0, False
