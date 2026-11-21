import {execFileSync} from 'node:child_process';
import {existsSync, mkdirSync} from 'node:fs';
const revision = '838ea330296148621f7a23f7cb647b11e73b5184';
const target = '.deps/OpenIndustries';
mkdirSync('.deps', {recursive:true});
if (!existsSync(`${target}/.git`)) {
  execFileSync('git', ['clone', '--filter=blob:none', '--no-checkout', 'https://github.com/Mapped-Assembly/OpenIndustries.git', target], {stdio:'inherit'});
  execFileSync('git', ['-C', target, 'checkout', revision], {stdio:'inherit'});
}
const actual = execFileSync('git', ['-C', target, 'rev-parse', 'HEAD'], {encoding:'utf8'}).trim();
if (actual !== revision) throw new Error(`OpenIndustries revision mismatch: expected ${revision}, got ${actual}`);
console.log(`OpenIndustries renderer pinned at ${revision}`);
