import { randomUUID } from 'node:crypto';
import { constants } from 'node:fs';
import { chmod, mkdir, open, rename, rm } from 'node:fs/promises';
import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';

const TOKEN_KEY = 'TELEGRAM_BOT_TOKEN';
const CHAT_ID_KEY = 'OWNER_CHAT_ID';

export function resolveTelegramConfigPath({ env = process.env, homeDir = homedir() } = {}) {
  if (env.TELEGRAM_SKILL_ENV_FILE?.trim()) {
    return resolve(env.TELEGRAM_SKILL_ENV_FILE.trim());
  }

  const configHome = env.XDG_CONFIG_HOME?.trim()
    ? resolve(env.XDG_CONFIG_HOME.trim())
    : join(homeDir, '.config');
  return join(configHome, 'codex', 'send-telegram-message.env');
}

export async function loadTelegramCredentials({ env = process.env, homeDir = homedir() } = {}) {
  const environmentToken = env[TOKEN_KEY]?.trim();
  const environmentChatId = env[CHAT_ID_KEY]?.trim();
  if (environmentToken && environmentChatId) {
    return {
      token: environmentToken,
      chatId: environmentChatId,
      source: 'environment',
    };
  }

  const configPath = resolveTelegramConfigPath({ env, homeDir });
  const parsed = parseEnvFile(await readPrivateConfigFile(configPath));
  const token = environmentToken || parsed[TOKEN_KEY]?.trim();
  const chatId = environmentChatId || parsed[CHAT_ID_KEY]?.trim();

  if (!token) {
    throw new Error(`${TOKEN_KEY} is not configured in the environment or ${configPath}`);
  }
  if (!chatId) {
    throw new Error(`${CHAT_ID_KEY} is not configured in the environment or ${configPath}`);
  }

  return { token, chatId, source: configPath };
}

export async function writeTelegramCredentials({
  token,
  chatId,
  env = process.env,
  homeDir = homedir(),
} = {}) {
  const normalizedToken = validateCredential(TOKEN_KEY, token);
  const normalizedChatId = validateCredential(CHAT_ID_KEY, chatId);
  const configPath = resolveTelegramConfigPath({ env, homeDir });
  const configDirectory = dirname(configPath);
  const temporaryPath = `${configPath}.${process.pid}.${randomUUID()}.tmp`;
  const content = `${TOKEN_KEY}=${normalizedToken}\n${CHAT_ID_KEY}=${normalizedChatId}\n`;

  await mkdir(configDirectory, { recursive: true, mode: 0o700 });
  let handle;
  try {
    handle = await open(temporaryPath, 'wx', 0o600);
    await handle.writeFile(content, 'utf8');
    await handle.sync();
    await handle.close();
    handle = undefined;
    await rename(temporaryPath, configPath);
    await chmod(configPath, 0o600);
  } catch (error) {
    await handle?.close().catch(() => {});
    await rm(temporaryPath, { force: true }).catch(() => {});
    throw error;
  }

  return configPath;
}

async function readPrivateConfigFile(configPath) {
  if (!Number.isInteger(constants.O_NOFOLLOW)) {
    throw new Error('Secure credential loading requires O_NOFOLLOW support');
  }

  let handle;
  try {
    handle = await open(configPath, constants.O_RDONLY | constants.O_NOFOLLOW);
  } catch (error) {
    if (error?.code === 'ENOENT') {
      throw new Error(`Telegram credential file not found at ${configPath}`);
    }
    if (error?.code === 'ELOOP') {
      throw new Error(`Telegram credential file must not be a symlink: ${configPath}`);
    }
    throw error;
  }

  try {
    const fileStats = await handle.stat();
    if (!fileStats.isFile()) {
      throw new Error(`Telegram credential path is not a regular file: ${configPath}`);
    }
    if ((fileStats.mode & 0o077) !== 0) {
      throw new Error(`Telegram credential file permissions must be 0600: ${configPath}`);
    }
    return await handle.readFile('utf8');
  } finally {
    await handle.close();
  }
}

function parseEnvFile(content) {
  const values = {};
  for (const rawLine of content.split(/\r?\n/u)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) {
      continue;
    }

    const match = /^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/u.exec(line);
    if (!match || (match[1] !== TOKEN_KEY && match[1] !== CHAT_ID_KEY)) {
      continue;
    }
    values[match[1]] = parseEnvValue(match[2]);
  }
  return values;
}

function parseEnvValue(value) {
  const trimmed = value.trim();
  if (trimmed.startsWith('"') && trimmed.endsWith('"')) {
    try {
      return JSON.parse(trimmed);
    } catch {
      throw new Error('Telegram credential file contains an invalid quoted value');
    }
  }
  if (trimmed.startsWith("'") && trimmed.endsWith("'")) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

function validateCredential(name, value) {
  const normalized = value?.trim();
  if (!normalized) {
    throw new Error(`${name} is not configured`);
  }
  if (/[\r\n\0]/u.test(normalized)) {
    throw new Error(`${name} contains an unsupported control character`);
  }
  return normalized;
}
