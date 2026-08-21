import { NextRequest } from "next/server";

const encoder = new TextEncoder();

function event(name: string, data: Record<string, unknown>, id: number): Uint8Array {
  return encoder.encode(`id: ${id}\nevent: ${name}\ndata: ${JSON.stringify(data)}\n\n`);
}

export async function POST(request: NextRequest) {
  const payload = await request.json().catch(() => ({})) as { symbol?: string; message?: string };
  const symbol = typeof payload.symbol === "string" ? payload.symbol.toUpperCase() : "AAPL";
  const message = typeof payload.message === "string" ? payload.message.trim() : "";
  if (!message) return Response.json({ error: "message_required" }, { status: 400 });

  const answer = `${symbol} 的研究重点可以先拆成三层：盈利增长的来源、当前估值隐含的预期，以及可能改变投资逻辑的风险。基于当前演示数据，建议把服务业务增速、AI 产品转化和监管进展列为后续核验清单。`;
  const chunks = answer.match(/.{1,18}/gu) ?? [answer];
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      controller.enqueue(event("meta", { symbol, mode: "demo", message }, 1));
      for (const [index, text] of chunks.entries()) {
        await new Promise((resolve) => setTimeout(resolve, 28));
        controller.enqueue(event("delta", { text }, index + 2));
      }
      controller.enqueue(event("done", { report: symbol === "AAPL" ? "/reports" : "/reports?symbol=AAPL" }, chunks.length + 2));
      controller.close();
    },
  });
  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
