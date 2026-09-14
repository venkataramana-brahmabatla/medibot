'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import Header from '../components/Header';
import LoginScreen from '../components/LoginScreen';
import ChatMessage from '../components/ChatMessage';
import ChatInput from '../components/ChatInput';
import CollectionsModal from '../components/CollectionsModal';
import { User, Message, Role } from '../types';
import { DEMO_ACCOUNTS } from '../constants/demoAccounts';
import { Stethoscope, Sparkles } from 'lucide-react';

function readStoredUser(): User | null {
  if (typeof window === 'undefined') return null;

  const savedUser = localStorage.getItem('medibot_user');
  if (!savedUser) return null;

  try {
    return JSON.parse(savedUser) as User;
  } catch {
    localStorage.removeItem('medibot_user');
    return null;
  }
}

export default function Home() {
  const [user, setUser] = useState<User | null>(readStoredUser);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [accessibleCollections, setAccessibleCollections] = useState<string[]>(() => {
    const storedUser = readStoredUser();
    return DEMO_ACCOUNTS.find((account) => account.role === storedUser?.role)?.accessible_collections ?? [];
  });
  const [isCollectionsOpen, setIsCollectionsOpen] = useState(false);
  const chatBottomRef = useRef<HTMLDivElement>(null);

  const fetchAccessibleCollections = useCallback(async (role: Role) => {
    try {
      const res = await fetch(`http://localhost:8000/collections/${role}`);
      if (res.ok) {
        const data = await res.json();
        setAccessibleCollections(data.accessible_collections || []);
      }
    } catch (err: unknown) {
      console.error('Failed to fetch collections:', err);
    }
  }, []);

  // Auto-scroll chat to bottom
  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleLogin = (token: string, username: string, role: Role, fullName: string) => {
    const u: User = { token, username, role, full_name: fullName };
    setUser(u);
    localStorage.setItem('medibot_user', JSON.stringify(u));
    void fetchAccessibleCollections(role);

    // Initial greeting
    setMessages([
      {
        id: 'welcome',
        sender: 'bot',
        text: `Welcome back, ${fullName}! You are signed in as '${role}'. You have access to ${role === 'admin' ? 'ALL' : 'your permitted'} document collections. Ask any clinical, nursing, equipment, or SQL analytical question!`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      },
    ]);
  };

  const handleLogout = () => {
    setUser(null);
    setMessages([]);
    localStorage.removeItem('medibot_user');
  };

  const handleSendMessage = async (text: string) => {
    if (!user) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      sender: 'user',
      text,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      const res = await fetch('http://localhost:8000/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${user.token}`,
        },
        body: JSON.stringify({
          question: text,
        }),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || 'Failed to fetch response');
      }

      const data = await res.json();

      const botMsg: Message = {
        id: (Date.now() + 1).toString(),
        sender: 'bot',
        text: data.answer,
        sources: data.sources,
        retrieval_type: data.retrieval_type,
        role: data.role,
        status: data.status,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      setMessages((prev) => [...prev, botMsg]);
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown request error';
      const errorMsg: Message = {
        id: (Date.now() + 1).toString(),
        sender: 'bot',
        text: `Error connecting to MediBot server: ${errorMessage || 'Make sure FastAPI is running on http://localhost:8000'}`,
        status: 'error',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  if (!user) {
    return <LoginScreen onLogin={handleLogin} />;
  }

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      {/* Top Header */}
      <Header
        user={user}
        onLogout={handleLogout}
        onOpenCollections={() => setIsCollectionsOpen(true)}
      />

      {/* Main Chat Feed */}
      <main className="flex-1 overflow-y-auto p-4 md:p-6 space-y-4 max-w-5xl w-full mx-auto">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center p-8 space-y-4">
            <div className="w-16 h-16 rounded-2xl bg-amber-900/20 border border-amber-700/30 flex items-center justify-center shadow-lg">
              <Stethoscope className="w-8 h-8 text-amber-500" />
            </div>
            <div className="space-y-1">
              <h2 className="text-2xl font-bold text-stone-100">Welcome to MediBot RAG 2.0</h2>
              <p className="text-sm text-stone-400 max-w-md">
                Ask natural language medical questions or analytical queries across hospital records. Access control is enforced automatically for <span className="text-amber-300 font-semibold">{user.role}</span>.
              </p>
            </div>
          </div>
        ) : (
          messages.map((msg) => <ChatMessage key={msg.id} message={msg} />)
        )}

        {/* Loading Indicator */}
        {loading && (
          <div className="glass-card p-4 rounded-2xl flex items-center gap-3 animate-pulse max-w-md">
            <div className="w-8 h-8 rounded-xl bg-amber-900/30 text-amber-400 flex items-center justify-center">
              <Sparkles className="w-4 h-4 animate-spin" />
            </div>
            <p className="text-xs text-stone-300 font-medium">
              Searching Qdrant DB / SQL Engine & synthesizing answer...
            </p>
          </div>
        )}

        <div ref={chatBottomRef} />
      </main>

      {/* Bottom Chat Input */}
      <div className="max-w-5xl w-full mx-auto">
        <ChatInput
          onSendMessage={handleSendMessage}
          disabled={loading}
          role={user.role}
        />
      </div>

      {/* Access Permissions Modal */}
      <CollectionsModal
        isOpen={isCollectionsOpen}
        onClose={() => setIsCollectionsOpen(false)}
        user={user}
        accessibleCollections={accessibleCollections}
      />
    </div>
  );
}
