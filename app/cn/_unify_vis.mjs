// AlphaPilot page visual unification - Node.js script
// Replaces inline colors with Tailwind CSS v4 variables
// Usage: node _unify_vis.mjs
import { readFileSync, writeFileSync } from 'fs';

function processFile(path, label) {
  console.log(`=== ${label} ===`);
  let c = readFileSync(path, 'utf8');
  const orig = c;
  const count = {};

  function doReplace(oldStr, newStr, note) {
    const before = c;
    // Must be a literal string match (not regex) so split+join is safe
    let split = c.split(oldStr);
    if (split.length > 1) {
      const n = split.length - 1;
      c = split.join(newStr);
      count[note] = (count[note] || 0) + n;
    }
  }

  // Phase 1: Specific structural additions
  // chat: assistant bubble (user.message wrapper)
  doReplace(
    'rounded-2xl px-4 py-3 text-[13px] leading-relaxed bg-[#0C1728] border border-[#1D2A42] text-[#EAF2FF]',
    'rounded-2xl px-4 py-3 text-[13px] leading-relaxed bg-surface-card card-lift border border-border-subtle text-text-primary',
    'chat-assistant-bubble'
  );
  // chat: loading dots bubble
  doReplace(
    'rounded-2xl px-4 py-3 bg-[#0C1728] border border-[#1D2A42]',
    'rounded-2xl px-4 py-3 bg-surface-card card-lift border border-border-subtle',
    'chat-loading-bubble'
  );
  // add data-table class to tables
  doReplace(
    '<table className="w-full text-left">',
    '<table className="w-full text-left data-table">',
    'data-table'
  );
  // tag-badge on trade action labels
  doReplace(
    'span className={`text-[11px] px-2 py-0.5 rounded-full ${',
    'span className={`text-[11px] px-2 py-0.5 rounded-full tag-badge ${',
    'tag-badge-trade-action'
  );
  // tag-badge on strategy status labels
  doReplace(
    'span className={`text-[10px] px-2 py-0.5 rounded-full ${',
    'span className={`text-[10px] px-2 py-0.5 rounded-full tag-badge ${',
    'tag-badge-strategy-status'
  );
  // tag-badge on Beta label
  doReplace(
    'className="text-[10px] px-2 py-0.5 rounded-full bg-[#4DA3FF]/10 text-[#4DA3FF] border border-[#4DA3FF]/30">Beta',
    'className="text-[10px] px-2 py-0.5 rounded-full tag-badge bg-[#4DA3FF]/10 text-[#4DA3FF] border border-[#4DA3FF]/30">Beta',
    'tag-badge-beta'
  );
  // tag-badge on strategy active status (non-template literal version)
  doReplace(
    'text-[10px] px-2 py-0.5 rounded-full bg-[rgba(62,230,168,0.15)] text-[#3EE6A8]',
    'text-[10px] px-2 py-0.5 rounded-full tag-badge bg-[rgba(62,230,168,0.15)] text-[#3EE6A8]',
    'tag-badge-active'
  );
  doReplace(
    'text-[10px] px-2 py-0.5 rounded-full bg-[#6E7C93]/20 text-[#6E7C93]',
    'text-[10px] px-2 py-0.5 rounded-full tag-badge bg-[#6E7C93]/20 text-[#6E7C93]',
    'tag-badge-stopped'
  );

  // Phase 2: Color variables (longer patterns first)
  // focus/hover/placeholder variants
  doReplace('focus:border-[#4DA3FF]', 'focus:border-status-info', 'focus-border-info');
  doReplace('hover:border-[#4DA3FF]/50', 'hover:border-status-info/50', 'hover-border-info-50');
  doReplace('hover:border-[#4DA3FF]', 'hover:border-status-info', 'hover-border-info');
  doReplace('hover:border-[#1D2A42]', 'hover:border-border-subtle', 'hover-border-subtle');
  doReplace('hover:bg-[#16202f]', 'hover:bg-surface-container', 'hover-bg-container');
  doReplace('hover:shadow-[#4DA3FF]/50', 'hover:shadow-status-info/50', 'hover-shadow-info');
  doReplace('placeholder:text-[#6E7C93]', 'placeholder:text-text-disabled', 'placeholder-disabled');

  // border with opacity
  doReplace('border-[#4DA3FF]/30', 'border-status-info/30', 'border-info-30');
  doReplace('border-[#4DA3FF]/20', 'border-status-info/20', 'border-info-20');
  doReplace('border-[#1D2A42]/50', 'border-border-subtle/50', 'border-subtle-50');
  doReplace('border-[#1D2A42]/30', 'border-border-subtle/30', 'border-subtle-30');

  // bg with opacity
  doReplace('bg-[#6E7C93]/20', 'bg-text-disabled/20', 'bg-disabled-20');
  doReplace('bg-[#4DA3FF]/10', 'bg-status-info/10', 'bg-info-10');

  // solid border
  doReplace('border-[#1D2A42]', 'border-border-subtle', 'border-subtle');
  doReplace('border-[#4DA3FF]', 'border-status-info', 'border-info');
  doReplace('border-[#FF5D5D]', 'border-status-danger', 'border-danger');

  // border-t / border-b
  doReplace('border-t border-[#1D2A42]', 'border-t border-border-subtle', 'border-t-subtle');
  // border-b variants - longest first
  doReplace('border-b border-[#1D2A42]/50', 'border-b border-border-subtle/50', 'border-b-subtle-50');
  doReplace('border-b border-[#1D2A42]/30', 'border-b border-border-subtle/30', 'border-b-subtle-30');
  doReplace('border-b border-[#1D2A42]', 'border-b border-border-subtle', 'border-b-subtle');

  // text colors
  doReplace('text-[#EAF2FF]', 'text-text-primary', 'text-primary');
  doReplace('text-[#9FB0C7]', 'text-text-secondary', 'text-secondary');
  doReplace('text-[#6E7C93]', 'text-text-disabled', 'text-disabled');
  doReplace('text-[#3EE6A8]', 'text-status-success', 'text-success');
  doReplace('text-[#F5C451]', 'text-status-warning', 'text-warning');
  doReplace('text-[#FF5D5D]', 'text-status-danger', 'text-danger');
  doReplace('text-[#4DA3FF]', 'text-status-info', 'text-info');

  // bg colors
  doReplace('bg-[#0a1422]', 'bg-background', 'bg-background');
  doReplace('bg-[#121c2a]', 'bg-surface-container-low', 'bg-container-low');
  doReplace('bg-[#16202f]', 'bg-surface-container', 'bg-container');
  doReplace('bg-[#0C1728]', 'bg-surface-panel', 'bg-panel');
  doReplace('bg-[#101C30]', 'bg-surface-card', 'bg-card');
  doReplace('bg-[#4DA3FF]', 'bg-status-info', 'bg-info');

  // gradient
  doReplace('from-[#4DA3FF]', 'from-status-info', 'from-info');

  // to-
  doReplace('to-[#35e0a3]', 'to-status-success', 'to-success');
  doReplace('to-[#7ddeff]', 'to-status-info/60', 'to-info');

  // Report
  const keys = Object.keys(count);
  if (keys.length === 0) {
    console.log('  No changes');
  } else {
    let total = 0;
    for (const k of keys.sort()) {
      console.log(`  ${count[k]}x  ${k}`);
      total += count[k];
    }
    console.log(`  ---- Total: ${total} replacements ----`);
  }

  if (c !== orig) {
    writeFileSync(path, c, 'utf8');
    console.log('  Written');
  } else {
    console.log('  No write needed');
  }
  console.log('');

  const sum = keys.reduce((a, k) => a + count[k], 0);
  return sum;
}

let total = 0;
total += processFile('D:/AI/alphapilot/部署文件/frontend/app/cn/watchlist/page.tsx', '1/3 watchlist/page.tsx');
total += processFile('D:/AI/alphapilot/部署文件/frontend/app/cn/chat/page.tsx', '2/3 chat/page.tsx');
total += processFile('D:/AI/alphapilot/部署文件/frontend/app/cn/paper-trading/page.tsx', '3/3 paper-trading/page.tsx');

console.log(`========== DONE! Total: ${total} replacements ==========`);
