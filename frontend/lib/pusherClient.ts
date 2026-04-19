"use client";
import Pusher from "pusher-js";
import pako from "pako";

let _pusher: Pusher | null = null;
export function getPusher() {
  if (_pusher) return _pusher;
  _pusher = new Pusher(process.env.NEXT_PUBLIC_PUSHER_KEY!, {
    cluster: process.env.NEXT_PUBLIC_PUSHER_CLUSTER ?? "eu",
  });
  return _pusher;
}

export function decodeToolPayload(data: any): any {
  if (data && data.__gz && typeof data.b64 === "string") {
    const bytes = Uint8Array.from(atob(data.b64), (c) => c.charCodeAt(0));
    const json = pako.ungzip(bytes, { to: "string" });
    return JSON.parse(json);
  }
  return data;
}

export function subscribeToolCalls(
  threadId: string,
  onToolCall: (payload: { id: string; name: string; args: any }) => void
) {
  const channel = getPusher().subscribe(`agent-${threadId}`);
  const handler = (data: any) => onToolCall(decodeToolPayload(data));
  channel.bind("tool_call", handler);
  return () => {
    channel.unbind("tool_call", handler);
    getPusher().unsubscribe(`agent-${threadId}`);
  };
}
