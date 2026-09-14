'use client';

import React, { useState } from 'react';
import { DEMO_ACCOUNTS } from '../constants/demoAccounts';
import { Stethoscope, Shield, Lock, ArrowRight, UserCheck, Activity } from 'lucide-react';
import { DemoAccount, Role } from '../types';

interface LoginScreenProps {
  onLogin: (token: string, username: string, role: Role, fullName: string) => void;
}

const roleColors: Record<string, { bg: string; text: string; border: string }> = {
  doctor: { bg: 'bg-emerald-800/20', text: 'text-emerald-300', border: 'border-emerald-700/40' },
  nurse: { bg: 'bg-lime-800/20', text: 'text-lime-300', border: 'border-lime-700/40' },
  billing_executive: { bg: 'bg-amber-800/20', text: 'text-amber-300', border: 'border-amber-700/40' },
  technician: { bg: 'bg-stone-700/30', text: 'text-stone-300', border: 'border-stone-600/40' },
  admin: { bg: 'bg-orange-800/20', text: 'text-orange-300', border: 'border-orange-700/40' },
};

export default function LoginScreen({ onLogin }: LoginScreenProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const executeLogin = async (u: string, p: string) => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch('http://localhost:8000/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: u, password: p }),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || 'Login failed');
      }

      const data = await res.json();
      onLogin(data.access_token, data.username, data.role, data.full_name);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Could not connect to MediBot API at http://localhost:8000');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!username || !password) {
      setError('Please fill in both username and password.');
      return;
    }
    executeLogin(username, password);
  };

  return (
    <div className="min-h-screen w-full flex items-center justify-center p-4 md:p-8">
      <div className="w-full max-w-5xl grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
        
        {/* Left Column: Branding & Demo Quick Login */}
        <div className="lg:col-span-7 space-y-6">
          <div className="space-y-3">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-amber-900/20 border border-amber-700/30 text-amber-300 text-xs font-semibold uppercase tracking-wider">
              <Activity className="w-3.5 h-3.5 animate-pulse text-amber-400" /> MediAssist Health Network
            </div>
            <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight text-stone-100 flex items-center gap-3">
              <Stethoscope className="w-10 h-10 text-amber-500" /> MediBot
            </h1>
            <p className="text-stone-400 text-sm md:text-base leading-relaxed">
              Internal intelligent clinical assistant with <span className="text-amber-400 font-medium">Qdrant Hybrid Search</span>, <span className="text-lime-400 font-medium">Cross-Encoder Reranking</span>, <span className="text-orange-400 font-medium">SQL RAG</span>, and strict <span className="text-emerald-400 font-medium">Role-Based Access Control (RBAC)</span>.
            </p>
          </div>

          {/* Quick Demo Accounts Selection */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-stone-300 flex items-center gap-2">
                <UserCheck className="w-4 h-4 text-amber-400" /> Demo Role Accounts (Click to Auto-Login)
              </h2>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {DEMO_ACCOUNTS.map((acc: DemoAccount) => {
                const colors = roleColors[acc.role] || roleColors.nurse;
                return (
                  <button
                    key={acc.username}
                    onClick={() => executeLogin(acc.username, acc.password)}
                    disabled={loading}
                    className="glass-card p-3.5 rounded-xl text-left hover:scale-[1.02] active:scale-[0.98] transition-all cursor-pointer group flex flex-col justify-between"
                  >
                    <div>
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="font-semibold text-stone-100 group-hover:text-amber-300 text-sm">
                          {acc.full_name}
                        </span>
                        <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-md border ${colors.bg} ${colors.text} ${colors.border}`}>
                          {acc.role.replace('_', ' ')}
                        </span>
                      </div>
                      <p className="text-xs text-stone-400">{acc.department}</p>
                    </div>

                    <div className="mt-3 flex items-center justify-between text-[11px] text-stone-400 pt-2 border-t border-stone-700/40">
                      <span>Collections: <strong className="text-stone-300">{acc.accessible_collections.length}</strong></span>
                      <span className="text-amber-400 font-medium group-hover:translate-x-1 transition-transform flex items-center gap-1">
                        Sign In <ArrowRight className="w-3 h-3" />
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Right Column: Manual Login Form */}
        <div className="lg:col-span-5">
          <div className="glass-panel p-6 md:p-8 rounded-2xl border border-stone-700/50 space-y-6">
            <div className="space-y-1 text-center">
              <div className="w-12 h-12 rounded-xl bg-amber-900/20 border border-amber-700/30 flex items-center justify-center mx-auto mb-3">
                <Lock className="w-6 h-6 text-amber-400" />
              </div>
              <h3 className="text-xl font-bold text-stone-100">Staff Login</h3>
              <p className="text-xs text-stone-400">Enter your credentials to access MediBot</p>
            </div>

            {error && (
              <div className="p-3 rounded-lg bg-orange-950/40 border border-orange-700/40 text-orange-300 text-xs flex items-center gap-2">
                <Shield className="w-4 h-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-stone-300 uppercase tracking-wider mb-1.5">
                  Username
                </label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="e.g. nurse.priya"
                  className="w-full bg-stone-900/90 border border-stone-700/50 rounded-xl px-4 py-2.5 text-sm text-stone-100 placeholder-stone-500 focus:outline-none focus:border-amber-500 transition-colors"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-stone-300 uppercase tracking-wider mb-1.5">
                  Password
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full bg-stone-900/90 border border-stone-700/50 rounded-xl px-4 py-2.5 text-sm text-stone-100 placeholder-stone-500 focus:outline-none focus:border-amber-500 transition-colors"
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 rounded-xl bg-gradient-to-r from-amber-600 to-amber-700 hover:from-amber-500 hover:to-amber-600 text-stone-100 font-semibold text-sm shadow-lg shadow-amber-900/30 transition-all flex items-center justify-center gap-2 cursor-pointer"
              >
                {loading ? (
                  <span className="inline-block animate-spin border-2 border-stone-100 border-t-transparent rounded-full w-4 h-4" />
                ) : (
                  <>
                    Sign In to MediBot <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </button>
            </form>
          </div>
        </div>

      </div>
    </div>
  );
}
