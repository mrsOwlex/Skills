globalThis.fetch = async (_url, options) => {
  process.stderr.write(`${JSON.stringify({
    event: 'mock_telegram_request',
    body: JSON.parse(options.body),
  })}\n`);
  return new Response(JSON.stringify({
    ok: true,
    result: { message_id: 42 },
  }), { status: 200, headers: { 'content-type': 'application/json' } });
};
