import { useState } from "react";
import { ChatDrawer } from "./ChatDrawer";

export function ChatBubble(): JSX.Element {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button className="pw-chat-bubble" type="button" onClick={() => setOpen((value) => !value)} aria-label="打开 Chat Assistant">
        <span>问</span>
      </button>
      <ChatDrawer open={open} onClose={() => setOpen(false)} />
    </>
  );
}
