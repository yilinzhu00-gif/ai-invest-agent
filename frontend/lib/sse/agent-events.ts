export type AgentEvent = {
  id: number | null;
  event: string;
  data: Record<string, unknown>;
};

function parseRecord(record: string): AgentEvent | null {
  if (!record.trim()) return null;
  let id: number | null = null;
  let event = "message";
  let data: Record<string, unknown> = {};
  for (const line of record.split("\n")) {
    if (line.startsWith("id: ")) {
      const parsed = Number(line.slice(4));
      id = Number.isSafeInteger(parsed) ? parsed : null;
    } else if (line.startsWith("event: ")) {
      event = line.slice(7);
    } else if (line.startsWith("data: ")) {
      try {
        const parsed = JSON.parse(line.slice(6));
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) data = parsed as Record<string, unknown>;
      } catch {
        return null;
      }
    }
  }
  return { id, event, data };
}

export async function* readAgentEvents(response: Response): AsyncGenerator<AgentEvent> {
  const reader = response.body?.getReader();
  if (!reader) return;
  const decoder = new TextDecoder();
  let buffered = "";
  while (true) {
    const next = await reader.read();
    if (next.done) break;
    buffered += decoder.decode(next.value, { stream: true });
    const records = buffered.split("\n\n");
    buffered = records.pop() ?? "";
    for (const record of records) {
      const event = parseRecord(record);
      if (event) yield event;
    }
  }
  if (buffered.trim()) {
    const finalEvent = parseRecord(buffered);
    if (finalEvent) yield finalEvent;
  }
}
