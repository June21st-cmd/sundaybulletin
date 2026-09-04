param (
    [string]$TargetDate = ""
)

$envPath = "C:\Users\june2\.gemini\antigravity-ide\scratch\sunday-bulletin\.env"
$cookieVal = ""

if (Test-Path $envPath) {
    Get-Content $envPath | ForEach-Object {
        if ($_ -match 'HYANGLIN_COOKIE=(.+)') { $cookieVal = $matches[1].Trim() }
    }
}

$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession

if ($cookieVal) {
    $cookie = New-Object System.Net.Cookie
    $cookie.Name = "PHPSESSID"
    $cookie.Value = $cookieVal
    $cookie.Domain = "www.hyanglin.org"
    $session.Cookies.Add($cookie)
}

# 1. 당회 목록 접속
$danghoeUrl = "https://www.hyanglin.org/index.php?mid=b_church&category=645"
$listRes = Invoke-WebRequest -Uri $danghoeUrl -WebSession $session -UserAgent "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

if ($listRes.Content -match "권한이 없습니다") {
    Write-Error "로그인 세션이 만료되었거나 권한이 없습니다. .env의 HYANGLIN_COOKIE를 확인하세요."
    exit 1
}

# 최신 당회록 문서 번호 찾기 (title 영역의 document_srl)
$titleRegex = [regex]'<td class="title">\s*<a[^>]+document_srl=(\d+)'
$match = $titleRegex.Match($listRes.Content)
if (-not $match.Success) {
    Write-Error "당회록 최신 글을 찾을 수 없습니다."
    exit 1
}

$docSrl = $match.Groups[1].Value
$viewUrl = "https://www.hyanglin.org/index.php?mid=b_church&category=645&document_srl=$docSrl"
$viewRes = Invoke-WebRequest -Uri $viewUrl -WebSession $session -UserAgent "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

# 2. 목회 계획 행 추출
$rows = [regex]::Matches($viewRes.Content, '<tr>([\s\S]*?)</tr>')
$plans = @()

foreach ($row in $rows) {
    $cells = [regex]::Matches($row.Groups[1].Value, '<td[^>]*>([\s\S]*?)</td>')
    $cellTexts = @()
    foreach ($c in $cells) {
        $t = ($c.Groups[1].Value -replace '<[^>]+>', ' ' -replace '&nbsp;', ' ' -replace '\s+', ' ').Trim()
        $cellTexts += $t
    }
    if ($cellTexts.Count -ge 3 -and ($cellTexts[1] -match '^\d+$' -or $cellTexts[2] -match '주일')) {
        $plans += [PSCustomObject]@{
            Month  = $cellTexts[0]
            Day    = $cellTexts[1]
            Season = $cellTexts[2]
            Events = $cellTexts[3]
            Notes  = if ($cellTexts.Count -gt 4) { $cellTexts[4] } else { "" }
        }
    }
}

Write-Host "`n=== [향린교회 최신 목회 계획표] ===" -ForegroundColor Cyan
$plans | Format-Table -AutoSize
