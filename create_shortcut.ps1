$WshShell = New-Object -comObject WScript.Shell
$DesktopPath = "C:\Users\miyoo\OneDrive\Desktop"
$ProjectPath = "$DesktopPath\jason_market"
$Shortcut = $WshShell.CreateShortcut("$DesktopPath\Jason Market.lnk")

$Shortcut.TargetPath = "powershell.exe"
$Shortcut.Arguments = "-NoExit -Command `"Set-Location '$ProjectPath'; python menu.py`""
$Shortcut.WorkingDirectory = $ProjectPath
$Shortcut.Description = "Run Jason Market Portfolio Tracker"
$Shortcut.IconLocation = "powershell.exe, 0"
$Shortcut.Save()

Write-Host "✅ 바탕화면에 'Jason Market' 바로가기가 생성되었습니다."
