// Optional, paid model sample. Only public SOUL and fictional fixtures leave this machine.
import { readFile, writeFile, mkdir, chmod } from 'node:fs/promises';
import { execFileSync, spawnSync } from 'node:child_process';
import { randomUUID, createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { createModelSettings } from '../ui/server/models.mjs';

const root = fileURLToPath(new URL('../', import.meta.url));
const interactive = process.argv[4] === '--interactive';
if (process.argv[2] !== '--live' || !(process.argv.length === 4 || process.argv.length === 5 && interactive)) {
  console.error('Usage: node scripts/probe_conversation_play.mjs --live <local-baseline-commit> [--interactive]\nUses the configured paid API and the real background allowance; saves private results in .setup/.');
  process.exit(2);
}
const base = execFileSync('git', ['rev-parse', '--verify', '--end-of-options', process.argv[3] + '^{commit}'], { cwd: root, encoding: 'utf8' }).trim();
const before = execFileSync('git', ['show', base + ':config/SOUL.md'], { cwd: root, encoding: 'utf8' });
let after = await readFile(new URL('../config/SOUL.md', import.meta.url), 'utf8');
const fixtureText = await readFile(new URL('../tests/fixtures/' + (interactive ? 'conversation_dialogues.json' : 'conversation_play.json'), import.meta.url), 'utf8');
const fixture = JSON.parse(fixtureText);
if (interactive) {
  // Keep experimental prompt text out of the installed persona and normal fixed replay.
  const start = after.indexOf('<!-- FISH_CONVERSATION_BEGIN -->');
  const end = after.indexOf('<!-- FISH_CONVERSATION_END -->');
  const anchor = fixture.candidate?.anchor, paragraph = fixture.candidate?.paragraph;
  if (typeof anchor !== 'string' || !anchor || typeof paragraph !== 'string' || !paragraph.trim() || start < 0 || end <= start) throw Error('Candidate guide boundaries unavailable.');
  const position = after.indexOf(anchor, start);
  const duplicate = after.indexOf(anchor, position + anchor.length);
  if (position < start || position >= end || duplicate >= 0 && duplicate < end) throw Error('Candidate anchor must occur once inside the public conversation guide.');
  after = after.slice(0, position) + paragraph + '\n\n' + after.slice(position);
}
// Use the actual provider instruction and local prefetch on synthetic episodes.
// No private SOUL, existing memory database, user profile or real session is read.
const pluginBefore = execFileSync('git', ['show', base + ':plugins/fish-episodes/__init__.py'], { cwd: root, encoding: 'utf8' });
const pluginAfter = await readFile(new URL('../plugins/fish-episodes/__init__.py', import.meta.url), 'utf8');
function localContext(cases, plugins = {}) {
  return JSON.parse(execFileSync('python3', ['-c', `import ast,json,sys,tempfile
from pathlib import Path
from datetime import datetime,timedelta,timezone
sys.path.insert(0,str(Path.cwd()/'scripts'))
from fish_journal import Journal,tokens
from fish_conversation import context
d=json.load(sys.stdin)
def instruction(source):
 tree=ast.parse(source)
 method=next(n for n in ast.walk(tree)if isinstance(n,ast.FunctionDef)and n.name=='system_prompt_block')
 return ast.literal_eval(method.body[0].value)
out={'provider':{k:instruction(v)for k,v in d['plugins'].items()},'hints':{}}
with tempfile.TemporaryDirectory()as temporary:
 root=Path(temporary);now=datetime.now(timezone.utc)
 with Journal(root,now=now)as journal:
  for scenario in d['cases']:
   history=scenario['history']
   for i in range(0,len(history),2):
    journal.capture(scenario['id'],history[i][1],history[i+1][1],recorded_at=(now-timedelta(minutes=len(history)-i)).isoformat())
   out['hints'][scenario['id']]=context(root,scenario['user'],journal=journal,session_id=scenario['id'],tokenize=tokens,now=now)
print(json.dumps(out,ensure_ascii=False))`], { cwd: root, input: JSON.stringify({ plugins, cases }), encoding: 'utf8' }));
}
const local = localContext(interactive ? [] : fixture.cases, { before: pluginBefore, after: pluginAfter });
const connection = await createModelSettings(root).balanceConnection();
if (!connection?.key) throw Error('Configured model connection unavailable.');
const settings = { model: connection.model, max_tokens: 640, temperature: 0.7, stream: false };
const directory = new URL('../.setup/', import.meta.url);
await mkdir(directory, { recursive: true });
const output = new URL((interactive ? 'conversation-dialogues-' : 'conversation-play-') + new Date().toISOString().replace(/[:.]/g, '-') + '.json', directory);
const textOnly = '此回放只提供文字对话，没有可执行工具。请直接续写下一条聊天文字，不输出工具调用、工具标记或表情包命令，不声称执行了未执行的动作。';
const hash = value => createHash('sha256').update(value).digest('hex');
const report = { baseline: base, model: connection.model, settings, scope: fixture.scope, textOnly,
  comparison: interactive ? 'baseline versus experimental candidate; not an installed persona change' : 'baseline versus public working tree',
  candidateParagraph: interactive ? fixture.candidate.paragraph : undefined,
  hashes: { fixture: hash(fixtureText), beforeSoul: hash(before), afterSoul: hash(after), beforeProvider: hash(pluginBefore), afterProvider: hash(pluginAfter) }, records: [] };

function ledger(data) {
  const result = spawnSync('python3', ['-c', `import sys,json;from pathlib import Path;sys.path.insert(0,str(Path.cwd()/'scripts'));from fish_budget import Budget
d=json.load(sys.stdin)
with Budget(Path.cwd())as b:
 r=b.reserve(d['id'],d['estimate'],source='background',task='aux:play_probe',model=d['model'])if d['action']=='reserve'else b.settle(d['id'],d.get('usage'),error=d.get('error',False))
 print(json.dumps(r))`], { cwd: root, input: JSON.stringify(data), encoding: 'utf8' });
  if (result.status) throw Error('Background allowance unavailable.');
  return JSON.parse(result.stdout);
}
function usageOf(raw) {
  if (!Number.isInteger(raw?.prompt_tokens) || !Number.isInteger(raw?.completion_tokens)) return null;
  const cached = raw.prompt_cache_hit_tokens ?? raw.prompt_tokens_details?.cached_tokens ?? 0;
  const written = raw.prompt_tokens_details?.cache_write_tokens ?? 0;
  if (![cached, written, raw.prompt_tokens, raw.completion_tokens].every(n => Number.isInteger(n) && n >= 0) || cached + written > raw.prompt_tokens) return null;
  return { input_tokens: raw.prompt_tokens - cached - written, cache_read_tokens: cached, cache_write_tokens: written, output_tokens: raw.completion_tokens };
}
async function save() { await writeFile(output, JSON.stringify(report, null, 2), { mode: 0o600 }); await chmod(output, 0o600); }

await save();
outer: for (const scenario of fixture.cases) {
  // Alternate request order to reduce a systematic before-first ordering effect.
  const variants = fixture.cases.indexOf(scenario) % 2 ? ['after', 'before'] : ['before', 'after'];
  for (const variant of variants) {
   const history = scenario.history.map(([role, content]) => ({ role, content }));
   const users = interactive ? scenario.users : [scenario.user];
   for (const [index, user] of users.entries()) {
    const hint = interactive ? localContext([{ id: scenario.id, history: history.map(({role, content}) => [role, content]), user }]).hints[scenario.id] : local.hints[scenario.id];
    const body = { ...settings, messages: [{ role: 'system', content: (variant === 'before' ? before : after) + '\n' + local.provider[variant] + '\n' + textOnly },
      ...history, { role: 'user', content: user }] };
    if (hint) body.messages[0].content += '\n' + hint;
    const id = 'play-probe-' + randomUUID();
    const permit = ledger({ action: 'reserve', id, estimate: Buffer.byteLength(JSON.stringify(body)) + settings.max_tokens, model: connection.model });
    if (!permit.allowed) { report.records.push({ id: scenario.id, variant, turn: index + 1, skipped: 'background allowance' }); await save(); break outer; }
    let usage = null, record;
    try {
      const response = await fetch(connection.base_url + '/chat/completions', { method: 'POST', headers: { Authorization: 'Bearer ' + connection.key, 'Content-Type': 'application/json' }, body: JSON.stringify(body), redirect: 'error', signal: AbortSignal.timeout(45000) });
      if (!response.ok) { await response.body?.cancel(); throw Error('Provider HTTP ' + response.status); }
      const value = await response.json(); usage = usageOf(value.usage);
      const text = value.choices?.[0]?.message?.content || '';
      record = { id: scenario.id, variant, turn: index + 1, user, text, finish: value.choices?.[0]?.finish_reason, usage, toolArtifact: /DSML|<tool_call|<function_call/.test(text) };
    } catch (error) {
      record = { id: scenario.id, variant, turn: index + 1, user, error: /^Provider HTTP \d+$/.test(error.message) ? error.message : 'Model sample unavailable' };
    }
    // A failed or missing usage report is charged conservatively by Budget.
    ledger({ action: 'settle', id, usage, error: Boolean(record.error) });
    report.records.push(record); await save();
    console.log(JSON.stringify({ id: record.id, variant, turn: record.turn, text: record.text, finish: record.finish, error: record.error }));
    // A broken response must not become a made-up successful turn in the next request.
    if (record.error || record.toolArtifact || record.finish !== 'stop' || !record.text?.trim()) break;
    history.push({ role: 'user', content: user }, { role: 'assistant', content: record.text });
   }
  }
}
console.log('Saved fictional model samples in .setup/; evaluate manually against fixture rubrics.');
