"use client";

import { ArrowUp, Mic, MicOff, Square } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

// Minimal typing for the Web Speech API (not in TypeScript's DOM lib).
interface SpeechRecognitionResultLike {
  isFinal: boolean;
  0: { transcript: string };
}
interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: ArrayLike<SpeechRecognitionResultLike>;
}
interface SpeechRecognitionLike {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start(): void;
  stop(): void;
  onresult: ((e: SpeechRecognitionEventLike) => void) | null;
  onend: (() => void) | null;
  onerror: ((e: { error: string }) => void) | null;
}
type RecognitionCtor = new () => SpeechRecognitionLike;

function getRecognition(): RecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: RecognitionCtor;
    webkitSpeechRecognition?: RecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function Composer({
  onSend,
  onStop,
  streaming,
  disabled,
  disabledReason,
  draft,
  onDraftConsumed,
}: {
  onSend: (text: string) => void;
  onStop: () => void;
  streaming: boolean;
  disabled?: boolean;
  disabledReason?: string;
  draft?: string | null;
  onDraftConsumed?: () => void;
}) {
  const [value, setValue] = useState("");
  const [listening, setListening] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [voiceSupported, setVoiceSupported] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const baseTextRef = useRef("");

  useEffect(() => {
    // Feature detection must run on the client only.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setVoiceSupported(getRecognition() !== null);
  }, []);

  const resize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  }, []);

  useEffect(resize, [value, resize]);

  useEffect(() => {
    if (draft) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setValue(draft);
      onDraftConsumed?.();
      requestAnimationFrame(() => textareaRef.current?.focus());
    }
  }, [draft, onDraftConsumed]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const typing = target?.closest("input, textarea, [contenteditable=true]");
      if (e.key === "/" && !typing) {
        e.preventDefault();
        textareaRef.current?.focus();
      }
      if (e.key === "Escape" && streaming) onStop();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [streaming, onStop]);

  useEffect(() => () => recognitionRef.current?.stop(), []);

  const submit = () => {
    const text = value.trim();
    if (!text || streaming || disabled) return;
    recognitionRef.current?.stop();
    onSend(text);
    setValue("");
  };

  const toggleVoice = () => {
    if (listening) {
      recognitionRef.current?.stop();
      return;
    }
    const Ctor = getRecognition();
    if (!Ctor) return;
    const rec = new Ctor();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = navigator.language || "en-US";
    baseTextRef.current = value ? `${value.trimEnd()} ` : "";
    rec.onresult = (e) => {
      let finalText = "";
      let interim = "";
      for (let i = 0; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) finalText += r[0].transcript;
        else interim += r[0].transcript;
      }
      setValue(baseTextRef.current + finalText + interim);
    };
    rec.onerror = (e) => {
      setVoiceError(
        e.error === "not-allowed"
          ? "Microphone permission was denied."
          : `Voice input error: ${e.error}`,
      );
    };
    rec.onend = () => {
      setListening(false);
      recognitionRef.current = null;
    };
    recognitionRef.current = rec;
    setVoiceError(null);
    setListening(true);
    rec.start();
  };

  const canSend = value.trim().length > 0 && !disabled;

  return (
    <div className="mx-auto w-full max-w-3xl">
      <div
        className={cn(
          "brackets panel relative rounded-2xl transition",
          "focus-within:border-cyan/35 focus-within:shadow-[0_0_40px_-14px_rgba(34,211,238,0.55)]",
          listening && "border-cyan/50",
        )}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
          rows={1}
          placeholder={
            disabled ? (disabledReason ?? "Unavailable") : listening ? "Listening…" : "Ask NEXUS anything…"
          }
          disabled={disabled}
          aria-label="Message NEXUS"
          className="scroll-thin block max-h-[220px] w-full resize-none bg-transparent px-4 pt-3.5 pb-12 text-[0.95rem] leading-relaxed text-ink placeholder:text-ink-faint focus:outline-none disabled:cursor-not-allowed"
        />
        <div className="absolute inset-x-2 bottom-2 flex items-center justify-between">
          <button
            type="button"
            onClick={toggleVoice}
            disabled={!voiceSupported || disabled}
            title={
              voiceSupported
                ? listening
                  ? "Stop dictation"
                  : "Dictate (browser speech recognition)"
                : "Voice input is not supported in this browser"
            }
            aria-label={listening ? "Stop dictation" : "Start dictation"}
            aria-pressed={listening}
            className={cn(
              "grid size-9 place-items-center rounded-xl border transition",
              listening
                ? "border-cyan/60 bg-cyan/15 text-cyan shadow-[0_0_18px_-4px_rgba(34,211,238,0.8)]"
                : "border-line text-ink-muted hover:border-line-strong hover:text-ice",
              "disabled:cursor-not-allowed disabled:opacity-40",
            )}
          >
            {voiceSupported ? <Mic className={cn("size-4", listening && "animate-pulse")} /> : <MicOff className="size-4" />}
          </button>
          <div className="flex items-center gap-3">
            <span className="hidden font-mono text-[10px] tracking-wider text-ink-faint sm:inline">
              {streaming ? "ESC TO STOP" : "ENTER ↵ SEND · SHIFT+ENTER NEWLINE"}
            </span>
            {streaming ? (
              <button
                type="button"
                onClick={onStop}
                aria-label="Stop generating"
                title="Stop generating (Esc)"
                className="grid size-9 place-items-center rounded-xl border border-danger/40 bg-danger/10 text-danger transition hover:bg-danger/20"
              >
                <Square className="size-3.5 fill-current" />
              </button>
            ) : (
              <button
                type="button"
                onClick={submit}
                disabled={!canSend}
                aria-label="Send message"
                title="Send (Enter)"
                className={cn(
                  "grid size-9 place-items-center rounded-xl transition",
                  canSend
                    ? "bg-cyan text-void shadow-[0_0_22px_-4px_rgba(34,211,238,0.9)] hover:bg-ice"
                    : "bg-white/5 text-ink-faint",
                )}
              >
                <ArrowUp className="size-4" strokeWidth={2.5} />
              </button>
            )}
          </div>
        </div>
      </div>
      {voiceError && <p className="mt-2 text-center text-xs text-warn">{voiceError}</p>}
    </div>
  );
}
