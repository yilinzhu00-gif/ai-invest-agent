import { describe, expect, it } from "vitest";

import { readAgentEvents } from "../lib/sse/agent-events";

async function collectEvents(response: Response) {
  const events = [];
  for await (const event of readAgentEvents(response)) events.push(event);
  return events;
}

describe("readAgentEvents", () => {
  it("does not turn a fully consumed SSE stream into an empty message event", async () => {
    const events = await collectEvents(new Response(
      "id: 1\nevent: text.delta\ndata: {\"text\":\"第一阶段\"}\n\n"
      + "event: heartbeat\ndata: {}\n\n",
    ));

    expect(events).toEqual([
      { id: 1, event: "text.delta", data: { text: "第一阶段" } },
      { id: null, event: "heartbeat", data: {} },
    ]);
  });

  it("keeps a final non-delimited event", async () => {
    const events = await collectEvents(new Response("id: 2\nevent: run.completed\ndata: {}"));

    expect(events).toEqual([{ id: 2, event: "run.completed", data: {} }]);
  });
});
