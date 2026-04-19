'use client'

import { useState, useEffect, useRef, KeyboardEvent } from 'react'
import { getChatHistory, streamChatFetch, type ChatMessage } from '@/lib/api'

interface ChatPanelProps {
  memoId: string
}

export default function ChatPanel({ memoId }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loadingHistory, setLoadingHistory] = useState(true)
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    async function loadHistory() {
      try {
        const history = await getChatHistory(memoId)
        setMessages(history)
      } catch {
        // silently ignore if no history
      } finally {
        setLoadingHistory(false)
      }
    }
    loadHistory()
  }, [memoId])

  // Auto-scroll whenever messages or streaming content changes
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingContent])

  async function sendMessage() {
    const text = input.trim()
    if (!text || isStreaming) return

    setInput('')
    setError(null)

    // Optimistically add user message
    const userMsg: ChatMessage = {
      id: `temp-user-${Date.now()}`,
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, userMsg])
    setIsStreaming(true)
    setStreamingContent('')

    let fullContent = ''

    try {
      for await (const token of streamChatFetch(memoId, text)) {
        fullContent += token
        setStreamingContent(fullContent)
      }

      // Commit the completed assistant message
      const assistantMsg: ChatMessage = {
        id: `temp-assistant-${Date.now()}`,
        role: 'assistant',
        content: fullContent,
        created_at: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, assistantMsg])
      setStreamingContent('')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to get response. Please try again.')
      setStreamingContent('')
    } finally {
      setIsStreaming(false)
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="flex flex-col h-full bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-800 flex items-center gap-2">
        <div className="w-2 h-2 rounded-full bg-indigo-500" />
        <h2 className="text-sm font-semibold text-gray-200">Ask the Analyst</h2>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {loadingHistory ? (
          <div className="flex justify-center py-8">
            <span className="w-5 h-5 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : messages.length === 0 && !isStreaming ? (
          <div className="flex flex-col items-center justify-center h-full text-center py-12">
            <div className="w-10 h-10 bg-indigo-900/50 rounded-full flex items-center justify-center mb-3">
              <svg className="w-5 h-5 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-3 3-3-3z" />
              </svg>
            </div>
            <p className="text-gray-500 text-sm">Ask a question about this investment memo.</p>
            <p className="text-gray-600 text-xs mt-1">e.g. &ldquo;What are the main risks?&rdquo;</p>
          </div>
        ) : (
          <>
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${
                    msg.role === 'user'
                      ? 'bg-indigo-600 text-white rounded-br-sm'
                      : 'bg-gray-800 text-gray-200 rounded-bl-sm'
                  }`}
                >
                  {msg.content}
                </div>
              </div>
            ))}

            {/* Streaming in-progress */}
            {isStreaming && (
              <div className="flex justify-start">
                <div className="max-w-[85%] bg-gray-800 text-gray-200 rounded-2xl rounded-bl-sm px-4 py-2.5 text-sm leading-relaxed">
                  {streamingContent ? (
                    <span className="whitespace-pre-wrap">{streamingContent}</span>
                  ) : (
                    <span className="flex items-center gap-1.5 text-gray-500">
                      <span className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce [animation-delay:-0.3s]" />
                      <span className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce [animation-delay:-0.15s]" />
                      <span className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce" />
                    </span>
                  )}
                </div>
              </div>
            )}
          </>
        )}

        {error && (
          <div className="px-4 py-3 bg-red-900/40 border border-red-700 rounded-lg text-red-300 text-xs">
            {error}
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t border-gray-800 p-3">
        <div className="flex items-end gap-2 bg-gray-800 border border-gray-700 rounded-xl px-3 py-2 focus-within:border-indigo-600 transition-colors">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isStreaming}
            rows={1}
            placeholder="Ask a follow-up question..."
            className="flex-1 bg-transparent text-gray-100 text-sm placeholder-gray-500 resize-none focus:outline-none max-h-32 overflow-y-auto"
            style={{ minHeight: '24px' }}
          />
          <button
            onClick={sendMessage}
            disabled={!input.trim() || isStreaming}
            className="shrink-0 w-8 h-8 flex items-center justify-center bg-indigo-600 hover:bg-indigo-500 disabled:bg-gray-700 disabled:cursor-not-allowed rounded-lg transition-colors"
            aria-label="Send message"
          >
            {isStreaming ? (
              <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <svg className="w-3.5 h-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            )}
          </button>
        </div>
        <p className="text-xs text-gray-700 mt-1.5 text-center">
          Press Enter to send &bull; Shift+Enter for new line
        </p>
      </div>
    </div>
  )
}
