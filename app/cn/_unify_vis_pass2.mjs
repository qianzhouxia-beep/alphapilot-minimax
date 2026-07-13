// AlphaPilot visual unification - PASS 2 (remaining edge cases)
// Run after pass 1
import { readFileSync, writeFileSync } from 'fs';

function processFile(path, label) {
  console.log(`=== ${label} ===`);
  let c = readFileSync(path, 'utf8');
  const orig = c;
  const count = {};

  function doReplace(oldStr, newStr, note) {
    const before = c;
    let split = c.split(oldStr);
    if (split.length > 1) {
      const n = split.length - 1;
      c = split.join(newStr);
      count[note] = (count[note] || 0) + n;
    }
  }

  // spinner border-t
  doReplace('border-t-[#4DA3FF]', 'border-t-status-info', 'spinner-border-t');

  // small colored dots (bg-[#3EE6A8], bg-[#9FB0C7], bg-[#F5C451])
  doReplace('bg-[#3EE6A8]', 'bg-status-success', 'dot-green');
  doReplace('bg-[#9FB0C7]', 'bg-text-secondary', 'dot-gray');
  doReplace('bg-[#F5C451]', 'bg-status-warning', 'dot-yellow');

  // text on gradient button (dark navy)
  doReplace('text-[#0a1422]', 'text-background', 'text-on-gradient');

  // button hover lighter blue
  doReplace('hover:bg-[#7ddeff]', 'hover:bg-status-info/70', 'hover-bg-lighter');

  // hover text warning
  doReplace('hover:text-[#FFB74D]', 'hover:text-status-warning/80', 'hover-text-warning');

  const keys = Object.keys(count);
  if (keys.length === 0) {
    console.log('  No changes');
  } else {
    let total = 0;
    for (const k of keys.sort()) {
      console.log(`  ${count[k]}x  ${k}`);
      total += count[k];
    }
    console.log(`  ---- Pass 2 total: ${total} replacements ----`);
  }

  if (c !== orig) {
    writeFileSync(path, c, 'utf8');
    console.log('  Written');
  } else {
    console.log('  No write needed');
  }
  return 0;
}

processFile('D:/AI/alphapilot/部署文件/frontend/app/cn/watchlist/page.tsx', '1/3 watchlist/page.tsx');
processFile('D:/AI/alphapilot/部署文件/frontend/app/cn/chat/page.tsx', '2/3 chat/page.tsx');
processFile('D:/AI/alphapilot/部署文件/frontend/app/cn/paper-trading/page.tsx', '3/3 paper-trading/page.tsx');
