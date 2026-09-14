'use client';

import React, { useState } from 'react';
import { Bot, User, ShieldAlert, ChevronDown, ChevronUp, FileText, Database, Sparkles, AlertTriangle } from 'lucide-react';
import { Message, SourceCitation } from '../types';

interface ChatMessageProps {
  message: Message;
}

export default function ChatMessage({ message }: ChatMessageProps) {
  const [showSources, setShowSources] = useState(true);

  const isUser = message.sender === 'user';
  const isRBACBlocked = message.status === 'rbac_blocked' || message.status === 'no_results_or_rbac_refusal' || message.text.includes('Access Denied');

  return (
    <div className={`flex gap-3 md:gap-4 p-4 md:p-5 rounded-2xl transition-all ${
      isUser ? 'bg-stone-800/50 border border-stone-700/40 ml-auto max-w-3xl' : 'glass-card'
    }`}>
      {/* Avatar Icon */}
      <div className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${
        isUser
          ? 'bg-amber-900/30 text-amber-300 border border-amber-700/40'
          : isRBACBlocked
          ? 'bg-orange-950/60 text-orange-400 border border-orange-800/40'
          : 'bg-gradient-to-br from-amber-700 to-amber-800 text-stone-100 shadow-md'
      }`}>
        {isUser ? <User className="w-5 h-5" /> : isRBACBlocked ? <ShieldAlert className="w-5 h-5" /> : <Bot className="w-5 h-5" />}
      </div>

      {/* Message Body */}
      <div className="space-y-3 flex-1 min-w-0">
        {/* Header Badges */}
        {!isUser && (
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="font-bold text-stone-100 tracking-wide">MediBot</span>

            {/* Retrieval Type Badge */}
            {message.retrieval_type === 'hybrid_rag' && (
              <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-lime-950/40 text-lime-300 border border-lime-700/40">
                <Sparkles className="w-3 h-3 text-lime-400" /> Hybrid RAG (Dense + BM25 + Rerank)
              </span>
            )}
            {message.retrieval_type === 'sql_rag' && (
              <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-950/40 text-amber-300 border border-amber-700/40">
                <Database className="w-3 h-3 text-amber-400" /> SQL RAG (mediassist.db)
              </span>
            )}

            {/* RBAC Refusal Badge */}
            {isRBACBlocked && (
              <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-orange-950/50 text-orange-400 border border-orange-800/40">
                <AlertTriangle className="w-3 h-3" /> RBAC Refusal
              </span>
            )}

            <span className="text-[10px] text-stone-500 ml-auto">{message.timestamp}</span>
          </div>
        )}

        {/* Text Content */}
        <div className={`text-sm md:text-base leading-relaxed whitespace-pre-wrap ${
          isRBACBlocked ? 'text-orange-200 bg-orange-950/30 p-3.5 rounded-xl border border-orange-800/40 font-medium' : 'text-stone-200'
        }`}>
          {message.text}
        </div>

        {/* Source Citations Block */}
        {!isUser && message.sources && message.sources.length > 0 && (
          <div className="pt-2 border-t border-stone-700/40 space-y-2">
            <button
              onClick={() => setShowSources(!showSources)}
              className="flex items-center justify-between w-full text-xs font-semibold text-amber-400 hover:text-amber-300 transition-colors cursor-pointer"
            >
              <span className="flex items-center gap-1.5">
                <FileText className="w-3.5 h-3.5" /> Source Citations ({message.sources.length})
              </span>
              {showSources ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </button>

            {showSources && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                {message.sources.map((src: SourceCitation, i: number) => (
                  <div
                    key={i}
                    className="p-2.5 rounded-lg bg-stone-900/80 border border-stone-800 text-xs space-y-0.5 hover:border-amber-700/40 transition-colors"
                  >
                    <div className="flex items-center justify-between text-stone-200 font-medium">
                      <span className="truncate">{src.source_document}</span>
                      <span className="text-[9px] uppercase px-1.5 py-0.2 rounded bg-stone-800 text-stone-400 border border-stone-700">
                        {src.collection}
                      </span>
                    </div>
                    <p className="text-[11px] text-stone-400 truncate">Section: {src.section_title}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
