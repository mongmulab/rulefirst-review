'use strict';
const vscode = require('vscode');
const cp = require('child_process');
const fs = require('fs');
const path = require('path');
const { toDiagnosticSpecs, summary, buildArgs, timestamp } = require('./lib/findings');

let diagnostics;
let output;
let status;
let lastReport = null; // { md, json }
let running = null;

function cfg() {
  return vscode.workspace.getConfiguration('rulefirst');
}

function enginePath(ctx) {
  const set = cfg().get('enginePath');
  if (set) return set;
  const bundled = path.join(ctx.extensionPath, 'engine');
  if (fs.existsSync(path.join(bundled, 'rulefirst'))) return bundled;
  return path.join(ctx.extensionPath, '..', 'core'); // 저장소에서 바로 실행할 때
}

function targetFolder() {
  const ed = vscode.window.activeTextEditor;
  if (ed) {
    const f = vscode.workspace.getWorkspaceFolder(ed.document.uri);
    if (f) return f;
  }
  return (vscode.workspace.workspaceFolders || [])[0];
}

function reportDir(ctx) {
  const set = cfg().get('reportDir');
  const dir = set || path.join(ctx.globalStorageUri.fsPath, 'reports');
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

function levelOf(l) {
  if (l === 'error') return vscode.DiagnosticSeverity.Error;
  if (l === 'warning') return vscode.DiagnosticSeverity.Warning;
  return vscode.DiagnosticSeverity.Information;
}

function apply(folder, report) {
  diagnostics.clear();
  for (const [rel, specs] of toDiagnosticSpecs(report)) {
    const uri = vscode.Uri.joinPath(folder.uri, ...rel.split('/'));
    diagnostics.set(uri, specs.map((s) => {
      const d = new vscode.Diagnostic(new vscode.Range(s.line, 0, s.line, Number.MAX_SAFE_INTEGER), s.message, levelOf(s.level));
      d.source = s.origin;
      d.code = s.code;
      return d;
    }));
  }
}

async function review(ctx, files) {
  if (running) {
    vscode.window.showInformationMessage('RuleFirst 리뷰가 이미 실행 중입니다.');
    return;
  }
  const folder = targetFolder();
  if (!folder) {
    vscode.window.showWarningMessage('열린 작업 폴더가 없습니다.');
    return;
  }
  const dir = reportDir(ctx);
  const stamp = timestamp();
  const base = `${stamp}_${path.basename(folder.uri.fsPath)}`;
  const jsonOut = path.join(dir, `${base}.json`);
  const mdOut = path.join(dir, `${base}.md`);
  const c = cfg();
  const args = buildArgs({
    repo: folder.uri.fsPath, jsonOut, mdOut, files,
    base: c.get('base'), failOn: c.get('failOn'),
    llmEndpoint: c.get('llm.endpoint'), llmModel: c.get('llm.model'),
  });
  const python = c.get('pythonPath') || 'python';
  const env = {
    ...process.env,
    PYTHONPATH: [enginePath(ctx), process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
    PYTHONIOENCODING: 'utf-8',
  };

  output.appendLine(`\n$ ${python} ${args.join(' ')}`);
  await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: 'RuleFirst 리뷰', cancellable: true },
    (progress, token) => new Promise((resolve) => {
      const child = cp.spawn(python, args, { cwd: folder.uri.fsPath, env, windowsHide: true });
      running = child;
      let tail = '';
      token.onCancellationRequested(() => child.kill());
      child.stderr.setEncoding('utf8');
      child.stderr.on('data', (chunk) => {
        output.append(chunk);
        tail = (tail + chunk).slice(-2000);
        const last = chunk.trim().split(/\r?\n/).pop();
        if (last) progress.report({ message: last.replace('[rulefirst] ', '') });
      });
      child.on('error', (e) => {
        running = null;
        vscode.window.showErrorMessage(`Python 을 실행하지 못했습니다 (${python}): ${e.message}. 설정 rulefirst.pythonPath 를 확인하세요.`);
        resolve();
      });
      child.on('close', (code) => {
        running = null;
        if (token.isCancellationRequested) {
          vscode.window.showInformationMessage('RuleFirst 리뷰를 취소했습니다.');
          return resolve();
        }
        if (code !== 0 && code !== 1) {
          output.show(true);
          vscode.window.showErrorMessage(`RuleFirst 실행 오류 (종료 코드 ${code}). 출력 창을 확인하세요. ${tail.trim().split(/\r?\n/).pop() || ''}`);
          return resolve();
        }
        let report;
        try {
          report = JSON.parse(fs.readFileSync(jsonOut, 'utf8'));
        } catch (e) {
          vscode.window.showErrorMessage(`리포트를 읽지 못했습니다: ${e.message}`);
          return resolve();
        }
        lastReport = { md: mdOut, json: jsonOut };
        apply(folder, report);
        const text = summary(report);
        status.text = `$(checklist) ${report.blocked ? '보류' : '통과'} ${report.findings.length}`;
        status.tooltip = `RuleFirst: ${text}\n클릭하면 리포트를 엽니다.`;
        status.show();
        const show = report.blocked ? vscode.window.showWarningMessage : vscode.window.showInformationMessage;
        show(`RuleFirst: ${text}`, '리포트 열기', '문제 패널').then((pick) => {
          if (pick === '리포트 열기') openReport();
          if (pick === '문제 패널') vscode.commands.executeCommand('workbench.actions.view.problems');
        });
        resolve();
      });
    }),
  );
}

function openReport() {
  if (!lastReport || !fs.existsSync(lastReport.md)) {
    vscode.window.showInformationMessage('아직 이번 세션에서 만든 리포트가 없습니다.');
    return;
  }
  vscode.commands.executeCommand('markdown.showPreview', vscode.Uri.file(lastReport.md));
}

function activate(ctx) {
  diagnostics = vscode.languages.createDiagnosticCollection('rulefirst');
  output = vscode.window.createOutputChannel('RuleFirst Review');
  status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 50);
  status.command = 'rulefirst.openReport';
  ctx.subscriptions.push(
    diagnostics, output, status,
    vscode.commands.registerCommand('rulefirst.reviewChanges', () => review(ctx)),
    vscode.commands.registerCommand('rulefirst.reviewFile', (uri) => {
      const target = uri || (vscode.window.activeTextEditor && vscode.window.activeTextEditor.document.uri);
      if (!target) return;
      review(ctx, [vscode.workspace.asRelativePath(target, false)]);
    }),
    vscode.commands.registerCommand('rulefirst.openReport', openReport),
    vscode.commands.registerCommand('rulefirst.clear', () => {
      diagnostics.clear();
      status.hide();
    }),
  );
}

function deactivate() {
  if (running) running.kill();
}

module.exports = { activate, deactivate };
