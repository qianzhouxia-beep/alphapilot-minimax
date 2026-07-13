# AlphaPilot visual unification script
# Replaces inline colors with Tailwind CSS variables, adds data-table / tag-badge / card-lift
$ErrorActionPreference = "Stop"

function Process-File($Path, $Label) {
    Write-Host "=== $Label ===" -ForegroundColor Cyan
    $c = [System.IO.File]::ReadAllText($Path)
    $orig = $c
    $count = @{}

    function Do-Replace($old, $new, $note) {
        $before = $c
        $c = $c.Replace($old, $new)
        $n = [regex]::Matches($before, [regex]::Escape($old)).Count
        $m = $n - [regex]::Matches($c, [regex]::Escape($old)).Count
        if ($m -gt 0) {
            $count[$note] = $m
        }
    }

    # Phase 1: Specific patterns (data-table, tag-badge, bubble styles)
    # chat: assistant bubble
    Do-Replace 'rounded-2xl px-4 py-3 text-[13px] leading-relaxed bg-[#0C1728] border border-[#1D2A42] text-[#EAF2FF]' `
              'rounded-2xl px-4 py-3 text-[13px] leading-relaxed bg-surface-card card-lift border border-border-subtle text-text-primary' `
              "chat-assistant-bubble"
    # chat: loading bubble
    Do-Replace 'rounded-2xl px-4 py-3 bg-[#0C1728] border border-[#1D2A42]' `
              'rounded-2xl px-4 py-3 bg-surface-card card-lift border border-border-subtle' `
              "chat-loading-bubble"
    # add data-table to tables
    Do-Replace '<table className="w-full text-left">' `
              '<table className="w-full text-left data-table">' `
              "data-table"
    # tag-badge on trade action
    Do-Replace "span className={`text-[11px] px-2 py-0.5 rounded-full `" `
              "span className={`text-[11px] px-2 py-0.5 rounded-full tag-badge `" `
              "tag-badge-trade-action"
    # tag-badge on strategy status
    Do-Replace "span className={`text-[10px] px-2 py-0.5 rounded-full `" `
              "span className={`text-[10px] px-2 py-0.5 rounded-full tag-badge `" `
              "tag-badge-strategy-status"
    # tag-badge on Beta label
    Do-Replace 'className="text-[10px] px-2 py-0.5 rounded-full bg-[#4DA3FF]/10 text-[#4DA3FF] border border-[#4DA3FF]/30">Beta' `
              'className="text-[10px] px-2 py-0.5 rounded-full tag-badge bg-[#4DA3FF]/10 text-[#4DA3FF] border border-[#4DA3FF]/30">Beta' `
              "tag-badge-beta"
    # tag-badge on strategy status
    Do-Replace 'text-[10px] px-2 py-0.5 rounded-full bg-[rgba(62,230,168,0.15)] text-[#3EE6A8]' `
              'text-[10px] px-2 py-0.5 rounded-full tag-badge bg-[rgba(62,230,168,0.15)] text-[#3EE6A8]' `
              "tag-badge-active"
    Do-Replace 'text-[10px] px-2 py-0.5 rounded-full bg-[#6E7C93]/20 text-[#6E7C93]' `
              'text-[10px] px-2 py-0.5 rounded-full tag-badge bg-[#6E7C93]/20 text-[#6E7C93]' `
              "tag-badge-stopped"

    # Phase 2: Color variables (long patterns first)
    Do-Replace 'focus:border-[#4DA3FF]' 'focus:border-status-info' 'focus-border-status-info'
    Do-Replace 'hover:border-[#4DA3FF]/50' 'hover:border-status-info/50' 'hover-border-status-info-50'
    Do-Replace 'hover:border-[#4DA3FF]' 'hover:border-status-info' 'hover-border-status-info'
    Do-Replace 'hover:border-[#1D2A42]' 'hover:border-border-subtle' 'hover-border-border-subtle'
    Do-Replace 'hover:bg-[#16202f]' 'hover:bg-surface-container' 'hover-bg-surface-container'
    Do-Replace 'hover:shadow-[#4DA3FF]/50' 'hover:shadow-status-info/50' 'hover-shadow-status-info'
    Do-Replace 'placeholder:text-[#6E7C93]' 'placeholder:text-text-disabled' 'placeholder-text-disabled'

    Do-Replace 'border-[#4DA3FF]/30' 'border-status-info/30' 'border-status-info-30'
    Do-Replace 'border-[#4DA3FF]/20' 'border-status-info/20' 'border-status-info-20'
    Do-Replace 'border-[#1D2A42]/50' 'border-border-subtle/50' 'border-border-subtle-50'
    Do-Replace 'border-[#1D2A42]/30' 'border-border-subtle/30' 'border-border-subtle-30'

    Do-Replace 'bg-[#6E7C93]/20' 'bg-text-disabled/20' 'bg-text-disabled-20'
    Do-Replace 'bg-[#4DA3FF]/10' 'bg-status-info/10' 'bg-status-info-10'
    Do-Replace 'bg-[#4DA3FF]' 'bg-status-info' 'bg-status-info'

    Do-Replace 'border-[#1D2A42]' 'border-border-subtle' 'border-border-subtle'
    Do-Replace 'border-[#4DA3FF]' 'border-status-info' 'border-status-info'
    Do-Replace 'border-[#FF5D5D]' 'border-status-danger' 'border-status-danger'

    Do-Replace 'border-t border-[#1D2A42]' 'border-t border-border-subtle' 'border-t-border-subtle'
    Do-Replace 'border-b border-[#1D2A42]' 'border-b border-border-subtle' 'border-b-border-subtle'
    Do-Replace 'border-b border-[#1D2A42]/50' 'border-b border-border-subtle/50' 'border-b-border-subtle-50'
    Do-Replace 'border-b border-[#1D2A42]/30' 'border-b border-border-subtle/30' 'border-b-border-subtle-30'

    Do-Replace 'text-[#EAF2FF]' 'text-text-primary' 'text-text-primary'
    Do-Replace 'text-[#9FB0C7]' 'text-text-secondary' 'text-text-secondary'
    Do-Replace 'text-[#6E7C93]' 'text-text-disabled' 'text-text-disabled'
    Do-Replace 'text-[#3EE6A8]' 'text-status-success' 'text-status-success'
    Do-Replace 'text-[#F5C451]' 'text-status-warning' 'text-status-warning'
    Do-Replace 'text-[#FF5D5D]' 'text-status-danger' 'text-status-danger'
    Do-Replace 'text-[#4DA3FF]' 'text-status-info' 'text-status-info'

    Do-Replace 'bg-[#0a1422]' 'bg-background' 'bg-background'
    Do-Replace 'bg-[#121c2a]' 'bg-surface-container-low' 'bg-surface-container-low'
    Do-Replace 'bg-[#16202f]' 'bg-surface-container' 'bg-surface-container'
    Do-Replace 'bg-[#0C1728]' 'bg-surface-panel' 'bg-surface-panel'
    Do-Replace 'bg-[#101C30]' 'bg-surface-card' 'bg-surface-card'

    Do-Replace 'from-[#4DA3FF]' 'from-status-info' 'from-status-info'

    if ($count.Count -eq 0) {
        Write-Host "  No changes" -ForegroundColor Yellow
    } else {
        $total = ($count.Values | Measure-Object -Sum).Sum
        foreach ($kv in $count.GetEnumerator() | Sort-Object Name) {
            Write-Host "  $($kv.Value)x  $($kv.Key)" -ForegroundColor Green
        }
        Write-Host "  ---- Total: $total replacements ----" -ForegroundColor Cyan
    }

    if ($c -ne $orig) {
        $utf8BOM = New-Object System.Text.UTF8Encoding $true
        [System.IO.File]::WriteAllText($Path, $c, $utf8BOM)
        Write-Host "  Written" -ForegroundColor Green
    } else {
        Write-Host "  No write needed" -ForegroundColor Yellow
    }
    Write-Host ""
    return ($count.Values | Measure-Object -Sum).Sum
}

$total = 0
$total += Process-File "D:\AI\alphapilot\部署文件\frontend\app\cn\watchlist\page.tsx" "1/3 watchlist/page.tsx"
$total += Process-File "D:\AI\alphapilot\部署文件\frontend\app\cn\chat\page.tsx" "2/3 chat/page.tsx"
$total += Process-File "D:\AI\alphapilot\部署文件\frontend\app\cn\paper-trading\page.tsx" "3/3 paper-trading/page.tsx"

Write-Host "========== DONE! Total: $total replacements ==========" -ForegroundColor Magenta
