import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

import {
  sendTelegramMessage,
  splitTelegramMessage,
} from '../scripts/send-telegram-message.mjs';

test('requires the Telegram bot token and owner chat ID', async () => {
  await assert.rejects(
    sendTelegramMessage({ token: '', chatId: '123', text: 'Hello' }),
    /TELEGRAM_BOT_TOKEN/,
  );
  await assert.rejects(
    sendTelegramMessage({ token: 'test-token', chatId: '', text: 'Hello' }),
    /OWNER_CHAT_ID/,
  );
});

test('splits long messages without losing content', () => {
  const text = `${'a'.repeat(2500)}\n\n${'b'.repeat(2500)}`;
  const chunks = splitTelegramMessage(text, 4000);

  assert.equal(chunks.length, 2);
  assert.equal(chunks.join(''), text);
  assert.ok(chunks.every((chunk) => chunk.length <= 4000));
});

test('never splits an emoji surrogate pair at a hard boundary', () => {
  const text = `${'a'.repeat(3999)}😀b`;
  const chunks = splitTelegramMessage(text, 4000);

  assert.equal(chunks.join(''), text);
  assert.ok(chunks.every((chunk) => chunk.length <= 4000));
  assert.doesNotMatch(chunks[0].at(-1), /[\uD800-\uDBFF]/u);
  assert.doesNotMatch(chunks[1].at(0), /[\uDC00-\uDFFF]/u);
});

test('posts every chunk to the Telegram Bot API as plain text', async () => {
  const requests = [];
  const fetchImpl = async (url, options) => {
    requests.push({ url, options, body: JSON.parse(options.body) });
    return new Response(JSON.stringify({
      ok: true,
      result: { message_id: requests.length },
    }), { status: 200, headers: { 'content-type': 'application/json' } });
  };

  const result = await sendTelegramMessage({
    token: 'test-token',
    chatId: 'owner-chat',
    text: `${'a'.repeat(4000)}\n${'b'.repeat(20)}`,
    fetchImpl,
  });

  assert.deepEqual(result, { success: true, chunks: 2, messageIds: [1, 2] });
  assert.equal(requests.length, 2);
  assert.equal(requests[0].url, 'https://api.telegram.org/bottest-token/sendMessage');
  assert.equal(requests[0].options.method, 'POST');
  assert.equal(requests[0].options.headers['content-type'], 'application/json');
  assert.deepEqual(Object.keys(requests[0].body).sort(), [
    'chat_id',
    'disable_web_page_preview',
    'text',
  ]);
  assert.equal(requests[0].body.chat_id, 'owner-chat');
  assert.equal(requests[0].body.disable_web_page_preview, false);
  assert.ok(requests.every((request) => request.body.text.length <= 4000));
});

test('reports partial delivery without leaking the bot token', async () => {
  let callCount = 0;
  const fetchImpl = async () => {
    callCount += 1;
    if (callCount === 1) {
      return new Response(JSON.stringify({
        ok: true,
        result: { message_id: 99 },
      }), { status: 200, headers: { 'content-type': 'application/json' } });
    }
    return new Response(JSON.stringify({ ok: false, description: 'Bad Request' }), {
      status: 400,
      headers: { 'content-type': 'application/json' },
    });
  };

  await assert.rejects(
    sendTelegramMessage({
      token: 'super-secret-token',
      chatId: 'owner-chat',
      text: `${'a'.repeat(4000)}\n${'b'.repeat(20)}`,
      fetchImpl,
    }),
    (error) => {
      assert.equal(error.name, 'TelegramDeliveryError');
      assert.equal(error.sentChunks, 1);
      assert.equal(error.totalChunks, 2);
      assert.equal(error.deliveryUnknown, true);
      assert.doesNotMatch(error.message, /super-secret-token/);
      assert.doesNotMatch(error.cause?.message ?? '', /super-secret-token/);
      assert.match(error.message, /Bad Request/);
      return true;
    },
  );
});

test('rejects empty messages before making a request', async () => {
  let requested = false;
  await assert.rejects(
    sendTelegramMessage({
      token: 'test-token',
      chatId: 'owner-chat',
      text: '  \n',
      fetchImpl: async () => {
        requested = true;
      },
    }),
    /must not be empty/,
  );
  assert.equal(requested, false);
});

test('treats a malformed success response as delivery-unknown', async () => {
  await assert.rejects(
    sendTelegramMessage({
      token: 'test-token',
      chatId: 'owner-chat',
      text: 'Hello',
      fetchImpl: async () => new Response(JSON.stringify({ ok: true, result: {} }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    }),
    (error) => {
      assert.equal(error.sentChunks, 0);
      assert.equal(error.totalChunks, 1);
      assert.equal(error.deliveryUnknown, true);
      assert.match(error.message, /message_id/);
      return true;
    },
  );
});

test('CLI removes only the heredoc framing newline', () => {
  const scriptPath = fileURLToPath(new URL('../scripts/send-telegram-message.mjs', import.meta.url));
  const mockPath = fileURLToPath(new URL('./mock-fetch.mjs', import.meta.url));
  const result = spawnSync(process.execPath, ['--import', mockPath, scriptPath], {
    input: 'Exact message text\n',
    encoding: 'utf8',
    env: {
      ...process.env,
      TELEGRAM_BOT_TOKEN: 'test-token',
      OWNER_CHAT_ID: 'owner-chat',
    },
  });

  assert.equal(result.status, 0, result.stderr);
  const request = result.stderr
    .trim()
    .split('\n')
    .map((line) => JSON.parse(line))
    .find((event) => event.event === 'mock_telegram_request');
  assert.equal(request.body.text, 'Exact message text');
});
