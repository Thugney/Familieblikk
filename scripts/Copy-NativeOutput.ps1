function Copy-NativeOutputToFile {
    param([string]$Executable, [string[]]$NativeArguments, [string]$DestinationPath)
    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $Executable
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    foreach ($argument in $NativeArguments) { $startInfo.ArgumentList.Add($argument) }
    $stream = [IO.File]::Open($DestinationPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    try {
        if (-not $process.Start()) { throw 'Kunne ikke starte sikkerhetskopieringsprosessen.' }
        $errors = $process.StandardError.ReadToEndAsync()
        # Binary stream copied directly to disk; no PowerShell text conversion or full archive buffer.
        $process.StandardOutput.BaseStream.CopyTo($stream, 65536)
        $stream.Flush($true)
        $process.WaitForExit()
        $errorText = $errors.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) { throw "Sikkerhetskopieringen feilet. Ufullstendig fil er beholdt for kontroll. $errorText" }
    } finally {
        $stream.Dispose()
        $process.Dispose()
    }
}
