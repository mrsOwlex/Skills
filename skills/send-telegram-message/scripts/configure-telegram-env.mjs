#!/usr/bin/env node

import { pathToFileURL } from 'node:url';

import { writeTelegramCredentials } from './telegram-config.mjs';

async function main() {
  try {
    const configPath = await writeTelegramCredentials({
      token: process.env.TELEGRAM_BOT_TOKEN,
      chatId: process.env.OWNER_CHAT_ID,
    });
    process.stdout.write(`${JSON.stringify({
      event: 'telegram_credentials_configured',
      configPath,
    })}\n`);
  } catch (error) {
    process.stderr.write(`${JSON.stringify({
      event: 'telegram_credentials_configuration_failed',
      error: error instanceof Error ? error.message : String(error),
    })}\n`);
    process.exitCode = 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}
