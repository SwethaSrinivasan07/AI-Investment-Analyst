'use client'

import { useState, useEffect, useRef, KeyboardEvent } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { getChatHistory, streamChatFetch, type ChatMessage } from '@/lib/api'

interface ChatPanelProps {
  memoId: string
}

const assistantProseClass =
  'prose prose-sm max-w-none ' +
  'prose-p:my-1 prose-p:leading-relaxed prose-p:text-[#121212] prose-p:text-[13px] ' +
  'prose-headings:text-[#121212] prose-h3:text-[13px] prose-h3:font-medium prose-h3:mt-2 ' +
  'prose-strong:text-[#121212] prose-strong:font-medium ' +
  'prose-ul:my-1 prose-ul:pl-4 prose-li:my-0.5 prose-li:text-[#121212] prose-li:text-[13px] ' +
  'prose-code:text-[#2E2A47] prose-code:bg-black/5 prose-code:px-1 prose-code:text-[11px]'

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
        // silently ignore
      } finally {
        setLoadingHistory(false)
      }
    }
    loadHistory()
  }, [memoId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingContent])

  async function sendMessage() {
    const text = input.trim()
    if (!text || isStreaming) return

    setInput('')
    setError(null)

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
    <div className="flex flex-col h-full bg-white border border-black/8 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-black/8 flex items-center gap-2">
        <div className="w-1 h-4 bg-[#2E2A47]" />
        <h2 className="text-[13px] font-medium text-[#121212]">Ask the Analyst</h2>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-5 py-5 space-y-6">
        {loadingHistory ? (
          <div className="flex justify-center py-8">
            <span className="w-4 h-4 border-2 border-[#2E2A47] border-t-transparent rounded-full animate-spin" />
          </div>
        ) : messages.length === 0 && !isStreaming ? (
          <div className="flex flex-col items-center justify-center h-full text-center py-12">
            <div className="w-10 h-10 bg-[#F6F3EE] border border-black/8 flex items-center justify-center mb-3">
              <svg className="w-4 h-4 text-[#5C5C5C]/40" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-3 3-3-3z" />
              </svg>
            </div>
            <p className="text-[#5C5C5C] text-[13px]">Ask a question about this memo.</p>
            <p className="text-[#5C5C5C]/60 text-[11px] mt-1">e.g. &ldquo;What are the main risks?&rdquo;</p>
          </div>
        ) : (
          <>
            {messages.map((msg) => (
              <div key={msg.id}>
                {msg.role === 'user' ? (
                  <div>
                    <p className="text-[10px] font-medium text-[#5C5C5C] uppercase tracking-widest mb-1.5">You</p>
                    <p className="text-[13px] text-[#121212] leading-relaxed">{msg.content}</p>
                  </div>
                ) : (
                  <div className="border-l-2 border-[#2E2A47] pl-3">
                    <p className="text-[10px] font-medium text-[#2E2A47] uppercase tracking-widest mb-1.5">Analyst</p>
                    <ReactMarkdown remarkPlugins={[remarkGfm]} className={assistantProseClass}>
                      {msg.content}
                    </ReactMarkdown>
                  </div>
                )}
              </div>
            ))}

            {isStreaming && (
              <div className="border-l-2 border-[#2E2A47] pl-3">
                <p className="text-[10px] font-medium text-[#2E2A47] uppercase tracking-widest mb-1.5">Analyst</p>
                {streamingContent ? (
                  <ReactMarkdown remarkPlugins={[remarkGfm]} className={assistantProseClass}>
                    {streamingContent}
                  </ReactMarkdown>
                ) : (
                  <span className="flex items-center gap-1 py-0.5">
                    <span className="w-1 h-1 bg-[#5C5C5C] animate-bounce [animation-delay:-0.3s]" />
                    <span className="w-1 h-1 bg-[#5C5C5C] animate-bounce [animation-delay:-0.15s]" />
                    <span className="w-1 h-1 bg-[#5C5C5C] animate-bounce" />
                  </span>
                )}
              </div>
            )}
          </>
        )}

        {error && (
          <div className="px-3 py-2.5 bg-[#A14A44]/8 border border-[#A14A44]/20 text-[#A14A44] text-[12px]">
            {error}
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t border-black/8 p-3">
        <div className="flex items-end gap-2 bg-[#F6F3EE] border border-black/8 px-3 py-2 focus-within:border-[#2E2A47]/40 transition-colors">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isStreaming}
            rows={1}
            placeholder="Ask a follow-up question..."
            className="flex-1 bg-transparent text-[#121212] text-[13px] placeholder-[#5C5C5C]/40 resize-none focus:outline-none max-h-32 overflow-y-auto"
            style={{ minHeight: '24px' }}
          />
          <button
            onClick={sendMessage}
            disabled={!input.trim() || isStreaming}
            className="shrink-0 w-7 h-7 flex items-center justify-center bg-[#2E2A47] hover:bg-[#1E1A35] disabled:bg-black/10 disabled:cursor-not-allowed transition-colors"
            aria-label="Send message"
          >
            {isStreaming ? (
              <span className="w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />
            ) : (
              <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            )}
          </button>
        </div>
        <p className="text-[11px] text-[#5C5C5C]/40 mt-1.5 text-center">
          Enter to send · Shift+Enter for new line
        </p>
      </div>
    </div>
  )
}
