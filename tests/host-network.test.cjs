const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const root = path.resolve(__dirname, '..');

function config(extra = {}, includeImport = false) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'familieblikk-host-test-'));
  const file = path.join(directory, '.env');
  fs.writeFileSync(file, fs.readFileSync(path.join(root, '.env.example')));
  const keep = /^(PATH|PATHEXT|SYSTEMROOT|WINDIR|USERPROFILE|HOME|APPDATA|LOCALAPPDATA|TEMP|TMP|DOCKER_CONFIG|PROGRAMFILES(?:\(X86\))?|PROGRAMDATA|COMSPEC)$/i;
  const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => keep.test(key)));
  Object.assign(env, {DJANGO_SECRET_KEY:'synthetic-host-test-key', POSTGRES_PASSWORD:'synthetic-owner-only', POSTGRES_APP_PASSWORD:'synthetic-app-only', ...extra});
  if (includeImport && !env.PRIVATE_IMPORT_PATH) env.PRIVATE_IMPORT_PATH = directory;
  const args = ['compose', '--env-file', file, '-f', 'docker-compose.yml'];
  if (includeImport) args.push('-f', 'docker-compose.import.yml');
  try {
    return JSON.parse(execFileSync('docker', [...args, 'config', '--format', 'json'], {cwd:root, env, encoding:'utf8', stdio:['ignore','pipe','pipe']}));
  } finally {
    fs.unlinkSync(file);
    fs.rmdirSync(directory);
  }
}

test('host-nettverk og fast webport 6451 er standard for hele hostingprosjektet', () => {
  const c = config({APP_PORT:'4180', APP_BIND:'127.0.0.1', POSTGRES_HOST:'db'});
  assert.equal(c.name, 'familieblikk');
  for (const name of ['db','migrate','app','push-worker']) {
    assert.equal(c.services[name].network_mode, 'host');
    assert.equal(c.services[name].ports, undefined);
    assert.equal(c.services[name].networks, undefined);
  }
  assert.ok(c.services.app.command.includes('0.0.0.0:6451'));
  assert.equal(c.volumes.database.name, 'familieblikk_database');
  assert.ok(c.services.db.volumes.some(v => v.type === 'volume' && v.source === 'database' && v.target === '/var/lib/postgresql/data'));
  assert.equal(c.services.app.depends_on.migrate.condition, 'service_completed_successfully');
  assert.equal(c.services.app.read_only, true);
  assert.equal(c.services.app.environment.DJANGO_ALLOWED_HOSTS, 'blikk.betilab.com');
  assert.equal(c.services.app.environment.CSRF_TRUSTED_ORIGINS, 'https://blikk.betilab.com');
  assert.equal(c.services.app.environment.DJANGO_TRUST_PROXY, '1');
  assert.equal(c.services.app.environment.DJANGO_HTTPS, '0');
  assert.ok(c.services.app.environment.POSTGRES_PASSWORD !== c.services.migrate.environment.POSTGRES_PASSWORD, 'Appen skal ikke få databaseeierens passord');
});

test('localhost, PGPORT og valgfri databaseport er konsistente uten å endre webporten', () => {
  for (const port of ['6452','16452']) {
    const c = config({POSTGRES_PORT:port});
    assert.equal(c.services.db.environment.PGPORT, port);
    assert.ok(c.services.db.command.includes('listen_addresses=127.0.0.1'));
    assert.ok(c.services.db.command.includes('hba_file=/etc/familieblikk/pg_hba.conf'));
    assert.ok(c.services.db.command.includes('password_encryption=scram-sha-256'));
    assert.equal(c.services.db.command.at(-1), port);
    for (const name of ['app','migrate','push-worker']) {
      assert.equal(c.services[name].environment.POSTGRES_HOST, '127.0.0.1');
      assert.equal(c.services[name].environment.POSTGRES_PORT, port);
    }
    const hba = c.services.db.volumes.find(v => v.target === '/etc/familieblikk/pg_hba.conf');
    assert.ok(hba && hba.read_only);
    assert.ok(c.services.app.command.includes('0.0.0.0:6451'));
  }
});

test('oppdatering bevarer eksplisitt gjenopprettet DB og privat import uten ny eierklargjøring', () => {
  const c=config({POSTGRES_DB:'synthetic_restored_household',POSTGRES_APP_USER:'synthetic_limited_app'},true);
  for(const name of ['db','migrate','app','push-worker'])assert.equal(c.services[name].environment.POSTGRES_DB,'synthetic_restored_household');
  assert.equal(c.services['push-worker'].environment.POSTGRES_USER,'synthetic_limited_app');
  assert.equal(c.services['push-worker'].environment.POSTGRES_PASSWORD,c.services.app.environment.POSTGRES_PASSWORD);
  assert.ok(!c.services['push-worker'].volumes,'Worker trenger ikke privat importmontering');
  assert.ok(c.services.app.volumes.some(v=>v.target==='/private-import'&&v.read_only));
  assert.match(c.services.migrate.command.join(' '),/migrate --noinput.*setup_push.*setup_runtime_role/);
  assert.doesNotMatch(c.services.migrate.command.join(' '),/provision_owner|restore|apply_import|seed/);
  const ignore=fs.readFileSync(path.join(root,'.gitignore'),'utf8');
  assert.ok(ignore.includes('/Familieblikk-Synology-overforing.zip'));assert.ok(ignore.includes('/Familieblikk-Synology-overforing/'));
});

test('releasekontrakten bevarer eksisterende prosjektnavn, volum, hemmelighet og importvalg', () => {
  const overrides = {COMPOSE_PROJECT_NAME:'synthetic_existing_nas',POSTGRES_DB:'synthetic_restored_household',DJANGO_SECRET_KEY:'synthetic-existing-key-never-replace',PRIVATE_IMPORT_PATH:root};
  const after = config(overrides,true);
  assert.equal(after.name,'synthetic_existing_nas');
  assert.equal(after.volumes.database.name,'synthetic_existing_nas_database');
  for(const name of ['app','migrate','push-worker']){
    assert.equal(after.services[name].environment.DJANGO_SECRET_KEY,overrides.DJANGO_SECRET_KEY);
    assert.equal(after.services[name].environment.POSTGRES_DB,overrides.POSTGRES_DB);
  }
  assert.equal(after.services.app.volumes.find(v=>v.target==='/private-import').source.replaceAll('\\','/'),root.replaceAll('\\','/'));
  assert.doesNotMatch(after.services.migrate.command.join(' '),/provision_owner|restore|apply_import|seed|flush|DROP|TRUNCATE/i);
  const dockerignore=fs.readFileSync(path.join(root,'.dockerignore'),'utf8');
  assert.ok(dockerignore.startsWith('*\n'));
  assert.doesNotMatch(dockerignore,/^!(?:\.env|private-data|Familieblikk-Synology)/m);
  for(const name of ['AGENTS.md','rules.md','docs/DRIFT.md']){
    const rules=fs.readFileSync(path.join(root,name),'utf8');
    for(const term of ['POSTGRES_DB','PRIVATE_IMPORT_PATH','down -v','prune','flush/drop/truncate','separat'])assert.ok(rules.includes(term),name+' missing preservation rule '+term);
  }
});

test('Docker-image og privat import beholder host-nettverk og port 6451', () => {
  const dockerfile = fs.readFileSync(path.join(root,'Dockerfile'),'utf8');
  assert.match(dockerfile, /^EXPOSE 6451$/m);
  const cmd = JSON.parse(dockerfile.match(/^CMD (.+)$/m)[1]);
  assert.ok(cmd.includes('0.0.0.0:6451'));
  const c = config({}, true);
  assert.equal(c.services.app.network_mode, 'host');
  assert.ok(c.services.app.volumes.some(v => v.target === '/private-import' && v.read_only));
  const hba = fs.readFileSync(path.join(root,'docker/postgres/pg_hba.conf'),'utf8');
  assert.match(hba, /^host\s+all\s+all\s+127\.0\.0\.1\/32\s+scram-sha-256$/m);
  assert.match(hba, /^host\s+all\s+all\s+::1\/128\s+scram-sha-256$/m);
  assert.doesNotMatch(hba, /^host\s+.*\s+trust\s*$/m);
});
