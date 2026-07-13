import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { chmod, mkdtemp, readFile, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

import {
  loadTelegramCredentials,
  resolveTelegramConfigPath,
} from '../scripts/telegram-config.mjs';

test('resolves a stable user config path without workspace assumptions', () => {
  assert.equal(
    resolveTelegramConfigPath({ env: {}, homeDir: '/home/alex' }),
    '/home/alex/.config/codex/send-telegram-message.env',
  );
  assert.equal(
    resolveTelegramConfigPath({ env: { XDG_CONFIG_HOME: '/config' }, homeDir: '/ignored' }),
    '/config/codex/send-telegram-message.env',
  );
  assert.equal(
    resolveTelegramConfigPath({
      env: { TELEGRAM_SKILL_ENV_FILE: '/custom/telegram.env' },
      homeDir: '/ignored',
    }),
    '/custom/telegram.env',
  );
});

test('prefers already exported credentials without requiring a config file', async () => {
  const result = await loadTelegramCredentials({
    env: {
      TELEGRAM_BOT_TOKEN: 'exported-token',
      OWNER_CHAT_ID: 'exported-chat',
    },
    homeDir: '/path/that/does/not/exist',
  });

  assert.deepEqual(result, {
    token: 'exported-token',
    chatId: 'exported-chat',
    source: 'environment',
  });
});

test('loads credentials from a private standalone env file', async (t) => {
  const directory = await mkdtemp(join(tmpdir(), 'telegram-config-test-'));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const configPath = join(directory, 'telegram.env');
  await writeFile(configPath, [
    '# Telegram skill credentials',
    'TELEGRAM_BOT_TOKEN=file-token',
    'OWNER_CHAT_ID=file-chat',
    '',
  ].join('\n'), { mode: 0o600 });

  const result = await loadTelegramCredentials({
    env: { TELEGRAM_SKILL_ENV_FILE: configPath },
    homeDir: '/ignored',
  });

  assert.deepEqual(result, {
    token: 'file-token',
    chatId: 'file-chat',
    source: configPath,
  });
});

test('refuses a credential file readable by group or others', async (t) => {
  const directory = await mkdtemp(join(tmpdir(), 'telegram-config-test-'));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const configPath = join(directory, 'telegram.env');
  await writeFile(configPath, 'TELEGRAM_BOT_TOKEN=x\nOWNER_CHAT_ID=y\n', { mode: 0o600 });
  await chmod(configPath, 0o644);

  await assert.rejects(
    loadTelegramCredentials({
      env: { TELEGRAM_SKILL_ENV_FILE: configPath },
      homeDir: '/ignored',
    }),
    /permissions.*0600/i,
  );
});

test('refuses a symlinked credential file', async (t) => {
  const directory = await mkdtemp(join(tmpdir(), 'telegram-config-test-'));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const targetPath = join(directory, 'target.env');
  const symlinkPath = join(directory, 'telegram.env');
  await writeFile(targetPath, 'TELEGRAM_BOT_TOKEN=x\nOWNER_CHAT_ID=y\n', { mode: 0o600 });
  await symlink(targetPath, symlinkPath);

  await assert.rejects(
    loadTelegramCredentials({
      env: { TELEGRAM_SKILL_ENV_FILE: symlinkPath },
      homeDir: '/ignored',
    }),
    /symlink|regular file/i,
  );
});

test('configuration CLI writes a private file without printing credentials', async (t) => {
  const directory = await mkdtemp(join(tmpdir(), 'telegram-config-test-'));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const configPath = join(directory, 'telegram.env');
  const scriptPath = fileURLToPath(new URL('../scripts/configure-telegram-env.mjs', import.meta.url));
  const result = spawnSync(process.execPath, [scriptPath], {
    encoding: 'utf8',
    env: {
      ...process.env,
      TELEGRAM_BOT_TOKEN: 'migration-token',
      OWNER_CHAT_ID: 'migration-chat',
      TELEGRAM_SKILL_ENV_FILE: configPath,
    },
  });

  assert.equal(result.status, 0, result.stderr);
  assert.doesNotMatch(`${result.stdout}${result.stderr}`, /migration-token|migration-chat/);
  assert.match(result.stdout, /telegram_credentials_configured/);
  assert.equal((await readFile(configPath, 'utf8')).trim(), [
    'TELEGRAM_BOT_TOKEN=migration-token',
    'OWNER_CHAT_ID=migration-chat',
  ].join('\n'));
  const mode = (await import('node:fs/promises')).stat(configPath).then((value) => value.mode & 0o777);
  assert.equal(await mode, 0o600);
});

test('sender CLI loads the standalone config file', async (t) => {
  const directory = await mkdtemp(join(tmpdir(), 'telegram-config-test-'));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const configPath = join(directory, 'telegram.env');
  await writeFile(configPath, 'TELEGRAM_BOT_TOKEN=file-token\nOWNER_CHAT_ID=file-chat\n', { mode: 0o600 });
  const scriptPath = fileURLToPath(new URL('../scripts/send-telegram-message.mjs', import.meta.url));
  const mockPath = fileURLToPath(new URL('./mock-fetch.mjs', import.meta.url));
  const env = { ...process.env, TELEGRAM_SKILL_ENV_FILE: configPath };
  delete env.TELEGRAM_BOT_TOKEN;
  delete env.OWNER_CHAT_ID;

  const result = spawnSync(process.execPath, ['--import', mockPath, scriptPath], {
    input: 'Loaded independently\n',
    encoding: 'utf8',
    env,
  });

  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /telegram_message_sent/);
  const request = result.stderr
    .trim()
    .split('\n')
    .map((line) => JSON.parse(line))
    .find((event) => event.event === 'mock_telegram_request');
  assert.equal(request.body.chat_id, 'file-chat');
  assert.equal(request.body.text, 'Loaded independently');
});
