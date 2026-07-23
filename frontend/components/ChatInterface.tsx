"use client";

import React, { useRef, useState, useEffect, useCallback } from "react";
import { Mic, Send } from "lucide-react";

const WS_URL = "ws://127.0.0.1:8000/api/v1/chat/123";

export default function ChatInterface() {
  const [input, setInput] = useState("");
  const [isListening, setIsListening] = useState(false);
  const [connected, setConnected] = useState(false);
  const [messages, setMessages] = useState<{
    role: "user" | "ai";
    content: string;
  }[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const recognitionRef = useRef<any>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Keep the newest exchange visible without shifting the fixed input controls.
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ─── WebSocket Connection ───────────────────────────────────────────────

  useEffect(() => {
    const connect = () => {
      const ws = new WebSocket(WS_URL);

      ws.onopen = () => {
        setConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          // Play audio and dispatch speaking events
          if (data.audio) {
            const audio = new Audio(`data:audio/mp3;base64,${data.audio}`);

            audio.addEventListener("play", () => {
              window.dispatchEvent(new CustomEvent("start-speaking"));
            });

            audio.addEventListener("ended", () => {
              window.dispatchEvent(new CustomEvent("stop-speaking"));
            });

            audio.play().catch(() => {
              // Autoplay blocked — dispatch stop
              window.dispatchEvent(new CustomEvent("stop-speaking"));
            });
          }

          // Dispatch the avatar event and independently persist the response.
          // Keeping these as two explicit operations prevents UI history from
          // depending on any listener attached to the global window event.
          if (data.content) {
            window.dispatchEvent(
              new CustomEvent("ai-message-received", {
                detail: data.content,
              })
            );
            setMessages((prev) => [
              ...prev,
              { role: "ai", content: data.content },
            ]);
          }
        } catch {
          // Ignore malformed messages
        }
      };

      ws.onclose = () => {
        setConnected(false);
        // Reconnect after 3s
        setTimeout(connect, 3000);
      };

      ws.onerror = () => {
        ws.close();
      };

      wsRef.current = ws;
    };

    connect();

    return () => {
      wsRef.current?.close();
    };
  }, []);

  // ─── Send Message ───────────────────────────────────────────────────────

  const sendMessage = useCallback(
    (text: string) => {
      const textToSend = text.trim();
      if (!textToSend) return;

      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ payload: textToSend }));
        setMessages((prev) => [
          ...prev,
          { role: "user", content: textToSend },
        ]);
        setInput("");
      }
    },
    []
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    sendMessage(input);
  };

  // ─── Speech Recognition ─────────────────────────────────────────────────

  const toggleListening = useCallback(() => {
    const SpeechRecognition =
      (window as any).webkitSpeechRecognition ||
      (window as any).SpeechRecognition;

    if (!SpeechRecognition) {
      alert("Speech recognition is not supported in this browser.");
      return;
    }

    if (isListening) {
      recognitionRef.current?.stop();
      setIsListening(false);
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = "en-US";

    recognition.onresult = (event: any) => {
      const transcript = event.results[0][0].transcript;
      sendMessage(transcript);
      setIsListening(false);
    };

    recognition.onerror = () => {
      setIsListening(false);
    };

    recognition.onend = () => {
      setIsListening(false);
    };

    recognition.start();
    recognitionRef.current = recognition;
    setIsListening(true);
  }, [isListening, sendMessage]);

  // ─── Quick Prompts ──────────────────────────────────────────────────────

  const quickPrompts = ["Translate", "Nearby", "Culture"];

  // ─── Render ─────────────────────────────────────────────────────────────

  return (
    <div className="absolute bottom-0 z-20 flex w-full flex-col items-center p-4 pointer-events-none">
      {/* Scrollable glassmorphism transcript; rendered only after first message. */}
      {messages.length > 0 && (
        <div className="w-full max-w-3xl h-48 overflow-y-auto bg-gray-900/70 backdrop-blur-md rounded-2xl p-4 mb-2 shadow-2xl pointer-events-auto flex flex-col gap-3 scrollbar-thin scrollbar-thumb-gray-600">
          {messages.map((message, index) => (
            <div
              key={`${message.role}-${index}`}
              className={`flex w-full ${
                message.role === "user" ? "justify-end" : "justify-start"
              }`}
            >
              <div
                className={`max-w-[80%] whitespace-pre-wrap break-words rounded-2xl px-4 py-2 text-sm shadow-md ${
                  message.role === "user"
                    ? "rounded-br-sm bg-blue-600 text-white"
                    : "rounded-bl-sm bg-gray-700 text-gray-100"
                }`}
              >
                {message.content}
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>
      )}

      {/* Quick Prompts */}
      <div className="flex justify-center gap-2 mb-3 pointer-events-auto">
        {quickPrompts.map((prompt) => (
          <button
            key={prompt}
            onClick={() => sendMessage(prompt)}
            className="px-4 py-1.5 bg-white/90 backdrop-blur-sm rounded-full text-sm font-medium text-gray-700 shadow-md hover:bg-white hover:shadow-lg transition-all"
          >
            {prompt}
          </button>
        ))}
      </div>

      {/* Input Bar */}
      <form
        onSubmit={handleSubmit}
        className="flex w-full max-w-3xl items-center gap-2 pointer-events-auto"
      >
        <div className="flex min-w-0 flex-1 items-center bg-white/95 backdrop-blur-sm rounded-full shadow-lg px-4 py-2 border border-gray-200">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask the concierge..."
            className="min-w-0 flex-1 bg-transparent outline-none text-sm text-gray-800 placeholder-gray-400"
          />
          <button
            type="button"
            onClick={toggleListening}
            className={`p-2 rounded-full transition-colors ${
              isListening
                ? "bg-red-100 text-red-600"
                : "hover:bg-gray-100 text-gray-500"
            }`}
            aria-label="Voice input"
          >
            <Mic size={18} />
          </button>
          <button
            type="submit"
            className="p-2 rounded-full hover:bg-blue-100 text-blue-600 transition-colors"
            aria-label="Send message"
          >
            <Send size={18} />
          </button>
        </div>
      </form>

      {/* Disclaimer */}
      <p className="text-xs text-gray-400 mt-2 text-center">
        AI-generated responses may occasionally be inaccurate. Please verify
        important information.
      </p>
    </div>
  );
}
