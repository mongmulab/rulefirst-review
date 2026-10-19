'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { toDiagnosticSpecs, summary, buildArgs, level } = require('../lib/findings');

const report = {
  blocked: true,
  file_count: 2,
  counts: { critical: 1, low: 1 },
  findings: [
    { file: 'conf/app.yml', line: 3, severity: 'critical', perspective: 'security', rule_id: 'SEC-001', title: '평문 비밀번호', advice: '환경변수로', source: 'rule' },
    { file: 'conf/app.yml', line: 0, severity: 'low', perspective: 'ux', rule_id: 'UX-004', title: 'console.log', advice: '', source: 'rule' },
    { file: 'web/A.java', line: 12, severity: 'high', perspective: 'security', rule_id: 'LLM-S1', title: '권한 확인 없음', advice: '', source: 'llm' },
  ],
};

test('파일별로 묶고 줄 번호를 0부터로 바꾼다', () => {
  const m = toDiagnosticSpecs(report);
  assert.deepStrictEqual([...m.keys()], ['conf/app.yml', 'web/A.java']);
  const [a, b] = m.get('conf/app.yml');
  assert.strictEqual(a.line, 2);
  assert.strictEqual(b.line, 0); // 0 이하 줄은 첫 줄로
  assert.strictEqual(a.level, 'error');
  assert.match(a.message, /^\[치명·보안\] 평문 비밀번호 — 환경변수로$/);
  assert.strictEqual(m.get('web/A.java')[0].origin, 'RuleFirst(모델)');
});

test('빈 리포트도 안전하다', () => {
  assert.strictEqual(toDiagnosticSpecs({}).size, 0);
  assert.match(summary({}), /^통과 · 치명 0/);
});

test('요약 문구', () => {
  assert.strictEqual(summary(report), '배포 보류 · 치명 1 · 높음 0 · 중간 0 · 낮음 1 · 대상 2개 파일');
});

test('인자: 변경분 모드와 파일 모드', () => {
  const common = { repo: 'R', jsonOut: 'j', mdOut: 'm' };
  const a = buildArgs({ ...common, base: 'origin/main', failOn: 'medium' });
  assert.deepStrictEqual(a.slice(-4), ['--base', 'origin/main', '--fail-on', 'medium']);
  const b = buildArgs({ ...common, files: ['x/A.java'], base: 'HEAD' });
  assert.ok(b.includes('--files') && !b.includes('--base'));
});

test('모델 이름은 엔드포인트가 있을 때만 넘긴다', () => {
  const common = { repo: 'R', jsonOut: 'j', mdOut: 'm' };
  assert.ok(!buildArgs({ ...common, llmModel: 'tiny' }).includes('--llm-model'));
  const on = buildArgs({ ...common, llmEndpoint: 'http://127.0.0.1:8080/v1', llmModel: 'tiny' });
  assert.ok(on.includes('--llm-endpoint') && on.includes('--llm-model'));
});

test('등급 매핑', () => {
  assert.strictEqual(level('high'), 'error');
  assert.strictEqual(level('medium'), 'warning');
  assert.strictEqual(level('low'), 'information');
});
