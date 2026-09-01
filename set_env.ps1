# Requires PowerShell 7

$EnvFilePath = Join-Path $PSScriptRoot ".env"

if (-not (Test-Path -Path $EnvFilePath)) {
    Write-Error "The .env file was not found at: $EnvFilePath"
    exit 1
}

# Read file, ignore comments and empty lines
Get-Content -Path $EnvFilePath | Where-Object { 
    -not [string]::IsNullOrWhiteSpace($_) -and -not $_.Trim().StartsWith("#") 
} | ForEach-Object {
    # Split by the first '=' only (Limit 2)
    $Parts = $_ -split '=', 2
    
    if ($Parts.Count -eq 2) {
        $Key = $Parts[0].Trim()
        $Value = $Parts[1].Trim()

        # Remove potential wrapping quotes (double or single)
        if ($Value -match '^"(.*)"$' -or $Value -match "^'(.*)'$") {
            $Value = $matches[1]
        }

        # Set the environment variable for the current process scope
        [System.Environment]::SetEnvironmentVariable($Key, $Value, [System.EnvironmentVariableTarget]::Process)
        
        Write-Host "Set env var: $Key" -ForegroundColor Cyan
    }
}
