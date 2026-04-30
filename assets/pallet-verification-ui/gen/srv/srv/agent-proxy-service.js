'use strict';

const AGENT_URL =
  process.env.AGENT_URL ||
  'https://ba0ebe82-7f7643b4.cf54612.stage.kyma.ondemand.com';

module.exports = class AgentProxyService extends cds.ApplicationService {
  async init() {
    this.on('verify', async (req) => {
      const { deliveryOrder, imageUrl, channel } = req.data;

      // Build the A2A JSON-RPC 2.0 message
      const userText = [
        `Verify pallet for EWM outbound delivery order: ${deliveryOrder}.`,
        `Image: ${imageUrl}`,
        `Channel: ${channel || 'web'}`,
      ].join('\n');

      const a2aPayload = {
        jsonrpc: '2.0',
        method: 'message/send',
        id: Date.now(),
        params: {
          message: {
            role: 'user',
            parts: [{ kind: 'text', text: userText }],
          },
        },
      };

      let agentResponse;
      try {
        const response = await fetch(`${AGENT_URL}/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(a2aPayload),
          signal: AbortSignal.timeout(120_000),
        });

        if (!response.ok) {
          const err = await response.text();
          req.reject(502, `Agent returned ${response.status}: ${err}`);
          return;
        }

        agentResponse = await response.json();
      } catch (err) {
        req.reject(503, `Could not reach agent: ${err.message}`);
        return;
      }

      // Extract the text reply from the A2A response
      const result =
        agentResponse?.result?.message?.parts?.[0]?.text ||
        agentResponse?.result?.parts?.[0]?.text ||
        JSON.stringify(agentResponse?.result ?? agentResponse);

      return result;
    });

    return super.init();
  }
};
