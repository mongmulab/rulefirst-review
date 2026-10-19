'use strict';
// VS Code API 에 기대지 않는 순수 로직. node --test 로 시험한다.

const SEVERITY_KO = { critical: '치명', high: '높음', medium: '중간', low: '낮음' };
const PERSPECTIVE_KO = {
  security: '보안', ux: 'UX', test: '테스트', structure: '구조', e2e: 'E2E', performance: '성능',
};
const ORDER = ['critical', 'high', 'medium', 'low'];

function level(sev) {
  if (sev === 'critical' || sev === 'high') return 'error';
  if (sev === 'medium') return 'warning';
  return 'information';
}

/** 리포트 JSON 을 파일별 진단 명세로 바꾼다. 줄 번호는 0부터. */
function toDiagnosticSpecs(report) {
  const byFile = new Map();
  for (const f of (report && report.findings) || []) {
    const sev = SEVERITY_KO[f.severity] || f.severity;
    const per = PERSPECTIVE_KO[f.perspective] || f.perspective;
    const spec = {
      line: Math.max(0, (Number(f.line) || 1) - 1),
      message: `[${sev}·${per}] ${f.title}${f.advice ? ' — ' + f.advice : ''}`,
      level: level(f.severity),
      code: f.rule_id,
      origin: f.source === 'llm' ? 'RuleFirst(모델)' : 'RuleFirst',
    };
    if (!byFile.has(f.file)) byFile.set(f.file, []);
    byFile.get(f.file).push(spec);
  }
  return byFile;
}

function summary(report) {
  const counts = (report && report.counts) || {};
  const parts = ORDER.map((s) => `${SEVERITY_KO[s]} ${counts[s] || 0}`);
  const head = report && report.blocked ? '배포 보류' : '통과';
  return `${head} · ${parts.join(' · ')} · 대상 ${(report && report.file_count) || 0}개 파일`;
}

/** 엔진 명령줄 인자를 만든다. */
function buildArgs(o) {
  const args = ['-m', 'rulefirst', 'review', '--repo', o.repo, '--json-out', o.jsonOut, '--md-out', o.mdOut, '--quiet'];
  if (o.files && o.files.length) args.push('--files', ...o.files);
  else args.push('--base', o.base || 'HEAD');
  if (o.failOn) args.push('--fail-on', o.failOn);
  if (o.llmEndpoint) args.push('--llm-endpoint', o.llmEndpoint);
  if (o.llmEndpoint && o.llmModel) args.push('--llm-model', o.llmModel);
  if (o.config) args.push('--config', o.config);
  return args;
}

function timestamp(d = new Date()) {
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}

module.exports = { toDiagnosticSpecs, summary, buildArgs, level, timestamp, SEVERITY_KO };
