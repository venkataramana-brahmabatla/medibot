'use client';

import React, { useState } from 'react';
import { Stethoscope, Shield, Lock, ArrowRight, Activity } from 'lucide-react';
import { Role } from '../types';

interface LoginScreenProps {
  onLogin: (token: string, username: string, role: Role, fullName: string) => void;
}

export default function LoginScreen({ onLogin }: LoginScreenProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const executeLogin = async (u: string, p: string) => {
    setLoading(true);
    setError('');
    try {
      const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';
      const res = await fetch(`${apiBaseUrl}/login`, {
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
      setError(err instanceof Error ? err.message : 'Could not connect to MediBot API');
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
      <div className="w-full max-w-xl">
        <div className="space-y-6">
          <div className="space-y-3">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-amber-900/20 border border-amber-700/30 text-amber-300 text-xs font-semibold uppercase tracking-wider">
              <Activity className="w-3.5 h-3.5 animate-pulse text-amber-400" /> MediAssist Health Network
            </div>
            <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight text-stone-100 flex items-center gap-3">
              <Stethoscope className="w-10 h-10 text-amber-500" /> MediBot
            </h1>
            <p className="text-stone-400 text-sm md:text-base leading-relaxed">
              Internal clinical and operational assistant for MediAssist staff.
            </p>
          </div>
        </div>

        <div className="mt-8">
          <div className="glass-panel p-6 md:p-8 rounded-2xl border border-stone-700/50 space-y-6">
            <div className="space-y-1 text-center">
              <div className="w-12 h-12 rounded-xl bg-amber-900/20 border border-amber-700/30 flex items-center justify-center mx-auto mb-3">
                <Lock className="w-6 h-6 text-amber-400" />
              </div>
              <h3 className="text-xl font-bold text-stone-100">Staff Login</h3>
              <p className="text-xs text-stone-400">Local demo sign-in only; production identity login is not configured.</p>
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
                  autoComplete="username"
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
                  autoComplete="current-password"
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
