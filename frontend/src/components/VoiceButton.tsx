"use client"

import { useRef, useState } from "react"
import { Mic, MicOff } from "lucide-react"

/** Hands-free control using the browser Web Speech API (no API key needed). */
export default function VoiceButton({ onTranscript }: { onTranscript: (text: string) => void }) {
  const [listening, setListening] = useState(false)
  const recognition = useRef<any>(null)

  function toggle() {
    const SpeechRecognition =
      (globalThis as any).SpeechRecognition ?? (globalThis as any).webkitSpeechRecognition
    if (!SpeechRecognition) {
      alert("Speech recognition is not supported in this browser.")
      return
    }
    if (listening) {
      recognition.current?.stop()
      setListening(false)
      return
    }
    const instance = new SpeechRecognition()
    instance.lang = "en-IN"
    instance.interimResults = false
    instance.continuous = false
    instance.onresult = (event: any) => onTranscript(event.results[0][0].transcript as string)
    instance.onend = () => setListening(false)
    instance.start()
    recognition.current = instance
    setListening(true)
  }

  return (
    <button
      onClick={toggle}
      title="Voice command"
      className={`btn h-[54px] px-3 ${listening ? "border-accent text-accent" : ""}`}
    >
      {listening ? <MicOff size={18} /> : <Mic size={18} />}
    </button>
  )
}
