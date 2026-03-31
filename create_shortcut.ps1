$WshShell = New-Object -comObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("C:\Users\miyoo\OneDrive\Desktop\Jason Market.lnk")
$Shortcut.TargetPath = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
$Shortcut.Arguments = '-NoExit -Command "Set-Location C:\jason_market; python menu.py"'
$Shortcut.WorkingDirectory = "C:\jason_market"
$Shortcut.Save()
Write-Host "바로가기 생성 완료"
