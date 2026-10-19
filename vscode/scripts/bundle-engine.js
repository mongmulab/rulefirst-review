'use strict';
// 저장소의 엔진·규칙·체크리스트를 확장 폴더(engine/)로 복사한다. vsce package 전에 실행.
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..', '..');
const dest = path.resolve(__dirname, '..', 'engine');

function copyDir(src, dst) {
  fs.mkdirSync(dst, { recursive: true });
  for (const e of fs.readdirSync(src, { withFileTypes: true })) {
    if (e.name === '__pycache__' || e.name.endsWith('.pyc')) continue;
    const s = path.join(src, e.name);
    const d = path.join(dst, e.name);
    if (e.isDirectory()) copyDir(s, d);
    else fs.copyFileSync(s, d);
  }
}

fs.rmSync(dest, { recursive: true, force: true });
copyDir(path.join(root, 'core', 'rulefirst'), path.join(dest, 'rulefirst'));
copyDir(path.join(root, 'rules'), path.join(dest, 'rules'));
copyDir(path.join(root, 'checklists'), path.join(dest, 'checklists'));
fs.copyFileSync(path.join(root, 'LICENSE'), path.resolve(__dirname, '..', 'LICENSE'));
console.log(`engine bundled -> ${dest}`);
