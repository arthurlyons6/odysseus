<#
.SYNOPSIS
Local PowerShell execution wrapper. Executes `Command` via cmd.exe /c,
captures stdout/stderr, and returns a single JSON line.

.PARAMETER Command
Shell command to execute. Filesystem or console commands are fine.

.PARAMETER TimeoutSeconds
Hard timeout. Default: 120.

.PARAMETER WorkingDirectory
Working directory. Default: C:\Users\13464\odysseus

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File C:\Users\13464\odysseus\scripts\Invoke-CommandWithOutput.ps1 -Command 'dir /b .'
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true, Position=0)]
  [string]$Command,
  [Parameter(Mandatory=$false)]
  [int]$TimeoutSeconds = 120,
  [Parameter(Mandatory=$false)]
  [string]$WorkingDirectory = 'C:\Users\13464\odysseus'
)

$ErrorActionPreference = 'SilentlyContinue'
$InformationPreference = 'SilentlyContinue'
$ProgressPreference = 'SilentlyContinue'

$startMs = [long]((Get-Date -AsUTC) - [datetime]'1970-01-01T00:00:00Z').TotalMilliseconds

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = if ($IsWindows) { $env:ComSpec } else { '/bin/sh' }
$psi.Arguments = '/c "' + ($Command -replace '\"', [char]34 * 2) + '"'
$psi.WorkingDirectory = $WorkingDirectory
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.CreateNoWindow = $true
$psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
$psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8

$p = [System.Diagnostics.Process]::Start($psi)
$exited = $p.WaitForExit($TimeoutSeconds * 1000)
$stdo = $p.StandardOutput.ReadToEnd()
$stde = $p.StandardError.ReadToEnd()
if (-not $exited) {
  try { $p.Kill() } catch {}
}
$endMs = [long]((Get-Date -AsUTC) - [datetime]'1970-01-01T00:00:00Z').TotalMilliseconds)
$durationMs = [long]($endMs - $startMs)
if ($durationMs -lt 0) { $durationMs = 0 }

$result = New-Object PSObject -Property @{
  ok          = [bool]($exited)
  command     = $Command
  exitCode    = [int]($p.ExitCode)
  stdout      = $stdo
  stderr      = $stde
  timedOut    = [bool](-not $exited)
  runnerError = ''
  workingDir  = $WorkingDirectory
  durationMs  = [long]$durationMs
  processId   = [int]$p.Id
}
try {
  ($result | ConvertTo-Json -Compress)
} catch {
  '{"ok":false,"command":"' + $Command + '","exitCode":-1,"stdout":"","stderr":"serialize failed","timedOut":false,"runnerError":"serialize_failed","workingDir":"' + $WorkingDirectory + '","durationMs":0,"processId":' + $p.Id + '}'
}
