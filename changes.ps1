# PowerShell script to apply visual optimizations
# All files are UTF-8 with BOM

$HeaderBarPath = "D:\AI\alphapilot\部署文件\frontend\components\HeaderBar.tsx"
$PagePath = "D:\AI\alphapilot\部署文件\frontend\app\cn\page.tsx"

Write-Host "=== 1) HeaderBar.tsx: Replace ⭐ emoji with SVG star icon ==="

$hb = Get-Content $HeaderBarPath -Raw

# Replace ⭐ emoji with SVG star (full fill star, same as used in watchlist link)
$oldStar = '<span style={{ fontSize: 14 }}>⭐</span>'
$newStar = '<svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>'
$hb = $hb.Replace($oldStar, $newStar)
Write-Host "  - Replaced ⭐ emoji with SVG star"

# Adjust nav border to be more subtle
$oldBorder = 'rounded-lg border border-[#1D2A42] bg-[#0C1728] p-0.5'
$newBorder = 'rounded-lg border border-[#1D2A42]/50 bg-[#0C1728] p-0.5'
$hb = $hb.Replace($oldBorder, $newBorder)
Write-Host "  - Made nav border more subtle (50% opacity)"

Set-Content $HeaderBarPath -Value $hb -Encoding UTF8
Write-Host "  -> HeaderBar.tsx saved"

Write-Host ""
Write-Host "=== 2) page.tsx: Sniper card class + simplify text sizes ==="

$page = Get-Content $PagePath -Raw

# 2a) Change the outer div from verbose inline classes to sniper-card
$oldSniperRow = 'rounded-lg bg-[#121c2a] p-2.5 hover:bg-[#16202f] transition-colors'
$newSniperRow = 'sniper-card'
$page = $page.Replace($oldSniperRow, $newSniperRow)
Write-Host "  - Changed sniper outer div to sniper-card class"

# 2b) Simplify inner text sizes: remove redundant text-[13px] from grid cells inside sniper cards
# The stock name link: text-[14px] -> text-[13px] (simplify)
$oldNameLink = 'text-[14px] font-medium text-[#EAF2FF] hover:text-[#A78BFA] truncate'
$newNameLink = 'text-[13px] font-medium text-[#EAF2FF] hover:text-[#A78BFA] truncate'
$page = $page.Replace($oldNameLink, $newNameLink)
Write-Host "  - Simplified stock name font size 14px -> 13px"

Set-Content $PagePath -Value $page -Encoding UTF8
Write-Host "  -> page.tsx saved"

Write-Host ""
Write-Host "=== 3) Verify changes ==="

# Quick check
$hbCheck = Get-Content $HeaderBarPath -Raw
if ($hbCheck.Contains("sniper-card") -or $hbCheck.Contains("phase-grid")) { 
    # Just check file is valid
}
if ($hbCheck.Contains('<polygon points="12 2')) {
    Write-Host "  ✓ HeaderBar: SVG star found"
} else {
    Write-Host "  ✗ HeaderBar: SVG star NOT found!"
}

$pageCheck = Get-Content $PagePath -Raw
if ($pageCheck.Contains('className="sniper-card"')) {
    Write-Host "  ✓ page.tsx: sniper-card class found"
} else {
    Write-Host "  ✗ page.tsx: sniper-card class NOT found!"
}

if ($pageCheck.Contains('text-[13px] font-medium text-[#EAF2FF] hover:text-[#A78BFA]')) {
    Write-Host "  ✓ page.tsx: Simplified text sizes found"
} else {
    Write-Host "  ✗ page.tsx: Simplified text sizes NOT found!"
}

Write-Host ""
Write-Host "=== All changes applied ==="
