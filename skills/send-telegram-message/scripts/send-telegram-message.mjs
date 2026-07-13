#!/usr/bin/env node

import { pathToFileURL } from 'node:url';

const TELEGRAM_API_BASE = 'https://api.telegram.org/bot';
const TELEGRAM_CHUNK_SIZE = 4000;

export class TelegramDeliveryError extends Error {
  constructor(message, { sentChunks = 0, totalChunks = 0, deliveryUnknown = false } = {}) {
    super(message);
    this.name = 'TelegramDeliveryError';
    this.sentChunks = sentChunks;
    this.totalChunks = totalChunks;
    this.deliveryUnknown = deliveryUnknown;
  }
}

export function splitTelegramMessage(text, maxLength = TELEGRAM_CHUNK_SIZE) {
  if (!Number.isInteger(maxLength) || maxLength <= 0) {
    throw new TypeError('maxLength must be a positive integer');
  }
  if (text.length <= maxLength) {
    return [text];
  }

  const chunks = [];
  let remaining = text;

  while (remaining.length > maxLength) {
    const paragraphIndex = remaining.lastIndexOf('\n\n', maxLength - 2);
    let endIndex = paragraphIndex >= 0 ? paragraphIndex + 2 : 0;

    if (endIndex <= 0) {
      const lineIndex = remaining.lastIndexOf('\n', maxLength - 1);
      endIndex = lineIndex >= 0 ? lineIndex + 1 : 0;
    }
    if (endIndex <= 0) {
      endIndex = maxLength;
      if (isHighSurrogate(remaining.charCodeAt(endIndex - 1))
        && isLowSurrogate(remaining.charCodeAt(endIndex))) {
        endIndex -= 1;
      }
    }

    chunks.push(remaining.slice(0, endIndex));
    remaining = remaining.slice(endIndex);
  }

  if (remaining.length > 0) {
    chunks.push(remaining);
  }

  return chunks;
}

function isHighSurrogate(codeUnit) {
  return codeUnit >= 0xD800 && codeUnit <= 0xDBFF;
}

function isLowSurrogate(codeUnit) {
  return codeUnit >= 0xDC00 && codeUnit <= 0xDFFF;
}

export async function sendTelegramMessage({
  token,
  chatId,
  text,
  fetchImpl = globalThis.fetch,
}) {
  if (!token?.trim()) {
    throw new TelegramDeliveryError('TELEGRAM_BOT_TOKEN is not configured');
  }
  if (!chatId?.trim()) {
    throw new TelegramDeliveryError('OWNER_CHAT_ID is not configured');
  }
  if (typeof text !== 'string' || !text.trim()) {
    throw new TelegramDeliveryError('Telegram message must not be empty');
  }
  if (typeof fetchImpl !== 'function') {
    throw new TelegramDeliveryError('This script requires Node.js 18 or newer with fetch support');
  }

  const normalizedToken = token.trim();
  const normalizedChatId = chatId.trim();
  const chunks = splitTelegramMessage(text);
  const messageIds = [];
  let sentChunks = 0;

  for (const chunk of chunks) {
    try {
      const response = await fetchImpl(`${TELEGRAM_API_BASE}${normalizedToken}/sendMessage`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          chat_id: normalizedChatId,
          text: chunk,
          disable_web_page_preview: false,
        }),
        signal: AbortSignal.timeout(30_000),
      });
      const payload = await readTelegramPayload(response);

      if (!response.ok || payload.ok !== true) {
        const detail = typeof payload.description === 'string'
          ? payload.description
          : `HTTP ${response.status}`;
        throw new Error(detail);
      }

      const messageId = payload.result?.message_id;
      if (!Number.isInteger(messageId)) {
        throw new Error('Telegram success response is missing result.message_id');
      }
      messageIds.push(messageId);
      sentChunks += 1;
    } catch (error) {
      const safeMessage = redactSecret(
        error instanceof Error ? error.message : String(error),
        normalizedToken,
      );
      throw new TelegramDeliveryError(`Telegram delivery failed: ${safeMessage}`, {
        sentChunks,
        totalChunks: chunks.length,
        deliveryUnknown: true,
      });
    }
  }

  return { success: true, chunks: chunks.length, messageIds };
}

async function readTelegramPayload(response) {
  try {
    return await response.json();
  } catch {
    return { ok: false, description: `HTTP ${response.status} returned invalid JSON` };
  }
}

function redactSecret(value, secret) {
  return secret ? value.replaceAll(secret, '[REDACTED]') : value;
}

async function readStdin() {
  let input = '';
  process.stdin.setEncoding('utf8');
  for await (const chunk of process.stdin) {
    input += chunk;
  }
  return input;
}

async function main() {
  const text = stripFramingLineEnding(await readStdin());

  try {
    const result = await sendTelegramMessage({
      token: process.env.TELEGRAM_BOT_TOKEN,
      chatId: process.env.OWNER_CHAT_ID,
      text,
    });
    process.stdout.write(`${JSON.stringify({ event: 'telegram_message_sent', ...result })}\n`);
  } catch (error) {
    const event = {
      event: 'telegram_message_failed',
      error: error instanceof Error ? error.message : String(error),
      sentChunks: error instanceof TelegramDeliveryError ? error.sentChunks : 0,
      totalChunks: error instanceof TelegramDeliveryError ? error.totalChunks : 0,
      deliveryUnknown: error instanceof TelegramDeliveryError ? error.deliveryUnknown : false,
    };
    process.stderr.write(`${JSON.stringify(event)}\n`);
    process.exitCode = 1;
  }
}

function stripFramingLineEnding(text) {
  return text.replace(/\r?\n$/, '');
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}
